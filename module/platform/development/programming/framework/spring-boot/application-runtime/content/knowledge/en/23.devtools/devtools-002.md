# Distinguishing Restart, Resource Reload, and Full JVM Restart in Spring Boot Devtools

## 1. Why Are These Three Operations Not the Same?

When developing a Spring Boot application, you edit Java, HTML, CSS, or configuration files and expect to see the new result. There are at least **three distinct update boundaries**:

1. **Devtools restart (restarting the Spring application via the restart classloader):** Spring Boot Devtools closes the running application context, discards the classloader for application code, and restarts the application portion within the **same JVM**. The PID and JVM start time remain unchanged.
2. **Resource reload / LiveReload (reloading resources and UI):** updated static resources or templates are served **without recreating the Spring application context**. LiveReload, if configured and supported by the browser, can trigger a browser refresh so the user sees the new content.
3. **Full JVM restart (restarting the JVM process):** stops the old Java process and launches a new Java process. The JVM, heap, classloaders, static state, startup flags, application context, and beans are created from scratch.

These three concepts are easily lumped together as "reload", yet their scope of impact differs significantly. Mistaking one for another can wipe debugging state, fail to pick up new changes, or make you think editing an HTML file restarted the entire server.

This lesson belongs to the **Devtools** group of the Spring Boot Application Runtime module. After this lesson, you should be able to identify the exact update type based on **classpath**, **Spring context**, **JVM PID/start time**, **caching**, and **LiveReload behavior**.

### Quick Mental Model

~~~text
Compiled Java code changes
  -> Devtools detects classpath change
  -> closes old context / discards old restart classloader
  -> creates new restart classloader / initializes new context
  -> JVM PROCESS STAYS ALIVE

Static/template file changes on the classpath
  -> no need to restart Spring context
  -> server can serve the new version of the resource
  -> LiveReload triggers browser refresh (if client is connected)
  -> JVM STAYS ALIVE, CONTEXT IS STILL THE OLD CONTEXT

Stop the Java process and launch it again
  -> old JVM terminates
  -> new JVM starts with new flags/classpath/environment
  -> all classloaders and context are created fresh
  -> COLD START, NEW PROCESS
~~~

**Key conclusion:** A Devtools restart is not a JVM restart; LiveReload is not a Devtools restart either. And the browser refreshing automatically does not imply that Java code has been reloaded.

## 2. Comparison Table of the Three Boundaries

| Criterion | Devtools restart | Resource reload / LiveReload | Full JVM restart |
| --- | --- | --- | --- |
| Scope of impact | Spring application + restart classloader | Resource files / browser | Entire Java process |
| JVM PID | Unchanged | Unchanged | Usually different, though the OS may reuse a PID |
| JVM start time | Unchanged | Unchanged | New |
| Spring ApplicationContext | Creates a new context | Unchanged | New context in a new process |
| Application singleton beans | Recreated in the new context | Not recreated solely from resource reload | Recreated |
| App static state in restart classloader | Usually resets per restart | Unchanged | Reset |
| Library static state in base classloader | Can persist | Unchanged | Reset |
| Compiled application Java classes | Loaded from the new restart classloader | Unchanged | Loaded in the new JVM |
| Web app may briefly drop connections | Yes | Usually not from resource reload | Yes during old/new process handoff |
| HTTP sessions | Depends on config/server; do not assume always lost | Usually unaffected by resource-only changes | Depends on external persistence and server |
| JVM flags like `-Xmx`, `-javaagent` | Unchanged | Unchanged | New flags can take effect |
| JAR libraries in base classloader | Do not expect them to be swapped | Unchanged | Loaded from the new classpath |
| Requires Java compilation? | Yes, so classpath output changes | No for HTML/CSS already copied to runtime classpath | Usually yes if source changed |
| Requires browser refresh to see UI? | May be needed | Yes; LiveReload client can do this automatically | May be needed |
| Purpose | Fast feedback loop for code/config changes | Quick asset/template edits | Clean startup, changing JVM/dependencies |

This table reflects typical Spring Boot 3.5 Devtools behavior in local environments run via an IDE or build plugin. Additional framework mechanisms, browser caches, multi-module setups, or containers may alter some rows; measure by actual runtime signals rather than guessing from the action name.

## 3. What Is Spring Boot Devtools?

`spring-boot-devtools` is a **development-time** dependency. It provides:
- Automatic Restart based on file changes on the classpath.
- A LiveReload server so browsers with a compatible client/extension auto-refresh when resources change.
- Convenient development defaults, such as reducing caching for template engines and static resources.
- Watcher, trigger file, and classloader separation settings to speed up the development loop.

Maven dependency declaration:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
~~~

In Gradle, declare it in the development-only configuration:

~~~gradle
dependencies {
    developmentOnly("org.springframework.boot:spring-boot-devtools")
}
~~~

**Do not use Devtools as a production operations component.** Devtools automatically disables itself when running a fully packaged application in normal contexts such as `java -jar`. Repackaged archives exclude Devtools by default. Never force-enable it via system properties in production, as remote development features and development defaults create security and operational risks.

### Where Can Devtools Actually Work?

- **IDE/expanded classpath**: typically has `target/classes` or `build/classes` as directories on the classpath; Devtools can watch them.
- **`mvn spring-boot:run`** or **`gradle bootRun`**: the build plugin runs the application in development mode; Devtools usually works if the dependency is present and restart is not disabled.
- **`java -jar target/app.jar`**: fully packaged application; Devtools normally **does not run**; editing source or `target/classes` after the JAR has started does not swap classes inside the JAR.
- **Production Docker image**: never use Devtools for hot deployment; replace the image and roll out through your deployment pipeline.

**Note on Maven/Gradle plugins:** running via build plugins requires keeping proper forking behavior. If you disable forking, the environment and isolated application classloader that Devtools expects may not be created properly; restart may behave differently or stop working.

## 4. The Devtools Restart Mechanism: Two Classloaders, One JVM

Devtools Automatic Restart uses **two classloaders**:

- **Base classloader**: holds classes that rarely change, usually from external dependency JARs.
- **Restart classloader**: holds classes under active development, usually from the output directories of open project modules in the IDE.

When Devtools detects a valid change:

~~~text
JVM started at T0, PID=P
  |
  +-- BaseClassLoader (rarely changing libraries)
  |
  +-- RestartClassLoader #1 (compiled app classes)
  |       |
  |       +-- ApplicationContext #1
  |       +-- Singletons #1
  |       +-- HTTP mappings / runners / web server...
  |
  +-- Classpath watcher detects change
          |
          +-- Close ApplicationContext #1
          +-- Discard RestartClassLoader #1
          +-- Create RestartClassLoader #2
          +-- Re-run application startup
          |       |
          |       +-- ApplicationContext #2
          |       +-- Singletons #2
          |       +-- New HTTP mappings
          |
          +-- BaseClassLoader remains alive
          +-- JVM still has PID=P, start time=T0
~~~

This is an **application-level restart inside a living JVM**, not a cold start of a new JVM. That is why it is usually faster than restarting the whole process: libraries in the base classloader do not need to be loaded from scratch.

### What Gets Recreated?

Typically singleton beans, the embedded web server, context-managed event listeners, and application state living in the replaced classloader are recreated in the new application context.

`@PostConstruct` hooks, runners, and Spring startup events can fire again when the application restarts. Resources owned by old beans must be stopped/closed during the old context's close path; do not assume Devtools merely "patches bytecode inside the JVM" while keeping every object intact.

### What Can Stay Alive?

- **The JVM process** and JVM-wide settings.
- The base classloader and its rarely changing library classes.
- Static variables or caches held by classes **in the base classloader** (they are not reset with the restart classloader).
- Threads or resources **not properly managed by Spring**, if old code leaks them.
- Databases, message brokers, and cloud resources external to the JVM.
- Certain session state if supported by the servlet container / Devtools persistence configuration.

This means an issue that only appears after several Devtools restarts may be a **resource leak or classloader leak**, rather than "Java always resets everything" like in a cold start.

### Is Restart the Same as Hot Code Swap?

No. Devtools restart **swaps the application classloader and recreates the context**. It differs from:
- An IDE debugger's `HotSwap`, which can replace the bytecode of certain loaded classes without restarting the whole context, within JVM/debugger limits.
- Advanced class-reloading tools such as JRebel.
- Browser Hot Module Replacement (HMR) in frontend build tools.

Therefore, never assume Devtools preserves Spring singleton instances or all in-memory state after editing a Java method.

## 5. When Does Devtools Actually Restart?

**The most important condition: Devtools watches files on the classpath, not source files by magic.**

In a typical Maven project:

~~~text
src/main/java/...       (Java source)
       |
       +-- mvn compile / IDE build
       v
target/classes/...      (compiled .class on runtime classpath)
       |
       +-- Devtools FileSystemWatcher detects classpath change
       v
Spring ApplicationContext restart
~~~

In Eclipse/Spring Tools, saving a file can trigger automatic compilation. In IntelliJ IDEA, you usually need **Build Project**, auto-build, or equivalent settings while the application is running. Editing `src/main/java` without the IDE compiling/copying to output gives **nothing for Devtools to detect**.

When using build plugins and needing to update compiled classes:

~~~bash
mvn compile
~~~

Run this command in another terminal while the app is alive; it updates the output if Java source changed. Once the watcher sees a valid classpath change, the restart occurs after a polling interval and quiet period.

### Commonly Overlooked Steps

1. Save the Java source file.
2. IDE/Maven actually compiles a new class file.
3. The class file is written into the runtime classpath directory watched by the running process.
4. The Devtools watcher detects the update.
5. Devtools waits for a quiet period to avoid restarting mid-compile while multiple files are written.
6. The old context closes and the new context starts.

If the application is running a packaged JAR, compiling to `target/classes` does not update classes inside the **JAR used by the running process**. That is why "I built it and the JAR still runs old code" is not necessarily a Devtools bug.

### Condition Evaluation Delta Log

Devtools can print the **delta** in auto-configuration evaluation results on restart, which helps when adding/removing beans or changing conditional properties. You can disable it if logs become noisy:

~~~properties
spring.devtools.restart.log-condition-evaluation-delta=false
~~~

This is a diagnostic aid, not a separate JVM restart. Nor does the delta log replace the root cause exception if the new startup fails.

## 6. Resource Reload: Static Assets, Templates, and Browser

Static resources like HTML, CSS, JavaScript, images, and view templates like Thymeleaf usually **do not require recreating the Spring context** when their content changes.

In Spring Boot Devtools 3.5, the following paths are **excluded from triggering a full application restart by default**:

~~~text
/META-INF/maven
/META-INF/resources
/resources
/static
/public
/templates
~~~

This enables faster page or template edits. However, the file must be updated at the **actual resource path served by the application**.

### Two Meanings of "Reload"

**A. Resource is served with new content:** The browser or HTTP client requests the URL again and the server/templating engine returns the updated resource. The Spring context can remain intact.

**B. LiveReload browser refresh:** Devtools provides a LiveReload server, while the browser needs a LiveReload-capable client/extension connected to that server. When classpath resources change, Devtools sends a signal for the browser to refresh the UI.

**B does not guarantee A.** A browser refresh simply re-requests the page. If the runtime resource is still stale because the file was not copied, caching is still enabled, or a proxy/CDN serves an old version, the browser will still display old content.

### Is LiveReload Mandatory?

No. You can:
- Open the page in a browser and press refresh manually.
- Use `curl` to re-read the static resource or template.
- Use a compatible LiveReload browser extension for auto-refresh.

LiveReload is **not** a mechanism for updating Java classes inside the JVM. Java code changes still require compilation and usually a Devtools restart.

### Thymeleaf and Caching

Template engines typically enable template caching for production performance. Devtools applies several **development property defaults** to reduce caching, including `spring.thymeleaf.cache=false` when using Thymeleaf. Thus, an updated template on the runtime classpath can usually be re-read without restarting the context.

If you still see the old template, check:
- Has the target file in `target/classes/templates` or the actual output classpath been updated?
- Was template caching overridden back to `true`?
- Is the response passing through another proxy or cache?
- Is the application running via IDE/plugin or as a packaged JAR?
- Did you edit the exact template used by the view resolver?

### CSS/JS Static Resources

Devtools also tunes resource caching defaults for development. However, browsers maintain their own caches. With fingerprinted URLs, CDNs, service workers, or reverse proxies, those layers can serve stale assets.

To distinguish, read the actual content with an HTTP client:

~~~bash
curl -i http://localhost:8080/hello.txt
~~~

Compare the response body with the file on the runtime classpath. If `curl` sees the new version while the browser shows the old one, suspect **browser cache or service workers** before blaming Devtools.

## 7. Runnable Java 17+ Demo: Measuring JVM, Context, and Resources

Demo goal: use **one application** with 3 independent signals:

- `pid` and `jvmStartMillis`: identify the JVM process (PIDs can be reused by the OS; start time is stronger).
- `contextToken`: a UUID generated **once per ApplicationContext**, changing whenever Devtools restarts the context.
- `javaMessage`, static text, and Thymeleaf view: compare when a Java class changes versus when a resource changes.

Run the demo in development mode via `mvn spring-boot:run`; to observe a full JVM restart, manually stop the process and start it again. Do not run two instances on port 8080 simultaneously.

### 7.1. Project Structure

~~~text
devtools-boundary-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/devtoolsboundary/
    │   └── DevtoolsBoundaryApplication.java
    └── resources/
        ├── application.properties
        ├── static/
        │   └── hello.txt
        └── templates/
            └── view.html
~~~

### 7.2. Maven pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>devtools-boundary-demo</artifactId>
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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

`spring-boot-starter-web` provides the embedded servlet server and REST/static asset support. `spring-boot-starter-thymeleaf` resolves the `view` template. `spring-boot-devtools` supports local development and is marked optional to avoid transitive inclusion in other modules.

### 7.3. Complete Java File

Save to `src/main/java/com/example/devtoolsboundary/DevtoolsBoundaryApplication.java`:

~~~java
package com.example.devtoolsboundary;

import java.lang.management.ManagementFactory;
import java.util.Map;
import java.util.UUID;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DevtoolsBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(DevtoolsBoundaryApplication.class, args);
    }

    @Bean
    ContextIdentity contextIdentity() {
        return new ContextIdentity(UUID.randomUUID().toString());
    }

    // This bean has only one instance per ApplicationContext.
    record ContextIdentity(String token) {
    }

    @RestController
    static class DiagnosticController {
        private final ContextIdentity identity;

        DiagnosticController(ContextIdentity identity) {
            this.identity = identity;
        }

        @GetMapping("/diag")
        Map<String, Object> diagnostics() {
            return Map.of(
                    "pid", ProcessHandle.current().pid(),
                    "jvmStartMillis",
                    ManagementFactory.getRuntimeMXBean().getStartTime(),
                    "contextToken", identity.token(),
                    "appClassLoader",
                    String.valueOf(getClass().getClassLoader()),
                    "javaMessage", "java-v1"
            );
        }
    }

    @Controller
    static class ViewController {

        @GetMapping("/view")
        String view() {
            return "view";
        }
    }
}
~~~

This is a self-contained Java file inside the Maven project above with no placeholders left to create. Java 17 supports `record`, `ProcessHandle`, `Map.of`, and `UUID`. Spring Boot component scanning picks up static nested controllers inside the `@SpringBootApplication` class package.

**Explanation of the five fields in GET /diag:**

| Field | Source | When It Changes |
| --- | --- | --- |
| `pid` | `ProcessHandle.current().pid()` | Usually different in a new JVM process, though PIDs can be reused |
| `jvmStartMillis` | `ManagementFactory.getRuntimeMXBean().getStartTime()` | Only changes when the JVM actually restarts |
| `contextToken` | Singleton bean UUID per context | Changes whenever a new context is created, including Devtools restarts |
| `appClassLoader` | Classloader that loaded `DiagnosticController` | Usually shows the restart classloader in dev mode; string representation is not a stable API |
| `javaMessage` | Hardcoded string in Java code | Only becomes v2 after the new class is loaded |

`Map.of` does not guarantee JSON key ordering; PIDs, timestamps, UUIDs, and classloader strings cannot be predicted verbatim either. Therefore, **there is no fixed literal stdout/JSON** for this endpoint. The actual verification compares **fields before and after each operation**.

### 7.4. The application.properties File

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=devtools-boundary-demo
server.port=8080
spring.main.banner-mode=off

# Keep devtools restart and LiveReload enabled in local runs.
spring.devtools.restart.enabled=true
spring.devtools.livereload.enabled=true
~~~

You may omit the two Devtools properties since they default to enabled in eligible development environments. Do not set `spring.devtools.restart.trigger-file` in the basic demo so every valid classpath change is evaluated directly.

**Note:** `application.properties` is also a classpath file watched by the watcher; editing this configuration can trigger a restart. The "resource reload without restart" exercise below only edits files in `static` and `templates`.

### 7.5. Static File hello.txt

File `src/main/resources/static/hello.txt`:

~~~text
STATIC_VERSION=v1
~~~

While the app is running, try:

~~~bash
curl -s http://localhost:8080/hello.txt
~~~

Expected response body:

~~~text
STATIC_VERSION=v1
~~~

This line is served from a **resource**, not from a Java method in `DiagnosticController`. Modifying `hello.txt` requires no Java compilation.

### 7.6. Thymeleaf File view.html

File `src/main/resources/templates/view.html`:

~~~html
<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Devtools Boundary Demo</title>
</head>
<body>
    <h1>TEMPLATE_VERSION=v1</h1>
    <p>This page is returned by the Thymeleaf view resolver.</p>
    <p><a href="/hello.txt">View static resource</a></p>
    <p><a href="/diag">View runtime diagnostics</a></p>
</body>
</html>
~~~

`ViewController` returns the view name `view`, and Thymeleaf uses its default prefix/suffix to locate `classpath:/templates/view.html`. This is valid HTML; `th:text` is not required for Thymeleaf to render an HTML file.

Access:

~~~bash
curl -s http://localhost:8080/view
~~~

The HTML response will contain the string:

~~~text
TEMPLATE_VERSION=v1
~~~

Markup whitespace may vary depending on view engine processing, so the text marker is what you verify.

## 8. Experiment 1: Baseline When the Application First Starts

Open terminal A in the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Wait for the server to be ready on `http://localhost:8080`. In terminal B, call:

~~~bash
curl -s http://localhost:8080/diag
curl -s http://localhost:8080/hello.txt
curl -s http://localhost:8080/view
~~~

**Meaningful results:**

- `/diag` returns a PID `P1`, JVM timestamp `T1`, and context token `C1`, with `javaMessage=java-v1`.
- `/hello.txt` returns `STATIC_VERSION=v1`.
- `/view` contains `TEMPLATE_VERSION=v1`.
- The ApplicationContext started successfully and corresponding startup logs are visible.

Example JSON **illustrating structure only, not real values or fixed key order**:

~~~json
{
  "pid": 11111,
  "jvmStartMillis": 1790000000000,
  "contextToken": "uuid-context-1",
  "appClassLoader": "org.springframework.boot.devtools.restart.classloader.RestartClassLoader@...",
  "javaMessage": "java-v1"
}
~~~

Do not copy `"11111"` or `"uuid-context-1"` as expected values. In real tests, record the **values returned by the endpoint** and compare across requests.

## 9. Experiment 2: Change Only Static Resource/Template Without Context Restart

Keep terminal A running. Edit the two source files:

~~~text
src/main/resources/static/hello.txt:
  STATIC_VERSION=v2

src/main/resources/templates/view.html:
  <h1>TEMPLATE_VERSION=v2</h1>
~~~

Because the app runs against the **runtime classpath**, editing source files alone may **not be enough** if your IDE has not copied resources to the output directory. To change only these two resources without accidentally compiling Java or touching `application.properties`, copy just the modified files:

**Bash/zsh, run in terminal B at the project root:**

~~~bash
cp src/main/resources/static/hello.txt target/classes/static/hello.txt
cp src/main/resources/templates/view.html target/classes/templates/view.html
~~~

**Windows PowerShell (equivalent):**

~~~powershell
Copy-Item -LiteralPath .\src\main\resources\static\hello.txt -Destination .\target\classes\static\hello.txt -Force
Copy-Item -LiteralPath .\src\main\resources\templates\view.html -Destination .\target\classes\templates\view.html -Force
~~~

The copy commands above assume Maven has created `target/classes` and the server is running via `mvn spring-boot:run` as in the experiment. If your IDE/build tool uses a different output directory, **copy to your actual runtime classpath**, rather than blindly using this path.

Then call again:

~~~bash
curl -s http://localhost:8080/hello.txt
curl -s http://localhost:8080/view
curl -s http://localhost:8080/diag
~~~

**Expectations:**

- `/hello.txt` -> `STATIC_VERSION=v2`.
- `/view` contains `TEMPLATE_VERSION=v2`.
- `/diag` still reports `javaMessage=java-v1`.
- `pid=P1` and `jvmStartMillis=T1` are **unchanged**.
- `contextToken=C1` is **unchanged**: no evidence of context recreation.
- If the browser has a compatible LiveReload client, it may auto-refresh; otherwise, click reload manually.

This is a **resource reload**, not an automatic application restart. The `static/**` and `templates/**` paths are excluded from the default restart trigger, even though changes can still be detected by LiveReload.

### What If the Browser Still Shows v1?

Do not rush to restart the JVM. Verify in order:

1. Does the target file inside `target/classes` actually contain v2?
2. Is the app genuinely serving resources from that classpath?
3. Does `curl` already see v2?
4. Was Thymeleaf caching re-enabled by a higher-precedence property?
5. Does the browser have a hard cache, service worker, CDN, or reverse proxy?
6. Is the LiveReload extension/client actually enabled and connected?

If `curl` already sees v2 while the browser shows stale content, the issue is usually in the browser/HTTP cache layer. If `curl` also sees v1, check resource paths, copying, and server-side caching first.

## 10. Experiment 3: Edit Java and Trigger Devtools Restart

Keep the app running from terminal A. Change the literal in `DiagnosticsController.diagnostics()`:

~~~java
"javaMessage", "java-v2"
~~~

Replacing the old line:

~~~java
"javaMessage", "java-v1"
~~~

These are **two replacement lines for the given code**, not two lines to keep simultaneously in the Java file. Save the source, then compile while terminal A is still running:

~~~bash
mvn compile
~~~

Devtools watches the classpath, so the updated class file in `target/classes` is detected. After a short pause for the watcher to let file writes settle, the application logs a restart cycle and serves requests again. **No need to stop the old JVM process**.

Call again:

~~~bash
curl -s http://localhost:8080/diag
curl -s http://localhost:8080/hello.txt
curl -s http://localhost:8080/view
~~~

**Key expectations:**

| Field/Symptom | Before Java Change | After Devtools Restart |
| --- | --- | --- |
| `pid` | P1 | **P1** |
| `jvmStartMillis` | T1 | **T1** |
| `contextToken` | C1 | **C2** (new UUID) |
| `javaMessage` | java-v1 | **java-v2** |
| `appClassLoader` | First-run application loader | New application loader (`toString` usually differs) |
| `STATIC_VERSION` | v2 | v2 |
| `TEMPLATE_VERSION` | v2 | v2 |

`contextToken` is almost certainly different because a new UUID is generated by the bean factory method, though UUIDs technically have a negligible collision probability; this is a demo marker, not a transaction ID or cryptographic guarantee. `jvmStartMillis` and PID remaining identical is strong evidence that **the JVM was not restarted**.

If `javaMessage` did not change while `contextToken` changed, Devtools may have restarted against old Java output (compiling the wrong module/output directory) or you may be calling the wrong process/port. If neither changed, check compilation, the watcher, the Devtools dependency, and the runtime environment.

**Warning:** during a Devtools restart, the web server briefly stops and re-initializes; requests arriving mid-restart can fail. Devtools is not a zero-downtime rolling deployment or production hot swap.

## 11. Experiment 4: Stop the Process and Start a New JVM

To compare with a cold start, stop the app running in terminal A using normal terminal control (e.g., Ctrl+C for `mvn spring-boot:run`), verify port 8080 has no lingering instance, then run again:

~~~bash
mvn spring-boot:run
~~~

Call:

~~~bash
curl -s http://localhost:8080/diag
~~~

Now:
- `jvmStartMillis=T2` is new, differing from `T1`.
- `pid` usually differs from P1 (do not rely on PID alone as a guarantee, since the OS can reuse PIDs).
- `contextToken=C3` is new because a fresh context was created.
- `javaMessage=java-v2` because the source was compiled in Experiment 3.
- Base classloader, restart classloader, and JVM-wide static state are all initialized from scratch.

This is a **full JVM restart**. If you previously changed JVM flags `-Xmx`, Java agents, the target JDK, or process-level environment variables in the launcher, only a **new process** picks up those startup settings.

### Testing with a Packaged JAR: Devtools' Special Boundary

After stopping the dev app, build:

~~~bash
mvn package
java -jar target/devtools-boundary-demo-0.0.1-SNAPSHOT.jar
~~~

In standard packaged JAR mode, **Devtools is disabled and the dependency is normally excluded from the JAR**. Do not expect editing `src/main/java`, `target/classes`, or `src/main/resources` to trigger a Devtools restart in the `java -jar` process.

To ship new code/resources into a packaged JAR, build a new artifact and start a new process (or deploy via your release workflow). Never force-enable Devtools remote/restart in production images as a substitute for a deployment pipeline.

## 12. Three Change Paths and Observed Outcomes

| Action | Affected Files | Expected Response |
| --- | --- | --- |
| Edit Java + compile | `target/classes/**/*.class` | Devtools application restart in the same JVM |
| Edit Java source without compiling | `src/main/java` | Unlikely to take effect in the running app |
| Edit `static/hello.txt` and copy to classpath | `target/classes/static/hello.txt` | Resource reload, no context restart by default |
| Edit `templates/view.html` and copy to classpath | `target/classes/templates/view.html` | Template reload (with matching cache config), no context restart by default |
| F5 / reload browser | Browser HTTP request | Reloads page; does not change Java classes/context |
| LiveReload browser extension receives event | Browser | Automatic browser refresh; does not mean JVM restart |
| Change dependency library JAR in base classloader | Dependency JAR | Usually requires full JVM restart to load new dependency cleanly |
| Change Maven/Gradle dependency graph | Build classpath | Rebuild and restart JVM to ensure consistent new dependency graph |
| Change `-Xmx` or `-javaagent` | JVM launch options | Full JVM restart required |
| Change OS env var read at process startup | Launch environment | New process required for new environment |
| Edit `application.properties` on watched classpath | Classpath resource/config | Can trigger Devtools restart (not just static LiveReload) |
| Edit a file outside classpath | Not watched by default | No effect unless specific reload mechanism or extra paths configured |
| Call `context.stop()` then `context.start()` | Lifecycle beans | Not equivalent to Devtools restart or JVM restart |
| Close an `ApplicationContext` | Context | Does not spawn a new JVM or trigger Devtools restart |

**Note:** "changing a dependency JAR always triggers a Devtools restart" is a false assumption. The base classloader persists across restarts; a **new JVM** is needed to consistently load a different library classpath.

## 13. Configuring Restart and Resource Reload Behavior

### 13.1. Ignoring Resources When Deciding to Restart

By default, Devtools does not restart when common resources change. To **replace the default exclusion list**:

~~~properties
spring.devtools.restart.exclude=static/**,public/**
~~~

This example comes from the official docs. However, **replacing** the exclusion list may leave previously excluded paths (like `templates/**`) unexcluded, unintentionally triggering more restarts.

To **keep defaults and only append exclusions**:

~~~properties
spring.devtools.restart.additional-exclude=reports/**,docs/**
~~~

`additional-exclude` is usually safer when you only want to ignore a few extra paths. Match paths relative to the runtime classpath root rather than guessing absolute source paths.

### 13.2. Watching Additional Paths Outside the Classpath

~~~properties
spring.devtools.restart.additional-paths=../shared-resources
~~~

This example assumes an external directory needs watching. This **adds a watch region**; it does not automatically make external files valid classpath resources or compile Java sources. Combine with exclusions if changes under that path should only trigger LiveReload instead of a full restart.

### 13.3. Trigger File to Avoid Continuous Restarts

If the IDE auto-compiles too frequently, you can require restart checks to wait for a specific trigger file:

~~~properties
spring.devtools.restart.trigger-file=.reloadtrigger
~~~

Create this file in classpath resources, for example:

~~~text
src/main/resources/.reloadtrigger
~~~

After editing other files and compiling/copying, update the trigger file on the runtime classpath. Devtools checks pending changes and restarts only if actionable changes exist. **Updating the trigger file does not guarantee a restart if no eligible changes occurred**.

The trigger file must be a **simple filename without a path**, and the corresponding file must exist on the classpath. This lets teams control when Devtools evaluates restarts, avoiding multiple restarts during a single IDE build pass.

### 13.4. FileSystemWatcher: Poll Interval and Quiet Period

Devtools uses a file system watcher with a polling interval and quiet period to avoid reading files while the compiler is still writing them. If the IDE produces batched changes and Devtools restarts too early, increase these timings:

~~~properties
spring.devtools.restart.poll-interval=2s
spring.devtools.restart.quiet-period=1s
~~~

These values trade slightly slower change detection for stability in large workspaces or high-latency file systems. Do not use them to "fix" uncopied classes in the wrong output directory: the watcher cannot detect files absent from the classpath.

### 13.5. Disabling LiveReload While Keeping Restart

~~~properties
spring.devtools.livereload.enabled=false
~~~

Disabling the LiveReload server **does not disable Devtools application restart**. You can still edit Java + compile to restart; the browser simply will not receive auto-refresh signals from LiveReload.

Note on multiple concurrent Devtools apps: documentation notes that only one LiveReload server can run at a time in that environment. If another application already occupies the server, subsequent apps may lack LiveReload even though Java restart works normally.

### 13.6. Disabling Automatic Restart

~~~properties
spring.devtools.restart.enabled=false
~~~

In `application.properties`, this setting prevents file-watching restarts. However, Devtools may still **initialize the restart classloader**. It disables watching for changes, **not guaranteeing the complete absence of the restart classloader**.

To turn off restart support completely before Spring Boot starts:

~~~java
public static void main(String[] args) {
    System.setProperty("spring.devtools.restart.enabled", "false");
    SpringApplication.run(MyApplication.class, args);
}
~~~

This is a **non-standalone snippet**: it requires `MyApplication`, imports, and the application class. The key point is that the property must be set **before calling `SpringApplication.run`**. Even better in production is keeping Devtools off the runtime classpath altogether.

## 14. When Is Starting a New JVM Mandatory?

An in-process context restart **does not recreate the JVM**. Therefore, the following changes usually require a new process:

- JVM startup options: `-Xms`, `-Xmx`, Java agents, module flags, native library paths.
- Selecting a **different JDK/JVM version**.
- Underlying dependency JARs or build classpath changes, especially classes loaded by the base classloader.
- A global library/static cache in the base classloader needing a genuine reset.
- OS environment variables read from the **process** environment at launch time.
- Native resources, state, or classloader leaks that are only fully cleared when the process exits.
- Switching to a newly built artifact or container image.
- Changes requiring coordinated restarts across a cluster or external connections.

Some application configurations can still take effect during a Devtools restart if they reside in the newly loaded classpath. Do not equate **changing a YAML application property** with **changing a JVM launch flag**.

### Is a Cold Restart Always Slower Than Devtools?

Usually slower because the JVM process must start and reload base libraries, though there is no fixed time delta. For tiny apps, the gap may be small; for large apps, classloader restarts can save substantial time.

Do not cite uncontrolled microbenchmarks claiming "Devtools is N times faster" for every app. Timing also depends on database migrations, remote config, bean initialization, filesystem speed, IDE overhead, and network calls.

### Does a Full JVM Restart Always Wipe All Data?

It clears old **heap/process state**, but does not delete data persisted outside the JVM:
- Database records.
- Disk files, uploaded assets, persistent caches.
- Redis or message queues.
- External session stores.
- Cloud services and persistent volumes.

If an application still shows old data after a JVM restart, that is likely expected persistence behavior, not Devtools failing to refresh.

## 15. Lifecycle and Cleanup in Devtools Restarts

Devtools restarts depend on closing the old context. If a bean-managed resource is not cleaned up, each restart can **leak another instance**:

~~~text
Context #1 -> executor #1 starts
     |
     +-- Devtools restart -> Context #1 closes
     |                       but executor #1 is not shut down
     |
Context #2 -> executor #2 starts
     |
     +-- Devtools restart -> Context #2 closes
                             but executor #2 is not shut down

JVM remains alive:
  executor #1 + executor #2 + ...
~~~

This is a dangerous issue in development and can lead to port conflicts, thread leaks, or classloader leaks.

### Who Is Responsible for Closing?

- Singleton `@Bean` owning a client/pool: use `@PreDestroy`, `DisposableBean`, or `@Bean(destroyMethod="close")` per contract.
- Background workers: use `SmartLifecycle.stop(Runnable)` invoking the callback once shutdown actually completes.
- File streams or request/task responses: close at the operation boundary.
- Manually created executors: the owner must call `shutdown`/`awaitTermination` per policy.
- External resources outside the JVM: need leases, timeouts, or recovery mechanisms if the process crashes.

**Do not** treat a Devtools restart as "a new JVM so all static/native resources definitely reset". That is the biggest difference from a cold restart.

### Shutdown Hook

Spring Boot 3.5 docs note that Devtools relies on the application context shutdown hook to close the context during a restart. If you disable the hook via `SpringApplication.setRegisterShutdownHook(false)`, Devtools restart may not function properly.

Do not disable the context shutdown hook in Devtools demos; if special lifecycle handling is needed for production apps, separate dev and production configurations and fully understand the cleanup contract.

### ApplicationRunner and Startup Events

Every time Devtools restarts the application context, the Spring Boot startup pipeline runs again, including refresh and runners. Do not put **non-idempotent** business actions inside a runner assuming it runs only once per JVM lifetime.

For example, automatically sending emails, creating payments, publishing messages, or running destructive migrations from a runner can repeat every time a developer edits a class. Use profiles, migration frameworks, idempotency guards, or separate jobs outside startup when needed.

## 16. Multi-Module Scenarios and Classloader Errors

In multi-module projects:
- Modules open in the IDE are usually loaded by the restart classloader.
- JAR dependencies usually go into the base classloader.
- A class can be loaded early via reflection or annotation scanning by a different classloader than expected.
- Same class name loaded by **two different classloaders** produces **two distinct `Class` objects**.
- Serialization with standard `ObjectInputStream` may resolve classes using the wrong classloader.

Common symptoms:
- `ClassCastException` even though the type names look identical.
- `NoClassDefFoundError` during restart that does not occur when running a clean JAR.
- Reflection cannot see expected annotations or classes.
- Local module edits are ignored when packaged as a JAR in the base classloader.
- The app only fails after the second or third Devtools restart.

### How to Isolate

1. Disable Devtools restart completely before `SpringApplication.run` and re-run in development mode.
2. If the error disappears, suspect classloader separation rather than just business code.
3. Print the classloaders of the involved types:
   - `SomeType.class.getClassLoader()`.
   - `object.getClass().getClassLoader()`.
4. Check whether the module is resolved as an output directory or a JAR.
5. Configure Devtools classloader rules when necessary instead of blindly adding dependencies.

### The META-INF/spring-devtools.properties File

Devtools supports `restart.include.*` and `restart.exclude.*` patterns to move classpath entries into the desired loader.

**Illustrative** example—adjust regexes to match your real project classpath paths:

~~~properties
restart.include.localmodule=/my-company-module-[\w\d.-]+\.jar
restart.exclude.largegenerated=/generated-library-[\w\d.-]+\.jar
~~~

Unlike `spring.devtools.restart.exclude` (which excludes resources from **triggering a restart**), `META-INF/spring-devtools.properties` controls **classloader assignment** of classpath entries. Both contain the word "exclude" but **do not do the same thing**.

Do not use `System.properties` as a replacement for this file; the documentation specifies it as configuration inside `META-INF/spring-devtools.properties` on the classpath. Property key suffixes must be distinct, and regexes apply to classpath entries rather than specific Java source files.

## 17. Troubleshooting: File Edited Yet Application Does Not Change

| Symptom | Common Cause | Check and Fix |
| --- | --- | --- |
| Edited Java, yet `/diag` still returns java-v1 | `.class` file not compiled/copied to runtime classpath | IDE Build Project or `mvn compile` |
| Compiled, yet `contextToken` unchanged | Devtools not running or watcher does not see path | Check dependency, IDE vs. packaged JAR, classpath output, `restart.enabled` |
| Resource v2 in source, HTTP still returns v1 | Not copied to runtime classpath | Compare source file and `target/classes` |
| Resource on classpath is v2, browser still shows v1 | Browser/proxy/cache, view cache | Call `curl`, hard refresh, check headers/caches |
| Browser does not auto-refresh | Missing LiveReload extension/client or server disabled/port busy | Install/enable client if needed; manual refresh still works |
| Browser auto-refreshes, yet Java behavior is old | LiveReload only refreshes the page | Compile Java to trigger a Devtools restart |
| Editing CSS triggers full context restart | Replaced default `restart.exclude`, path outside exclusions, or build touched other classes | Inspect exclusions and file timestamps |
| Editing Java triggers multiple restarts | IDE compiles in stages, quiet period too short | Increase `quiet-period`, `poll-interval`, or use a trigger file |
| Running `java -jar` expecting Devtools restart | Packaged applications disable Devtools | Use IDE / `mvn spring-boot:run` in development |
| PID changed after editing a resource | You actually restarted the process/container | Check process manager or IDE auto-restart |
| PID unchanged but `contextToken` changed | Devtools/application context restart | Confirm via `jvmStartMillis` and restart logs |
| `contextToken` changed but `javaMessage` unchanged | Stale classpath or wrong build/module | Inspect the exact class file in `target/classes` |
| `Address already in use` after restart | Old context kept socket open or another process occupies port | Inspect destroy callbacks and port owner |
| Type cast error only in dev mode | Base/restart classloader split | Inspect classloaders, test disabling restart, check include/exclude |
| Devtools unexpectedly inactive with AspectJ weaving | Automatic restart is unsupported in this mode | Adjust workflow or drop Devtools restart expectation |
| Changed JVM `-Xmx`, yet memory unchanged | Devtools restart does not create a new JVM | Stop process and launch JVM with the new flag |
| Every Devtools restart sends an email | Runner or `@PostConstruct` has non-idempotent side effect | Extract job, add guard/profile/idempotency |
| "Lots of Condition Evaluation delta logs" | Devtools logs auto-config delta on restart | Set `log-condition-evaluation-delta=false` |
| Static edit still triggers app restart | IDE/build plugin also touched classes or other resources | Check timestamps and watcher logs; copy resource individually to test |
| Reload succeeded yet session data remains | Session persistence or external session store | Distinguish app context, session, and persistent data |

### Minimal Diagnostic Procedure

1. **Check launch mode:** IDE, `mvn spring-boot:run`, `bootRun`, or `java -jar`?
2. **Check PID and JVM start time:** Did the process actually change?
3. **Check context token/generation:** Was the Spring context recreated?
4. **Identify edited file:** Java `.java`, compiled `.class`, static asset, template, or pom/JVM arg?
5. **Inspect runtime classpath:** Is the new file in the directory the app is actually serving from?
6. **Check exclusion/trigger settings:** Did you inadvertently trigger restarts for resources?
7. **Check multi-layer caching:** Template, static resource, browser, service worker, proxy.
8. **Read lifecycle cleanup logs:** Did the old context close cleanly?
9. **Check base/restart classloaders:** Are type/loading errors tied to the classloader split?
10. **Try a cold JVM restart:** If only a cold start works, isolate base classloader/process settings or leaked state.

## 18. Counterexamples and Common Misconceptions

### 18.1. "Saving a Java File Automatically Restarts Spring"

Not by default. Devtools requires the **classpath output** to change. In IDEs without auto-compile, saving only writes the source file; bytecode has not changed. Build/copy so the watcher sees the new class.

### 18.2. "LiveReload Is Java Hot Swap"

False. LiveReload targets **browser reload**. A Java method does not change just because the browser re-requests an HTTP endpoint. New Java code requires specialized class reloading or a Devtools restart.

### 18.3. "Devtools Restarts by Calling System.exit and Launching Another JVM"

False. The whole point of Devtools is that **the old JVM stays alive** and the base classloader persists; only the restart classloader and context are swapped. A cold JVM restart happens at the process-launcher level.

### 18.4. "Resource Reload Always Preserves User Sessions"

Not a universal guarantee. In a resource-only reload, the context is not recreated; yet sessions still depend on session timeouts, stores, and servers. In a Devtools restart, Devtools has defaults supporting servlet session persistence, but do not assume every session or workload is invariant.

### 18.5. "All Static Fields Reset After a Devtools Restart"

False. Static fields of classes in the restart classloader are recreated, while static fields in the base classloader can persist. Only a cold JVM restart resets all JVM process state (aside from data persisted outside the process).

### 18.6. "Setting restart.enabled=false in application.properties Means No Restart Classloader"

Not quite. Spring Boot documentation notes this property can merely disable the watcher while the classloader is still initialized. To disable it completely, set the system property before `SpringApplication.run` or exclude Devtools.

### 18.7. "Editing the Original Resource in src Is Enough for HTTP to Serve the New Version"

Not always true. The application may serve from `target/classes` or a JAR rather than directly from `src/main/resources`. Verify where the runtime loads resources from.

### 18.8. "Changing a Dependency JAR Is Automatically Applied by Devtools Restart"

Do not rely on that. Dependency JARs typically live in the base classloader; new dependencies or classpaths usually require starting a new JVM.

### 18.9. "Editing application.properties Like CSS Will Only Reload the Browser"

Generally false. Configuration properties can affect bean construction, the web server, or auto-configuration. Modifying a config file on the classpath typically triggers a Devtools restart; do not treat it like a static asset.

### 18.10. "Devtools Restart Has Zero Downtime"

No. The context and web server can close and re-initialize. Devtools is a development tool, not a zero-downtime rolling deployment or hot-upgrade strategy.

## 19. Self-Practice Exercises

**Exercise 1 — Identify the three identities:** Run the demo and record `pid`, `jvmStartMillis`, and `contextToken` from `/diag`. Identify which field measures the JVM process and which measures the context.

**Exercise 2 — Static resource reload:** Edit `hello.txt` from v1 to v2 and copy only that file to `target/classes/static`. Use `curl` to verify the HTTP response is v2 while `contextToken` matches the initial value.

**Exercise 3 — Template reload:** Edit `view.html` from v1 to v2 and copy only to `target/classes/templates`. Verify `/view` updates while JVM timestamp and context token remain unchanged.

**Exercise 4 — LiveReload with/without client:** Open a browser, edit static content with a LiveReload extension enabled and then disabled. Distinguish automatic browser refresh from the server serving new resources on manual refresh.

**Exercise 5 — Java restart:** Change `java-v1` to `java-v2` and compile with `mvn compile`. Verify `contextToken` changes while JVM start time stays the same.

**Exercise 6 — Cold restart:** Stop the process and start a fresh `mvn spring-boot:run`. Verify JVM start time changes and a new token is issued.

**Exercise 7 — Packaged JAR:** Run `mvn package`, execute `java -jar`, edit source, and compile in another terminal. Verify the packaged process does not auto-restart via Devtools.

**Exercise 8 — Disable restart:** Set `spring.devtools.restart.enabled=false` in `application.properties`, restart the dev process, then edit Java and compile. Explain why the watcher does not trigger a context restart.

**Exercise 9 — Trigger file:** Configure `.reloadtrigger`, edit a class and compile without touching the trigger file. Then update the trigger file on the classpath and observe when the restart occurs.

**Exercise 10 — Classloader issue:** Create a dependent module with a shared class; try loading it from an open project directory versus from a JAR. Compare classloaders and adjust classloader include/exclude only when an actual error occurs.

**Exercise 11 — Resource leak:** Create an executor that is not closed on context shutdown. Observe thread count across several Devtools restarts in a test environment; then add proper cleanup and compare. Never leave leaking code in production.

**Exercise 12 — Property vs. JVM flag:** Change an application property on the classpath and trigger a restart; compare with changing `-Xmx` while the process is alive. Explain why changing a JVM flag requires launching a new JVM.

## 20. Review Questions

**Question 1.** Does a Devtools restart create a new JVM process?

**Answer:** No. It swaps the restart classloader and re-initializes the Spring application context within the running JVM.

**Question 2.** What roles do Devtools' two classloaders play?

**Answer:** The base classloader holds rarely changing libraries; the restart classloader loads application code under development. Restarts usually swap only the restart classloader, speeding up the feedback loop.

**Question 3.** Does editing `.java` and simply saving guarantee an automatic restart?

**Answer:** No. The compiled classpath output must change via IDE build/auto-compile or `mvn compile`.

**Question 4.** Does serving updated CSS/HTML require restarting the context?

**Answer:** Usually not for static resources/templates excluded from restart by Devtools, provided the runtime classpath and caching allow serving the new content.

**Question 5.** Does LiveReload patch Java classes automatically?

**Answer:** No. It sends a browser refresh signal when resources change and a client supports it; Java code requires a separate compile/restart workflow.

**Question 6.** What does an unchanged PID with a changed `contextToken` indicate?

**Answer:** It aligns with a Devtools restart creating a new context inside the same JVM, especially when `jvmStartMillis` is also unchanged.

**Question 7.** What do changed JVM start time and changed `contextToken` indicate?

**Answer:** They align with a full JVM restart. The new context is a consequence of the new process.

**Question 8.** Why does `java -jar` lack Devtools auto-restart even when the POM includes the dependency?

**Answer:** Packaged applications normally disable Devtools, and repackaged archives exclude Devtools from the artifact by default.

**Question 9.** When is starting a new JVM required?

**Answer:** When changing JVM flags/JDK, underlying classpath/dependency JARs, startup OS environment variables, or wanting to reset all process state.

**Question 10.** How does `spring.devtools.restart.exclude` differ from `additional-exclude`?

**Answer:** `exclude` replaces the exclusion list; `additional-exclude` preserves default exclusions and appends patterns.

**Question 11.** How does `META-INF/spring-devtools.properties` differ from `spring.devtools.restart.exclude`?

**Answer:** The `META-INF` file with `restart.include/exclude.*` controls which classpath entries go into the base vs. restart classloader; `spring.devtools.restart.exclude` controls whether resource changes trigger a restart.

**Question 12.** Why might an app fail only after a Devtools restart?

**Answer:** Possible thread/resource leaks, static state in the base classloader, or classloader compatibility/reflection/serialization issues. Compare against a cold start and verify cleanup.

**Question 13.** What if template v2 is in `target/classes` yet the browser still sees v1?

**Answer:** Check template caching, browser/proxy/service-worker caches, exact template path, and the raw HTTP response via `curl`.

**Question 14.** Does a Devtools restart guarantee browser sessions are cleared?

**Answer:** No. Certain configs/devtools defaults support session persistence; inspect the actual session storage behavior.

**Question 15.** Should Devtools be used to hot-update a production application?

**Answer:** No. Devtools is a developer tool; production should use standard build/deploy/rollout and graceful shutdown per security and operational practices.

## 21. Official Documentation and Summary

Reference documentation for Spring Boot 3.5.16:

- [Spring Boot 3.5 — Developer Tools](https://docs.spring.io/spring-boot/3.5/reference/using/devtools.html): Devtools module, automatic restart, restart vs. reload, resources, LiveReload, trigger file, classloaders, and limitations.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.devtools.restart.*`, caching, and LiveReload properties.
- [Spring Boot 3.5 — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html): repackaging and JAR distribution.
- [Spring Boot 3.5 — Web Servlet / Static Resources](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): static content, templates, and resource serving paths.
- [Java 17 — ProcessHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessHandle.html): process identification when observing the JVM.
- [Java 17 — RuntimeMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/RuntimeMXBean.html): `getStartTime()` and JVM runtime information.

### Key Takeaways

1. **Devtools restart**: swaps the restart classloader and application context inside the **same JVM**.
2. **Resource reload**: static assets/templates are served anew **without necessarily recreating the context**.
3. **LiveReload**: auto-refreshes the browser when a compatible client is active; not Java hot swap.
4. **Full JVM restart**: new Java process; heap, base classloader, and startup flags are loaded from scratch.
5. Devtools **watches the runtime classpath**, not reading changes in `src/main/java` automatically unless compiled.
6. Static/templates are normally **excluded from restarts**; proper runtime classpath and cache policies are required.
7. Compare `pid + jvmStartMillis + contextToken` to verify the true boundary.
8. Standard packaged `java -jar` **does not activate Devtools**; never use Devtools in production.
9. When changing dependency JARs, JDK, `-Xmx`, or process OS environment variables, use a **new JVM**.
10. Proper lifecycle cleanup is still mandatory across Devtools restarts: the JVM does not reset resources lingering in the base classloader.
