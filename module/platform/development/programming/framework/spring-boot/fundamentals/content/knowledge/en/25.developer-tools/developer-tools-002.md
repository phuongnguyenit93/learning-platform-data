# Automatic Restart Based on Classpath Changes

During Spring Boot application development, developers continuously edit controllers, services, configurations, or templates and re-run the app to check the results. Having to stop the JVM, relaunch the application, and wait for all dependencies to load every single time makes the edit–run–verify loop sluggish.

**Spring Boot DevTools** provides a key capability: **automatic restart based on classpath changes**. When it detects that files in monitored classpath directories have changed and settled, DevTools can close the current application context and restart the application **within the same JVM process** using a new classloader for the code under active development.

The core idea is not "saving a Java file makes Spring Boot compile it automatically." Automatic restart reacts to **classpath changes**, such as `.class` files after an IDE build or resource files after being copied to the output directory. If you edit source code without the compiled output changing, DevTools may not see anything requiring a restart.

This lesson covers how automatic restart works, DevTools' two classloaders, how to set it up with Maven/Gradle and IDEs, distinguishing restart from browser LiveReload and JVM HotSwap, configuring exclusions and trigger files, troubleshooting, securing production environments, and hands-on exercises you can observe directly.

## 1. The Problem Automatic Restart Solves

Suppose a Spring Boot API has an endpoint:

~~~java
@RestController
@RequestMapping("/greeting")
public class GreetingController {

    @GetMapping
    public String greeting() {
        return "Hello";
    }
}
~~~

When a developer changes the returned string to `"Welcome"`, they want to call the endpoint again promptly to see the result. Without tooling support, the workflow is usually:

~~~text
Edit GreetingController.java
          |
          v
Stop the running application
          |
          v
Compile / restart the JVM
          |
          v
Wait for Spring ApplicationContext to become ready
          |
          v
Call GET /greeting again
~~~

With DevTools, while running the application in development mode:

~~~text
Edit GreetingController.java
          |
          v
IDE or build tool updates .class file
          |
          v
Classpath directory changes
          |
          v
DevTools detects change, waits for files to settle
          |
          v
Close context and restart with new classloader
          |
          v
Call GET /greeting again
~~~

The second workflow reduces manual steps and is often faster than starting a fresh JVM, because a portion of the dependencies does not need to be loaded from scratch.

### 1.1. Goals and limitations

Automatic restart is meant for the **local development loop**. It helps test code/configuration changes faster, but it is not:

- A hot-update deployment tool for production.
- An arbitrary hot-reload mechanism for every class inside the JVM.
- A Java compilation system replacing your IDE or build tool.
- A source code synchronization mechanism between a developer machine and a server.
- A tool that automatically migrates databases, preserves sessions, or keeps application state across restarts.
- A replacement for running tests after editing code.

Think of it as a tool that **reinitializes the portion of the application under development** when the classpath changes, not a feature that guarantees all runtime state is preserved.

## 2. What Is Spring Boot DevTools?

DevTools is Spring Boot's set of developer-experience utilities, including capabilities such as:

- Automatic restart when the classpath changes.
- Development-oriented defaults, such as adjusting template caching in supported technologies.
- LiveReload integration for browsers under suitable conditions.
- Other development-workflow utilities depending on the Boot version.

Primary dependency:

~~~text
org.springframework.boot:spring-boot-devtools
~~~

In a normal Spring Boot application, the restart feature is enabled when DevTools is present in an eligible runtime environment and not disabled by configuration.

### 2.1. Why is it called restart rather than recompile?

DevTools does not parse Java syntax and run `javac`. It observes **locations on the runtime classpath**, especially directories containing compiled classes and resources.

For example, with Maven:

~~~text
src/main/java/com/example/GreetingController.java
                     |
                  javac
                     v
target/classes/com/example/GreetingController.class
                     |
              DevTools observes
                     v
               Restart context
~~~

Or with Gradle:

~~~text
src/main/java/com/example/GreetingController.java
                     |
            Gradle / IDE compile
                     v
build/classes/java/main/com/example/GreetingController.class
                     |
              DevTools observes
                     v
               Restart context
~~~

If the IDE saved the source without compiling it, the `.class` file on the classpath might remain unchanged. The result is **no automatic restart**, even though the code in the editor is different.

### 2.2. What is the classpath in this context?

The classpath contains the locations the JVM/ClassLoader uses to find classes and resources at runtime. In a development project, it typically includes:

- Compiled Java class directories.
- Resource directories copied to output.
- Library dependency JARs.
- Other module output directories if they are on the runtime classpath.

Not all locations are reloaded by DevTools in the same way. DevTools is primarily designed to prioritize developer-edited classes/resources in **directories**, while stable dependency JARs are typically kept in the base classloader tier.

## 3. Two Classloaders: The Basis for Fast Restarts

A central idea of Spring Boot DevTools is using **two classloaders**.

~~~text
                  Running JVM
                       |
              +--------+--------+
              |                 |
              v                 v
     Base ClassLoader   Restart ClassLoader
     ----------------   -------------------
     Rarely changing    Project classes
     dependency JARs    Developing resources
              |                 |
              +--------+--------+
                       |
                       v
               Spring ApplicationContext
                       |
               [Classpath changes]
                       |
                       v
            Old context is closed
            Old Restart ClassLoader discarded
            New Restart ClassLoader created
            New context started
                       |
                       v
                 JVM stays alive
~~~

### 3.1. Base classloader

The base classloader typically holds libraries that rarely change: dependency JARs from Spring Framework, Spring Boot, and external libraries.

These stable classes do not have to be reloaded entirely on every restart. That is one reason restarting with DevTools can be faster than terminating the JVM and launching a new process.

### 3.2. Restart classloader

The restart classloader typically holds the project's classes and resources located in actively developed classpath directories.

When a change requiring a restart occurs:

1. The current ApplicationContext is closed.
2. Lifecycle components are requested to shut down via Spring mechanisms.
3. The old restart classloader is no longer used to serve the new context.
4. A new restart classloader is created to see the new classes/resources.
5. A new ApplicationContext is built and started up again.

This description is a conceptual model, not a guaranteed shutdown ordering for every resource across all Boot versions and custom lifecycles.

### 3.3. Restart does not create a new JVM

Unlike stopping `java` and running it again, DevTools usually restarts **inside the same JVM**. Therefore:

- The Process ID may remain the same.
- Classes loaded in the base classloader do not need to be reloaded.
- Spring's startup sequence is still executed for the new application context.
- Related lifecycle listeners and startup logic may run again.
- Resources outside the context or held by long-lived classloaders must be managed carefully.

Do not assume every static field or state outside Spring is reset. State behavior depends on which classloader holds that class, lingering references, and how resources are managed.

### 3.4. Why can classloader errors arise?

Two classes with the same fully qualified name loaded by **two different classloaders** are not treated by the JVM as the same type.

In systems using reflection, Java serialization, service loaders, or complex proxies, errors can sometimes appear such as:

~~~text
ClassCastException:
com.example.SomeType cannot be cast to com.example.SomeType
~~~

This error can be surprising because the class names on both sides are identical. One possible cause is that two versions of `SomeType` were loaded from two different classloaders.

Not every such `ClassCastException` is caused by DevTools. However, if the error only surfaces during automatic restarts, inspect the classloader boundary before changing business logic.

## 4. Adding spring-boot-devtools with Maven

In a Spring Boot Maven project, add the dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
~~~

The `optional=true` flag means that when your module is used as a dependency of another project, Maven does not automatically pull DevTools into the dependent project just because this module declares it.

For a standalone application, this configuration signals that DevTools is a development dependency rather than a business-functionality component.

### 4.1. How to run

Depending on the project:

~~~bash
mvn spring-boot:run
~~~

Or run the main class from the IDE.

To observe restarts after editing Java, ensure the IDE or Maven actually updates output classes. Running `mvn spring-boot:run` does not turn typing code in an editor into new bytecode unless a tool builds/copies the output.

### 4.2. Are Java source and target/classes always in sync?

No. For example:

~~~text
src/main/java/com/example/MessageService.java
target/classes/com/example/MessageService.class
~~~

The Java file may have been saved, yet the `.class` file in `target/classes` still holds the old content.

You need to enable appropriate automatic building in the IDE or explicitly run a compile step. Only when output files on the classpath change does DevTools receive a signal to restart.

### 4.3. No need to package a JAR on every edit

For the development loop, running directly from classpath directories is more convenient than creating a full executable JAR after every edit. Spring Boot DevTools is designed for this workflow.

If you run an executable JAR in a standard deployment manner, DevTools usually disables development restart features automatically. Do not build production workflows around swapping classes inside a running JAR.

## 5. Adding spring-boot-devtools with Gradle

With a Spring Boot Gradle plugin supporting `developmentOnly`, you can declare:

Gradle Groovy DSL:

~~~groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    developmentOnly("org.springframework.boot:spring-boot-devtools")
}
~~~

`developmentOnly` clearly marks the dependency for development and avoids including it in the runtime of packaged applications per plugin conventions.

You can run the project with:

~~~bash
./gradlew bootRun
~~~

On Windows without a Bash shell, you can use:

~~~powershell
.\gradlew.bat bootRun
~~~

### 5.1. Do not confuse bootRun with continuous compilation

`bootRun` is the task for running the application, whereas whether source files are recompiled while the app is running depends on your IDE/build workflow.

An IDE may automatically update output classes upon build. In a terminal workflow, you may need to run the corresponding compile/classes task to refresh classpath output. Do not conclude DevTools is broken just because the app-running task does not detect raw source edits by itself.

### 5.2. The Gradle daemon and DevTools restart are different mechanisms

The Gradle daemon keeps a background build process alive to speed up Gradle tasks. DevTools restart refreshes the Spring application context inside the running application JVM.

They are not the same mechanism, even though both can reduce development-loop turnaround time.

## 6. What Actually Triggers Automatic Restart?

DevTools monitors the classpath and compares the state of eligible directories during check cycles.

Changes that commonly trigger a restart:

- A new `.class` file written to the output directory.
- A `.class` file replaced after a build.
- A class deleted from the output directory.
- A resource updated in a monitored location that does not match restart exclusion patterns.
- Additional directories configured to be watched having eligible changes.

For example:

~~~text
IDE: save MessageService.java
    |
    +-- Not compiled yet
    |      |
    |      +--> target/classes unchanged
    |                |
    |                +--> Restart may not happen yet
    |
    +-- IDE build / compile
           |
           +--> target/classes/MessageService.class changes
                     |
                     +--> DevTools detects
                               |
                               +--> Restart
~~~

### 6.1. Source changes do not equal classpath changes

A crucial rule:

> **DevTools observes the runtime classpath; it does not directly watch every source file in the editor like a compiler.**

For Java, to change behavior, code must be compiled into a new class. For resources, check where the resource resides and whether the build tool copied it to output.

### 6.2. Waiting for changes to settle before restarting

A single build may update multiple files sequentially. Restarting immediately when the first file changes could cause the context to see an incompletely updated classpath.

DevTools uses a polling mechanism and a *quiet period* to wait for changes to settle before restarting.

These can be tuned:

~~~properties
spring.devtools.restart.poll-interval=2s
spring.devtools.restart.quiet-period=1s
~~~

These two values are examples only. If a build takes time to write many files, too short a quiet period can trigger a restart while outputs are still changing.

Do not raise poll interval/quiet period arbitrarily without reason: larger values slow down feedback on edits, while values that are too small can cause multiple restarts.

## 7. Complete Spring Boot Example: Observing Automatic Restart

Let's create a small application with a controller and a service. The goal is to edit code, compile, and observe DevTools restarting the context.

### 7.1. Project structure

~~~text
devtools-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/devtools/
    │   ├── DevtoolsApplication.java
    │   ├── GreetingController.java
    │   ├── GreetingService.java
    │   └── StartupReporter.java
    └── resources/
        └── application.properties
~~~

### 7.2. Maven dependencies

In a Spring Boot project that already has an appropriate parent or dependency management, add:

~~~xml
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
~~~

`spring-boot-starter-web` provides MVC and the HTTP server under normal configuration. `spring-boot-devtools` provides development restart support when run appropriately.

### 7.3. Main class

`DevtoolsApplication.java`:

~~~java
package com.example.devtools;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DevtoolsApplication {

    public static void main(String[] args) {
        SpringApplication.run(DevtoolsApplication.class, args);
    }
}
~~~

### 7.4. Service

`GreetingService.java`:

~~~java
package com.example.devtools;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String message(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

### 7.5. Controller

`GreetingController.java`:

~~~java
package com.example.devtools;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/greetings")
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping
    public String greet(@RequestParam String name) {
        return greetingService.message(name);
    }
}
~~~

### 7.6. Printing a message on context startup

`StartupReporter.java`:

~~~java
package com.example.devtools;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class StartupReporter implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "Application context started: "
                        + System.currentTimeMillis()
        );
    }
}
~~~

`ApplicationRunner` runs after context refresh and before Boot finishes startup. When DevTools restarts the context, this runner is invoked again, helping learners observe a new startup timestamp.

### 7.7. Running and testing the endpoint

Start from the IDE or run:

~~~bash
mvn spring-boot:run
~~~

Send a request:

~~~bash
curl "http://localhost:8080/api/greetings?name=Lan"
~~~

Expected result:

~~~text
Hello, Lan!
~~~

Change `GreetingService.java`:

~~~java
return "Welcome, " + name + "!";
~~~

After the IDE/build updates `GreetingService.class` on the runtime classpath, DevTools detects the change and can restart.

Call the endpoint again:

~~~bash
curl "http://localhost:8080/api/greetings?name=Lan"
~~~

Expected result:

~~~text
Welcome, Lan!
~~~

If the endpoint still returns the old string, do not rush to add Spring annotations. First confirm that the output class was actually updated and that the application is running from the right output directory.

### 7.8. Signs of a restart

In the logs, you can observe the context stopping and starting back up. Depending on the version and logging, the main thread after a restart may be named something like `restartedMain`.

Do not rely on that specific log string as a business condition. It is merely a diagnostic indicator. You can observe how many times `StartupReporter` prints or check the new response to confirm the behavior.

## 8. Configuring the IDE So Output Classes Are Updated

The IDE is a vital part of the restart mechanism. DevTools cannot see a new class if the IDE does not compile that class into the location the application uses.

### 8.1. IntelliJ IDEA

In IntelliJ IDEA, saving a file does not always automatically compile the project while an application is running. Ensure the IDE has an appropriate workflow to update output classes, for example:

- Run `Build Project` or a compile action after editing Java.
- Enable automatic build if the IDE version and project policies allow it.
- When needed, configure auto-make to operate while the app is running; exact setting names vary across IntelliJ versions.
- Verify whether the application runs using the IntelliJ classpath or via a delegated Gradle/Maven run, as output paths may differ.

What needs verification is: after building, did the `.class` file that the JVM is using actually change?

### 8.2. Eclipse and Spring Tools

Eclipse has a `Build Automatically` mechanism. When enabled and the project is properly configured, saving Java source can trigger compilation and update output classes, allowing DevTools to detect the change.

If no restart occurs, check for build errors first. When a Java file fails to compile, there is usually no valid new class output for DevTools to load.

### 8.3. VS Code

In VS Code, class-updating behavior depends on the Java extension, project importer, and how the application is launched. You may need to compile via Maven/Gradle or use the Java extension workflow to generate new output.

Do not assume the editor's "auto save" feature means "auto build" for a Java project.

### 8.4. Running from the terminal

If running `mvn spring-boot:run` or `./gradlew bootRun`, decide how class output will be updated while the process keeps running:

- Leverage IDE builds while pointing to the right output directory.
- Run the appropriate compile task when Java changes.
- Use a project-supported continuous build workflow if truly needed.
- Avoid having two tools write to the same output directory in an uncontrolled manner, which can cause race conditions or build conflicts.

**Observation goal:** the watched file has changed on the runtime classpath. How you achieve that depends on your tooling and project structure.

## 9. LiveReload and Automatic Restart Are Not the Same

DevTools can integrate LiveReload, but **LiveReload** and **automatic restart** are two different features.

**Automatic restart** reinitializes the Spring application context when classpath changes require a restart.

**LiveReload** sends a signal so a properly configured browser can refresh the page, which is typically helpful after editing resources like HTML, CSS, or JavaScript.

~~~text
Java change -> compile -> .class changes
                                |
                                v
                       DevTools restart
                                |
                                v
                       Context restarts

Static resource change -> copy to classpath
                                |
                                v
                       May not restart
                                |
                                v
                       LiveReload notifies browser
                                |
                                v
                          Browser refresh
~~~

Browsers may require an extension/client supporting LiveReload; not every browser connects automatically just because DevTools is a dependency.

### 9.1. Static content changes

Locations such as `static`, `public`, `resources`, or `META-INF/resources` typically receive default restart exclusion policies in Spring Boot DevTools for certain resources.

When these files change, DevTools may not restart the application context, yet it can still trigger LiveReload under matching conditions.

This is intentional: editing CSS/JS does not necessarily require reloading the entire context.

### 9.2. Template changes

For Spring Boot–supported template engines, DevTools can adjust defaults such as disabling template caching in development.

Depending on the template engine and resource setup, editing a template may only require a browser refresh or LiveReload without a context restart.

If the template remains stale, check:

- Was the new template saved/copied to the output location?
- Does the template engine have caching enabled?
- Is the request using the expected template?
- Is the browser caching the resource?
- Was the resource handled as a non-restarting change?

### 9.3. Disabling LiveReload

When you do not want DevTools to run the LiveReload server:

~~~properties
spring.devtools.livereload.enabled=false
~~~

This property does not mean all automatic restarts are disabled. The two features have separate settings.

### 9.4. Quick comparison

| Behavior | Automatic restart | LiveReload |
| --- | --- | --- |
| Target affected | Spring application context | Browser / LiveReload client |
| Main trigger | Classpath change requiring restart | Eligible resource change |
| Restarts context? | Yes | Not the nature of LiveReload |
| Requires browser client? | No | Usually yes |
| Typically used when | Editing Java classes, configs needing restart | Editing UI resources |
| Preserves context? | No | Possibly, if LiveReload only |

## 10. Distinguishing from JVM HotSwap

Many IDEs/debuggers support **HotSwap**: while debugging, replacing certain class definitions in the running JVM without necessarily restarting the context.

This is a different mechanism from automatic restart.

| Criterion | DevTools restart | Standard JVM HotSwap |
| --- | --- | --- |
| Mechanism | Closes context, creates new restart classloader/context | Redefines running class per JVM/debugger capabilities |
| Restarts Spring context? | Yes | Not necessarily |
| Class structure changes | Can be reloaded via new classloader | Standard HotSwap usually has significant limits |
| Beans recreated | Normally yes | Not necessarily |
| Runner/lifecycle callbacks | Can re-run | Not solely from HotSwap |
| Requires debugger? | No | Usually requires a debug session / corresponding support |
| Best suited for | General Boot development | Debug loops for supported edits |

Some plugins or extended JVMs may provide stronger hot-reload capabilities than standard HotSwap, but that is a different tooling ecosystem.

### 10.1. HotSwap can hide that the context was not reinitialized

If you change simple method logic and debugger HotSwap succeeds, the endpoint can return the new result without any restart logs appearing.

That is not a sign that DevTools is broken. The IDE may have applied the new bytecode directly. If you need to re-verify bean configurations or lifecycles, check whether a context restart is actually needed.

### 10.2. Restart is not deployment

Even when DevTools sees new code locally, production pipelines still need proper build/test/package/deploy workflows. DevTools does not replace artifact compatibility checks or release procedures.

## 11. Configuring Exclusions for Resources Not Needing Restart

Not every classpath change needs to restart the Spring context. Some static files or templates do not alter bean configuration.

Spring Boot DevTools comes with built-in restart exclusion patterns for certain resource locations, typically involving static resources, templates, and build metadata.

To add exclusions without replacing those defaults, use:

~~~properties
spring.devtools.restart.additional-exclude=generated/**,fixtures/**
~~~

For example:

~~~text
src/main/resources/
├── generated/
│   └── large-report.json
├── fixtures/
│   └── sample-data.json
└── application.properties
~~~

When output resources have paths matching the excluded patterns, updating them does not necessarily restart the context.

### 11.1. restart.exclude and restart.additional-exclude

The two properties differ:

- `spring.devtools.restart.exclude`: specifies patterns used to exclude from restart, which can replace the default exclusion set.
- `spring.devtools.restart.additional-exclude`: appends patterns to the default exclusions.

In most cases where you just need to exclude a few extra custom folders, **prefer `additional-exclude`** to keep the default behavior for static assets/templates.

For example:

~~~properties
spring.devtools.restart.additional-exclude=reports/**,external-cache/**
~~~

### 11.2. Do not exclude code that needs a restart

If you exclude too broadly:

~~~properties
spring.devtools.restart.exclude=**
~~~

you may prevent most changes from triggering restarts as expected. Never use a catch-all exclusion pattern unless the purpose is completely clear.

### 11.3. Excluding from restart does not mean removing from the classpath

A resource excluded from restart **does not disappear from the application**. It simply is not used as a restart signal under that mechanism. The file can still be read via `ResourceLoader` if it is on the classpath.

This differs from configuring Maven/Gradle to omit a file from build output.

## 12. Watching Additional Paths

Sometimes an application depends on a directory outside the classpath that you want DevTools to watch when edited.

You can configure:

~~~properties
spring.devtools.restart.additional-paths=/opt/myapp/shared-config
~~~

This is an example path for Linux or container environments. On Windows, the path must match the development machine's filesystem.

`additional-paths` gives DevTools an extra location to observe. It **does not automatically place files in that directory onto the Java classpath**, nor does it bind their contents as Spring properties if the project has no mechanism to read them.

### 12.1. When should you use it?

- A module uses configuration files outside the project.
- A resource directory is generated by an external tool.
- Shared development data lives in a common directory.
- You want the application to restart when edits affect initialization logic.

### 12.2. When should you avoid it?

If a directory contains logs, cache files, or continuously changing data, watching the whole directory can cause repeated restarts and disrupt your development flow.

Specify a narrow path; avoid pointing to overly broad directories like an entire home directory or a build directory containing frequently changing outputs that do not require a restart.

## 13. Trigger File: Restart Only When You Explicitly Trigger It

Sometimes a build updates many classes/resources, and you do not want the context to restart mid-way. Spring Boot DevTools supports a **trigger file**: restarting only when a designated trigger file is updated under the watcher mechanism.

Configuration:

~~~properties
spring.devtools.restart.trigger-file=.reloadtrigger
~~~

Create a trigger file named `.reloadtrigger` in an appropriate classpath location, for example:

~~~text
src/main/resources/.reloadtrigger
~~~

Ensure this file is actually copied to the runtime classpath. A file that only sits in source resources but is skipped by the build tool cannot act as a trigger observable by DevTools.

### 13.1. Usage workflow

1. Edit one or more Java classes.
2. Compile to update output classes.
3. Finish preparing all changes you want to apply.
4. Update the timestamp/content of the trigger file on the classpath.
5. DevTools detects the trigger and performs the needed restart.

Conceptual example:

~~~text
Edit A.java + B.java + C.java
        |
        v
IDE/Build compiles classes
        |
        v
No restart needed on each edit
        |
        v
Update .reloadtrigger
        |
        v
DevTools performs one intentional restart
~~~

### 13.2. A trigger file does not mean calling an endpoint to restart

This is a file-watching mechanism, not an HTTP endpoint. Never build a public API allowing arbitrary users to send a "restart application" request based on this feature.

### 13.3. A common point of confusion

The property:

~~~properties
spring.devtools.restart.trigger-file=.reloadtrigger
~~~

is a **file name**, not an absolute filesystem path. DevTools needs to find the trigger file where the classpath can reach it according to its rules.

If using an IDE that updates output resources automatically, editing the source trigger file may copy it to output. Otherwise, check the output path before assuming DevTools is ignoring the trigger.

## 14. Disabling Automatic Restart When Needed

Certain development scenarios call for temporarily disabling restarts:

- Debugging a lifecycle race where restarts interfere.
- Running benchmarks or measuring stable startup times.
- Using a library with incompatible classloader behavior.
- Developing with another tool that already handles restarts.
- Testing runtime state that must persist until explicitly stopped.

### 14.1. Disabling via application.properties

~~~properties
spring.devtools.restart.enabled=false
~~~

In this usage, DevTools stops performing standard automatic restarts, yet some internal DevTools components—including initializing the restart classloader—may still be set up depending on timing and property sources.

If you need to **completely disable the restart infrastructure**, set the system property early enough before `SpringApplication.run`.

### 14.2. Disabling completely before run()

~~~java
@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        System.setProperty(
                "spring.devtools.restart.enabled",
                "false"
        );

        SpringApplication.run(Application.class, args);
    }
}
~~~

Setting the system property before running Boot prevents the restart mechanism from being activated from the start, which is useful when troubleshooting specific classloader errors.

This snippet should only be used with clear intent, as it removes DevTools' benefits in the development workflow.

### 14.3. Omitting the dependency from environments not needing DevTools

In some cases, the simplest approach is not placing DevTools on that environment's runtime classpath. Do not ship DevTools to production only to rely on a protective property.

### 14.4. Disabling LiveReload separately

If you simply do not want browser refreshes:

~~~properties
spring.devtools.livereload.enabled=false
~~~

Automatic restart can continue working. Conversely, disabling automatic restart does not mean all caching mechanisms, LiveReload, or other development tools are disabled.

## 15. Development-Only: Do Not Use DevTools as a Production Strategy

DevTools is designed for development environments. Spring Boot usually detects when an application runs as a fully packaged artifact and disables development-oriented DevTools features.

This means:

- Running from an IDE with an appropriate output directory: DevTools restart can work.
- Running via an appropriate Maven/Gradle development task: DevTools can work.
- Running an executable archive in production: DevTools-based restart is normally not enabled in development mode.
- To release a new version: use build/test/release/deploy pipelines instead of swapping classes inside a running artifact.

### 15.1. Why restrict the dependency?

DevTools uses defaults geared toward coding convenience, not production policy. File watching, LiveReload, and remote development features (if supported/configured) are not things you want accidentally exposed in a real deployment.

With Maven, `optional=true` helps limit propagation across the dependency graph. With Gradle, `developmentOnly` expresses the exact intended usage.

### 15.2. Do not enable remote DevTools casually

If your Spring Boot version supports remote DevTools, it is a development mechanism requiring strict protection, not a general-purpose administration endpoint.

Do not configure remote restart on production servers or expose secrets/endpoints just to avoid redeploying. For production, use CI/CD and proper rollout mechanisms.

## 16. Configuring the Two Classloaders When Conflicts Arise

In most projects, DevTools picks sensible classloaders: project output directories go in the restart classloader, while dependency JARs sit in the base classloader.

However, some multi-module applications or libraries creating proxies/serializing objects may need adjustments.

DevTools supports a special configuration file:

~~~text
META-INF/spring-devtools.properties
~~~

Properties with prefixes like `restart.include.` or `restart.exclude.` allow specifying which classpath entries should be handled by the restart or base classloader based on matching patterns.

Illustrative example:

~~~properties
restart.include.shared=/shared-library-[\\w.-]+\\.jar
restart.exclude.generated=/generated-model-[\\w.-]+\\.jar
~~~

These patterns apply to **classpath entry URLs**, not arbitrary globs of Java source files. The expressions above are illustrative only; in real use, verify against your project's actual URLs and dependency packaging.

### 16.1. When should you adjust include?

If a library/project module changes frequently but resides in the base classloader, you can consider moving that classpath entry into the restart classloader so it reloads alongside application classes.

### 16.2. When should you adjust exclude?

If a specialized component misbehaves when reloaded through the restart classloader, you can consider moving that entry to the base classloader.

Changing classloaders can affect many beans, serialization types, and static state. Do not add include/exclude rules by guesswork without confirming the classloader is the root cause.

### 16.3. A safe diagnostic approach

1. Determine whether the error only happens on DevTools restart or also on a clean JVM startup.
2. Disable the restart infrastructure early enough to compare behavior.
3. Inspect the classpath entry containing the involved class.
4. Examine how objects need to communicate across the two classloaders.
5. Only after confirming a mismatch should you consider `spring-devtools.properties`.

If an error disappears after disabling restart, that is a valuable clue, though not yet proof that include/exclude rules are the immediate fix. You may need to fix a resource leak, serialization boundary, or how `Class` objects are cached.

## 17. Automatic Restart and ApplicationContext Lifecycle

DevTools restart closes the current context and recreates it. Consequently, startup callbacks can execute again.

For example:

~~~java
@Component
public class StartupInitializer implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Load reference data...");
    }
}
~~~

After each restart, `run(...)` may be called again. If the code inside has side effects—such as inserting duplicate rows into a database—you must design for **idempotency**.

### 17.1. Runners should not assume they run only once per JVM lifetime

In development with DevTools, a single JVM can host multiple sequential application contexts. Thus, "once on startup" does not mean "once until the process is killed."

For migrations, seed data, and startup tasks:

- Use dedicated migration tools where appropriate.
- Design operations to run repeatedly without corrupting data.
- Distinguish temporary development data from production data.
- Do not place critical side effects inside a listener that only makes sense during local experiments.

### 17.2. @PostConstruct, @PreDestroy, and @Bean lifecycle

Bean creation/destruction callbacks for the old and new contexts can be invoked following the Spring lifecycle.

A bean managing connections, thread pools, or scheduled tasks must clean up properly when the context closes; otherwise, lingering threads or file handles can hold references to the old classloader and cause memory leaks.

### 17.3. State inside beans can be lost

Suppose a singleton bean holds a counter:

~~~java
@Service
public class CounterService {

    private int value;

    public int next() {
        return ++value;
    }
}
~~~

After a DevTools restart, the new context typically creates a new bean, so the counter returns to its initial state.

Do not use in-memory singleton state to store data that must survive restarts. If data needs persistence, choose appropriate storage and manage its lifecycle.

### 17.4. Static state is not always reset

Some classes loaded by the base classloader survive restarts; their static fields do not necessarily disappear.

Do not rely on "DevTools restart will wipe every static cache," nor on "static caches are guaranteed to stay intact." It depends on classloader ownership and cross-module references.

## 18. How Restart Affects Connections and Background Tasks

Because the old context is closed, resource-managing beans typically must shut down and be recreated:

- The HTTP server and related web beans.
- Context-managed connection pools.
- Spring-managed schedulers or executors.
- Message broker consumers.
- In-memory caches and bean state.
- Resource loaders, clients, and other configuration beans.

Exact behavior depends on configuration and lifecycle implementations.

### 18.1. In-flight requests may be affected

DevTools restart should not be viewed as a graceful rolling deployment. A request currently being processed may be interrupted or the client may experience a temporary connection error during context restart.

This is acceptable in many local development workflows, but unsuitable for serving production traffic.

### 18.2. Background threads must be managed

If the application spawns threads manually:

~~~java
new Thread(() -> {
    while (true) {
        // ...
    }
}).start();
~~~

without a way to stop them when the context closes, those threads can keep living after restart and retain references to the old classloader.

Use a Spring-managed executor/scheduler or a lifecycle component like `SmartLifecycle` when coordinated shutdown is needed. If you must create threads manually, provide cancellation flags, interruption handling, and cleanup invoked on context close.

### 18.3. External state can still persist

DevTools restart does not reset databases, Kafka topics, Redis, written files, or systems external to the application. Therefore, restarting the context does not mean resetting everything back to an initial test state.

If a manual test requires clean data, use a dedicated seed/reset strategy instead of relying on automatic restart.

## 19. Does Automatic Restart Help with application.properties Changes?

DevTools can detect changes in configuration resources when they reside on the watched classpath and are not excluded from restarts.

For example, editing:

~~~properties
app.greeting.prefix=Hello
~~~

to:

~~~properties
app.greeting.prefix=Welcome
~~~

If the IDE/build copies the updated file from `src/main/resources/application.properties` to the output directory, that change can trigger a restart. When the new context is created, Spring Boot reloads configuration from effective property sources.

However, distinguish three steps:

1. You edit the source configuration file.
2. The actual file on the runtime classpath is updated.
3. DevTools detects the change and restarts.

If step 2 does not occur, the application may continue using the old configuration.

### 19.1. Externalized configuration

If configuration resides outside the runtime classpath, such as a file mounted from a separate path, DevTools does not watch it by default. You may need `additional-paths` or another refresh mechanism depending on the architecture.

### 19.2. Restart vs. runtime rebinding

Restart creates a new context and rebinds bean configuration properties. This differs from a **dynamic config refresh** feature that keeps the context alive and updates values on running beans.

Spring Boot DevTools is not a dynamic configuration management solution for production.

## 20. Common Errors and How to Find the Root Cause

### 20.1. Saved Java file but application did not restart

**Symptom:** Source file changed, logs show no restart, and endpoint still returns the old result.

**Common cause:** IDE did not compile, so `.class` output did not change.

**Resolution:** Build the project or compile the class; verify the `.class` file on the runtime classpath was updated.

### 20.2. Compiled but still no restart

Possible reasons:

- DevTools is not on the runtime classpath.
- The application is running from a packaged JAR, so development restart does not behave like an IDE run.
- `spring.devtools.restart.enabled=false`.
- Build output differs from the runtime classpath the app is using.
- The file is in an unwatched location.
- A restart exclusion pattern excluded the change.
- A trigger file is enabled but has not been updated.

**Resolution:** check these conditions one by one; avoid changing multiple properties at once.

### 20.3. Only edited HTML/CSS and saw no restart

Some static/template resources are excluded from restart by default. DevTools may only emit LiveReload if the environment supports it.

**Resolution:** check resource output, template caching, and browser LiveReload. Do not treat the absence of a context restart as an error when only UI files changed.

### 20.4. Edited application.yml but new value did not apply

**Cause:** the new file was not copied to the classpath, the app is reading another external config with higher precedence, or no restart happened.

**Resolution:** inspect resource output, effective property sources, and restart trigger/exclusion settings.

### 20.5. DevTools restarts continuously

**Cause:** a file in a watched path is being updated repeatedly; a tool generates resources after each startup; the IDE/build modifies multiple files sequentially.

**Resolution:** locate the volatile folder/file, narrow watched paths, add `additional-exclude`, consider a trigger file, or tune the quiet period.

### 20.6. Continuous builds causing too many restarts

**Cause:** changes are written in multiple batches spaced far enough apart to look settled.

**Resolution:** consider `spring.devtools.restart.quiet-period`, a trigger file, or a build workflow applying the batch at once.

### 20.7. ClassCastException after restart

**Possible cause:** two classloaders own incompatible class definitions across the classloading boundary.

**Resolution:** compare against a run without restart, check dependency/module placement, and consider `META-INF/spring-devtools.properties` if needed.

### 20.8. Port remains occupied after restart

**Possible cause:** the application created a server/socket outside the Spring lifecycle that did not close when the old context shut down, or another process is using the port.

**Resolution:** manage resources via bean lifecycle; check which process/socket holds the port. Do not assume DevTools always releases manually created resources.

### 20.9. Startup data inserted multiple times

**Cause:** an `ApplicationRunner` or startup listener creates data with side effects and runs again in every new context.

**Resolution:** design idempotent initialization or move migrations/seeding to proper tooling.

### 20.10. Used JVM HotSwap and saw no restart logs

**Cause:** the debugger applied new method bytecode without restarting the context.

**Resolution:** distinguish HotSwap from DevTools; if you need to test a fresh lifecycle, trigger an actual classpath restart.

### 20.11. DevTools accidentally shipped to production

**Cause:** misconfigured dependency/runtime profile or customized build artifact altering how DevTools is excluded.

**Resolution:** use Maven `optional` or Gradle `developmentOnly`, keep production artifacts lean, inspect dependency composition, and never use remote development tooling on real servers.

### 20.12. Assuming restart preserves in-memory state

**Cause:** confusing context restart with swapping a method implementation on a living object.

**Resolution:** treat beans as recreatable; use external stores for data that must persist and design explicit shutdown/reinitialization.

## 21. Diagnostic Checklist When Restart Does Not Occur

When Java edits do not change results, follow an observable sequence:

1. **Confirm the app is running in development mode** via an IDE, `spring-boot:run`, or `bootRun` appropriately.
2. **Confirm DevTools is present on the runtime classpath** and not excluded from the run configuration.
3. **Confirm restart is enabled** and no system property disables it early.
4. **Verify the source compiles successfully**; no Java errors block the build.
5. **Verify the output directory for the active class** changed after the build.
6. **Check exclusion patterns and `trigger-file`** to see if the change is ignored or waiting.
7. **Wait long enough for polling/quiet period** and observe context restart logs.
8. **Call the endpoint or task again** to observe the new behavior.
9. **If an error occurs on restart**, try a clean run without restart to isolate classloader issues.
10. **Only then adjust tuning properties** to lower latency or adjust classloaders.

This sequence prevents confusing compilation, runtime classpath, and DevTools issues with one another.

## 22. Observing Restart Timing and Application Impact

You can create a component to log whenever a new context starts:

~~~java
@Component
public class RestartObservation implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(RestartObservation.class);

    @Override
    public void run(ApplicationArguments args) {
        long pid = ProcessHandle.current().pid();

        log.info(
                "Context initialized, process id = {}",
                pid
        );
    }
}
~~~

When DevTools restarts, the startup log can appear again in the same JVM and the PID typically stays unchanged.

This helps distinguish it from the OS or IDE stopping the old process and spawning a new one.

If a startup task loads a database or connects to an external service each time, observing logs also shows how many times the task re-executes.

### 22.1. Additional indicators

Besides PID and logs, you can track:

- New context startup timestamps.
- Number of times runners execute.
- Number of times bean lifecycle methods are invoked.
- Classloader type of classes in the project.
- Responses from a test endpoint.
- Time elapsed from compile until the endpoint serves traffic again.

These observations help understand the feature, but should not become production logic depending on DevTools.

## 23. Hands-On Exercises

### Exercise A: Test restart after changing a service

Create a project with `spring-boot-starter-web` and `spring-boot-devtools`. Write `GreetingService.message()` returning `"Hello"` and a controller returning that result.

Run from the IDE, call the endpoint, and change the value to `"Welcome"`. Compile the project and observe DevTools restart. Call the endpoint again to verify the new class is used.

### Exercise B: Prove save does not equal compile

Disable your IDE's automatic build if applicable, edit Java source, and only save the file. Observe that the application does not restart yet.

Then build the project, verify the `.class` output changes, and observe the restart. Explain the path from source to classpath.

### Exercise C: Observe the two classloaders

In a runner, print:

~~~java
System.out.println(
        GreetingService.class.getClassLoader()
);
System.out.println(
        org.springframework.boot.SpringApplication.class.getClassLoader()
);
~~~

Observe the classloaders of the application class and the framework class. After a restart, check which one shows signs of being recreated.

Do not use the classloader's `toString()` string as a stable contract across Boot versions; use it only for illustration.

### Exercise D: Compare a Java class with a static resource

Create:

~~~text
src/main/resources/static/site.css
~~~

Edit the CSS, update resource output, and observe whether the context restarts or only LiveReload occurs. Then edit a Java class, compile, and compare.

### Exercise E: Add an excluded directory

Create a directory:

~~~text
src/main/resources/generated/
~~~

Configure:

~~~properties
spring.devtools.restart.additional-exclude=generated/**
~~~

Edit a resource in that directory and observe the behavior. Compare it with changing a project `.class` file.

### Exercise F: Trigger file

Enable:

~~~properties
spring.devtools.restart.trigger-file=.reloadtrigger
~~~

Create the trigger file on the classpath, compile several Java edits, and then update the trigger once. Observe whether DevTools restarts right when you intentionally trigger it.

### Exercise G: Disable restart in two ways

Try:

~~~properties
spring.devtools.restart.enabled=false
~~~

Then try setting the system property before `SpringApplication.run`. Compare the behavior and explain why the second approach is helpful when you need to eliminate the restart classloader infrastructure altogether.

### Exercise H: Observe state and runner

Create a singleton `CounterService` with an incrementing counter and an `ApplicationRunner` logging timestamps. Call the endpoint to increment the counter, then edit a class and restart.

Observe the bean state and runner. Explain why restarting does not mean database data is reset too.

### Exercise I: Inspect application packaging

Run the project using the development workflow, then package an executable JAR and run it via `java -jar` in the standard way.

Compare DevTools behavior and explain why automatic restart is not used as a production update strategy.

### Exercise J: Diagnose a restart loop

Create a file updated periodically under a watched path in a test environment. Observe repeated restarts; then exclude the directory from restarts or use a trigger file.

Do not run continuous-restart experiments on environments serving real users.

## 24. Self-Check Questions

**1. What changes does automatic restart rely on?**

It relies on changes detected by DevTools in watched classpath locations or additional paths, not merely saving `.java` files in an editor.

**2. Does DevTools automatically compile Java source?**

No. The IDE or build tool must update class outputs so DevTools sees new bytecode.

**3. Why is restarting usually faster than starting a new JVM?**

DevTools usually retains the base classloader for stable dependencies and only recreates the restart classloader/context for the code under development.

**4. Does restart create a new Java process?**

Normally no. The context restarts inside the same JVM process.

**5. When should you add the `spring-boot-devtools` dependency?**

In development environments where you want restarts and DevTools utilities. In Maven it is usually declared `optional=true`; in Gradle you can use `developmentOnly`.

**6. Why does editing CSS not always restart the context?**

Some static resources are excluded from restarts by default; such changes may only trigger LiveReload/browser refresh.

**7. Is LiveReload the same as DevTools restart?**

No. LiveReload mainly serves browser refresh, whereas restart reinitializes the Spring context.

**8. How does JVM HotSwap differ from automatic restart?**

HotSwap can redefine running classes within JVM/debugger limits, whereas DevTools restart creates a new context and restart classloader.

**9. What is the purpose of `spring.devtools.restart.additional-exclude`?**

To append patterns that should not trigger context restarts while retaining default exclusions.

**10. What is `spring.devtools.restart.trigger-file` used for?**

To allow restarting via a trigger file only when changes are ready, avoiding restarts mid-way across multiple build passes.

**11. Does `spring.devtools.restart.enabled=false` always eliminate all restart classloader mechanisms?**

Do not assume so if the property is only read during application initialization. To completely disable the restart infrastructure, set the system property early enough before `SpringApplication.run`.

**12. Why might a class cast error appear only after a DevTools restart?**

Because some classes may be loaded by different classloaders across two context generations, making type identity incompatible across the classloader boundary.

**13. Do @PostConstruct or ApplicationRunner run again?**

They can run again when the new context creates beans and starts up. Startup side effects should be designed idempotently.

**14. Does DevTools restart erase database data?**

No. Context restart does not automatically reset external storage.

**15. Should remote DevTools be enabled in production?**

No. DevTools is a development tool, not a production deployment or administration mechanism.

## 25. Conclusion

**Automatic restart based on classpath changes** is a helpful development feature of Spring Boot DevTools. Once Java code is compiled or resources are copied into watched classpath locations, DevTools can detect the changes, wait for output to settle, and close and restart the Spring application context within the same JVM.

The two-classloader mechanism explains why restarting is often faster than launching a new JVM: stable dependency JARs can remain in the base classloader, while project classes are reloaded through the restart classloader. However, it also explains risks of classloader mismatches, bean state resets, and startup callbacks running again.

When using DevTools, remember these key distinctions:

- **Saving source does not equal compiling:** restart needs to see changes on the runtime classpath.
- **Automatic restart is not LiveReload:** one restarts the context, the other mainly refreshes the browser.
- **Automatic restart is not JVM HotSwap:** one creates a new context/classloader, the other can redefine running classes.
- **Restart is not production deployment:** do not use DevTools to update user-facing applications.
- **Configure intentionally:** use `additional-exclude`, `additional-paths`, `trigger-file`, `poll-interval`, and `quiet-period` when genuinely needed.

Understanding the exact boundaries between editor, compiler, classpath, classloader, and application context lets you leverage Spring Boot DevTools to shorten the development loop without confusing build, runtime, or deployment problems.
