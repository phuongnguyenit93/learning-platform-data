# The Role of JarLauncher, WarLauncher, and PropertiesLauncher in Spring Boot Loader

## 1. What Problem Do the Three Launchers Solve?

When building Spring Boot, you can package the application into an **executable JAR** or **executable WAR** to run with `java -jar`. Inside the archive are not only application classes, but typically dependency libraries **as JARs nested inside the JAR/WAR**. The standard JVM does not automatically find classes inside multi-level nested JARs merely by adding the outermost archive file to `-classpath`.

**Spring Boot Loader** is the bootstrap code packaged inside the archive to:

1. Take control when the JVM reads `META-INF/MANIFEST.MF`.
2. Locate application classes and nested libraries inside the archive.
3. Create/configure an appropriate class loader.
4. Invoke the real `main(String[] args)` method of the Spring Boot application.

The three commonly mentioned launchers:

- **`JarLauncher`:** the default launcher for an executable **JAR** following the `BOOT-INF/classes` and `BOOT-INF/lib` layout.
- **`WarLauncher`:** the default launcher for an executable **WAR** following the `WEB-INF/classes`, `WEB-INF/lib`, and `WEB-INF/lib-provided` layout.
- **`PropertiesLauncher`:** a configurable launcher for where to find additional libraries and the main class, e.g., via `loader.path`, `loader.main`, and `loader.properties`. Suitable when you want to expand the classpath outside the archive without immediately repackaging.

These are **archive bootstrap** components, not Spring MVC controllers, Spring beans, annotation processors, or three types of application servers.

**Version scope:** the examples and package classes in this guide use **Spring Boot 3.5.x**, Java 17+. Starting in Spring Boot 3.2, the launchers reside in the `org.springframework.boot.loader.launch` package. When reading Spring Boot 2.x or 3.1 guides, you may see the old names `org.springframework.boot.loader.JarLauncher`/`WarLauncher`/`PropertiesLauncher`; **do not copy the old class names** into a Boot 3.5 manifest.

## 2. Startup Mechanism: Main-Class Is Not Start-Class

In a Spring Boot executable archive packaged by the Maven/Gradle plugin, the manifest typically holds **two distinct roles**:

- `Main-Class`: the class with the `main` method that `java -jar` calls first — a Boot Loader **launcher**.
- `Start-Class`: the class containing **your application's** `main(String[] args)`, such as `com.example.loader.LoaderDemoApplication`.

Typical executable JAR manifest:

```text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.loader.LoaderDemoApplication
```

Typical executable WAR manifest:

```text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: com.example.loader.LoaderDemoApplication
```

Manifest of a JAR selecting PropertiesLauncher:

```text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.PropertiesLauncher
Start-Class: com.example.loader.LoaderDemoApplication
```

These lines illustrate the **relevant metadata portion**, not a complete dump. Actual manifests may include `Spring-Boot-Version`, `Spring-Boot-Classes`, `Spring-Boot-Lib`, and other fields.

Startup flow:

```text
java -jar app.jar / app.war
            |
            v
JVM reads META-INF/MANIFEST.MF
            |
            v
Main-Class = Boot Loader Launcher
            |
            v
Launcher determines classpath:
    app classes + nested dependency jars
            |
            v
Creates class loader + loads Start-Class
            |
            v
LoaderDemoApplication.main(args)
            |
            v
SpringApplication.run(...)
```

Important point: **`Start-Class` does not automatically become the Java main entry point just because it is written in the manifest**. `java -jar` uses `Main-Class`, and only the launcher finds and invokes `Start-Class`. Do not try to edit the manifest `Main-Class` to the application class while keeping the nested JAR layout intact; the classpath of the nested dependencies will not be set up properly.

**You do not need to manually generate `Class-Path` in the manifest for each nested JAR.** Spring Boot Loader derives the classpath from the supported layout.

## 3. Direct Comparison of the Three Launchers

| Criterion | `JarLauncher` | `WarLauncher` | `PropertiesLauncher` |
|---|---|---|---|
| Primary use case | Executable JAR | Executable WAR | Archive needing customizable classpath/main |
| Application classes | `BOOT-INF/classes/` | `WEB-INF/classes/` | Usually `BOOT-INF/classes/` with JAR/ZIP-style layout |
| Nested dependencies | `BOOT-INF/lib/` | `WEB-INF/lib/` and `WEB-INF/lib-provided/` | Uses `BOOT-INF/lib/` by default; can add to classpath |
| Library paths | Fixed convention | Fixed convention | `loader.path` / `LOADER_PATH` / launcher configuration |
| Application main selection | `Start-Class` | `Start-Class` | `loader.main` or `Start-Class` when applicable |
| Changing classpath via `loader.path` | Not how this launcher is configured | Not how this launcher is configured | Yes |
| Runnable via `java -jar`? | Yes, if the archive is packaged properly | Yes, if the WAR is an executable WAR | Yes, if packaged with the proper launcher/layout |
| Typical build tool choice | Maven repackage with `JAR` layout / Gradle `bootJar` | Maven repackage with `WAR` layout / Gradle `bootWar` | Maven `ZIP`/`DIR` layout; Gradle can configure the Boot archive manifest |
| Replaces SpringApplication? | No | No | No |
| Common pitfalls | Trying to use `-cp` or adding external jars unknown to the loader | Confusing executable WAR with external servlet container deployment | Version/classpath conflicts, trusting untrusted external libs, confusing `loader.*` with `spring.*` |

**Remember:** the launcher name describes **how startup and class lookup work**, not whether the application uses Tomcat, Undertow, Netty, MVC, or WebFlux. A Boot JAR can hold a non-web application; a Boot WAR is usually associated with a servlet web application.

## 4. Why Boot Loader Instead of a Regular JAR?

A regular JAR contains `.class` files directly at the root package path and can use `java -cp` with libraries located **outside** the archive. A Spring Boot executable archive typically keeps each dependency library intact as a **nested JAR**, unlike "shading" which merges all library classes into a single JAR namespace.

Example executable JAR structure:

```text
app.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
│   └── launch/JarLauncher.class     # Boot Loader at archive root
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/loader/LoaderDemoApplication.class
    │   └── application.properties
    ├── lib/
    │   ├── spring-boot-*.jar
    │   ├── spring-context-*.jar
    │   └── ... other dependencies
    ├── classpath.idx                # May be generated by plugin
    └── layers.idx                   # May be generated by plugin
```

The JAR names `spring-boot-*.jar` in the tree are illustrative, not exact names guaranteed across all versions. The bootstrap loader is at the **archive root**, while application source classes reside in `BOOT-INF/classes`.

**Technical reason:** Java's `URLClassLoader` with a standard classpath does not automatically treat each `BOOT-INF/lib/dependency.jar` as a separate archive to open and load classes from. Spring Boot provides a nested JAR access mechanism, reads entry offsets within the archive file, and provides a class loader supporting nested URLs. With the proper layout, there is no need to extract all dependency JARs into a temporary directory just to run the application.

Some libraries are incompatible with custom loaders if they insist on using `ClassLoader.getSystemClassLoader()` or assume every resource is a `java.io.File` on the filesystem. When reading packaged resources, prefer a classpath resource stream instead of forcing it into a physical file path.

## 5. JarLauncher: The Default Choice for Executable JARs

### 5.1. How JarLauncher Finds Classes

`JarLauncher` recognizes Boot-defined locations, primarily:

- `BOOT-INF/classes/`: application classes and resources.
- `BOOT-INF/lib/`: dependency JARs packaged by the plugin.

It constructs the runtime classpath and invokes `Start-Class`. When the command is:

```bash
java -jar target/loader-demo-0.1.0-SNAPSHOT.jar
```

the JVM does not directly call `LoaderDemoApplication.main` from the manifest. It calls `JarLauncher.main`; the launcher sets up the classpath before handing off to the application. **`JarLauncher` is not a tool for picking up libraries from an arbitrary folder next to the JAR when you set `loader.path`.** If you need that mechanism, see `PropertiesLauncher`.

### 5.2. How Does the Spring Boot Maven Plugin Create It?

In Maven using `spring-boot-starter-parent` and `spring-boot-maven-plugin`, `mvn package` can produce an executable JAR via the preconfigured `repackage` goal. The default layout is based on the archive type.

Example plugin configuration section:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
```

This snippet is for a POM that inherits `spring-boot-starter-parent`, has main sources, and has `<packaging>jar</packaging>` or defaults to JAR. The parent usually already defines the `repackage` execution; do not add a duplicate execution if you only want the default JAR.

With Maven without the Boot parent, you must configure the plugin version, `repackage` execution, and appropriate dependency management. **Merely adding the `spring-boot-loader` library as a dependency does not automatically turn a regular JAR into a properly laid-out executable JAR**.

### 5.3. Gradle bootJar

With Gradle Groovy DSL, the Java plugin, and the Spring Boot Gradle plugin:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.1.0-SNAPSHOT'

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
```

This `build.gradle` snippet is a configuration usable in a single-module project that already has `settings.gradle`/wrapper, along with the Java main class in the practice section. Run:

```bash
./gradlew bootJar
java -jar build/libs/loader-demo-0.1.0-SNAPSHOT.jar
```

The JAR name depends on the root project name, `version`, and archive customizations; `bootJar` creates the executable JAR, whereas the `jar` task produces a regular Java archive. `./gradlew bootRun` runs directly from the development classpath and is not a real test of the `JarLauncher` path from a packaged executable JAR.

## 6. WarLauncher: Launching Executable WARs

### 6.1. The WAR Layout Is a Different Convention

A Spring Boot executable WAR typically has the structure:

```text
app.war
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
│   └── launch/WarLauncher.class
└── WEB-INF/
    ├── classes/
    │   └── com/example/web/WebApplication.class
    ├── lib/
    │   ├── spring-webmvc-*.jar
    │   └── ... application libraries
    └── lib-provided/
        ├── tomcat-embed-*.jar
        └── ... provided-scope dependencies (if any)
```

`WarLauncher` looks for classes in `WEB-INF/classes` and JARs in `WEB-INF/lib` **as well as `WEB-INF/lib-provided`** when run via `java -jar app.war`. The two library directories exist for different reasons.

`WEB-INF/lib-provided` holds dependencies **needed to run the self-contained WAR via `java -jar`** that **should not be loaded twice by an external servlet container** when deploying the WAR traditionally. Common example: the embedded servlet container dependency marked `provided`.

### 6.2. Two Ways to Use the Same Executable WAR

**Approach A — standalone run:**

```bash
java -jar target/web-demo-0.1.0-SNAPSHOT.war
```

In this path, the JVM reads the manifest, invokes `WarLauncher`, and uses the necessary dependencies inside the WAR (including libraries in `WEB-INF/lib-provided` if packaged) to start the embedded server.

**Approach B — deploy to an external servlet container:** place the WAR into a compatible Tomcat/servlet container. The container handles deployment per the Servlet model, using `WEB-INF/classes` and `WEB-INF/lib` along with the API/container it provides. **The external container does not invoke `WarLauncher` via Boot Loader's `java -jar` mechanism**; the application must be configured so the Servlet container bootstraps properly, usually via a class extending `SpringBootServletInitializer`.

Therefore, **"using a WAR" does not automatically mean "WarLauncher will be invoked by external Tomcat"**. WarLauncher belongs to **the executable WAR run path**, not a replacement for a servlet container's WAR deployment mechanism.

### 6.3. Example Class for a Servlet WAR

In a project with suitable Spring MVC/Tomcat dependencies, create:

```java
package com.example.web;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class WebApplication extends SpringBootServletInitializer {
    public static void main(String[] args) {
        SpringApplication.run(WebApplication.class, args);
    }

    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder application) {
        return application.sources(WebApplication.class);
    }
}
```

`main` supports `java -jar`; `configure` supports the Servlet container path when the WAR is deployed. This is valid Java source, but requires the Spring Boot classpath and full WAR build configuration. It differs from the non-web example in the later section; **do not put two main classes into the same project** hoping the plugin will automatically pick the right one.

### 6.4. Maven WAR Packaging

A Spring Boot web project POM needs WAR packaging selected:

```xml
<packaging>war</packaging>

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
```

This is a **snippet to merge into a POM** that already has the Boot parent, `groupId`, `artifactId`, `version`, and `spring-boot-maven-plugin`; it is not a standalone XML document. Declaring Tomcat as provided is a common configuration when deploying a WAR to an external container. When the Spring Boot Plugin repackages, appropriate provided dependencies go into `WEB-INF/lib-provided` for the executable WAR.

Run `./mvnw package` and inspect `target/*.war`. When deploying to an external container, verify **Servlet API, Jakarta namespace, and Tomcat/JDK versions** compatible with the Spring Boot version. Do not take a Boot 3.5 WAR and arbitrarily deploy it to an overly old servlet container.

### 6.5. Gradle bootWar

In a Gradle Java web project with the Spring Boot plugin applied, you can add the `war` plugin and configure:

```groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
```

In a real project, also include `group`, `version`, toolchain, and the `WebApplication` source shown above. The `bootWar` task creates the executable WAR; regular `war` creates a WAR per the Java war plugin. Use `providedRuntime` for its intended purpose instead of arbitrarily removing the embedded servlet container from the entire runtime classpath, since an executable WAR still needs to start standalone.

## 7. PropertiesLauncher: Expanding the Classpath and Specifying Main

### 7.1. The Right Mental Model

`PropertiesLauncher` still bootstraps the class loader and invokes the application. It differs by allowing operators to **supply additional classpath locations or main class information at runtime**. That is why it fits certain packaging/deployment models that want to keep dependencies outside the archive or add trusted libraries.

It **does not automatically download new dependencies from Maven Central**, does not modify `pom.xml`/`build.gradle`, does not provide hot-reload, and is not a Spring `PropertySource` for business properties.

In the JAR/ZIP-style archive layout it supports, classes/libraries in `BOOT-INF/classes` and `BOOT-INF/lib` continue to be used; `loader.path` appends other entries to the classpath.

Conceptual example:

```text
/opt/demo/
├── app.jar                     # Spring Boot ZIP layout, PropertiesLauncher
├── loader.properties           # Launcher configuration (optional)
└── external-lib/
    ├── vendor-client.jar
    └── plugin-api-impl.jar
```

When `loader.path=external-lib` and `loader.home=/opt/demo`, the launcher can find additional libraries in this directory without necessarily rebuilding `app.jar`. However, expanding the classpath alters **executable code**, so versions, signatures, access permissions, and file sources must be controlled.

### 7.2. Commonly Used Properties

| Property | Meaning |
|---|---|
| `loader.path` / `LOADER_PATH` | Comma-separated list: directories, JARs/ZIPs, or loader-supported locations to add to the classpath |
| `loader.home` / `LOADER_HOME` | Base directory for relative paths in `loader.path`, normally defaulting to the current working directory |
| `loader.main` / `LOADER_MAIN` | Specifies the application class to invoke; if absent, `Start-Class` can be used |
| `loader.args` / `LOADER_ARGS` | Default application arguments passed to main |
| `loader.config.name` | Launcher config filename, usually `loader.properties` (excluding extension) |
| `loader.config.location` | Explicit launcher config file location if needed, e.g., `file:/opt/demo/loader.properties` |
| `loader.system` / `LOADER_SYSTEM` | Optional mechanism to expose loader configuration as System properties; do not assume enabled by default |

Spring Boot also supports configuration via manifest entries and Java system properties. Exact precedence among configuration sources is determined by the loader implementation/version; when `loader.path` is set in multiple places, verify actual behavior on the running archive rather than guessing from shell command order.

**Do not confuse namespaces:**

- `loader.path`: **class/library** paths loaded by the launcher.
- `spring.config.location` or `spring.config.additional-location`: **Spring Boot configuration file** paths.
- `spring.profiles.active`: **Spring application** profile.
- `java.class.path`/`-cp`: classpath used by the **standard JVM**; when running `java -jar`, the launcher builds the application classpath from nested JARs as well.

They solve different problems.

### 7.3. loader.properties Example

Place the `loader.properties` file in a location `PropertiesLauncher` can find, such as the process's default working directory:

```properties
loader.path=external-lib
loader.home=/opt/demo
```

The `/opt/demo` value is a Linux example. In a real environment, use a real readable path. Relative paths in `loader.path` are resolved relative to `loader.home`; if you change the current working directory without controlling `loader.home`, the launcher may fail to find the files.

Or pass Java system properties directly at runtime (no file needed):

```bash
java -Dloader.home=/opt/demo -Dloader.path=external-lib \
     -jar /opt/demo/app.jar
```

The multiline command uses `\` line continuation for Unix/macOS shells; on Windows enter on one line and use appropriate paths. To set the env var in a POSIX shell:

```bash
LOADER_PATH=/opt/demo/external-lib java -jar /opt/demo/app.jar
```

These methods **only work when the archive uses PropertiesLauncher**. With `JarLauncher`, setting `-Dloader.path` does not switch this fixed launcher to PropertiesLauncher's classpath resolution.

### 7.4. Selecting PropertiesLauncher When Packaging with Maven

**In the Spring Boot Maven Plugin, `layout=ZIP` (alias `DIR`) produces a JAR-like layout that uses `PropertiesLauncher`.** The word "ZIP" here is a **layout** name, not a requirement to rename the executable file extension from `.jar` to `.zip`.

If the POM inherits `spring-boot-starter-parent` and already declares the Spring Boot Maven Plugin, update the plugin configuration to:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <layout>ZIP</layout>
    </configuration>
</plugin>
```

This is a **fragment inside `<build><plugins>` of a POM**, not a standalone POM. With starter parent, the `repackage` execution is usually already configured; if using a different parent, you must bind the `repackage` goal to the build lifecycle.

Rebuild:

```bash
./mvnw clean package
```

Then inspect the manifest of the new executable JAR: `Main-Class` should be `org.springframework.boot.loader.launch.PropertiesLauncher`. If it is still `JarLauncher`, you may have edited the wrong module, run the wrong Maven profile, or inspected an old artifact file.

### 7.5. Configuring the Manifest When Using Gradle

In a project with the `bootJar` task from the Spring Boot Gradle plugin, you can customize the manifest of **the task that produces the executable archive**. Groovy DSL example for Boot 3.5:

```groovy
tasks.named('bootJar') {
    manifest {
        attributes 'Main-Class':
            'org.springframework.boot.loader.launch.PropertiesLauncher'
    }
}
```

This is a **snippet added to `build.gradle`**, not a complete file. After running `./gradlew bootJar`, **re-check the manifest** and test `java -Dloader.path=... -jar ...`. Avoid editing the regular `jar` task's manifest and assuming `bootJar` changed its launcher; whichever task builds the file you run determines the behavior.

For WAR archives/Gradle Boot plugin or custom layouts, verify compatibility between the archive layout and the chosen launcher. `PropertiesLauncher` usually fits a **BOOT-INF**-style layout; do not merely change `Main-Class` of a `WEB-INF`-based executable WAR to PropertiesLauncher assuming it will understand all paths properly. When a WAR is needed for an external servlet container, prefer the standard WAR launcher/model.

## 8. Hands-On Lab: Verifying JarLauncher and PropertiesLauncher

The exercise below uses **Maven + Spring Boot 3.5.x + Java 17** with an application **without a web server** so logs are easy to observe. The goal is to prove that the Java runtime **only** finds a class outside the archive when the classpath is properly extended via PropertiesLauncher.

### 8.1. Create the Application

Directory structure:

```text
loader-demo/
├── pom.xml
├── mvnw / mvnw.cmd / .mvn/              # Maven Wrapper from Initializr
├── src/main/java/com/example/loader/
│   └── LoaderDemoApplication.java
└── extra-src/demo/extra/
    └── Greeting.java
```

Maven `pom.xml` (this is the complete file for the example):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
            https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>loader-demo</artifactId>
    <version>0.1.0-SNAPSHOT</version>

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

Java class `src/main/java/com/example/loader/LoaderDemoApplication.java`:

```java
package com.example.loader;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LoaderDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(LoaderDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showExternalLibrary() {
        return args -> {
            System.out.println("BOOT_APP_OK");
            try {
                Class<?> greetingClass =
                        Class.forName("demo.extra.Greeting");
                Object message =
                        greetingClass.getMethod("say").invoke(null);
                System.out.println("EXTENSION=" + message);
            } catch (ClassNotFoundException e) {
                System.out.println("EXTENSION=absent");
            }
        };
    }
}
```

The application uses Spring Boot and Spring Framework to create a context, then executes `ApplicationRunner`. When the launcher cannot find `demo.extra.Greeting`, it prints `EXTENSION=absent`. When the external JAR is loaded, reflection invokes `say()` and prints the returned string. This is valid Java 17 **when run via Maven with Spring dependencies**, not a class runnable with bare `javac`.

### 8.2. Run the Default Executable JAR

At the project root:

```bash
./mvnw clean package
java -jar target/loader-demo-0.1.0-SNAPSHOT.jar
```

Spring Boot logs contain many lines that vary by environment. The two lines **printed by the application itself** will be:

```text
BOOT_APP_OK
EXTENSION=absent
```

After the runner completes, because the example only includes `spring-boot-starter` (no embedded web server), the process normally exits rather than staying open on an HTTP port. If you add `spring-boot-starter-web`, process lifecycle behavior will differ.

Inspect the manifest and structure:

```bash
jar tf target/loader-demo-0.1.0-SNAPSHOT.jar
unzip -p target/loader-demo-0.1.0-SNAPSHOT.jar META-INF/MANIFEST.MF
```

The `unzip -p` command is for systems with `unzip`; on Windows you can use an archive viewer or extract into a separate inspection folder. Expect the manifest to contain `Main-Class: org.springframework.boot.loader.launch.JarLauncher` and `Start-Class: com.example.loader.LoaderDemoApplication`.

### 8.3. Create an Additional External Library JAR

Create file `extra-src/demo/extra/Greeting.java`:

```java
package demo.extra;

public final class Greeting {
    private Greeting() {
    }

    public static String say() {
        return "hello-from-external-jar";
    }
}
```

This class **only uses the Java Standard Library** and can be compiled independently with `javac`:

```bash
mkdir -p extra-classes external-lib
javac --release 17 -encoding UTF-8 -d extra-classes \
      extra-src/demo/extra/Greeting.java
jar --create --file external-lib/greeting.jar -C extra-classes .
```

On Windows, create the `extra-classes` and `external-lib` folders beforehand using File Explorer or PowerShell `New-Item -ItemType Directory -Force extra-classes,external-lib`; enter the `javac` command on a single line. The resulting `external-lib/greeting.jar` **is not inside the application's `BOOT-INF/lib`**.

### 8.4. With JarLauncher: loader.path Does Not Work as Expected

Run the **default JAR from Step 8.2** again:

```bash
java -Dloader.path=external-lib \
     -jar target/loader-demo-0.1.0-SNAPSHOT.jar
```

Because this archive still uses `JarLauncher`, the launcher does not load `external-lib` via PropertiesLauncher's mechanism. Therefore, the application-printed output remains:

```text
BOOT_APP_OK
EXTENSION=absent
```

If the result differs, inspect the manifest to confirm it is truly JarLauncher, or check whether `demo.extra.Greeting` accidentally ended up in the main sources/outputs or another dependency.

### 8.5. Switch to PropertiesLauncher

In `pom.xml`, replace the current `spring-boot-maven-plugin` section with:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <layout>ZIP</layout>
    </configuration>
</plugin>
```

Rebuild so you do not run the stale artifact:

```bash
./mvnw clean package
unzip -p target/loader-demo-0.1.0-SNAPSHOT.jar META-INF/MANIFEST.MF
```

Expect `Main-Class` to change to `org.springframework.boot.loader.launch.PropertiesLauncher`; `Start-Class` remains the application main.

Run with the external library:

```bash
java -Dloader.path=external-lib \
     -jar target/loader-demo-0.1.0-SNAPSHOT.jar
```

The two output lines printed by the application:

```text
BOOT_APP_OK
EXTENSION=hello-from-external-jar
```

**Why did the same source yield a different result?** `PropertiesLauncher` added the JAR in `external-lib` to the effective classpath. `Class.forName` in the application class now finds `demo.extra.Greeting`. This example demonstrates **class loading mechanics**, not a recommendation to drop arbitrary plugin JARs into production.

You can also place `loader.path=external-lib` in a `loader.properties` file in the working directory, then run `java -jar ...` without passing `-Dloader.path`. Finding the properties file depends on `loader.home` and supported launcher locations; if running from another directory, consider using an absolute path to avoid location mismatches.

### 8.6. Experiment Observation Table

| Archive being run | How it is run | Expected output |
|---|---|---|
| Default Maven JAR: JarLauncher | `java -jar app.jar` | `EXTENSION=absent` |
| Default JAR: JarLauncher | `java -Dloader.path=external-lib -jar app.jar` | Still `EXTENSION=absent` |
| Maven ZIP layout: PropertiesLauncher | `java -jar app.jar`, no loader.path | `EXTENSION=absent` |
| Maven ZIP layout: PropertiesLauncher | `java -Dloader.path=external-lib -jar app.jar` | `EXTENSION=hello-from-external-jar` |

The table assumes the exact directory layout of the example and no other configuration. If values differ from expectations, check Main-Class/Start-Class, source output classpath, `loader.home`, and external library files before changing code.

## 9. Inspecting Manifest, Nested JARs, and Launcher by Build Tool

### 9.1. Maven

From the project root:

```bash
./mvnw clean package
jar tf target/loader-demo-0.1.0-SNAPSHOT.jar
unzip -p target/loader-demo-0.1.0-SNAPSHOT.jar META-INF/MANIFEST.MF
```

Look for entries:

```text
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/com/example/loader/LoaderDemoApplication.class
BOOT-INF/lib/...
```

If you switched to ZIP layout, the launcher entry changes in the manifest; the archive might still contain multiple launcher classes, so **the presence of a class file does not prove which launcher is selected**. Rely on `Main-Class`.

### 9.2. Gradle

In a project with the Boot plugin applied:

```bash
./gradlew bootJar
jar tf build/libs/loader-demo-0.1.0-SNAPSHOT.jar
unzip -p build/libs/loader-demo-0.1.0-SNAPSHOT.jar META-INF/MANIFEST.MF
```

When a WAR is needed, use `bootWar` and inspect the corresponding `.war` file:

```bash
./gradlew bootWar
jar tf build/libs/web-demo-0.1.0-SNAPSHOT.war
```

Final filenames are illustrative only. If the project customizes `archiveFileName`, `version`, root name, or multi-module setup, locate the exact generated archive. **Do not inspect a `plain` JAR and conclude the loader is wrong**: in some Gradle builds, both a plain JAR and a bootJar can exist.

### 9.3. Using Java to Read the Manifest When unzip Is Unavailable

A standalone Java 17 program can read the manifest of a JAR or WAR (path passed via command line):

```java
import java.io.IOException;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public class ReadManifest {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println("Usage: java ReadManifest <archive.jar-or-war>");
            System.exit(2);
        }

        try (JarFile archive = new JarFile(args[0])) {
            Manifest manifest = archive.getManifest();
            if (manifest == null) {
                throw new IllegalStateException("No manifest");
            }

            Attributes attributes = manifest.getMainAttributes();
            System.out.println("Main-Class="
                    + attributes.getValue("Main-Class"));
            System.out.println("Start-Class="
                    + attributes.getValue("Start-Class"));
        }
    }
}
```

Save the file as `ReadManifest.java`, using JDK 17+:

```bash
javac --release 17 ReadManifest.java
java ReadManifest target/loader-demo-0.1.0-SNAPSHOT.jar
```

Using the example's default JAR, the two **stdout lines of the inspection program** are:

```text
Main-Class=org.springframework.boot.loader.launch.JarLauncher
Start-Class=com.example.loader.LoaderDemoApplication
```

If using PropertiesLauncher, `Main-Class=...PropertiesLauncher` replaces it; if using an executable WAR, `...WarLauncher`. This is a **standalone compilable** Java Standard Library program requiring no Spring dependencies.

## 10. Classpath Behavior: Differences to Understand

### 10.1. Nested Classpath and Load Order

In a Boot JAR/WAR, application classes typically take precedence according to the classpath constructed by the launcher. The order of nested dependencies can also be described by `BOOT-INF/classpath.idx` generated by the plugin. The index file serves to control classpath ordering when launching the archive via Boot Loader; it is not a `spring.profiles.active` configuration file.

When expanding `loader.path` with PropertiesLauncher, the classpath may contain duplicate class/JAR versions overlapping with `BOOT-INF/lib`. **Which class gets loaded depends on the loader and effective classpath order**, not "the newest version" or "the file with the highest version number". Therefore, adding an external `vendor.jar` can accidentally shadow APIs or cause `NoSuchMethodError`/`ClassCastException`/`LinkageError` when versions are incompatible.

Do not try to resolve version conflicts by dumping batches of JARs into external-lib hoping Spring Boot will pick the right set. Manage BOM/dependency versions from the build tool and only use an external classpath for specific requirements.

### 10.2. Boot Class Loader and System Class Loader

Application classes are loaded by Spring Boot Launcher's class loader. Some libraries explicitly calling `ClassLoader.getSystemClassLoader()` to find resources may fail to see classes in nested JARs; the common practice is to use the **thread context class loader** or the class loader of the handling class.

Example of reading a resource properly in an application:

```java
try (var input =
        LoaderDemoApplication.class.getResourceAsStream("/banner.txt")) {
    if (input == null) {
        throw new IllegalStateException("Missing banner.txt");
    }
    // Read bytes from the stream; do not force a resource inside a JAR into a File.
}
```

This is an illustrative Java snippet **inside a method that handles IOException**; it requires `src/main/resources/banner.txt` on the classpath. It is not a standalone program.

### 10.3. Index Files and Docker Layers Are Not New Launchers

- `BOOT-INF/classpath.idx` may describe library ordering in the classpath.
- `BOOT-INF/layers.idx` describes archive layer separation to optimize container image builds.
- There is no launcher named "LayersLauncher" just because a JAR contains layers metadata.
- Layer metadata **does not create a different classloader** and does not turn a WAR-style archive into a JAR.

### 10.4. ZIP/JAR Format Constraints

Spring Boot's nested jar mechanism requires nested JAR entries in the outer archive to use an appropriate storage method (`STORED` at the nested jar entry level) so the loader can seek data inside. A poorly written custom ZIP script can produce a file that still extracts cleanly yet **fails to launch** through Boot Loader.

If custom packaging is needed, prefer the Spring Boot Maven/Gradle Plugin instead of assembling archives manually. `jar tf` only proves the archive has entries; it does not prove the manifest/classloader and dependencies are valid for running.

## 11. Concepts Easily Confused

| Concept | Same as launcher? | Distinction |
|---|---|---|
| `SpringApplication.run` | No | Bootstraps the **Spring ApplicationContext** after classes have been loaded |
| `@SpringBootApplication` | No | Composite annotation for configuration/auto-configuration/component scan |
| Maven `spring-boot:run` | No | Goal that runs the application from the development classpath, without requiring executable JAR packaging |
| Gradle `bootRun` | No | JavaExec task running from the runtime classpath, distinct from the `java -jar` path |
| `spring-boot:repackage` | No | **Build-time**: creates the executable archive and manifest/loader |
| Gradle `bootJar` / `bootWar` | No | **Build-time**: packages the archive; the launcher runs after the artifact starts |
| `java -cp` | No | Standard JVM classpath; does not automatically resolve Boot-style nested JARs |
| `loader.path` | A PropertiesLauncher setting | Adds libraries/classes to the application classpath |
| `spring.config.additional-location` | No | Where Spring looks for application configuration files |
| `java -jar app.war` | WAR launcher path | JVM uses Main-Class/WarLauncher if the WAR is executable |
| Deploying WAR to external Tomcat | Servlet container path | Does not mean external Tomcat invokes WarLauncher |
| Shaded uber JAR | No | Merges classes into a single JAR, unlike Spring Boot keeping nested dependency jars |
| GraalVM native image | Not using JVM JAR loader | Native executables have their own packaging/startup model |

Do not blame Spring Boot Loader when the error lies in **application context startup** (e.g., missing datasource, port already in use). Conversely, a `ClassNotFoundException` before the Spring banner appears is definitely worth checking the manifest/classpath/nested dependencies for.

## 12. Common Errors and Diagnosis

### 12.1. `no main manifest attribute`

**Symptom:** `java -jar app.jar` reports no main manifest attribute.

**Possible cause:** running a plain JAR created by `jar`, or the Maven `repackage` plugin did not execute, or wrong build file.

**How to check:** inspect `META-INF/MANIFEST.MF`. With Maven, check `spring-boot-maven-plugin`/`repackage` goal and the right file after `package`. With Gradle, select the `bootJar` output rather than the plain jar.

### 12.2. `ClassNotFoundException: org.springframework.boot.loader.launch.JarLauncher`

**Possible cause:** manifest points to a Boot 3.2+ launcher but the archive lacks loader classes at the root; manually editing a plain JAR's manifest, or mixing old and new classes/packages.

**Resolution:** do not copy a manifest alone; rebuild the archive with the appropriate plugin. Check `jar tf` to confirm loader classes at the root and the exact class/package path for **the actual Spring Boot version**.

### 12.3. `ClassNotFoundException` for Application Class

**Possible cause:** wrong `Start-Class` package/class, project has multiple main classes and the plugin picked the wrong one, class was not compiled, or it was excluded from the archive.

**Resolution:** check `Start-Class`, entries in `BOOT-INF/classes`/`WEB-INF/classes`, source package, and the plugin's main class property. Do not replace `Main-Class` with the application main to bypass verification.

### 12.4. `NoClassDefFoundError` for Third-Party Library

**Possible cause:** dependency missing in `BOOT-INF/lib` or `WEB-INF/lib`, excluded/wrong scope, or incompatible version.

**Resolution:** inspect the Maven/Gradle dependency tree and the actual archive entries. Do not assume a library visible when running from the IDE/`bootRun` is also present in the executable JAR.

### 12.5. `-Dloader.path` Specified Yet External JAR Still Not Loaded

**Questions to check:**

1. Does the manifest actually select `PropertiesLauncher`?
2. Does `loader.path` point to a valid supported directory/JAR?
3. Relative to which `loader.home`/working directory are relative paths resolved?
4. Is the file readable and a valid JAR?
5. Is there a duplicate class/package name in other JARs causing the loader to load a different class?

A `JarLauncher` session **does not become PropertiesLauncher** merely because you pass `-Dloader.path`.

### 12.6. Executable WAR Runs with `java -jar` but Fails When Deployed to Tomcat

**Possible cause:** missing `SpringBootServletInitializer` or `configure` mapping, external Tomcat incompatible with Servlet/Jakarta namespace, duplicate servlet container dependency in `WEB-INF/lib`, or missing context path config.

**Resolution:** clearly separate the self-contained WAR path from the external container path. Check `WEB-INF/lib-provided`/provided scope, server version, and container deployment logs; do not check only `Main-Class`.

### 12.7. A JAR Runs in the IDE but Fails with `java -jar`

IDEs, Maven `spring-boot:run`, and Gradle `bootRun` usually use the development classpath. A Boot executable JAR uses the archive's nested classpath. Check packaging, dependencies, resource files, JVM version, profile/environment, and resources accessed via `File` instead of classpath streams.

## 13. Choosing a Launcher by Scenario

| Scenario | Recommendation |
|---|---|
| Spring Boot microservice as an executable JAR | **Default JarLauncher** via Maven repackage/Gradle bootJar |
| Spring Boot CLI/batch packaged as a single JAR | **JarLauncher**; no web server or WAR needed |
| Web app needing executable WAR and/or external servlet container deployment | **WarLauncher** for `java -jar`; configure `SpringBootServletInitializer` for external deploy |
| Need to load additional libraries from a controlled directory | **PropertiesLauncher** with appropriate layout, `loader.path`, and integration tests |
| Only need to change `application.yml` in the deploy environment | No launcher change needed; use **Spring externalized configuration** |
| Want to change `server.port` or profile | No launcher change needed; pass application args/env/`spring.*` |
| Building cache-optimized images | Use container layers/layered JAR or buildpacks; not necessarily a launcher change |
| Want to inject arbitrary plugin logic at runtime | Weigh security/classpath risks; PropertiesLauncher can help but requires allowlisting, testing, and version control |
| Project wants fewer ops errors and immutable builds | Prefer default JarLauncher/WarLauncher and fixed dependencies inside the artifact |

**Rule of thumb:** use the **least customized** launcher that satisfies deployment requirements. PropertiesLauncher is helpful when the classpath genuinely must change outside the artifact, but it also introduces an additional source of behavioral variation not fully captured by the application file's hash alone.

## 14. Security and Build Reproducibility with External Classpaths

When using `PropertiesLauncher`, an `external-lib/unknown.jar` file can contain bytecode executed inside the application JVM with the process's privileges. This **is not a place to store untrusted plugins** or treat as a sandbox. The launcher only loads classes; it does not scan vulnerabilities, verify signatures, check licenses, or isolate permissions.

Safety checklist:

1. Allow only authorized pipelines/ops teams to write to the external-lib directory.
2. Pin versions and checksums/signatures if deployment policy requires; log build manifest/external dependency versions.
3. Scan dependencies/vulnerabilities in both nested `BOOT-INF/lib` **and** external JARs.
4. Keep file permissions tight; prevent untrusted users from influencing `loader.path`.
5. Test for class/version conflicts via integration tests on the exact artifact and exact external library set.
6. Avoid using external JARs to silently override core security libraries without review.
7. Explicitly record `loader.home` and working directories in systemd/container/startup scripts.
8. If rolling back, roll back **both the application file and external-lib**; an unchanged artifact can behave differently when external-lib changes.

In container deployments, a directory mount can alter the runtime classpath outside an immutable image. Unless strictly required, packaging dependencies into the image/artifact and keeping data configs external is easier to reproduce.

## 15. Post-Packaging Verification Checklist

1. **Identify artifact type:** `.jar` or `.war`? Is it truly an executable archive built by the Boot plugin?
2. **Check `Main-Class`:** matches `JarLauncher`, `WarLauncher`, or `PropertiesLauncher`?
3. **Check `Start-Class`:** points to the right class with `public static void main(String[] args)`?
4. **Check layout:** `BOOT-INF/classes/lib` for JAR, `WEB-INF/classes/lib/lib-provided` for WAR?
5. **Check nested dependencies:** required JARs are in launcher-recognized directories; do not rely on IDE classpath.
6. **Execute `java -jar`:** check exit code/application logs and core functionality, not just `jar tf`.
7. **With PropertiesLauncher:** verify `loader.path`, `loader.home`, `loader.properties` location, and `loader.main` selection if overridden.
8. **With executable WAR:** test both `java -jar` and external container deployment separately (if both are required).
9. **Check class/resource paths:** avoid assuming nested JARs or resources are always physical files.
10. **Verify Spring Boot version:** launcher classes changed package between Boot 3.1 and 3.2; do not mix docs across versions.
11. **Control external code sources:** record hashes/versions/permissions of external libraries.
12. **Avoid manual post-build archive edits:** if layout changes are needed, update the Maven/Gradle build script and rebuild for a reproducible artifact.

### Official Documentation

- [Spring Boot 3.5 — Launching Executable Jars](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/launching.html)
- [Spring Boot 3.5 — Nested JARs](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html)
- [Spring Boot 3.5 — PropertiesLauncher Features](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/property-launcher.html)
- [Spring Boot 3.5 — Executable Jar Restrictions](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/restrictions.html)
- [Spring Boot 3.5 — Maven Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
- [Spring Boot 3.5 — Gradle Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html)
- [PropertiesLauncher Java API (Spring Boot 3.5)](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/loader/launch/PropertiesLauncher.html)

**Takeaway:** `JarLauncher` launches **BOOT-INF-based JARs**; `WarLauncher` launches **WEB-INF-based WARs**, including `lib-provided` libraries in executable mode; `PropertiesLauncher` adds the ability to **customize the classpath and main class**. All three are Spring Boot Loader bootstraps: they build the class-loading environment, then invoke your application according to the manifest/configuration.
