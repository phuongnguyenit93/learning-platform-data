# Resources Requiring Restart, Excluded Resources, and Trigger Files

During Spring Boot application development, we frequently edit Java classes, YAML files, HTML templates, CSS, or JavaScript and inspect the results. Stopping the JVM and restarting manually after every edit slows down the development loop, especially when an application has many beans, repositories, security configurations, and infrastructure connections.

**Spring Boot DevTools** shortens the development loop by watching changes in eligible paths and automatically **restarting the ApplicationContext** when needed. However, not every change needs to reinitialize the application. Modifying a Java service differs from modifying a CSS file or template. DevTools therefore provides mechanisms for:

- **Resources requiring restart:** changes significant enough to recreate the application context and reload classes.
- **Resources excluded from restart:** changes that can be served directly or update the browser without restarting the entire context.
- **Additional watched paths:** notifying DevTools about resources residing outside standard classpath directories.
- **Trigger file:** a file acting as a switch; only when you explicitly update this file do pending changes trigger a DevTools restart.

To use these effectively, you need to understand **which files DevTools watches**, **whether the IDE/build tool has placed changes onto the runtime classpath**, and **the differences among restart, LiveReload, and manual UI refresh**.

This lesson focuses on properties such as `spring.devtools.restart.exclude`, `spring.devtools.restart.additional-exclude`, `spring.devtools.restart.additional-paths`, and `spring.devtools.restart.trigger-file`, along with Maven, Gradle, IDE, multi-module examples, and common pitfalls.

## 1. DevTools Is a Tool for the Development Loop

Spring Boot DevTools is a set of development-support utilities. One notable capability is **automatic restart**: when watched files change, DevTools closes the current application context, creates a new context, and uses an appropriate classloader mechanism to load the new class versions.

Example loop:

~~~text
Edit OrderService.java
        |
        v
IDE or build tool compiles
        |
        v
OrderService.class in output directory changes
        |
        v
DevTools detects classpath change
        |
        v
Close old context, create new context
        |
        v
Application runs with updated code
~~~

Key point: DevTools is **not a compiler**. It does not automatically turn edited `.java` files into bytecode. If the IDE has not compiled or output classes have not changed, DevTools may see no reason to restart.

### Restart is not starting the JVM from scratch

During a typical restart, the running JVM is kept alive while eligible Spring application components are recreated. DevTools uses a multi-classloader mechanism to reduce the cost of reloading unchanged libraries.

This differs from:

~~~text
Stop java process
        |
        v
Launch a new java process
        |
        v
Load entire JVM, classpath, framework, and application
~~~

By keeping the JVM and base libraries that do not need reloading on every turn, a restart can be faster than a cold start. However, that does not mean all runtime state is cleanly reset: static state in base-classloader classes or improperly cleaned resources can create differences compared to starting a fresh process.

### DevTools should only be used during development

Auto-restart and DevTools utilities are not a production hot-deployment mechanism. In a fully packaged application, Spring Boot usually disables DevTools features meant for development; meanwhile, dependencies should be configured so DevTools is not accidentally propagated into deployed artifacts.

Production should rely on official deployment, restart, and health-check pipelines from your operational platform.

## 2. Adding DevTools to a Project

In a Maven project already using Spring Boot dependency management:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
~~~

`optional=true` prevents DevTools from accidentally becoming a required transitive dependency of modules depending on this project. Whether DevTools ends up in the final artifact also depends on packaging plugins and build configuration.

In Gradle Kotlin DSL, you can use the development-oriented configuration:

~~~kotlin
dependencies {
    developmentOnly(
        "org.springframework.boot:spring-boot-devtools"
    )
}
~~~

With Gradle Groovy DSL:

~~~groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

`developmentOnly` expresses intent much more clearly than putting DevTools in production runtime dependencies. Build tool plugins and versions must support that configuration.

### An illustrative project structure

~~~text
store-service/
├── pom.xml
├── src/
│   └── main/
│       ├── java/
│       │   └── com/example/store/
│       │       ├── StoreApplication.java
│       │       └── OrderService.java
│       └── resources/
│           ├── application.yml
│           ├── static/
│           │   ├── css/site.css
│           │   └── js/app.js
│           └── templates/
│               └── order.html
└── target/
    └── classes/
        ├── com/example/store/...
        ├── application.yml
        ├── static/
        └── templates/
~~~

With Maven, `target/classes` is typically the classpath output directory. With Gradle, there may be output directories like `build/classes/java/main` and `build/resources/main`. DevTools watches the actual classpath entries the application runs with, not just the `src` folder name.

## 3. DevTools Watches the Classpath, Not Simply Source Files

A frequent point of confusion:

> I edited `OrderService.java` and saved it—why hasn't Spring Boot restarted yet?

The reason may be that DevTools is watching `OrderService.class` on the runtime classpath, while the IDE has not recompiled the source file.

Full flow:

~~~text
src/main/java/OrderService.java
                  |
                  | IDE/build tool compiles
                  v
target/classes/.../OrderService.class
                  |
                  | DevTools FileSystemWatcher observes
                  v
            Restart trigger
~~~

Similarly for resources:

~~~text
src/main/resources/templates/order.html
                  |
                  | Resource copy or IDE output sync
                  v
target/classes/templates/order.html
                  |
                  v
           DevTools observes
~~~

If resources reside in an external classpath directory used directly at runtime, the copy flow may differ. Still, the rule remains checking **the actual path placed on the classpath and watched**.

### Typical working environments

- **Eclipse / Spring Tools:** automatic build typically updates output classes upon file save.
- **IntelliJ IDEA:** may require building the project or configuring auto-build appropriately while the app is running.
- **VS Code with Java tooling:** verify whether the Java extension or build workflow updates output directories.
- **Maven / Gradle CLI:** how you launch and compile determines when output files change.

If running a packaged JAR and editing external sources, the JAR does not change by itself. Do not expect DevTools inside a packaged application to read raw source and reload.

## 4. Two Classloaders in DevTools Restart

A typical restart mechanism uses two classloaders:

1. **Base classloader:** holds reusable libraries/inputs.
2. **Restart classloader:** holds classpath entries of the application under development, typically open directories.

Diagram:

~~~text
                     JVM stays alive
                            |
       +--------------------+--------------------+
       |                                         |
       v                                         v
 Base classloader                         Restart classloader
       |                                         |
       +--> Spring Framework jars                +--> OrderService.class
       +--> Hibernate / Jackson jars             +--> OrderController.class
       +--> Dependency jars                      +--> App configuration
       |                                         |
       +------------- Runtime context -----------+
                            |
                 When change is detected
                            |
                            v
                   Close current context
                            |
                            v
                  Replace restart classloader
                            |
                            v
                   Create new context
~~~

This model explains why DevTools restart can be faster than a cold start, and also explains a class of classloading problems in multi-module setups or libraries using reflection/serialization.

**Note:** these classloaders govern splitting classpath entries; they do not directly decide whether a CSS file is excluded from restart. Resource exclusion rules and classloader splitting are two separate configuration groups.

## 5. How Does Restart Differ from LiveReload?

DevTools is often mentioned alongside **LiveReload**, yet the two concepts differ.

**Restart** recreates the Spring application portion:

~~~text
Classpath changes
       |
       v
Close ApplicationContext
       |
       v
Create new context
       |
       v
Server/beans ready again
~~~

**LiveReload** notifies a LiveReload-capable client to refresh the page when resources change:

~~~text
CSS / template / static asset changes
       |
       v
DevTools detects change
       |
       v
Send LiveReload notification
       |
       v
Matching browser/plugin reloads page
~~~

Not every browser receives LiveReload events automatically. Usually a matching extension or client integration is needed. Without one, you can still refresh manually to see new resources.

### A restart can also trigger LiveReload

DevTools can notify LiveReload when the application restarts or supported resources change. Even so, "browser reload" and "Spring context restart" remain two separate events. When investigating why a change does not appear, distinguish:

- Has the application restarted yet?
- Is the server serving the new resource?
- Has the browser reloaded yet?
- Is the browser or template engine caching old content?

## 6. Which Resources Typically Require a Restart?

Some common change types:

| Change | Typical expected behavior | Why? |
|---|---|---|
| `OrderService.class` recompiled | Restart | Business code changed |
| `@Configuration` class changed | Restart | Bean definitions/configuration changed |
| New `@Component` appeared | Restart | Component scan needs to run again |
| `application.yml` on classpath changed | Usually restarts | Environment and bean configs need reloading |
| `application.properties` changed | Usually restarts | Property binding/conditions may change |
| Thymeleaf template in default exclusion area | No full restart needed | Template engine can re-read template when caching is suitably configured |
| CSS/JS in `static` | No full restart needed | Static resources do not require rebuilding the bean graph |
| File outside all watched paths | No automatic restart | DevTools is not notified of the change |
| Java source changed but `.class` output unchanged | May not restart yet | DevTools is not a Java compiler |

Outcomes in the table depend on real configuration: whether paths are watched, excluded, copied/built by the IDE, and whether DevTools mode is active.

### Why should application.yml trigger a restart?

Properties can determine which beans are registered:

~~~yaml
app:
  billing:
    mode: simulation
~~~

A bean configuration:

~~~java
@Configuration
public class BillingConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.billing",
            name = "mode",
            havingValue = "simulation"
    )
    BillingGateway simulationGateway() {
        return new SimulationBillingGateway();
    }
}
~~~

If `app.billing.mode` changes, merely modifying the file on disk does not cause Spring to re-evaluate every bean condition automatically. Restarting the context allows configuration conditions and property bindings to be reprocessed.

### Why does CSS not need a restart?

A file:

~~~text
src/main/resources/static/css/site.css
~~~

is normally served by the web server as a static asset. Once the updated version reaches the runtime resource location, the application does not have to recreate the `OrderService` bean just because a CSS property changed. This is why DevTools excludes certain resource directories from **restart** by default while still emitting LiveReload notifications.

## 7. Resources Excluded from Restart by Default

Spring Boot DevTools typically includes **default restart exclusions** for resources that do not require restarting the context. Common groups include classpath paths corresponding to:

~~~text
/META-INF/maven
/META-INF/resources
/resources
/static
/public
/templates
~~~

These are illustrative path groups based on Spring Boot documentation; exact pattern/exclusion syntax can vary across versions. When you need the exact list, consult the documentation for the Spring Boot version your project runs.

Typical meaning:

- `static` and `public` usually hold static files served over HTTP.
- `templates` usually holds templates such as Thymeleaf.
- `META-INF/resources` can contain static web resources.
- `META-INF/maven` holds Maven metadata.
- `resources` is a resource location used in web serving by convention.

When resources excluded from restart change, DevTools can still watch the changes and emit LiveReload. **Excluding from restart does not always mean ignoring the file completely.**

### Default exclusions do not remove resources from the classpath

A file in `static` is still served by the application. DevTools exclusion rules only affect the decision of whether to restart the ApplicationContext when the file changes.

Do not confuse:

~~~text
Exclude from DevTools restart
          !=
Exclude resource from JAR or runtime classpath
          !=
Block access to static resource
          !=
Completely ignore all changes to the resource
~~~

Those are separate concerns belonging to build packaging, resource handling, and DevTools.

## 8. spring.devtools.restart.exclude: Replacing the Exclusion List

You can configure:

~~~properties
spring.devtools.restart.exclude=static/**,public/**
~~~

Or YAML:

~~~yaml
spring:
  devtools:
    restart:
      exclude: "static/**,public/**"
~~~

The `spring.devtools.restart.exclude` property specifies resource patterns that do not need to trigger a restart.

**Common pitfall:** when configuring `exclude` yourself, you are supplying an exclusion list used **instead of the corresponding defaults**. If you only list two patterns while the system previously excluded templates, metadata, and other groups, this change can stop those default groups from being treated as expected.

Therefore, do not use `spring.devtools.restart.exclude` merely to "add one extra folder," unless you intentionally want to manage the entire exclusion list.

### When should you intentionally replace the entire exclude list?

For example, a project has special runtime resources where changing certain templates or metadata must cause a context restart rather than just LiveReload. You can redesign the exclude list and intentionally **omit** that group from exclusions.

Keep the consequence in mind: unexcluded files can cause frequent application restarts while developers edit UI files.

### Patterns match resource paths, not URL routes

Example:

~~~properties
spring.devtools.restart.exclude=static/**,public/**
~~~

Patterns match paths inside the watched area, not raw request URLs like `/css/site.css`. Configuration must be checked against the actual classpath structure.

If a file is absent from the output location or outside monitored roots, even a valid exclude pattern will not make DevTools detect it.

## 9. spring.devtools.restart.additional-exclude: Appending to Defaults

To **keep default excludes** and append new patterns, use:

~~~properties
spring.devtools.restart.additional-exclude=generated-docs/**,frontend-cache/**
~~~

YAML:

~~~yaml
spring:
  devtools:
    restart:
      additional-exclude: "generated-docs/**,frontend-cache/**"
~~~

This is suitable when a project has a resource directory updated continuously that does not affect the bean graph.

Example structure:

~~~text
src/main/resources/
├── application.yml
├── templates/
├── static/
├── generated-docs/
│   ├── api-index.html
│   └── search-data.json
└── frontend-cache/
    └── manifest.json
~~~

If `generated-docs` is only served as static documentation, emitting LiveReload or refreshing individually may be enough. Restarting the entire context every time files regenerate wastes time.

### Comparing exclude and additional-exclude

| Property | Goal | Effect on defaults |
|---|---|---|
| `spring.devtools.restart.exclude` | Define excluded resource groups | Can replace the default exclusion list |
| `spring.devtools.restart.additional-exclude` | Append exclusion patterns | Preserves default exclusions |
| `spring.devtools.restart.additional-paths` | Add extra paths to watch | Not an exclusion list |
| `spring.devtools.restart.trigger-file` | Restart only when trigger file updates | Does not replace file classification logic |

**Rule of thumb:** if you just need to add one or two folders that should not restart the context, start with `additional-exclude`.

## 10. Example: Frontend Assets Built Continuously

Suppose a frontend build tool writes artifacts to:

~~~text
store-service/
├── src/main/java/...
├── src/main/resources/
│   └── static/
└── frontend/
    ├── src/
    └── dist/
        ├── index.html
        ├── app.js
        └── site.css
~~~

If the development pipeline copies `frontend/dist` onto the classpath on each build, every frontend compile can generate bursts of file changes.

Typical solutions include:

1. Deliver built assets to the location served by the backend.
2. Avoid full Spring context restarts just because HTML/CSS/JS are rewritten.
3. Let the browser reload via LiveReload or manual refresh.
4. Control caching so updates are actually served.

For instance, if the destination is `static`, default exclusions may already suffice. If outputs are copied into another folder on the classpath, you can add a matching pattern:

~~~yaml
spring:
  devtools:
    restart:
      additional-exclude: "frontend-build/**"
~~~

Crucial point: the pattern must match **the path seen by the watcher**, not just a folder name in the source repository.

### Do not accidentally exclude backend configuration files

If you place `application.yml` inside an excluded folder, editing properties that control beans may fail to restart the context. Thus, only exclude resources that can genuinely be consumed without reinitializing the application.

A folder mixing Java configuration outputs and static assets usually needs structural separation before adding broad exclusion patterns.

## 11. spring.devtools.restart.additional-paths: Watching Additional Paths

By default, DevTools watches eligible classpath directories. A project might also use resources or configuration files residing outside the normal classpath.

Example:

~~~text
workspace/
├── store-service/
│   ├── src/main/java/...
│   └── src/main/resources/...
└── shared-development-config/
    ├── banner.txt
    └── mock-partners.yml
~~~

To have DevTools watch `shared-development-config`, configure:

~~~properties
spring.devtools.restart.additional-paths=../shared-development-config
~~~

YAML:

~~~yaml
spring:
  devtools:
    restart:
      additional-paths:
        - ../shared-development-config
~~~

Example paths are resolved relative to the runtime environment and property evaluation; check the working directory, absolute vs. relative paths, and actual read permissions of the process.

### Watching extra paths does not automatically place resources on the classpath

This is a very important distinction:

~~~text
Add to additional-paths
         |
         +--> DevTools can detect file changes
         |
         X--> Does NOT automatically turn files into classpath resources
         X--> Does NOT auto-inject files into Spring Environment
         X--> Does NOT auto-define beans or config imports
~~~

If the application needs to load external config files, there must be a corresponding loading mechanism—such as Config Data imports or application code reading the files. `additional-paths` only participates in **watching and triggering development behavior**, not replacing data-loading mechanisms.

### When to use additional-paths?

Some scenarios:

- Templates developed in a directory outside the main module.
- Test/mock configurations sitting outside classpath output.
- A frontend build directory used directly by the backend during development.
- Shared resources across modules absent from watched classpath directories.
- Files generated by external tools that need to trigger reload/restart when changed.

If changing a file neither affects application state nor requires a browser reload, there is no need to watch it.

## 12. Combining additional-paths with Exclusions

Files inside `additional-paths` may change frequently. DevTools lets you use exclusion rules to control which changes require a restart versus which should only trigger LiveReload.

Conceptual example:

~~~text
../shared-dev-assets/
├── templates/
│   └── invoice.html
├── images/
│   └── logo.svg
└── config/
    └── invoice-rules.yml
~~~

Desired behavior:

- Editing `invoice.html` or `logo.svg`: no restart needed.
- Editing `invoice-rules.yml`: context must reload if rules are bound on startup.

Illustrative configuration:

~~~yaml
spring:
  devtools:
    restart:
      additional-paths:
        - ../shared-dev-assets
      additional-exclude: "templates/**,images/**"
~~~

**Verify patterns against the structure seen by the watcher.** When additional watched paths lie outside the classpath, matching semantics can depend on the root base used by the watcher. Do not assume patterns written by URL or source tree always match correctly.

The goal of combining these is to separate:

~~~text
Additional paths
      |
      +--> Meaningful changes for Spring configuration -> restart
      |
      +--> Excluded static/template changes          -> reload without restart
~~~

### Can an external folder reload without restarting?

Simply editing a file and emitting LiveReload does not guarantee the backend reads the new content. If the application copied that file at startup, reloading the browser alone will not update the copy. You must design the resource flow properly: either read directly from the external directory at runtime or run an appropriate copy/sync step.

## 13. What Is a Trigger File?

In a large project, a single build may write **many class and resource files** over several seconds. If the watcher reacts before file writes finish, the app may restart while the classpath is still changing.

In addition to tuning poll interval and quiet period, DevTools provides a **trigger file**: a file watched as an "I am ready to restart" signal.

Example configuration:

~~~properties
spring.devtools.restart.trigger-file=.reloadtrigger
~~~

Or YAML:

~~~yaml
spring:
  devtools:
    restart:
      trigger-file: ".reloadtrigger"
~~~

Once the trigger file is located on the classpath, DevTools performs restarts based on changes to the trigger file instead of restarting immediately whenever other files change.

### Why is a trigger file useful?

Without a trigger file:

~~~text
Compile A.class
      |
      +--> Restart
Compile B.class
      |
      +--> Restart again
Copy config
      |
      +--> Restart again
~~~

This illustrates a build with spaced write batches; real watchers do have a quiet period to coalesce changes, so they do not necessarily restart on every single file.

With a trigger file:

~~~text
Compile A.class
Compile B.class
Copy config
         |
         | Build complete
         v
Update .reloadtrigger
         |
         v
DevTools restarts once
~~~

A trigger file is especially useful when developers want to control **when restarts happen** rather than ignore changes.

## 14. Creating and Placing the Trigger File Properly

A common structure:

~~~text
src/main/resources/
├── application.yml
└── .reloadtrigger
~~~

The `.reloadtrigger` file can be empty. Its filename is configured via:

~~~properties
spring.devtools.restart.trigger-file=.reloadtrigger
~~~

Normally this property specifies **a file name**, without requiring full directory paths in the value. DevTools needs to find the trigger file on the classpath.

With Maven, after resources are copied:

~~~text
target/classes/.reloadtrigger
~~~

With Gradle, it may reside in:

~~~text
build/resources/main/.reloadtrigger
~~~

depending on how the IDE/build tool configures the runtime classpath.

### Having the file in src/main/resources alone is not enough

If you create:

~~~text
src/main/resources/.reloadtrigger
~~~

but the build tool or IDE has not copied it to the output directory used by the app, DevTools may **fail to find the trigger file on the classpath**.

Therefore, verify three things:

1. The file exists in source or a managed location.
2. The file appears on the **runtime classpath**.
3. When updated, its timestamp/content changes where the watcher observes it.

### Do not arbitrarily put an absolute path into trigger-file

This example is not the usual intended configuration:

~~~properties
spring.devtools.restart.trigger-file=/home/user/project/target/classes/.reloadtrigger
~~~

The trigger file property is designed to specify a filename looked up on the classpath. Watching an external directory is the job of `additional-paths`; the two mechanisms have different purposes.

## 15. How to Trigger a Restart Using a Trigger File

Once DevTools and the trigger file are configured, a development workflow can look like:

1. Edit one or more Java classes.
2. Let the IDE/build tool compile/copy everything cleanly to the output directory.
3. Update the trigger file watched by the application.
4. DevTools detects the change and performs a restart per its mechanism.

Example in a Unix shell, if Maven output is actively used by the app:

~~~bash
touch target/classes/.reloadtrigger
~~~

Or with Gradle:

~~~bash
touch build/resources/main/.reloadtrigger
~~~

Make sure the file exists and is on the runtime classpath; paths are examples only.

In PowerShell on Windows:

~~~powershell
$p = "target/classes/.reloadtrigger"
(Get-Item -LiteralPath $p).LastWriteTime = Get-Date
~~~

If you only touch the source file:

~~~bash
touch src/main/resources/.reloadtrigger
~~~

there must be a copy/sync mechanism to the output directory so the watcher sees the updated timestamp. In IDEs that automatically copy resources on save, editing the source file may suffice; in other workflows, resource processing must be triggered.

### You can change file content instead of only updating the timestamp

Some file-sync tools or version control systems have quirks around timestamps. Writing new content to the trigger file is a clear way to ensure the file genuinely changed:

~~~bash
date > target/classes/.reloadtrigger
~~~

This is strictly a development-environment action. Do not put file-modification commands in production code.

## 16. Trigger Files Are Not Deployment Commands

A trigger file only coordinates DevTools automatic restarts inside a running development runtime. It does not:

- Compile Java sources automatically.
- Guarantee resource copying has finished.
- Perform database migrations safely.
- Deploy JARs to production servers.
- Ask Kubernetes to restart pods.
- Reload all caches or resources outside the Spring context.
- Create a new JVM from scratch.

Distinction diagram:

~~~text
Edit source
   |
   v
Build/compile/copy
   |
   v
Update trigger file
   |
   v
DevTools context restart
   |
   v
Local/dev app uses new classes/resources
~~~

If the application runs in production containers from immutable images, do not use trigger files to replace image rollout pipelines.

## 17. Trigger Files and Excluded Resources

Suppose a batch of edits consists only of:

~~~text
static/css/site.css
templates/order.html
~~~

and these paths are excluded from restart. If the browser only needs the new resources, a full Spring context restart is unnecessary.

If you configure a trigger file, do not assume **every touch of the trigger file guarantees a restart** in all situations. Final behavior depends on which changes DevTools observed, whether they qualify as restart-worthy, and how the active version handles trigger files.

What to aim for:

- Resource-only changes should serve/LiveReload properly.
- Java class or application configuration changes trigger restarts when activated.
- The trigger file itself should not accidentally be excluded from the watched scope.
- Do not use overly broad exclusion patterns that defeat the trigger's purpose.

### When trigger is configured and Java edits do not restart immediately

That can be **intended behavior**: DevTools is waiting for the trigger file to change. Verify you updated the right file on the runtime classpath before concluding restarts are broken.

## 18. Using Trigger Files in an IDE

Some IDEs automatically compile and copy batches of files as soon as a developer saves. This is convenient, yet can cause DevTools to restart before you finish a series of edits.

A trigger file enables an intentional loop:

~~~text
Edit a group of source files
          |
          v
IDE build / compile
          |
          v
Run checks/unit tests per project workflow if desired
          |
          v
Intentionally touch .reloadtrigger
          |
          v
Observe Spring Boot restart
~~~

This is helpful when the application has noticeable startup time or the editor emits continuous file changes.

### Choosing recognizable trigger file names

Names such as:

~~~text
.reloadtrigger
.restart-trigger
.spring-restart
~~~

all work if consistent with the property and classpath. Pick one name and document it consistently so team members do not create competing trigger files.

### Empty files may be skipped by tooling

Certain resource filters, packaging rules, or IDEs skip dotfiles or empty files by default. If the trigger is not recognized, inspect the actual file inside the runtime output directory.

Do not assume that because a file sits in the repository, the running JVM sees it too.

## 19. Tuning Watch Cadence: poll-interval and quiet-period

DevTools uses a watcher mechanism to detect file changes. If a toolchain writes classes/resources in multiple bursts, you want to avoid restarting while files are still being written.

You can tune:

~~~properties
spring.devtools.restart.poll-interval=2s
spring.devtools.restart.quiet-period=1s
~~~

General meaning:

- **`poll-interval`:** how often the watcher checks for changes.
- **`quiet-period`:** how long things must remain quiet before treating a write batch as settled.

These are illustrative values, not fixed recommendations for every machine.

### Observation example

~~~text
0.0s  Build starts writing A.class
0.3s  Build writes B.class
0.6s  Build writes application.yml
1.1s  Build finishes
         |
         v
Watcher waits for quiet period
         |
         v
Restarts once changes have settled
~~~

If the watcher starts restarting too early or repeatedly, tune these two properties according to real file-write timings.

### Do not raise every timeout excessively

If you make the quiet period too large, the edit–run loop becomes sluggish. If you make it too small, the classpath may not have settled and multiple restarts occur. Balance responsiveness against your IDE and build tool characteristics.

### When is a trigger file better than tuning polling?

If the issue is simply a build taking a couple seconds to copy files, tuning the quiet period may suffice. If developers **want explicit control over when restarts happen**, a trigger file fits better.

You can combine both, though avoid adding complex settings when defaults are already stable.

## 20. Example Configurations for Different Scenarios

### Case A: small application, using defaults

~~~yaml
spring:
  application:
    name: store-service
~~~

If DevTools is already on the development classpath, usually no extra restart properties are needed. Java class edits trigger automatic restarts when outputs update; default resources like static/templates already have suitable exclusions.

Try this option first. Over-customizing too early can create patterns that are hard to diagnose.

### Case B: adding a folder that does not need restarts

~~~yaml
spring:
  devtools:
    restart:
      additional-exclude: "generated-docs/**,assets-cache/**"
~~~

Retains default excludes and adds two folders generated during development.

### Case C: managing a custom exclusion list

~~~yaml
spring:
  devtools:
    restart:
      exclude: "static/**,public/**,templates/**"
~~~

This configuration explicitly defines the exclusion list. Understand this does not merely add folders to defaults; other default exclusions may no longer apply.

### Case D: watching external configuration

~~~yaml
spring:
  devtools:
    restart:
      additional-paths:
        - ../shared-dev-config
~~~

DevTools can detect file changes in the additional directory. If the application needs to read those files, a separate config-loading mechanism is still required.

### Case E: multi-step build, using a trigger file

~~~yaml
spring:
  devtools:
    restart:
      trigger-file: ".reloadtrigger"
      poll-interval: 2s
      quiet-period: 1s
~~~

After compile/copy finishes, update `.reloadtrigger` in the output directory watched by the watcher.

### Case F: combining additional paths and exclusions

~~~yaml
spring:
  devtools:
    restart:
      additional-paths:
        - ../shared-dev-assets
      additional-exclude: "static/**,generated-docs/**"
      trigger-file: ".reloadtrigger"
~~~

This fits large projects with multiple change sources. Verify path-matching semantics and trigger behavior on your specific Boot version rather than copying it as a "standard config" for every project.

## 21. A Hands-On Maven Project

Suppose the structure is:

~~~text
inventory-service/
├── pom.xml
├── src/main/java/com/example/inventory/
│   ├── InventoryApplication.java
│   ├── InventoryController.java
│   └── InventoryService.java
├── src/main/resources/
│   ├── application.yml
│   ├── .reloadtrigger
│   ├── static/css/site.css
│   └── templates/inventory.html
└── target/classes/...
~~~

Dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
~~~

Development configuration:

~~~yaml
spring:
  application:
    name: inventory-service
  devtools:
    restart:
      additional-exclude: "generated-reports/**"
      trigger-file: ".reloadtrigger"
~~~

Illustrative workflow:

1. Run the application from an IDE or a development task whose classpath uses output directories.
2. Verify `.reloadtrigger` exists in the output directory.
3. Edit logic in `InventoryService.java`.
4. Compile to produce the new class file.
5. Update `target/classes/.reloadtrigger`.
6. Observe the context restart in the logs.
7. Call the endpoint again to verify the new behavior.

If you only edit `static/css/site.css`, the backend can serve the new file without restarting the context; the browser needs a reload or LiveReload client.

### Why not edit files directly in target/classes as permanent sources?

`target/classes` is build output. A clean/build will overwrite or delete files you edit manually there. A trigger file can be touched there as a temporary signal for the watcher; canonical sources must still reside in `src/main/resources` to survive builds.

## 22. A Hands-On Gradle Project

With Gradle:

~~~kotlin
plugins {
    id("org.springframework.boot") version "<spring-boot-version>"
    java
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    developmentOnly("org.springframework.boot:spring-boot-devtools")
}
~~~

This snippet is an illustrative skeleton; actual versions and dependency management must match the project being built.

Configuration:

~~~yaml
spring:
  devtools:
    restart:
      additional-exclude: "ui-build/**"
      trigger-file: ".reloadtrigger"
~~~

Typical output paths:

~~~text
build/classes/java/main
build/resources/main
~~~

After building/copying, verify the trigger file actually resides on the development process's classpath.

### A common point of confusion with Gradle

A build command may produce new output classes, yet that only helps DevTools restart if **the running process uses those updated classpath entries**. If the app was launched from a separate old JAR, building into a new directory does not alter the running JAR.

### Multi-project Gradle

In a project with `api`, `domain`, and `shared`, depending on how it is launched, modules can appear on the classpath as:

- Individual module output directories.
- Built JARs.

This affects which classes belong to the restart classloader and which file changes are seen by the watcher. If a module only appears as a JAR, DevTools may not treat it like an open project output directory.

## 23. Multi-Module: Why Did a Shared Module Change Without Restarting the App?

Suppose:

~~~text
workspace/
├── store-api/
│   └── Spring Boot application
├── store-domain/
│   └── Domain classes
└── store-common/
    └── Shared utilities
~~~

When running `store-api` from an IDE, `store-domain` may be placed on the classpath as an output directory so class file changes are watched.

However, if `store-common` is resolved from a JAR in the local Maven repository, editing `store-common` sources without rebuilding or updating the runtime classpath leaves the running process seeing the old JAR.

Distinguish two issues:

1. **Was the change compiled/copied onto the active classpath?**
2. **How are that classpath entry managed by DevTools' restart classloader and watcher?**

Not every multi-module issue is fixed by `additional-paths`. If the process still loads old classes from a JAR, watching a source folder alone does not give the classloader a new class version.

### Inspecting the actual classpath

An investigation checklist:

- Check whether the dependency is a project/module output or a packaged JAR.
- Check the output path containing the newly compiled classes.
- Confirm the development process uses that path.
- Check whether DevTools receives the classpath change.
- If classloading conflicts arise, check the restart classloader configuration described next.

## 24. Distinguishing Resource Restart Exclusions from Classloader Exclusions

These are two different configuration groups that are easily confused because both contain the word *exclude*.

**Group one: which file changes should trigger a restart?**

~~~properties
spring.devtools.restart.exclude=static/**,public/**
spring.devtools.restart.additional-exclude=generated-docs/**
~~~

This group controls **file-change behavior**.

**Group two: which classpath entries go into the base vs. restart classloader?**

Spring Boot DevTools supports classloader configuration via:

~~~text
META-INF/spring-devtools.properties
~~~

With keys like:

~~~properties
restart.include.project-common=/project-common-[^/]+\.jar
restart.exclude.vendor-library=/vendor-library-[^/]+\.jar
~~~

These are illustrative regex examples against classpath entries. Real patterns must match the URL/path of entries on the runtime classpath processed by DevTools, not relative `static/**` globs.

Comparison table:

| Setting | Target affected |
|---|---|
| `spring.devtools.restart.exclude` | Resource changes that do not require a context restart |
| `spring.devtools.restart.additional-exclude` | Additional resource exclusions |
| `spring.devtools.restart.additional-paths` | Extra paths monitored by the watcher |
| `spring.devtools.restart.trigger-file` | When the watcher is permitted to perform a restart |
| `restart.include.*` in `spring-devtools.properties` | Classpath entries placed into the restart classloader |
| `restart.exclude.*` in `spring-devtools.properties` | Classpath entries kept out of the restart classloader |

**Do not use `spring.devtools.restart.exclude` to fix class-identity errors between base and restart classloaders.** When a `ClassCastException` occurs between classes sharing a name but loaded by two different classloaders, analyze classloader partitioning and dependencies rather than static resource paths.

## 25. Common Classloader Errors During Restart

Some libraries use reflection, serialization, custom classloaders, or caching keyed by `Class` objects. When DevTools restarts part of the classpath, issues can occur such as:

- `ClassCastException` even though both class names in the message match.
- Objects deserialized with an old classloader.
- Threads holding references to beans/classes of a closed context.
- Libraries using static registries in the base classloader retaining objects from an old restart classloader.
- Shared module classpaths residing in an unexpected classloader.

Conceptual example:

~~~text
com.example.Order (BaseClassLoader)
          !=
com.example.Order (RestartClassLoader)
~~~

Two classes with the same fully-qualified name but different defining classloaders are two distinct Java types.

### Resolution steps

1. Identify which classloader loaded which class.
2. Check whether the entry containing the class is a directory or a JAR.
3. Check for caches/static registries retaining old references.
4. Check for background threads that failed to stop after context restart.
5. If necessary, tune `restart.include.*` / `restart.exclude.*` in `META-INF/spring-devtools.properties`.
6. Check a cold start when suspecting a restart-only issue.

Do not disable DevTools permanently to hide a serious cleanup/lifecycle bug, though temporarily disabling restart helps compare behavior and isolate causes.

## 26. Disabling DevTools Restart When Needed

When DevTools is present but you do not want automatic restarts:

~~~properties
spring.devtools.restart.enabled=false
~~~

Or:

~~~yaml
spring:
  devtools:
    restart:
      enabled: false
~~~

This setting is useful when debugging startup, running specialized integration workflows, or when restarts interfere in a development setup.

### Disabling restart via property vs. disabling completely very early

Spring Boot may still initialize some restart classloader infrastructure even if the property is read during bootstrap and disables restarts afterward.

If you need to **completely disable the restart mechanism from the very start**, set the system property before `SpringApplication.run(...)`:

~~~java
public static void main(String[] args) {
    System.setProperty(
            "spring.devtools.restart.enabled",
            "false"
    );

    SpringApplication.run(StoreApplication.class, args);
}
~~~

Or pass a JVM system property when launching the app:

~~~bash
java -Dspring.devtools.restart.enabled=false \
     -jar store-service.jar
~~~

In a packaged application, DevTools restart normally does not run as it does on an exploded development classpath. The example here contrasts **reading config at runtime** with **disabling very early**, not a recommendation to ship DevTools in packaged production applications.

### Do not confuse with LiveReload

Disabling restart differs from disabling LiveReload:

~~~properties
spring.devtools.livereload.enabled=false
~~~

An application may want to keep restarts while turning off LiveReload browser notifications. These are two separate features.

## 27. When Is Restart Not Needed?

Some changes can be served without recreating the ApplicationContext:

- CSS/JS served directly from static resource locations.
- Template engines configured not to cache templates in development.
- Documentation or image files read by the web server at request time.
- Resources with external watchers/loaders applying updates by design.

However, note: **not restarting does not guarantee running code sees the new data**.

For example:

~~~java
@Service
public class RuleService {

    private final String rule;

    public RuleService(ResourceLoader loader) {
        this.rule = loadRuleOnce(loader);
    }
}
~~~

If rules are read **once in the constructor**, modifying the file on disk while excluding it from restart leaves `RuleService` holding the stale rule.

Conversely:

~~~java
public String currentRule() {
    return loadRuleFromExternalFile();
}
~~~

re-reads the file on each call, at the cost of I/O and requiring appropriate synchronization/consistency handling.

Therefore, before excluding a resource, ask: **does the application actually have a mechanism to re-read it after the file changes?**

## 28. Template Caching and LiveReload

Spring Boot DevTools typically applies development-time defaults that surface edits faster, including reducing or disabling caches for supported template engines where applicable.

For example, when using Thymeleaf, a common development setting is:

~~~properties
spring.thymeleaf.cache=false
~~~

Once an updated template reaches the location Thymeleaf reads from, the next HTTP request can use the new template without a context restart.

### Why did I edit HTML yet the browser still shows the old page?

Possible reasons:

1. The file was not copied to the output classpath.
2. The template engine is still caching the old version.
3. Browser cache holds old content.
4. The request renders a different view template.
5. The LiveReload client is not connected.
6. The file lies outside the resource locations used by Spring.
7. A reverse proxy or CDN is caching responses.

Do not increase restart frequency to solve a browser caching issue. Identify which layer holds the stale copy.

## 29. LiveReload Is Not Always Needed

If you are only developing a REST API and testing with curl/Postman, browser LiveReload may be unnecessary. Turning off LiveReload is straightforward:

~~~yaml
spring:
  devtools:
    livereload:
      enabled: false
~~~

When developing HTML/CSS directly, LiveReload helps refresh the UI quickly. However, if you use a frontend framework with its own development server/hot module replacement, **two competing reload mechanisms** may exist.

For example:

~~~text
Vite / frontend dev server
         |
         +--> HMR for JS/CSS
         |
Spring Boot DevTools
         |
         +--> Restart backend context
         +--> LiveReload notification
~~~

In such an architecture, you might only want DevTools for the Java backend and let frontend tooling handle HMR/browser refreshes. Avoid running LiveReload on top if it wipes UI state on every frontend rebuild.

## 30. Build Size and Sequential Write Batches

A build might write:

~~~text
OrderController.class
OrderService.class
OrderRepository.class
application.yml
schema.json
templates/order.html
static/css/site.css
~~~

The watcher may see many changes in a short window. Depending on configuration, some only trigger LiveReload while others require restarts. If a build writes slowly or intermittently across files, DevTools may restart multiple times.

To reduce this:

- Ensure the IDE/build tool does not copy files in endless loops.
- Use an appropriate quiet period.
- Add a trigger file to restart only after complete builds.
- Exclude generated asset groups that do not affect the context.
- Do not place build output inside a directory watched as build input to avoid feedback loops.
- Avoid scripts rewriting the timestamp of `application.yml` without actual content changes.

### Restart loop bug

Example:

~~~text
Context startup
    |
    v
A startup job writes a file under watched classpath
    |
    v
DevTools detects change
    |
    v
Restart
    |
    v
Startup job writes the file again
    |
    v
Restart again...
~~~

This is a workflow design flaw. Move generated files out of watched areas, exclude the right path, or avoid writing unnecessary files on every startup.

## 31. Diagnostics: Edited Java Yet No Restart

Suppose you edit:

~~~java
@Service
public class PriceService {

    public BigDecimal price() {
        return new BigDecimal("10.00");
    }
}
~~~

to:

~~~java
@Service
public class PriceService {

    public BigDecimal price() {
        return new BigDecimal("12.00");
    }
}
~~~

Yet the endpoint still returns `10.00`.

Check step by step:

1. Does the application have `spring-boot-devtools` on the development runtime classpath?
2. Is automatic restart enabled?
3. Are you running from an IDE/exploded classpath or an old packaged JAR?
4. Did the IDE compile `PriceService.java` into a new `PriceService.class`?
5. Is the new `.class` file in the output directory used by the running process?
6. Is that output directory classified under a different classloader or watcher than expected?
7. Is `trigger-file` configured, forcing restarts to wait for trigger updates?
8. Do startup logs show a context restart?
9. Are multiple app instances running and are you hitting an old instance?
10. Is a caching layer or another route returning stale data?

**Do not touch `spring.devtools.restart.exclude` as your first step.** If the runtime classpath has not changed, the issue lies in compilation/copying or run target, not exclusion patterns.

## 32. Diagnostics: Edited CSS Yet Spring Restarts Everything

If editing CSS restarts the Spring context:

- Check which classpath path the CSS is copied to.
- Check whether default exclusions were overridden by `spring.devtools.restart.exclude`.
- Check whether the asset sits under `static`, `public`, or an eligible default group.
- If CSS lives in a custom folder, add a pattern via `additional-exclude`.
- Check whether the build tool also modified classes or config files simultaneously.

For instance, a frontend build might accidentally rewrite `application.yml` or a generated Java class, triggering a restart even though CSS itself is in an excluded folder.

### Typically appropriate configuration

~~~yaml
spring:
  devtools:
    restart:
      additional-exclude: "ui-output/**"
~~~

This preserves default exclusions and adds the new folder.

## 33. Diagnostics: Trigger File Does Not Work

Possible causes:

| Symptom | Possible cause | How to check |
|---|---|---|
| Editing Java still restarts immediately | `trigger-file` property not applied or file not found | Check Environment and classpath |
| Editing Java does not restart, touching trigger does nothing | Touched source file by mistake; output file unchanged | Locate runtime trigger file |
| File exists in repo but goes unrecognized | Build/IDE skips dotfiles or has not copied it | Check output resources |
| Touched right file yet no change seen | Timestamp resolution or watcher missed it | Modify content, check mtime |
| Trigger behaves inconsistently | Multiple output directories/instances, wrong working dir | Verify active process and real classpath |
| Restart happens too early during build | IDE updates trigger before other files finish copying | Update only after build or use an ordered script |
| Browser reloads without context restart | Only excluded resource changes occurred | Distinguish LiveReload from restart |
| No browser reload seen | LiveReload client disconnected or disabled | Check browser integration |

### Trigger file is a filename searched on the classpath

If using:

~~~properties
spring.devtools.restart.trigger-file=.reloadtrigger
~~~

the filename must match and the file must appear on the runtime classpath. A file sitting in a parent directory does not act as a trigger merely because its name matches.

## 34. Diagnostics: additional-paths Is Not Watched

Configured:

~~~properties
spring.devtools.restart.additional-paths=../shared-config
~~~

yet editing files there has no effect.

Possible causes:

- The relative path resolves from a different working directory than expected.
- The directory did not exist when the application started.
- The process lacks read or access permissions.
- The path is a symlink or network mount with different behavior than local watchers.
- The file is excluded by an active pattern.
- A trigger file requires explicit activation.
- DevTools restart is disabled.
- The app does not re-read the file contents even though the context restarted.
- The app reads a different copy of the edited file.

To isolate, you can test temporarily with an absolute path in development, verify existence and permissions, and then return to a portable configuration. Never hard-code personal machine paths into shared production configs.

### additional-paths is not spring.config.import

Setting:

~~~yaml
spring:
  devtools:
    restart:
      additional-paths:
        - ../shared-config
~~~

does not automatically import `shared-config/application.yml` into the Environment. If you want Spring Boot to read an external config location, use Config Data properties such as `spring.config.import` or `spring.config.additional-location` in the proper place.

## 35. Important Misconceptions

### "DevTools automatically compiles Java when I save"

Incorrect. DevTools watches changes in eligible classpath directories. Compiling source belongs to the IDE or build tool.

### "Exclude blocks the application from accessing the file"

Incorrect. DevTools exclude relates to restart decisions, not an HTTP filter or resource packaging configuration.

### "Changing a template without restarting means DevTools is broken"

Not necessarily. Templates and static assets typically belong to resources that do not require a full restart. If the browser shows stale output, check resource output, caching, and LiveReload.

### "additional-paths puts files onto the classpath"

Incorrect. It adds a watched path; it does not automatically turn resources into classpath resources or Spring configuration.

### "Trigger files reload Java sources automatically"

Incorrect. Sources must be compiled/copied to runtime output first; the trigger only decides when restart runs.

### "With trigger-file configured, every touch guarantees a restart"

Do not assume so. Outcomes depend on how the file is located and watched, which changes were recorded, and the DevTools version's configuration.

### "spring.devtools.restart.exclude and restart.exclude.* mean the same thing"

Incorrect. The first is resource change exclusion; `restart.exclude.*` in `META-INF/spring-devtools.properties` governs classloader partitioning.

### "Editing YAML updates beans without restarting"

Not necessarily. Already-initialized and bound beans usually do not pick up new values just because a file on disk changed. Restarting to rebuild the context is how DevTools usually updates development configuration.

### "DevTools restart is like hot deployment in production"

Incorrect. DevTools is a development tool, not a replacement for deployment strategies, rolling updates, or process supervision.

## 36. Combining DevTools with Tests and Builds

A typical development loop includes:

~~~text
Edit code
   |
   v
Compile / build output
   |
   +--> DevTools restart for quick manual testing
   |
   +--> Unit/integration tests to verify behavior
   |
   +--> Build artifact for deployment
~~~

DevTools restart **does not prove new code compiles across all modules**, does not run all tests, and does not replace a clean build before release.

When debugging behavior that appears only during DevTools restarts and not on cold starts, examine:

- Static/cache state retained in the base classloader.
- Whether bean cleanup releases threads/resources.
- Libraries using custom classloaders or serialization.
- Generated files modified between cycles.
- Differences between the local runtime and packaged deployment.

To compare, temporarily disable restart and start a fresh process. That is a diagnostic technique, not advice to disable DevTools everywhere.

## 37. Configuring per Development Environment

DevTools targets local environments. A team might agree on a shared development configuration:

~~~yaml
spring:
  devtools:
    restart:
      additional-exclude: "generated-docs/**,ui-build/**"
      trigger-file: ".reloadtrigger"
      poll-interval: 2s
      quiet-period: 1s
    livereload:
      enabled: false
~~~

Not every project needs all these properties. For example:

- Small projects may need only DevTools defaults.
- Projects with many generated resources benefit from `additional-exclude`.
- Projects with multi-pass builds can consider `trigger-file`.
- Projects with dedicated frontend HMR can disable LiveReload.
- Projects with external templates can use `additional-paths` if watching is genuinely needed.

Tailor configuration to your team's workflow and separate local-only defaults from deployment settings.

### Do not ship personal machine settings in releases

Avoid putting:

~~~yaml
spring:
  devtools:
    restart:
      additional-paths: "C:/Users/someone/Desktop/shared-config"
~~~

into shared application configuration. Every developer may have a different working directory. Prefer stable relative paths, environment-specific properties, or suitable launcher configurations.

## 38. Hands-On Exercise by Change Type

Suppose an application has an endpoint:

~~~java
@RestController
@RequestMapping("/api/greeting")
public class GreetingController {

    @GetMapping
    public Map<String, String> greeting() {
        return Map.of("message", "Hello");
    }
}
~~~

And a static file:

~~~text
src/main/resources/static/css/site.css
~~~

Configuration:

~~~yaml
spring:
  devtools:
    restart:
      additional-exclude: "generated-docs/**"
      trigger-file: ".reloadtrigger"
~~~

### Experiment A: edit controller

Change:

~~~java
return Map.of("message", "Hello");
~~~

to:

~~~java
return Map.of("message", "Hello, DevTools");
~~~

Then compile so output `GreetingController.class` updates. If using a trigger file, update the trigger file on the classpath after building. Once the context restart completes, calling the endpoint returns the new content.

### Experiment B: edit CSS

Change a property:

~~~css
body {
    background-color: #fafafa;
}
~~~

to:

~~~css
body {
    background-color: #f0f0f0;
}
~~~

Ensure the file is copied or served from the location holding the new content. If the static path is excluded from restart, the Spring context does not need to rebuild just for CSS changes. The browser may need a refresh or LiveReload client.

### Experiment C: edit configuration

Add to `application.yml`:

~~~yaml
app:
  greeting:
    message: "Good morning"
~~~

If a bean reads this configuration at startup, the context must be recreated so bindings and bean conditions reflect the new value, unless the application has its own runtime refresh mechanism. If using a trigger, touch the trigger once new resource output is ready.

### Experiment D: edit a file in generated-docs

Create a file in the output resource folder:

~~~text
generated-docs/index.html
~~~

If the `generated-docs/**` pattern matches, modifying this file should not trigger a full context restart merely for the resource change. Ensure the application can actually serve/read the new file if you want to see the result.

### Experiment E: verify the trigger properly

When editing Java without updating the trigger yet, observe whether the application waits. Then update the right trigger file on the classpath; this confirms both mechanisms are distinct.

This exercise aims to clarify the **relationship among file changes, compile/copy, watcher, restart, and browser reload**, rather than merely seeing a log line and assuming the entire setup works.

## 39. Quick Diagnostic Table

| Symptom | Common likelihood | Action to take |
|---|---|---|
| Java code edited yet old behavior persists | Not compiled or process uses old JAR | Check `.class` output and runtime classpath |
| Java compiled yet no restart | Trigger waiting or watcher disabled | Check `trigger-file` and restart settings |
| Every CSS edit restarts | Default excludes replaced or build also edits another file | Use `additional-exclude` and inspect output |
| New CSS not visible | File not copied, browser cache, or LiveReload disconnected | Check runtime resources and client |
| New template not visible | Template cache or wrong path | Check engine/cache/output |
| External config edit has no effect | Not watched or not loaded | Distinguish `additional-paths` and Config Data |
| Trigger file not found | File exists in source only | Verify classpath output |
| Multiple restarts in one build | Build writes in multiple batches | Tune quiet period or use trigger file |
| ClassCastException only after restart | Classloader split or stale static reference | Check `spring-devtools.properties` and lifecycle |
| Restart loop | Startup writes watched file | Move location or exclude resource properly |
| No LiveReload | Missing browser client or feature disabled | Check browser/DevTools configuration |
| Behavior differs when running JAR | Packaged classpath and DevTools behavior differ | Compare dev and release environments |
| Restart disabled via YAML yet restart classloader still present | Restart infrastructure initialized early | Use system property before `run` if full disable needed |
| Excluded resource edited yet restart still happens | Other classes/configs also changed in build | Inspect the full batch of file changes |
| `additional-paths` misses files | Wrong relative path, permissions, or symlink | Verify working directory and real path |

## 40. Design Principles to Remember

1. **DevTools is not a compiler.** Ensure your IDE or build tool updates the runtime classpath before expecting a restart.
2. **Restarts rely on changes in watched paths.** Not every source file is watched directly by the watcher.
3. **Keep default excludes if you only want to add exclusions.** Prefer `additional-exclude` over `exclude`.
4. **Do not exclude resources affecting the bean graph without a reload strategy.** For instance, configuration properties need rebinding.
5. **Use `additional-paths` to watch external sources**, remembering it does not load files into Environment/classpath automatically.
6. **Use a trigger file when you want to control restart timing.** It helps with multi-step builds or continuous IDE compilation.
7. **The trigger file must be found on the runtime classpath.** Creating it in source alone is insufficient if output is not updated.
8. **Distinguish LiveReload from ApplicationContext restart.** Browser refresh does not mean beans were recreated.
9. **Account for template/browser caching.** A new resource can exist on disk without being visible to the client yet.
10. **Tune poll interval and quiet period intentionally.** Avoid premature restarts or unnecessary delays.
11. **Distinguish resource exclusions from classloader include/exclude.** These two property groups solve two different problems.
12. **Inspect the runtime classpath in multi-module projects.** Dependency JARs and open project directories behave differently.
13. **Ensure lifecycle cleanup.** Repeated restarts can expose leaked background threads or retained static caches.
14. **Do not treat DevTools as production hot deployment.** Release pipelines use dedicated artifacts and orchestration.
15. **Use the simplest configuration that fits your workflow.** Do not add every property just because DevTools supports it.
16. **When errors occur, identify which layer has not updated.** Source, build output, watcher, context, resource cache, and browser are separate stages.

## Conclusion

Spring Boot DevTools shortens the development loop by observing changes on the development classpath and **restarting the ApplicationContext when needed**. Edits to Java classes or Spring configuration usually require a restart, while static assets and templates generally do not need to reinitialize the entire bean graph. Therefore, DevTools provides default exclusions from restart for such resources.

`spring.devtools.restart.exclude` defines a replacement exclusion list, whereas `spring.devtools.restart.additional-exclude` **appends** patterns while keeping defaults. `spring.devtools.restart.additional-paths` extends watching to directories outside the normal classpath, without automatically loading data from those directories into the application. `spring.devtools.restart.trigger-file` lets developers explicitly mark when to restart after builds/copies complete.

When facing "I edited a file, yet the application hasn't changed," walk through the chain **source → compile/copy → runtime classpath → DevTools watcher → context restart or LiveReload → browser/cache**. Identifying the exact un-updated stage solves the issue far faster than increasing restart frequency or adding arbitrary exclusions. Using these mechanisms properly preserves fast responsiveness during development while keeping a clear separation from production deployment lifecycles.
