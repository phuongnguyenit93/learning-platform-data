# Reading `WEB-INF/classes`, `WEB-INF/lib`, and `WEB-INF/lib-provided` in a Spring Boot WAR

## 1. What Will You Learn?

A Spring Boot application can be packaged as a **WAR** to deploy into an external servlet container (such as a compatible Apache Tomcat), or as a **Spring Boot executable WAR** that launches itself with `java -jar`. Both deployment modes can use **the exact same WAR file**, yet you must understand the internal directories accurately to avoid bundling duplicate servlet containers, missing dependencies, or misreading the classpath.

This lesson focuses on reading three key locations:

- `WEB-INF/classes/` — application classes and resources compiled by the project.
- `WEB-INF/lib/` — application JARs loaded by traditional servlet containers.
- `WEB-INF/lib-provided/` — **provided** JARs retained by a **Spring Boot executable WAR** for standalone execution; traditional containers do **not** put this folder on the webapp classpath under WAR standards.

After this lesson, you will be able to:

1. Inspect a `.war` file tree with `jar tf` without extracting everything.
2. Locate Java classes and `application.properties` in `WEB-INF/classes`, library dependencies in `WEB-INF/lib`, and embedded Tomcat dependencies in `WEB-INF/lib-provided`.
3. Explain why `WEB-INF/lib-provided` can **physically exist** inside the WAR yet **cause no conflict** when deployed to an external servlet container.
4. Distinguish Spring Boot's `WarLauncher` mechanism under `java -jar` from an external Tomcat's classloader.
5. Configure Maven (`<packaging>war</packaging>`, `provided` scope, Spring Boot Maven Plugin) or Gradle (`war`, `providedRuntime`, and `bootWar`).
6. Write a Java 17+ Spring MVC application that runs in both modes.
7. Independently verify the manifest, dependency placement, HTTP responses, context paths, `jakarta.servlet` namespace errors, and container versions.
8. Avoid confusing an executable WAR with a `BOOT-INF`-style JAR, and avoid assuming a traditional WAR must contain `WEB-INF/lib-provided`.

**Example versions:** Spring Boot **3.5.16**, Java **17+**, chosen to provide concrete syntax, libraries, and launcher names. Real projects should use the Spring Boot, Maven/Gradle, and servlet container lines approved by their team. Spring Boot 4 changes some artifact and starter names; do not apply 3.5 examples verbatim to another major version.

## 2. What Is a WAR? Why Is It Different from a JAR?

### 2.1. WAR in the Servlet Ecosystem

**WAR (Web Application Archive)** is a web application deployment package following the Java Servlet specification. Physically, a `.war` file uses the ZIP format just like a `.jar`, yet its webapp layout reserves special locations:

~~~text
example.war
├── META-INF/
│   └── MANIFEST.MF
├── index.html                       (if web root resources exist)
└── WEB-INF/
    ├── classes/
    │   └── com/example/.../*.class
    ├── lib/
    │   └── *.jar
    └── web.xml                       (if using a descriptor)
~~~

In a traditional WAR:

- `WEB-INF/classes` holds application classes and resources, acting as a webapp **classpath root**.
- Each JAR directly inside `WEB-INF/lib` becomes part of the web application classpath.
- `WEB-INF/web.xml` is the traditional deployment descriptor, though **not required** in many modern applications using programmatic or annotation-based initialization.
- Resources under `WEB-INF` are protected by the servlet container from direct HTTP requests under Servlet rules; they are **not** a "public static folder."
- Web-root files/resources (such as images or HTML at the WAR root) can be served by the container if appropriately configured.

For example, a Java application places `com.example.war.WebApplication` at:

~~~text
WEB-INF/classes/com/example/war/WebApplication.class
~~~

That is the **path stored inside the archive**, not the Java source path. The source normally lives at `src/main/java/com/example/war/WebApplication.java` and is compiled by Maven/Gradle into `.class`.

### 2.2. Spring Boot Executable WAR Extends the Traditional Layout

The Spring Boot Maven/Gradle plugin can build an **executable WAR** that both:

- deploys inside a compatible servlet container; and
- runs directly via `java -jar my-app.war` using the Spring Boot Loader.

To support both execution paths, Spring Boot adds launcher classes, a manifest entry point, and the **`WEB-INF/lib-provided`** directory for dependencies that must not enter an external container's webapp classpath yet are needed in embedded mode.

~~~text
demo-war-0.0.1-SNAPSHOT.war
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
│   └── launch/WarLauncher.class
└── WEB-INF/
    ├── classes/
    │   ├── com/example/war/
    │   │   ├── DemoWarApplication.class
    │   │   └── HelloController.class
    │   └── application.properties
    ├── lib/
    │   ├── spring-boot-*.jar
    │   ├── spring-context-*.jar
    │   └── ...
    └── lib-provided/
        ├── tomcat-embed-core-*.jar
        ├── tomcat-embed-el-*.jar
        ├── tomcat-embed-websocket-*.jar
        └── ...
~~~

This is an **illustrative tree**, since JAR names and versions depend on your build and dependency management. `WEB-INF/lib-provided` does not necessarily hold the exact three Tomcat files in every version; inspect the real artifact. `*` stands in for version/variant suffixes in the diagram, not literal filenames containing asterisks.

### 2.3. A Crucial Summary Table

| Path in WAR | What does it contain? | External servlet container | `java -jar` via Boot `WarLauncher` |
| --- | --- | --- | --- |
| `WEB-INF/classes/` | Application classes and resources | **Loaded into webapp classpath** | **Loaded into app classpath** |
| `WEB-INF/lib/*.jar` | Webapp runtime libraries | **Loaded into webapp classpath** | **Loaded with app** |
| `WEB-INF/lib-provided/*.jar` | Environment-supplied dependencies, typically embedded Tomcat | **Excluded from webapp classpath per Servlet WAR convention** | **Actively loaded by Boot Loader** |
| `org/springframework/boot/loader/` | Boot loader classes at archive root | Not the container's webapp bootstrap mechanism | `WarLauncher` bootstraps app |
| `META-INF/MANIFEST.MF` | Manifest and executable WAR entry point | Does not use `Main-Class` to launch the servlet app | `java -jar` reads `Main-Class` |
| `WEB-INF/web.xml` | Legacy descriptor / if needed | Processed by container on deploy | Not Boot Loader's primary mechanism |
| Web resources at WAR root | Web root content | May be served over HTTP per config | May be handled by framework/embedded container depending on config |

**Core point:** `WEB-INF/lib-provided` is **not a standard directory for servlet containers to load**. It is an organizational section inside a Spring Boot executable WAR solving a paradox: external Tomcat must use its own Tomcat, while `java -jar` needs embedded Tomcat to open a server itself.

## 3. Reading Each Directory Properly

### 3.1. `WEB-INF/classes` Is a Classpath Root

If the WAR contains:

~~~text
WEB-INF/classes/com/example/war/HelloController.class
WEB-INF/classes/application.properties
WEB-INF/classes/static/info.txt
~~~

then at runtime the application resolves the class by name:

~~~java
com.example.war.HelloController
~~~

and performs resource lookups such as:

~~~java
getClass().getClassLoader().getResource("application.properties");
~~~

rather than importing classes under package `WEB-INF.classes.com.example.war`. `WEB-INF/classes` is a **classpath root**, not part of the Java package name.

Typically source directories map as follows:

| Project Source | Location in WAR |
| --- | --- |
| `src/main/java/com/example/war/HelloController.java` after compile | `WEB-INF/classes/com/example/war/HelloController.class` |
| `src/main/resources/application.properties` | `WEB-INF/classes/application.properties` |
| `src/main/resources/static/info.txt` | `WEB-INF/classes/static/info.txt` |
| `src/main/resources/templates/page.html` | `WEB-INF/classes/templates/page.html` |
| `src/main/webapp/assets/logo.svg` (if used) | `assets/logo.svg` at web root, not `WEB-INF/classes` |
| `src/test/java/...` | **Not included** in the runtime WAR artifact |

For example, `application.properties` inside `WEB-INF/classes` remains a **classpath resource** read by Spring Boot at startup. `WEB-INF/classes/static/info.txt` can be served by Spring MVC static resource handling at its mapped URL if framework/configuration allows; do not assume the URL must contain `WEB-INF/classes`.

Never place passwords, API keys, or production secrets inside `src/main/resources/application.properties`, because packaging embeds them in the artifact. Use externalized configuration and proper secret management.

### 3.2. `WEB-INF/lib` Is the Webapp Library Classpath

Dependencies in `WEB-INF/lib` are used when the WAR deploys to an external servlet container. Libraries such as `spring-webmvc`, `spring-context`, Jackson, and business libraries must live on the webapp classpath unless supplied by the container under contract.

Example:

~~~text
WEB-INF/lib/spring-webmvc-6.*.jar
WEB-INF/lib/jackson-databind-2.*.jar
WEB-INF/lib/slf4j-api-2.*.jar
~~~

These are **illustrative names only**, and major versions may change with the Spring Boot BOM; do not use this snippet to count exact dependencies. For actual versions, inspect `mvn dependency:tree` or Gradle `dependencies` alongside `jar tf` on the output.

Traditional servlet containers load `WEB-INF/lib` JARs into a **web application classloader**. However, containers can also have shared parent-level libraries; delegation and classloading rules vary by server. If you accidentally package a Servlet API or Tomcat implementation inside `WEB-INF/lib` duplicating what the server provides, the risk of class conflicts and startup failures rises.

**Having a JAR in `WEB-INF/lib` does not mean Spring injects it as a bean**; it merely makes its classes and resources available on the classpath. Auto-configuration, component scanning, and bean lifecycles are separate mechanisms.

### 3.3. `WEB-INF/lib-provided` Holds Dependencies for Standalone Mode

When a Maven dependency is declared `provided`, or Gradle uses `providedRuntime`, and the WAR is packaged by the Spring Boot plugin, those libraries go into `WEB-INF/lib-provided`. The prime example is the embedded Tomcat starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
    <scope>provided</scope>
</dependency>
~~~

When the WAR deploys to external Tomcat:

~~~text
External Tomcat:
  server-managed servlet engine / servlet API / web container
        |
        v
  WEB-INF/classes + WEB-INF/lib
        |
        X WEB-INF/lib-provided is not part of the standard webapp classpath
~~~

When the WAR runs directly:

~~~text
java -jar demo-war.war
        |
        v
  Main-Class: org.springframework.boot.loader.launch.WarLauncher
        |
        +--> WEB-INF/classes
        +--> WEB-INF/lib/*.jar
        +--> WEB-INF/lib-provided/*.jar
        |
        v
  Start-Class: com.example.war.DemoWarApplication
        |
        v
  embedded Tomcat starts the application
~~~

**`provided` does not mean "never packaged in the WAR."** That holds for a plain WAR built by the Maven WAR Plugin under normal dependency scope rules, yet Spring Boot **`repackage`** places required `provided` dependencies in `WEB-INF/lib-provided` so the WAR can still run standalone. Likewise, Boot's `bootWar` collects dependencies from `providedRuntime`.

### 3.4. Why Not Strip Embedded Tomcat Completely?

If embedded Tomcat were completely omitted from the executable WAR, `java -jar` would lack a servlet engine to start an HTTP server. Spring Boot keeps it separated so **`WarLauncher`** can load it standalone while external containers ignore it. That is why `WEB-INF/lib-provided` differs from simply deleting the dependency.

Conversely, if your sole target is a **traditional WAR that never needs `java -jar`**, you can take the WAR created by Maven WAR Plugin or Gradle `war` without running Boot repackage; that archive may **lack `WEB-INF/lib-provided`**. The absence of that directory is **not an error** when the artifact is designed as a plain WAR.

## 4. WAR Runs Two Ways: Who Starts the Application?

### 4.1. Path A: External Servlet Container

Suppose operations deploys the WAR to an external Apache Tomcat:

~~~text
$CATALINA_BASE/webapps/demo-war.war
    |
    v
Tomcat unpacks or reads WAR
    |
    v
Tomcat creates webapp classloader
    |
    +--> WEB-INF/classes
    +--> WEB-INF/lib/*.jar
    |
    v
SpringBootServletInitializer / Servlet integration
    |
    v
Spring ApplicationContext initializes inside the servlet container
    |
    v
Controller receives requests via external Tomcat
~~~

In this case, **external Tomcat decides the HTTP port, connectors, webapp context path, and part of the servlet server layer**. The manifest's `Main-Class` is not used by Tomcat to run `main(String[] args)` like `java -jar`.

A Servlet-based Spring Boot app typically includes a class extending `SpringBootServletInitializer` and overriding `configure(SpringApplicationBuilder)` to register the entry point for Servlet bootstrap.

### 4.2. Path B: Executable WAR

Example:

~~~bash
java -jar target/demo-war-0.0.1-SNAPSHOT.war
~~~

The JVM reads the manifest and invokes **`WarLauncher`**, a `spring-boot-loader` class placed at the **WAR root** by the Spring Boot plugin. `WarLauncher` knows the nested locations:

~~~text
WEB-INF/classes/
WEB-INF/lib/
WEB-INF/lib-provided/
~~~

and builds the classloader before calling `Start-Class` (the application class containing `main`). Here embedded Tomcat is on the classpath thanks to `lib-provided`, and the app runs its own HTTP server.

### 4.3. Distinguishing `WarLauncher` from `JarLauncher`

| Property | Spring Boot Executable JAR | Spring Boot Executable WAR |
| --- | --- | --- |
| Common `Main-Class` (Boot 3.5) | `org.springframework.boot.loader.launch.JarLauncher` | `org.springframework.boot.loader.launch.WarLauncher` |
| App classes | `BOOT-INF/classes` | `WEB-INF/classes` |
| Dependency JARs | `BOOT-INF/lib` | `WEB-INF/lib`, `WEB-INF/lib-provided` |
| Plain external servlet container deployment | Not standard WAR deployment | Deployable if app is suitable and container compatible |
| On `java -jar` | Loader loads nested JARs | Loader also loads provided nested JARs |

**Do not run `java -cp app.war com.example.war.DemoWarApplication` expecting the standard JVM to discover nested dependencies.** The standard Java launcher does not read JARs nested inside `WEB-INF/lib`/`WEB-INF/lib-provided` the way Boot Loader does. For an executable WAR, use `java -jar` to go through the manifest/`WarLauncher`.

## 5. Complete Maven Example: A WAR Both Deployable and `java -jar` Runnable

### 5.1. Structure

Create a project using Java 17, Spring Boot 3.5.x, Spring Web, and Maven. File layout:

~~~text
demo-war/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/war/
    │   │   ├── DemoWarApplication.java
    │   │   └── HelloController.java
    │   └── resources/
    │       └── application.properties
    └── test/java/com/example/war/
        └── DemoWarApplicationTests.java
~~~

If generated from Spring Initializr, the project may include `mvnw`, `mvnw.cmd`, and `.mvn/wrapper/`; if created manually with the files below, use an installed `mvn`.

### 5.2. Complete `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>demo-war</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>war</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <!-- Spring MVC/JSON and application dependencies. -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <!-- Present when running WAR standalone; not loaded from WEB-INF/lib
             in an external servlet container. -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
            <scope>provided</scope>
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

Because the project **inherits `spring-boot-starter-parent`**, the parent already configures the `repackage` execution for Spring Boot Maven Plugin. Declaring the plugin inside `<build><plugins>` produces the executable WAR in the `package` phase.

**Why list both `spring-boot-starter-web` and `spring-boot-starter-tomcat`?** The Web starter normally pulls in the Tomcat starter transitively. Declaring the Tomcat starter **directly with `provided` scope** gives Maven an explicit placement directive rather than leaving it as a default runtime/compile dependency in `WEB-INF/lib`. The version is managed by the inherited Spring Boot BOM.

**If you already have a corporate parent:** keep that parent, import the `spring-boot-dependencies` BOM under `dependencyManagement`, and explicitly configure the `spring-boot-maven-plugin` version and `repackage` goal. Importing the BOM **does not bring along plugin executions**. Java compiler and Maven WAR Plugin settings must also be managed appropriately by the parent or module.

### 5.3. Boot Main Class + Servlet Initializer

Create `src/main/java/com/example/war/DemoWarApplication.java`:

~~~java
package com.example.war;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class DemoWarApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(DemoWarApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(DemoWarApplication.class, args);
    }
}
~~~

**This is a complete Java file.**

- `@SpringBootApplication`: marks the main configuration and enables component scanning and auto-configuration.
- `extends SpringBootServletInitializer` + `configure`: supplies the bootstrap path for an **external Servlet container**.
- `main(String[] args)`: entry point used when **`WarLauncher`** launches the app via `java -jar`.
- Both startup paths use **`DemoWarApplication.class`** as the configuration source so behavior stays consistent.

If you have `main` without a proper initializer, `java -jar` may work while the external container fails to bootstrap the Spring app properly. Conversely, if you have a servlet initializer without a Boot-launcher-callable `main`, a plain WAR may deploy externally yet fail the executable requirement.

### 5.4. Controller Handling HTTP GET

Create `src/main/java/com/example/war/HelloController.java`:

~~~java
package com.example.war;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "WAR_OK";
    }
}
~~~

`@RestController` writes the returned string straight to the HTTP response body. Because the controller sits in the same `com.example.war` package as the main class, default component scanning detects it.

### 5.5. Configuration Resource

Create `src/main/resources/application.properties`:

~~~properties
spring.application.name=demo-war
server.port=8080
~~~

On `java -jar`, embedded Tomcat uses `server.port=8080` unless overridden by env/JVM/CLI. **When deploying to an external Tomcat, the actual port is determined by external Tomcat connectors**—do not treat `8080` in the app's file as authoritative.

### 5.6. Spring Boot ApplicationContext Test

Create `src/test/java/com/example/war/DemoWarApplicationTests.java`:

~~~java
package com.example.war;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class DemoWarApplicationTests {

    @Test
    void contextLoads() {
        // Succeeds when Spring ApplicationContext initializes.
    }
}
~~~

`spring-boot-starter-test` has `test` scope. Maven's test classpath still includes the components needed for Spring Boot tests; `provided` scope does not drop Tomcat from the test classpath. This test only checks context loading; **it does not prove the entire HTTP deployment path**. For real applications, add smoke/integration tests against the packaged WAR itself.

### 5.7. Build and Run the Executable WAR

Inside `demo-war/`:

~~~bash
java -version
mvn -version
mvn clean package
java -jar target/demo-war-0.0.1-SNAPSHOT.war
~~~

If Maven Wrapper is present:

~~~bash
./mvnw clean package
java -jar target/demo-war-0.0.1-SNAPSHOT.war
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd clean package
java -jar .\target\demo-war-0.0.1-SNAPSHOT.war
~~~

Start Spring Boot in the first terminal and test the endpoint from a second terminal:

~~~bash
curl -s http://localhost:8080/hello
~~~

**Exact expected HTTP response body** (assuming unchanged URL/port and successful startup):

~~~text
WAR_OK
~~~

Application logs contain startup timestamps, thread names, and container info that vary by environment. Do not require entire stdout to match a verbatim sample.

**Standalone execution conclusion:** this WAR uses `WarLauncher` to load `WEB-INF/lib-provided` containing embedded Tomcat, so even though Tomcat is declared `provided`, the application still has a container to run itself.

## 6. Using `jar tf` to Inspect the Archive Without Extracting

### 6.1. Listing Files Inside the WAR

~~~bash
jar tf target/demo-war-0.0.1-SNAPSHOT.war
~~~

`jar tf` is a JDK tool that reads ZIP entries **without extracting or modifying** the WAR.

Look for lines like:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/WarLauncher.class
WEB-INF/classes/com/example/war/DemoWarApplication.class
WEB-INF/classes/com/example/war/HelloController.class
WEB-INF/classes/application.properties
WEB-INF/lib/spring-webmvc-6.x.y.jar
WEB-INF/lib-provided/tomcat-embed-core-10.x.y.jar
~~~

**`6.x.y` and `10.x.y` are illustrative version placeholders**, not literal filenames or runtime-measured results. In practice, read all entries and verify exact versions resolved by the BOM/build.

### 6.2. Filtering by the Three Groups on Linux/macOS

~~~bash
jar tf target/demo-war-0.0.1-SNAPSHOT.war |
  grep -E '^(WEB-INF/classes/|WEB-INF/lib/|WEB-INF/lib-provided/)'
~~~

To view only application classes and resources:

~~~bash
jar tf target/demo-war-0.0.1-SNAPSHOT.war |
  grep '^WEB-INF/classes/'
~~~

View only dependency JARs in the two library directories:

~~~bash
jar tf target/demo-war-0.0.1-SNAPSHOT.war |
  grep -E '^WEB-INF/(lib|lib-provided)/[^/]+\.jar$'
~~~

The last regex matches only `.jar` files directly inside those two paths. If the build introduces unusual nested paths, this filter skips them, which is also a signal to check packaging.

### 6.3. Filtering in Windows PowerShell

~~~powershell
jar tf .\target\demo-war-0.0.1-SNAPSHOT.war |
    Select-String '^WEB-INF/classes/'

jar tf .\target\demo-war-0.0.1-SNAPSHOT.war |
    Select-String '^WEB-INF/lib/'

jar tf .\target\demo-war-0.0.1-SNAPSHOT.war |
    Select-String '^WEB-INF/lib-provided/'
~~~

Paths **inside the JAR/WAR** always use `/`, even on Windows. Paths to the **external archive file** can use `.\target\...` in PowerShell.

### 6.4. Counting Contents Under the Right Conditions

Do not use "JAR count" as a package quality metric. A WAR with many dependencies due to many starters can still be valid; a WAR without `WEB-INF/lib-provided` can be valid if it is a plain WAR. Verify the deployment target and plugins first, then inspect the classpath.

Example entry count check if tracking build drift:

~~~bash
jar tf target/demo-war-0.0.1-SNAPSHOT.war |
  grep -c '^WEB-INF/lib/.*\.jar$'
~~~

Counts are only meaningful when comparing builds with the same dependencies/configuration. For a Boot executable WAR with `provided` Tomcat, **verify where Tomcat sits**, not just total JAR count.

## 7. Reading `MANIFEST.MF` to Distinguish Traditional WARs from Executable WARs

### 7.1. Manifest of an Executable WAR

The Spring Boot plugin updates the manifest to direct the JVM to the Boot Loader. In Spring Boot 3.5, key attributes are usually:

~~~text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: com.example.war.DemoWarApplication
Spring-Boot-Version: 3.5.16
~~~

This is an **illustrative excerpt of relevant attributes**, not a claim that every project's manifest has only four lines. Real manifests may contain additional entries or option-specific fields.

Explanation:

- `Main-Class`: the Java launcher invokes `WarLauncher`, not the application's `main` directly.
- `Start-Class`: Boot Loader invokes the class containing `main(String[] args)`.
- `Spring-Boot-Version`: helps identify the plugin/loader release, though it does not replace the dependency tree.
- Manifest lines follow line-wrapping rules; **do not parse a manifest assuming values never wrap across lines**.

### 7.2. Viewing the Manifest with `unzip` If Installed

~~~bash
unzip -p target/demo-war-0.0.1-SNAPSHOT.war META-INF/MANIFEST.MF
~~~

`unzip -p` streams the archive entry contents to stdout without altering the WAR. On Windows, if `unzip` is not installed, open the WAR with a ZIP utility to inspect `META-INF/MANIFEST.MF` read-only, or run `jar xf` inside a **separate temp directory** (noting that extraction writes files to disk) and avoid manually repacking the release artifact.

### 7.3. The Manifest Is Not the External Container Startup Mechanism

External Tomcat does not pick `Start-Class` from the manifest and invoke `public static void main`. It uses Servlet container webapp startup, reading `WEB-INF/classes`/`WEB-INF/lib` and the Spring initializer.

Therefore **a correct manifest is not enough** to confirm a WAR deploys externally. Conversely, **a correct initializer is not enough** to confirm `java -jar` works if the Spring Boot Loader or embedded dependencies were stripped.

## 8. Configuring Gradle to Produce the Same Style of Executable WAR

### 8.1. The `war` Plugin and Spring Boot `bootWar`

In Gradle, the `war` plugin enables WAR support and the `providedRuntime` configuration. The Spring Boot Gradle Plugin detects `war` and registers the **`bootWar`** task to package an executable WAR.

Per Spring Boot documentation, use:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
~~~

`providedRuntime` is better than `compileOnly` for embedded Tomcat because `compileOnly` is absent from the test classpath, which can cause web integration tests to fail. This is a **Gradle configuration**, not a Maven scope name. With Maven, use `<scope>provided</scope>`.

### 8.2. Complete `build.gradle` (Groovy DSL)

Using the Java sources and `application.properties` from section 5 (with the same package paths), create a separate Gradle project `demo-war-gradle/`:

~~~groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.5.16'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
~~~

The Spring Boot plugin works with `io.spring.dependency-management` to import the BOM for the Boot plugin version, so Spring Boot starters do not need explicit versions. Use a Gradle version compatible with **both the Boot 3.5 plugin and the dependency-management plugin**; the Gradle Wrapper should be committed and controlled by the project. In this setup `bootWar` outputs the executable WAR, while `war` may emit a separate plain WAR with a classifier per plugin conventions.

Create `settings.gradle`:

~~~groovy
rootProject.name = 'demo-war'
~~~

**Note:** the Maven and Gradle projects are **two illustrative build variants**. You can share the same Java sources, but you should not run both build tools on one directory tree and mix artifacts from `target/` and `build/libs/` without defining a single release source.

### 8.3. Building and Running with Gradle

When the project has a Gradle Wrapper:

~~~bash
./gradlew clean bootWar
java -jar build/libs/demo-war-0.0.1-SNAPSHOT.war
jar tf build/libs/demo-war-0.0.1-SNAPSHOT.war
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean bootWar
java -jar .\build\libs\demo-war-0.0.1-SNAPSHOT.war
jar tf .\build\libs\demo-war-0.0.1-SNAPSHOT.war
~~~

If using only a system-installed Gradle, run `gradle clean bootWar` and ensure a compatible version. **Verify the exact filename in `build/libs/`** if the project sets a custom `archiveBaseName`, classifier, or version.

Look for these entries:

~~~text
WEB-INF/classes/com/example/war/DemoWarApplication.class
WEB-INF/classes/com/example/war/HelloController.class
WEB-INF/lib/spring-webmvc-*.jar
WEB-INF/lib-provided/tomcat-embed-core-*.jar
org/springframework/boot/loader/launch/WarLauncher.class
~~~

If you run the `war` task instead of `bootWar`, the artifact normally follows a **plain WAR** layout and may omit the Boot Loader and `WEB-INF/lib-provided`. Do not compare the two tasks assuming their outputs match.

### 8.4. Groovy vs. Kotlin DSL: Equivalent Snippet

Here is a **`build.gradle.kts` fragment** (not a full file, yet sufficient to show dependency declarations):

~~~kotlin
plugins {
    java
    war
    id("org.springframework.boot") version "3.5.16"
    id("io.spring.dependency-management") version "1.1.7"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    providedRuntime("org.springframework.boot:spring-boot-starter-tomcat")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Remaining blocks such as `repositories`, `group`/`version`, toolchain, and test tasks must be configured per your project. In Kotlin DSL, `providedRuntime(...)` becomes available only after the `war` plugin creates that configuration.

## 9. From Scope/Configuration to WAR Archive Path

### 9.1. Maven Dependency Scopes

In Maven, consider two classpath scopes:

- **External container runtime classpath:** takes app classes, WAR `WEB-INF/lib`, and container-supplied libraries.
- **Executable WAR runtime classpath:** Boot `WarLauncher` adds `WEB-INF/lib-provided` to the app classloader.

| Maven dependency scope | When compiling code | When tests run | Typical location in Boot executable WAR | Notes |
| --- | --- | --- | --- | --- |
| `compile` | Yes | Yes | `WEB-INF/lib` | Webapp runtime dependencies |
| `runtime` | Not necessarily at direct compile | Yes | `WEB-INF/lib` | E.g., drivers needed only at runtime |
| `provided` | Yes | Yes | `WEB-INF/lib-provided` | Expected to be provided by external container |
| `test` | Not at main compile | Yes | Excluded from WAR runtime | JUnit, Mockito, and test utilities |

This is the **typical placement with Spring Boot Maven Plugin `repackage` and the WAR layout**. If the project has exclusions, custom plugin configs, `system`/`optional` scopes, or other intervening plugins, inspect the actual artifact. **Do not infer placement from scope without knowing what kind of archive you are inspecting.**

### 9.2. Gradle Configurations

| Gradle | Purpose in Boot WAR project | Placement under `bootWar` |
| --- | --- | --- |
| `implementation` | Application dependencies | Usually `WEB-INF/lib` |
| `runtimeOnly` | Dependencies needed at runtime | Usually `WEB-INF/lib` |
| `providedRuntime` | Libraries to be supplied by external container | `WEB-INF/lib-provided` |
| `testImplementation`/`testRuntimeOnly` | Tests | Excluded from WAR runtime |
| `compileOnly` | Compile only | Should not replace `providedRuntime` for embedded Tomcat needed in tests |

**Clarifying a common question:** `spring-boot-starter-web` depends transitively on the Tomcat starter; adding `providedRuntime 'spring-boot-starter-tomcat'` lets the WAR plugin distinguish embedded Tomcat from web application libraries. Verify `bootWar` output directly, since Gradle has its own dependency configuration/resolution rules rather than relying solely on artifact names.

### 9.3. Do Not Mark Every Library as `provided`

Just because an external container supplies the **Servlet API and engine** does not mean it supplies Spring Framework, Jackson, database drivers, or business code. If you mark `spring-boot-starter-web` as provided and exclude it from `WEB-INF/lib` while the external server has no Spring Web, the application will throw missing-class errors on deployment.

Practical rule of thumb:

- Servlet engine / Servlet API owned by the external server: **`provided`** per deployment contract.
- Application libraries not supplied by the external container: packaged in `WEB-INF/lib`.
- Test-only dependencies: excluded from the runtime WAR.
- JNDI drivers or shared libraries genuinely supplied by the server: mark provided only when **confirmed by operations documentation** and tested; never guess.

## 10. Deploying the WAR to an External Servlet Container

### 10.1. Choosing a Spring Boot-Compatible Container

Spring Boot 3.x uses **Jakarta Servlet** APIs (`jakarta.servlet.*`), instead of `javax.servlet.*` used by Spring Boot 2.x and legacy servlet containers. Consequently, a Boot 3.5 WAR cannot be assumed compatible with Tomcat 9 merely because both are called "Servlet containers."

Select a Tomcat/Jetty/server version with Jakarta Servlet compatibility supported by your Boot release; for this Boot 3.5 example, **Tomcat 10.1** aligns with the embedded Tomcat 10.1 line. In production, verify system requirement tables, organizational standards, JVM/Jakarta versions, and the servlet features and framework libraries used before deploying.

### 10.2. Placing the WAR File into Tomcat

This example assumes you manage a local Tomcat with its own `CATALINA_BASE`, running with `autoDeploy` enabled. Copy `target/demo-war-0.0.1-SNAPSHOT.war` into `webapps`:

~~~bash
cp target/demo-war-0.0.1-SNAPSHOT.war \
  "$CATALINA_BASE/webapps/demo-war.war"
~~~

This is a **POSIX example**, assuming `CATALINA_BASE` exists and you have deploy permissions; it does not start Tomcat itself. Make sure any external tests/services the app relies on are also ready.

If the WAR is named `demo-war.war`, Tomcat will by default deploy it under context path `/demo-war` when auto-deploy and standard container settings are active. The example endpoint is then:

~~~bash
curl -s http://localhost:8080/demo-war/hello
~~~

Expected response body:

~~~text
WAR_OK
~~~

**Warning:** `/demo-war` and port 8080 are **illustrative default Tomcat assumptions**, not values hardcoded by Spring Boot. If operations configures another context path, host/vhost, port, or names the WAR `ROOT.war`, the real URL changes.

### 10.3. Why Doesn't External Tomcat Load `lib-provided`?

The container only loads standard WAR classpath locations (`WEB-INF/classes` and `WEB-INF/lib/*.jar`), plus libraries it provides itself. `WEB-INF/lib-provided` is not a directory the Servlet spec tells containers to scan as application libraries. Therefore:

- **External** Tomcat uses the server's own Tomcat/Jakarta Servlet implementation.
- Spring Framework and business libraries still come from the WAR's `WEB-INF/lib`.
- Embedded Tomcat inside `WEB-INF/lib-provided` is not loaded into the webapp classloader as a `WEB-INF/lib` dependency.
- The WAR may still contain `WarLauncher` at root; it does not override the external container's bootstrap flow.

That is the **core design intent** of a Spring Boot executable WAR. Never try to force external Tomcat to load `WEB-INF/lib-provided` for "completeness"—doing so risks injecting duplicate embedded Tomcat/Jakarta APIs into the webapp classloader.

### 10.4. Cases Unsuitable for WAR

Spring Boot WebFlux built on Reactor Netty does not support traditional servlet WAR deployment the way a Spring MVC Servlet application does. If an application is reactive-first WebFlux, do not switch `packaging` from JAR to WAR expecting external Tomcat to load Boot as a regular servlet app.

Before choosing WAR, ask: **does the operating environment require an external servlet container?** If not, an executable Spring Boot JAR is the common choice and easier to deploy independently. A WAR is appropriate when the application must run inside a centrally managed container or match an existing infrastructure model.

## 11. One WAR Can Be Both Executable and Deployable: Limitations to Remember

### 11.1. What Differs Between the Two Runs?

Same Java controller, yet the two modes can differ:

| Aspect | `java -jar` | WAR in External Tomcat |
| --- | --- | --- |
| HTTP port | Embedded Tomcat per Spring config, e.g., 8080 | External Tomcat Connector config |
| Context path | Usually root `/` if unconfigured | Usually based on WAR name / Host config |
| Servlet engine | From `WEB-INF/lib-provided` | Server-managed Tomcat/Jakarta libraries |
| Classpath | Boot `WarLauncher` loads both `lib` and `lib-provided` | Container loads `classes` + `lib` per rules |
| Spring startup | `main` via `Start-Class` | `SpringBootServletInitializer` via Servlet integration |
| JVM options | `java -jar` command / process runner | Java process running external Tomcat |
| Environment / file paths | Per app process cwd and env | Per Tomcat process env and cwd |
| Logging / shared libraries | Per embedded app / classpath | May be affected by server/shared classloaders |

Thus **"runs with `java -jar`" does not prove "deploys cleanly to external Tomcat"** and vice versa. Test both if your organization commits to supporting both modes.

### 11.2. Why Is a Boot WAR Not Just a Regular ZIP?

A Spring Boot executable WAR contains Boot Loader code and nested dependencies. Nested JAR entries must be written with the layout and ZIP storage methods that Boot Loader expects. If you unpack and re-ZIP a WAR with a script that breaks layout, manifest, or entry storage methods, `java -jar` can break even though an external container still accepts the WAR.

Use Spring Boot Maven Plugin `repackage` or Gradle `bootWar` to produce an executable WAR; never manually drop `spring-boot-loader` files into a JAR root hoping bootstrapping works.

### 11.3. An Executable WAR Is Not a Library JAR

In a WAR, application classes live under `WEB-INF/classes` rather than root package paths like `com/example/war/*.class`. Therefore do not use a WAR as a dependency in place of a library JAR module for another project. Extract shared code into a Java library module or publish the proper library artifact.

## 12. Distinguishing a Plain WAR from a Boot Executable WAR

Some projects run only Maven `maven-war-plugin` or Gradle `war` **without** Boot `repackage`/`bootWar`. In that case:

- `WEB-INF/classes`: still contains app classes.
- `WEB-INF/lib`: still contains packaged libraries.
- `WEB-INF/lib-provided`: may **not exist**.
- Root `org/springframework/boot/loader/...`: may **be absent**.
- Manifest `Main-Class: WarLauncher`: **not guaranteed**.
- `java -jar plain.war`: typically fails to run because no Boot entry point or embedded libs were packaged.

**A plain WAR is not necessarily a broken artifact.** If it is meant for external container deployment and tested against that contract, lacking `lib-provided` is normal. Reach the right conclusion based on deployment requirements, build task/goal, and specific output artifact.

### 12.1. Maven Output When Using `repackage`

With `spring-boot-maven-plugin:repackage`, the plugin may **replace the original WAR artifact** with the executable WAR; the non-executable original is normally preserved alongside it with the `.original` suffix by default. With a custom classifier, outputs differ. Do not assume two WARs exist with the same structure and path.

Verify the exact file published/deployed by CI rather than grabbing the newest file in `target`. An artifact ending in `.original` may be a plain WAR lacking `lib-provided`, unlike the executable WAR.

### 12.2. Gradle Output When Both `war` and `bootWar` Exist

The Spring Boot Gradle plugin can generate a `bootWar` executable artifact and a `war` plain artifact (typically using the `plain` classifier by Boot 3.x convention). Do not pick `*-plain.war` and expect it to run via `java -jar` without configuring an executable manifest/loader. Configure explicit names/classifiers in CI and smoke-test the exact artifact intended for release.

## 13. Typical Errors and How to Fix Them

| Symptom | Error Mechanism | Diagnosis and Resolution |
| --- | --- | --- |
| `java -jar app.war` reports `no main manifest attribute` | Running a plain WAR, missing Boot `repackage`/`bootWar` | Read manifest; verify build goal and right artifact |
| WAR has `WEB-INF/classes` yet no `WEB-INF/lib-provided` | No provided dependencies or plain WAR artifact | Check deployment target, Maven scopes / Gradle configurations, and Boot plugin execution |
| `java -jar` reports missing Tomcat/Servlet classes | Embedded Tomcat was excluded or not in `lib-provided` | Check `WEB-INF/lib-provided`, dependency graph, and plugin excludes |
| External Tomcat deploy reports duplicate Servlet / Servlet API classes | Embedded servlet container packaged in `WEB-INF/lib`, or server/library incompatibility | Mark Tomcat `provided`/`providedRuntime`, inspect actual archive, check server version |
| `ClassNotFoundException: jakarta.servlet...` | Servlet container too old or wrong dependency scope/classpath | Use a Jakarta-compatible container supported by your Boot line; inspect lib placement |
| `NoClassDefFoundError: org.springframework...` on external container | Spring libs mistakenly marked provided or excluded | Keep application dependencies in `WEB-INF/lib`; do not assume external Tomcat provides Spring |
| `@RestController` returns 404 after deploy | WAR context path is not root, or bootstrap/config wrong | Try `/<war-name>/hello`; check deployment logs and initializer |
| HTTP 404 even though `java -jar` works | External Servlet initializer failed to bootstrap app or wrong context path | Verify extending `SpringBootServletInitializer`/`configure` and Tomcat context |
| `server.port=8080` has no effect in external Tomcat | Port is owned by external connector | Update Tomcat server config/URL; do not change `application.properties` to control external server |
| `jar tf` shows `tomcat-embed-*.jar` inside `WEB-INF/lib` | Maven/Gradle dependency scope not set properly | Inspect compile/transitive deps, direct `provided`/`providedRuntime`, clean rebuild |
| Gradle `bootWar` does not exist | `war` plugin or Boot plugin not applied | Check `plugins`, `./gradlew tasks`, and Gradle version |
| Gradle `compileOnly` Tomcat causes test failures | `compileOnly` is absent from test classpath | Use `providedRuntime` per Spring Boot guide |
| Maven `repackage` does not run | Not inheriting Boot parent, goal unbound, or plugin undeclared | Declare plugin version + execution in custom parent/child |
| Manifest still shows `JarLauncher` inside a `.war` file | Wrong task/JAR layout or custom plugin overrode manifest | Check Spring Boot packaging/layout, output tasks; do not override manifest in wrong plugin |
| A Tomcat JAR appears in both `lib` and `lib-provided` | Dependency conflict / custom packaging / duplicate entries | Inspect `jar tf` and effective dependency graph; remove duplicate declaration |
| External WAR deploy fails with `javax.servlet`/`jakarta.servlet` | Mixing Spring Boot 2.x/3.x and servlet container generations | Check compatibility matrix and migrate import namespaces |
| App runs yet `application.properties` is not seen | Resources omitted from `WEB-INF/classes` or config overridden | Check files in WAR and Spring property sources / external config |
| External server adds `WEB-INF/lib-provided` to app classpath itself | Server has non-standard custom scan/classloader or broken deploy script | Remove that custom path so the container uses its own implementation |

### 13.1. Ordered Debugging Procedure

**Step 1 — Identify the exact file:** artifact name and exact path from Maven/Gradle/CI; distinguish executable WAR vs. plain WAR.

**Step 2 — Inspect the layout:** `jar tf`, verify the three folders `classes`/`lib`/`lib-provided`, and Boot Loader.

**Step 3 — Read the manifest:** Is `Main-Class` `WarLauncher`? Is `Start-Class` the main class? If not, you may be holding a plain WAR or a misconfigured build.

**Step 4 — Read the dependency graph:** Maven `dependency:tree`/`help:effective-pom` or Gradle `dependencies`/`dependencyInsight`; verify Tomcat starter scope/configuration.

**Step 5 — Smoke-test both modes:** `java -jar` and external Tomcat (if the project supports both); compare port, context path, and logs.

**Step 6 — Fix only the root cause:** scope, plugin/task, or container compatibility; do not randomly delete Tomcat JARs to shrink size and break executable mode.

## 14. Path Analysis Exercise Using a Sample Archive Listing

Suppose a WAR contains these entries:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/WarLauncher.class
WEB-INF/classes/com/example/war/DemoWarApplication.class
WEB-INF/classes/com/example/war/HelloController.class
WEB-INF/classes/application.properties
WEB-INF/lib/spring-context-6.x.y.jar
WEB-INF/lib/spring-webmvc-6.x.y.jar
WEB-INF/lib-provided/tomcat-embed-core-10.x.y.jar
WEB-INF/lib-provided/tomcat-embed-el-10.x.y.jar
~~~

Answer the following:

**Question A:** Where does an **external servlet container's** application classloader find `HelloController.class`?  
**Answer:** `WEB-INF/classes/com/example/war/HelloController.class`, treating `WEB-INF/classes` as the classpath root.

**Question B:** Where is the Spring WebMVC JAR located for external container use?  
**Answer:** `WEB-INF/lib/spring-webmvc-6.x.y.jar`, where WAR webapp libraries are loaded by the container.

**Question C:** Why does `tomcat-embed-core` in `lib-provided` not cause two Tomcat engines on external deployment?  
**Answer:** `WEB-INF/lib-provided` is not a standard webapp library classpath scanned by external containers; external Tomcat uses its own engine.

**Question D:** Why can the exact same WAR file run with `java -jar`?  
**Answer:** Spring Boot's `WarLauncher` constructs a classloader spanning `WEB-INF/classes`, `WEB-INF/lib`, **and** `WEB-INF/lib-provided`; embedded Tomcat is present for standalone execution.

**Question E:** Does every WAR contain `WEB-INF/lib-provided`?  
**Answer:** No. It is a directory serving Boot executable WARs when provided dependencies exist; a plain WAR may lack it completely.

**Question F:** Can you remove `WEB-INF/lib-provided` and still deploy externally?  
**Answer:** Plain external deployment may still work if all other requirements hold, yet standalone `java -jar` can break. Do not manually edit packaged contents without confirming the artifact contract.

**Question G:** Does `Main-Class=WarLauncher` cause external Tomcat to call `main`?  
**Answer:** No. External Tomcat uses Servlet bootstrap and initializers, not the Java launcher manifest used by `java -jar`.

## 15. Hands-On Exercises with the Sample Project

### Exercise 1 — Identify the Archive

Create the Maven project in section 5 and run `mvn clean package`. Use `jar tf` to find:
- `WEB-INF/classes/com/example/war/DemoWarApplication.class`;
- `WEB-INF/lib/` with Spring dependencies;
- `WEB-INF/lib-provided/` with embedded Tomcat dependencies.

Record the real Tomcat filenames and versions (do not copy placeholder names). Explain which mode loads each file.

### Exercise 2 — Compare Manifest Fields

Read `META-INF/MANIFEST.MF`. Identify `Main-Class` and `Start-Class`. Explain why `Main-Class` is `WarLauncher` rather than pointing directly to `DemoWarApplication`.

### Exercise 3 — Check URLs Across Deployment Modes

Run the executable WAR and call `http://localhost:8080/hello`. Next deploy the same WAR to external Tomcat as `demo-war.war` and call `http://localhost:8080/demo-war/hello` under typical configuration. Note that the response body is `WAR_OK` while the URL context path need not match.

### Exercise 4 — Wrong Scope

In a test-only copy of the project, remove `<scope>provided</scope>` from the Tomcat starter dependency, run clean package, and check which directory receives the Tomcat JARs. Do not deploy the broken version to external Tomcat. Restore the scope, rebuild, and compare `jar tf`.

### Exercise 5 — Gradle `providedRuntime`

Create the Gradle variant with `war` and Spring Boot plugins, `implementation starter-web` + `providedRuntime starter-tomcat`, and run `bootWar`. Inspect the output and compare the three key locations against the Maven output.

### Exercise 6 — CI Check

Write a smoke check in your **own project's** pipeline that fails if an executable WAR expected to have `WarLauncher`, `WEB-INF/classes`, or `WEB-INF/lib-provided` lacks any of them. Do not apply this check to a plain WAR; define the artifact contract first.

## 16. Pre-Release Checklist for WARs

- [ ] Target decided: external-container-only, `java -jar`-only, or dual-mode support.
- [ ] If external deployment: Servlet application is compatible with the Jakarta/container version.
- [ ] `<packaging>war</packaging>` or Gradle `war` plugin is properly configured.
- [ ] For executable WAR: Spring Boot `repackage` or `bootWar` runs, not plain `war` alone.
- [ ] `WEB-INF/classes` holds the application classes and resources actually needed.
- [ ] `WEB-INF/lib` holds Spring MVC/Jackson/business runtime libraries, not confused with `lib-provided`.
- [ ] Embedded servlet container is marked Maven `provided` or Gradle `providedRuntime` by design.
- [ ] `WEB-INF/lib-provided` contains provided dependencies needed for `java -jar`, not misplaced in `WEB-INF/lib`.
- [ ] Verified `Main-Class=WarLauncher` and `Start-Class` of the executable archive.
- [ ] Main class supports both `main` and `SpringBootServletInitializer` if dual-mode is required.
- [ ] Ran `jar tf`, dependency tree, and HTTP tests on the exact artifact to be released.
- [ ] On external deploy, verified port and context path belong to the external server.
- [ ] Did not mark all Spring libraries as provided when the external server does not supply them.
- [ ] Did not mix Spring Boot 3.x Jakarta APIs with `javax.servlet.*` generation servlet containers.
- [ ] Did not store secrets inside embedded `application.properties` or treat the manifest as a security control.
- [ ] Aware that `WEB-INF/lib-provided` can be completely absent in a plain WAR without being an error.

## 17. Official Documentation for Reference

- Spring Boot 3.5 — Nested JARs and executable WAR structure: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html
- Spring Boot 3.5 — Launching Executable JARs/WARs (WarLauncher): https://docs.spring.io/spring-boot/3.5/specification/executable-jar/launching.html
- Spring Boot 3.5 — Maven Packaging Executable Archives: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Spring Boot 3.5 — Traditional Deployment: https://docs.spring.io/spring-boot/3.5/how-to/deployment/traditional-deployment.html
- Spring Boot 3.5 — Gradle Plugin Packaging: https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html
- Spring Boot 3.5 — System Requirements: https://docs.spring.io/spring-boot/3.5/reference/getting-started/system-requirements.html
- Spring Boot 3.5 — SpringBootServletInitializer API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/support/SpringBootServletInitializer.html
- Spring Boot 3.5 — BootWar API, providedClasspath: https://docs.spring.io/spring-boot/3.5/gradle-plugin/api/java/org/springframework/boot/gradle/tasks/bundling/BootWar.html
- Maven WAR Plugin: https://maven.apache.org/plugins/maven-war-plugin/
- Gradle WAR Plugin: https://docs.gradle.org/current/userguide/war_plugin.html

**Conclusion:** Read a Spring Boot WAR by its three regions: **`WEB-INF/classes` = application code and resources**, **`WEB-INF/lib` = webapp runtime libraries when running in an external container**, and **`WEB-INF/lib-provided` = dependencies expected from the external container yet retained by the Boot Loader for `java -jar`**. This design allows **a single executable WAR** to satisfy both deployment paths when properly bootstrapped and configured. Before declaring anything "right or wrong," confirm whether the WAR is **plain or executable**, read the manifest, inspect the archive with `jar tf`, and smoke-test the execution path the product actually supports.