# Devtools Scope in Development Environments and Behavior with Packaged Applications

`spring-boot-devtools` shortens the feedback loop during Spring Boot development: classpath changes can trigger an **`ApplicationContext` restart**, certain static resource changes can trigger **LiveReload**, and default settings are tuned for convenient UI editing and error inspection. However, these conveniences **are not features to carry verbatim into operational environments**.

Specifically, there are two separate questions:

1. **Does the final JAR/container image contain the `spring-boot-devtools` dependency?**
2. **If Devtools is on the classpath, does it actually activate restart/LiveReload/default properties under the current launch method?**

In **Spring Boot 3.3**, running a packaged application with `java -jar` is recognized as a production-like launch and Devtools is **disabled by default**. Additionally, **repackaged archives exclude Devtools by default** when using Spring Boot's recommended build setup. These two layers reinforce each other, yet **never confuse "disabled" with "absent from the artifact"**.

This Knowledge lesson belongs to the **Spring Boot Application Runtime** module, chapter **Devtools**, applying to **Spring Boot 3.3.x, Java 17+, Gradle or Maven**. The goal is to understand Devtools' boundaries in local development, contrast **IDE/`bootRun` with executable JARs**, practice inspecting packaged files, and establish a safe boundary between development, staging, and production.

## 1. What Is Devtools and What Problem Does It Solve?

Spring Boot Devtools is a **development-phase dependency** named:

~~~text
org.springframework.boot:spring-boot-devtools
~~~

When placed properly on the development classpath and activated, it provides key capabilities:

| Group | Development Value | What Must Not Be Assumed |
| --- | --- | --- |
| Automatic restart | Quickly re-initializes the app when the classpath updates | Not hot swapping every Java bytecode inside the JVM |
| LiveReload | Signals LiveReload-enabled browsers when matching resources change | Not auto-rebuilding frontends or replacing server code in production |
| Development property defaults | Disables certain caches and surfaces extra debug details | Must not be treated as safe production defaults |
| Global/local Devtools settings | Configures watcher, trigger file, and restart behavior | Does not replace deployment configuration management |
| Remote development support | Controlled remote updates in certain dev scenarios | **Never enable remote Devtools in production** |

**Devtools is not a `dev` application environment in the sense of `spring.profiles.active=dev`.** Profiles select Spring configurations. Devtools is a module whose presence/absence on the classpath interacts with launch detection and dedicated flags.

For example, two environments may both use profile `dev`, yet one runs `bootRun` (directory-based classpath) and the other runs an executable JAR (packaged classpath). Devtools behavior differs despite the identical profile.

## 2. Two Distinct Layers of Protection: Dependency and Runtime Activation

### Layer A — Is the Dependency Inside the Artifact?

If Devtools **is absent from the released JAR**, none of its code exists to activate. This is a stronger safeguard than relying solely on runtime flags.

Recommended Gradle configuration:

~~~groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

Common Maven configuration:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
~~~

In Spring Boot 3.3, **repackaged executable archives exclude Devtools by default**. With Gradle, `developmentOnly` scopes the dependency strictly to development and keeps it from becoming a transitive dependency for other modules. With Maven, `optional=true` does not mean "forbidden everywhere", rather marking the dependency so it is not pulled transitively when another module consumes yours.

### Layer B — If the Module Is Still on the Classpath, Does It Run?

Spring Boot 3.3 also uses **launch-type detection**. When running a fully packaged application via `java -jar` (or a special classloader treated as a production launch), Devtools features are **automatically disabled**.

Per documentation, the system property:

~~~properties
spring.devtools.restart.enabled=false
~~~

can disable restart functionality. Conversely, setting the JVM system property `-Dspring.devtools.restart.enabled=true` can **force-enable Devtools even on a launch treated as production**, provided the module is on the classpath. **Never use this force-enable override in production** due to security and stability risks.

**Release rules should enforce both:** exclude Devtools from production artifacts **and** never set JVM/system/application properties force-enabling Devtools features.

### Scenario Matrix

| Scenario | Devtools on Classpath? | Expected Behavior |
| --- | --- | --- |
| IDE/classpath with `developmentOnly` | Present in dev config | Restart/LiveReload/default dev properties can run |
| `./gradlew bootRun` with `developmentOnly` | Present in dev runtime | Can activate Devtools and watch classpath |
| `./gradlew bootJar` with standard config | **Absent** from default repackaged JAR | No Devtools present to activate |
| `java -jar` with standard JAR above | Absent | Runs as a normal Spring Boot application |
| Fully packaged JAR **intentionally embedding Devtools** | Present | By default Spring Boot treats this as a production-style launch and disables Devtools |
| JAR intentionally embedding Devtools **and forced with `-Dspring.devtools.restart.enabled=true`** | Present | Can re-enable Devtools; **prohibited in production** |
| Container running exploded classpath **containing Devtools** | May be present | Do not rely on environment names; verify classpath and actual activation |
| `spring.profiles.active=prod` yet launched via IDE with Devtools present | Present | Profile `prod` **does not guarantee the module is gone** |

The rows above describe common **Spring Boot 3.3** behavior. When using custom packaging plugins, custom classloaders, layered images, exploded archives, or non-standard build tools, **inspect the actual artifact and launcher** instead of relying solely on command names.

## 3. Adding Devtools Properly in Gradle

For Spring Boot 3.3.x, use `developmentOnly` rather than writing:

~~~groovy
implementation 'org.springframework.boot:spring-boot-devtools'
~~~

The `implementation` line above is an **example of a non-recommended choice for dev-only tools**, as it mixes Devtools into the application's core dependency scope instead of isolating it as development-only. Do not copy it into the sample config below.

Complete configuration with Gradle's native BOM:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
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
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)

    implementation 'org.springframework.boot:spring-boot-starter-web'

    // Strictly for running in development environments:
    developmentOnly 'org.springframework.boot:spring-boot-devtools'

    testImplementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Common mistake:** the Spring Boot Gradle plugin does not automatically manage versions for unversioned dependencies without a BOM or dependency-management mechanism. The example declares `platform(SpringBootPlugin.BOM_COORDINATES)` so starters and Devtools resolve to Spring Boot's aligned versions. When a project already uses `io.spring.dependency-management` or a version catalog, keep one consistent dependency-management strategy.

In **multi-module projects**, add Devtools only to the runnable application module for development as needed; do not pull it into library modules as a production dependency merely to get IDE auto-restarts in the main app.

### Maven: `optional` and Packaging Are Two Separate Stories

If the app uses Maven, add:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
~~~

The Spring Boot Maven plugin **excludes Devtools from repackaged archives** by default. `optional` prevents the dependency from being pulled transitively by modules consuming your library, yet **it does not mean "Devtools is guaranteed absent from every package type"**. If using another build system or copying dependencies manually into an image, verify the final artifact.

## 4. When Does Devtools Watch Changes and Restart?

A common misconception: "Just save the `.java` file and Devtools immediately reads source and patches running code." The real workflow is:

1. Developer edits Java source.
2. IDE or Gradle/Maven **recompiles classes**.
3. The classpath directory holding classes/resources updates.
4. Devtools detects **classpath changes** via its file system watcher.
5. If changes satisfy restart rules, Devtools closes the old context, replaces the restart classloader, and builds a new context.

~~~text
Edit HelloController.java
   |
   v
Compile / Build Project / gradle classes
   |
   v
build/classes/java/main/HelloController.class changes
   |
   v
Devtools FileSystemWatcher detects
   |
   v
Close running ApplicationContext
   |
   v
Create new restart ClassLoader
   |
   v
Restart context / Spring Boot application
   |
   v
Call HTTP endpoint again -> see new logic
~~~

**If you only edit source without the IDE compiling and updating the classpath, no restart occurs.**

Depending on the IDE:

- Eclipse/Spring Tools usually compile/update the classpath on save.
- IntelliJ IDEA usually requires `Build Project` or appropriate auto-build settings.
- With Gradle `bootRun`, Devtools uses the main source set's classpath; when the compiler/Gradle updates output, the watcher detects it.

### Restart Is Not a JVM Process Restart

Spring Boot Devtools uses **two classloaders**:

- **Base classloader**: classes from rarely changing dependency JARs.
- **Restart classloader**: classes belonging to the project under active development, typically loaded from output directories.

On restart, the old restart classloader is discarded and a new one is created; **a new JVM process** is not needed every time. By keeping the loaded base intact, cycles can be faster than cold starts.

This also means:

- Each restart creates a **new `ApplicationContext` and new singleton beans**.
- Bean fields, static state in the restart classloader, and context in-memory caches are reset.
- Resources outside the Spring context or custom threads not properly cleaned up can leak across restarts.
- A "1-second restart" **is not equivalent** to a "1-second cold production startup" because the JVM, JIT, and base classloader are already warm.

**Devtools is not a replacement for rolling deployments, container restarts, or releasing new JARs.**

## 5. LiveReload Differs from Automatic Restart

Devtools can launch a **LiveReload server** to notify browsers running a LiveReload extension when resources change. Distinguish three behaviors:

| Change | Typical Default Behavior |
| --- | --- |
| Compiled Java class or non-excluded resource | Triggers **application restart** |
| Static resource in `/static`, `/public`, `/resources` or template in `/templates` | Normally **no context restart**, though it can trigger **LiveReload** |
| `.java` file saved without compiling; classpath unchanged | No guaranteed restart |
| File outside classpath with no additional paths configured | Not watched by Devtools |
| Code inside a dependency JAR changes | Not a general hot-reload target; may need rebuild/restart another way |

Paths excluded from restart by default in Spring Boot Devtools include:

~~~text
/META-INF/maven
/META-INF/resources
/resources
/static
/public
/templates
~~~

To adjust exclusions:

~~~properties
spring.devtools.restart.exclude=static/**,public/**
~~~

The config above **replaces** the corresponding default exclusion patterns. To **append** patterns while keeping defaults, use:

~~~properties
spring.devtools.restart.additional-exclude=uploads/**,generated/**
~~~

**Never add production data directories to the watcher** "for debugging convenience", as Devtools could restart the app whenever the system writes files there.

### Does LiveReload Require a Browser Extension?

Yes. Devtools emits LiveReload signals, while the browser needs a **LiveReload-supporting client** (typically an extension or equivalent integration) to auto-refresh. Do not treat the LiveReload server running as proof every browser tab refreshed automatically.

Only **one LiveReload server** should run per machine/port. When launching multiple DevTools apps from an IDE, not all of them can bind the LiveReload port simultaneously.

Disable LiveReload when not needed:

~~~properties
spring.devtools.livereload.enabled=false
~~~

This line **only disables LiveReload**; it does not turn off restarts or remove the dependency from the classpath.

## 6. Devtools Changes Property Defaults: Handy in Dev, Never a Production Baseline

Frameworks use caches to optimize throughput. During development, caching can hide template/static resource edits after a refresh. Devtools provides **development-time property overrides**, such as:

| Property | Devtools Development Default in Spring Boot 3.3 |
| --- | --- |
| `spring.thymeleaf.cache` | `false` |
| `spring.freemarker.cache` | `false` |
| `spring.mustache.servlet.cache` | `false` |
| `spring.web.resources.cache.period` | `0` |
| `spring.web.resources.chain.cache` | `false` |
| `server.error.include-message` | `always` |
| `server.error.include-stacktrace` | `always` |

These are **a few examples**, not the entire defaults table. Frameworks absent from a project (e.g., no Thymeleaf) mean the corresponding property has no practical effect.

Devtools easily makes local environments **diverge from production** in multiple dimensions:

- Static/template caching differs, so local performance does not mirror production.
- HTTP error responses can expose **extra details** that must never leak in public environments.
- Restart classloaders and repeated context startups alter runtime state.
- LiveReload/watchers add threads, ports, and file-watching overhead.

To disable **only Devtools property defaults** locally:

~~~properties
spring.devtools.add-properties=false
~~~

**This setting does not disable automatic restart or LiveReload.**

### Do Not Run Simulated Production Load Tests with Devtools Active

Devtools alters caching and classloading, so benchmarks on `bootRun` cannot establish:

- Cold startup of an executable JAR.
- CPU/RSS load and GC under real traffic.
- Static/template latency with production caching enabled.
- Classloader and dependency behavior of the released container image.

To validate production behavior, run the **actual release artifact** launched the way your deployment environment runs it, with matching JDK, profile, and memory limits.

## 7. Disabling Restart at the Right Level: Property vs. JVM System Property

Spring Boot 3.3 documentation distinguishes two cases:

### Stopping Change Watching While Still Initializing Restart Support

Set in `application.properties`:

~~~properties
spring.devtools.restart.enabled=false
~~~

This **stops watching files for restarts**, yet Spring Boot notes the restart classloader may still initialize. If you are facing a **classloader issue**, editing only the config file may not strip all restart machinery from bootstrap.

### Disabling Restart Support Very Early

Set the **JVM system property before `SpringApplication.run(...)`**:

~~~java
package com.example.devtools;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DisableRestartDemoApplication {

    public static void main(String[] args) {
        System.setProperty("spring.devtools.restart.enabled", "false");
        SpringApplication.run(DisableRestartDemoApplication.class, args);
    }
}
~~~

This is a **standalone class illustrating the restart-disable technique**; it is **not meant to coexist simultaneously in the Section 9 sample project**. Having two `@SpringBootApplication` classes in the same package causes component-scan conflicts, so test with **one** entry point at a time.

It can also be passed at launch:

~~~bash
java -Dspring.devtools.restart.enabled=false \
     -jar build/libs/devtools-scope-demo-1.0.0.jar
~~~

Note: `-D...` is a **JVM system property** and must appear **before `-jar`**. Placing it after the JAR makes it an application argument without the same early initialization timing.

**Operational stance:** to truly guarantee production contains no Devtools, **exclude the dependency from the artifact**. Disabling restart via properties is a runtime control, not proof the JAR lacks Devtools or remote support code.

## 8. `spring.profiles.active` Does Not Replace Dependency Scoping

Example:

~~~properties
spring.profiles.active=prod
spring.devtools.restart.enabled=false
~~~

This can **disable restart** in an environment, yet it does not prove Devtools is absent from the artifact, nor does it prove other Devtools components were stripped from the classpath.

Conversely:

~~~bash
java -jar app.jar --spring.profiles.active=dev
~~~

does not magically embed Devtools into the JAR if `bootJar` excluded it. Profiles switch config; **switching profiles cannot load a dependency that does not exist inside the artifact**.

Proper verification matrix:

| Question | How to Verify |
| --- | --- |
| Is the Devtools dependency declared strictly for development? | `build.gradle` / `pom.xml` |
| Is it on the runtime classpath of local `bootRun`? | Gradle dependencies/classpath in development mode |
| Is it inside the executable JAR? | `jar tf build/libs/....jar` and inspect `BOOT-INF/lib` |
| Which launcher runs the app? | Process command line, container `ENTRYPOINT`, app logs |
| Is the restart classloader active? | Devtools logs, classloaders, and classpath change tests |
| Does LiveReload open a port locally? | LiveReload logs/port, browser extension |
| Did production accidentally enable remote support? | Check build manifest, remote secret, exposed endpoints, and network |

**Never make `profile=prod` your sole security barrier.**

## 9. Runnable Example: Comparing `bootRun` with Executable JAR

We build a **Spring Boot 3.3.13 + Java 17 + Gradle** project with an HTTP endpoint returning:

- A `v1` marker to observe class changes.
- An `instanceToken` generated when the controller bean is instantiated, showing context recreation after classpath restarts.
- The class name of the classloader that loaded the controller, strictly for **local debugging**.
- A static resource to verify resource updates do not necessarily trigger restarts.

**Warning:** the classloader diagnostic endpoint below is for **local/test environments**, not public production builds. Excluding Devtools from packaging does not automatically remove debug endpoints you wrote yourself.

### 9.1 Directory Structure

~~~text
devtools-scope-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/devtoolsscope/
    │   │   ├── DevtoolsScopeApplication.java
    │   │   └── ProbeController.java
    │   └── resources/
    │       └── static/
    │           └── message.txt
    └── test/
        └── java/com/example/devtoolsscope/
            └── ProbeControllerTest.java
~~~

### 9.2 `settings.gradle`

~~~groovy
rootProject.name = 'devtools-scope-demo'
~~~

### 9.3 `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
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
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    implementation 'org.springframework.boot:spring-boot-starter-web'

    // For bootRun / IDE only; excluded from bootJar by default.
    developmentOnly 'org.springframework.boot:spring-boot-devtools'

    testImplementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**BOM matters:** when declaring starters and Devtools without explicit versions, a compatible dependency management mechanism is required. `SpringBootPlugin.BOM_COORDINATES` uses Gradle's native BOM support. Do not assume the Spring Boot plugin manages all versions automatically unless a BOM or `dependency-management` plugin is applied.

### 9.4 `DevtoolsScopeApplication.java`

~~~java
package com.example.devtoolsscope;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DevtoolsScopeApplication {

    public static void main(String[] args) {
        SpringApplication.run(DevtoolsScopeApplication.class, args);
    }
}
~~~

No Devtools API is invoked from application code. This is intentional: **Devtools is a development dependency**, so the app must run cleanly when Devtools is absent from the release JAR.

### 9.5 `ProbeController.java`

~~~java
package com.example.devtoolsscope;

import java.util.Map;
import java.util.UUID;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProbeController {

    private final String instanceToken = UUID.randomUUID().toString();

    @GetMapping("/api/probe")
    public Map<String, String> probe() {
        return Map.of(
                "marker", "v1",
                "instanceToken", instanceToken,
                "controllerClassLoader",
                ProbeController.class.getClassLoader().getClass().getName());
    }
}
~~~

**Explanation:**

- `"marker"` is fixed at `"v1"` in the initial source.
- `instanceToken` is generated once when Spring creates the controller bean; if the context restarts and recreates the bean, the token changes. This is an **illustrative signal**, not a replacement for real context lifecycle tracking.
- `controllerClassLoader` shows the class that loaded `ProbeController`. Under Devtools restart you may see a classloader in `org.springframework.boot.devtools.restart.classloader`; in a standard executable JAR, a different loader appears depending on launcher/version. **Never write tests asserting exact internal classloader names**.
- `Map.of` serializes to JSON via Jackson from the web starter; **JSON key order is not guaranteed**, so assert by field rather than raw JSON string equality.

### 9.6 Static File `message.txt`

Create `src/main/resources/static/message.txt`:

~~~text
resource-v1
~~~

Spring MVC's default static resource handler serves this file at:

~~~text
http://localhost:8080/message.txt
~~~

When `build/resources/main/static/message.txt` changes content, Devtools can emit LiveReload **without restarting the context** due to default restart exclusions. When editing source only, make sure the build/IDE copies the resource to the active classpath directory.

### 9.7 `ProbeControllerTest.java`

~~~java
package com.example.devtoolsscope;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProbeControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void respondsWithMarker() throws Exception {
        mvc.perform(get("/api/probe"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.marker").value("v1"));
    }
}
~~~

This test verifies basic HTTP behavior without relying on Devtools. **It does not prove Devtools is excluded from repackaged archives**; that step checks `bootJar` directly.

### 9.8 Build and Run Under the Development Classpath

In the project directory with a compatible Gradle Wrapper:

~~~bash
./gradlew clean test
./gradlew bootRun
~~~

In Windows PowerShell:

~~~powershell
.\gradlew.bat clean test
.\gradlew.bat bootRun
~~~

If you have no wrapper yet but have a compatible Gradle installed, you can use `gradle bootRun`.

Once the app has started, in another terminal:

~~~bash
curl -sS http://localhost:8080/api/probe
curl -sS http://localhost:8080/message.txt
~~~

**Example HTTP response structure** (the actual UUID and classloader name vary at runtime, not exact strings to match):

~~~json
{
  "marker": "v1",
  "instanceToken": "a-valid-uuid-generated-at-runtime",
  "controllerClassLoader": "org.springframework.boot.devtools.restart.classloader.RestartClassLoader"
}
~~~

Static file content:

~~~text
resource-v1
~~~

During `bootRun` with Devtools active, the classloader name above is **typical**, not a public contract to assert on. If Devtools is disabled or a different launcher is used, the name can differ.

### 9.9 Edit the Java Class and Observe Restart

On your **development machine**:

1. Keep `bootRun` running.
2. Edit `ProbeController.java`: change `"marker", "v1"` to `"marker", "v2"`.
3. Use IDE `Build Project` or run compile to update the classpath:
   
~~~bash
./gradlew classes
~~~

4. Watch restart logs; Devtools detects the recompiled class.
5. Call again:

~~~bash
curl -sS http://localhost:8080/api/probe
~~~

Once the restart completes, expect:

- `marker` becomes `v2`.
- `instanceToken` differs from the first run because the controller bean was recreated.
- The classloader may share the **class name** `RestartClassLoader`, yet the actual loader object is new.
- The JVM process running `bootRun` stays alive without re-invoking `java -jar`.

**If no change appears**, check `.class` copy timing, IDE auto-build settings, whether another Gradle daemon/launch is running, `spring.devtools.restart.enabled`, watcher logs, and whether the output directory matches the classpath watched by `bootRun`. Never conclude Devtools is broken just because you pressed Save without building classes.

After testing, restore `"marker", "v1"` and rebuild before running the JAR comparison section so tutorial data stays consistent.

### 9.10 Edit Only a Static Resource

Change `src/main/resources/static/message.txt` from `resource-v1` to `resource-v2`, then ensure `processResources` or the IDE updated the output classpath.

~~~bash
./gradlew processResources
~~~

Then:

- `GET /message.txt` returns the new content.
- Devtools can send a LiveReload signal to a browser extension.
- **No full context restart is needed** because `static/**` falls under default non-restart patterns.
- The controller's `instanceToken` stays unchanged across a static-only resource update.

**Browser/cache note:** if caching or proxies are involved, verify the raw request and response headers; a browser refresh alone does not prove the server read the new resource.

### 9.11 Build the Executable JAR

Stop `bootRun` after local testing. Build the archive:

~~~bash
./gradlew clean test bootJar
~~~

On Windows:

~~~powershell
.\gradlew.bat clean test bootJar
~~~

Given the example's `rootProject.name` and `version`, the JAR is created at:

~~~text
build/libs/devtools-scope-demo-1.0.0.jar
~~~

Check the real filename if the project customizes artifact names, archive classifiers, or build config.

### 9.12 Verify Devtools Is Absent from the JAR

On Bash (JDK includes `jar`):

~~~bash
jar tf build/libs/devtools-scope-demo-1.0.0.jar |
    grep 'BOOT-INF/lib/spring-boot-devtools'
~~~

With standard Gradle config, the command above **prints no matching lines**; `grep` returns exit code `1` when nothing matches, so **do not mistake that for a build error**. For a clean CI check:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

jar_file="build/libs/devtools-scope-demo-1.0.0.jar"

if jar tf "$jar_file" | grep -q 'BOOT-INF/lib/spring-boot-devtools'; then
    echo "FAIL: devtools found in release jar"
    exit 1
fi

echo "PASS: no spring-boot-devtools in executable jar"
~~~

On Windows PowerShell:

~~~powershell
$jar = ".\build\libs\devtools-scope-demo-1.0.0.jar"
$matches = jar tf $jar | Select-String 'BOOT-INF/lib/spring-boot-devtools'
if ($LASTEXITCODE -ne 0) {
    throw "Unable to list jar contents"
}
if ($matches) {
    throw "Unexpected devtools dependency in executable jar"
}
Write-Output "PASS: no spring-boot-devtools in executable jar"
~~~

**This inspects actual artifact contents rather than trusting the build script alone.** In standard Gradle builds, nested dependencies live under `BOOT-INF/lib`. If your project builds images from exploded/layered artifacts or custom assemblies, inspect those image-creation outputs too.

### 9.13 Run the Packaged Application

In a terminal:

~~~bash
java -jar build/libs/devtools-scope-demo-1.0.0.jar
~~~

And in a second terminal:

~~~bash
curl -sS http://localhost:8080/api/probe
curl -sS http://localhost:8080/message.txt
~~~

When the JAR is built with the sample config:

- The endpoint returns `marker=v1` if you restored source to `v1` before building.
- `instanceToken` is generated fresh when the JVM starts; there is no reason to compare UUIDs with `bootRun`.
- `controllerClassLoader` is **not** Devtools' restart classloader in standard setups.
- Editing `src/main/java` or `src/main/resources` on the dev machine **does not modify the already-built executable JAR**.
- The packaged app will **not auto-restart via Devtools** when you rebuild source in the project directory.
- To run new code/resources in the JAR, **build a new artifact and relaunch/redeploy that artifact**.

**Do not guess the exact classloader name** of an executable JAR, as Spring Boot loaders vary across versions and packaging modes. It suffices to prove Devtools is absent from the archive and classpath-change restarts no longer happen.

## 10. Why Can You See Devtools in the IDE Yet Not in `java -jar`?

Check sequence:

~~~text
IDE/bootRun
  -> uses output directories + developmentOnly dependency
  -> Devtools sees classpath directories
  -> Devtools monitors class/resource updates
  -> restart/LiveReload can run

bootJar
  -> packages classes/resources + runtime dependencies
  -> excludes Devtools by default
  -> JAR does not contain spring-boot-devtools

java -jar
  -> runs the packaged JAR
  -> Devtools is absent from archive
  -> editing external source/build output does not affect JAR contents
~~~

The crux is **build layout and launcher**, not a "dev/prod" profile name working magic.

### Packaged Does Not Mean "Live Source Reading"

An executable JAR contains a snapshot of **bytecode/resources from packaging time**. Editing `src/main/java` or `src/main/resources` afterward does not alter the JAR. If an external configuration file is reloaded by Spring via another mechanism, that is **runtime config reloading**, not Devtools restart.

Even if you rebuild a JAR **with the same filename** while a JVM is running the old JAR, never expect the JVM to pick up new bytecode automatically. Deploy a new build with a clear version/digest and use proper lifecycle/restart orchestration.

## 11. Devtools and Other Launch Forms

| Launch Form | Boundary to Remember |
| --- | --- |
| IDE from `build/classes`/`target/classes` | Directory-based classpath; Devtools can restart when output changes |
| `gradle bootRun` | Runs via `JavaExec` with main runtime classpath; suitable for development |
| `mvn spring-boot:run` | Runs on dev classpath; similar behavior when Devtools applies |
| `java -jar app.jar` | Fully packaged application; Devtools disabled by default even if embedded |
| Docker image from release JAR | Must not contain Devtools; inspect the actual image |
| Exploded/loose classpath in container | Not automatically production-safe if Devtools is present |
| WAR deployed to servlet container | Verify packaging/classloader and dependencies; never use Devtools in production |
| Native image/GraalVM | Never expect Devtools classloader restart to behave like a JVM dev classpath |

**Always inspect the final artifact and actual launcher.** A pipeline might produce a clean `bootJar`, yet the `Dockerfile` copies all of `build/libs` or pulls dev libraries into the image in a later step.

## 12. What If Someone Forces Devtools Into the Archive?

Spring Boot allows customizing packaging to **intentionally include Devtools in repackaged archives**, primarily for special remote development cases. For instance, docs mention Maven's `excludeDevtools=false`, while Gradle can customize the packaging task's classpath to include `developmentOnly`.

**This lesson strongly advises against enabling that option.** It is an exception meant for isolated/trusted test environments, not production configuration.

Why is it dangerous?

1. Remote support allows updating an app remotely; misconfiguring it compromises security.
2. Devtools development property defaults can expose more error information than acceptable in production.
3. Auto-restarting on classpath edits is not an audited release mechanism with clear versions/digests and rollbacks.
4. Restart classloaders and watchers can cause unexpected behavior in long-lived applications.
5. Container/Deployment workflows should deploy verified artifacts rather than swapping bytecode inside a customer-facing JVM.

Spring Boot documentation states **never enable remote Devtools support on a production deployment**. If an organization runs a dedicated internal remote dev environment, it still requires network isolation, TLS, strong secrets, and dedicated ops policies—**never turn that exception into an official deployment path**.

## 13. Comparing Devtools with Hot Reload and Production Deployment

| Mechanism | What Changes? | Where Appropriate? |
| --- | --- | --- |
| Devtools automatic restart | `ApplicationContext` and restart classloader | Developer machine / dev environment |
| Devtools LiveReload | Signals browser refresh when resources change | Developer machine with supporting client |
| JVM HotSwap / JRebel or bytecode reload tools | Can replace class definitions at another level | Per tool capabilities/license, usually dev |
| Full JVM restart | Fresh JVM/process, classpath loaded from scratch | Cold testing and operations |
| Docker/Kubernetes rolling update | New Pods/instances using new image/artifact version | Staging/production |
| Spring Cloud Config/Actuator refresh or custom config mechanism | Specific config values/runtime state | Must rely on explicit mechanisms and limits, not Devtools |

Devtools restart **is not "hot reload everything"**. It uses two classloaders and recreates the context. The JVM keeps the base classloader, so not every dependency JAR reloads and not every binary library update is picked up automatically.

## 14. Classloader Limitations in Multi-Module Projects

The Devtools restart classloader works well for most simple apps, yet multi-module projects or apps using reflection/serialization can hit:

- `ClassCastException` when the same class name is loaded by **two different classloaders**.
- `ClassNotFoundException` when a library uses the wrong thread context classloader.
- Resources/annotation types loaded early by the base classloader while application classes live in the restart loader.
- Context recreation exposing resource/thread leaks from uncleaned code.
- Objects deserialized with standard `ObjectInputStream` hitting classloader incompatibilities.

How to investigate:

1. Reproduce the bug under `bootRun` with Devtools.
2. Disable restart support via **system property** `-Dspring.devtools.restart.enabled=false` before `run()`.
3. If the bug disappears, suspect the classloader boundary instead of immediately rewriting business logic.
4. Compare class names and classloader identities where the error occurs.
5. If needed, use `META-INF/spring-devtools.properties` to adjust `restart.include` and `restart.exclude` by classpath.
6. Re-test changes on both the dev classpath and the packaged application.

Documentation example using `spring-devtools.properties`:

~~~properties
restart.include.projectcommon=.*/project-common-[^/]+\\.jar
restart.exclude.legacy=.*/legacy-module/(build|target)/.*
~~~

**These are illustrative regex patterns—never apply verbatim to every workspace.** Match against your real classpath and Java Properties regex escaping rules, especially double backslashes. Bad regexes can make things worse.

### A Limitation Worth Checking Immediately

`SpringApplication.setRegisterShutdownHook(false)` can break Devtools restarts, because Devtools depends on the context's shutdown hook to stop it during restarts. Never disable the hook just to "reduce logs" while using automatic restart.

There are also limitations with AspectJ weaving and deserialization; when encountering signature errors, consult **Known Limitations** for your exact Spring Boot version.

## 15. What to Disable? Picking the Right Tool

| Goal | Proper Approach | Do Not Confuse With |
| --- | --- | --- |
| Keep Devtools out of production JARs | `developmentOnly` / Maven `optional` + artifact check | Setting only profile `prod` |
| Stop watching classpath for restarts locally | `spring.devtools.restart.enabled=false` | Guaranteeing no restart loader is created |
| Disable restart support from early startup | JVM system property `-Dspring.devtools.restart.enabled=false` | Replacing dependency removal |
| Stop starting the LiveReload server | `spring.devtools.livereload.enabled=false` | Automatically disabling restart |
| Stop applying Devtools property defaults | `spring.devtools.add-properties=false` | Automatically disabling LiveReload or watcher |
| Restart only on explicit intent | `spring.devtools.restart.trigger-file=.reloadtrigger` | A production release mechanism |
| Prevent exposing remote devtools in deployment | Do not package/enable remote support on prod | Merely setting an arbitrary secret |
| Isolate production performance | Measure real JAR/image without Devtools | Treating devtools restart time as cold startup |

To **completely remove Devtools from a release**, prioritize **artifact-level controls**, not just runtime properties.

## 16. Inspecting Docker Images and CI/CD

Containerized deployments must inspect the **final image**, not just `build.gradle`.

Simple example `Dockerfile`:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY build/libs/devtools-scope-demo-1.0.0.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This is an **illustrative Dockerfile** assuming `bootJar` produced that filename, without a reader's actual app. It launches the JAR using exec-form so stop signals reach the Java process cleanly.

Never use a setup like this in production just to save build time:

~~~text
COPY entire-project-with-build-output /app
java -cp "/app/build/classes:/app/dev-libs/*" com.example.MyApplication
~~~

This is an **illustrative anti-pattern**, not a runnable Dockerfile. Copying development dependencies into the image and using a loose classpath can put Devtools on the runtime classpath, defeating artifact exclusion.

### Recommended CI Gates

- **Build gate:** consistent Gradle/Maven dependency management.
- **Archive gate:** executable JAR/WAR contains no `spring-boot-devtools`.
- **Image gate:** final image does not accidentally copy Devtools JARs or dev classpaths.
- **Configuration gate:** no `spring.devtools.remote.secret` and no forced `-Dspring.devtools.restart.enabled=true` in deployments.
- **Behavior gate:** startup/health/functional smoke tests run against the real artifact without Devtools.
- **Security gate:** no debug-only HTTP endpoints, excessive error details, or public LiveReload ports.
- **Release gate:** code changes roll out via versioned builds/image digests, rolling updates, and rollbacks—never auto-restarting from file edits inside containers.

These gates prevent the "build script looked right yet actual deployment still ships Devtools" failure mode.

## 17. Distinguishing Three Types of Testing

### Functional Testing

`@SpringBootTest` or `MockMvc` verifies endpoints/services work. Necessary, yet **does not tell whether a release artifact contains Devtools**.

### Classpath and Packaging Testing

Inspect `jar tf`, check `BOOT-INF/lib`, or inspect image layers/dependencies. This answers **whether Devtools is inside the package**, without proving every feature activates.

### Runtime Behavior Testing

Run `bootRun` and observe restarts on classpath edits; run the executable JAR and verify editing source does not alter the JAR. In production-like environments, verify the effective JVM command line, confirm Devtools is not forced on, and confirm no remote endpoint is exposed.

**All three** are needed to verify safety and proper behavior.

## 18. Common Practical Mistakes

**Mistake 1 — Thinking `spring.profiles.active=prod` removes Devtools.** False: profiles are configuration and do not alter already-built JAR contents. Inspect the artifact.

**Mistake 2 — Using `implementation 'spring-boot-devtools'` without checking scope.** Devtools is a development dependency; use `developmentOnly` and verify packaging output.

**Mistake 3 — Believing `java -jar` will auto-restart because the project declares Devtools.** Standard JARs exclude Devtools; packaged launches are also treated as production-style by Boot.

**Mistake 4 — Seeing `spring.devtools.restart.enabled=false` in `application.properties` and claiming no restart classloader is created.** Docs distinguish that from setting the system property early.

**Mistake 5 — Thinking Devtools compiles Java source itself.** It watches **classpath changes**; the IDE/build tool must update output classes.

**Mistake 6 — Thinking static resources must restart the entire context.** Static/template directories are usually restart exclusions and can trigger LiveReload.

**Mistake 7 — Thinking the LiveReload server refreshes every browser automatically.** A supporting browser extension/client is required.

**Mistake 8 — Thinking LiveReload and automatic restart share one toggle.** They use separate properties; disabling one does not remove the other.

**Mistake 9 — Measuring production startup using Devtools restart duration.** The base classloader/JVM is already warm, unlike a cold process.

**Mistake 10 — Copying an exploded development classpath into a container.** This can ship Devtools and dev mode into production even though standard `bootJar` excludes the module.

**Mistake 11 — Forcing `-Dspring.devtools.restart.enabled=true` on a packaged production app.** Re-enables Devtools if present, creating a security risk.

**Mistake 12 — Enabling remote support in production because `remote.secret` is set.** Spring Boot docs forbid this; a secret does not make a dev feature production-safe.

**Mistake 13 — Skipping checks for classloader leaks across multiple restarts.** Repeated new contexts expose uncleaned executors, threads, and sockets.

**Mistake 14 — Using `System.out.println` and concluding Devtools recreates beans on every Save.** Know which event triggers restarts and which instances/contexts actually recreate.

**Mistake 15 — Not inspecting the final image.** Dockerfiles/assemblies may bypass the verified JAR or copy extra dev dependencies.

**Mistake 16 — Leaving debug controllers in production because "Devtools was excluded".** Endpoints in application code still get packaged normally; remove or secure them separately.

**Mistake 17 — Treating `spring.devtools.add-properties=false` as an off switch for the whole module.** It only stops default property overrides.

**Mistake 18 — Ignoring multi-module classloader issues.** Devtools uses base/restart loaders; inspect boundaries on `ClassCastException` or reflection/serialization failures.

**Mistake 19 — Neglecting trigger files and `additional-paths` controls.** Continuously changing build/output files can trigger excessive restarts.

**Mistake 20 — Mixing up Spring Boot versions.** Property defaults, packaging plugins, and runtime behavior must match your version—never copy blindly from Boot 4.x into 3.3.

## 19. Self-Check Questions

1. **What environment is `spring-boot-devtools` primarily designed for?** Development.
2. **How do you declare Devtools in Gradle?** Use `developmentOnly 'org.springframework.boot:spring-boot-devtools'`.
3. **What attribute does Maven typically use for the Devtools dependency?** `<optional>true</optional>`.
4. **Does standard `bootJar` include Devtools?** No by default under standard Spring Boot 3.3 config.
5. **If Devtools is absent from the JAR, can `java -jar` use it?** No.
6. **If a JAR intentionally packages Devtools, does a fully packaged launch activate Devtools by default?** Typically no; Boot treats it as a production-style launch.
7. **Which system property can force-enable it, and should it be used in production?** `-Dspring.devtools.restart.enabled=true`; **should not be used, and never in production**.
8. **Does `spring.profiles.active=prod` remove Devtools from the artifact?** No.
9. **Where does the Devtools watcher detect changes?** Relevant directories/classpath entries, not uncompiled source code.
10. **Why might editing `.java` and pressing Save not trigger a restart?** Output `.class` files may not have changed yet.
11. **Does a DevTools restart spawn a new JVM process every time?** Not necessarily; it primarily swaps the restart classloader/context within the running JVM.
12. **Why is Devtools restart not a valid cold-startup benchmark?** The base loader/JVM is already warm.
13. **How many main classloaders does Devtools use for restart?** Two: base and restart.
14. **Must changing a resource in `static` restart the context?** Normally no; it can trigger LiveReload.
15. **What does LiveReload need on the browser side?** A supporting extension/client.
16. **Property to disable LiveReload?** `spring.devtools.livereload.enabled=false`.
17. **Property to disable Devtools property defaults?** `spring.devtools.add-properties=false`.
18. **Can setting the restart-disable property in an application file still initialize the loader?** Yes, it can.
19. **How do you disable restart support early?** Set JVM system property `spring.devtools.restart.enabled=false` before `run`.
20. **How do you prove a JAR does not contain Devtools?** List contents with `jar tf` and check `BOOT-INF/lib`.
21. **Why is checking only `build.gradle` insufficient?** Image or later packaging steps can still add dependencies.
22. **Should remote Devtools be enabled in production once a strong secret is set?** No.
23. **What risk do Devtools default error details pose?** Exposing debugging info to clients/logs.
24. **What errors can multi-module setups encounter?** Classloader identity, reflection, deserialization, and resource leaks.
25. **When replacing code in an already-built JAR, does the running JVM update automatically?** No; rebuild and launch/deploy the new artifact.
26. **Can `@SpringBootTest` prove packaging is free of Devtools?** No; inspect the artifact directly.
27. **Why avoid debug HTTP endpoints in production even after Devtools is excluded?** Because application-code endpoints are still packaged normally.
28. **What is the proper production deployment mechanism for code updates?** Versioned artifacts + controlled restarts/rolling deployments.

**Conclusion:** In Spring Boot 3.3, Devtools **serves the development classpath**, whereas releases should **omit the Devtools dependency**. Gradle `developmentOnly`/Maven `optional` handle dependency scoping; standard repackaged JARs exclude Devtools by default. When launching packaged apps via `java -jar`, Spring Boot also disables Devtools features by default if the module happens to be present. Separate **classpath presence** from **runtime activation**, understand that restarts depend on **compiled classpath changes** rather than auto-compiling source, and verify **JARs, images, effective JVM command lines, and runtime behavior**. Never enable remote Devtools in production; production changes must flow through clear build, release, and rollback pipelines.

### References

- Spring Boot 3.3 — **Developer Tools**, dependency scoping, fully packaged applications, default properties, restart/LiveReload, remote support: https://docs.spring.io/spring-boot/3.3/reference/using/devtools.html
- Spring Boot 3.3 — **Gradle Plugin: Running your Application**, `bootRun` and updating classpath: https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html
- Spring Boot 3.3 — **Gradle Plugin: Packaging Executable Archives**: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3 — **Gradle Plugin: Managing Dependencies**: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
- Spring Boot 3.3 — **Maven Plugin: Packaging Executable Archives**, Devtools exclusion: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — **Externalized Configuration and Profiles**: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — **SpringApplication** and application lifecycle: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
