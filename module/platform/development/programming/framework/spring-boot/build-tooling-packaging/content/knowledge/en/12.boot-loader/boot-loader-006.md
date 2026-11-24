# Configuring PropertiesLauncher with loader.path and loader.main in Spring Boot

## 1. Goal and Mental Model

Spring Boot packages Java applications into executable JARs, yet not every executable JAR uses the same **Boot Loader**. With a standard JAR, `JarLauncher` normally loads classes in `BOOT-INF/classes` and dependency JARs nested in `BOOT-INF/lib`. When an application needs to pick up **extra JARs from an external directory** or needs to **select the main class at startup**, Spring Boot provides `PropertiesLauncher`.

Two central properties:

- `loader.path`: specifies external directories, archives, or locations added to the **classpath managed by Boot Loader**.
- `loader.main`: specifies the **fully qualified class name** with `public static void main(String[] args)` that `PropertiesLauncher` will invoke.

Conceptual example:

```text
/opt/loader-demo/
├── app.jar                           # Boot archive with PropertiesLauncher
├── lib/
│   └── greeting-extension.jar        # Externally deployed JAR
└── config/
    └── loader.properties             # Loader configuration

        java -Dloader.path=/opt/loader-demo/lib -jar app.jar
                             |
                             v
               PropertiesLauncher (Main-Class)
                             |
              +--------------+---------------+
              |                              |
        BOOT-INF/classes                /opt/loader-demo/lib
        BOOT-INF/lib                    greeting-extension.jar
              |                              |
              +--------------+---------------+
                             v
                 loader.main or Start-Class
                             |
                             v
                 app's main(String[] args)
```

**Key takeaway:** `PropertiesLauncher` runs **before** the Spring Boot ApplicationContext is created. `loader.path` is a classpath setting of the **bootstrap launcher**, not the Spring property `spring.config.location`. `loader.main` selects the `main` method, not a controller name or Spring bean name.

This lesson uses **Java 17+ and Spring Boot 3.5.0** for consistent plugin/loader configuration. This is a pinned version for the example, not a claim that it is the latest release. When using Spring Boot 2.x or 4.x, check the launcher namespace and packaging mechanism for your actual version.

## 2. Distinguishing JarLauncher, WarLauncher, and PropertiesLauncher

Boot Loader is the set of bootstrap classes placed inside an executable archive to set up a classloader capable of reading **nested JARs**. In Spring Boot 3.5:

| Launcher | Default scenario | Classpath from archive | Supports loader.path? |
| --- | --- | --- | --- |
| `org.springframework.boot.loader.launch.JarLauncher` | Standard executable JAR | `BOOT-INF/classes`, `BOOT-INF/lib` | Not via `PropertiesLauncher` mechanism |
| `org.springframework.boot.loader.launch.WarLauncher` | Executable WAR | `WEB-INF/classes`, `WEB-INF/lib`, and `WEB-INF/lib-provided` | Not via `PropertiesLauncher` mechanism |
| `org.springframework.boot.loader.launch.PropertiesLauncher` | Flexible layout, external classpath, main selection | Standard archive locations plus launcher config | **Yes**: `loader.path`, `loader.main`, and related properties |

Merely adding `-Dloader.path=/some/lib` to a **JarLauncher** command does not mean JarLauncher will read that path. With the Spring Boot Maven Plugin, choose `<layout>ZIP</layout>` (or `DIR`, an alias for ZIP) to produce an archive using `PropertiesLauncher`. `ZIP` here is **the Boot plugin's layout name**, not a requirement to rename your `.jar` extension to `.zip`.

The **Manifest** for a standard Boot JAR typically has:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.loader.LoaderDemoApplication
```

When using the ZIP/PropertiesLauncher layout, expect:

```text
Main-Class: org.springframework.boot.loader.launch.PropertiesLauncher
Start-Class: com.example.loader.LoaderDemoApplication
```

`Main-Class` is the launcher class invoked first by the JVM. `Start-Class` is the Spring Boot application main, invoked by the launcher after preparing the classpath. `loader.main` can override the launcher's main selection at runtime; it **does not modify the manifest contents** of the JAR file.

Maven/Spring Boot plugins may add other manifest attributes; the lines above are the **representative entries to verify**, not the complete manifest. Launcher package names changed across some Spring Boot versions, so do not copy Boot 2.x launcher paths into a Boot 3.5 JAR.

## 3. Class-Loading Mechanism of PropertiesLauncher

A `java -jar app.jar` execution can be understood as:

1. Java reads `META-INF/MANIFEST.MF`, locating `Main-Class`.
2. If the manifest points to `PropertiesLauncher`, the JVM calls `PropertiesLauncher.main(String[])`.
3. The launcher reads its configuration sources: system properties, environment variables, launcher config file, and manifest, per version rules.
4. The launcher prepares a classloader for classes/resources inside the archive and permitted `loader.path` locations.
5. The launcher determines the main class: uses `loader.main` if validly specified, otherwise usually takes `Start-Class` from the manifest.
6. The launcher invokes `main(String[] args)` on the selected class. Only from here does Spring Boot start initializing the ApplicationContext, embedded web server, beans, and application configs.

```text
java -jar
  |
  v
META-INF/MANIFEST.MF
  |
  +-- Main-Class = PropertiesLauncher
                       |
                       +-- resolve loader.home
                       +-- read loader.properties / loader settings
                       +-- resolve loader.path and BOOT-INF/*
                       +-- choose loader.main or Start-Class
                       |
                       v
                JVM context classloader
                       |
                       v
                main(String[] args)
                       |
                       v
                SpringApplication.run(...)
```

Paths `BOOT-INF/classes` and `BOOT-INF/lib` inside the archive are still used by PropertiesLauncher in a normal JAR model; `loader.path` **appends** new locations rather than deleting packaged dependencies. When two JARs inadvertently contain the same class, search order can cause version conflicts; do not treat `loader.path` as an official dependency replacement system with Maven-like conflict resolution.

## 4. Launcher Configuration Table You Need to Know

| Property | Purpose | Example | Notes |
| --- | --- | --- | --- |
| `loader.path` | Extra classpath (comma-separated list) | `lib,plugins/analytics.jar` | Relative entries are resolved against `loader.home` |
| `loader.main` | Class containing static main to execute | `com.example.loader.AlternateMain` | Must exist in the constructed classloader |
| `loader.home` | Base directory for relative paths and finding external config | `/opt/loader-demo` | Usually defaults to the JVM working directory (`user.dir`) |
| `loader.config.name` | Launcher config filename without extension | `loader` → `loader.properties` | Can be explicitly set to avoid picking the wrong file |
| `loader.config.location` | Explicit location of launcher config file | `file:/opt/loader-demo/config/loader.properties` | Accepts loader-style locations, not Spring config data |
| `loader.args` | Default application arguments | `--server.port=9090` | Prepended to args before invoking main |
| `loader.system` | Allows exporting loaded launcher properties to Java System properties | `false` | False by default; consider avoiding leaks/collisions |

Commonly used corresponding names:

| Loader property | Environment variable | Manifest attribute |
| --- | --- | --- |
| `loader.path` | `LOADER_PATH` | `Loader-Path` |
| `loader.home` | `LOADER_HOME` | `Loader-Home` |
| `loader.main` | `LOADER_MAIN` | `Start-Class` |
| `loader.args` | `LOADER_ARGS` | `Loader-Args` |
| `loader.config.location` | `LOADER_CONFIG_LOCATION` | `Loader-Config-Location` |
| `loader.system` | `LOADER_SYSTEM` | `Loader-System` |

Three ways to express a path:

```bash
# Java system property, only works when the launcher is actually PropertiesLauncher:
java -Dloader.path=/opt/loader-demo/lib -jar app.jar

# Environment variable on Linux/macOS:
LOADER_PATH=/opt/loader-demo/lib java -jar app.jar
```

```properties
# loader.properties file:
loader.path=/opt/loader-demo/lib
```

**Do not equate** `LOADER_MAIN` with `SPRING_MAIN_*`, or `loader.path` with `spring.config.location`. The former belongs to Boot Loader; the latter belongs to Spring Boot application configuration.

### Precedence Order and Config File Rules

According to the Boot 3.x specification documentation, `PropertiesLauncher` values can come from environment variables, Java system properties, `loader.properties`, an exploded archive's manifest, and the archive's manifest. Among sources sharing the same key, documented precedence is typically **environment → system → loader.properties → manifest**, where the key supports those sources. Do not guess precedence across override files scattered in multiple places; use a single configuration source in real deployments and verify the JAR of your running version.

One place `loader.properties` is looked up is the `loader.home` directory; other locations can include the classpath root and `BOOT-INF/classes`. You can point directly to the file with `-Dloader.config.location=file:/.../loader.properties`. Some defaults/lookup locations have changed and differed in API docs across versions; **the safe operational practice is configuring an explicit file location** in environments requiring reproducibility.

## 5. Complete Example: Spring Boot 3.5.0 + Maven ZIP Layout

The lab builds a web app. When run **without an external JAR**, the endpoint returns a built-in value. When a JAR is added to `loader.path`, the same endpoint finds the external class and returns a different value. A second main class demonstrates that `loader.main` can switch the entry point.

**Requirements:**

- JDK 17 or newer and Maven supporting Spring Boot 3.5.
- Access to Maven Central or an authorized repository manager to download dependencies/plugins.
- Bash/Linux/macOS terminal for `mkdir`, `javac`, `jar`, and `curl` commands. On Windows you can run Git Bash or adapt directory creation commands for PowerShell.
- This project is a standalone example; do not paste it into an existing Maven/Gradle project without merging POMs properly.

Structure:

```text
loader-demo/
├── pom.xml
├── src/
│   └── main/java/com/example/loader/
│       ├── LoaderDemoApplication.java
│       └── AlternateMain.java
├── extensions-src/
│   └── com/example/extra/GreetingExtension.java
├── extension-classes/                  # created by javac, do not commit
├── external-libs/
│   └── greeting-extension.jar          # created by jar, NOT inside app.jar
└── target/
    └── loader-demo-0.0.1-SNAPSHOT.jar  # repackaged by Maven
```

### 5.1. Complete pom.xml File

**`pom.xml`:**

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
    <artifactId>loader-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>loader-demo</name>
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
                <configuration>
                    <mainClass>com.example.loader.LoaderDemoApplication</mainClass>
                    <layout>ZIP</layout>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`<layout>ZIP</layout>` is the **key** setting telling the Boot plugin to use `PropertiesLauncher` as the manifest `Main-Class`. `<mainClass>...LoaderDemoApplication</mainClass>` explicitly specifies the default entry point; this matters because the project also has `AlternateMain` and the plugin need not guess which main class to pick.

Because the POM inherits `spring-boot-starter-parent` and declares `spring-boot-maven-plugin`, the `repackage` execution is already configured in the `package` phase. Do not add a second `repackage` execution with another ID. If the project **does not** use the starter parent, you must bind the `spring-boot:repackage` goal separately to the package phase and pin an appropriate plugin version.

### 5.2. Main Application and Endpoint to Test the External Class

**`src/main/java/com/example/loader/LoaderDemoApplication.java`:**

```java
package com.example.loader;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class LoaderDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(LoaderDemoApplication.class, args);
    }

    @GetMapping("/greet")
    public String greet(
            @RequestParam(name = "name", defaultValue = "Lan") String name) {
        try {
            ClassLoader contextLoader =
                    Thread.currentThread().getContextClassLoader();

            Class<?> extension = Class.forName(
                    "com.example.extra.GreetingExtension", true, contextLoader);

            Object value = extension
                    .getMethod("greet", String.class)
                    .invoke(null, name);

            return (String) value;
        }
        catch (ClassNotFoundException ex) {
            return "builtin:" + name;
        }
        catch (ReflectiveOperationException ex) {
            throw new IllegalStateException("Invalid greeting extension", ex);
        }
    }
}
```

In this example, the application **intentionally uses reflection** to avoid a compile-time dependency on the external JAR. That is the easiest way to observe `loader.path` genuinely extending the classpath. In larger systems, sharing a common interface with `ServiceLoader`, SPI, or a clearly designed/versioned Spring bean contract is more maintainable. Reflection here is an educational illustration, not a recommendation for a full plugin platform.

`Thread.currentThread().getContextClassLoader()` is the appropriate classloader when a Boot app has been configured by the launcher. Using `ClassLoader.getSystemClassLoader()` to look up classes inside nested JARs can fail, because the JVM system classloader does not necessarily understand Boot Loader's nested dependency layout.

Without the external `GreetingExtension`, the controller returns **`builtin:Lan`** or `builtin:<name>`. If the class exists yet the method signature is wrong or reflection fails, the application throws an exception rather than silently treating a broken plugin as absent. This separates **JAR not loaded** from **corrupt or incompatible JAR**.

### 5.3. Alternate Main Class to Test loader.main

**`src/main/java/com/example/loader/AlternateMain.java`:**

```java
package com.example.loader;

public final class AlternateMain {

    private AlternateMain() {
    }

    public static void main(String[] args) {
        String value = (args.length == 0) ? "no-args" : args[0];
        System.out.println("alternate-main:" + value);
    }
}
```

`AlternateMain` **does not start SpringApplication**, so selecting this main brings up no HTTP server. This is the clearest test to confirm `loader.main` actually overrode `Start-Class`.

### 5.4. Build the Executable JAR

Run from the project root:

```bash
mvn -B -ntp clean package
```

With the sample POM, the primary output file created is usually:

```text
target/loader-demo-0.0.1-SNAPSHOT.jar
```

And the original JAR before repackaging is normally kept with a `.jar.original` suffix. `mvn package` builds the Maven JAR first, and `spring-boot:repackage` rewraps it into an executable archive. `layout=ZIP` still creates a **JAR with the `.jar` extension**, except the manifest points to `PropertiesLauncher`.

If the repository uses Maven Wrapper, invoke `./mvnw -B -ntp clean package` (Windows: `mvnw.cmd`). This POM has no tests, so `package` may report no tests to run; that is not a runtime error. In real projects, do not skip unit/integration tests when preparing release artifacts.

### 5.5. Inspect the Launcher in the JAR

```bash
jar tf target/loader-demo-0.0.1-SNAPSHOT.jar
```

Key entries will include:

```text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/PropertiesLauncher.class
BOOT-INF/classes/com/example/loader/LoaderDemoApplication.class
BOOT-INF/classes/com/example/loader/AlternateMain.class
BOOT-INF/lib/...
```

`BOOT-INF/lib/...` above is a **placeholder describing the dependency group**, not an actual JAR filename. Inspect the manifest directly in Bash:

```bash
unzip -p target/loader-demo-0.0.1-SNAPSHOT.jar META-INF/MANIFEST.MF
```

Two lines to look for:

```text
Main-Class: org.springframework.boot.loader.launch.PropertiesLauncher
Start-Class: com.example.loader.LoaderDemoApplication
```

The manifest may contain many more lines. If you see `Main-Class: org.springframework.boot.loader.launch.JarLauncher`, double-check `<layout>ZIP</layout>` and make sure you are inspecting the right artifact. Merely having `PropertiesLauncher.class` inside the JAR is not enough: **the manifest's Main-Class** decides which launcher `java -jar` invokes.

## 6. Hands-On loader.path: Loading a JAR Completely Outside the Archive

### 6.1. Create an External JAR Using JDK 17

Create file **`extensions-src/com/example/extra/GreetingExtension.java`** in the project root, **not** inside the app's `src/main/java`:

```java
package com.example.extra;

public final class GreetingExtension {

    private GreetingExtension() {
    }

    public static String greet(String name) {
        return "external:" + name;
    }
}
```

Use the JDK's Java compiler:

```bash
mkdir -p extension-classes external-libs
javac --release 17 -d extension-classes \
  extensions-src/com/example/extra/GreetingExtension.java

jar --create \
  --file external-libs/greeting-extension.jar \
  -C extension-classes .
```

`javac --release 17` targets Java 17 bytecode/APIs for this simple source. `jar --create` packages the compiled class into a standalone JAR. Verify:

```bash
jar tf external-libs/greeting-extension.jar
```

Expect entry:

```text
com/example/extra/GreetingExtension.class
```

This JAR **is not** packaged into `BOOT-INF/lib` by Maven because its source lies outside `src/main/java` and the POM declares no dependency on that artifact. Thus only extending the runtime classpath via the launcher enables the app to find that class.

### 6.2. Run Without loader.path

From the project root, run:

```bash
java -jar target/loader-demo-0.0.1-SNAPSHOT.jar
```

In another terminal:

```bash
curl -fsS 'http://localhost:8080/greet?name=Lan'
```

**Expected response body:**

```text
builtin:Lan
```

If port 8080 is occupied by another application or a Spring Boot config overrides the port, change the port at launch:

```bash
java -jar target/loader-demo-0.0.1-SNAPSHOT.jar --server.port=9090
```

Then use `http://localhost:9090/greet?name=Lan`. Stop the JVM with Ctrl+C before changing startup modes to avoid two processes fighting over port 8080.

### 6.3. Run with loader.path

Run:

```bash
java -Dloader.path=external-libs \
  -jar target/loader-demo-0.0.1-SNAPSHOT.jar
```

The command above assumes **the current working directory is the project root**, so `external-libs` points to the directory containing `greeting-extension.jar`. PropertiesLauncher will pick up JARs in that path.

Call:

```bash
curl -fsS 'http://localhost:8080/greet?name=Lan'
```

**Expected response body:**

```text
external:Lan
```

This is an observable difference using the exact same app JAR **without rebuilding the application**: without `loader.path`, the extension class is absent; with it, the class enters the application's classloader.

The classloader path is set up **when the JVM process starts**. Copying new JARs into `external-libs` after Spring Boot has started does not guarantee immediate discovery; normally a JVM restart is needed to bring new archives onto the classpath.

### 6.4. Using Absolute Paths, Environment Variables, and Multiple Locations

On Linux/macOS, if not running from the project root, avoid relying on the working directory:

```bash
java -Dloader.path=/opt/loader-demo/lib \
  -jar /opt/loader-demo/app.jar
```

Or use an environment variable:

```bash
LOADER_PATH=/opt/loader-demo/lib \
  java -jar /opt/loader-demo/app.jar
```

Multiple entries can be declared, separated by **commas**:

```bash
java -Dloader.path=/opt/loader-demo/lib,/opt/loader-demo/plugins \
  -jar /opt/loader-demo/app.jar
```

Those two directories are illustrative deployment structures that must exist and hold valid JARs. In PowerShell:

```powershell
$env:LOADER_PATH = "C:\apps\loader-demo\lib"
java -jar C:\apps\loader-demo\app.jar
```

Use appropriate Windows paths; do not copy `/opt/...` to Windows. When targeting a single archive directly instead of a directory:

```bash
java -Dloader.path=/opt/loader-demo/lib/greeting-extension.jar \
  -jar /opt/loader-demo/app.jar
```

`loader.path` entries can be resource directories, specific JARs/ZIPs, or supported archive directory paths; do not treat this as Maven dependency syntax or repository URLs. `loader.path` does not automatically download artifacts from Maven Central. Building/publishing external JARs still requires a separate dependency management and provenance control process.

### 6.5. Why Not Use Regular -cp?

With an executable Boot JAR, `java -jar app.jar` uses the manifest and Boot Loader; the JVM's `-cp` does not automatically know how to resolve nested `BOOT-INF/lib/*.jar`. Syntax like:

```bash
java -cp external-libs/* -jar app.jar
```

is not a reliable way to extend an executable JAR's classpath: under `-jar`, the JVM handles the classpath per the executable archive rather than using `-cp` as when invoking an ordinary main class. With Spring Boot `PropertiesLauncher`, **`loader.path`** is the mechanism designed for additional classpaths.

## 7. Hands-On loader.main: Switching the Main Class Without Rebuilding

The example's default manifest has `Start-Class: com.example.loader.LoaderDemoApplication`, so running normally brings up the web server.

To **switch the main class** to `AlternateMain`:

```bash
java -Dloader.main=com.example.loader.AlternateMain \
  -jar target/loader-demo-0.0.1-SNAPSHOT.jar \
  demo
```

**Stdout printed by `AlternateMain` (excluding JVM/launcher logs):**

```text
alternate-main:demo
```

This run does not start an embedded web server, because `AlternateMain.main` merely prints one line and exits. The `demo` argument after the JAR name is forwarded to the alternate main's `String[] args`.

You can use an environment variable:

```bash
LOADER_MAIN=com.example.loader.AlternateMain \
  java -jar target/loader-demo-0.0.1-SNAPSHOT.jar demo
```

Or put the main class in `loader.properties`:

```properties
loader.main=com.example.loader.AlternateMain
```

**Do not confuse arguments before vs. after `-jar`:**

- `java -Dloader.main=com.example.loader.AlternateMain -jar app.jar`: Java system property read by the launcher **before choosing main**.
- `java -jar app.jar --loader.main=com.example.loader.AlternateMain`: this is an **application argument** sent to the already-chosen main; do not expect PropertiesLauncher to switch main this way.
- `java -jar app.jar --spring.profiles.active=dev`: Spring application config **after** main is selected; does not change the launcher main.
- `-Dloader.main=...` works via PropertiesLauncher's mechanism, distinct from `-Dstart.class=...` of a Maven build script.

`loader.main` must specify a class that actually exists on the classpath PropertiesLauncher just built. That class must have an accessible static `main(String[])`. Entering the wrong package causes a **main class not found** error right at bootstrap, before Spring beans are created.

### Can the Main Class Live Inside an External JAR?

Yes, if a valid main class sits inside an archive loaded via `loader.path`. General example:

```bash
java -Dloader.path=/opt/loader-demo/plugins \
  -Dloader.main=com.example.plugin.PluginEntryPoint \
  -jar /opt/loader-demo/app.jar
```

`com.example.plugin.PluginEntryPoint` here is an **illustrative** name, not part of the demo we wrote. To actually run, the external JAR must contain that class with `public static void main(String[] args)`, matching dependencies, and classloader compatibility. Never use `loader.main` to run arbitrary untrusted code; it grants permission to execute Java code inside the application process itself.

## 8. The loader.properties File and loader.home

If you pass many `-Dloader.*` flags on the command line every time, configuration becomes hard to manage. `PropertiesLauncher` supports a launcher configuration file, usually named `loader.properties`.

Linux deployment example:

```text
/opt/loader-demo/
├── app.jar
├── config/
│   └── loader.properties
└── lib/
    └── greeting-extension.jar
```

**`/opt/loader-demo/config/loader.properties`:**

```properties
loader.path=lib
loader.main=com.example.loader.LoaderDemoApplication
```

Launch command with explicit location:

```bash
java \
  -Dloader.home=/opt/loader-demo \
  -Dloader.config.location=file:/opt/loader-demo/config/loader.properties \
  -jar /opt/loader-demo/app.jar
```

**Explanation:**

- `loader.home=/opt/loader-demo` serves as the base to resolve `loader.path=lib` into `/opt/loader-demo/lib`.
- `loader.config.location=file:/opt/loader-demo/config/loader.properties` points **explicitly to the launcher config file**. Independent of whether the file sits in CWD or is embedded in the JAR.
- `loader.main=...LoaderDemoApplication` can be omitted since the manifest `Start-Class` is already right; kept here solely to illustrate control capability.
- The `file:/...` path is a Linux/Unix URI example. On Windows use appropriate file URIs and escaping.

If the launcher file sits in `loader.home` under a recognized name, you can use `-Dloader.home=/opt/loader-demo` and default `loader.properties` discovery. However, across multi-environment deployments and to avoid ambiguity, specifying an **explicit location** is clearer.

### 8.1. Difference Between loader.config.name and loader.config.location

- `loader.config.name` specifies the **filename** without `.properties`, e.g., `loader`; the launcher searches for `loader.properties` in supported locations.
- `loader.config.location` specifies a concrete **file address**, e.g., `file:/opt/loader-demo/config/loader.properties`.
- Do not use `loader.path` hoping the launcher will discover `loader.properties`: **the lookup path for the launcher config file and the expanded classpath loaded via loader.path are two separate things**.

Example running with an explicitly specified name and the file in the project working directory:

```bash
java -Dloader.config.name=loader \
  -Dloader.home=. \
  -jar target/loader-demo-0.0.1-SNAPSHOT.jar
```

The example above assumes a valid `./loader.properties` exists. If you prefer not to place the file in the project root, use `loader.config.location=file:/absolute/path/loader.properties` as in the previous section.

### 8.2. Do Not Confuse with Spring application.properties

The two files have different responsibilities:

| File | Processed by | Which keys go here? |
| --- | --- | --- |
| `loader.properties` | `PropertiesLauncher` during bootstrap | `loader.path`, `loader.main`, `loader.home`, loader options |
| `application.properties` | Spring Boot Environment/Config Data **after main runs** | `server.port`, `spring.profiles.active`, datasource, logging, etc. |

Putting `loader.path=lib` inside `application.properties` expecting PropertiesLauncher to read it as a loader setting is something **you should not rely on** in new designs. Keep the launcher file and application configuration clearly separated.

To have Spring Boot load application config outside the JAR, use a Spring Boot supported mechanism, e.g.:

```bash
java -Dloader.path=/opt/loader-demo/lib \
  -jar /opt/loader-demo/app.jar \
  --spring.config.additional-location=optional:file:/opt/loader-demo/config/
```

`--spring.config.additional-location` is an **application argument** processed by Spring after main has started. It does not change the loader's JAR paths. The `config` directory must contain appropriately named Spring config files, such as `application.properties`.

**Security:** if `loader.properties` or `application.properties` contains sensitive info, keep it outside Git/JAR with minimal file permissions. Still, merely having `loader.path` does not keep secrets safe: any extended JAR can read data/process env while running inside the same JVM.

## 9. Choosing a Configuration Source: -D, Environment, loader.properties, or Manifest

Three most common ways for `loader.path`:

```bash
# Approach 1: Java system property
java -Dloader.path=/opt/loader-demo/lib -jar /opt/loader-demo/app.jar

# Approach 2: Environment variable (Bash)
LOADER_PATH=/opt/loader-demo/lib java -jar /opt/loader-demo/app.jar

# Approach 3: loader.properties at explicit location
java -Dloader.config.location=file:/opt/loader-demo/config/loader.properties \
  -jar /opt/loader-demo/app.jar
```

Pick **one primary source** per deployment to prevent conflicts. If multiple sources specify `loader.path` or `loader.main`, which value wins depends on the precedence rules of your running PropertiesLauncher version; do not assume Spring Boot Application Environment's precedence applies to the launcher. Reliable verification means checking the manifest, JVM command, environment, and the example endpoint.

Declaring `Loader-Path` or `Start-Class` in the manifest at build time can be useful when every environment shares the same layout, yet when using the Spring Boot Maven plugin you should configure **`mainClass`/layout in the plugin** rather than manually editing the manifest after repackaging. Modifying a JAR file after signing/checksumming also breaks artifact integrity.

### 9.1. Commas in loader.path vs. CLASSPATH Separators

`loader.path` uses **commas** to separate multiple entries. Do not mistakenly use Unix classpath colons `:` or Windows classpath semicolons `;`:

```properties
loader.path=/opt/loader-demo/lib,/opt/loader-demo/plugins
```

This is NOT:
```properties
loader.path=/opt/loader-demo/lib:/opt/loader-demo/plugins
```

For directory or JAR names containing spaces, set values properly in the properties file or escape/quote for the shell; prefer stable deployment paths free of special characters, unnecessary spaces, or commas in names.

### 9.2. Classpath Order and Duplicate Class Names

When `loader.path` has multiple entries, earlier entries generally take precedence over later ones per the launcher's contract. Yet never rely on class shadowing to "patch" dependencies:

- Two JARs containing the same `com.example.Util` can pick the wrong version, causing `NoSuchMethodError` or `LinkageError`.
- Dependencies inside `BOOT-INF/lib` may already be used by the loader at startup; do not assume an external JAR will safely override them.
- Duplicate resources (such as `META-INF/services/...`) may follow lookup semantics different from normal class loading.
- Mismatched Spring Boot/Java versions can break bytecode and dependency APIs.

With a plugin architecture, define a small API/SPI, manage compatibility, and version explicitly. If true isolation between untrusted plugins is required, **a single shared PropertiesLauncher classloader is insufficient**; consider isolating in separate processes/containers or using a plugin framework with clear classloader policies.

## 10. Difference Between loader.main and SpringApplication

`loader.main` is **the class containing main** selected by the launcher. That class may invoke `SpringApplication.run(...)`, though it does not have to.

What the demo proves:

- Without `loader.main`: the launcher reads `Start-Class` and runs `LoaderDemoApplication`, bringing up the HTTP server.
- `loader.main=...AlternateMain`: the launcher runs `AlternateMain`, only printing a console line, with no Spring context/web server.
- `loader.main=...MissingMain`: the launcher cannot find the class; the build still succeeds, but **runtime fails**.
- If the chosen main resides in an external JAR, ensure that external JAR is loaded via `loader.path` before main is invoked.

In a multi-entry-point application, use `loader.main` to switch run modes **only by intentional design**. Do not use it to "pick a controller" or "switch Spring profiles"; use `--spring.profiles.active=...`, the `SPRING_PROFILES_ACTIVE` environment variable, or Spring config files for profiles.

**Distinguish the lifecycles:**

| Change | Rebuild JAR needed? | JVM restart needed? |
| --- | --- | --- |
| Change `loader.path` on run command for new run | No | Yes, because classpath is built at startup |
| Change `loader.main` for new run | No | Yes, because main is picked at startup |
| Update external JAR contents | No app JAR rebuild needed | Normally yes, to load new classes/versions |
| Change `<layout>ZIP</layout>` in Boot plugin | **Yes** | Yes, run the new artifact |
| Change `<mainClass>` to alter manifest Start-Class | **Yes** | Yes |
| Change `--server.port`, `SPRING_PROFILES_ACTIVE` | No | Usually yes; app reads config at startup |

`loader.main` is not a hot-reload option capable of swapping main in an already-running JVM. When separate batch tasks are needed, consider packaging appropriate modules/apps rather than maintaining one artifact with many hard-to-control mains.

## 11. Spring Boot Maven Plugin: ZIP/DIR Layout and repackage

Maven lifecycle for the example:

```text
mvn clean package
    |
    +-- compile Java sources
    +-- test (if any)
    +-- maven-jar-plugin:jar creates source JAR
    +-- spring-boot-maven-plugin:repackage
          |
          +-- places application classes in BOOT-INF/classes
          +-- places dependency JARs in BOOT-INF/lib
          +-- adds Boot Loader classes
          +-- uses ZIP layout => Main-Class PropertiesLauncher
```

`ZIP` / `DIR` in the Boot Maven Plugin is a JAR-like layout that starts with `PropertiesLauncher`. `NONE` is a different layout without a bootstrap loader; do not use `NONE` if you still want `java -jar` to automatically load nested dependencies via PropertiesLauncher.

Minimal plugin snippet when using the Spring Boot starter parent and an explicit app main:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <configuration>
                <layout>ZIP</layout>
                <mainClass>com.example.loader.LoaderDemoApplication</mainClass>
            </configuration>
        </plugin>
    </plugins>
</build>
```

This is a POM snippet, not a complete `pom.xml` file. With the starter parent, **do not declare the repackage goal a second time**. Without the starter parent, you must declare the plugin version, repackage execution in the `package` phase, and appropriate Java compiler configuration.

### What About Gradle?

Boot Loader concepts **do not depend on Maven**, though how Gradle configures the `bootJar` task differs from the Maven plugin. Do not copy XML `<layout>ZIP</layout>` verbatim into `build.gradle` or `build.gradle.kts`. When using Gradle, check the version-specific documentation for `BootJar`/manifest and how to produce an executable archive whose `Main-Class` is genuinely `PropertiesLauncher`. `loader.path` and `loader.main` at **JVM runtime** only work if the final JAR file contains the matching launcher. Inspecting `META-INF/MANIFEST.MF` is the universal verification step across build tools.

## 12. Real-World Deployment on VMs, Docker, and Kubernetes

### 12.1. VM/Host: Stable External-to-JAR Layout

A clear deployment structure:

```text
/opt/loader-demo/
├── app.jar                     # fixed per release
├── lib/
│   └── greeting-extension.jar # vetted, explicit version
├── config/
│   ├── loader.properties
│   └── application.properties
└── logs/                       # runtime logs per separate config
```

`loader.properties`:

```properties
loader.path=lib
loader.main=com.example.loader.LoaderDemoApplication
```

Startup command:

```bash
java \
  -Dloader.home=/opt/loader-demo \
  -Dloader.config.location=file:/opt/loader-demo/config/loader.properties \
  -jar /opt/loader-demo/app.jar \
  --spring.config.additional-location=optional:file:/opt/loader-demo/config/
```

`loader.home` and `loader.config.location` are **JVM options placed before `-jar`**. The Spring application option `--spring.config.additional-location` goes **after the JAR name**, because it is passed to `main(String[] args)`.

Files under `lib` should be placed by controlled build/release pipelines, not an arbitrary user-upload directory. When replacing a JAR used by the classloader, deploy via immutable artifacts and controlled rolling restarts rather than overwriting a JAR file mid-run.

### 12.2. Docker: Fixed App Packaging, Mounted External Folder

Illustrative Dockerfile with the Maven-built JAR from Section 5:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /opt/app
COPY target/loader-demo-0.0.1-SNAPSHOT.jar /opt/app/app.jar
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-Dloader.path=/opt/app/extensions", "-jar", "/opt/app/app.jar"]
```

Build the image:

```bash
mvn -B -ntp clean package
docker build -t loader-demo:dev .
```

Assuming `external-libs/greeting-extension.jar` was created in Section 6. Run the container and **mount the folder read-only**:

```bash
docker run --rm \
  -p 127.0.0.1:8080:8080 \
  -v "$PWD/external-libs:/opt/app/extensions:ro" \
  loader-demo:dev
```

When using Bash with a Docker daemon/host setup supporting this volume mount, `curl -fsS 'http://localhost:8080/greet?name=Lan'` expects **`external:Lan`**. If the volume lacks a compatible JAR, the result is **`builtin:Lan`**. On Windows PowerShell, adjust host path syntax and line continuation. This is a **development** environment example and excludes production networking/secret/repository policies.

Key points:

- `-Dloader.path=/opt/app/extensions` is passed directly to the application JVM (distinct from Gradle `-D` on the build JVM).
- Mounting `:ro` restricts overwriting extension files from inside the container; however, you must still secure the JAR source before mounting.
- The image's startup still requires `Main-Class=PropertiesLauncher`; adding `-Dloader.path` to a `JarLauncher` image will not work.
- The container image must have a compatible Java runtime and `app.jar` must genuinely be an executable Boot archive.
- When replacing an extension JAR, restart the container so the launcher constructs a new classpath.

### 12.3. Kubernetes: Safe Options

In Kubernetes, you can mount a **read-only** volume containing external JARs and pass `-Dloader.path` in the application container's JVM command or `JAVA_TOOL_OPTIONS`. However, setting `JAVA_TOOL_OPTIONS` broadly across build agents or multi-process pods can affect other JVMs. Prefer configuring the **application container's** entrypoint directly.

An illustrative `containers` snippet, **not a complete Kubernetes Deployment**:

```yaml
containers:
  - name: app
    image: registry.example.org/loader-demo:dev
    command: ["java"]
    args:
      - "-Dloader.path=/opt/app/extensions"
      - "-jar"
      - "/opt/app/app.jar"
    volumeMounts:
      - name: extensions
        mountPath: /opt/app/extensions
        readOnly: true
```

Supply matching `volumes` and an approved artifact source. Do not treat ConfigMaps as suitable storage for arbitrary large binary JARs; release-managed volumes/images offer better control. With multiple replicas, every pod must receive the exact same extension version (digest/checksum) and undergo consistent restarts/rollouts. Mounting a new JAR does not trigger automatic hot reload.

## 13. Security and Risks of Expanded Classpaths

`loader.path` lets the process load **additional Java code**. This increases flexibility while also expanding the attack surface:

1. **Use only artifacts from trusted sources:** approved internal repositories, verified checksums/signatures, SBOM and vulnerability checks per policy.
2. **Never let end users write to extension directories:** a JAR can execute code inside the process with the JVM's privileges, not merely serve passive data.
3. **Restrict file permissions:** make files/volumes read-only where appropriate; the account running the app must lack write permission on the JARs.
4. **Never use an external path to "hot-patch" a security dependency without testing:** classpath precedence and binary compatibility can cause crashes or altered behavior.
5. **Version pinning:** record exact extension versions and checksums alongside the app build; deployments must be reproducible.
6. **Test compatibility:** Java target class version, plugin APIs, transitive dependencies, and colliding package/class names.
7. **Do not believe PropertiesLauncher sandboxes plugins:** JARs in the same JVM share network, filesystem, and API access under process permissions; if strong isolation is needed, run in a separate process/container.
8. **Avoid placing secrets in loader.properties unless necessary:** loader settings only choose classpath/main. Spring runtime secrets belong in a protected secret manager/env.
9. **Track all changes outside the JAR:** because `app.jar`'s checksum stays unchanged when external JARs change, CI/CD must record a release manifest including extension artifacts.
10. **Clear rollback:** retain previous external JAR versions and restart procedures, rolling back configs/JARs as a unit; avoid live-editing multiple pods concurrently.

## 14. Troubleshooting Common Errors

| Symptom | Possible cause | How to check/fix |
| --- | --- | --- |
| `-Dloader.path=...` has no effect | Archive uses `JarLauncher` instead of `PropertiesLauncher` | `unzip -p app.jar META-INF/MANIFEST.MF`; configure `layout=ZIP` and rebuild |
| `NoClassDefFoundError` or `ClassNotFoundException` for extension | Wrong `loader.path`, missing JAR/class, relative path wrong for home, class in wrong JAR | `jar tf extension.jar`, check `-Dloader.home`, real paths, and container env |
| Controller still returns `builtin:Lan` | Reflection cannot see extension class | Compare runs with/without path; verify exact `com/example/extra/GreetingExtension.class` |
| Controller returns HTTP 500 once JAR is present | Class exists yet method signature, dependency, or reflective call failed | Check `IllegalStateException`/`InvocationTargetException` cause and extension version |
| `loader.main` does not switch main | Archive not using PropertiesLauncher, wrong property source, or wrong class name | Inspect Main-Class, try `java -Dloader.main=... -jar app.jar` |
| `Main class not found` | Wrong package in `loader.main`, class not on classpath | `jar tf` on BOOT-INF/classes or external JAR; check dots/casing |
| Two main classes present, Maven build fails | Plugin cannot auto-detect a single main | Add `<mainClass>...LoaderDemoApplication</mainClass>` in Boot plugin |
| `java -jar app.jar --loader.path=lib` does not load JAR | `--loader.path` was passed as an application argument, not a JVM loader property | Put `-Dloader.path=lib` **before** `-jar` or use `LOADER_PATH` |
| `loader.properties` not read | Placed in wrong location, wrong config.name/location, confused with Spring `application.properties` | Use `-Dloader.config.location=file:/absolute/path/loader.properties` |
| Relative path works in dev yet fails in systemd/CI | Different CWD, `loader.home` defaults to `user.dir` | Set `-Dloader.home=/opt/app` and fixed paths |
| Replaced external JAR yet app uses old version | Classloader is built at JVM start; process not restarted | Rollout/restart the JVM or container |
| `NoSuchMethodError` / `LinkageError` | Duplicate class or binary incompatibility between embedded and external JAR | Check versions, jar list, deduplicate, test compatibility |
| `UnsupportedClassVersionError` | Extension compiled with newer Java than runtime JVM | Check `java -version` and compile with `javac --release 17` where appropriate |
| Reading resource with system classloader fails | Nested JAR/classpath uses launcher classloader | Use context classloader or corresponding framework API |
| HTTP endpoint does not open port | `loader.main` points to AlternateMain instead of Spring app; or app startup failed | Check launcher selection and startup logs |
| Docker loads extension on host yet not inside container | Path must be the path **inside the container** with proper mount | Check volume mount, readOnly, `-Dloader.path` |
| Permission error in lib directory | JVM user cannot read external JAR/dir | Ensure read/execute permissions for the JVM user |
| Loaded wrong `loader.properties` from CWD | Multiple files with same name in search locations | Use absolute config location, remove stale leftover files |
| Classpath varies across replicas | Inconsistent extension volume/image | Pin artifact digest, roll out consistent releases |

### Systematic Debug Checklist

1. Check **Java/Spring Boot versions**: `java -version`, Boot plugin version/parent.
2. Check **the running artifact**: exact `target/...jar` path or image digest?
3. Inspect **`META-INF/MANIFEST.MF`**: is `Main-Class` `PropertiesLauncher`? Is `Start-Class` the expected default main?
4. Inspect **`BOOT-INF/classes` / `BOOT-INF/lib`** and the external JAR itself via `jar tf`.
5. Check the exact **JVM startup command**, confirming `-Dloader.path` and `-Dloader.main` come before `-jar`.
6. If using a file, explicitly set **`loader.config.location`**; if using relative paths, confirm `loader.home`.
7. Confirm **the extension folder/JAR exists in the process's own filesystem** (especially Docker/Kubernetes).
8. Reproduce via the demo endpoint `/greet?name=Lan`: `builtin:Lan` without extension; `external:Lan` when loaded successfully.
9. If the extension is present yet the app errors, inspect the linkage/reflection/config stack trace instead of just concluding `loader.path` "didn't run".
10. Verify Spring Boot runtime config and loader config are not mixed; Spring profiles/server ports do not alter bootstrap classpaths.
11. Test artifact versions and perform controlled restarts; do not arbitrarily wipe dependency caches or rebuild everything to mask path bugs.

### Short Verification Commands

```bash
mvn -B -ntp clean package

# Inspect app manifest:
unzip -p target/loader-demo-0.0.1-SNAPSHOT.jar META-INF/MANIFEST.MF

# Inspect main classes inside executable JAR:
jar tf target/loader-demo-0.0.1-SNAPSHOT.jar |
  grep -E '^(BOOT-INF/classes|org/springframework/boot/loader/launch)'

# Inspect classes inside external JAR:
jar tf external-libs/greeting-extension.jar

# Test without extension:
java -jar target/loader-demo-0.0.1-SNAPSHOT.jar

# Test with extension (after stopping the app from the previous command):
java -Dloader.path=external-libs -jar target/loader-demo-0.0.1-SNAPSHOT.jar

# Test alternate main class (after stopping the web app):
java -Dloader.main=com.example.loader.AlternateMain \
  -jar target/loader-demo-0.0.1-SNAPSHOT.jar demo
```

The `jar tf`/`unzip`/`grep` lines use JDK and Unix CLI tools; `grep`/`unzip` are not installed by default on all Windows setups. On PowerShell, substitute `Select-String` for filtering and an equivalent ZIP/JAR tool for inspecting the manifest. The web server `java -jar` commands above are **long-running**, so stop the JVM before running the next startup command; they are not a single unattended end-to-end Bash script.

## 15. Misconceptions to Avoid

1. **"Just add loader.path to application.properties."** Wrong mental model: PropertiesLauncher's `loader.path` is resolved before Spring configuration processing. Separate `loader.properties` from Spring config data.
2. **"Both JarLauncher and PropertiesLauncher use loader.path."** No: JarLauncher uses a fixed classpath layout, whereas PropertiesLauncher supports extension.
3. **"ZIP layout creates a ZIP file that cannot run with java -jar."** No: with the Boot Maven plugin it still produces an executable JAR, differing only in the chosen launcher.
4. **"loader.main changes server.port or Spring profiles."** No: `loader.main` only selects the Java main class.
5. **"If Start-Class is set, main cannot be overridden."** No: PropertiesLauncher can read `loader.main` and pick a different main when that class is available.
6. **"Dropping an external JAR into the folder after the server starts is enough."** Not guaranteed: the classpath is built at JVM bootstrap; restart to load new artifacts.
7. **"Using -cp alongside -jar will extend the Boot archive's classpath."** Do not rely on that; use PropertiesLauncher and `loader.path`.
8. **"An external JAR is safe because it isn't packaged inside app.jar."** False: it executes within the same JVM; manage provenance, checksums, and permissions.
9. **"Running from any directory resolves relative paths the same way."** No: `loader.home`/`user.dir` and actual paths can differ.
10. **"loader.properties can be loaded because loader.path points to its folder."** Do not rely on circular reasoning: launcher config must be located **before** resolving the extended classpath.
11. **"An immutable app JAR guarantees an immutable deployment."** Not when runtime loads external JARs that can change; pin extension artifacts too.
12. **"PropertiesLauncher is a multi-plugin sandbox."** No: plugins can share the classloader/process and cause conflicts or leak secrets without proper controls.
13. **"Maven package automatically creates PropertiesLauncher."** Not if the default layout is JAR; select the right layout and inspect the manifest.
14. **"ClassNotFound always means Maven is missing a dependency."** The class may reside in an external JAR while `loader.path` is wrong or file permissions are invalid.
15. **"Main-Class in the manifest must be the SpringApplication class."** For a Boot executable archive, `Main-Class` is the Boot launcher; app main goes in `Start-Class`, unless overridden via `loader.main`.

## 16. Workflow for Applying in a Real Project

1. Confirm a **legitimate need**: do you really need to load external dependencies/JARs or switch main at runtime? If not, `JarLauncher` is simpler.
2. Pick consistent Spring Boot and plugin versions; use a supported Java runtime.
3. With Maven and Spring Boot starter parent, configure `spring-boot-maven-plugin` with `<layout>ZIP</layout>`, and `<mainClass>...` if there are multiple entry points.
4. Run `mvn clean package`, verify manifest **`Main-Class=PropertiesLauncher`**.
5. Prepare version-pinned external JAR directories; check `jar tf`, runtime compatibility, and read permissions.
6. Choose a single clear loader setting source: `-Dloader.path`, `LOADER_PATH`, or `loader.properties` with an explicit `loader.config.location`.
7. Set `loader.home` if using relative paths, especially under systemd, Docker, Kubernetes, or CI.
8. If switching entry points, verify the exact class name and pass `loader.main` at startup; ensure alternate mains are not invoked accidentally in production.
9. Test the launcher with smoke tests with/without external JARs and compare outputs, then test real business logic.
10. Protect JAR directories, checksums, CI/CD release manifests, rolling restarts, and rollback plans; never use `loader.path` to load user-uploaded code.
11. Keep **loader configuration**, **Spring Boot runtime configuration**, and **build tool configuration** separate so scopes do not blur.
12. On major Spring Boot upgrades, re-verify launcher class packages, layout semantics, file lookup, and classpath behavior in **that exact version's** documentation.

## 17. Official Documentation

- Spring Boot 3.5 – [Launching Executable Jars](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/launching.html): distinguishing JarLauncher, WarLauncher, PropertiesLauncher, Main-Class, and Start-Class.
- Spring Boot 3.5 – [PropertiesLauncher Features](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/property-launcher.html): `loader.path`, `loader.home`, `loader.main`, and launcher config sources.
- Spring Boot 3.5 – [PropertiesLauncher Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/loader/launch/PropertiesLauncher.html): API and descriptions of launcher properties.
- Spring Boot 3.5 Maven Plugin – [Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html): repackage, ZIP/DIR layout, and manifest.
- Spring Boot 3.5 – [The Executable Jar Format](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/index.html): nested JARs, classloaders, and format constraints.
- Spring Boot – [Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): comparison with post-bootstrap app configuration.
- Java SE 17 – [The Java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): rules for `java -D... -jar ...` and Java runtime options.

**Conclusion:** `PropertiesLauncher` is a Boot Loader whose classpath and entry point can be controlled at startup. `loader.path` **appends class/JAR locations**, `loader.main` **selects the main class**, and `loader.home` plus `loader.properties` keep paths predictable in deployment. In the Spring Boot Maven Plugin, **`layout=ZIP`** builds a JAR using this launcher; always verify the **manifest** instead of guessing from the file extension. Manage external JARs strictly with explicit versions/checksums and restart the JVM on classpath changes to keep builds and deployments reproducible.
