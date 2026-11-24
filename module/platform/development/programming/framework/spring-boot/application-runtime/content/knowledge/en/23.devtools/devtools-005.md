# Excluding Paths, Watching Additional Paths, and Using a Trigger File in Spring Boot Devtools 3.3

## 1. Objectives and Context

When developing with Spring Boot, editing a Java, HTML, CSS, configuration, or external resource file can result in different actions: **restarting the application context**, **notifying LiveReload**, **doing nothing**, or **waiting for an explicit confirmation action**. Spring Boot Devtools lets you control this behavior with three configuration groups:

- `spring.devtools.restart.exclude` and `spring.devtools.restart.additional-exclude`: define **which path changes do not require a full application restart**.
- `spring.devtools.restart.additional-paths`: expands the scope of **watched directories** beyond those already on the classpath.
- `spring.devtools.restart.trigger-file`: restricts **checking and triggering a restart to the moment you update a trigger file**, instead of restarting every time the IDE compiles.

This lesson belongs to the **Devtools** group, focusing directly on how these three mechanisms coordinate with **classpath output** and build tools. It uses Java 21, Spring Boot **3.3.13**, Maven, and `spring-boot-devtools`.

After completing this lesson, you should be able to:

1. Distinguish `restart` from `LiveReload` and browser refreshes.
2. Understand when source code edits become visible to Devtools, and why changing `src/main/java` may not trigger a restart if `target/classes` has not been updated.
3. Understand default exclusion paths and the difference between **overriding** and **appending** exclusions.
4. Watch an external directory outside the classpath without confusing **watching for changes** with **loading files into the Environment/classpath**.
5. Create a trigger file present on the classpath and update it only when you want Devtools to evaluate pending changes.
6. Run the sample project with `mvn spring-boot:run` and test Java changes, static resources, additional paths, and the trigger file.
7. Troubleshoot no-restart issues, excessive restarts, ineffective trigger files, and classloader/security misconceptions.
8. Write JUnit tests for the application, while understanding that restart file-watching requires integration/manual process tests rather than unit tests asserting OS watcher behavior.

**Important boundary:** Devtools is a **local development** tool—not a production hot-deploy framework, not an automatic configuration distribution mechanism, and not a replacement for rolling deployments.

## 2. Underlying Mechanism: Which Files Are Watched?

### 2.1. Devtools Does Not Watch Everything on Disk

Spring Boot Devtools normally watches entries on the **runtime classpath** that point to **directories**, for example:

```text
Maven project
src/main/java/com/example/demo/StatusController.java
                       |
                       | javac / mvn compile / IDE Build
                       v
target/classes/com/example/demo/StatusController.class
                       |
                       | Devtools file watcher detects classpath change
                       v
Restart needed? Trigger file configured?
                       |
                       +--> restart context (if conditions are met)
```

Editing `StatusController.java` in an editor without compiling/syncing the corresponding `.class` file **does not** give Devtools a classpath change. That is why:

- Eclipse or Spring Tools may update output on Save/Build depending on settings.
- IntelliJ IDEA often requires `Build -> Build Project` or enabling auto-compile while running.
- Maven can use `mvn compile` from another terminal.
- When running the app through a build plugin, you must keep **forking** properly enabled so the restart classloader works; do not disable forking and expect normal Devtools restarts.

The exact classpath output depends on the IDE/build tool: commonly `target/classes` for Maven, `build/classes` or `build/resources` for Gradle, or an IDE output folder. Always know which classpath the JVM is using.

### 2.2. Two Classloaders and Fast Restarts

Devtools restarts typically use:

- **Base classloader** for rarely changing libraries such as JAR dependencies.
- **Restart classloader** for project classes and resources under active development.

On restart, the restart loader is replaced with a new instance, the Spring application context is recreated, and corresponding bean lifecycles run again. Libraries already loaded in the base classloader are reused, so restarts can be shorter than cold starts.

This is **not** modifying a running method's body inside the JVM without recreating the Spring context. Old beans are destroyed and new beans are created, so you must consider differences from true hot code swapping regarding sessions, caches, and in-memory data.

### 2.3. Restart Differs from LiveReload

| Behavior | Spring Application | Browser |
| --- | --- | --- |
| **Full restart via Devtools** | Closes old context and starts a new context | May be asked to refresh when LiveReload is active |
| **LiveReload** | Does not necessarily restart the context | Browser with a LiveReload client/extension can reload |
| **Manual refresh** | Typically does not restart Spring | Browser sends a new request and displays updated content |
| **No classpath change** | File watcher may see no changes | No basis for auto-reloading |

Devtools includes a LiveReload server in development mode when enabled and in an eligible environment. **Do not confuse** serving an updated static file after pressing F5 with the Spring context restarting. To prove a restart occurred, look for an `ApplicationReadyEvent` log or verify a new lifecycle/instance.

## 3. Default Path Exclusions

Certain resource directories do not require a full restart whenever edited. Per Spring Boot 3.3 documentation, Devtools excludes these groups by default:

- `META-INF/maven/**`
- `META-INF/resources/**`
- `resources/**`
- `static/**`
- `public/**`
- `templates/**`

Therefore, modifying matching resources normally **does not trigger a full restart**, though it can trigger **LiveReload** when Devtools and LiveReload are properly configured.

Example:

```text
src/main/resources/static/site.css
          |
          | copy resources:resources
          v
target/classes/static/site.css
          |
          +-- New file read by server from classpath output
          +-- No Spring context rebuild needed by default
          +-- Browser can refresh manually or via LiveReload
```

Paths in patterns should be understood in terms of how Devtools matches the directories it watches. The `**`/`*` wildcards are glob-style/Ant-style configuration patterns, **not** literal filenames.

### 3.1. Replacing Exclusions with restart.exclude

Example:

```properties
spring.devtools.restart.exclude=static/**,public/**
```

**Point to remember:** `restart.exclude` **customizes/replaces the default list**, rather than appending these two patterns to all defaults.

Consequence: groups normally excluded by default, such as `templates/**` or `META-INF/resources/**`, may no longer be excluded if you specify only `static/**,public/**`. Editing them could cause Devtools to restart more aggressively than expected.

Use `restart.exclude` only when you **genuinely want to manage the entire exclusion set**, have checked the remaining patterns, and accept the change to restart/LiveReload behavior.

### 3.2. Keeping Defaults and Adding Exclusions: additional-exclude

To **keep the default exclusions** and add build-generated directories or temporary files:

```properties
spring.devtools.restart.additional-exclude=generated/**,**/*.tmp
```

This means files matching the additional patterns will not force a full restart under the exclusion policy, while `static/**`, `public/**`, `templates/**`, and the rest retain their default behavior.

For example, choosing `generated/**` for a directory containing files continuously generated on the classpath avoids triggering a restart on every unrelated report or metadata update. Evaluate whether those files **truly do not affect runtime beans/configs**: if a bean reads the content once at startup, excluding restarts may prevent the bean from ever loading the new value.

**Avoid `additional-exclude=**/*` or overly broad patterns**: doing so prevents important Java/classpath changes from triggering restarts and makes debugging confusing.

### 3.3. Comparison Table

| Configuration | Default Exclusion Set | Additional Patterns |
| --- | --- | --- |
| Nothing declared | Keeps defaults | None |
| `spring.devtools.restart.exclude=static/**,public/**` | **Replaced** by declared set | Static, public |
| `spring.devtools.restart.additional-exclude=generated/**` | **Keeps** defaults | Generated |
| Both `exclude` and `additional-exclude` set | Uses replacement set from `exclude` | Appends `additional-exclude` group |

When checking behavior, do not look solely at source file paths. Identify **the file on the classpath/path watched by the watcher** and the pattern Devtools applies to that path.

### 3.4. Excluding from Restart Does Not Remove from Classpath

A `static/site.css` on the classpath is still served by the HTTP server. `restart.additional-exclude` only affects **reload/restart decisions on change**; it does not remove files from JARs, forbid Spring from reading them, or make files secret.

If a file must not be packaged or released, fix Maven resources, Gradle source sets, packaging, or security rules; `spring.devtools.restart.exclude` cannot substitute for package exclusions.

## 4. Watching Additional Directories with additional-paths

Devtools watches classpath directories by default. Sometimes a project has a directory **outside** the classpath that still needs change detection during development:

```text
workspace/
├── local-dev-watch/             <-- outside app classpath
│   └── marker.txt
└── devtools-watch-demo/
    ├── pom.xml
    ├── src/main/java/...
    └── target/classes/...
```

Configure in `devtools-watch-demo/src/main/resources/application.properties`:

```properties
spring.devtools.restart.additional-paths=../local-dev-watch
```

The example above assumes the running process's working directory is the **project directory**. With IDEs, build runners, containers, or scripts, the working directory may differ. To be certain, use a **development-environment absolute path** or verify `user.dir` and that the target directory exists before running. Never hardcode a personal machine path into a shared multi-OS repository.

### 4.1. Watching Does Not Mean Automatically Reading Files

`additional-paths` only adds a **change source** to the file-watching mechanism. It does not automatically:

- Add files to the Java classpath.
- Put the directory into `spring.config.import`.
- Create new Spring beans for those files.
- Reload objects that previously read the file in a business sense.
- Distribute files to every node in Kubernetes.

For example, editing `../local-dev-watch/marker.txt` can make Devtools consider a restart, yet if application code **does not read** `marker.txt`, business behavior remains unchanged. If the application needs to read real configuration, configure the file-loading path and startup behavior explicitly.

### 4.2. Changes in additional-paths: Restart or LiveReload?

Files under additional paths are treated as changes warranting a full restart unless matched by exclusion rules. Spring Boot docs allow pairing `restart.exclude` settings to choose between full restart and LiveReload for additionally watched paths.

A sound workflow:

1. Specify an existing additional directory.
2. Start the application and wait for Devtools to settle.
3. Edit a non-excluded file and observe the restart.
4. If exclusions are needed, add patterns matching **how Devtools matches the actual path**; verify on the target OS/build runner.
5. If using a trigger file, update the trigger file on the classpath after making edits rather than expecting the additional directory to restart immediately.

**Do not confuse them:** `additional-exclude` and `additional-paths` are not synonyms. One says **which files should not trigger a restart**, while the other says **where else to watch**.

### 4.3. Is It Good to Watch Directories with Constantly Changing Data?

Usually no. A directory of logs, uploads, temporary outputs, or large generated artifacts changes continuously, causing Devtools to waste work scanning or restarting repeatedly. Avoid putting entire `target`, `build`, database files, temporary upload directories, or large git worktrees in `additional-paths` unless truly necessary.

In multi-module projects, watch only output directories that hold meaningful changes; pointing the watcher at all dependency JARs will not make them classloader-reloadable the way you expect.

## 5. Trigger File: Restart Only When Explicitly Requesting a Check

### 5.1. Purpose

In an IDE that compiles continuously, Devtools can restart too often: the developer saves file A, keeps editing file B, code is not yet in a consistent compiled state, or the application context keeps getting rebuilt. A **trigger file** creates a manual confirmation checkpoint.

Example property:

```properties
spring.devtools.restart.trigger-file=.reloadtrigger
```

The `.reloadtrigger` file must exist **somewhere on the runtime classpath**. Placing it in `src/main/resources` so it gets copied into output is a standard approach:

```text
src/
└── main/
    └── resources/
        ├── application.properties
        ├── .reloadtrigger
        └── static/
            └── message.txt
```

The property value is **the filename without a path**: `.reloadtrigger`, not `src/main/resources/.reloadtrigger` or `target/classes/.reloadtrigger`.

### 5.2. What Does the Trigger File Actually Control?

Updating the trigger file tells Devtools to **check changes it has already detected**. A restart **only actually happens if Devtools detected actionable work**; touching the trigger file with no prior restart-worthy changes may produce no observable restart.

Typical flow:

```text
Edit multiple Java files
      |
      +-- IDE/Maven compiles, target/classes changes
      |
      +-- Devtools records changes, but trigger-file has not updated yet
      |
Developer modifies .reloadtrigger on the classpath
      |
      +-- Devtools inspects accumulated changes
      |
      +-- If restart-worthy changes exist: close/restart context
      +-- Otherwise: no restart needed
```

**Think of the trigger file as "check now", not "force restart unconditionally".** If you only edited an excluded static resource, the context will not restart even after touching the trigger file; that is the expected outcome of the exclusion policy.

### 5.3. Source and Output Are Two Different Locations

With Maven:

```text
src/main/resources/.reloadtrigger     <-- source
              |
              | Maven resources:resources / compile
              v
target/classes/.reloadtrigger         <-- runtime classpath output
              |
              +-- Devtools watcher looks here
```

Editing only the source file without the IDE/build tool **copying it into output** prevents Devtools from observing any trigger update. When debugging, verify the file actually exists at `target/classes/.reloadtrigger` (or the equivalent output directory).

**Touching the file must change its timestamp or content enough for the watcher to detect it**. On filesystems with coarse timestamp resolution, appending a new marker to its content can be more reliable than rapid `touch` commands.

### 5.4. Can a Global Trigger File Be Used?

In personal development setups, Spring Boot Devtools supports global settings to apply a trigger file across multiple projects. This helps when the IDE auto-builds, though remember: each application still needs the trigger file on **its own classpath** and updated via its active build workflow.

Do not enable or customize global settings and forget they affect other projects, making developers think restart broke. For reproducible demos, set the property per project first.

## 6. Combining All Three Configurations

A complete development configuration:

```properties
spring.application.name=devtools-watch-demo
server.port=8080

# Keep default exclusions and append a few generated files.
spring.devtools.restart.additional-exclude=generated/**,**/*.tmp

# Also watch a sibling directory next to the project (local example).
spring.devtools.restart.additional-paths=../local-dev-watch

# Only check for restart when the marker is updated.
spring.devtools.restart.trigger-file=.reloadtrigger

# Optionally enable LiveReload for the development environment.
spring.devtools.livereload.enabled=true
```

**This is a local-environment example, not production properties.**

Meaning of this setup:

1. Java/classes change and compile to the classpath -> watched, waiting on the trigger file to evaluate restart.
2. Static resources are excluded from full restart by default -> can trigger LiveReload or show changes on refresh once output updates.
3. Files in `generated/**` and `*.tmp` files also do not force a full restart under policy.
4. `../local-dev-watch` is watched despite being outside the classpath; triggering a restart from edits there still obeys the trigger-file policy.
5. Touch the trigger file on the classpath -> Devtools checks meaningful pending changes and restarts the context if needed.

### 6.1. Prediction Table

| Action While App Is Running | Watched Location Updated? | Trigger Updated? | Expected Observation |
| --- | --- | --- | --- |
| Edit `.java` only without compiling | No new `.class` yet | No | Typically no restart |
| Edit `.java`, Maven compile | Yes | No | Waits for trigger |
| Edit `.java`, compile, then update classpath trigger | Yes | Yes | Restarts if real restart-worthy changes exist |
| Edit static file and copy resources | Yes | No | No full restart per defaults; LiveReload may fire |
| Update only trigger with no other changes | Trigger changed | Yes | Checks only; restart not guaranteed |
| Edit `../local-dev-watch/marker.txt` | Yes, via `additional-paths` | No | Waits for trigger |
| Edit a file outside classpath not in `additional-paths` | No | Yes | Does not restart just from that external edit |
| Disable Devtools restart completely | Watcher inactive | Yes | Do not expect auto-restart |

This table reflects standard Spring Boot 3.3 mechanics. Exact LiveReload outcomes depend on the browser extension, resource copying, pattern matchers, watcher state, and build/IDE setup.

## 7. Sample Project: Java 21 + Spring Boot 3.3.13

The project uses Maven with two Java classes and a few resources. The app exposes `GET /hello` returning `v1`; each time the application context completes startup successfully, it prints a `DEMO READY at ...` marker to observe restarts.

### 7.1. Project Structure

```text
devtools-watch-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/devtools/
    │   │   ├── DevtoolsWatchApplication.java
    │   │   └── StatusController.java
    │   └── resources/
    │       ├── application.properties
    │       ├── .reloadtrigger
    │       └── static/
    │           └── message.txt
    └── test/
        └── java/com/example/devtools/
            └── StatusControllerTest.java

# Outside the project, create before running:
../local-dev-watch/marker.txt
```

### 7.2. Maven pom.xml

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
    <artifactId>devtools-watch-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-devtools</artifactId>
            <scope>runtime</scope>
            <optional>true</optional>
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

`runtime` ensures Devtools is present when running in development rather than a library for compiling business code. `optional=true` prevents Devtools from propagating transitively to projects depending on this module.

**Important:** Spring Boot Maven repackaging excludes `spring-boot-devtools` from executable JARs by default; when running a packaged `java -jar`, Devtools is typically disabled via production-mode detection. To practice restarts, use `mvn spring-boot:run` or an IDE launch with exploded classes rather than relying on `java -jar target/...jar`.

### 7.3. DevtoolsWatchApplication.java

File `src/main/java/com/example/devtools/DevtoolsWatchApplication.java`:

```java
package com.example.devtools;

import java.time.Instant;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class DevtoolsWatchApplication {

    public static void main(String[] args) {
        SpringApplication.run(DevtoolsWatchApplication.class, args);
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("DEMO READY at " + Instant.now());
    }
}
```

The event handler in a Spring-managed bean is invoked when Boot publishes `ApplicationReadyEvent`. A Devtools restart creates a new context and emits a fresh startup event sequence; the log appears multiple times with different timestamps. **The timestamp is dynamic**, so do not hardcode a single date/time as expected output.

This ready marker lets you observe **application context startup/restart**; it does not prove all external dependencies or async work in a production app are healthy.

### 7.4. StatusController.java

File `src/main/java/com/example/devtools/StatusController.java`:

```java
package com.example.devtools;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatusController {

    @GetMapping("/hello")
    public String hello() {
        return "v1";
    }
}
```

Later you just change `"v1"` to `"v2"`, compile onto the classpath, and update the trigger. If a restart occurs, the next `GET /hello` call will return `v2`.

### 7.5. application.properties

File `src/main/resources/application.properties`:

```properties
spring.application.name=devtools-watch-demo
server.port=8080
spring.devtools.restart.additional-exclude=generated/**,**/*.tmp
spring.devtools.restart.additional-paths=../local-dev-watch
spring.devtools.restart.trigger-file=.reloadtrigger
spring.devtools.livereload.enabled=true
```

Note: in this project we **do not set `spring.devtools.restart.exclude`** so default exclusions remain intact. If you want to test overriding them, try setting that property in a separate run and compare behavior.

### 7.6. .reloadtrigger

File `src/main/resources/.reloadtrigger`:

```text
initial
```

The content can be any text; what matters is that **the filename matches the property** and **the file appears on the runtime classpath**. No Java class is needed for the marker.

### 7.7. message.txt

File `src/main/resources/static/message.txt`:

```text
static-v1
```

This static file is served by the Spring Boot web app at `GET /message.txt`. Try editing it to `static-v2`, copying resources to output, and refreshing the browser; this case helps distinguish static resource updates from full context restarts.

### 7.8. Creating the Additional Watched Directory

Inside `devtools-watch-demo`, on Bash/zsh:

```bash
mkdir -p ../local-dev-watch
printf 'marker-v1\n' > ../local-dev-watch/marker.txt
```

Or PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path ../local-dev-watch
Set-Content -Path ../local-dev-watch/marker.txt -Value 'marker-v1'
```

The directory must exist **before the initial startup**. The relative path works when the working directory is the project root; launching from an IDE may require adjusting the working directory accordingly.

## 8. Running the Demo and Testing the Three Mechanisms

### 8.1. Preparing Classpath Output

In the project, using terminal A:

```bash
java -version
mvn -version
mvn -q compile
mvn spring-boot:run
```

When running, the standard Maven plugin uses the project's classes/resources rather than a repackaged executable JAR. Wait for the application to start; in the console you will see a marker like:

```text
DEMO READY at 2026-01-01T00:00:00Z
```

This is a **format example**, not a fixed timestamp. During an actual run, the time comes from `Instant.now()`.

In terminal B:

```bash
curl -sS http://localhost:8080/hello
curl -sS http://localhost:8080/message.txt
```

The first two response bodies are respectively:

```text
v1
static-v1
```

These two outputs are from **two separate requests**, not a single two-line response. `curl` may print them back-to-back without a newline if you run both commands consecutively; inspect each command separately when needed.

### 8.2. Ensuring the Trigger File Is on the Classpath

With Maven, after `mvn compile`, the expected path is:

```text
target/classes/.reloadtrigger
```

Check with Bash:

```bash
test -f target/classes/.reloadtrigger && echo present
```

or PowerShell:

```powershell
Test-Path target/classes/.reloadtrigger
```

If `false`/missing, do not continue assuming the trigger file works. Ensure Maven resources copied the file from `src/main/resources`, verify the running JVM's classpath output directory, and rebuild if needed.

### 8.3. Editing Java Without Updating the Trigger

While the app is running in terminal A:

1. Open `StatusController.java`.
2. Change `return "v1";` to `return "v2";`.
3. Compile the new class in terminal B:

```bash
mvn -q compile
```

4. Watch the logs in terminal A and call `GET /hello` again.

With the demo's trigger file config, the classpath change is recorded, yet Devtools **waits for the marker to update before evaluating a restart**. Thus the app keeps serving old code `v1` until the marker updates.

**Potential confusion:** other live/hot-reload systems (IDE hot swap, JRebel, or special plugins) can update method bodies without a Spring restart. If your environment has those enabled, turn them off for this experiment so you observe only Devtools.

### 8.4. Explicitly Triggering the Restart Check

After compiling Java and confirming `target/classes/.reloadtrigger` exists, in terminal B on Bash:

```bash
printf '\ntrigger %s\n' "$(date +%s)" >> src/main/resources/.reloadtrigger
mvn -q resources:resources
```

The first command updates the source marker; the second Maven command copies the updated marker to the output classpath. Once Devtools sees both the changed `.class` and the updated marker, it performs the restart. Watch the console: a new `DEMO READY at ...` marker appears.

A faster diagnostic shortcut **for local demos only** is editing the marker directly in the classpath output:

```bash
printf '\ncheck-now\n' >> target/classes/.reloadtrigger
```

However, edits directly in `target/classes` can be overwritten on the next build; normally edit source and let the IDE/Maven copy resources.

Once the restart finishes:

```bash
curl -sS http://localhost:8080/hello
```

Expected response body:

```text
v2
```

This simultaneously verifies that the new Java code compiled, the trigger worked, and the new application context is serving requests.

### 8.5. Testing Static Resources Without a Full Restart

Change `src/main/resources/static/message.txt` from `static-v1` to `static-v2`, then:

```bash
mvn -q resources:resources
curl -sS http://localhost:8080/message.txt
```

Once classpath output updates and static serving does not cache the old copy, the result is:

```text
static-v2
```

Thanks to the default `static/**` exclusion, this resource change **does not require a full Spring context restart**. A LiveReload client can auto-refresh the browser; without one, refresh manually. With a trigger file configured, do not expect a static file change to emit a new `DEMO READY`.

If the static file still returns `static-v1`, check resource copying, browser/proxy caching, and classpath output before changing exclusion policies.

### 8.6. Testing additional-paths

Edit the file outside the project:

```bash
printf 'marker-v2\n' > ../local-dev-watch/marker.txt
```

At this point Java classes and static resources have not changed. With `trigger-file` active, **do not expect an external marker edit to restart immediately**. After updating the trigger file on the classpath, Devtools checks pending changes:

```bash
printf '\ncheck-external\n' >> target/classes/.reloadtrigger
```

Watch the console to see whether the change in `../local-dev-watch` caused a context restart. If not, verify working directory, directory existence, actual watched path, exclusions, scanner timing, and marker updates; never assume `additional-paths` turns files into beans or configs automatically.

A cleaner test is modifying the external marker once more and then updating the trigger file after the IDE/build settles, avoiding overlapping changes within a single watcher scan window.

### 8.7. Testing additional-exclude

Create a generated-style resource under classpath resources (if not already present):

```bash
mkdir -p src/main/resources/generated
printf 'report-v1\n' > src/main/resources/generated/report.txt
mvn -q resources:resources
```

With `spring.devtools.restart.additional-exclude=generated/**,**/*.tmp` and the trigger file active, edit `report.txt`, copy it to classpath output, and update the trigger to check for restart. Expected result: changes in the excluded group **do not force a full restart**, while LiveReload may still fire depending on the environment.

**Do not use this case to claim Java code failed to restart**: `generated/report.txt` is a resource that does not affect bean instantiation. To verify a full restart, edit `StatusController.java` as in Section 8.3.

### 8.8. Windows PowerShell Equivalent

When using Windows PowerShell, after editing `StatusController.java` and compiling:

```powershell
mvn -q compile

Add-Content -Path src/main/resources/.reloadtrigger -Value ("trigger " + (Get-Date).ToString("O"))
mvn -q resources:resources

Invoke-RestMethod http://localhost:8080/hello
```

In the default Maven setup, the source trigger must be copied to output. If your build/IDE uses a different output folder, update the file **on the actual runtime classpath** rather than assuming `target/classes` in every scenario.

## 9. JUnit Testing the Application

JUnit can test controllers, contexts, and request mappings. However, a standard `@SpringBootTest` **does not prove** Devtools file-watcher/restart works with an IDE, classpath output, or trigger file in a long-running process. Many test runners even disable Devtools restart via test mechanisms.

### 9.1. StatusControllerTest.java

File `src/test/java/com/example/devtools/StatusControllerTest.java`:

```java
package com.example.devtools;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class StatusControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void helloReturnsVersionOne() throws Exception {
        mvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("v1"));
    }
}
```

Run while `StatusController.java` still returns `v1`:

```bash
mvn test
```

This test checks HTTP controller wiring without opening a real port. If you already changed the controller to `v2` for the restart experiment, update the expected string in the test accordingly or revert the source before running tests.

**Do not** treat a MockMvc test as a substitute for testing the Devtools watcher: a unit/integration test only runs a context in the test process and does not test the "file edit -> compile -> trigger -> restart" cycle on a running app.

### 9.2. Reliable Restart Test Scenario

To verify Devtools works, run a long-lived process test (manual or controlled integration automation):

1. Start via `mvn spring-boot:run` or an IDE run with exploded classes.
2. Record the initial `DEMO READY` marker/timestamp.
3. Change code `v1` -> `v2`.
4. Compile and verify classpath output updated.
5. **Without** touching the trigger, observe the context has not restarted for that change.
6. Update the trigger on the output classpath.
7. Observe the new `DEMO READY` marker and HTTP returning `v2`.
8. Test a static resource separately, confirming no full restart is needed.
9. Test the external folder with `additional-paths`.
10. Restore the project to its initial state after the experiment.

Never use an arbitrary `Thread.sleep(500)` and assume restart finished; if automating, poll readiness/HTTP responses with a **bounded deadline** and verify timestamps/events clearly. File-watcher debounce/scan intervals and CPU/IDE speed can vary.

## 10. Overriding Exclusions vs. Appending Exclusions: Before/After Cases

### 10.1. Nothing Set

```properties
# Neither restart.exclude nor additional-exclude is set.
```

Default groups such as static/public/templates are excluded from full restarts.

### 10.2. Setting Only exclude

```properties
spring.devtools.restart.exclude=static/**,public/**
```

Now `templates/**` is **no longer necessarily** a default exclusion. This can cause restarts when editing templates that previously only needed LiveReload.

### 10.3. Adding additional-exclude

```properties
spring.devtools.restart.additional-exclude=generated/**,**/*.tmp
```

Default exclusions are preserved, with generated/temp groups added on top.

### 10.4. Setting Both

```properties
spring.devtools.restart.exclude=static/**,public/**
spring.devtools.restart.additional-exclude=generated/**
```

The policy starts from `static/**,public/**` and appends `generated/**`. Do not mistakenly assume `additional-exclude` silently restores `templates/**`.

### 10.5. When Is Excluding a File Wrong?

Suppose `src/main/resources/application.properties` contains:

```properties
my.feature.enabled=false
```

If a custom service reads that property during bean initialization, changing the property while **excluding it from restart** leaves the service holding the old value. Never treat critical configuration files like static image files served straight to the browser.

**Selection criterion:** only exclude files whose updates **do not require recreating the ApplicationContext/beans** to take effect. Images, CSS, and templates supported by engine reloading are good candidates; config initialization files and `.class` files should not be excluded carelessly.

## 11. Devtools Restart Is Not Production Hot Deployment

### 11.1. Devtools Does Not Run from Packaged Executable JARs by Default

With the Maven plugin, executable archives normally **exclude Devtools**. Spring Boot also detects apps launched with `java -jar`: it treats them as production-like launches and disables Devtools by default.

Therefore, a flawed way to test this topic is:

```bash
mvn package
java -jar target/devtools-watch-demo-0.0.1-SNAPSHOT.jar
# Edit Java and expect the JAR to auto-restart like an IDE.
```

You are running a packaged artifact; classes inside the JAR do not swap themselves just because source files were saved. To test the file watcher, run `mvn spring-boot:run` or launch from your IDE in development mode.

### 11.2. Never Re-Enable Devtools via System Property in Production

There are ways to force Devtools active even under other classloaders, yet Spring Boot documentation warns of security risks when enabling it in production. Never use that as a substitute for rolling deployments or blue-green releases.

Devtools includes development-time defaults and LiveReload; these must not be treated as hardening, cluster deployment, or secret management.

### 11.3. Restart Recreates the Context Instead of Preserving All In-Memory State

In-flight requests, scheduled jobs, or streams may be disrupted when Devtools restarts the context. During development, verify the old context cleans up properly: `@PreDestroy`, `SmartLifecycle.stop`, and shutdown hooks. Devtools relies on the Spring application context shutdown hook for restarts; disabling the hook can break restart behavior.

Do not use Devtools restart to test exactly-once guarantees in production. Critical jobs require transactions, outbox/queue patterns, and retries/idempotency.

## 12. Distinguishing File-Watching from Restart Classloader Customization

Two configuration groups both contain `exclude` yet solve **different problems**.

### 12.1. Excluding Watched Resource Changes

```properties
spring.devtools.restart.additional-exclude=generated/**
```

Belongs to the application properties namespace. Meaning: changes to matching resources **do not force a full restart** under policy.

### 12.2. Customizing Base/Restart Classloaders

`META-INF/spring-devtools.properties` can contain `restart.include.*` and `restart.exclude.*` entries to assign **classpath entries/JARs** to the base or restart classloader. These patterns are **regular expressions** applied to classpath entries, **not** the file-watcher exclusion patterns above.

Illustrative example (no need to add to the demo):

```properties
restart.include.project-common=.*/project-common-[^/]+\.jar
```

This is purely a regex syntax example in `spring-devtools.properties`—**never** copy it into `application.properties` expecting it to act like `spring.devtools.restart.additional-exclude`.

When encountering `ClassCastException`, reflection mismatches, or deserialization errors due to two classloaders, first confirm restart is the cause before customizing classloaders. Do not add unnecessary include/exclude regexes for a problem that is just static file reloading.

## 13. Tuning the File Watcher in Slow Build Environments

When an IDE builds/copies batches of files over several seconds, Devtools may observe multiple waves of changes. The goal is to avoid restarting while output is still unstable.

Advanced Devtools watcher settings:

```properties
spring.devtools.restart.poll-interval=2s
spring.devtools.restart.quiet-period=1s
```

These are **tuning examples**; pick durations with a clear rationale. Poll interval controls how often changes are checked; quiet period is the calm window required to avoid restarting mid-copy.

If the quiet period is shorter than the time Maven/IDE takes to copy resources, the app can restart while files are still out of sync. If it is too long, restarts feel sluggish. Using a trigger file can cut down restarts caused by IDE auto-build, though you should still observe actual behavior on your filesystem and build tool.

**Do not try fixing every no-restart problem by raising poll intervals**: first verify Devtools is active, the classpath truly changed, the trigger file exists, exclusion policies allow it, and the output path is right.

## 14. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Edit `.java`, app does not restart | New `.class` not compiled yet | IDE Build / `mvn compile` |
| Compiled yet still no restart | Trigger file enabled but unchanged | Update the marker on the classpath |
| Touched marker yet no restart | No restart-worthy changes or file not in output | Check compiled classes, exclusions, `target/classes` marker |
| Editing static CSS restarts whole context | Overrode defaults with overly narrow `restart.exclude` | Use `additional-exclude` instead of `exclude` when only adding |
| File outside classpath does not restart | Not in `additional-paths` or wrong relative path vs. working dir | Check actual path, permissions, and file watcher |
| Added `additional-paths` yet Java does not read file | Watcher does not add files to classpath/config automatically | Define explicit file-loading config |
| No LiveReload seen | Missing LiveReload browser client, output unchanged, LiveReload server inactive | Check extension/network/manual refresh |
| Static file stays on old version | IDE/Maven did not copy resource or browser cache | Copy resources, inspect output, refresh/clear cache |
| `java -jar` does not auto-restart | Devtools disabled in packaged apps | Use Maven run or IDE dev launch |
| `@SpringBootTest` passes yet restart still fails | Test does not exercise the watcher in a long-lived process | Test restart via a real process with a deadline |
| Devtools restarts continuously | Watched directory contains constantly changing generated/log files | Exclude accurately or narrow `additional-paths` |
| Config variable does not update when excluded | Bean reads file only at startup | Do not exclude that config; allow restart |
| Trigger exists only in `src/main/resources` | Not copied into runtime classpath | Run `mvn resources:resources` and check output |
| Trigger file setting includes a path | Property expects a filename, not a source path | `spring.devtools.restart.trigger-file=.reloadtrigger` |
| Multi-module `ClassCastException` after restart | Class loaded in wrong base/restart classloader | Diagnose classloaders, customize `spring-devtools.properties` if needed |
| Shutdown hook disabled | Devtools restart cannot close context properly | Restore hook or review lifecycle management |
| Unsure if a real restart occurred | Looking only at browser refresh | Watch `ApplicationReadyEvent` or lifecycle logs |
| Trigger file restarts with no code change | Other watched changes were already queued | Check watched directories, generated files, and logs |
| Exclusions too broad | New beans/configs fail to take effect | Narrow patterns and test by group |
| Shipping devtools to production | Security and operational risk | Keep in development-only runtime |

### 14.1. Diagnostic Checklist

1. Is `spring-boot-devtools` on the **runtime** classpath of the dev launch?
2. Is the app running from IDE/`mvn spring-boot:run` rather than packaged `java -jar`?
3. Is restart disabled via `spring.devtools.restart.enabled=false` or a system property?
4. Was the source file compiled/copied into a file on the classpath?
5. Is the actual classpath output `target/classes` or another directory?
6. Does the modified file fall under default exclude patterns?
7. Was `restart.exclude` set, unintentionally overriding defaults?
8. Should `restart.additional-exclude` be used instead of `exclude`?
9. Does `additional-paths` point to an existing folder matching the working directory?
10. Is the external directory actually seeing real changes via the watcher?
11. Is `trigger-file` strictly a **filename**?
12. Does the marker exist on the runtime classpath and has it been updated?
13. When the trigger changed, were **restart-worthy** changes pending?
14. Are Maven/IDE outputs written in waves exceeding the quiet period?
15. Are LiveReload client and browser refreshes being confused with context restarts?
16. Are generated/logs/cache directories causing overly frequent watcher activity?
17. Is JRebel/AspectJ instrumentation or a classloader incompatibility present?
18. Is the Spring shutdown hook still registered?
19. Did a new `DEMO READY` log appear after the action?
20. Does testing the same steps on a minimal demo eliminate confounding factors?

## 15. Practice Exercises

1. Explain the difference between saving a `.java` file and updating `.class` on the classpath.
2. Name the six directory groups Devtools excludes from forcing a full restart by default.
3. Compare `spring.devtools.restart.exclude` and `spring.devtools.restart.additional-exclude`.
4. Why can setting `restart.exclude=static/**,public/**` cause template edits to trigger restarts?
5. Choose a policy for a project with static CSS, Thymeleaf templates, and generated JSON.
6. Explain why watcher exclusions do not remove files from the executable JAR.
7. Create `../local-dev-watch` outside the project and configure `additional-paths`.
8. Why does the watcher seeing a file outside the classpath not mean Spring loads it into the `Environment`?
9. Create `.reloadtrigger` in `src/main/resources` and configure `trigger-file` properly.
10. Why does the `trigger-file` property take a filename rather than a source path?
11. Why must you verify the marker was copied into `target/classes`?
12. After changing the controller from v1 to v2 and compiling without touching the trigger, what do you expect?
13. Touch the trigger after compiling; what proves the context restarted?
14. Edit only `static/message.txt` and copy output; must the context restart?
15. When no restart-worthy changes exist, does touching the trigger force a restart?
16. Test an external path with `additional-paths` and a trigger; record your observations.
17. Why is adding the entire `target` directory to `additional-paths` usually a bad idea?
18. Write a JUnit MockMvc test for `GET /hello` and explain why that test does not prove file watching works.
19. Configure exclusions to keep defaults while ignoring `generated/**` and `*.tmp`.
20. When JRebel is enabled, how does Devtools restart interact with it?
21. When using `mvn spring-boot:run`, why must the plugin run with proper forking?
22. Describe a scenario where browser LiveReload succeeds yet the Spring context did not restart.
23. Distinguish `spring.devtools.restart.additional-exclude` from `restart.exclude.X` in `META-INF/spring-devtools.properties`.
24. If the app runs fine yet `java -jar` alone does not restart, what is the likely reason?
25. Design a deadline-based restart test procedure without relying on `Thread.sleep` as proof of completion.
26. Why should Devtools not be enabled in production to auto hot-deploy source edits?
27. If the watcher restarts continuously due to log files, how would you fix the policy and directory scope?
28. Explain the effect of `poll-interval` and `quiet-period` when an IDE copies files slowly.
29. If a resource is excluded yet a bean reads it only at initialization, when does a new value take effect?
30. Build a test matrix covering Java class changes, static file changes, `additional-path` changes, and trigger-only changes.

**Completion criteria:** properly configure `exclude`/`additional-exclude`, `additional-paths`, and `trigger-file` on Spring Boot 3.3; run the Maven demo; prove restarts occur only after classpath updates and trigger changes; distinguish LiveReload from full restarts; keep Devtools out of production.

## 16. Official References

- Spring Boot 3.3 — Developer Tools: https://docs.spring.io/spring-boot/3.3/reference/using/devtools.html
- Spring Boot 3.3 — Automatic Restart, Excluding Resources, Watching Additional Paths, Using a Trigger File: https://docs.spring.io/spring-boot/3.3/reference/using/devtools.html#using.devtools.restart
- Spring Boot 3.3 — Devtools application properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html
- Spring Boot 3.3 — Maven plugin, Running Your Application: https://docs.spring.io/spring-boot/3.3/maven-plugin/run.html
- Spring Framework 6.1 — ApplicationReadyEvent (Spring Boot API): https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html
