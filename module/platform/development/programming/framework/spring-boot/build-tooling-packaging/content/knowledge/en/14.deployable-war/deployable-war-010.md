# Verifying the Same WAR in Standalone Execution and Servlet Container Deployment

## Goal and Approach

A Servlet-based Spring Boot application can be distributed as an **executable WAR**. What makes this file special is that the **exact same WAR** can:

1. Run directly via `java -jar app.war` thanks to the **Spring Boot launcher** and embedded servlet container packaged in the archive.
2. Be **deployed into an external servlet container** (such as a compatible Apache Tomcat), where the container receives the WAR, initializes the Spring application, and supplies the Servlet runtime.

This does **not** mean every WAR runs with `java -jar`, nor that renaming `.jar` to `.war` suffices. To prove it, you must verify **the build configuration, initializer class, ZIP layout, launch method, HTTP endpoint, URL/context path, and the exact same file bytes**.

After this lesson, you will know how to:

- Configure **Maven** or **Gradle** to build an executable WAR that runs standalone and deploys to external Tomcat.
- Explain the roles of `SpringBootServletInitializer`, `main(String[])`, `spring-boot-starter-web`, and marking `spring-boot-starter-tomcat` as **`provided`**.
- Inspect `WEB-INF/classes`, `WEB-INF/lib`, `WEB-INF/lib-provided`, and the Spring Boot launcher.
- Run **both modes from a single WAR file without rebuilding in between**, check SHA-256 digests, and compare HTTP responses.
- Distinguish **ports**, **context paths**, **classpaths**, **property resolution**, and **lifecycles** between the two modes.
- Build a CI checklist and handle issues such as HTTP 404, missing initializer, duplicate Servlet APIs, or picking a plain WAR by mistake.

**Example version context:** Spring Boot **3.3.13**, Java **17+**, compatible Maven **3.6.3+** or Gradle **8.x**, external **Apache Tomcat 10.1** (Servlet 6.0). This combination is for learning and documentation reference, **not an instruction to arbitrarily upgrade/downgrade versions** in a real project. Spring Boot 3.3 can run on servlet containers supporting Servlet 5.0+, though this lesson uses Tomcat 10.1 to minimize differences. Newer Spring Boot/Tomcat generations have their own requirements. Tomcat **9** uses the legacy `javax.servlet` namespace and is not a suitable target for running a `jakarta.servlet`-based Spring Boot 3.3 app unchanged.

## 1. What Does "The Same WAR" Mean?

In this lab, we produce **one file**:

```text
dual-mode-0.0.1-SNAPSHOT.war
```

Then:

```text
                        ONE BUILT WAR FILE
                  (single byte set, single SHA-256)
                                 |
                 +---------------+---------------+
                 |                               |
                 v                               v
         java -jar app.war             Copy WAR to external Tomcat
                 |                               |
           Boot WarLauncher              Tomcat WebApp Loader
                 |                               |
      embedded Tomcat starts        External Tomcat initializes webapp
                 |                               |
       GET http://...:18080/probe      GET http://...:8080/dual-mode/probe
                 |                               |
          READY|context=                  READY|context=/dual-mode
```

Both responses are **expected results of the source code and the example's port/context path settings**, not logs from a previously executed environment. In real deployments, verify output with `curl` or a test client rather than trusting a diagram alone.

**Requirements for "the same WAR":**

- Build **once**, and use the file in `target/` or `build/libs/` to run `java -jar`.
- Then **copy that exact verified file**, without running `package`/`bootWar` again and grabbing a different build.
- Rename **the copy** to `dual-mode.war` if you want Tomcat to assign context path `/dual-mode`; renaming the file **does not change its content bytes**.
- Compute SHA-256 of the source file and the copy: **matching digests** prove the file bytes stayed identical across the copy.
- Keep runtime settings intentional; identical WAR bytes **do not mean** both environments share the same hostname, port, context path, profiles, environment variables, or Tomcat version.

For rigorous comparison, record the Java version, WAR file hash, app version, and external Tomcat details together. Never declare two environments "identical" merely because both returned HTTP 200.

## 2. Two Startup Paths, Two Sets of Responsibilities

### 2.1 Running Standalone with the Spring Boot Launcher

When invoking:

```bash
java -jar dual-mode-0.0.1-SNAPSHOT.war --server.port=18080
```

The JVM reads `META-INF/MANIFEST.MF` to find `Main-Class`, typically `org.springframework.boot.loader.launch.WarLauncher` in Spring Boot 3.3. The launcher loads the application and nested libraries. Boot's `Start-Class` points to `DualModeApplication` containing `main(String[])`.

`SpringApplication.run(...)` creates the `ApplicationContext` and the embedded servlet container—here, Tomcat. Tomcat libraries inside `WEB-INF/lib-provided` of the executable WAR still serve **embedded** mode via the Boot launcher. The HTTP port responds to `server.port`, set to **18080** in the example to avoid colliding with external Tomcat on port 8080.

When running via `java -jar`, no separately installed Tomcat is required if the archive carries the needed dependencies, JDK, and matching environment. Still, a **JDK must be present** or provided by the image/runtime.

### 2.2 Deploying to an External Servlet Container

When an external Tomcat deploys a WAR:

1. Tomcat creates a **`ServletContext`** for the application at its context path.
2. The container treats `WEB-INF/classes` and valid libraries in `WEB-INF/lib` as the webapp classpath.
3. Spring Framework discovers `WebApplicationInitializer`; `SpringBootServletInitializer` acts as the bridge to build the Spring context inside the external Servlet container.
4. Tomcat uses **its own** connector and port; the app does not run a second embedded Tomcat.
5. Libraries inside `WEB-INF/lib-provided` are **solely for the embedded launcher**, not standard libraries loaded by external Tomcat from `WEB-INF/lib`.

**Point-by-point contrast:**

| Component | `java -jar app.war` | Deploy `app.war` to external Tomcat |
| --- | --- | --- |
| Who launches? | JVM → Boot `WarLauncher` → `main` | External Tomcat → Servlet initialization → `SpringBootServletInitializer` |
| Servlet container | Embedded Tomcat inside WAR runtime | Separately installed/managed Tomcat |
| HTTP port | `server.port`, e.g., 18080 | Tomcat connector (e.g., 8080); `server.port` in app does not configure that connector |
| Default context path in lesson | Empty string `""` | From deployed WAR name, e.g., `/dual-mode` |
| App classes | `WEB-INF/classes` loaded by Boot loader | `WEB-INF/classes` loaded by webapp classloader |
| Application libraries | `WEB-INF/lib` | `WEB-INF/lib` |
| Provided embedded server libraries | `WEB-INF/lib-provided` usable by Boot launcher | Excluded from standard webapp libraries |
| Entry point | `main(String[])` | `configure(SpringApplicationBuilder)` |
| Start/stop lifecycle | Managed by JVM process | Managed by Servlet container deploy/redeploy/undeploy |
| Multiple webapps | One independent Boot app JVM | One Tomcat can host multiple WARs with isolated contexts/classloaders |

Do not write two diverging business-logic configurations just to "make both modes work." Keep one Spring application; if complex `SpringApplicationBuilder` customization is needed, extract it into a method invoked from **both `main` and `configure`** instead of modifying only one branch.

## 3. Building a Spring Boot Servlet App for Both Modes

The example uses this structure:

```text
dual-mode/
├── pom.xml                 # Choose Maven
│   or build.gradle         # Choose Gradle Groovy DSL
├── settings.gradle         # Only if choosing Gradle
├── mvnw / mvnw.cmd         # Maven Wrapper, when project has Maven
├── gradlew / gradlew.bat   # Gradle Wrapper, when project has Gradle
└── src/
    ├── main/
    │   ├── java/com/example/dualmode/
    │   │   ├── DualModeApplication.java
    │   │   └── ProbeController.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/dualmode/ProbeIntegrationTest.java
```

A real project needs only **one build system**; the layout lists both options rather than requiring Maven and Gradle side by side.

### 3.1 Application Class Serving as Servlet Initializer

File `src/main/java/com/example/dualmode/DualModeApplication.java`:

```java
package com.example.dualmode;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class DualModeApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder builder) {
        return builder.sources(DualModeApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(DualModeApplication.class, args);
    }
}
```

This is a **complete Java class within a Spring Boot project having the right dependencies** and Java 17+; **it will not compile with a bare `javac` command** because Spring Boot classes must be on the classpath. The Java package matches the file path.

- `@SpringBootApplication` marks the root configuration and component scanning in package `com.example.dualmode`.
- `main` serves executable WAR `java -jar` or dev runs via `spring-boot:run`/`bootRun`.
- `SpringBootServletInitializer` and `configure(...)` run when an external servlet container initializes the app from the WAR. `builder.sources(...)` specifies the root configuration class.
- Traditional `web.xml` is unnecessary for this simple Spring Boot MVC app; Spring Framework Servlet initialization handles required registrations.
- If you omit `extends SpringBootServletInitializer` or lack a valid Servlet bootstrap path, `java -jar` may still succeed while external container deployment yields only 404s or fails to build an `ApplicationContext`.

### 3.2 Controller Proving the Active Context Path

File `src/main/java/com/example/dualmode/ProbeController.java`:

```java
package com.example.dualmode;

import jakarta.servlet.ServletContext;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProbeController {

    private final ServletContext servletContext;

    public ProbeController(ServletContext servletContext) {
        this.servletContext = servletContext;
    }

    @GetMapping(value = "/probe", produces = MediaType.TEXT_PLAIN_VALUE)
    public String probe() {
        return "READY|context=" + servletContext.getContextPath();
    }
}
```

This class returns a fixed prefix plus the **context path actually assigned to the application by the Servlet container**. `ServletContext#getContextPath()` lets us **measure** the difference between both modes without inventing artificial `mode=standalone` or `mode=external` flags.

In this exact example:

- Embedded Tomcat starts at the root context (no `server.servlet.context-path` set) → response body `READY|context=`.
- External Tomcat receives the WAR copy named `dual-mode.war` and deploys it at `/dual-mode` assuming no context descriptor/custom mapping overrides it → response body `READY|context=/dual-mode`.

Do not infer from differing responses that the application bytes changed. Here the **exact same controller class** runs inside two different `ServletContext` instances.

### 3.3 Application Config Leaving External Container Ports Alone

File `src/main/resources/application.properties`:

```properties
spring.application.name=dual-mode
```

We intentionally **omit** `server.port` and `server.servlet.context-path` from the shared file. During standalone tests, pass the port on the command line; externally, let Tomcat configure port and context. Keeping the shared file minimal makes it easy to separate infrastructure from application logic.

If you need the same profile in both environments, configure both intentionally—for example `--spring.profiles.active=qa` on `java -jar` and `SPRING_PROFILES_ACTIVE=qa` or matching Tomcat configuration externally. **Matching profiles do not guarantee matching environments**: environment variables, secrets, Java versions, Tomcat versions, files, and timezones can still differ.

### 3.4 Testing the Application with an Embedded Server

File `src/test/java/com/example/dualmode/ProbeIntegrationTest.java`:

```java
package com.example.dualmode;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ProbeIntegrationTest {

    @Autowired
    private TestRestTemplate rest;

    @Test
    void returnsRootContextInEmbeddedMode() {
        String body = rest.getForObject("/probe", String.class);
        assertThat(body).isEqualTo("READY|context=");
    }
}
```

The test uses an embedded web environment **opening a random port**, avoiding port 8080 collisions. It confirms the controller, `ServletContext`, and Spring context work in embedded mode; **it does not prove the WAR deploys to external Tomcat**. External deployment still requires separate verification after building the WAR.

This test needs `spring-boot-starter-test` and the servlet runtime on the test classpath. With Gradle, `providedRuntime` keeps server libraries on the proper runtime/test classpaths; `compileOnly` is not equivalent.

## 4. Maven: Configuring Both Executable and Deployable WAR

### 4.1 POM Suitable for the Sample Application

File `pom.xml`:

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

    <groupId>com.example</groupId>
    <artifactId>dual-mode</artifactId>
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
```

This is a **complete POM** for building the sample's two classes and test, given a prepared Maven Wrapper or compatible Maven. You also need the `src/...` code from section 3 and network/Maven repository access to fetch dependencies. Do not assume a project has the Wrapper unless `mvnw`/`mvnw.cmd` have been created; if missing, use an installed Maven or generate a verified Wrapper.

**Meaning:**

1. `<packaging>war</packaging>` requests Maven WAR packaging.
2. `spring-boot-starter-web` provides Spring MVC and application libraries used in both modes.
3. `spring-boot-starter-tomcat` with `<scope>provided</scope>` signifies that the Servlet container provides the server runtime on external deployment.
4. `spring-boot-starter-parent` configures the `spring-boot-maven-plugin` `repackage` goal when the plugin is declared. If you only **import the BOM** without the parent, you must configure the `repackage` execution explicitly.
5. Spring Boot Maven `repackage` creates the **executable WAR** and places provided dependencies into `WEB-INF/lib-provided`. Consequently embedded Tomcat remains usable during `java -jar`.
6. `spring-boot-starter-test` is for testing only and is not needed in the executable WAR runtime.

Maven `provided` has two layers of meaning to keep separate: Maven core omits it from the **ordinary runtime classpath**, while Spring Boot `repackage` still **packages provided dependencies inside the executable WAR under `WEB-INF/lib-provided`**. That is intentional behavior, not a flaw to "fix" by stripping Tomcat from every corner of the WAR.

### 4.2 Building with Maven

```bash
# In project directory with pom.xml and mvnw:
./mvnw clean verify

# Can use package if full verify-phase checks are not needed:
./mvnw clean package

# View Tomcat dependency and its scope:
./mvnw dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-tomcat

# View POM model after parent/plugin config inheritance:
./mvnw help:effective-pom -Doutput=effective-pom.xml
```

**Note for an accurate "same WAR" experiment:** run **a single final build** for both execution paths; the commands above show build/inspection options, not an instruction to run `clean verify` and then `clean package` and compare two files. Run tests first, build once, record the output file's SHA-256, and **do not rebuild until both modes have been verified**.

Expected files with the POM configuration above:

```text
target/dual-mode-0.0.1-SNAPSHOT.war              # executable Boot WAR
target/dual-mode-0.0.1-SNAPSHOT.war.original     # pre-repackage WAR (may exist)
```

`.war.original` is the plain WAR backed up when Boot `repackage` **replaces the main artifact**, not the primary WAR to run via `java -jar`. If the plugin has a custom classifier, output files differ and `.original` may not appear. **Always inspect the actual files** rather than relying solely on filename patterns.

## 5. Gradle: `war` + Spring Boot `bootWar` + `providedRuntime`

### 5.1 Complete Groovy DSL Configuration

`settings.gradle`:

```groovy
rootProject.name = 'dual-mode'
```

`build.gradle`:

```groovy
plugins {
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a **sufficient Gradle configuration for the lesson's Java/Spring Boot project** (paired with section 3 code), given a compatible Gradle Wrapper and JDK 17. The `war` Gradle plugin applies the Java plugin implicitly. Seeing `war`, the Spring Boot plugin adds the `bootWar` task.

Why use `providedRuntime` instead of `compileOnly` for Tomcat?

- Gradle War plugin's `providedRuntime` includes the dependency in **development/test runtimes**, while **excluding it from `WEB-INF/lib` of a plain WAR** intended for an external container.
- Spring Boot `bootWar` places provided dependencies into `WEB-INF/lib-provided`. When launched by Boot via `java -jar`, embedded Tomcat is ready.
- `compileOnly` serves main compilation only; it is absent from test runtime and does not support both WAR execution modes. Using `compileOnly` instead of `providedRuntime` can cause random-port tests and executable WAR runs to fail for lack of a server.

**Transitivity:** Gradle War plugin's `providedRuntime`/`providedCompile` can affect transitive dependencies. If a library is marked provided along one path while also pulled in via `implementation`, inspect the resolved graph and WAR contents rather than assuming it is guaranteed to live in `WEB-INF/lib`.

### 5.2 If Using Kotlin DSL

This is a **`build.gradle.kts` snippet** highlighting the key parts, not the complete file:

```kotlin
plugins {
    war
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    providedRuntime("org.springframework.boot:spring-boot-starter-tomcat")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}
```

In Kotlin DSL, also add `group`, `version`, toolchain, repositories, and `tasks.test` appropriately. Do not mix Groovy's `providedRuntime '...'` syntax into `build.gradle.kts`.

### 5.3 Gradle Build Commands

```bash
./gradlew clean test bootWar

# List tasks if needed:
./gradlew tasks --all

# Inspect Tomcat module:
./gradlew dependencyInsight --dependency spring-boot-starter-tomcat \
  --configuration runtimeClasspath
```

Default output paths per the example name/version:

```text
build/libs/dual-mode-0.0.1-SNAPSHOT.war         # executable Boot WAR
build/libs/dual-mode-0.0.1-SNAPSHOT-plain.war   # plain WAR if war task also ran
```

**Distinction:** Gradle creates `bootWar` and `war` via two separate tasks; Spring Boot uses the `plain` classifier by convention for the regular WAR so the two tasks do not overwrite one filename. Running only `bootWar` may **not produce** `-plain.war`. In this lesson's dual-deploy workflow, use the **executable WAR built by `bootWar`**, not an arbitrary file matching `*.war`.

## 6. Executable WAR Layout to Inspect Before Running

A Spring Boot executable WAR follows this standard layout:

```text
dual-mode-0.0.1-SNAPSHOT.war
├── META-INF/
│   └── MANIFEST.MF
├── WEB-INF/
│   ├── classes/
│   │   ├── com/example/dualmode/DualModeApplication.class
│   │   ├── com/example/dualmode/ProbeController.class
│   │   └── application.properties
│   ├── lib/
│   │   ├── spring-webmvc-...jar
│   │   ├── spring-context-...jar
│   │   └── ... application libraries ...
│   └── lib-provided/
│       ├── tomcat-embed-core-...jar
│       └── ... servlet runtime marked provided ...
└── org/springframework/boot/loader/
    └── ... WarLauncher ...
```

This is an **illustrative tree**; exact dependency names and manifest details vary by version. Do not treat `...` lines as literal archive entries.

| Part | During `java -jar` | During external Tomcat deploy |
| --- | --- | --- |
| `WEB-INF/classes` | Application classes/resources | Webapp classes/resources |
| `WEB-INF/lib` | Application dependency JARs | Application dependency JARs on webapp classpath |
| `WEB-INF/lib-provided` | Lets Boot launcher use embedded servlet dependencies | Excluded from standard `WEB-INF/lib` classpath; avoids clashing with external container |
| `org/springframework/boot/loader` | Boot loader loads and launches app | Not external Tomcat's Servlet application initializer |
| `META-INF/MANIFEST.MF` | JVM uses `Main-Class` | Tomcat does not start the webapp via `java -jar` |
| `SpringBootServletInitializer` class | Present, though `main` path is called | Used by Servlet initialization |

Do not confuse `BOOT-INF/*` of an executable JAR with `WEB-INF/*` of a WAR. Checking a WAR for `BOOT-INF/lib` will report missing entries even on a completely valid archive.

### 6.1 Verifying with `jar tf`

Maven:

```bash
WAR="target/dual-mode-0.0.1-SNAPSHOT.war"
jar tf "$WAR"
```

Gradle:

```bash
WAR="build/libs/dual-mode-0.0.1-SNAPSHOT.war"
jar tf "$WAR"
```

Choose **one** `WAR=...` line matching your build tool. Then inspect the relevant entries:

```bash
jar tf "$WAR" | grep -E \
  '^(WEB-INF/classes/|WEB-INF/lib/|WEB-INF/lib-provided/|org/springframework/boot/loader/)'
```

A valid executable WAR per this example must have classes under `WEB-INF/classes` and Tomcat dependencies under `WEB-INF/lib-provided`. If Tomcat appears only inside `WEB-INF/lib`, check `provided`/`providedRuntime` scope, transitivity, and which task produced the artifact.

### 6.2 Manifest: Difference Between `Main-Class` and `Start-Class`

Using `unzip` on macOS/Linux (if installed):

```bash
unzip -p "$WAR" META-INF/MANIFEST.MF
```

For the sample Spring Boot 3.3 executable WAR, **expect** lines like:

```text
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: com.example.dualmode.DualModeApplication
```

`Main-Class` is for the JVM/launcher; `Start-Class` points to the application. Never pass `Start-Class` directly as the `java -jar` entry point. Across different plugin/loader versions, the `Main-Class` name can vary; always read the actual manifest.

`Main-Class` alone does not prove the WAR runs: it still needs the right runtime dependencies, classes/application config, a free port, and a compatible JDK. Likewise, a WAR with a valid web structure but no Boot launcher can deploy to an external container, yet is **not an executable WAR** meeting the dual-mode requirement.

## 7. Verification Procedure A – Running Standalone with `java -jar`

Goal of Step A: prove the WAR file **starts embedded Tomcat itself** and the endpoint returns the expected body before handing that exact file to external Tomcat.

### 7.1 Build Exactly Once and Freeze the Artifact

Suppose you choose Maven:

```bash
./mvnw clean verify
WAR="target/dual-mode-0.0.1-SNAPSHOT.war"
test -f "$WAR"
jar tf "$WAR"
```

If you choose Gradle:

```bash
./gradlew clean test bootWar
WAR="build/libs/dual-mode-0.0.1-SNAPSHOT.war"
test -f "$WAR"
jar tf "$WAR"
```

**These two blocks are alternatives**; do not run both Maven and Gradle to build "one file." Here `test -f` is the shell builtin checking file existence, not Gradle/Maven `test`. Adjust the filename if your project sets a custom `exec`/`boot` classifier, `archiveFileName`, or `finalName`.

Record the initial hash:

```bash
sha256sum "$WAR"
```

On macOS without `sha256sum`, use `shasum -a 256 "$WAR"`. **Do not modify or rebuild the file** after recording the hash. If CI runs on Windows, section 9 gives equivalent PowerShell commands.

### 7.2 Starting the Executable WAR on Port 18080

In **terminal 1**:

```bash
java -jar "$WAR" --server.port=18080
```

This command runs in the foreground and holds the terminal; banner and startup logs depend on the environment. If `Address already in use` occurs, pick another free port and update the test URL. If the Java version is incompatible, the app may abort before binding the port.

Once logs or a port check confirm the app is ready, open **terminal 2**:

```bash
curl --fail --silent --show-error http://localhost:18080/probe
```

Expected response body:

```text
READY|context=
```

Explanation:

- `/probe` is the `@GetMapping` in `ProbeController`.
- `server.servlet.context-path` is unset, so `ServletContext#getContextPath()` returns an empty string.
- `--server.port=18080` is an argument read by Spring Boot when starting the **embedded** server.
- The exact body is a single ASCII line with no trailing newline added by the controller; how `curl` displays the prompt/newline depends on the terminal. **This is not the full stdout of `java -jar`**.
- Running `ProbeIntegrationTest` on a random port proves similar embedded logic, yet does not replace executing the final WAR file.

Once verified, press **Ctrl+C** in terminal 1 to stop the embedded application. You can run it concurrently with external Tomcat when using **two different ports**, though running sequentially in this lesson makes log collection and fault isolation easier.

### 7.3 Recording Standalone Evidence

Save details such as:

```text
WAR path: target/dual-mode-0.0.1-SNAPSHOT.war
WAR SHA-256: (actual string printed by sha256sum)
Launch command: java -jar ... --server.port=18080
HTTP URL: http://localhost:18080/probe
HTTP status: 200 if successful
HTTP body: READY|context=
Server lifecycle: Started, then stopped after test
```

The placeholder for `SHA-256` instructs learners to record the **actual value**, not a dummy digest. Never copy a hash from elsewhere and claim it is your machine's archive digest.

## 8. Verification Procedure B – Deploying **That Exact WAR** to External Tomcat

Step B uses **a copy of that same WAR**, without re-running `package` or `bootWar`. The example target is a pre-installed **Apache Tomcat 10.1**. You need write permission to the deploy directory and permission to start the lab Tomcat instance; never touch production Tomcat for a lab exercise.

### 8.1 Preparing the Right External Tomcat Version

- Tomcat 10.1 supports Jakarta Servlet 6.0, matching Spring Boot 3.3 applications using `jakarta.servlet`.
- Tomcat 9.x relies on `javax.servlet`; attempting to deploy a Spring Boot 3.3 WAR directly onto it typically triggers API/initialization errors. Do not try to fix this by randomly mixing `javax.servlet-api` and `jakarta.servlet-api`.
- Run external Tomcat on a **JDK compatible** with the application bytecode—here Java 17+.
- External Tomcat has an HTTP connector port, typically 8080 by default. Check that port 8080 is free; if not, adjust the **lab instance's** Tomcat `conf/server.xml` rather than editing `server.port` in the application file.
- Stop any prior process or older deployment sharing the same context path so Tomcat does not serve a stale unpacked/cached WAR.
- Set `CATALINA_HOME` and, if using a separate instance, `CATALINA_BASE` to the right Tomcat. Do not mix libraries across different Tomcat versions.

### 8.2 Copying the Archive Without Rebuilding

**Bash/macOS/Linux** example, assuming `CATALINA_HOME` points to the Tomcat 10.1 installation and `CATALINA_BASE` points to the lab instance (or the same path as `CATALINA_HOME`). After step 7, `$WAR` still refers to the original file:

```bash
# CATALINA_HOME and CATALINA_BASE are pre-configured.
test -f "$WAR"
test -d "$CATALINA_BASE/webapps"

# Use filename dual-mode.war so Tomcat assigns context path /dual-mode.
cp "$WAR" "$CATALINA_BASE/webapps/dual-mode.war"

# Same bytes => both SHA-256 hashes must match.
sha256sum "$WAR" "$CATALINA_BASE/webapps/dual-mode.war"
```

If the two digests **do not match**, halt the experiment: the wrong artifact may have been selected, the copy was altered, or a path points elsewhere. Never claim "same WAR" before resolving the mismatch. Watch for symlinks, auto-updaters, or non-byte-preserving copy pipelines as well.

The copy is named `dual-mode.war` to receive context path `/dual-mode` under default auto-deploy rules. **Renaming does not alter the ZIP contents**, yet Tomcat can still assign another context path if `context.xml`, host config, a custom context descriptor, or `ROOT.war` is in play.

### 8.3 Running External Tomcat

In **terminal 3** (after stopping the embedded app from Part A to avoid interference):

```bash
"$CATALINA_HOME/bin/catalina.sh" run
```

This runs Tomcat in the foreground and prints logs to the terminal (command path may vary across packages/distributions). If Tomcat runs as a service or inside a container, use that environment's valid start method; **never run two Tomcat instances sharing the same `CATALINA_BASE`**.

Watch Tomcat logs until webapp deployment finishes; if Spring initialization fails, check the stack trace (do not stop at reading "Server startup"). Tomcat itself can finish starting up even when **the WAR application failed to deploy**.

In another terminal:

```bash
curl --fail --silent --show-error http://localhost:8080/dual-mode/probe
```

With Tomcat's connector on port **8080**, the WAR copy named `dual-mode.war`, and no context overrides, the expected response body is:

```text
READY|context=/dual-mode
```

If Tomcat uses another port, replace `8080`. If the WAR is deployed at root (e.g., `ROOT.war`), the URL may be `/probe` and the context path empty. Avoid misinterpreting a **404 at `/probe`** in external Tomcat as "the app is broken" before trying `/dual-mode/probe`.

### 8.4 Confirming Same Artifact, Avoiding Stale Deployments

On the same host/container filesystem (before/after deployment while original and copy remain intact):

```bash
sha256sum "$WAR" "$CATALINA_BASE/webapps/dual-mode.war"
```

When digests match, both modes are **pointing at the exact same archive bytes**. To be extra certain Tomcat **loaded the newly copied version**, verify deployment timestamps/logs, context path, and clear stale exploded/cached folders in the lab environment if signs of stale deployment appear. Never blindly delete Tomcat directories serving other apps.

Here is the distinction between **artifact identity** and **runtime identity**:

- Artifact identity: SHA-256, class contents, and WAR dependencies.
- Runtime identity: Java/Tomcat versions, ports, JVM flags, profiles, environment, secrets, databases, native libraries, networking, classloaders, and app server config.

The same WAR can succeed in both modes yet produce different configuration values, performance, or logs. This lesson proves **the same WAR works in both**, not that every runtime behavior across both environments is strictly identical.

### 8.5 Do Not Substitute `java -jar` Results for an External Deploy Test

A WAR can run directly yet return 404 or fail startup in external Tomcat due to:

- Missing `SpringBootServletInitializer`.
- External Servlet container having the wrong Jakarta Servlet or JDK version.
- Wrong context path or host mapping.
- Duplicate Servlet API or Tomcat JARs inside `WEB-INF/lib`.
- Custom listener/filter or application init incompatible with the external lifecycle.
- Different external Spring profile, config, or secrets.
- Right WAR filename, yet Tomcat deployed an older copy or a different context.

Conversely, a plain WAR can deploy to Tomcat yet fail `java -jar` because it lacks the Spring Boot launcher and `lib-provided`. To claim "dual-mode," you must **test both**.

## 9. Windows PowerShell: Testing Each Mode and Verifying Hashes

If you use Windows, you need Java 17+, Maven/Gradle Wrapper, and Tomcat 10.1 for the lab. The commands below assume you already know the **exact WAR path**; choose one build system.

### 9.1 Build and Run Standalone

Maven:

```powershell
.\mvnw.cmd clean verify
$war = "target\dual-mode-0.0.1-SNAPSHOT.war"
Get-FileHash -Algorithm SHA256 -LiteralPath $war
java -jar $war --server.port=18080
```

Gradle (an alternative to Maven; do not run both):

```powershell
.\gradlew.bat clean test bootWar
$war = "build\libs\dual-mode-0.0.1-SNAPSHOT.war"
Get-FileHash -Algorithm SHA256 -LiteralPath $war
java -jar $war --server.port=18080
```

Once the app is ready, open **another PowerShell**:

```powershell
(Invoke-WebRequest -Uri "http://localhost:18080/probe").Content
```

Expected output in the example is `READY|context=`; `Invoke-WebRequest` returns a response object if `.Content` is omitted, so read `Content` explicitly. Stop the standalone app before deploying if testing sequentially.

### 9.2 Copy to External Tomcat, Compare Hashes, and Call the New URL

Assuming `$env:CATALINA_BASE` and `$env:CATALINA_HOME` point to your lab Tomcat:

```powershell
$target = Join-Path $env:CATALINA_BASE "webapps\dual-mode.war"

Copy-Item -LiteralPath $war -Destination $target

Get-FileHash -Algorithm SHA256 -LiteralPath $war
Get-FileHash -Algorithm SHA256 -LiteralPath $target

& (Join-Path $env:CATALINA_HOME "bin\catalina.bat") run
```

In another terminal, after deployment finishes:

```powershell
(Invoke-WebRequest -Uri "http://localhost:8080/dual-mode/probe").Content
```

Expected output under default deployment: `READY|context=/dual-mode`. If `CATALINA_HOME` is unset or Tomcat runs as a Windows service, use the authorized service start method; never guess Tomcat installation paths.

**Operational caution:** never run `Copy-Item -Force` onto a WAR managed by a live production process just to test; use a dedicated lab instance and deployment window. On a running Tomcat process, overwriting the file directly can trigger unintended redeployment.

## 10. Automated Testing: Unit/Integration Layers vs. WAR Smoke Tests

### 10.1 Test Layers to Keep Distinct

| Check Type | What It Proves | What It Does NOT Prove |
| --- | --- | --- |
| Java compile | `DualModeApplication`/controller compiles with dependencies | WAR packages full runtime |
| `@SpringBootTest` `RANDOM_PORT` | Embedded Spring/Tomcat starts and HTTP logic works | Same executable WAR deploys externally |
| `mvn package` / Gradle `bootWar` | Archive built without error | Archive runs standalone or deploys externally |
| `jar tf`/manifest/layout | File has classes and libs in expected folders | No runtime config, port, or profile errors |
| `java -jar` + `curl` | Executable WAR starts and endpoint succeeds in embedded mode | External servlet container can also start it |
| Tomcat deploy + `curl` | External container bootstraps app and endpoint succeeds | Same WAR bytes unless hashes are compared |
| Matching SHA-256 on both files | Source and copy archive bytes are identical when checked | Both runtime environments/configs match |

**A complete test for this lesson:** HTTP tests in both modes + matching WAR digest. Production environments also require security, integration, observability, and reliability tests per system requirements.

### 10.2 Bash Gate Checking the Executable WAR Before Deploy

Here is a **complete Bash script** checking the WAR layout for the **Spring Boot 3.3 + `provided` Tomcat** example. It does not deploy to Tomcat automatically or run HTTP checks, preventing the script from touching external servers without a lab environment.

```bash
#!/usr/bin/env bash
set -euo pipefail

artifact="target/dual-mode-0.0.1-SNAPSHOT.war"
if [[ ! -f "$artifact" ]]; then
    echo "FAIL: WAR artifact missing"
    exit 1
fi

entries="$(jar tf "$artifact")"

if ! grep -Fxq 'WEB-INF/classes/com/example/dualmode/DualModeApplication.class' <<< "$entries"; then
    echo "FAIL: application class missing"
    exit 1
fi

if ! grep -Fxq 'WEB-INF/classes/com/example/dualmode/ProbeController.class' <<< "$entries"; then
    echo "FAIL: controller class missing"
    exit 1
fi

if ! grep -Eq '^WEB-INF/lib-provided/tomcat-embed-core-[^/]+[.]jar$' <<< "$entries"; then
    echo "FAIL: embedded Tomcat missing from lib-provided"
    exit 1
fi

if grep -Eq '^WEB-INF/lib/tomcat-embed-core-[^/]+[.]jar$' <<< "$entries"; then
    echo "FAIL: embedded Tomcat wrongly included in WEB-INF/lib"
    exit 1
fi

if ! grep -Fq 'org/springframework/boot/loader/launch/WarLauncher.class' <<< "$entries"; then
    echo "FAIL: Spring Boot WarLauncher missing"
    exit 1
fi

echo "PASS: executable WAR layout verified"
```

Change `artifact=...` to `build/libs/...war` if using Gradle. For an archive **matching the example configuration**, the script prints:

```text
PASS: executable WAR layout verified
```

This is the **conditional** stdout when every assertion passes, not output from a real project run. It does not check manifest/`Start-Class`, HTTP, or SHA-256, and does not fit projects intentionally using a servlet runtime other than Tomcat. When using Jetty/Undertow or a different Boot loader layout, update the rules to match your **policy**.

### 10.3 A Repeatable CI Scenario

A sound workflow with a prepared lab Tomcat:

1. Check out source and use the pinned Wrapper.
2. Run unit/integration tests (including `ProbeIntegrationTest`).
3. Build **one executable WAR** via `package`/`bootWar`.
4. Check `jar tf`, manifest, provided runtime, and WAR hash.
5. Launch that exact WAR via `java -jar` on a lab port; wait until ready, then call `GET /probe` and assert the response.
6. Stop the standalone instance; copy the WAR to lab Tomcat and re-verify SHA-256.
7. Wait for Tomcat to confirm context deployment, call `GET /dual-mode/probe`, and assert the response.
8. Collect logs/hashes/HTTP statuses for both, undeploy, and clean up lab resources intentionally.
9. Promote only the **verified artifact**—never rebuild in a later stage bypassing the gate.

Using `-plain.war`/`.war.original` separately or deploying a freshly rebuilt WAR breaks the "same WAR" guarantee. Without reproducible archive settings and fixed timestamps, rebuilding can change the digest even with identical source code; therefore **copying the exact single file** is the most direct proof.

### 10.4 Never Assume "Wait 5 Seconds" Means Tomcat Is Ready

Startup time depends on hardware, data, network, schema migrations, and deployment state. A CI script should **poll HTTP with a timeout**, inspect logs on timeout, and stop the process on failure. Example read-only probe command:

```bash
curl --fail --silent --show-error \
     --connect-timeout 3 --max-time 10 \
     http://localhost:8080/dual-mode/probe
```

Only treat the endpoint as healthy once HTTP returns 200 with the expected body. On 404, check context path and deploy logs; on 503/500, check stack traces and the Spring context. A "running" container does not guarantee every webapp inside it is ready.

## 11. Context Path: The Single Most Common Source of Confusion

### 11.1 One Endpoint, Two URLs

With one controller mapping `/probe`:

| Factor | Standalone Embedded | External Tomcat |
| --- | --- | --- |
| Executed file | `dual-mode-0.0.1-SNAPSHOT.war` | Byte-identical copy named `dual-mode.war` |
| Port | `18080` per `--server.port` | `8080` per lab's default Tomcat `server.xml` |
| Context path | Root `""` | `/dual-mode` from WAR filename |
| Controller mapping | `/probe` | `/probe` |
| Full URL | `http://localhost:18080/probe` | `http://localhost:8080/dual-mode/probe` |
| Expected response body | `READY|context=` | `READY|context=/dual-mode` |

**Do not add `/dual-mode` to `@GetMapping` just to make external Tomcat work.** Controller mappings are paths **inside the context**; the container prefix is managed independently.

### 11.2 `ROOT.war` and Context Descriptors

If you name the WAR `ROOT.war` under Tomcat's default auto-deploy convention, the context path can be empty, making the external URL `http://localhost:8080/probe`. Both modes then return `READY|context=` at root context, yet they still use two distinct startup mechanisms.

Tomcat supports context mapping via host configuration and context descriptors. When custom mappings are used, the WAR filename alone no longer dictates the path; inspect real config, manager UI, or logs instead of guessing from the filename.

### 11.3 `server.servlet.context-path` Does Not Always Replace Tomcat Context

In embedded mode, `server.servlet.context-path=/api` makes the app run under `/api`. In external Tomcat, the webapp context is managed by the container upon deployment. Do not rely on editing `server.servlet.context-path` inside `application.properties` as a substitute for external Tomcat configuration across all environments. To change the URL on external deployment, configure the **container/host context path** properly.

### 11.4 Proxies and Public Paths

When the app sits behind Nginx, a load balancer, or ingress, the public URL may carry an additional prefix; `Forwarded`/`X-Forwarded-*` headers also influence how the app constructs absolute URLs. `ServletContext#getContextPath()` still reflects the **webapp context inside the container**, not necessarily the public prefix seen by end users. That is why this lab's probe illustrates container mechanics rather than full production routing.

## 12. Classpath Checks: Avoiding Duplicate Tomcat and Servlet APIs

### 12.1 Two Library Directories with Distinct Meanings

An executable WAR should place application libraries in `WEB-INF/lib` and embedded Tomcat in `WEB-INF/lib-provided`. In an external container, external Tomcat libraries are already supplied, so embedded Tomcat should stay out of `WEB-INF/lib` to prevent classloader conflicts.

**Illustrative** paths:

```text
WEB-INF/lib/spring-webmvc-6.x.jar
WEB-INF/lib/jackson-databind-2.x.jar
WEB-INF/lib-provided/tomcat-embed-core-10.1.x.jar
WEB-INF/lib-provided/tomcat-embed-websocket-10.1.x.jar
```

`6.x`/`2.x`/`10.1.x` are illustrative version-line labels, not exact filenames. Read actual names and versions from `jar tf` or the dependency graph.

### 12.2 How Do Maven and Gradle Resolve "Provided"?

Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
    <scope>provided</scope>
</dependency>
```

Gradle:

```groovy
dependencies {
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
```

Both configurations serve the same goal in this lesson, though their syntax and semantics across all classpaths are not completely identical. Maven core omits `provided` from the ordinary runtime dependency classpath, while Boot `repackage` adds special handling. Gradle War plugin's `providedRuntime` stays on runtime/test classpaths as needed yet stays out of a plain WAR as an app dependency; Boot `bootWar` places it into `lib-provided`.

**Do not use Gradle `compileOnly` instead of `providedRuntime` for Tomcat here**, because web integration tests need the container at runtime. **Do not use Maven `runtime` instead of `provided`** when targeting external Tomcat deployment, because embedded server libraries risk landing in `WEB-INF/lib`.

### 12.3 Why Quick Local Tests Miss Conflicts

An app can start locally because Boot's launcher picks the right libs from `lib-provided`, yet fail when deployed externally due to:

- Incompatible external Tomcat version / Servlet API.
- Mixing `jakarta.servlet` and `javax.servlet`.
- A JAR in `WEB-INF/lib` bundling server classes that clash under parent-first/delegation rules.
- Custom servlet/filter/listener config relying on the embedded server lifecycle.
- A library needed by the app accidentally marked provided even though the external container **does not supply it**.
- Server classpath carrying shared libraries incompatible with the app's libraries.

**Practical lesson:** even after `java -jar` PASSES, you must still test external deployment on a real Tomcat version. Conversely, a working WAR deploy does not prove the WAR has the Boot launcher and runs via `java -jar`.

## 13. Distinguishing Plain WAR, Boot Executable WAR, and JAR

| Artifact Type | Built By | Has `WEB-INF`? | Has Boot Launcher? | Runs `java -jar` by Default? |
| --- | --- | --- | --- | --- |
| Plain WAR Gradle `war` | Gradle War task | Yes | No by default | Not the goal of a plain WAR |
| Plain WAR Maven pre-repackage | Maven WAR Plugin | Yes | No by default | Not the goal |
| Boot executable WAR | Gradle `bootWar` or Maven `repackage` on WAR | Yes | Yes | Yes, if app/runtime valid |
| Boot executable JAR | Gradle `bootJar` or Maven `repackage` on JAR | Usually uses `BOOT-INF`, not WAR layout | Yes | Yes |
| Plain JAR | Gradle `jar` or Maven Jar Plugin | Not WAR layout | No by default | Only if manifest/classpath explicitly configured |

With Gradle Boot 3.3, the `war` task uses the `plain` classifier by convention when `bootWar` is configured, so you may see:

```text
build/libs/dual-mode-0.0.1-SNAPSHOT.war        # Boot executable
build/libs/dual-mode-0.0.1-SNAPSHOT-plain.war  # plain
```

With default Maven repackaging:

```text
target/dual-mode-0.0.1-SNAPSHOT.war            # Boot executable
target/dual-mode-0.0.1-SNAPSHOT.war.original   # WAR before repackage
```

Never select an artifact with a `*.war` wildcard when multiple types exist, and never grab `.war.original` expecting `WarLauncher`. In this "same WAR" verification, **the artifact must be identified once and kept untouched**.

## 14. Runtime Configuration Differences to Review After HTTP Passes

### 14.1 Port, Context, Hostname

Embedded Spring Boot can control `server.port`/`server.address` and `server.servlet.context-path`. External Tomcat has its own connectors and context mappings. When comparing:

- Who **owns the port**, the app or the container?
- Does the context path come from `server.servlet.context-path` (embedded) or WAR deployment descriptor / WAR filename (external)?
- Which hostname/port does the HTTP request actually hit? Does DNS/proxy rewrite the path?
- If using HTTPS, is TLS terminated at the Boot container, reverse proxy, or Tomcat connector?

### 14.2 Profiles and Externalized Configuration

Identical WARs do not enforce identical configuration. One environment may supply different `SPRING_PROFILES_ACTIVE`, database URLs, secrets, logging config, or Java system properties. If two endpoints exhibit different logic, do not jump to blaming executable/external incompatibility: compare runtime inputs first.

**Good verification principle:** pick a minimal `/probe` endpoint free of databases/secrets; once dual-mode startup is proven, layer on integration tests with external services. That keeps WAR packaging issues separate from environment connectivity errors.

### 14.3 App Lifecycle and Thread Handling

Standalone: stopping the JVM stops the embedded server. External: Tomcat manages deploy, undeploy, and can restart/reload the webapp while the Tomcat JVM stays alive. Therefore, check graceful shutdown and resource cleanup on undeploy—not just JVM termination—for threads, schedulers, connection pools, and app resources.

### 14.4 Logging and Classloaders

The standalone Boot launcher and external Tomcat use different classloading mechanisms. Tomcat also maintains its own server logs and may have different logging configurations or shared libraries. Do not assume "WAR deploy broke" merely because Spring logs do not appear on Tomcat's stdout; inspect both instance and webapp logs. Also avoid placing container-level libraries (like servlet engine implementations) inside `WEB-INF/lib` where they cause classloading conflicts.

## 15. Symptom-Driven Troubleshooting Without Guessing Root Causes

| Symptom | Possibilities to Check | Verification Step |
| --- | --- | --- |
| `java -jar app.war` reports `no main manifest attribute` | Using a plain WAR or Maven didn't run repackage | `unzip -p app.war META-INF/MANIFEST.MF`, check task/goal |
| `java -jar` cannot find main class | Wrong `Start-Class`, mispackaged class, or missing `main` | Inspect classes in `WEB-INF/classes` and manifest |
| Embedded run reports missing Tomcat classes | Missing `providedRuntime`/`provided` or custom packaging dropped `lib-provided` | `jar tf`, dependency report, `bootWar` task |
| Embedded run hits `Address already in use` | Port 18080/8080 already bound | Pass another `--server.port` for embedded; check listening process |
| External Tomcat starts OK yet URL returns 404 | Wrong context path, app deploy failed, initializer skipped, or controller unscanned | Test `/dual-mode/probe`, check deploy logs and `SpringBootServletInitializer` |
| External Tomcat fails with `javax.servlet` / `jakarta.servlet` | Old Tomcat 9 or mixed APIs | Use a Jakarta Servlet container compatible with Boot 3.3; inspect JARs |
| External Tomcat throws `NoClassDefFoundError` | App library marked provided when external container does not supply it | Check `WEB-INF/lib` and dependency graph |
| External Tomcat fails with duplicate Servlet/Tomcat classes | Embedded server library misplaced in `WEB-INF/lib` | Check `WEB-INF/lib-provided` and Maven/Gradle provided settings |
| WAR runs `java -jar` OK yet external deploy FAILS | Container, JDK, initializer, classpath, or app config differs | Compare runtime inputs, Tomcat logs, Servlet compatibility |
| External deploy OK yet `java -jar` FAILS | Plain WAR only, or missing Boot loader / `lib-provided` | Inspect executable WAR layout and build task |
| `/probe` returns `READY|context=` in both | External deploy at root path or unexpected context mapping | Check WAR name, `ROOT`, context descriptor, Tomcat Manager |
| External `/probe` 404 yet `/dual-mode/probe` OK | Context prefix omitted in first URL | Keep controller mapping `/probe`; use context-prefixed URL |
| SHA-256 differs between the two copies | Wrong file copied, WAR modified, or accidental rebuild | Stop, re-select source artifact, copy exact bytes, and re-hash |
| Tomcat log says webapp deployed yet endpoint fails | Servlet context failed init, or mapping/security error | Read Spring startup logs and specific HTTP 404/401/500 error |
| `@SpringBootTest` PASSES yet deploy FAILS | Test checks embedded runtime only | Add external Tomcat smoke test |
| CI checked WAR yet production runs a different build | Pipeline rebuilt/copied or deployed the wrong artifact | Attach SHA-256 and verify exact artifact at deploy stage |
| Gradle produces `-plain.war` alongside main WAR | `war` and `bootWar` are separate tasks | Pick `bootWar` output for dual-mode verification |
| Maven produces `.war.original` | Pre-repackage archive preserved | Pick executable `.war`, not `.original` |
| 404 occurs only behind reverse proxy | Proxy path rewrite or header forwarding differs | Test direct Tomcat URL first, then ingress/proxy |

### 15.1 Three Distinct Levels of "PASS"

- **Build PASS:** WAR was created; does not prove it runs.
- **Standalone PASS:** `java -jar` and `GET /probe` succeed; does not prove an external container works.
- **External PASS + byte identity:** Tomcat deploys the WAR cleanly, `GET /dual-mode/probe` succeeds, and source and copied WAR hashes match. Only with all three has the exercise proven **one executable WAR compatible with both mechanisms** in the test environment.

If external deployment succeeds using a WAR with a different hash, it **fails the same-artifact criterion**. If both hashes match yet the app never boots or returns HTTP 500, it also fails. Conclusions must combine hard evidence, not rely on a single "Deployment completed" log line.

## 16. Step-by-Step Lab: From WAR File to Repeatable Proof

### Part A – Set Up the Project

1. Choose Maven **or** Gradle; create the project matching the `dual-mode` example.
2. Add `DualModeApplication` extending `SpringBootServletInitializer` and `ProbeController`.
3. Pin Spring Boot 3.3.13, Java 17, and the Web starter; verify build tool and JDK compatibility.
4. Mark embedded Tomcat as `provided` (Maven) or `providedRuntime` (Gradle).
5. Add `ProbeIntegrationTest` and run the test.
6. Answer: if you remove `SpringBootServletInitializer`, which mode still works and which can break? If you use `compileOnly` instead of `providedRuntime`, what changes at test runtime?

### Part B – Package and Inspect the File

1. Build **one executable WAR** and record its exact path.
2. Compute SHA-256, save the result, and do not rebuild between the two tests.
3. List `WEB-INF/classes`, `WEB-INF/lib`, and `WEB-INF/lib-provided` with `jar tf`.
4. Check the manifest for `Main-Class` and `Start-Class`.
5. Explain why embedded Tomcat belongs in `WEB-INF/lib-provided` rather than `WEB-INF/lib`.
6. If `-plain.war` or `.war.original` exists, identify exactly which file is used for the dual-mode test.

### Part C – Run with `java -jar`

1. Run the original WAR with `--server.port=18080`.
2. Request `http://localhost:18080/probe`.
3. Confirm status 200 and body `READY|context=` per the example.
4. Record start/stop logs, JDK version, and WAR SHA-256.
5. Stop the application after measuring.

### Part D – External Tomcat

1. Prepare a lab Tomcat **10.1**, Java 17+, with a dedicated HTTP port.
2. Copy the **exact WAR** to `webapps/dual-mode.war` while lab Tomcat is stopped or per the proper deploy procedure.
3. Compare SHA-256 of the copy with the source WAR; they must match.
4. Start Tomcat, wait for deployment to finish, and inspect logs.
5. Request `http://localhost:8080/dual-mode/probe` per the example config; check HTTP 200 and body `READY|context=/dual-mode`.
6. Record the actual context path, port, and Tomcat version.
7. If a reverse proxy or context descriptor is present, adjust the URL and expectations to match real deployment rather than randomly changing Java mappings.

### Part E – Clarifying Confusing Edge Cases

On a separate lab branch (never in production), analyze one by one:

- Deploy `-plain.war`: why **can** an external container run it while `java -jar` fails?
- Rename `dual-mode.war` to `ROOT.war`: how do the path and `ServletContext#getContextPath()` change, and do the WAR bytes change?
- Run external Tomcat on port 8181 instead of 8080: which config must change? Why does `--server.port=8181` have no effect on a standalone external Tomcat?
- Remove `SpringBootServletInitializer`: does embedded `java -jar` still have a startup path via `main`? Is external startup still registered?
- Drop `providedRuntime` or move Tomcat to `implementation`: what changes in `WEB-INF/lib-provided`/`WEB-INF/lib`, and what external classloader risk arises?
- Rebuild the WAR between runs: how do you distinguish "same source code" from "same artifact bytes"?

Changes that break the WAR are **experimental lab exercises on a copy**. After observing, revert configuration before building a release pipeline.

## 17. Dual-Mode Deployment Report Template

Use this template so others can reproduce your results; uppercase values are **placeholders to fill with real results**, not pre-observed data:

```text
Project/module name: DUAL_MODE_MODULE
Spring Boot plugin version: BOOT_VERSION
Java (build/run): JAVA_VERSION
Build system: MAVEN_OR_GRADLE
Build command: EXACT_BUILD_COMMAND
WAR origin path: EXACT_ORIGIN_WAR_PATH
WAR origin SHA-256: ACTUAL_SHA256
WAR deploy copy path: EXACT_TOMCAT_WEBAPPS_WAR_PATH
WAR deploy SHA-256: ACTUAL_SHA256
Archive layout check: PASS_OR_FAIL

Standalone command: EXACT_JAVA_JAR_COMMAND
Standalone bind port: ACTUAL_PORT
Standalone URL: ACTUAL_URL
Standalone HTTP status: ACTUAL_HTTP_STATUS
Standalone response: ACTUAL_RESPONSE

Tomcat external version: ACTUAL_TOMCAT_VERSION
Tomcat connector port: ACTUAL_CONNECTOR_PORT
External context path: ACTUAL_CONTEXT_PATH
External URL: ACTUAL_EXTERNAL_URL
External HTTP status: ACTUAL_HTTP_STATUS
External response: ACTUAL_RESPONSE

Same WAR bytes? YES_IF_SHA256_MATCH
Both boot modes successful? YES_ONLY_IF_BOTH_HTTP_CHECKS_PASS
Observed discrepancies: ACTUAL_DETAILS
```

Never submit a blank template as a "PASS report." Record real values and keep key logs. If no Tomcat environment is available for deployment, you may complete the standalone section, **yet must clearly report external deployment as unverified** rather than inferring results from theory.

## 18. Official Documentation for Reference

- Spring Boot 3.3.13 – Traditional Deployment (Servlet initializer, Maven provided, Gradle providedRuntime): https://docs.spring.io/spring-boot/3.3/how-to/deployment/traditional-deployment.html
- Spring Boot 3.3 – Gradle Plugin, Packaging Executable Archives (`bootWar`, `WEB-INF/lib-provided`, plain WAR): https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3 – Maven Plugin, Packaging Executable Archives (WAR repackage, provided, manifest/layout): https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3.13 – System Requirements (Java, Maven/Gradle, Servlet container): https://docs.spring.io/spring-boot/3.3/system-requirements.html
- Spring Boot 3.3 – Executable Jar/WAR Format: https://docs.spring.io/spring-boot/3.3/specification/executable-jar/index.html
- Apache Tomcat 10.1 – Application Deployment and Manager, Servlet specification: https://tomcat.apache.org/tomcat-10.1-doc/deployer-howto.html
- Apache Tomcat 10.1 – Context Configuration: https://tomcat.apache.org/tomcat-10.1-doc/config/context.html
- Gradle – War Plugin: https://docs.gradle.org/current/userguide/war_plugin.html
- Maven – Dependency Scope Mechanism (`provided`): https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html

**Key takeaway:** a reliable dual-mode executable WAR requires **`main` + `SpringBootServletInitializer` + marking the embedded server `provided` + the `lib-provided` layout**. Verification must follow the entire chain: **build one WAR → inspect layout → run `java -jar` → copy exact bytes → compare SHA-256 → deploy to external Tomcat → send live HTTP requests**. Only when **both runs pass using the exact same WAR bytes** can you conclude the task is satisfied.