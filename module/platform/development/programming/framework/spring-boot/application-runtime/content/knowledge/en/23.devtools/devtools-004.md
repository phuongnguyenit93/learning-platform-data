# Classpath Change Detection Conditions and Recompilation Requirements in Spring Boot Devtools

## 1. Objective and Common Pitfall

When developing a Spring Boot application, we normally want to edit code and immediately see the new behavior without manually stopping and restarting the server. **Spring Boot Devtools** provides an **automatic restart** mechanism to shorten this feedback loop. However, a common misconception is:

> "I saved the Java file in my IDE—why didn't Spring Boot restart automatically?"

The core answer: **Devtools watches changes to entries on the runtime classpath**, especially classpath entries pointing to **directories**. It **does not act as a Java compiler** and does not by default watch every source file in `src/main/java` directly.

For a Java code change to be detected by Devtools, it typically goes through this chain:

~~~mermaid
flowchart LR
    A["Edit .java"] --> B["Save source code"]
    B --> C["IDE / Maven / Gradle compiles"]
    C --> D[".class file on runtime classpath is updated"]
    D --> E["Devtools FileSystemWatcher detects change"]
    E --> F["Wait quiet period"]
    F --> G["Close old ApplicationContext and restart"]
    G --> H["New context uses new bytecode"]
~~~

If you stop at **saving `.java`** and the compiler has not written `.class` to the path the running application uses, there is **no observable classpath update** to trigger a standard restart.

This lesson explains **what actually triggers a restart**, how to spot a missing compile step, the difference between classpath and source code, exclude/trigger-file/watcher configuration, how restart differs from LiveReload, and provides a runnable **Java 17+ / Spring Boot 3.5.x** project to experiment with.

## 2. What Does Classpath Mean in Devtools Experiments?

The **classpath** is the set of directories and JARs the JVM uses to locate application classes and resources. Not every directory in a project is automatically on the runtime classpath.

In Maven, a typical layout is:

~~~text
my-project/
├── pom.xml
├── src/
│   └── main/
│       ├── java/com/example/demo/
│       │   ├── DemoApplication.java
│       │   └── RevisionController.java
│       └── resources/
│           ├── application.properties
│           └── static/notice.txt
└── target/
    └── classes/
        ├── com/example/demo/
        │   ├── DemoApplication.class
        │   └── RevisionController.class
        ├── application.properties
        └── static/notice.txt
~~~

During a typical development run via `mvn spring-boot:run`:

- `src/main/java/.../RevisionController.java` is the **source** read by the compiler.
- `target/classes/.../RevisionController.class` is the **compiled bytecode**.
- `src/main/resources/application.properties` is the **resource source**.
- `target/classes/application.properties` is the **copied resource** in the output classpath.
- Dependency JARs from the Maven repository are separate classpath entries, typically loaded by another classloader layer.

Devtools looks at **the actual paths on the running process's classpath**. Modifying a source file alone does not mean the running process sees new bytecode or resources.

### With Gradle and IDEs

Gradle typically outputs to locations such as:

~~~text
build/classes/java/main/
build/resources/main/
~~~

IDEs may use `out/production/...`, `bin/main/...`, `target/classes`, or output managed by the build tool. Do not assume one path is right for every IDE configuration. Verify by checking the **run configuration**, the running process's classpath, and output file timestamps/hashes after compiling.

### "Classpath Entry Is a Directory" Matters

According to Spring Boot 3.5 docs, **by default Devtools monitors classpath entries pointing to directories**. That is why apps running from exploded classes during development work with restart. It **does not operate as a mechanism that swaps bytecode inside a JAR already loaded by the JVM**.

For a **fully packaged** application run with `java -jar target/app.jar`, Spring Boot treats it as a production-style launch and **Devtools automatically disables devtools features**, unless intentionally overridden in a way that should never be used in production.

## 3. Prerequisites for Automatic Restart to Actually Work

We can break this down into the following conditions:

| Condition | Why It Is Needed | If Not Met |
| --- | --- | --- |
| `spring-boot-devtools` dependency in development runtime | Provides the restart watcher and restart classloader | No Devtools restart mechanism |
| Launched in development mode with a classes directory | Gives Devtools a runtime classpath directory to watch | Packaged JARs normally do not activate devtools |
| `spring.devtools.restart.enabled` not turned off | Allows restart/watcher to operate | Classpath changes will not trigger restart |
| File **actually changes on the watched classpath** | This is the trigger signal | Editing `.java` alone is insufficient if `.class` does not change |
| File not excluded from **full restart** | Default excludes typically only trigger LiveReload | No restart even though the resource updated |
| Not blocked by a trigger-file gate | With a trigger file, restart checks wait for the trigger to change | Compiling without touching the trigger does not restart |
| Watcher has polling + quiet period time | Prevents restarting while the compiler is still writing multiple files | Restart may be delayed or fire mid-batch |
| Proper lifecycle/context shutdown | Devtools must close the old context to re-initialize | Can fail if shutdown hook is disabled or custom lifecycle blocks |
| Forking remains enabled when using build plugins | Needed for an isolated application classloader | Disabling forking can break restart behavior |
| Not using incompatible technologies | E.g. AspectJ weaving per Devtools documentation | Restart may be unsupported |

These are **practical conditions**, not a promise that Devtools will definitely restart under every compiler, classloader setup, or filesystem. Always verify the actual launch path and logs.

## 4. Why Saving a .java File Is Usually Not Enough

Suppose `RevisionController.java` source currently contains:

~~~java
return "v1";
~~~

You edit it to:

~~~java
return "v2";
~~~

Yet the compiler has not run. The old `RevisionController.class` file in the output classpath still holds the previous version's bytecode. As the process continues loading classes from old bytecode, Devtools **cannot infer Java logic changes** from a source file outside the classpath.

The usual required step is:

~~~bash
mvn compile
~~~

Or building in the IDE so `.class` output updates. If Maven/IDE sees unchanged code or skips recompiling for some reason, the compile command can succeed yet **produce no classpath file changes**, resulting in no new restart.

### Plain Java 17 Example: Source vs. Compiled Class

We can prove this mechanism **without Spring Boot**.

Create **`SourceVsBytecode.java`**:

~~~java
public class SourceVsBytecode {
    public static void main(String[] args) {
        System.out.println("BYTECODE_V1");
    }
}
~~~

Run:

~~~bash
javac -d out SourceVsBytecode.java
java -cp out SourceVsBytecode
~~~

Output:

~~~text
BYTECODE_V1
~~~

Now **edit only `SourceVsBytecode.java`**: change the literal to `"BYTECODE_V2"`, save it, but **do not compile**. Run again:

~~~bash
java -cp out SourceVsBytecode
~~~

Output is still:

~~~text
BYTECODE_V1
~~~

Next:

~~~bash
javac -d out SourceVsBytecode.java
java -cp out SourceVsBytecode
~~~

Output:

~~~text
BYTECODE_V2
~~~

This is deterministic once you change the literal and compile successfully. Devtools operates on the same **bytecode/resource files the JVM actually uses**; the difference is that Devtools has a watcher to detect those changes and re-initialize the Spring context automatically.

## 5. Maven Dependency and Packaging Notes

Use in `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
~~~

`optional=true` is how Spring Boot instructs Maven so devtools **does not propagate transitively as a required dependency** to other modules depending on this artifact. With Gradle:

~~~groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

This Gradle block is a **snippet**, requiring a matching `build.gradle`, plugins, and dependency management.

### Why Keep Devtools Out of Production?

- Devtools is meant for development by default and applies developer-oriented property defaults, such as disabling caches for certain template engines.
- Automatic restart, LiveReload, and remote tools are not needed in a production runtime.
- Forcing Devtools on inside a production JAR can introduce **security and lifecycle risks**.
- A JAR repackaged by Spring Boot typically **excludes Devtools by default**.

Do not assume that because `pom.xml` lists devtools, `java -jar` must show `restartedMain` or auto-restart when editing source. Those are **two different launch modes**.

## 6. Runnable Spring Boot 3.5.16 / Java 17+ Project

This example creates an endpoint to easily observe `ApplicationContext` creation and code versions.

Requirements:
- Java 17+;
- Maven 3.6+ or a compatible installed version;
- Spring Boot **3.5.16**;
- Spring Web;
- Spring Boot Devtools in development runtime.

Structure:

~~~text
devtools-classpath-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/devtools/
    │   ├── DevtoolsClasspathApplication.java
    │   └── RevisionController.java
    └── resources/
        ├── application.properties
        └── static/notice.txt
~~~

### 6.1 pom.xml

~~~xml
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
    <artifactId>devtools-classpath-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
            <artifactId>spring-boot-devtools</artifactId>
            <optional>true</optional>
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

### 6.2 src/main/resources/application.properties

~~~properties
spring.application.name=devtools-classpath-demo
server.port=18086

demo.message=hello

# Only used to clearly observe the watcher in the lab.
spring.devtools.restart.poll-interval=2s
spring.devtools.restart.quiet-period=1s
~~~

The `2s` and `1s` values are chosen by this lesson, not defaults. Polling/quiet period affects **detection latency** after compilation; it does not replace compilation.

### 6.3 src/main/java/com/example/devtools/DevtoolsClasspathApplication.java

~~~java
package com.example.devtools;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DevtoolsClasspathApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                DevtoolsClasspathApplication.class, args);
    }
}
~~~

### 6.4 src/main/java/com/example/devtools/RevisionController.java

~~~java
package com.example.devtools;

import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RevisionController {

    private final String instanceId =
            UUID.randomUUID().toString();

    private final String message;

    public RevisionController(
            @Value("${demo.message:default}") String message) {
        this.message = message;
    }

    @GetMapping(value = "/revision", produces = "text/plain")
    public String revision() {
        return "v1|" + message + "|" + instanceId;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("LAB_READY version=v1"
                + " message=" + message
                + " instance=" + instanceId);
    }
}
~~~

**Why include `instanceId`?** Whenever Spring creates a new `RevisionController`, it generates a new UUID. When Devtools **restarts successfully and creates a new context**, the endpoint returns a different UUID. The UUID helps observe instance/context recreation, though it does not represent a **PID**: Devtools restarts the context/classloader **within the same JVM**, without launching a new process.

There is no business reason to embed such a UUID in production controllers; it is purely an experimental marker.

### 6.5 src/main/resources/static/notice.txt

~~~text
NOTICE_V1
~~~

This static file illustrates that resource updates can be served anew **without a full restart** under default exclusions. It does not involve the Java compiler.

### 6.6 Build Before the First Run

In the directory containing `pom.xml`:

~~~bash
mvn -q -DskipTests compile
~~~

Maven compiles sources into `target/classes` and copies `src/main/resources` into the corresponding output per the build lifecycle.

**Run in Terminal A and leave the process running:**

~~~bash
mvn spring-boot:run
~~~

Per Devtools docs, when using Maven/Gradle build plugins for restarts, keep **forking enabled**. Do not disable forking in plugin configuration. `spring-boot:run` launches the app from development classpath entries, unlike running a packaged JAR.

Terminal A may display Devtools info or restart-related thread names; **do not write brittle assertions** against internal log text of a specific plugin version.

### 6.7 Query Endpoints in Terminal B

~~~bash
curl -fsS http://127.0.0.1:18086/revision
curl -fsS http://127.0.0.1:18086/notice.txt
~~~

The first response has the form:

~~~text
v1|hello|<actual-run-uuid>
~~~

The line above is a **structural template**, not a fixed literal output because the UUID is randomly generated. The second response is **literally**:

~~~text
NOTICE_V1
~~~

In the logs, a line printed by our code starts with:

~~~text
LAB_READY version=v1 message=hello instance=
~~~

followed by the UUID after the final `=`. Framework logs may interleave; this is simply a reliable prefix from the demo code.

## 7. Experiment A: Edit .java Without Compiling

In Terminal A, **leave** `mvn spring-boot:run` running.

Open `src/main/java/com/example/devtools/RevisionController.java` and change only:

~~~java
return "v1|" + message + "|" + instanceId;
~~~

to:

~~~java
return "v2|" + message + "|" + instanceId;
~~~

Also update `"LAB_READY version=v1"` to `"LAB_READY version=v2"` so log output stays consistent.

**Only save the source file—do not click Build Project and do not run `mvn compile`.**

If your IDE has **auto-build/auto-compile disabled**, `target/classes/RevisionController.class` still holds the old version, so `curl /revision` still returns the prefix:

~~~text
v1|hello|
~~~

with no bytecode-triggered restart.

**If your IDE automatically compiles on Save**, you **may already see a restart**. This does not contradict the classpath rule: Devtools saw the `.class` updated by the IDE. To test "save without compile" in isolation, temporarily disable auto-build or verify that the output class timestamp/hash has not changed.

## 8. Experiment B: Compile to Update the Classpath

Leave Terminal A running, open **Terminal C** in the same project:

~~~bash
mvn -q -DskipTests compile
~~~

In this experiment, because you edited the source, the compiler writes new bytecode into `target/classes`. Once the watcher sees the classpath directory change and the quiet period ends, Devtools closes the old context and creates a new context.

Query again:

~~~bash
curl -fsS http://127.0.0.1:18086/revision
~~~

Response after restart has the form:

~~~text
v2|hello|<new-uuid>
~~~

Compare:
- Before compile, prefix `v1|hello|` when auto-build is off.
- After compile and restart, prefix `v2|hello|`.
- `instanceId` changes because Spring creates a new controller.
- **JVM PID** can remain the same; never use a PID change as the sole criterion for concluding a Devtools restart occurred.

**Timing note:** `mvn compile` finishing does not mean a request in the very next millisecond will see v2. The watcher has a poll interval, quiet period, and context recreation time. If a request arrives mid-restart, the client may see a transient connection error. Wait for the next ready log and retry.

### Inspecting the Actual Bytecode File

On Linux:

~~~bash
ls -l target/classes/com/example/devtools/RevisionController.class
stat target/classes/com/example/devtools/RevisionController.class
~~~

On PowerShell:

~~~powershell
Get-Item .\target\classes\com\example\devtools\RevisionController.class |
    Select-Object FullName, Length, LastWriteTime
~~~

A newer file timestamp is a useful clue, though timestamps alone can be affected by filesystems, copies, or build caches. Combine it with compiler output, process classpath, response version, and restart logs.

### When Maven Does Not Recompile

If `mvn compile` reports classes up to date or writes no new output, Devtools has no reason to restart simply because Maven ran. Check:
- Was the `.java` file actually saved?
- Did you edit the right source directory/module?
- Is Maven compiling the module containing the running app?
- Is the IDE running from `out/production` while Maven writes to `target/classes`?
- Does the code have compilation errors?
- Is the output classpath being watched by the watcher?

**Do not reach for `mvn clean` as a first reflex** while the app is running: wiping all of `target/classes` and rebuilding tends to emit multi-wave changes and unstable restarts. First verify paths and run a normal compile.

## 9. Experiment C: Changing application.properties

Keep Terminal A running. Change:

~~~properties
demo.message=hello
~~~

to:

~~~properties
demo.message=updated
~~~

**If you only edit `src/main/resources/application.properties`**, the running app may not read the new file yet. Copy the resource to the runtime classpath directory via Maven's lifecycle:

~~~bash
mvn -q -DskipTests compile
~~~

Maven runs resource processing before compile; the new content is copied to `target/classes/application.properties`.

After Devtools restarts, `curl /revision` has the form:

~~~text
v2|updated|<new-uuid>
~~~

Property configuration changes in `target/classes` fall on the watched classpath and can trigger a **full restart**, unless the file/path is excluded or gated by a trigger file.

### Distinguishing Java Compile and Resource Copying

Not every resource edit requires `javac`. A YAML/properties file copied to the classpath via `mvn resources:resources` or an IDE build is enough for Devtools to see the new file. Thus, answering "do I have to recompile?" depends on the file type:

| Change | Step to Update Output Classpath |
| --- | --- |
| `.java` implementation | Compile to `.class` |
| `.kt` / Scala code | Compile with the appropriate compiler |
| `application.properties`/`.yaml` in resources | Copy/process resource into output classpath |
| Adding a new class | Compiler writes new `.class` in the right output folder |
| Deleting a class | Build tool/IDE must delete stale `.class` for a real change |
| Changing dependency version/JAR | Usually requires build/resolution and **restarting the process** to update base classloader |
| HTML/CSS/JS in static/templates | Copy to classpath if needed; by default **no full restart**, LiveReload may fire |
| Editing a file outside classpath | Not watched by default; can configure additional paths |

Thus "Maven compile" is a **convenience command** that both compiles classes and processes resources, not a rule that Java's compiler turns every resource into bytecode.

## 10. Experiment D: Static Resource Updates Without a Full Restart

File `src/main/resources/static/notice.txt` currently has:

~~~text
NOTICE_V1
~~~

Change it to:

~~~text
NOTICE_V2
~~~

Then run:

~~~bash
mvn -q resources:resources
~~~

or use your IDE to build/copy resources to the runtime classpath.

When `target/classes/static/notice.txt` updates, under **default exclusions** Devtools normally **does not close the entire `ApplicationContext`**, while the updated resource can be served and/or emit a **LiveReload** signal to the browser.

~~~bash
curl -fsS http://127.0.0.1:18086/notice.txt
~~~

Expected body:

~~~text
NOTICE_V2
~~~

This occurs once the resource is properly copied and static serving is not cached with an old copy.

### Do Not Confuse LiveReload with Restart

| Mechanism | What Happens | How to Recognize |
| --- | --- | --- |
| Full Devtools restart | Context/beans recreated, new restart classloader | Startup/restart logs appear, new bean markers |
| LiveReload | Emits signal for browser refresh when resources change | Page reloads with supporting extension/client |
| Updated static resource served | Web server reads/serves new content once classpath file updates | Resource response changes; context may not restart |
| Browser hard refresh | Browser re-fetches resources itself | Does not prove Java code/beans updated |
| IDE debugger HotSwap | JVM redefines certain running classes | Not equivalent to refreshing Spring context/bean definitions |

**A LiveReload event does not mean Devtools recreated beans**, and a static file change does not need a full Spring context restart for the browser to display updated content.

## 11. Directories Excluded from Restart by Default

In Spring Boot 3.5, common patterns that do not trigger a **full restart** when updated are resources under:

~~~text
META-INF/maven/**
META-INF/resources/**
resources/**
static/**
public/**
templates/**
~~~

The properties documentation also lists patterns such as compiled test classes, `git.properties`, and `META-INF/build-info.properties` in the default excludes. The key point is that **these resources do not necessarily require a context restart**; a change may only need LiveReload if the app and LiveReload server are running properly.

### Replacing Default Exclusions

~~~properties
spring.devtools.restart.exclude=static/**,public/**
~~~

The `exclude` property **replaces the default set** in config; avoid accidentally using it when you only want to add a small exception. To append exclusions while **keeping default patterns**, use:

~~~properties
spring.devtools.restart.additional-exclude=generated/**,scratch/**
~~~

Compare the actual relative paths against watched directories, because an incorrect glob prevents the exclusion from matching.

### Exclusion Does Not Mean Completely Ignored

In the docs, resources excluded from restart can still trigger **LiveReload**. Therefore, saying "excluded means Devtools completely ignores the file" is inaccurate. More accurately: **it does not trigger a full restart per the exclude mechanism**; reload behavior and classpath copying still depend on configuration.

## 12. Watching Additional Paths Outside the Classpath

A project may use templates or external resources outside `src/main/resources`, for example:

~~~text
devtools-classpath-demo/
├── shared-config/
│   └── local-rules.json
└── src/main/...
~~~

Devtools lets you add paths to watch:

~~~properties
spring.devtools.restart.additional-paths=shared-config
~~~

This is an example relative path in a development setup; in real apps check the resolved directory against the working directory and launch configuration.

**Distinction to keep clear:** `additional-paths` lets the watcher observe extra paths, yet **does not automatically place files on the JVM classpath or make `ClassLoader.getResource(...)` find them**. If business code needs to read those files, it still needs its own file location configuration.

You can use `spring.devtools.restart.exclude`/`additional-exclude` to make updates there trigger LiveReload instead of a full restart. Do not use additional paths to fake Java compilation: pointing the watcher at `.java` files outside the classpath **does not turn source code into `.class` files**.

## 13. Trigger File: Controlling Restart Timing

If the IDE builds continuously, a series of small edits can cause multiple restarts. Devtools supports a **trigger file**:

~~~properties
spring.devtools.restart.trigger-file=.reloadtrigger
~~~

The file must exist **somewhere on the runtime classpath**, for example:

~~~text
src/main/resources/.reloadtrigger
target/classes/.reloadtrigger
~~~

If placed in the resource source directory, the build/IDE must **copy the file into the output classpath** for the watcher to see it. Creating `.reloadtrigger` at the project root outside the classpath violates the requirement.

### How It Works

1. Devtools notices classpath changes but does not restart immediately after every update.
2. When the **trigger file** changes, Devtools runs a restart check.
3. **Only if qualifying changes** were detected by Devtools does it actually perform a restart.
4. The trigger file is not a "restart command that always restarts regardless of changes".

Example steps:

~~~bash
# Ensure sources changed and are compiled first.
mvn -q -DskipTests compile

# Then update the source trigger file content.
# On Linux/Bash:
printf 'trigger-1\n' >> src/main/resources/.reloadtrigger

# Copy the updated trigger file to the runtime classpath.
mvn -q resources:resources
~~~

**Note:** to run this experiment, **add the trigger-file property and initial file before starting the app**. If `.reloadtrigger` does not exist yet, appending creates it, though you still must ensure it is copied as a classpath resource. The order compile -> touch trigger -> copy matters: touching the trigger **before the compiler finishes writing classes** can cause Devtools to restart with half-written class files.

If your IDE has built-in trigger file support (Spring Tools or IntelliJ Ultimate per docs), you can use its UI action instead of shell commands.

## 14. FileSystemWatcher Poll Interval and Quiet Period

Devtools uses a **polling** watcher that, after detecting changes, waits for a period with no further modifications (quiet period) before acting. This avoids restarting while the IDE/Maven is still writing multiple `.class`/resource files.

Example:

~~~properties
spring.devtools.restart.poll-interval=2s
spring.devtools.restart.quiet-period=1s
~~~

Meaning:
- `poll-interval=2s`: interval between filesystem checks.
- `quiet-period=1s`: requires no further changes during this quiet window before restarting.
- Does not guarantee restarting at exactly `2+1=3` seconds: scheduling, build duration, filesystem, CPU load, and context refresh all contribute.
- Does not make the compiler run automatically.

### When Multi-Wave Compiles Cause Multiple Restarts

An IDE or build tool may write hundreds of classes in waves. If the quiet period is shorter than the gap between waves, Devtools can restart after the first wave and then restart again on the next; even transient `ClassNotFoundException`/dependency inconsistencies can occur.

Only when you observe this in practice, raise poll/quiet periods carefully:

~~~properties
spring.devtools.restart.poll-interval=3s
spring.devtools.restart.quiet-period=2s
~~~

These numbers are **experimental settings only**, not defaults to copy blindly onto every machine. Do not increase them indefinitely, as it slows the feedback loop and can mask out-of-sync IDE output issues.

### Strange Filesystem Timestamps

On network drives, Docker volume mounts, WSL, or filesystems with coarse mtime resolution, the file watcher may detect changes late or erratically. Verify:
- output file size/content actually changed;
- the process sees the right mount/path;
- container and host clocks are reasonable;
- the watcher is active in a development launch;
- no trigger gate or exclude is blocking it.

## 15. Restart Classloader and Base Classloader

Devtools restarts quickly thanks to **two classloaders**:

~~~mermaid
flowchart TD
    JVM["JVM still running"] --> BASE["Base classloader: stable JAR libraries"]
    JVM --> R1["Restart classloader #1: application classes"]
    R1 --> C1["ApplicationContext #1"]
    CHANGE["Compiled classpath changed"] --> CLOSE["Close old context"]
    CLOSE --> DROP["Discard restart classloader #1"]
    DROP --> R2["Restart classloader #2"]
    BASE --> R2
    R2 --> C2["ApplicationContext #2 with new classes"]
~~~

Libraries from dependency JARs normally go into the base loader, while the project being edited goes into the restart loader. On restart, Devtools replaces the restart loader and builds a new context, while reusing the base loader; hence restarts are usually faster than a cold JVM process start.

### Practical Consequences

- Singleton beans in the old context are **not** the singletons of the new context; they are recreated.
- Static fields of application classes in the restart loader can reset when classes reload.
- The JVM process/PID does not necessarily change.
- Custom resources or threads created **outside the Spring lifecycle** may unexpectedly survive across restarts and leak.
- Adding/removing dependency JARs or changing library versions usually requires **restarting the process/build**, because the base classloader does not reload already loaded JARs.
- In multi-module projects or complex reflection setups, a class may be loaded by a different loader than expected.

### Restart Is Not HotSwap-Style Class Redefinition

Debugger HotSwap can patch method bodies of already loaded classes within JVM/debugger limits; Devtools creates a fresh Spring context and restart classloader. Therefore:
- changing signatures/bean definitions may require a Devtools restart rather than simple HotSwap;
- seeing new code in the debugger does not guarantee bean wiring was rebuilt;
- do not use HotSwap as proof that the watcher detected a classpath update.

## 16. Updating the Classpath with IDEs and Build Tools

### Eclipse / Spring Tool Suite

Per Spring Boot 3.5, when Eclipse automatic building is enabled, **saving a modified file** typically causes the IDE to compile and update classpath output, triggering a restart.

If no restart happens:
1. Check `Project > Build Automatically` or the active build mode.
2. Check for compilation errors: the IDE may keep old `.class` files when source fails to compile.
3. Verify the project output directory is on the running app's classpath.
4. Check trigger-file and excludes if configured.
5. Do not blame Devtools before the compiler produces output.

### IntelliJ IDEA

Per Devtools docs, **Build > Build Project** updates the classpath. In some IDE setups, Save **does not build automatically**; the user must build via menu/shortcut or enable auto-make appropriate for their IntelliJ version.

When launching via a Spring Boot run configuration:
- verify devtools is on runtime dependencies;
- identify the compiler output directory used by the IDE;
- ensure builds write to the **exact output directory** read by the running JVM process;
- if starting the app via Maven plugin while IntelliJ builds to a different output folder, new `.class` files may **not** appear where the watcher looks.

Avoid relying on one fixed keyboard shortcut across all OSes/keymaps. Use IDE menus to avoid Windows/macOS/Linux differences.

### Maven

In Terminal A:

~~~bash
mvn spring-boot:run
~~~

In Terminal B, after editing Java files:

~~~bash
mvn -q -DskipTests compile
~~~

Standard Maven output is `target/classes` for the corresponding project/module. No need to manually re-run `mvn spring-boot:run` if Devtools is active and the watcher sees the class change.

In multi-module projects, compile the **module containing the changed class** and ensure the running app uses that module's development output folder; if another module is still loaded as a dependency JAR in the base loader, rebuilding the JAR without restarting the JVM may have no effect.

### Gradle

Dependency example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

Run the app:

~~~bash
./gradlew bootRun
~~~

In another shell, after editing Java:

~~~bash
./gradlew classes
~~~

Spring Boot docs also note `gradle build` can update the classpath. Outputs like `build/classes/java/main` and `build/resources/main` must match the classpath used by `bootRun`. If Gradle runs under a different build daemon or custom configuration, verify actual class/resource file updates rather than just trusting `BUILD SUCCESSFUL`.

**Do not disable forking** when using Maven/Gradle plugins with Devtools restart; per docs, an isolated classloader is an essential prerequisite.

## 17. Difference Between the Two Ways to Disable Restart

### Disabling Only the Watcher/Restart via Properties

~~~properties
spring.devtools.restart.enabled=false
~~~

Per Spring Boot docs, this normally **stops watching file changes for restart**, yet the restart classloader **may still be initialized**. It fits cases where you want to pause automatic restarts temporarily in a dev environment without changing launch setup.

### Disabling Restart Support Completely

In `main`, **before `SpringApplication.run`**:

~~~java
public static void main(String[] args) {
    System.setProperty(
            "spring.devtools.restart.enabled", "false");
    SpringApplication.run(MyApplication.class, args);
}
~~~

This snippet requires `MyApplication` and importing `SpringApplication`. It shows how to set the **Java System property very early** to omit all restart support per Spring Boot docs. Do not put this into the Section 6 lab project when trying to test automatic restart.

You can also pass a JVM system property before launching the app; note `-D...` is a **JVM argument**, not a command-line argument after `-jar`.

### When Never to Force-Enable Devtools

Spring Boot allows overriding a production-style launch with `-Dspring.devtools.restart.enabled=true`, yet docs warn **never to do so in production due to security risks**. Never use it as a "trick" to swap code inside a production JAR bypassing build/deploy. Production rollouts require releasing new artifacts with managed startup/rollback.

## 18. Restart Exclusions and Classloader Customization Are Two Different Things

Two configuration groups are easily confused:

1. **File watcher/exclude** — which changed file paths trigger a full restart versus only LiveReload.
2. **Classloader include/exclude** — which classpath entries go into the restart loader versus the base loader.

Example classloader customization in:

~~~text
src/main/resources/META-INF/spring-devtools.properties
~~~

You can declare keys with prefixes:

~~~properties
restart.include.company-common=company-common-.+\\.jar
restart.exclude.shared-output=.*/shared-output/.*
~~~

Values are **regular expressions applied to classpath paths**, not file-watcher Ant globs. The two regexes above are illustrative; for a real project match them against full classpath entries and proper pattern syntax.

Do not alter classloader splitting to fix "saved `.java` without compiling": that is a **missing new bytecode** issue. Classloader customization is only needed when there is a clear issue with class identity, reflection, serialization, or multi-module setups.

### A Class Identity Issue Example

Two classes with the same fully qualified name loaded by **two different classloaders** are not considered the same class identity by the JVM. Thus you can see a `ClassCastException` that looks like a class "cannot be cast to itself". When it happens:
- try disabling restart to compare;
- inspect base/restart classpath splitting;
- check libraries using reflection/serialization;
- if that is the root cause, add appropriate `restart.include.*`/`restart.exclude.*` entries.

Do not try fixing it with `System.gc()` or randomly altering thread context classloaders.

## 19. Diagnostic Table: "Edited Code, No Restart"

| Symptom | Possible Cause | Test / Fix |
| --- | --- | --- |
| Saved `.java` yet no restart | Not compiled yet | Build Project or `mvn compile` |
| Maven compile succeeded yet still old code | Compiler wrote no new file or wrong module | Check `.class` timestamp/hash and output path |
| Compiled in IntelliJ yet Maven app runs old code | Two tools use different output directories | Compare JVM classpath against compiler output folder |
| Running via `java -jar` does not restart | Packaged apps disable devtools by default | Use `mvn spring-boot:run` or IDE launch in development |
| Devtools absent at runtime | Missing dependency or wrong scope | Check runtime dependencies and build config |
| `spring.devtools.restart.enabled=false` is set | Automatic restart disabled | Re-enable only in local development |
| Edited HTML/CSS yet context does not restart | Default resource excludes | Usually expected; check LiveReload/copying |
| No LiveReload in browser | Missing LiveReload client or server disabled | Check extension and `spring.devtools.livereload.enabled` |
| Trigger file configured, compile did not restart | Trigger file on classpath was not updated | Compile first, update trigger, and copy resource |
| Multiple restarts after build | Compiler writes in batches, quiet period too short | Increase quiet period after confirming root cause |
| Restart triggers mid-build | Watcher sees unstable output | Use a trigger file or increase quiet period |
| Added dependency yet code stays old | JAR in base loader not swapped | Restart process with the updated dependency classpath |
| New code active yet bean state is stale | Viewing external cache or wrong app/port | Check instance ID/port, logs, request routing |
| Port occupied after restart | Custom thread/server/resource not closed | Check bean destruction, shutdown hook, and sockets |
| Spring reports classloading error | Incompatible base/restart split | Temporarily disable restart, inspect `spring-devtools.properties` |
| `ClassNotFoundException` after several restarts | Unsynchronized compilation output or premature restart | Check compiler errors, quiet period, module outputs |
| Only an external resource fails to trigger | Not on watched classpath | Configure `additional-paths` and verify path |
| JRebel enabled | JRebel replaces restart mechanism | Follow the integration's documentation |
| AspectJ weaving in use | Automatic restart unsupported per docs | Use an appropriate build/restart workflow |

### Logical 90-Second Debug Sequence

1. **Confirm exact URL/port and PID** serving the request; do not hit a different instance by mistake.
2. **Confirm development launch mode**, not production-style `java -jar`.
3. **Confirm `spring-boot-devtools` is on runtime classpath** and restart is not disabled.
4. **Run Build Project / `mvn compile`** after editing Java.
5. **Inspect output classpath** to verify `.class` changed.
6. **Wait for poll + quiet period + context refresh** and inspect restart logs.
7. Check `exclude`, `trigger-file`, and `additional-paths` if configured.
8. If still stuck, inspect multi-module/classloader split, shutdown hook, and plugin forking.

This order avoids changing a dozen configs when the simple cause is **the IDE has not compiled yet**.

## 20. What Happens to State During a Devtools Restart?

A Devtools restart typically **closes the old `ApplicationContext` and creates a new context**. Therefore:
- Beans are recreated according to the dependency graph.
- `@PostConstruct`, `BeanPostProcessor`s, and runner/lifecycle callbacks run again.
- `ApplicationReadyEvent` fires again after a successful restart.
- Data held solely in bean memory is replaced with fresh instances.
- Databases, Redis, files, and session storage outside the JVM **are not automatically reset**.
- Static fields of classes in the restart loader can reset; static fields of classes in the base loader can persist.
- If custom non-daemon threads/executors are not stopped properly, they can survive across restarts and cause duplicate schedulers/jobs.
- Startup logic with side effects like sending emails, creating tables, seeding data, or calling APIs must be designed to be idempotent.

**Do not treat restart as a "safe deployment"**: during a Devtools restart, in-flight requests may be disrupted; this feature targets local development, not production hot deployment.

## 21. LiveReload, Browser Cache, and Sources of "Old Code"

When you do not see changes in the browser, the cause is not necessarily un-reloaded Java code:

- **Browser cache** may serve old CSS/JS.
- **Template engine caching** may serve a prior template; Devtools provides development property defaults to mitigate this depending on the engine.
- **Reverse proxy/cache/CDN** may return a cached response.
- **Wrong host/port** may hit a different running app.
- **IDE debugger HotSwap** patched classes in a different JVM than the project being built.
- **Static resource not copied to classpath**, even though `src/main/resources` was edited.
- **Backend bean not recreated**, if no full restart occurred.

In our demo, `curl /revision` and `curl /notice.txt` cleanly separate **Java logic** from **static resources**. Using a UUID marker in the controller gives an extra signal that the bean was recreated.

Devtools includes an embedded LiveReload server. On the browser side, you need a supporting extension/client to auto-reload tabs. Having Devtools on the server alone does not auto-refresh every browser tab.

Per docs, only **one LiveReload server** runs on a machine at a time; when running multiple development apps, later apps may fail to start LiveReload even though automatic restart still works.

## 22. Controlled Testing and Measuring Feedback Time

To evaluate workflow quality, do not merely claim "Devtools is fast" without measuring. You can record:

| Milestone | Definition |
| --- | --- |
| `T_save` | Time developer saves source |
| `T_compile_end` | Compiler finishes writing classes/resources |
| `T_watch_detect` | Watcher detects classpath change |
| `T_restart_begin` | Old context begins closing |
| `T_ready_again` | Next `ApplicationReadyEvent` |
| `T_endpoint_new` | Endpoint reliably returns the new version |

Useful metrics:
- `compile_duration = T_compile_end - T_save`;
- `watch_and_restart_duration = T_ready_again - T_compile_end`;
- `end_to_end_feedback = T_endpoint_new - T_save`;
- number of restarts per single Build Project;
- rate of failed builds or failed responses during restarts.

**Do not compare unsynchronized timestamps across multiple processes/machines**. For durations inside the same JVM, use `System.nanoTime()`; across IDE/build tool and app, use synchronized log timestamps or external observation tools.

### Why Avoid Single-Run Benchmarks?

Filesystem cache, JIT, CPU load, compiled class count, incremental compiler behavior, and bean graphs all vary timings. When tuning poll/quiet periods, measure multiple runs on the same project/workload and compare median/p95. A smaller poll interval does not guarantee faster total feedback if it causes mid-compile restarts.

## 23. Practical Application Checklist

- [ ] `spring-boot-devtools` dependency is on the development runtime.
- [ ] Maven uses `optional=true` or Gradle uses `developmentOnly` as recommended.
- [ ] Application runs in development mode with classpath directories.
- [ ] Build-plugin forking is not disabled when relying on Devtools restart.
- [ ] `spring.devtools.restart.enabled` is not disabled.
- [ ] Verified the edited file belongs to the **right module and source set**.
- [ ] IDE/Maven/Gradle compiled `.java` into new `.class`.
- [ ] Observed resources were copied into the output classpath.
- [ ] Compiler output directory matches a watched classpath entry.
- [ ] Waited for polling and quiet period before assuming it is broken.
- [ ] Checked excludes for `static`, `public`, `templates`.
- [ ] When using a trigger file, it sits on the runtime classpath and was updated **after** compile.
- [ ] If files are outside the classpath, configured `additional-paths` explicitly.
- [ ] Did not confuse LiveReload/browser refresh with a full context restart.
- [ ] For multi-module/classloader errors, diagnosed the classloader split with evidence.
- [ ] If testing disabling restart, understood properties vs. early `System` property.
- [ ] Did not force-enable Devtools on production packaged JARs.
- [ ] Properly cleaned up custom threads/resources to avoid leaks across restarts.
- [ ] Distinguished compiler errors, post-restart startup errors, and missed watcher detections.
- [ ] Measured actual feedback/latency instead of guessing from a single log line.

## 24. Review Questions

**1. What does Devtools watch by default?**  
Classpath entries pointing to **directories**, not all `.java` files under the source tree by default.

**2. Does simply saving a Java file guarantee a restart?**  
No. Bytecode on the runtime classpath must update. Eclipse auto-build may do this right after Save; IntelliJ typically needs Build Project per active workflow.

**3. Which Maven command updates compiled classes?**  
`mvn compile`, in the right module/project and without compilation errors.

**4. If Maven reports compile succeeded without writing new files, must Devtools restart?**  
No. It requires a detected classpath change, not just the completion of a Maven command.

**5. Does editing application.properties require javac?**  
Not necessarily; the resource must be copied/processed into the classpath directory the app uses.

**6. Why does a java -jar packaged app not restart with Devtools by default?**  
Spring Boot treats it as a production-style launch and disables devtools by default.

**7. Does changing CSS/HTML in static require restarting the whole context?**  
Usually not under default exclusions; updated resources can be served and LiveReload can fire.

**8. How does spring.devtools.restart.additional-exclude differ from exclude?**  
`additional-exclude` appends patterns while preserving default exclusions, whereas `exclude` replaces the default set.

**9. Does a trigger file restart even when no other changes occurred?**  
No. It triggers a **restart check**, and only restarts if Devtools has updates to process.

**10. Is a trigger file at the project root but not on the classpath valid?**  
No; per docs it must exist somewhere on the runtime classpath.

**11. Do poll-interval and quiet-period compile Java?**  
No. They only tune filesystem change detection and stabilization.

**12. Why does a Devtools restart not necessarily create a new PID?**  
Because it keeps the JVM and base classloader, replacing only the restart classloader/context.

**13. When adding a new library JAR, does Devtools definitely load the new version in the base classloader?**  
No. Usually a process restart is required to rebuild the runtime classpath/base loader.

**14. How do you disable the restart classloader completely?**  
Set the Java System property `spring.devtools.restart.enabled=false` **before** `SpringApplication.run` per Boot docs.

**15. Why might a multi-module project still run old code after compiling?**  
The app may load that module as a JAR in the base loader while the compiler updates a separate output directory.

**16. Does the LiveReload server automatically refresh all browser tabs without a client?**  
No; a supporting browser extension/client is needed, and caching/networking still affect it.

**17. If a project uses AspectJ weaving, is Devtools automatic restart supported?**  
Per Spring Boot 3.5 documentation, it is not supported with this mechanism.

**18. Why should Devtools never be treated as a production hot-deployment solution?**  
It is aimed at development, carries security/lifecycle implications, and cannot replace controlled release/deploy/rollback pipelines.

## 25. Official Documentation Sources

- [Spring Boot 3.5 — Developer Tools](https://docs.spring.io/spring-boot/3.5/reference/using/devtools.html): automatic restart, classpath update conditions, IDE/Maven/Gradle, LiveReload, trigger file, exclusions, and two classloaders.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): default `spring.devtools.restart.enabled`, exclude patterns, poll interval, and quiet period.
- [Spring Boot 3.5 — Maven Plugin: Run](https://docs.spring.io/spring-boot/3.5/maven-plugin/run.html): running development apps via `spring-boot:run` and plugin configuration.
- [Spring Boot 3.5 — Gradle Plugin](https://docs.spring.io/spring-boot/3.5/gradle-plugin/running.html): `bootRun`, tasks, and runtime configuration.
- [Spring Boot 3.5 — Application Properties: Devtools](https://docs.spring.io/spring-boot/3.5/reference/using/devtools.html#using.devtools): restart defaults and diagnostic options.
- [Oracle JDK 17 — javac command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): compiler producing `.class` from `.java`.
- [Oracle JDK 17 — java command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): runtime classpath and `-jar` behavior.

**Conclusion:** with Spring Boot Devtools, **editing source is not yet changing the classpath**. Only when Java source is **compiled into new bytecode in the output directory used by the running process** does the watcher get a signal to restart. Resource files must be **copied/processed** onto the classpath; static/templates may only trigger LiveReload. For quick diagnosis, verify **launch mode -> dependency -> output path -> compile/copy -> excludes/trigger -> polling -> restart log**. Never use Devtools in place of a compiler or a production deployment pipeline.