# Creating a WAR with Maven `war` and Spring Boot `repackage`

A Spring Boot project may need to produce a **WAR** to deploy into an external servlet container such as Apache Tomcat, instead of distributing only an executable JAR. With Maven, two distinct jobs are very easy to mistake for one:

1. **`maven-war-plugin:war`** gathers compiled code, resources, and required dependencies into a **Web Application Archive** following the `WEB-INF` structure.
2. **`spring-boot-maven-plugin:repackage`** takes the newly created WAR as input, adds the **Spring Boot Loader**, adjusts the manifest, and arranges runtime/provided dependencies to produce an **executable WAR** — capable of both running via `java -jar` and deploying to a compatible servlet container.

**Core point:** `<packaging>war</packaging>` does not automatically mean you have a WAR that can run with `java -jar`. The Maven WAR Plugin and Spring Boot Maven Plugin handle **two different steps** in the lifecycle. With the Spring Boot starter parent and standard configuration, `mvn clean package` executes them in the right order.

This lesson uses **Java 17, Spring Boot 3.3.13, Maven 3.9.x**, and a small Spring MVC application. The versions are pinned so you can follow along; when going to production, choose Java, Spring Boot, Maven plugins, and a servlet container matching versions supported in your environment. Note that Spring Boot 3.x moved to **Jakarta Servlet** (`jakarta.servlet.*`), so you cannot assume a new WAR will deploy onto every legacy Servlet server still using `javax.servlet.*`.

## 1. What Is a WAR? When Choose WAR Instead of JAR?

**WAR (Web Application Archive)** is also a ZIP-based archive like a JAR, but follows the Java servlet web application convention: application classes/resources under `WEB-INF/classes`, web library dependencies under `WEB-INF/lib`, while directly served resources can live in valid web application locations.

A Spring Boot servlet web project usually has two operational options:

- **Executable JAR:** `java -jar service.jar`; Spring Boot Loader starts the application with the packaged embedded servlet server.
- **WAR deployed to a servlet container:** copy/deploy `service.war` into a compatible Tomcat; Tomcat manages the process, port, context path, and servlet lifecycle for the application.
- **Executable WAR (Spring Boot):** remains a traditional deployable WAR **and** includes the Boot Loader, so it can also run standalone with `java -jar service.war`.

Comparison table:

| Feature | Standard WAR after `maven-war-plugin` | WAR after `spring-boot:repackage` | Spring Boot executable JAR |
| --- | --- | --- | --- |
| File extension | `.war` | `.war` | `.jar` |
| Application classes | `WEB-INF/classes` | `WEB-INF/classes` | `BOOT-INF/classes` |
| Web/runtime libraries | `WEB-INF/lib` | `WEB-INF/lib` | `BOOT-INF/lib` |
| Libraries marked `provided` | Not placed into `WEB-INF/lib` of a standard WAR | Placed by Boot in `WEB-INF/lib-provided` if needed for executable WAR | Boot repackaging has its own rules; do not infer from WAR layout |
| Boot Loader / executable manifest | Not added by the WAR Plugin | Has `WarLauncher`, `Main-Class`, and `Start-Class` | Has `JarLauncher`, `Main-Class`, and `Start-Class` |
| Runnable via `java -jar` | Not a default capability | Yes | Yes |
| Deploy to external servlet container | Purpose-built for this | Still suitable if the app and container are compatible | Not used directly as a traditional WAR |

**Do not interpret "executable WAR" as a file that runs without Java.** `java -jar` still requires a compatible JVM. In external deployment mode, the servlet container itself must satisfy the application's Servlet/Jakarta/Spring Boot requirements.

## 2. Two Maven Packaging Steps: `war:war` Then `spring-boot:repackage`

For a project with `<packaging>war</packaging>`:

```text
pom.xml + src/main/java + src/main/resources [+ src/main/webapp]
                               |
                               v
Maven lifecycle: validate -> compile -> test -> package
                               |
                               v
[1] maven-war-plugin:war
    Gathers WEB-INF/classes and compile/runtime dependencies into a plain WAR
    Does not build Boot Loader / executable manifest
                               |
                               v
    target/war-demo-1.0.0.war (original WAR)
                               |
                               v
[2] spring-boot-maven-plugin:repackage
    Reads original WAR, adds Spring Boot Loader/WarLauncher
    Adds WEB-INF/lib-provided for provided dependencies
    Sets manifest Main-Class/Start-Class
                               |
                +--------------+----------------+
                |                               |
                v                               v
 target/war-demo-1.0.0.war      target/war-demo-1.0.0.war.original
    (executable WAR)                   (WAR before repackage)
```

The `.original` output is the default behavior when `repackage` **replaces the main artifact** without a separate classifier. If the project customizes `classifier`, `attach`, or the archive name, different files may appear. Always inspect the actual files after a build.

### Why Use `mvn clean package`?

- `clean` deletes old build outputs; this helps avoid accidentally using a stale un-repackaged WAR.
- `package` walks through earlier phases and invokes plugins bound to the packaging/lifecycle.
- With `war` packaging, Maven binds the `war:war` goal to the `package` phase.
- When inheriting `spring-boot-starter-parent` and **declaring the Spring Boot Maven Plugin**, the parent supplies the `repackage` execution so it runs right after the original WAR is built in the corresponding phase.

**Do not run only `mvn spring-boot:repackage` on a clean workspace**: the `repackage` goal needs a source JAR/WAR to already exist. The plugin documentation recommends letting the lifecycle build the archive first, or running `mvn package spring-boot:repackage` when invoking the goal directly. If starter parent already binds `repackage` in `package`, prefer running `mvn clean package` once to avoid unnecessary duplicate goal execution.

### `war:war` Independent of Boot `repackage`

If you want to observe the WAR Plugin's output alone (once compiled code exists):

```bash
mvn clean compile war:war
```

That command invokes the Maven WAR Plugin to build a traditional WAR from compiled classes and dependencies. It **does not add** the Boot launcher via `repackage`. Nor does it replace `mvn test`/`mvn verify` for quality checks. After inspecting that step, run the standard flow:

```bash
mvn clean verify
```

`verify` runs through `package`, so with this lesson's standard POM, the WAR produced in `target` will be the **Boot-repackaged WAR**. Do not conclude the contents are identical just because both commands emit a `.war` file.

## 3. A WAR Deployed to a Container Does Not Start via `WarLauncher`

An important startup distinction:

**When running standalone:**

```bash
java -jar target/war-demo-1.0.0.war
```

The Java launcher reads `META-INF/MANIFEST.MF` and uses `Main-Class` to invoke `org.springframework.boot.loader.launch.WarLauncher`. Spring Boot's loader builds the classpath from `WEB-INF/classes`, `WEB-INF/lib`, **and** `WEB-INF/lib-provided`, then calls the application main class via `Start-Class`. Embedded Tomcat is brought onto the classpath at this point.

**When deploying to external Tomcat:**

```text
Running Tomcat
    |
    v
Tomcat receives WAR and executes servlet deployment lifecycle
    |
    v
Classes in WEB-INF/classes + JARs in WEB-INF/lib
    |
    v
Spring WebApplicationInitializer / SpringBootServletInitializer
    |
    v
SpringApplicationBuilder configures application context
    |
    v
Spring MVC DispatcherServlet + controller
```

Tomcat does **not** run `WarLauncher` via `java -jar` when deploying a WAR as a web application. It uses servlet discovery/initialization and the container's classloader. JARs placed in `WEB-INF/lib-provided` are not treated as standard webapp libraries for the container to load; the servlet container uses the libraries already provided at the server tier.

Because the two startup paths differ, the application class should support **both `main(String[])` and `SpringBootServletInitializer`** if you want the exact same WAR to run in both modes.

## 4. Exact Setup for Spring Boot 3.x

Before writing the POM, verify four things:

1. **Servlet app:** use `spring-boot-starter-web` (Spring MVC / servlet stack). Pure WebFlux apps running default Reactor Netty do **not** support this traditional WAR model as an equivalent option.
2. **WAR packaging:** `<packaging>war</packaging>` so Maven uses the corresponding lifecycle and Maven WAR Plugin.
3. **Provided servlet container dependency:** add a direct dependency on `spring-boot-starter-tomcat` with `<scope>provided</scope>`. This tells Maven that the external container provides Tomcat/Servlet API when deploying the WAR.
4. **Bootstrap for external container:** the main application class extends `SpringBootServletInitializer` and overrides `configure(SpringApplicationBuilder)`.

**Important compatibility:** Spring Boot 3.x is based on Jakarta EE/Servlet namespaces. For Spring Boot 3.3, Tomcat 10.1 is the typical compatible container family; **Tomcat 9 (`javax.servlet`) is not a compatible deployment target**. Do not look only at the name "Tomcat" and ignore the API and Java baseline. Beyond Servlet API compatibility, verify that the server version still receives security updates, check configuration, conflicting libraries, and organizational policy.

## 5. Complete Java 17 Example: One WAR for External Deploy and `java -jar`

This small example returns the fixed string `Hello WAR` from the `/hello` endpoint, tested with MockMvc. The Maven configuration builds an **executable WAR** instead of the default JAR.

### 5.1. Directory Structure

```text
war-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/dev/example/wardemo/
    │   │   ├── WarDemoApplication.java
    │   │   └── HelloController.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/dev/example/wardemo/
            └── HelloControllerTest.java
```

No `web.xml` file is needed for a typical Spring Boot MVC app using the Java Servlet initializer mechanism and proper plugin configuration. The Maven WAR Plugin can build the `WEB-INF` layout even when `src/main/webapp` has no special static resources. If a legacy application has JSP/`web.xml`, that is an extended case covered later.

### 5.2. Complete `pom.xml`

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
    <artifactId>war-demo</artifactId>
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

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-war-plugin</artifactId>
                <version>3.4.0</version>
                <configuration>
                    <failOnMissingWebXml>false</failOnMissingWebXml>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <mainClass>dev.example.wardemo.WarDemoApplication</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Reading the POM by responsibility:**

- `<packaging>war</packaging>` sets the project artifact type and lifecycle bindings.
- `maven-war-plugin` builds the webapp WAR under `WEB-INF`. The example pins version `3.4.0` explicitly; `failOnMissingWebXml=false` allows the project to have no `web.xml`. Starter parent already manages WAR Plugin configuration as well; declaring it explicitly makes this step visible to learners.
- `spring-boot-maven-plugin` repackages via `repackage`. When inheriting `spring-boot-starter-parent`, the goal already has an execution; the example only needs the plugin declaration and `mainClass` for it to run during `package`.
- `mainClass` specifies the **application entry point**; Spring Boot Maven Plugin manages the manifest so the executable WAR launches via `WarLauncher`, rather than putting the application class directly in `Main-Class`.
- `spring-boot-starter-web` brings in Spring MVC and defaults to the embedded Tomcat starter per Spring Boot conventions.
- Redeclaring `spring-boot-starter-tomcat` directly with `provided` scope makes Maven resolve it under that scope instead of bundling the embedded server into `WEB-INF/lib` as a normal webapp runtime dependency.
- `spring-boot-starter-test` is only for tests and does not enter the runtime WAR.

**Note:** `provided` does not mean Maven skips downloading the dependency, nor does it mean the dependency is absent from compile/test classpaths. `provided` scope excludes it from standard webapp libraries so an external container supplies it, while Spring Boot `repackage` places provided artifacts into `WEB-INF/lib-provided` so the executable WAR **still runs standalone** via `java -jar`.

### 5.3. Application Class with Both Entry Paths

Create `src/main/java/dev/example/wardemo/WarDemoApplication.java`:

```java
package dev.example.wardemo;

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
```

Explanation of the two entries:

- When running `java -jar`, Boot's `WarLauncher` reads `Start-Class` and calls `main(args)`; `SpringApplication.run(...)` creates the application context and starts embedded Tomcat.
- When an external container deploys the WAR, Spring's servlet initializer mechanism leads to `SpringBootServletInitializer.configure(...)` to build the context **without calling `main(args)`**.
- The same `@SpringBootApplication` keeps the root configuration consistent across both startup paths. If the project has specialized `SpringApplicationBuilder` configuration (profiles, banner, listeners), share that logic between `configure` and `main` to avoid unintended differences between the two run modes.

### 5.4. REST Controller

File `src/main/java/dev/example/wardemo/HelloController.java`:

```java
package dev.example.wardemo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello WAR";
    }
}
```

The class is in the same root package as the application and falls under default component scanning. No manual `DispatcherServlet` or XML servlet mapping is needed for this simple example.

### 5.5. Shared Configuration

File `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: war-demo
```

We intentionally **do not** configure `server.port` and `server.servlet.context-path` here so the difference between the two run modes is clear. When running standalone, Spring Boot's embedded Tomcat defaults to port 8080 unless overridden. When deploying to external Tomcat, **Tomcat** determines the connector port and webapp context path from the WAR filename/deployment config; do not assume both environments share the same URL.

### 5.6. Testing with MockMvc

File `src/test/java/dev/example/wardemo/HelloControllerTest.java`:

```java
package dev.example.wardemo;

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
class HelloControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void returnsHelloWar() throws Exception {
        mvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello WAR"));
    }
}
```

This test proves the application context and controller work on **Maven's test classpath**. It does not by itself prove that the **WAR after `repackage`** runs via `java -jar` or deploys cleanly to external Tomcat. That is why separate archive inspection and smoke tests appear below.

## 6. Building the WAR with Maven and Observing Which Goals Actually Run

In the directory containing `pom.xml`, with Java 17 and a compatible Maven:

```bash
mvn -version
mvn clean verify
```

If the project has Maven Wrapper, replace `mvn` with `./mvnw` on Linux/macOS or `mvnw.cmd` on Windows. `verify` runs through `package`, compiling, testing, building the WAR, and running Spring Boot `repackage` per the configuration.

In the build log, the two key plugin goals are:

```text
maven-war-plugin:...:war
spring-boot-maven-plugin:...:repackage
```

Exact version numbers and ordering of other log lines depend on the effective POM and Maven/plugin implementation. Do not check only for the substring `BUILD SUCCESS`; verify both goals and the final artifact.

Once complete, the default example produces:

```text
target/war-demo-1.0.0.war
target/war-demo-1.0.0.war.original
```

- `.war`: the executable WAR processed by Boot `repackage`.
- `.war.original`: the original WAR created by the Maven WAR Plugin before Boot repackaging, preserved by default.
- The `.original` file is still a byte-valid ZIP/WAR archive, but must not be treated as an executable WAR.
- With a custom output name, classifier, or `attach` setting, the released file may differ; rely on package metadata and actual contents.

### Do Not Invoke the `repackage` Goal at the Wrong Time

Do not run only:

```bash
mvn clean spring-boot:repackage
```

on a clean workspace expecting Boot to know how to create an input WAR itself. The `repackage` goal processes an **already-built source archive** from the `package` step; it does not replace the Maven WAR Plugin. With starter parent, the cleanest solution is:

```bash
mvn clean package
```

If a project does not bind automatically and you want to invoke the goal manually, Boot documentation recommends:

```bash
mvn package spring-boot:repackage
```

However, **do not run that command out of habit on a POM that already binds `repackage` in the `package` phase**, as it may run redundantly. Check `mvn help:effective-pom` and execution IDs first.

## 7. Contents of a Standard WAR vs. a WAR After `repackage`

Before `repackage`, the Maven WAR Plugin creates the layout for servlet deployment:

```text
war-demo-1.0.0.war.original
├── META-INF/
│   └── MANIFEST.MF
├── WEB-INF/
│   ├── classes/
│   │   ├── dev/example/wardemo/WarDemoApplication.class
│   │   ├── dev/example/wardemo/HelloController.class
│   │   └── application.yml
│   └── lib/
│       ├── spring-webmvc-*.jar
│       ├── spring-boot-*.jar
│       └── other compile/runtime libraries
└── ... web assets if any
```

This is a **plain WAR**; `maven-war-plugin` does not add Boot's `WarLauncher`. Because an external Tomcat already provides the Servlet runtime, provided dependencies do not belong in `WEB-INF/lib`.

After `repackage`:

```text
war-demo-1.0.0.war
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
│   ├── launch/WarLauncher.class
│   └── ... other Boot loader classes
└── WEB-INF/
    ├── classes/
    │   ├── dev/example/wardemo/WarDemoApplication.class
    │   ├── dev/example/wardemo/HelloController.class
    │   └── application.yml
    ├── lib/
    │   ├── spring-boot-3.3.13.jar
    │   ├── spring-webmvc-*.jar
    │   └── other runtime dependencies
    └── lib-provided/
        ├── tomcat-embed-core-*.jar
        ├── tomcat-embed-el-*.jar
        └── other provided dependencies needed for standalone mode
```

This diagram is representative, not an exhaustive list of every dependency. `tomcat-embed-websocket-*.jar` and other artifacts may appear depending on the resolved dependency graph. Check the actual build output for exact names and versions.

**Three invariants in meaning:**

1. `WEB-INF/classes` holds application code/resources in both WAR types.
2. `WEB-INF/lib` holds dependencies that the servlet container must see when deploying the WAR.
3. `WEB-INF/lib-provided` is the addition in a **Spring Boot executable WAR** used by Boot `WarLauncher` when running standalone. Standard external servlet containers do not treat it as `WEB-INF/lib`.

In particular, `WEB-INF/lib-provided` is **not** a directory required by Maven WAR Plugin for every WAR; it appears because of Boot's repackage strategy when provided dependencies exist.

## 8. Manifest and `WarLauncher`

The example's executable WAR is expected to have key attributes in `META-INF/MANIFEST.MF`:

```text
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: dev.example.wardemo.WarDemoApplication
Spring-Boot-Version: 3.3.13
```

The actual manifest may contain additional attributes. Distinguish:

- `Main-Class`: read by the Java launcher to know which **Boot Loader class** to invoke first.
- `Start-Class`: read by Spring Boot Loader to know the **application main class**. This is not a standard Java attribute replacing `Main-Class`.
- `WarLauncher`: the loader class that understands `WEB-INF/classes`, `WEB-INF/lib`, and `WEB-INF/lib-provided`.
- `SpringBootServletInitializer`: **different from** `WarLauncher`; it serves the servlet-container deployment path. When an external Tomcat deploys a WAR, Tomcat does not invoke `java -jar`, so it does not use `Main-Class` as the application's standalone entry point.

This is the clearest illustration of **"one archive, two startup mechanisms"**.

### Reading the Manifest Without Extracting the Entire WAR

Linux/macOS with `unzip`:

```bash
unzip -p target/war-demo-1.0.0.war META-INF/MANIFEST.MF
```

Or using the JDK tool in a separate working directory:

```bash
mkdir -p target/war-inspect
cd target/war-inspect
jar xf ../war-demo-1.0.0.war META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
```

After `cd` into the inspect directory, return to the project root before running `target/...` commands in later steps. Do not unpack a WAR into the source tree and commit build outputs.

### Inspecting Archive Contents

```bash
jar tf target/war-demo-1.0.0.war
jar tf target/war-demo-1.0.0.war.original
```

In the executable WAR, expect at least entries like:

```text
org/springframework/boot/loader/launch/WarLauncher.class
WEB-INF/classes/dev/example/wardemo/WarDemoApplication.class
WEB-INF/classes/dev/example/wardemo/HelloController.class
WEB-INF/lib/spring-boot-3.3.13.jar
WEB-INF/lib-provided/tomcat-embed-core-*.jar
```

Lines with `*` are **name patterns** to look for in output, not a literal entry containing `*`. Correct manifest and archive layout are necessary conditions, **not sufficient** to guarantee the application starts in every runtime environment.

### PowerShell on Windows

```powershell
jar tf target/war-demo-1.0.0.war |
    Select-String 'WarLauncher|WEB-INF/classes|WEB-INF/lib-provided'
```

The command filters entry names inside the WAR. With the sample project, you should find the `WarLauncher` class, application classes, and provided Tomcat JARs in the output.

## 9. Running the Executable WAR Standalone with `java -jar`

Once the WAR has gone through `repackage`, you do not need an external Tomcat installed to test standalone execution. With Java 17:

```bash
java -jar target/war-demo-1.0.0.war
```

The Boot loader opens the WAR and adds `WEB-INF/classes`, `WEB-INF/lib`, and `WEB-INF/lib-provided` to the required classpath; embedded Tomcat from the provided group is used in **standalone** mode.

After the logs report the server is ready, in **another terminal**:

```bash
curl -s http://localhost:8080/hello
```

Expected body:

```text
Hello WAR
```

If you want to avoid a port already used by another application:

```bash
java -jar target/war-demo-1.0.0.war --server.port=8081
```

Then in a second terminal:

```bash
curl -s http://localhost:8081/hello
```

The body is still `Hello WAR`. `--server.port=8081` is a Spring Boot runtime setting for the **embedded server** when running standalone; it does not edit the manifest/`WEB-INF/lib` or change an external Tomcat server's port.

**If `java -jar ...war.original` fails**, that is not necessarily a bug in Maven WAR Plugin: the original WAR lacks Spring Boot's `WarLauncher`/executable manifest. To run a plain WAR, deploy it to an external servlet container; to run standalone, use the repackaged archive.

## 10. Deploying the Same WAR to External Tomcat

With a Jakarta-compatible Servlet application and the right external Tomcat version, the servlet container can accept the exact same `war-demo-1.0.0.war` produced after Boot repackaging. It handles the WAR using the servlet web application layout; `WEB-INF/lib-provided` causes no conflicts because it is not treated as the webapp's `WEB-INF/lib`.

Assume external Tomcat is installed and `CATALINA_BASE` points to the **instance configuration** you are authorized to deploy to; stop or prepare Tomcat according to your operational procedure.

Linux/macOS:

```bash
cp target/war-demo-1.0.0.war "$CATALINA_BASE/webapps/war-demo.war"
```

Equivalent in PowerShell:

```powershell
Copy-Item target/war-demo-1.0.0.war "$env:CATALINA_BASE\webapps\war-demo.war"
```

When Tomcat auto-deploy is active, the application is usually mounted under **context path `/war-demo`** because the deployed archive is named `war-demo.war`. If Tomcat uses its default HTTP connector on port 8080, the test URL is:

```bash
curl -s http://localhost:8080/war-demo/hello
```

Expected body:

```text
Hello WAR
```

**Example assumptions:** Tomcat runs at `localhost:8080`, deployment succeeds, context path comes from the WAR name, and there is no reverse proxy or custom context config. In real systems, port, hostname, TLS, context path, and deploy permissions are all governed by the **external container/infrastructure**. If the WAR is named `ROOT.war`, the context path is typically `/`; if a context descriptor exists, it may differ further.

### Mechanism Differs from `java -jar`

When Tomcat deploys a WAR:

1. Tomcat unpacks/reads the WAR and creates a web application classloader and `ServletContext`.
2. Servlet startup discovery finds Spring's initializers; the application's `SpringBootServletInitializer` builds the Spring application context.
3. Spring MVC registers `DispatcherServlet`, making `/hello` reachable under Tomcat's context path.
4. Tomcat owns opening the port and managing the application/container lifecycle.

Tomcat does not read `Main-Class: ...WarLauncher` to bootstrap the app `java -jar`-style. The `main(String[])` method in the application class is still present, but is **not** the entry point invoked directly by the external container.

### Compatibility and Security

- With **Spring Boot 3.3**, use a container running on a compatible Java version and supporting the corresponding **Jakarta Servlet** API, such as the Tomcat 10.1 line; do not follow instructions meant for Tomcat 9 / `javax.servlet`.
- The servlet container must support the API/Servlet initialization version used by the application and libraries.
- Deployments must follow real-environment permissions, TLS/port configuration, filesystem write permissions, secrets, and logging rules.
- Do not expose Tomcat Manager or admin endpoints publicly just to test a WAR; configuring deployment permissions is a separate operational step.

## 11. Why Is Tomcat `provided` So Important?

`spring-boot-starter-web` transitively pulls in `spring-boot-starter-tomcat` as a runtime/compile dependency by default. When turning the project into an external WAR, an **external Tomcat container** already provides the servlet engine.

If embedded Tomcat libraries are left in `WEB-INF/lib` and deployed to Tomcat, the webapp may carry an unnecessary servlet implementation or cause classloading conflicts. Therefore Spring Boot documentation recommends:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
    <scope>provided</scope>
</dependency>
```

**What Maven `provided` scope means:**

- The dependency remains available for compilation, tests, and plugins that need to reference it.
- The Maven WAR Plugin does **not** place it as a regular runtime dependency under `WEB-INF/lib` of a standard WAR.
- When Spring Boot Maven Plugin repackages the WAR, it **places provided dependencies in `WEB-INF/lib-provided`**, enabling the standalone WAR to still run with the embedded server via `WarLauncher`.
- External Tomcat uses its own servlet container runtime and does not need the JARs in `WEB-INF/lib-provided`.

Therefore the claim "`provided` means the dependency is strictly absent from the WAR" is **false for an executable WAR after Boot repackage**: it can be present, but inside a dedicated directory rather than `WEB-INF/lib`.

### Checking How Maven Resolved the Scope

```bash
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-tomcat
mvn help:effective-pom
```

The dependency tree should reflect `spring-boot-starter-tomcat` declared directly by the project as `provided`. If another version or scope comes from a parent or transitive dependency, fix dependency management or the dependency declaration in the proper place instead of relying on whether the WAR happened to include or omit a JAR.

### If Using Jetty or Undertow

You must actively adjust web starter/dependency exclusions, choose an alternative servlet container supported by Spring Boot, and ensure the external container is compatible. Do **not** keep Tomcat as provided while arbitrarily dropping Jetty/Undertow runtimes into `WEB-INF/lib`. This article chooses Tomcat to clarify Maven `war` and `repackage`, not as a universal guide for every server.

## 12. Role of the Maven WAR Plugin for Web Resources

The Maven WAR Plugin does more than copy `.class` files. It organizes a servlet web application from sources such as:

| Source | Typical Target in WAR | Notes |
| --- | --- | --- |
| `target/classes` from compile/resources | `WEB-INF/classes` | Application classes and classpath resources |
| Compile/runtime dependencies | `WEB-INF/lib/*.jar` | Webapp libraries needed when deployed externally |
| `src/main/webapp` | Corresponding webapp root | Traditional web resources, JSP, `WEB-INF` descriptors when present |
| `src/main/webapp/WEB-INF/web.xml` | `WEB-INF/web.xml` | May exist in legacy apps; Spring Boot MVC usually does not need it |
| `src/main/resources/static` | On classpath, typically `WEB-INF/classes/static` | Spring Boot static-resource handling follows its own conventions |
| Provided-scope artifacts | Excluded from standard `WEB-INF/lib` | Boot `repackage` may place them in `WEB-INF/lib-provided` |

`war:war` by default has its goal bound to the `package` phase when `<packaging>war</packaging>`. Avoid confusing it with `war:exploded` or `war:inplace`: those are different webapp preparation forms and do not mean the Boot loader has been added.

**Creating a `web.xml` is not mandatory just to package a modern Spring MVC application.** With `SpringBootServletInitializer` and the proper servlet initializer mechanism, the container can discover the application without an XML descriptor. The sample POM sets `failOnMissingWebXml=false` so the Maven WAR Plugin does not fail when this file is absent.

### When Using JSP

JSP has packaging and container limitations, especially when choosing an executable JAR instead of a WAR. Since this lesson focuses on WARs, you can place JSPs in the appropriate webapp structure and configure the JSP engine if needed. However, **do not conclude that changing `<packaging>war</packaging>` automatically makes JSP work**: template resolvers, JSP dependencies, view prefix/suffix, embedded vs. external Tomcat, and Jakarta JSTL compatibility must all be verified separately.

### WAR Overlays and Webapp Files

The Maven WAR Plugin also supports **WAR overlays** and `webResources`/file-filtering configuration. Use them only when merging prebuilt applications or resources. If an overlay overlaps `WEB-INF` paths or alters resources, inspect the WAR Plugin output before Boot repackaging; the loader cannot fix broken resource overlay logic.

## 13. Maven Starter Parent vs. Importing Only the BOM

A common misconfiguration is importing only the Spring Boot BOM while forgetting the plugin/lifecycle setup. Distinguish:

| Component | What does it manage? |
| --- | --- |
| `spring-boot-dependencies` BOM | Dependency versions for a Boot release |
| `spring-boot-starter-parent` | Inherits dependency management plus convenient plugin management/executions |
| `maven-war-plugin` | Builds the standard web application WAR in the `package` phase |
| `spring-boot-maven-plugin` goal `repackage` | Converts the input JAR/WAR into a Spring Boot executable archive |
| `SpringBootServletInitializer` | Initializes the Spring application context via an external servlet container |

If a project uses only the BOM such as:

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

then it **does not automatically** bind `spring-boot:repackage`, create an executable manifest, or add the Boot loader. With a corporate parent, you must declare the Boot plugin **with the matching version** and execution, for example this fragment inside `build/plugins`:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.3.13</version>
    <executions>
        <execution>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

This is a **fragment for a POM using another parent**; do not paste it into the sample POM that already inherits starter parent, as doing so can duplicate configuration or mislead readers about the lifecycle. The sample `spring-boot-starter-parent` already provides the `repackage` execution.

**Plugin order:** Spring Boot repackage requires the original WAR built by the Maven WAR Plugin. In special custom builds where you configure multiple executions in the same phase, ensure WAR packaging runs before `repackage`. With standard WAR packaging + starter parent, the default lifecycle coordinates this properly.

### Do Not Override `Main-Class` from the Wrong Plugin

Boot repackage manages `Main-Class` and `Start-Class` in the executable WAR. To specify the application main class:

```xml
<configuration>
    <mainClass>dev.example.wardemo.WarDemoApplication</mainClass>
</configuration>
```

place it under **`spring-boot-maven-plugin`**—do not manually edit the manifest with `maven-war-plugin` expecting Boot to leave all fields untouched. The Boot plugin is responsible for rewriting the manifest to reflect the launcher.

## 14. Keeping Both a Standard WAR and an Executable WAR: Intentional Classifier

By default, `repackage` **replaces the main WAR** and keeps the original WAR with the `.original` suffix. An organization may prefer keeping both artifacts with an **explicit classifier** to manage publication and deployment accurately.

Spring Boot Maven Plugin configuration fragment for this scenario:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>dev.example.wardemo.WarDemoApplication</mainClass>
        <classifier>exec</classifier>
    </configuration>
</plugin>
```

With a POM using starter parent and an existing original WAR source, configuring a repackage classifier can produce/attach an executable WAR distinguished by the `exec` classifier while keeping the main artifact as the standard WAR. When outputs differ from convention, **confirm the actual filenames** in `target` and uploaded artifact metadata before modifying pipelines. Do not assume that a file without a classifier is always an executable WAR.

The choice depends on the goal:

- If **a single WAR** needs to both deploy externally and run standalone, Boot's default of repackaging the main WAR is simplest.
- If you need to **cleanly separate** the standard WAR and executable WAR for publishing, a classifier helps identify which artifact is which. Test each channel's exact artifact.
- Never publish two artifacts with the same coordinates/version and different contents to the same repository/path.
- Never accidentally push `.original` to a release channel just because a script globs `target/*`.

**Remember that a Boot-repackaged WAR can usually still be deployed externally**; separating classifiers is an artifact-governance choice, not a rule that servlet containers reject WARs containing the Boot Loader.

## 15. CI/CD Pipeline: Verifying Both the Artifact and Both Run Modes

A minimal workflow can follow this order:

```text
Pinned JDK + Maven/toolchain
           |
           v
mvn clean verify
  - compile
  - configured unit/integration tests
  - war:war
  - spring-boot:repackage
           |
           v
Inspect target/war-demo-1.0.0.war
  - manifest Main-Class = WarLauncher
  - Start-Class matches application class
  - WEB-INF/classes contains app
  - WEB-INF/lib contains runtime deps
  - WEB-INF/lib-provided contains embedded Tomcat
           |
           v
Smoke test 1: java -jar WAR + curl /hello
           |
           v
Smoke test 2: deploy to compatible Tomcat
                + curl /war-demo/hello
           |
           v
Publish SHA-256/checksum of the exact verified WAR
```

**Both smoke tests have distinct purposes:**

1. `java -jar` verifies the executable manifest, `WarLauncher`, embedded server, and `lib-provided` classpath.
2. Deploying to an external container verifies `SpringBootServletInitializer`, servlet classloading, compatibility, and external context path.

One test does not replace the other; `@SpringBootTest`/MockMvc in the POM also does not simulate the full external Tomcat lifecycle.

### Automated Gate: Checking for Launcher and Provided Tomcat

Linux/macOS with `jar` and `grep`:

```bash
set -e

WAR="target/war-demo-1.0.0.war"

jar tf "$WAR" | grep -q '^org/springframework/boot/loader/launch/WarLauncher.class$'
jar tf "$WAR" | grep -q '^WEB-INF/classes/dev/example/wardemo/WarDemoApplication.class$'
jar tf "$WAR" | grep -q '^WEB-INF/lib-provided/tomcat-embed-core-'
jar tf "$WAR" | grep -q '^WEB-INF/lib/spring-boot-'

echo "PASS: executable WAR structure looks correct"
```

Expected stdout when all checks pass:

```text
PASS: executable WAR structure looks correct
```

If any check fails, `set -e` stops the script with a non-zero exit code. This is a **structural check** gate, not proof that the entire app works properly or that an external container is compatible. Combine it with smoke tests and dependency scanning.

### Reading the WAR Manifest in CI

```bash
unzip -p target/war-demo-1.0.0.war META-INF/MANIFEST.MF
```

Look for at least:

```text
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: dev.example.wardemo.WarDemoApplication
```

The manifest may have additional entries; what matters is the correct launcher/main class and that the archive actually contains the corresponding classes and dependencies.

### Reproducibility

Pin the Spring Boot release, JDK, Maven Wrapper, and plugin versions per project policy. Generated archives can contain timestamps/metadata; `clean package` alone does not guarantee identical checksums across every machine. If reproducible builds are required, configure output timestamps and supported toolchains/plugins, then verify empirically.

## 16. Common Errors and How to Fix Them

| Symptom | Possible Cause | Check and Fix |
| --- | --- | --- |
| `java -jar ...war` reports `no main manifest attribute` | Only a plain WAR from `war:war`, Boot repackage has not run | Check manifest and plugin execution; run `mvn clean package` with Boot plugin |
| `java -jar ...war` reports missing `WarLauncher` | Archive lacks loader classes or manifest points elsewhere | `jar tf` for `...WarLauncher.class`; rebuild with Spring Boot Maven Plugin |
| WAR deploys to Tomcat but application does not start | Missing `SpringBootServletInitializer`, incompatible Servlet API, config, or bean error | Check Tomcat logs, extend initializer/`configure`, and check Jakarta compatibility |
| WAR runs with `java -jar` yet external Tomcat returns 404 | Different context path, failed deployment, or broken servlet startup | Check Tomcat logs/`webapps` WAR name/context path; try `/war-demo/hello` |
| Two conflicting Tomcat runtimes present | Embedded Tomcat is inside `WEB-INF/lib` | Declare `spring-boot-starter-tomcat` directly as `provided`, rebuild/inspect |
| `WEB-INF/lib-provided` is empty or missing Tomcat | Wrong scope or dependency excluded | `mvn dependency:tree` and `jar tf`; check repackage logs |
| `WEB-INF/lib-provided` has Tomcat yet external deploy still works | This is the intended behavior of an executable WAR | External container does not treat `lib-provided` as `WEB-INF/lib` |
| `mvn spring-boot:repackage` fails on a clean project | No input WAR/JAR exists yet | Use the `mvn package` lifecycle; `repackage` processes an existing archive |
| `mvn war:war` produces a WAR, yet `java -jar` fails | Maven WAR Plugin does not add an executable launcher/manifest | Enable Spring Boot `repackage` or deploy standard WAR to external container |
| Config has only the BOM and no executable WAR is produced | Importing BOM does not bind `repackage` | Declare Boot Maven Plugin version and valid execution |
| Tomcat 9 reports `javax/jakarta` class mismatch | Spring Boot 3.x uses Jakarta Servlet; Tomcat 9 uses `javax` | Pick a Jakarta-compatible servlet container; do not hack around with manual package rewrites |
| Application starts externally, yet some dependencies fail | Classloader/container library conflicts or wrong provided scopes | Check `WEB-INF/lib`, Tomcat logs, dependency graph, and package/class names |
| JSP does not render even though WAR builds cleanly | Missing JSP/JSTL deps, view resolver, or JSP packaging | Audit JSP config, servlet container, and Jakarta JSTL support |
| `maven-war-plugin` reports missing `web.xml` | Plugin/config disallows descriptorless Servlet 3+ webapps | Set `failOnMissingWebXml=false` or configure the Servlet model properly |
| CI deploys `.war.original` by mistake | Script selects file by glob | Select main artifact/classifier explicitly; verify manifest/`WarLauncher` before upload |
| Local uses port 8080, external Tomcat has different port/context | Two different runtime topologies | Read Tomcat configuration; external URLs usually include a WAR context path |
| Repackaged WAR breaks after manual re-ZIP | Outer archive/nested JAR semantics not preserved | Rebuild with the standard plugin; do not edit the ZIP manually |

### Concise Diagnostic Workflow

1. **Get the exact command and logs:** running `java -jar` or deploying to Tomcat? Does the error begin in the launcher or inside Spring/Tomcat?
2. **Verify the exact WAR file:** full path, version, timestamp, checksum, classifier, `.original`.
3. **Check the effective POM:** `<packaging>war</packaging>`, WAR Plugin, Spring Boot Plugin, and `repackage` execution.
4. **Check the dependency graph:** is Tomcat `provided`? Do Spring MVC/JSON libs have appropriate runtime scope?
5. **Check the layout:** `WEB-INF/classes`, `WEB-INF/lib`, `WEB-INF/lib-provided`, Boot `WarLauncher`.
6. **Check the manifest:** are Boot loader `Main-Class` and application `Start-Class` correct?
7. **Smoke-test the target path:** standalone `java -jar` **and/or** external Tomcat deployment with the proper context path.
8. **Fix source/POM and rebuild**; do not hand-patch released WARs.

## 17. Practice Scenarios and Answers

**Scenario A.** A POM only has `<packaging>war</packaging>` and `maven-war-plugin`. The team runs `mvn clean package` and gets a WAR, yet `java -jar` reports a missing main manifest attribute. Why?

*Answer:* Maven WAR Plugin builds a **deployable WAR**, not an **executable Spring Boot WAR**. You need the Spring Boot Maven Plugin with the `repackage` goal running on the generated WAR, or deploy the traditional WAR into a servlet container.

**Scenario B.** A WAR after Boot `repackage` contains `WEB-INF/lib-provided/tomcat-embed-core-...jar`. Should you delete it from the WAR before deploying to external Tomcat?

*Answer:* No. Spring Boot places provided dependencies in a separate directory so the WAR can run standalone, while an external container uses its own servlet/container libraries and does not load `lib-provided` as `WEB-INF/lib`. If the goal is one WAR that runs in both modes, keeping the Boot plugin output intact is the right approach.

**Scenario C.** An application has `main()`, the POM uses WAR packaging, yet deploying to external Tomcat creates no Spring context. What should you check?

*Answer:* Beyond compatibility, ensure the application supports the **`SpringBootServletInitializer`** path with `configure(SpringApplicationBuilder)`. An external container does not invoke `main()` through `WarLauncher`.

**Scenario D.** Running `java -jar war-demo-1.0.0.war` works at `/hello`; copying the same WAR to Tomcat as `war-demo.war` gives 404 at `/hello`. Why?

*Answer:* External Tomcat normally assigns context path `/war-demo` based on the WAR filename. With the example's default settings, try `/war-demo/hello` and inspect the deployment logs. `server.port` in embedded mode does not control external Tomcat's port.

**Scenario E.** Adding the Tomcat dependency with `compile` scope still lets the WAR build cleanly. Can you assume external deployment is fine?

*Answer:* No. Embedded servlet container libraries can get packaged into `WEB-INF/lib` and conflict with external Tomcat. Use `provided` per the Boot deployment guide and inspect the output.

**Scenario F.** A POM uses a corporate parent, imports the `spring-boot-dependencies` BOM, and has no Boot plugin execution. The WAR builds and deploys externally, yet fails to run with `java -jar`. What must be done?

*Answer:* Add the Spring Boot Maven Plugin with a valid version and `repackage` execution, ensuring it runs after WAR packaging. The BOM only manages dependency versions; it does not create the launcher or manifest.

**Scenario G.** Both `war-demo-1.0.0.war` and `war-demo-1.0.0.war.original` exist; which file should be deployed?

*Answer:* With this lesson's default setup, `.war` is the main artifact **after repackage**, usable for both external containers and standalone execution. `.war.original` is the original WAR; it can be deployed under the servlet model, but is not an executable WAR. Choose by the verified target, not an ambiguous glob.

**Scenario H.** MockMvc tests pass—does that guarantee the WAR runs on Tomcat 10.1?

*Answer:* Not yet. MockMvc verifies the application context/HTTP mappings on the test classpath; you still need a real deployment smoke test with external Tomcat and the right Jakarta Servlet runtime. Manifest and `WEB-INF` must also be checked.

**Scenario I.** Can you build an executable WAR for a pure WebFlux Netty app and deploy it identically into a servlet container?

*Answer:* The traditional Spring MVC recipe does not apply directly. Spring Boot 3.3 documentation states that WAR deployment is not supported for WebFlux applications using the default Netty model; choose a compatible servlet/web architecture if a WAR is mandatory.

**Scenario J.** You run `mvn clean package spring-boot:repackage` on a project inheriting starter parent that also declares the Boot plugin. What should you watch out for?

*Answer:* The parent usually already binds `repackage` to `package`. Calling the goal explicitly may repeat work unnecessarily; use `mvn clean package` or `verify` and inspect the effective POM/executions.

## 18. Pre-Completion Checklist for WAR Packaging

- **Deployment target:** is the application a servlet web app needing an external container or only standalone execution?
- **Runtime compatibility:** Java 17 target, Spring Boot 3.3/Jakarta API, compatible and supported external Tomcat.
- **POM:** `<packaging>war</packaging>` and appropriate `maven-war-plugin` configuration.
- **Bootstrap:** `SpringBootServletInitializer`/`configure` for external containers; `main()` for executable mode.
- **Dependencies:** `spring-boot-starter-web`, `spring-boot-starter-tomcat` as `provided`, test dependencies in `test` scope.
- **Plugin:** `spring-boot-maven-plugin` has the `repackage` goal and correct application main class, not merely importing the BOM.
- **Build:** `mvn clean verify` succeeds, and logs show Maven WAR Plugin followed by Boot `repackage` in order.
- **Archive:** `WEB-INF/classes` holds classes/resources, `WEB-INF/lib` holds runtime dependencies, and `WEB-INF/lib-provided` holds the embedded container.
- **Manifest:** `Main-Class` points to `WarLauncher`, and `Start-Class` points to the application main class.
- **Standalone smoke test:** `java -jar target/...war` and verify HTTP response rather than relying solely on unit tests.
- **External smoke test:** WAR deploys to a compatible servlet container, uses the right context path/port, and reports no servlet class conflicts.
- **Release:** record artifact identity/checksum and publish the verified WAR after QA; do not confuse with `.war.original` or another classifier.
- **Do not hand-edit WARs:** if anything is wrong, fix POM/source, rebuild, and re-verify every step; avoid re-ZIPping that breaks nested layout.

**Conclusion:** `maven-war-plugin` builds a **standard web application WAR**, while `spring-boot-maven-plugin:repackage` adds the **Spring Boot Loader and executable manifest** so a WAR can run with `java -jar`. `spring-boot-starter-tomcat` in **`provided`** scope lets you use an external container without conflicts, while `WEB-INF/lib-provided` allows Boot `WarLauncher` to load the embedded server when running standalone. For external servlet container deployment, the application needs the `SpringBootServletInitializer` initialization path—a distinct mechanism from `main()` in executable mode.

### Official Documentation

- Spring Boot 3.3.13 — Traditional Deployment / Create a Deployable War File: https://docs.spring.io/spring-boot/3.3/how-to/deployment/traditional-deployment.html
- Spring Boot 3.3.13 — Maven Plugin / Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot — Executable Archive Layout / Nested JARs: https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html
- Spring Boot — Launching Executable Archives / WarLauncher: https://docs.spring.io/spring-boot/specification/executable-jar/launching.html
- Apache Maven WAR Plugin — Overview and Goals: https://maven.apache.org/plugins/maven-war-plugin/
- Apache Maven WAR Plugin — `war:war` Goal Reference: https://maven.apache.org/plugins/maven-war-plugin/war-mojo.html
- Apache Maven — Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Apache Maven — Introduction to the Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html