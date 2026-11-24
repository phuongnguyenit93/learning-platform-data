# Preparing SpringBootServletInitializer and the Application Class for WAR Deployment

## 1. Goal and Real-World Context

Spring Boot applications are typically run with `java -jar` using an **embedded web server**. However, in enterprise environments, a web application may have to run inside an **external Servlet container** such as Apache Tomcat managed by an operations team. In that case, the application is usually packaged as a **WAR (Web Application Archive)** and Spring Boot needs a mechanism to initialize the `ApplicationContext` through the container's lifecycle.

The key mechanism is `SpringBootServletInitializer`. For a Spring MVC/Servlet application, this class enables an external container to bootstrap Spring Boot when the WAR is deployed. **Changing `.jar` to `.war` is not enough**: you must prepare the application class properly, configure packaging, and place the servlet engine dependency in the right scope.

Learning objectives:

1. Distinguish the two startup paths: `main(String[] args)` and `SpringBootServletInitializer.configure(SpringApplicationBuilder)`.
2. Write a Java 17+ class annotated with `@SpringBootApplication` that extends `SpringBootServletInitializer`, overrides `configure`, and still runs via `java -jar`.
3. Build a WAR with Maven (`<packaging>war</packaging>`, Tomcat `provided`) or Gradle (`war` plugin, `providedRuntime`, `bootWar` task).
4. Inspect `WEB-INF/classes`, `WEB-INF/lib`, `WEB-INF/lib-provided`, and recognize a proper executable WAR.
5. Deploy to a compatible Tomcat, verify the URL with the context root, and read logs when deployment fails.
6. Understand Jakarta Servlet compatibility, the Java runtime, component scanning, bean registration, and CI verification steps.

**Illustrative versions:** Spring Boot 3.3.5, Java 17, Tomcat 10.1, compatible Maven/Gradle Wrapper. This is a clearly scoped version example, not a recommendation to use the latest software release. In real deployments, follow your project's support matrix and upgrade policy.

## 2. Understanding the Two Startup Paths

### 2.1. When Running an Executable JAR or Executable WAR

~~~text
java -jar application.war
    |
    v
Spring Boot Launcher
    |
    v
Application.main(String[] args)
    |
    v
SpringApplication.run(Application.class, args)
    |
    v
Spring ApplicationContext + embedded Tomcat
    |
    v
DispatcherServlet -> Controller
~~~

Here **the application starts the embedded servlet engine itself**. `server.port` is used by Spring Boot for the embedded server, and `main` is the direct entry point. When running only with an embedded server, `SpringBootServletInitializer` is not needed.

### 2.2. When an External Tomcat Deploys the WAR

~~~text
Already-running External Tomcat 10.1
    |
    v
Deploy war-demo.war into web application context
    |
    v
Servlet startup detects WebApplicationInitializer
    |
    v
SpringBootServletInitializer.onStartup(ServletContext)
    |
    v
configure(SpringApplicationBuilder)
    |
    v
Spring ApplicationContext + register DispatcherServlet
    |
    v
HTTP /war-demo/ping -> Controller
~~~

An external Tomcat has its **own port, connector, classloader, and lifecycle**. When deploying a WAR, the container **does not call the static `main` method**. Instead, Spring Web uses the `WebApplicationInitializer` mechanism to invoke the application's initializer, and `configure` declares the Spring configuration sources to load.

An executable WAR built by the Spring Boot plugin can support **both run styles**. That does not mean the two bootstrap flows are identical: the Java entry point and the Servlet container callback are two distinct entry points.

### When Does This Not Apply?

- **Spring MVC/Servlet:** suitable for traditional WAR deployment.
- **Pure Spring WebFlux with Reactor Netty:** Spring Boot 3.3 documentation does not support traditional servlet-style WAR deployment for WebFlux. Do not use this guide to try packaging Netty into a Tomcat WAR application.
- **Standard executable JAR:** no WAR or initializer is needed if there is no external container requirement.

## 3. The SpringBootServletInitializer API and `configure` Signature

In Spring Boot 3, use these imports:

~~~java
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;
~~~

`SpringBootServletInitializer` provides a `WebApplicationInitializer` implementation that bridges the servlet container lifecycle to creating the Spring Boot `ApplicationContext`. Servlets, filters, and registration beans are registered in the appropriate context.

The most important part:

~~~java
@Override
protected SpringApplicationBuilder configure(SpringApplicationBuilder application) {
    return application.sources(WarDemoApplication.class);
}
~~~

Explanation:

- `protected` and the `SpringApplicationBuilder` return type must match the signature; `@Override` lets the compiler catch mismatched parameters or return types.
- `application.sources(WarDemoApplication.class)` adds the class annotated with `@SpringBootApplication` as the **configuration source** for Spring when the external container calls the initializer.
- `configure` returns the builder after configuration; it **does not call `SpringApplication.run` itself** and does not return an `ApplicationContext`.
- `SpringBootServletInitializer` is **not** a Controller, Servlet, or Filter; do not put `@RestController` on the initializer.
- If the initializer class is also the configuration source, Spring Boot may provide sensible default behavior; even so, explicitly configuring `sources(...)` avoids mistakes in projects with multiple configurations.

**Do not confuse** the old package from earlier Spring Boot generations with Boot 3's `org.springframework.boot.web.servlet.support.SpringBootServletInitializer`. Always check imports when migrating a project.

## 4. Sample Project with One Application Class Having Two Entry Points

For example, create the `war-demo` project:

~~~text
war-demo/
├── pom.xml                     (choose when using Maven)
├── mvnw, mvnw.cmd, .mvn/wrapper/
├── build.gradle                (choose when using Gradle Groovy DSL)
├── settings.gradle
├── gradlew, gradlew.bat, gradle/wrapper/
└── src/
    ├── main/
    │   ├── java/com/example/war/
    │   │   ├── WarDemoApplication.java
    │   │   └── PingController.java
    │   └── resources/application.properties
    └── test/java/com/example/war/
        └── PingControllerTest.java
~~~

The diagram lists **two build options for comparison**; a real repository is not required to maintain Maven and Gradle side by side.

### 4.1. File `src/main/java/com/example/war/WarDemoApplication.java`

~~~java
package com.example.war;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class WarDemoApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder application) {
        return application.sources(WarDemoApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(WarDemoApplication.class, args);
    }
}
~~~

This is a **self-contained, complete** Java class whose filename matches the public class name and uses Spring Boot 3 APIs. Both startup paths use the **same configuration source `WarDemoApplication.class`**:

- **External container:** calls `configure` via the initializer to create the web application context.
- **Executable WAR:** Boot Launcher calls `main`; `SpringApplication.run` initializes Spring and embedded Tomcat.

`@SpringBootApplication` enables Spring Boot auto-configuration and component scanning from package `com.example.war`. Make sure Controllers and Services are in this package or its subpackages; if you move code to another root package, component scanning may no longer find the beans.

### 4.2. File `src/main/java/com/example/war/PingController.java`

~~~java
package com.example.war;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

This controller is enough to verify both embedded and external modes. The Spring MVC mapping is **always `/ping` inside the application**. The external WAR prefix, such as `/war-demo`, is prepended as the context root by the servlet container.

### 4.3. File `src/main/resources/application.properties`

You can omit this file or add non-sensitive settings:

~~~properties
spring.application.name=war-demo
~~~

**Do not put database passwords or production tokens in source.** For this lab, there is no need to declare `server.port` or `server.servlet.context-path`. When running in embedded mode, port 8080 and context root `/` are usually sufficient; when deploying to external Tomcat, the external container decides the port and context root.

## 5. Maven: Configuring WAR Packaging

### 5.1. Complete POM Using Spring Boot Starter Parent

File `pom.xml` for the same application above:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>war-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

Meaning:

1. `<packaging>war</packaging>` tells Maven to use the WAR lifecycle and produce a WAR archive instead of a JAR.
2. `spring-boot-starter-web` provides Spring MVC and web application libraries.
3. `spring-boot-starter-tomcat` is a dependency of the Spring Web starter, but is **declared directly** with `<scope>provided</scope>` so the external container takes responsibility for the Servlet engine.
4. `spring-boot-starter-test` is only for testing and does not put test code into the runtime WAR.
5. `spring-boot-maven-plugin` together with the Starter Parent configuration produces a **repackaged/executable WAR**.
6. The parent manages related library versions; avoid adding separate Servlet API or Tomcat versions not verified for compatibility.

**Why does `provided` still appear inside the executable WAR?** Spring Boot Maven `repackage` places provided servlet container libraries into `WEB-INF/lib-provided` when using the WAR layout. An external container does not treat them as regular webapp libraries, yet `java -jar` can use them to run embedded Tomcat.

### 5.2. Projects Not Inheriting from Starter Parent

A POM with a corporate parent or that only imports the `spring-boot-dependencies` BOM **does not automatically get** full Maven plugin management/execution from Starter Parent. You must ensure:

- A compatible Maven War Plugin is configured or managed.
- The Spring Boot Maven Plugin uses a version aligned with the Spring Boot project.
- The `repackage` goal is bound to the `package` lifecycle phase if you want an executable WAR.

The following is a **fragment** inside `<build><plugins>` of a full POM, **not a standalone POM**:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.3.5</version>
    <executions>
        <execution>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

If you already use Starter Parent, **do not add a duplicate execution** just by copying this snippet: the Parent already configures it. For a deployable-only WAR that does not need to run via `java -jar`, the Spring Boot loader is not strictly required; this lesson uses an executable WAR to test both run modes on the same artifact.

### 5.3. Build and Inspect the WAR

Linux/macOS:

~~~bash
./mvnw --version
./mvnw clean verify
ls -lh target/*.war
jar tf target/war-demo-0.0.1-SNAPSHOT.war | grep '^WEB-INF/'
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd --version
.\mvnw.cmd clean verify
Get-ChildItem .\target\*.war
jar tf .\target\war-demo-0.0.1-SNAPSHOT.war |
    Select-String '^WEB-INF/'
~~~

`clean verify` runs through `package` and executes unit tests as configured. If the project changes `finalName`, module, or version, locate the **exact WAR name generated** rather than hardcoding the example path. The pre-`repackage` version may appear as an `.original` file, which is not the final executable WAR.

## 6. Gradle: `war` Plugin, `providedRuntime`, and `bootWar`

### 6.1. Groovy DSL

File `settings.gradle`:

~~~groovy
rootProject.name = 'war-demo'
~~~

Complete `build.gradle` file:

~~~groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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

tasks.named('test') {
    useJUnitPlatform()
}

springBoot {
    mainClass = 'com.example.war.WarDemoApplication'
}
~~~

**Explanation:**

- `id 'war'` applies the Gradle War plugin; when the Spring Boot Gradle plugin sees this plugin, it creates the **`bootWar`** task.
- `providedRuntime` is the configuration for a servlet container already provided by the external runtime; `bootWar` puts these libraries into **`WEB-INF/lib-provided`**.
- `providedRuntime` is **not the same as `compileOnly`**. Per Spring Boot documentation, `compileOnly` does not serve the web integration test classpath as desired.
- `springBoot.mainClass` makes the entry point explicit when running the executable WAR; it **does not replace the initializer** for an external container.
- `useJUnitPlatform()` enables running JUnit Jupiter tests through Gradle Test.
- `io.spring.dependency-management` supports BOM management when paired with the Spring Boot Gradle plugin.

If the project centralizes repositories in settings and uses `RepositoriesMode.FAIL_ON_PROJECT_REPOS`, omit the `repositories { mavenCentral() }` block from the build script and use the sources declared in settings per project conventions.

### 6.2. Kotlin DSL

File `settings.gradle.kts`:

~~~kotlin
rootProject.name = "war-demo"
~~~

File `build.gradle.kts`:

~~~kotlin
plugins {
    java
    war
    id("org.springframework.boot") version "3.3.5"
    id("io.spring.dependency-management") version "1.1.6"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    providedRuntime("org.springframework.boot:spring-boot-starter-tomcat")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}

springBoot {
    mainClass.set("com.example.war.WarDemoApplication")
}
~~~

Kotlin DSL and Groovy DSL are **two mutually exclusive alternatives**; do not place both in the same project. The Java sources from section 4 do not need to change. In a multi-module build, apply `war` and the Boot plugin only to the **Servlet application module to be deployed**, and do not enable WAR packaging on shared Java library modules.

### 6.3. Running Gradle

Linux/macOS:

~~~bash
./gradlew --version
./gradlew clean build
./gradlew bootWar
ls -lh build/libs/*.war
jar tf build/libs/war-demo-0.0.1-SNAPSHOT.war | grep '^WEB-INF/'
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean build
.\gradlew.bat bootWar
Get-ChildItem .\build\libs\*.war
jar tf .\build\libs\war-demo-0.0.1-SNAPSHOT.war |
    Select-String '^WEB-INF/'
~~~

The `bootWar` task creates the executable WAR. By Spring Boot Gradle plugin convention, the regular WAR task may produce a **`-plain.war`** file without a launcher like the executable WAR. Do not mistakenly run the plain WAR with `java -jar` and conclude the initializer is wrong.

## 7. Inspecting the WAR Structure

A Spring Boot executable WAR typically has a structure like:

~~~text
war-demo-0.0.1-SNAPSHOT.war
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...         (Boot launcher)
└── WEB-INF/
    ├── classes/
    │   ├── com/example/war/WarDemoApplication.class
    │   └── com/example/war/PingController.class
    ├── lib/
    │   ├── spring-webmvc-*.jar
    │   └── ...                                 (application libraries)
    └── lib-provided/
        └── tomcat-embed-*.jar                  (provided servlet container libraries)
~~~

This is an **illustrative diagram**, not the exact list of every nested JAR or the entire WAR. Use `jar tf` to see the real files.

**Three directories you must distinguish:**

| Directory | Contents | Who uses it? |
| --- | --- | --- |
| `WEB-INF/classes` | Compiled classes and resources of the application | Spring/webapp |
| `WEB-INF/lib` | Application runtime dependencies, e.g., Spring MVC | Webapp in external container or Boot launcher |
| `WEB-INF/lib-provided` | Embedded servlet container libraries marked provided | Spring Boot launcher when running executable WAR; avoids conflict with external container |

In a typical Spring Boot 3.3 executable WAR manifest:

~~~text
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: com.example.war.WarDemoApplication
~~~

Here `Main-Class` is the **Boot launcher**, while `Start-Class` is your application class. Do not change `Main-Class` to `WarDemoApplication` inside a repackaged WAR, as that can bypass nested library loading.

### Inspecting the Manifest on Linux/macOS

When `unzip` is installed:

~~~bash
unzip -p target/war-demo-0.0.1-SNAPSHOT.war META-INF/MANIFEST.MF
~~~

With Gradle, use `build/libs/war-demo-0.0.1-SNAPSHOT.war`. On a machine without `unzip`, the JDK's `jar` tool can extract the manifest into **a separate inspection directory** so you can open `META-INF/MANIFEST.MF`. Do not edit the archive manually.

## 8. Running the Executable WAR with `java -jar`

With the WAR just built by Maven `spring-boot:repackage` or Gradle `bootWar`:

~~~bash
# Maven
java -jar target/war-demo-0.0.1-SNAPSHOT.war

# Gradle (alternative command, use the exact file from your chosen build)
java -jar build/libs/war-demo-0.0.1-SNAPSHOT.war
~~~

Spring Boot starts embedded Tomcat thanks to `WEB-INF/lib-provided`, and the application registers `PingController`. Open a second terminal:

~~~bash
curl -fsS http://localhost:8080/ping
~~~

Expected response body:

~~~text
pong
~~~

If port 8080 is taken, you can run on another port in **embedded mode**:

~~~bash
java -jar target/war-demo-0.0.1-SNAPSHOT.war --server.port=8081
~~~

Then call `http://localhost:8081/ping`. The `--server.port` argument does not change the connector port of an **external Tomcat**; the external server manages its own port.

**Note:** if you only package the WAR with Maven War Plugin or standard Gradle `war`, the WAR may **be deployable but not runnable with `java -jar`**. Do not equate the existence of a `.war` file with it being an executable Spring Boot archive.

## 9. Deploying the WAR to External Apache Tomcat

### 9.1. Preparing the Environment

Example using **Tomcat 10.1.x** with Spring Boot 3.3 and Java 17:

- External Tomcat provides the Servlet API in the **`jakarta.servlet.*`** namespace.
- Do not use **Tomcat 9** (typically `javax.servlet.*`) for a standard Spring Boot 3 WAR configuration.
- The container has appropriate permissions and deployment configuration approved by operations.
- Port, hostname, and context path are determined from Tomcat configuration, not guessed from Spring Boot's `server.port`.
- The WAR has been built cleanly, checked structurally, and is not a plain WAR or stale artifact.
- Do not arbitrarily drop different versions of Spring Framework/Tomcat/Jakarta API libraries into Tomcat's global `lib` and cause classloader conflicts.

### 9.2. Deploying via the `webapps` Directory When Permitted

Linux example, **assuming** the `CATALINA_BASE` environment variable already points to a writable Tomcat instance:

~~~bash
# Already ran ./mvnw clean verify in the project directory
test -n "$CATALINA_BASE"
cp target/war-demo-0.0.1-SNAPSHOT.war \
   "$CATALINA_BASE/webapps/war-demo.war"
~~~

If using Gradle, replace the source with `build/libs/war-demo-0.0.1-SNAPSHOT.war`.

Windows PowerShell:

~~~powershell
if (-not $env:CATALINA_BASE) {
    throw "CATALINA_BASE is not set"
}
Copy-Item .\target\war-demo-0.0.1-SNAPSHOT.war "$env:CATALINA_BASE\webapps\war-demo.war"
~~~

This is an **illustrative deployment method**, not an instruction to alter an unauthorized production server. Depending on Tomcat configuration, copying the file may require `autoDeploy` enabled, a restart, or deployment via Manager/CI. **Having the WAR file in `webapps` does not prove the application started successfully**; you must read the logs and call the endpoint.

### 9.3. Checking the Context Path

When Tomcat is running on `localhost:8080` and the WAR is deployed as `war-demo.war` under default rules, the endpoint is typically:

~~~bash
curl -fsS http://localhost:8080/war-demo/ping
~~~

Output:

~~~text
pong
~~~

PowerShell:

~~~powershell
Invoke-RestMethod -Uri "http://localhost:8080/war-demo/ping"
~~~

**Explanation:** The controller still declares `@GetMapping("/ping")`. The `/war-demo` prefix is the **context root** assigned by the external servlet container, usually based on the WAR name or context configuration. If deployed as `ROOT.war`, the URL may be `/ping`. If the administrator configures a custom context path, the URL changes accordingly.

Do not change `@GetMapping("/ping")` to `@GetMapping("/war-demo/ping")` just to fix a 404, as that will accidentally double the prefix when deploying the WAR under a context root.

## 10. Separating `ServletInitializer` into Its Own Class When Needed

The shortest approach is having `WarDemoApplication extends SpringBootServletInitializer` as in section 4. However, sometimes a project prefers keeping the application class with only `main`, and placing the initializer in another file.

**This is an alternative approach; do not use it simultaneously with the extending application class from section 4.**

File `WarDemoApplication.java`:

~~~java
package com.example.war;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WarDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(WarDemoApplication.class, args);
    }
}
~~~

File `ServletInitializer.java`:

~~~java
package com.example.war;

import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

public class ServletInitializer extends SpringBootServletInitializer {
    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder builder) {
        return builder.sources(WarDemoApplication.class);
    }
}
~~~

Two files in the same package provide the two entry points. `ServletInitializer` does not need a `main` method; when the external container deploys the WAR, it initializes the application via `configure`. If the project already has another initializer, **do not unconditionally add another one**: multiple `WebApplicationInitializer` implementations or `web.xml` registering servlets/filters together can cause duplicate contexts or unexpected behavior.

### When You Need to Customize `SpringApplicationBuilder` on Both Run Paths

Settings placed only in `configure` **do not automatically run** when the JVM calls `main`. If you want consistent banner mode, default properties, or configuration sources, create a shared helper method and call it from both:

~~~java
package com.example.war;

import org.springframework.boot.Banner;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class WarDemoApplication extends SpringBootServletInitializer {
    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder builder) {
        return configureApplication(builder);
    }

    public static void main(String[] args) {
        configureApplication(new SpringApplicationBuilder()).run(args);
    }

    private static SpringApplicationBuilder configureApplication(
            SpringApplicationBuilder builder) {
        return builder.sources(WarDemoApplication.class)
                .bannerMode(Banner.Mode.OFF);
    }
}
~~~

This is an **alternative** to the class in section 4, not a second public class with the same name to paste into the same file. Do not hard-code passwords, tokens, or `profiles("production")` to force every environment into production.

## 11. Java, Jakarta Servlet, and Classloader Compatibility

### 11.1. Spring Boot 3 Moves to Jakarta

Spring Boot 3 uses Spring Framework 6 and Servlet APIs under the **`jakarta.servlet`** namespace. Tomcat 10.1 supports the corresponding Jakarta API line. Tomcat 9 belongs to the `javax.servlet` ecosystem and **should not be used for a Spring Boot 3 WAR** in standard deployments.

If an older project has:

~~~java
import javax.servlet.Filter;
~~~

that is the legacy API. When migrating to Spring Boot 3 you may need:

~~~java
import jakarta.servlet.Filter;
~~~

However, **changing a single import is not enough** if dependencies, custom servlets/filters, Spring Security, or other JPA/validation libraries still use the old Java EE namespace. You must upgrade the compatible library set and test it thoroughly.

### 11.2. Version Matrix

| Component | Example Version | Why Check? |
| --- | --- | --- |
| Java | 17 | Class file/JDK runtime must support both Spring Boot and Tomcat |
| Spring Boot | 3.3.5 | Brings in matching Spring Framework/Jakarta dependencies |
| Spring MVC | `spring-boot-starter-web` | Traditional WAR requires a servlet-based web stack |
| External Tomcat | 10.1.x | Jakarta Servlet API and container implementation |
| Tomcat starter | `provided` / `providedRuntime` | Prevents embedded Tomcat conflicts when deploying externally |
| Gradle/Maven | Wrapper version supported by Boot plugin | Must compile, test, and build the WAR properly |

A WAR can run via `java -jar` locally yet **fail on an external container** due to differences in JDK, Servlet API, or classloaders. A passing build does not substitute for testing on the exact target server version.

### 11.3. Why Not Copy Container JARs into the Application?

Servlet engine libraries are managed by the **external Tomcat**. When you mark embedded Tomcat as `provided` or `providedRuntime`, the executable WAR places it under `WEB-INF/lib-provided`; an external container does not treat that as regular webapp libraries. If you instead put `tomcat-embed-core` into `WEB-INF/lib`, Tomcat may hit duplicate classes or API conflicts.

Do not arbitrarily drop `javax.servlet-api` into a Spring Boot 3 WAR to "fix" missing servlet class errors; that is usually a symptom of an **incompatible servlet container runtime** or incompatible transitive dependency.

## 12. Testing Spring MVC and Testing WAR Deployment

### 12.1. Web MVC Test with JUnit Jupiter

Because the example POM/Gradle has `spring-boot-starter-test`, you can use a test to verify the endpoint without starting an external Tomcat. File `src/test/java/com/example/war/PingControllerTest.java`:

~~~java
package com.example.war;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(PingController.class)
class PingControllerTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void pingReturnsPong() throws Exception {
        mvc.perform(get("/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
    }
}
~~~

The test compiles/runs with JUnit Jupiter, Spring Boot Test, and Gradle `useJUnitPlatform()` or the Parent-managed Maven Surefire version.

**Limitation:** `@WebMvcTest` tests Spring MVC mapping and responses; it **does not prove** the WAR deploys to an external Tomcat. It does not check whether `SpringBootServletInitializer` is invoked by the container, whether classloaders behave properly, or whether the context root is right.

### 12.2. Verification Matrix

| Layer | Command/Check | Evidence |
| --- | --- | --- |
| Compile | Maven `compile` / Gradle `compileJava` | Initializer has valid signature and Boot 3 APIs are on classpath |
| Test | `mvnw clean verify` / `gradlew clean build` | `PingControllerTest` executed and passed |
| WAR structure | `jar tf` | `WEB-INF/classes`, `WEB-INF/lib`, `WEB-INF/lib-provided` are right |
| Manifest | `unzip -p ... META-INF/MANIFEST.MF` | Contains Boot `WarLauncher` and correct `Start-Class` |
| Embedded smoke | `java -jar ...war` + `curl /ping` | HTTP 200, response `pong` |
| External smoke | Deploy Tomcat 10.1 + `curl /war-demo/ping` | Container deploys successfully, HTTP 200, response `pong` |
| Regression | Auth/session/DB/upload/static file flows | No errors that appear only under an external container |

Passing JUnit tests and having a WAR file exist is **still not enough to declare deployment ready**. At minimum, run a WAR smoke test on a real servlet container or matching test environment.

### 12.3. Minimal CI

Linux/bash, choose **one** option:

~~~bash
# Maven
./mvnw --batch-mode --no-transfer-progress clean verify
jar tf target/war-demo-0.0.1-SNAPSHOT.war > war-entries.txt
grep -q '^WEB-INF/classes/com/example/war/WarDemoApplication.class$' war-entries.txt
grep -q '^WEB-INF/lib-provided/' war-entries.txt
~~~

~~~bash
# Gradle
./gradlew clean build
jar tf build/libs/war-demo-0.0.1-SNAPSHOT.war > war-entries.txt
grep -q '^WEB-INF/classes/com/example/war/WarDemoApplication.class$' war-entries.txt
grep -q '^WEB-INF/lib-provided/' war-entries.txt
~~~

The two snippets are alternatives and require JDK `jar` and `grep`. They verify **files inside the archive**, not an HTTP smoke test. Strict CI requires a job that runs the WAR and sends an HTTP request to the actual endpoint, or deploys to a compatible Tomcat and verifies it. Do not accidentally pick `-plain.war` or a file from a previous build.

## 13. Common Errors and How to Investigate

| Symptom | Possible Cause | Action |
| --- | --- | --- |
| Tomcat accepts WAR but Spring context does not start | Missing initializer, initializer on wrong classpath, `configure` does not load app | Check `WEB-INF/classes`, Tomcat logs, `sources(WarDemoApplication.class)` |
| Maven/Gradle reports missing `SpringBootServletInitializer` | Wrong package import, missing Boot dependency, or Boot version too old | Check compile classpath; import `org.springframework.boot.web.servlet.support` |
| `configure` reports `does not override` | Wrong parameter/return type/signature | Use `protected SpringApplicationBuilder configure(SpringApplicationBuilder builder)` |
| Produced archive is a JAR | Maven missing `<packaging>war</packaging>` or Gradle missing `war` | Check POM/plugins and the right packaging module |
| Gradle `Task 'bootWar' not found` | `war` + Boot plugins not applied in the right module | Enable `war` and Spring Boot plugins; check `gradlew tasks` |
| `java -jar file.war` reports no main manifest attribute | Running a plain WAR; Spring Boot repackage/bootWar did not run | Use the executable WAR containing `WarLauncher` and `Start-Class` |
| Nested Tomcat in `WEB-INF/lib` causes deployment errors | Servlet container dependency not marked provided | Use Maven `provided` / Gradle `providedRuntime` |
| `ClassNotFoundException: jakarta.servlet...` | External container or dependencies incompatible with Jakarta | Use Tomcat 10.1 for Boot 3 and audit APIs/transitives |
| `ClassNotFoundException: javax.servlet...` | Legacy library requiring Java EE inside a Jakarta project | Migrate dependencies and code to Jakarta-compatible versions |
| Embedded mode works but external fails | Missing initializer, classloader, or different container/JDK/config | Compare startup logs, WAR structure, Java/Tomcat versions |
| External WAR returns 404 at `/ping` | Context root `/war-demo` | Try `/war-demo/ping` or the actual context from Tomcat |
| HTTP 404 even with the context | Controller outside component scan or app failed to start | Check packages, Spring logs, and handler mappings |
| Set `server.port=8081` yet external Tomcat stays on 8080 | External container port is not managed by Boot | Configure Tomcat connector per operational procedure |
| WAR creates two ApplicationContexts or registers Filters twice | Multiple `WebApplicationInitializer`s, `web.xml`, and Java config overlapping | Keep one initializer, check mappings, remove duplicate registrations |
| CI build succeeds but production returns 500 | Missing secrets/JNDI, Servlet version, session/security, or database differences | Establish environment parity and integration/smoke tests |
| `@WebMvcTest` passes yet deployment fails | Test only checks MVC slice, does not start external container | Add WAR deployment verification on a compatible Tomcat |

When debugging, first record the **Java version, Spring Boot version, Tomcat version, artifact path, manifest, WAR structure, and deployment logs**. Do not swap multiple dependencies randomly or alter endpoint URLs without knowing whether the fault is in startup, packaging, component scanning, or context root.

## 14. Safe Deployment and Maintenance Practices

1. **Keep both startup paths consistent.** If `main` and `configure` use different configuration sources, the application may behave differently between embedded and external modes. For complex custom settings, share a single builder method.
2. **Only one clear initializer.** Do not create both a class extending `SpringBootServletInitializer` and a separate `ServletInitializer` unless you understand exactly how multiple `WebApplicationInitializer` instances interact.
3. **Do not bake secrets into the WAR.** Runtime config should be externalized via environment variables, a secret manager, Java system properties, or an organization-approved configuration mechanism.
4. **Follow the Jakarta namespace.** Spring Boot 3 is not compatible with legacy Tomcat 9 / `javax` Servlet runtimes.
5. **Do not use `server.port` to control external Tomcat.** Distinguish the external connector from the embedded server, as well as the WAR context root from Spring MVC mappings.
6. **Do not deploy the wrong artifact.** Gradle can create a plain WAR and Maven can keep an `.original` source; CI must publish the exact tested WAR.
7. **Read container logs on deploy.** Having the WAR in `webapps` does not mean Tomcat started it successfully; monitor exceptions, deployment status, and the HTTP endpoint.
8. **Pay attention to downtime/redeploy.** External containers manage undeploy/reload; background threads, JDBC drivers, schedulers, sessions, and resource cleanup must align with the lifecycle.
9. **Do not assume JAR and WAR are the same.** JAR uses `BOOT-INF`, WAR uses `WEB-INF`; the two packaging formats have different classpath structures and manifests.
10. **Always smoke-test both modes if you commit to supporting both.** Do not stop at checking `mvn package` or `gradlew bootWar`.

## 15. Hands-On Exercise with Completion Criteria

Work on an experimental branch of a Spring Boot MVC project that has Maven or Gradle Wrapper:

1. Create `WarDemoApplication.java` extending `SpringBootServletInitializer`, overriding `configure` to return the builder with `WarDemoApplication.class` added, while keeping the `main` method.
2. Create `PingController.java` with `GET /ping` returning `pong`.
3. Choose **Maven** (WAR packaging, Tomcat `provided` scope, Boot Maven Plugin) **or Gradle** (`war` plugin, `providedRuntime`, `bootWar`).
4. Run `clean verify` or `clean build`; verify that the JUnit test is discovered and executed.
5. Use `jar tf` to confirm `WEB-INF/classes`, `WEB-INF/lib`, and `WEB-INF/lib-provided`; verify `WarLauncher`/`Start-Class` in the manifest.
6. Run `java -jar` with the executable WAR; call `http://localhost:8080/ping` and verify response `pong`.
7. Deploy the **same WAR** to Tomcat 10.1, determine the actual context path, and call `http://localhost:8080/war-demo/ping` as appropriate; verify `pong`.
8. Compare the two startup paths: does external Tomcat call `main`? Who manages the port? Who sets the context root? Which class provides the Spring application sources?
9. Introduce a controlled failure on a separate branch (remove the initializer or use the wrong source), inspect the error in the container logs, and then **restore the working configuration**.
10. Document the JDK/Boot/Tomcat versions, WAR filename and checksum, test evidence, deploy command, and rollback plan.

**Done when:** you can explain and demonstrate how `SpringBootServletInitializer` connects the external Servlet container lifecycle to Spring Boot, build a properly structured WAR, and run **the same Spring MVC endpoint** in both executable WAR mode and external Tomcat.

## Official Documentation

- [Spring Boot 3.3 – Traditional Deployment](https://docs.spring.io/spring-boot/3.3/how-to/deployment/traditional-deployment.html)
- [Spring Boot 3.3 API – SpringBootServletInitializer](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/servlet/support/SpringBootServletInitializer.html)
- [Spring Boot 3.3 – Maven Plugin: Packaging](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot 3.3 – Gradle Plugin: Packaging](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot 3.3 – Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [Apache Tomcat 10.1 Documentation](https://tomcat.apache.org/tomcat-10.1-doc/)
- [Gradle – War Plugin](https://docs.gradle.org/current/userguide/war_plugin.html)
- [Maven – Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
