# The Role of spring-boot-devtools in the Development Loop

## 1. What Problem Does Devtools Solve?

In a Spring Boot application, a small change in a controller, service, configuration, or template often forces the developer to repeat many steps:

```text
Edit code -> save -> compile -> stop app -> restart -> wait for startup
    -> call API or open browser -> inspect result -> continue editing
```

Manually stopping and restarting the application wastes time, especially when the Spring container has many beans and dependencies. **`spring-boot-devtools`** is a Spring Boot module aimed at improving the feedback loop during **local development**. It helps update the running program faster and reduces certain cache-related friction.

The development loop with Devtools typically looks like this:

```text
Developer edits Java code
      |
      v
IDE/Gradle/Maven compiles -> .class file changes on the classpath
      |
      v
Devtools detects changes in watched directories
      |
      v
Close old ApplicationContext, create a new restart classloader
      |
      v
SpringApplication restarts within the same JVM
      |
      v
Call API / check logs / test new behavior
      |
      +-------------------> continue editing
```

For resource changes such as static files or templates, the feedback path can be shorter: **no context restart is needed**; default development caching settings and LiveReload (if supported by the client) help display the new content.

**Key point:** Devtools automatically restarts when **the classpath is updated**, and **does not compile Java source code itself**. Saving a `.java` file does not automatically produce a new `.class` file in the directory watched by the running application.

This lesson focuses on **Spring Boot 3.3.x / Java 17+**, using `3.3.13` for Gradle examples. Devtools is not a library to ship to production: it alters the local development experience with two classloaders and defaults optimized for development rather than operations.

## 2. Four Main Roles of Devtools

| Role | Behavior | Practical Benefit | What Must Not Be Misunderstood |
| --- | --- | --- | --- |
| **Automatic restart** | Watches changes in classpath directories and restarts the Spring app when needed | Reduces manual stop/start cycles on every class edit | Not a hot swap that replaces code immediately in every running thread |
| **Development property defaults** | Applies convenient defaults for development, especially template/resource caching and error details | Easier to see changes without stale cached content | Never apply verbatim to production |
| **LiveReload** | Can run a LiveReload server to signal the browser to refresh when resources change | Reduces manual page reloads | Not a Java compiler, and not frontend bundler JavaScript HMR |
| **Condition evaluation delta** | Can log auto-configuration changes on app restart | Investigate why beans/auto-config changed after editing properties/dependencies | Does not replace full stack traces, tests, or understanding configuration conditions |

In addition, Devtools supports a **trigger file**, exclude/additional paths lists, file watcher and classloader tuning, as well as advanced mechanisms like remote development. Most projects only need the dependency, automatic restart, and property defaults.

### 2.1. The Goal Is Fast Feedback, Not Automated Operations

Devtools helps a developer quickly test hypotheses:

- Change a controller's response value and call the endpoint again.
- Change a service implementation and observe the bean being re-initialized.
- Edit a property and see its impact on auto-configuration.
- Change a template, static CSS, or JavaScript and see changes on render/reload.
- Observe a startup failure from a new code change without re-typing the run command.

However, Devtools does **not** guarantee:

- That the new code is correct: you still need unit/integration tests.
- That the database schema is migrated or test data is properly reset.
- That remote services are reachable.
- That every library supports the restart classloader.
- That existing HTTP clients are not interrupted during a context restart.
- That production images will not accidentally contain remote devtools if the team intentionally misconfigures defaults.

## 3. Adding the Dependency in the Correct Development Scope

### 3.1. Gradle Groovy

In `build.gradle` for Spring Boot 3.3:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
```

The snippet above is an **illustrative dependencies block**, requiring the Spring Boot Gradle plugin and an appropriate repository. The `developmentOnly` configuration makes it clear this is a developer tool; it should not be pulled into released runtime dependencies like a business library.

### 3.2. Maven

In `pom.xml`:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
```

`optional=true` prevents devtools from being pulled transitively into other modules that depend on your project. With standard Maven and Boot packaging, devtools is also handled so it is excluded from the default production artifact.

### 3.3. Does Devtools Run Automatically with java -jar?

**By default, no.** Spring Boot treats a fully packaged application run via `java -jar` as a production-like environment and automatically disables Devtools functionality. Executable JARs/WARs created by the Spring Boot repackager also **exclude devtools by default**.

Comparison:

| How It Is Run | Expected Reality |
| --- | --- |
| `./gradlew bootRun` with `developmentOnly` | Devtools is on the development classpath and can enable restart |
| IDE running main with directory-based classpath | Devtools can watch classpath output when properly configured |
| `mvn spring-boot:run` with optional dependency | Suitable for the development loop if the launcher/forking supports it |
| `java -jar build/libs/app.jar` with default Boot packaging | Do not expect Devtools restart to run |
| Docker/Kubernetes production image | Never include devtools/remote devtools; perform real deployments |

Do not treat the difference between `bootRun` and `java -jar` as a "bug": it is an intentional boundary between development environments and operational artifacts.

### 3.4. Warning About Remote Devtools

Spring Boot provides an **opt-in** remote development mechanism, but official documentation explicitly warns **never to enable remote devtools in production**, as it can introduce security risks. Do not configure `spring.devtools.remote.secret` or force-package devtools into a production JAR to "hot-patch" a live system.

For staging/dev environments with special requirements, evaluate strictly against security guidelines and trusted networks; a normal local loop **does not need remote devtools**.

## 4. How Does Automatic Restart Work?

### 4.1. Devtools Does Not Watch Every Source File Directly

Devtools monitors **directory entries on the classpath**. For a Gradle project, an example flow is:

```text
src/main/java/.../GreetingController.java    (source code)
        |
        +--> Gradle/IDE compileJava
                |
                v
build/classes/java/main/.../GreetingController.class (classpath)
        |
        +--> Devtools watcher detects change
                |
                v
Restart ApplicationContext
```

Editing and saving `GreetingController.java` when the IDE **has not yet produced a new `.class` file** may not trigger a Devtools restart. This explains why on machine A "every Save restarts" while on machine B "you have to click Build Project":

- Eclipse/STS usually updates classpath output automatically on save if incremental build is enabled.
- IntelliJ IDEA may require `Build > Build Project` or an appropriate auto-build configuration.
- Using Gradle/Maven, you can run a compile command that updates the classpath output watched by the running process.

The reliable checkpoint for debugging is **did the classpath output change?**, rather than guessing whether the IDE "registered the Save".

### 4.2. Two Classloaders Are Why Restarts Are Fast

Devtools uses a two-classloader model:

```text
JVM process
  |
  +--> Base ClassLoader
  |      +--> stable libraries, Spring JARs and dependencies
  |      +--> not reloaded across normal restarts
  |
  +--> Restart ClassLoader #1
  |      +--> classes of the project under development
  |      +--> creates ApplicationContext #1
  |
  +--> detects classpath changed
         |
         +--> closes ApplicationContext #1
         +--> discards Restart ClassLoader #1 when possible
         +--> creates Restart ClassLoader #2
                 +--> new project classes
                 +--> creates ApplicationContext #2
```

Libraries from regular JARs normally reside in the **base classloader**, while open projects on the classpath reside in the **restart classloader**. When code changes, Devtools reuses the heavy library classes already loaded in base and only rebuilds the application portion. Thus, **restarts are faster than a cold JVM start** in many projects.

**This does not mean "no Spring context restart".** Beans are recreated; `@PostConstruct` on new singleton beans runs again; `@PreDestroy` or lifecycle stop methods run on the old context during restart. Connections/clients owned by the context must be closed and created according to proper lifecycle rules.

### 4.3. How Restart Differs from Hot Swap, Browser Reload, and Redeploy

| Mechanism | What Changes | Is the Context Recreated? |
| --- | --- | --- |
| **Devtools restart** | Replaces the restart classloader, restarts the Spring app portion | **Yes**, inside a living JVM |
| **JVM cold restart** | Stops the Java process and starts a new JVM | Yes, along with restarting the JVM |
| **Debugger HotSwap** | JVM replaces certain bytecodes/methods under supported conditions | Not necessarily |
| **JRebel/dynamic class reloading** | Proprietary class rewriting/reloading technology | Not necessarily following Devtools semantics |
| **LiveReload** | Signals the browser to refresh UI/resources | Not required |
| **Frontend HMR** | Bundler updates JS/CSS modules in the browser | Not a core Spring Devtools feature |
| **Deploy new JAR/Container** | Release artifact is replaced in infrastructure | Has its own deployment lifecycle |

For Java bean/controller changes, Devtools typically **restarts the context**, rather than patching classes in-place. Therefore, in-memory state in beans can be reset; in-flight requests may be interrupted; tests must verify the new behavior after the application finishes restarting.

### 4.4. Important Classloader Limitations

Some libraries that use `Class.forName`, reflection, annotation scanning, proxies, `ObjectInputStream`, or custom serialization across different classloaders may encounter errors:

- `ClassCastException` when the same class name is loaded by two different classloaders.
- `ClassNotFoundException` during deserialization due to using the wrong context classloader.
- Annotations not being visible in the classloader expected by the application.
- Static singletons or threads retained by a library from a previous restart causing leaks.
- Multi-project modules placed into the wrong base/restart loader.

To investigate, try disabling restart. If the error disappears, inspect the classloader behavior and `META-INF/spring-devtools.properties`, rather than assuming your domain logic is wrong. Section 10 explains how to configure restart include/exclude rules.


## 5. Runnable Example: Spring Boot 3.3.13 / Java 17 / Gradle

We will create a small web app with an endpoint returning a string. The goal is to verify two paths:

1. **Edit Java -> compile -> Devtools restart** and the endpoint returns the new body.
2. **Edit static resource -> processResources -> new content** **without a full restart** under default excludes.

The project uses no database, frontend bundler, or external services; the example is compact enough to isolate exactly where to look.

### 5.1. Directory Structure

```text
devtools-loop-lab/
├── build.gradle
├── settings.gradle
└── src/main/
    ├── java/com/example/devloop/
    │   ├── DevLoopApplication.java
    │   └── GreetingController.java
    └── resources/
        ├── application.properties
        └── static/
            └── notice.txt
```

Directory paths, packages, and class names must match. The project assumes a **Java 17-compatible Gradle Wrapper**. If you do not have a wrapper yet, generate one once using an installed Gradle tool; the commands below use the wrapper.

### 5.2. The build.gradle File

```groovy
plugins {
    id 'java'
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
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The `settings.gradle` file:

```groovy
rootProject.name = 'devtools-loop-lab'
```

The `developmentOnly` dependency adds Devtools to the `bootRun` classpath while avoiding treating it as a runtime dependency of the deployable JAR. The Spring Boot Gradle plugin manages the dependency version via the declared dependency management, so you do not need to specify the Devtools version manually.

### 5.3. The application.properties File

Create `src/main/resources/application.properties`:

```properties
server.port=8080
demo.greeting=hello

# For local development:
spring.devtools.restart.enabled=true
spring.devtools.livereload.enabled=true
spring.devtools.restart.log-condition-evaluation-delta=false
```

We disable the condition evaluation delta log in the demo to keep logs simpler; this **does not disable Devtools restart**. If you want to see auto-configuration condition changes after each restart, remove the `log-condition-evaluation-delta=false` line.

**Do not place the devtools properties above into every production environment** as a general policy. They belong in a local development demo with the `developmentOnly` dependency. Production must still separate configs/secrets and use proper release artifacts.

### 5.4. Complete Java Main File

Create `src/main/java/com/example/devloop/DevLoopApplication.java`:

```java
package com.example.devloop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DevLoopApplication {
    public static void main(String[] args) {
        SpringApplication.run(DevLoopApplication.class, args);
    }
}
```

The `main` method simply starts the web application without closing the context after `run`. The Spring Boot web starter provides the embedded servlet server.

### 5.5. Complete Java Controller File

Create `src/main/java/com/example/devloop/GreetingController.java`:

```java
package com.example.devloop;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final String greeting;

    public GreetingController(
            @Value("${demo.greeting:hello}") String greeting) {
        this.greeting = greeting;
    }

    @GetMapping(
            value = "/hello",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String hello() {
        return greeting;
    }
}
```

The controller uses constructor injection from a property. When the context is rebuilt after a restart, a new `GreetingController` bean is created and receives the current configuration value.

### 5.6. Static Resource

Create `src/main/resources/static/notice.txt` containing a single line:

```text
asset-v1
```

Default Spring MVC static resource mapping serves this file at `GET /notice.txt` when the server is running. The example assumes no custom security filters.

### 5.7. Starting the Development App

Windows PowerShell (terminal A):

```powershell
.\gradlew.bat bootRun
```

macOS/Linux (terminal A):

```bash
./gradlew bootRun
```

Wait until server startup completes (not just until Gradle starts compiling). When Devtools is active, logs may show a restart thread, but **do not treat an exact thread name as a hard assertion**, as log formatting can vary by environment.

Open terminal B:

```bash
curl -sS http://localhost:8080/hello
```

The HTTP response body is:

```text
hello
```

Check the static resource:

```bash
curl -sS http://localhost:8080/notice.txt
```

The HTTP body is:

```text
asset-v1
```

Note that `curl -sS` may not append a trailing newline after the body; `hello` and `asset-v1` here represent the **response content**, not asserting neat terminal cursor line breaks. If the Windows PowerShell `curl` alias does not behave like real curl, use `curl.exe -sS ...` or `Invoke-RestMethod -Uri ...`.

### 5.8. Experiment A: Edit Java Code and Observe Restart

In `GreetingController.java`, change **only the method body**:

Before:

```java
public String hello() {
    return greeting;
}
```

After:

```java
public String hello() {
    return greeting + "-v2";
}
```

This is a **complete edit within the existing Java file**, without creating a second method with the same signature.

After saving, **make sure the `.class` file on the classpath is updated**. If your IDE does not auto-compile, run in terminal B:

macOS/Linux:

```bash
./gradlew classes
```

Windows PowerShell:

```powershell
.\gradlew.bat classes
```

This command builds Java classes/resources. **There is no need to stop terminal A and re-run bootRun.** When `build/classes/java/main/.../GreetingController.class` changes, Devtools detects it and restarts the context within the same JVM. Wait for the restart to succeed, then call:

```bash
curl -sS http://localhost:8080/hello
```

New HTTP response body:

```text
hello-v2
```

If you still see `hello`, do not immediately blame Devtools: first check whether Gradle/IDE actually compiled the new file, whether terminal A is still alive, whether the app loads classes from the right directory, and whether the request hits the right port/process.

### 5.9. Experiment B: Edit a Static Resource Without a Full Restart

Change `src/main/resources/static/notice.txt` from:

```text
asset-v1
```

to:

```text
asset-v2
```

If your IDE automatically copies resources into the output directory, Devtools detects the change. Otherwise, run in terminal B:

```bash
./gradlew processResources
```

Wait until `build/resources/main/static/notice.txt` is updated and call:

```bash
curl -sS http://localhost:8080/notice.txt
```

New HTTP response body:

```text
asset-v2
```

**Under Boot 3.3 default excludes, resources under `static/**` do not trigger a full restart**; LiveReload can send a browser refresh notification if the user has a client/extension and the LiveReload server is active. Because devtools adjusts caching defaults in development, static resources can usually reflect new content without restarting the entire application context.

What must be observed is the change in the **classpath resource output**, not merely an uncopied source file. If you do not see the new content, check `build/resources/main/static/notice.txt` instead of repeating `bootRun`.

### 5.10. Experiment C: Change Configuration

Change `demo.greeting=hello` to `demo.greeting=welcome` in `application.properties`. To make Gradle copy it into the classpath, run:

```bash
./gradlew processResources
```

When Devtools restarts upon the configuration resource change, the new controller receives the `welcome` property. If you kept `return greeting + "-v2";` from Experiment A, the endpoint returns:

```text
welcome-v2
```

This illustrates **bean recreation and reloading configuration on restart**. If properties are managed in an external source outside the classpath, do not assume changes there are automatically watched; design a different config refresh mechanism when appropriate.

### 5.11. Experiment D: Build a Production-Like JAR

Stop local `bootRun` (for example, Ctrl+C), then build:

```bash
./gradlew bootJar
```

The standard JAR is expected at:

```text
build/libs/devtools-loop-lab-0.0.1-SNAPSHOT.jar
```

Run it:

```bash
java -jar build/libs/devtools-loop-lab-0.0.1-SNAPSHOT.jar
```

Because `spring-boot-devtools` uses `developmentOnly` and default Boot packaging excludes Devtools, **do not expect this JAR to auto-restart** when you edit `src/main/java` or `src/main/resources`. The packaged JAR contains code/resources from build time; subsequent source edits **do not change the JAR**.

You can inspect it briefly with:

```bash
jar tf build/libs/devtools-loop-lab-0.0.1-SNAPSHOT.jar
```

When reading the JAR listing, you should not see `spring-boot-devtools` in `BOOT-INF/lib` with this build config. If custom packaging intentionally includes Devtools, review the build setup; **never enable remote Devtools in production**.


## 6. Property Defaults: Reducing Cache Friction in Development

One reason for "I edited the template, refreshed, and still see the old page" is browser or framework template/resource caching. In production, caching is very useful; in development, it can hide changes.

When Devtools is active, Spring Boot 3.3 automatically applies several **development-time property defaults**. Examples from the official documentation:

| Property | Default Preferred by Devtools | Meaning |
| --- | --- | --- |
| `spring.thymeleaf.cache` | `false` | Do not cache compiled Thymeleaf templates during the development loop |
| `spring.freemarker.cache` | `false` | Reduce caching of FreeMarker templates |
| `spring.web.resources.cache.period` | `0` | Do not cache HTTP static resources over time in development |
| `spring.web.resources.chain.cache` | `false` | Do not cache the resource chain as in production-optimized environments |
| `server.error.include-message` | `always` | Include extra error message details for debugging |
| `server.error.include-binding-errors` | `always` | Show binding errors in applicable error responses |
| `server.error.include-stacktrace` | `always` | Can include stack traces in error responses for development setups |

**Security warning:** These error options can expose internal details in responses. This is why **you must not carry Devtools property defaults into production**.

If you do not want Devtools to add development defaults, set:

```properties
spring.devtools.add-properties=false
```

This **disables adding property defaults**, without automatically disabling automatic restart or LiveReload. If you override a property with explicit configuration of appropriate precedence, inspect the effective configuration rather than assuming Devtools always wins over every property source.

### 6.1. LiveReload Differs from Automatic Restart

Devtools can run an embedded **LiveReload** server (typically on port `35729`). It sends a signal to a supporting browser client/extension to automatically refresh the page on resource changes. To receive refreshes, a compatible client/extension or equivalent integration must typically be active.

Distinguish between:

- **Java class changes:** Devtools can restart the Spring application, and then LiveReload notifies the browser to reload when appropriate.
- **Static/template changes:** Only copying resources and LiveReload/browser refresh may be needed, without restarting the context.
- **Browser does not auto-reload:** Devtools restart can still work normally; check the LiveReload server and client.
- **LiveReload server running:** Does not mean HTTP controllers auto-update; Java still needs compilation/restart.
- **Vite/Webpack JS HMR:** A separate subsystem, not Devtools replacing frontend modules inside the browser.

Only **one LiveReload server** can bind the default port at a time, so when running multiple Spring Boot apps from an IDE, subsequent apps may fail to start LiveReload. To disable it individually:

```properties
spring.devtools.livereload.enabled=false
```

Restart can still work as long as `spring.devtools.restart.enabled` is not disabled.

### 6.2. Different File Groups Have Different Processing Paths

| Changed File | Requires Compiler/Build Copy? | Full Restart by Default? | Verification |
| --- | --- | --- | --- |
| `.java` | **Must compile to .class** | Possible after classpath update | Call endpoint / check startup logs |
| `application.properties` on classpath | Requires resource output update | Usually triggers restart | Property value in recreated bean |
| `static/**` / `public/**` | Requires new resource file available at runtime | **No**, per default excludes | Call static URL / refresh browser |
| `templates/**` | Requires template copied/updated at runtime | **No**, per default excludes | Re-render template with dev cache disabled |
| Files completely outside classpath | Not automatically available unless watched/copied | Not by default | Configure additional paths or custom mechanism |
| Gradle/Maven dependency changes | Must resolve/rebuild classpath | Not all changes are safe to hot-restart | Restart `bootRun`/IDE if library classpath changes |

**Do not assume a rule like "every Save restarts the app".** IDE, Gradle, resource mapping, and classloaders all affect the outcome.

## 7. Useful Configurations When the Loop Is Too Noisy

### 7.1. Excluding Resources That Do Not Need Restart

Default excludes in Boot 3.3 include groups such as `META-INF/maven/**`, `META-INF/resources/**`, `resources/**`, `static/**`, `public/**`, and `templates/**`. Changes in these paths normally do not trigger a context restart but can still trigger LiveReload.

**Distinguish between these two properties:**

```properties
spring.devtools.restart.exclude=static/**,public/**
```

The `exclude` property **replaces the default exclude list** with the list you specify. If you only declare `static/**,public/**`, other defaults may **no longer be excluded**.

If you want to keep defaults and **add** a pattern for frequently generated files, use:

```properties
spring.devtools.restart.additional-exclude=generated/**,reports/**
```

The pattern above does not create directories or build resources. It only applies when those file paths are actually monitored by the watcher in the local environment.

### 7.2. Watching Additional Paths Outside the Classpath

For projects with source generators, shared templates, or frontend assets outside the classpath, you can use:

```properties
spring.devtools.restart.additional-paths=../shared-config
```

This value is only an illustrative local path. In practice, adjust it to your working directory and project layout; additional paths make Devtools watch file changes, but **do not compile Java, copy assets into JARs, or resolve dependency classpaths**. You can combine it with `exclude` to choose between triggering a full restart or LiveReload.

### 7.3. Using a Trigger File to Explicitly Control Restart Timing

When IDE auto-build runs continuously or many files are generated at once, a developer may not want every batch of file changes to trigger a restart. Spring Boot provides a trigger file mechanism.

Place an empty file in the classpath resource sources:

```text
src/main/resources/.reloadtrigger
```

Configure:

```properties
spring.devtools.restart.trigger-file=.reloadtrigger
```

Once Devtools has observed classpath changes, it only checks for restart when the trigger file is updated. **The trigger file must appear on the classpath and change in the classpath output**, not just at a random path outside the application.

Practical workflow:

1. Edit multiple Java or configuration files.
2. Run the compiler/build so the classpath output updates.
3. Touch/update `.reloadtrigger` copied onto the classpath when ready to check for restart.
4. Devtools evaluates whether changes warrant a restart and performs it if needed.

Modifying the trigger file **does not guarantee a restart** if no actionable changes were detected; this property throttles the loop rather than acting as a forced JVM restart button.

### 7.4. Tuning the Watcher for Slow File-Copy Environments

The Devtools watcher checks for changes periodically and waits for a **quiet period** to avoid restarting on a half-copied batch of class files. On slower machines, network-mounted projects, or multi-module IDE builds, a quiet period that is too short can trigger a restart against an inconsistent classpath.

Example configuration per documentation:

```properties
spring.devtools.restart.poll-interval=2s
spring.devtools.restart.quiet-period=1s
```

This makes the watcher poll roughly every 2 seconds and wait roughly 1 second with no further changes before starting a restart. Trade-off: slightly slower feedback, but lower risk of repeated restarts or reading partially copied class files.

Only adjust these values with evidence: repeated restart logs, transient `ClassNotFoundException` during builds, or IDEs copying many files. Do not arbitrarily set tiny poll intervals to be "fastest", as it increases overhead and risks classpath instability.

### 7.5. Logging Auto-Configuration Conditions

On each restart, Devtools can log the **condition evaluation delta**, which is useful when changing dependencies, profiles, or configuration properties toggles auto-configured beans on or off.

If logs are too noisy in local dev:

```properties
spring.devtools.restart.log-condition-evaluation-delta=false
```

This property does not disable Spring's condition evaluation; it only controls **logging the condition report delta** upon restart.

## 8. Disabling Restart Properly When Needed

### 8.1. Disabling the Watcher via application.properties

```properties
spring.devtools.restart.enabled=false
```

This setting usually prevents the file watcher from performing automatic restarts, though Boot 3.3 notes that **the restart classloader may still be initialized**. That means if you are debugging a classloader issue, setting this property solely in config may not let you test the app with a normal single classloader.

### 8.2. Disabling the Restart Classloader Completely

Set the **JVM System property** before calling `SpringApplication.run(...)`:

```java
package com.example.devloop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DevLoopApplication {

    public static void main(String[] args) {
        System.setProperty(
                "spring.devtools.restart.enabled", "false");
        SpringApplication.run(DevLoopApplication.class, args);
    }
}
```

This is a **complete variant replacing the main file in Section 5.4**; do not keep two `DevLoopApplication` classes at the same time. Because the property is set early at the System level, Devtools can avoid initializing restart support altogether, making it suitable for isolating classloader bugs.

Equivalent in launch arguments:

```bash
java -Dspring.devtools.restart.enabled=false -cp ... com.example.devloop.DevLoopApplication
```

This line is an **illustrative classpath command**, where `...` stands for the real classpath supplied by the IDE/build tool; it is not a standalone command. With Gradle `bootRun`, configure the Java process's JVM/system property if you need to thoroughly rule out the restart loader, rather than only passing an application argument `--spring.devtools.restart.enabled=false`.

### 8.3. Do Not Confuse the Switches

| Property | Effect |
| --- | --- |
| `spring.devtools.restart.enabled=false` | Disables automatic restart (if set as an app property, the restart loader may still exist) |
| `System.setProperty("spring.devtools.restart.enabled","false")` before `run` | Disables restart support early, useful for loader debugging |
| `spring.devtools.livereload.enabled=false` | Disables the LiveReload server |
| `spring.devtools.add-properties=false` | Disables development property defaults |
| Removing the Devtools dependency from the classpath | Removes the entire module and its utilities |

When debugging, try changing **one axis at a time** to tell whether an issue belongs to restart, browser reload, or property defaults.

## 9. Safe Restarts with State, Threads, and Resources

Because a Devtools restart **closes the old context and creates a new one**, treat it as a fresh application lifecycle at the Spring level. Resources owned by beans must be cleaned up:

- JDBC connection pools, HTTP clients, sockets, message consumers.
- Scheduled tasks/executors, watchers, and background threads.
- Singleton caches and state stored in bean fields.
- Objects tied to requests/sessions.
- File handles, temp files, and broker subscriptions.

A lifecycle example:

```java
@Component
class LocalWorker {
    @PostConstruct
    void start() {
        // Prepare resources when the new bean is created.
    }

    @PreDestroy
    void stop() {
        // Clean up bean-owned resources before the old context closes.
    }
}
```

This is an **illustrative class**, requiring imports for `Component`, `PostConstruct`, and `PreDestroy`, and is not a standalone runnable project. For long-running workers, consider `SmartLifecycle` to coordinate start/stop phases rather than leaving threads alive outside the Spring context.

### 9.1. Things Typically Reset on Restart

- Singleton bean state is recreated and does not retain runtime state from previous requests.
- `static` fields on application classes may be reloaded due to the new restart classloader.
- In-memory caches living solely in the JVM/beans may be lost or uninitialized.
- An H2 in-memory database may be recreated depending on URL/lifecycle; **do not treat Devtools as a data-preservation mechanism**.
- Session persistence may have specific development defaults, but that does not guarantee all application state is preserved.
- The JVM PID may remain unchanged across a Devtools restart; that is not evidence that the Spring context did not restart.

**Do not rely on static fields or manually spawned threads to retain state across restarts.** If you need to test persistent data models, use a real database/testcontainer or migration/fixture tools rather than relying on in-JVM caches.

### 9.2. In-Flight HTTP Requests and Restarts

When Devtools closes the old context, the web server may stop and recreate. HTTP clients may experience connection refused/reset/503 during the restart window. Devtools makes no zero-downtime rollout guarantees like a Kubernetes load balancer.

Use it only to speed up developer feedback, not as a deployment mechanism for production traffic.

### 9.3. Startup Failures and Recovery

If new Java code fails to compile, the IDE/Gradle **does not produce valid classpath output** for Devtools to restart with the new code. If compilation succeeds but bean initialization fails, Devtools may attempt a restart and the application will fail to come back up. Read the root cause, fix the bug, and compile again; do not assume Devtools automatically rolls back a broken build.

In some cases, the watcher and context may enter an abnormal state; manually restarting `bootRun` is a valid recovery measure while verifying the technical issue is resolved. It does not substitute for understanding classloader failures.


## 10. When to Configure the Restart Classloader?

In multi-module projects, Devtools may misclassify classpath entries between the base and restart classloaders. For example, an internal library module packaged as a JAR containing annotations or custom converters might be loaded by a different loader than the main app.

Consequences can include:

```text
ClassCastException:
  com.example.api.Type cannot be cast to com.example.api.Type

ClassNotFoundException / NoSuchMethodError / annotation not visible
```

A message saying "a type cannot be cast to the exact same class name" typically points to classloader identity; **the same class name is not enough**, as the classloader is also part of runtime identity.

Troubleshooting sequence:

1. **Confirm the error only happens with Devtools restart enabled.** Disable restart completely via system property before `run` and compare.
2. Identify which class/library is loaded by the base vs. restart loader and where long-lived references are held.
3. Inspect the dependency graph and how modules are placed on the classpath (directory vs. JAR).
4. Only when truly necessary, add `META-INF/spring-devtools.properties` to move classpath entries between the two loaders.
5. Re-verify with both a full cold start and multiple Devtools restarts, not just a single startup.

### 10.1. Configuration File Structure

```text
src/main/resources/META-INF/spring-devtools.properties
```

Keys take the form:

```properties
restart.include.myshared=/myshared-[\\w\\d\\-\\.]+\\.jar
restart.exclude.localmodule=/my-local-module/(build|bin|out)/
```

These are **illustrative patterns** that must be adapted to your project's real classpath. `restart.include.*` places matching entries into the restart classloader; `restart.exclude.*` moves matching entries to the base classloader. Values are **regexes applied to classpath URLs/paths**, not the Ant path patterns used by `spring.devtools.restart.exclude`.

Keys must be **unique**. Spring Boot reads all `META-INF/spring-devtools.properties` files found on the classpath. Do not confuse this file with `application.properties` or global devtools settings.

### 10.2. Why Not Do This by Default for Every Module?

Misconfiguring classloaders can increase memory footprint, slow down restarts, and mask serialization or circular dependency design flaws. When everything works properly, let Boot split the two loaders automatically; only customize after reproducing and understanding the cause.

### 10.3. Deserialization and Thread Context ClassLoader

Default Java `ObjectInputStream` or frameworks using reflection may fail to see new classes from the restart loader if the wrong classloader is selected. For cases where deserializing data in a Spring application is genuinely needed, Spring provides `ConfigurableObjectInputStream`, which can use the appropriate context classloader.

This is a deep diagnostic technique, not a mandatory step to enable Devtools. Before intervening, confirm the issue disappears when restart is disabled and inspect the involved library.

## 11. Production Boundary and Security Principles

### 11.1. Why Should Devtools Not Be Packaged for Production?

Devtools has defaults prioritizing developer convenience such as:

- Disabled/restricted caching for templates/static resources.
- Error responses that may expose more information.
- Classpath watchers and restart machinery.
- LiveReload server and remote development capabilities if explicitly enabled.

These are unsuitable by default for applications serving real users. Beyond performance and stability, exposing error details or opening a remote devtools endpoint poses **risks of information disclosure or unauthorized control**.

**Proper standard:** Development uses only `developmentOnly` or Maven optional; production artifacts use `bootJar`/`repackage`, which excludes devtools by default. Inspect the dependency tree and executable JAR contents before release. Never enable `spring.devtools.remote.secret` in production.

### 11.2. Devtools Is Not a Remote Hotfix Tool

If a bug appears in production, build and test a new artifact, roll it out through your release pipeline, and monitor health/rollbacks. Never use Devtools to "push new classes to a live container" to bypass deployment. Remote Devtools is an opt-in development feature, and Boot documentation advises against enabling it in production.

### 11.3. Be Careful with Real Data Even in Local Dev

An application running locally with Devtools might still point to a production database, broker, or remote API. Fast restarts and repeated startup runners can send requests or run migrations multiple times.

- Use separate dev profiles and credentials.
- Block write operations to production systems when running locally.
- Design `ApplicationRunner`, `@PostConstruct`, and `SmartLifecycle.start()` to be idempotent with clear ownership.
- Configure timeouts and avoid leaking connections across repeated restarts.
- Keep test data in isolated environments.

Devtools accelerates iteration on **both good code and bugs/side effects**, so maintain strict data boundaries.

## 12. Diagnostic Checklist When Devtools Does Not Restart

1. **Is the dependency present?** In Gradle, you need `developmentOnly 'org.springframework.boot:spring-boot-devtools'`.
2. **How is the app launched?** IDE/`bootRun` differs from packaged `java -jar`; JARs typically exclude devtools.
3. **Did the classpath output change?** Check `build/classes/java/main` or `target/classes` after compiling.
4. **Does the IDE have auto-build enabled?** Saving `.java` is not enough if the compiler has not updated `.class`.
5. **Is a trigger file enabled?** If so, you must update the configured file on the classpath.
6. **Is the file excluded?** `static/**` and `templates/**` usually use LiveReload without a full restart.
7. **Is `restart.enabled` turned off?** Check both app config and JVM system properties.
8. **Are JRebel/AspectJ weaving/custom launchers in use?** There are cases where Devtools restart is unsupported or disabled.
9. **Is the context shutdown hook disabled?** Devtools needs to close the context properly during restart.
10. **Did the watcher miss a batch file copy?** Try tuning poll interval/quiet period based on evidence.
11. **Is there a restart classloader error?** Try disabling restart early, and inspect modules and serialization.
12. **Are two processes bound to the same port?** Requests might be hitting an old JAR or another IDE instance instead of your newly compiled app.
13. **Is a proxy/browser caching?** Use `curl` directly or disable client cache to isolate.
14. **Did the server finish restarting successfully?** The root cause could be a bean startup failure rather than the watcher.
15. **Is the new resource in the output path?** If source changed but `processResources` did not copy it, runtime will not see it.
16. **Is Devtools triggering too many restarts?** Check generated files, excludes, and trigger files.
17. **Is LiveReload not working in the browser?** Check the extension/server/port; Java restart may still be working fine.
18. **Is the environment isolated?** The Gradle daemon, IDE output directory, and target Java process must align.

### 12.1. Quick Troubleshooting Table

| Symptom | Common Explanation | First Thing to Check |
| --- | --- | --- |
| Edit `.java`, Save, but API returns old result | No new `.class` on classpath | Compile and inspect `.class` |
| Running `java -jar` does not restart | Production-like packaged app | Use `bootRun` for development |
| CSS changed but no new startup logs | Resource excluded from full restart | Refresh browser, check static file |
| Logs show restart but HTTP still returns old value | Wrong process/port, stale code, or cache | Direct `curl` and check URL/PID |
| Multiple consecutive restarts | IDE copying in batches or generated files | Trigger file, quiet period, exclude |
| Strange `ClassCastException` on restart | Class loaded by two different loaders | Disable restart, check `spring-devtools.properties` |
| LiveReload enabled but browser does not refresh | Missing client/extension or port conflict | Check LiveReload server and browser integration |
| New static file visible but Java method still old | Static files do not trigger Java compilation | Build Java classes, wait for restart |
| Devtools disabled despite dependency in POM | Running packaged app, missing dev classpath, config off | Check launch mode and runtime classpath |
| Still restarts after `spring.devtools.add-properties=false` | Property only controls defaults | Use `spring.devtools.restart.enabled` to turn off restart |
| App fails startup after compiling | Bug in new code/config | Read root exception, fix, and recompile |
| Devtools runs initialization tasks multiple times | Context restart recreates beans/runners | Design startup logic to be idempotent |
| Template unchanged despite edited source file | Template not copied or template cache still active | Check output path and effective cache config |
| Devtools "stops" while debugging | Launcher, shutdown hook, or classloader issue | Check logs and launch method before blaming watcher |

## 13. Practice and Self-Assessment Questions

**Question 1.** Which step in the edit-test loop does `spring-boot-devtools` shorten?

**Answer:** It restarts the Spring application when classpath output changes, reducing manual stop/start cycles while also providing property defaults and LiveReload. Compiling and testing remain separate responsibilities.

**Question 2.** Why might simply saving a Java file not trigger a restart?

**Answer:** Devtools watches classpath directories rather than compiling source code itself. The IDE/Gradle/Maven must produce a new `.class` file.

**Question 3.** Does a Devtools restart launch a new JVM process?

**Answer:** No, by default. Devtools swaps the restart classloader and recreates the context within the same JVM, which can be faster than a cold start.

**Question 4.** Why might editing `static/app.css` not restart the context?

**Answer:** Static resources belong to default excludes; new content can be served/LiveReloaded without a full restart.

**Question 5.** How does `spring.devtools.restart.exclude` differ from `additional-exclude`?

**Answer:** `exclude` replaces the default exclude list; `additional-exclude` appends to the default list.

**Question 6.** How do you disable LiveReload while keeping auto-restart?

**Answer:** Set `spring.devtools.livereload.enabled=false`, leaving restart enabled.

**Question 7.** Why is `developmentOnly` needed in Gradle?

**Answer:** Because Devtools is a development tool, not a production dependency. It is used during `bootRun` but should not be transitive or packaged into default release JARs.

**Question 8.** If you run an executable archive built with standard configuration via `java -jar`, will editing `src/main/java` update the JAR?

**Answer:** No. The JAR is an already-packaged artifact and Devtools is disabled/excluded by default in packaged environments.

**Question 9.** Why can "Class X cannot be cast to Class X" occur?

**Answer:** Two versions of the same class name were loaded by different classloaders, so they do not share runtime type identity. Inspect base vs. restart loaders.

**Question 10.** Is LiveReload the same as Vite/Webpack HMR?

**Answer:** No. LiveReload signals the browser to refresh; it does not swap frontend modules in memory with HMR semantics.

**Question 11.** Does `spring.devtools.add-properties=false` disable auto-restart?

**Answer:** No. It disables development property defaults and does not control the restart watcher.

**Question 12.** How do you completely remove the restart classloader when debugging a library issue?

**Answer:** Set `System.setProperty("spring.devtools.restart.enabled","false")` before `SpringApplication.run` or remove the Devtools dependency from the classpath.

**Question 13.** Why can Devtools cause a bean's `@PostConstruct` to run multiple times in one IDE session?

**Answer:** Each restart creates a new ApplicationContext, so singleton beans are re-initialized.

**Question 14.** Should you enable remote devtools to patch a production JAR without redeploying?

**Answer:** No. Spring Boot documentation advises against enabling remote devtools in production due to security risks.

**Question 15.** If a trigger file exists but no actionable classpath changes occurred, is touching the trigger guaranteed to restart?

**Answer:** No. The trigger file tells Devtools to check for updates and only restarts if relevant changes were detected.

**Question 16.** When startup fails after a restart, where should you look?

**Answer:** The root stacktrace / `APPLICATION FAILED TO START`, compilation output, configuration/dependency changes, and resource state. Devtools does not fix or roll back business/code errors automatically.

## 14. Summary and References

### 14.1. Principles to Remember

- **Devtools is a local development loop tool**, not a component meant to run in production.
- **Java source -> compile -> classpath update -> Devtools restart** is the critical chain. Saving alone may not suffice.
- **Restarts use two classloaders**, usually faster than cold starts, yet still recreate the Spring ApplicationContext and bean state.
- **Static/template resources** are typically excluded from full restarts; dev cache defaults and LiveReload speed up feedback.
- **LiveReload only hints the browser to refresh**, and does not compile Java or replace JRebel/frontend HMR.
- **`developmentOnly` / Maven optional**, and Boot packaging excludes or disables Devtools in executable JARs by default.
- **Only tune** `additional-exclude`, `additional-paths`, trigger files, and poll/quiet periods when there is a clear need.
- **Proactively test disabling restart** if you encounter unusual classloader or serialization errors.
- **Never enable remote devtools in production**, and never let error-detail defaults leak real data.

### 14.2. Official Documentation for Spring Boot 3.3

1. [Spring Boot 3.3 — Developer Tools](https://docs.spring.io/spring-boot/3.3/reference/using/devtools.html): dependencies, automatic restart, LiveReload, property defaults, and troubleshooting.
2. [Spring Boot 3.3 — Running Your Application](https://docs.spring.io/spring-boot/3.3/reference/using/running-your-application.html): IDEs, Gradle/Maven launchers, and development mode.
3. [Spring Boot 3.3 — Gradle Plugin](https://docs.spring.io/spring-boot/3.3/gradle-plugin/reference/htmlsingle/): `bootRun`, `bootJar`, and `developmentOnly`.
4. [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.devtools.*` properties and default values.
5. [Spring Boot 3.3 — Packaging for Production](https://docs.spring.io/spring-boot/3.3/reference/using/packaging-for-production.html): boundary between executable artifacts and development runtime.

**Conclusion:** `spring-boot-devtools` shortens the **edit -> compile -> observe application response to new code** loop via fast restarts, convenient caching defaults, and LiveReload. Its value lies in **developer feedback**, not replacing compilers, test suites, release pipelines, or safe operational practices.
