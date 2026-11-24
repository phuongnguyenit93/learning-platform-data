# Spring Boot Devtools and Development-Time Dependency Scope

During Spring Boot application development, developers frequently edit Java code, HTML, templates, CSS, and configuration. If every change required stopping the process, rebuilding the entire JAR, and running it manually, the feedback loop would be slow. **Spring Boot Devtools** is a set of development-time tools designed to shorten the code edit → observe result cycle.

However, Devtools differs from a typical business library. It alters application behavior while running on a developer machine, uses a classpath-watching mechanism, automatically restarts the context, and modifies certain default settings. Therefore, beyond knowing how to use it, you need to understand **dependency scope** so that Devtools is present during development without accidentally becoming an operational component in production.

## 1. What Is Spring Boot Devtools?

The primary dependency is:

~~~text
org.springframework.boot:spring-boot-devtools
~~~

When added to the classpath of an application running in development mode, Devtools provides several utilities:

- **Automatic restart:** detects eligible changes on the classpath and restarts the application.
- **LiveReload:** provides a LiveReload server so compatible browsers can reload the page when resources change.
- **Development-time defaults:** adjusts certain default settings convenient for development, such as reducing template caching or providing useful diagnostic information.
- **Restart configuration points:** allows excluding directories, watching additional paths, or using a trigger file to control when restarts occur.

Devtools does not replace the compiler, build tool, or IDE. Nor is it pure Java HotSwap: when a classpath change requires a restart, Spring Boot can recreate the ApplicationContext, register beans, and re-run initialization steps.

These behaviors are primarily meaningful in the **local development loop on a developer's machine**. Production typically requires immutable artifacts, controlled lifecycles, and no components watching for source code changes.

## 2. Distinguishing Restart, LiveReload, and Build

Three operations are often collectively referred to as "auto-reload", but they are actually different.

| Mechanism | What triggers it | Result |
|---|---|---|
| IDE/compiler | Saving, building, or compiling source | Writes new classes/resources to the output directory |
| Devtools restart | Eligible changes on the watched classpath | Restarts the application portion using the restart classloader |
| LiveReload | A resource change capable of emitting a reload signal | Compatible browser reloads the page |

For example, you edit a Java class:

~~~java
@RestController
@RequestMapping("/hello")
public class HelloController {

    @GetMapping
    public String hello() {
        return "Hello from Devtools";
    }
}
~~~

Change the returned string and **compile the class** so the output classpath is updated. Devtools detects the change and performs a restart. Once the restart completes, new requests will use the new class version.

If you only save `HelloController.java` without the IDE compiling it, `HelloController.class` in the output directory might not change. Devtools watches the classpath rather than compiling every Java source file itself; therefore, a restart is not guaranteed.

Conversely, when you edit a CSS file in `static/`, the browser may need to reload to display the updated UI, but it usually does not need to reinitialize the entire ApplicationContext.

## 3. Adding Devtools with Gradle: developmentOnly

For Spring Boot applications using the Spring Boot Gradle plugin, the recommended declaration is the **`developmentOnly`** configuration:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
    id 'io.spring.dependency-management' version '<dependency-management-version>'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

In the example, the version strings are placeholders for the project's actual plugin versions, not runnable versions as-is.

If using Gradle Kotlin DSL:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "<spring-boot-version>"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    developmentOnly("org.springframework.boot:spring-boot-devtools")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

`developmentOnly` expresses that Devtools serves the development process. The configuration is supported by the Spring Boot Gradle plugin so the dependency is present on the classpath when running the application in an appropriate development workflow, while not being automatically included in the executable archive created by `bootJar` or `bootWar` under standard packaging.

### Why shouldn't it be placed in implementation?

An `implementation` dependency is part of the application's main dependency model. Devtools does not provide business APIs that production code needs to call and should not become a runtime dependency packaged into the deployed application.

Declaring:

~~~groovy
developmentOnly 'org.springframework.boot:spring-boot-devtools'
~~~

communicates the intent more clearly:

- Developers have Devtools when running in a development workflow.
- The build tool can treat the dependency differently from actual runtime libraries.
- Deployment packaging does not need to carry IDE-oriented auto-restart mechanisms.

Do not confuse `developmentOnly` with the Spring `dev` profile: this is a **build-time Gradle dependency configuration**, not an active profile of the Spring ApplicationContext.

### What if the project does not use the Spring Boot Gradle plugin?

`developmentOnly` is not a built-in default configuration that always exists in every Gradle project. It is provided and integrated by the appropriate Spring Boot plugin. For custom build scripts, you must check exactly which dependency configuration is used in the application's runtime classpath and packaged archive.

Do not copy `developmentOnly` into a plain Gradle project and assume Gradle will understand this configuration without the corresponding plugin or configuration definition.

## 4. Adding Devtools with Maven: optional dependency

In a Maven project, the common declaration is:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-devtools</artifactId>
        <optional>true</optional>
    </dependency>
</dependencies>
~~~

The `<optional>true</optional>` element is very important. In Maven, it indicates that the dependency is **optional for projects that consume the library containing that declaration**; transitively dependent projects do not automatically pull in Devtools as a required dependency.

Points to distinguish:

- `optional` is a Maven mechanism to control **transitive dependencies**.
- It is **not** a Spring profile and does not automatically activate the `dev` profile.
- It **does not mean** Devtools is excluded from every classpath of the project declaring it.
- Excluding Devtools from the executable JAR also involves the repackaging configuration of the Spring Boot Maven Plugin.

With Maven, the Spring Boot Maven Plugin excludes Devtools from the `repackage`d artifact by default (unless the project intentionally changes this behavior). As a result, `mvn spring-boot:run` in a development environment can use Devtools, while the executable JAR for deployment does not need to package it.

### Is runtime scope okay?

If the main code does not import Devtools APIs, you can explicitly declare runtime scope:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <scope>runtime</scope>
    <optional>true</optional>
</dependency>
~~~

`runtime` indicates that the dependency is not needed on the compile classpath but can be used at runtime. `optional` still serves to control transitive propagation to dependent projects.

However, do not confuse the concept of **Maven runtime scope** with the **production environment**. In Maven, a runtime dependency can be placed on the runtime classpath; excluding it from the executable archive is the responsibility of the packaging/plugin or the corresponding build process.

## 5. Comparing Dependency Scopes in Gradle and Maven

| Purpose | Gradle | Maven |
|---|---|---|
| Add Devtools for development | `developmentOnly` when using the Boot Gradle plugin | `spring-boot-devtools` dependency with `optional=true` |
| Avoid pulling Devtools transitively into other projects | Depends on Gradle's configuration and publishing model | `<optional>true</optional>` |
| Exclude from executable archive | Boot Gradle plugin handles `developmentOnly` under standard packaging | Spring Boot Maven Plugin excludes Devtools by default during repackage |
| Run application from build tool | `bootRun` | `spring-boot:run` |
| Package executable JAR | `bootJar` | `package` combined with Boot plugin's `repackage` |

It is important not to equate the two dependency scope systems by name. Maven does not have a standard `developmentOnly` like the Spring Boot Gradle plugin; Gradle also does not use `optional=true` with the same declarative meaning as in a POM.

Regardless of which build tool you use, keep this rule: **Devtools is a developer dependency, not a required component of the deployed application**.

## 6. How Does Devtools Work with Two Classloaders?

Devtools' automatic restart relies on two classloader groups:

1. **Base classloader:** typically contains libraries that rarely change, such as third-party dependency JARs.
2. **Restart classloader:** typically contains the application's classes and resources under active development in the output directory.

When an eligible change is detected, Devtools does not need to reload all dependency JARs. It can close the old context, discard the old restart classloader, and create a new restart classloader to load the updated application code.

~~~text
Initial launch
     |
     +--> Base classloader
     |      +--> Spring Framework
     |      +--> Third-party libraries
     |
     +--> Restart classloader #1
            +--> Controller
            +--> Service
            +--> Application configuration
                     |
                 Classpath changes
                     |
                     v
              Close old context
                     |
                     v
           Restart classloader #2
            +--> New Controller
            +--> New Service
            +--> New Configuration
                     |
                     v
           Create new ApplicationContext
~~~

Because the base classloader is usually retained, restarting can be faster than a full JVM cold start.

### Restart does not preserve all state

Spring singletons are recreated when the ApplicationContext restarts. State that exists only in bean memory can be lost. Connections, schedulers, and resources managed by Spring must be stopped or released following proper lifecycle hooks; avoid holding state in static singletons or unmanaged manually created threads.

If a long-running task is in progress, a restart may interrupt the task. In a development environment, this is usually an acceptable trade-off, but restart should not be misunderstood as a zero-downtime version upgrade mechanism.

### Some classloader issues

In a multi-module project, some modules may be placed in the base classloader instead of the restart classloader, causing changes in those modules not to appear as expected after a restart. Certain libraries that use reflection, serialization, or store class references in static state can also be sensitive to classloader boundaries.

When encountering hard-to-explain classloader errors, you can try running the application without restart to distinguish business logic bugs from restart classloader bugs; then adjust restart include/exclude rules if genuinely needed.

## 7. Running Devtools in an IDE

A common workflow:

1. Add the Devtools dependency with the right scope.
2. Sync the Maven/Gradle project.
3. Run the main class annotated with `@SpringBootApplication` in the IDE.
4. Edit a Java class.
5. Let the IDE compile the code into new classes in the output directory.
6. Devtools observes the classpath and restarts the application.

Example main class:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

In IntelliJ IDEA, building the project or enabling automatic build according to IDE settings can update output classes. In Eclipse, the automatic build mechanism typically compiles classes when source files change.

Exact menu names and behavior may vary by IDE version. The constant rule is that **Devtools must see changes to compiled classes/resources on the classpath**, not just uncompiled source file changes.

### When running with Gradle

With the Spring Boot Gradle plugin:

~~~bash
./gradlew bootRun
~~~

During development, `bootRun` uses the application's classpath and can include Devtools when the dependency is properly declared as `developmentOnly`. However, the `bootRun` command itself does not turn Gradle into a continuous compiler for every source change while the task is running.

You still need a workflow that updates the output classpath, such as an IDE build or an appropriate build mechanism. When Java changes are not compiled, do not expect Devtools to compile source code on Gradle's behalf.

### When running with Maven

You can run:

~~~bash
mvn spring-boot:run
~~~

The Maven plugin runs the application from the project rather than only running a packaged executable JAR. With the Devtools dependency present, automatic restart can work when compiled classes/resources change.

Maven compile or IDE build remains a separate part of the workflow. If there is no change on the classpath, Devtools has no signal to restart.

## 8. Static Files and Templates Usually Do Not Require a Context Restart

In a web application, resources under common paths such as:

~~~text
/META-INF/maven
/META-INF/resources
/resources
/static
/public
/templates
~~~

are typically treated by Devtools as resources that can change **without needing to restart the ApplicationContext**. Changes to them can emit a LiveReload signal or be served directly under development configuration.

For example:

~~~text
src/main/resources/
├── static/
│   ├── css/site.css
│   └── js/site.js
└── templates/
    └── home.html
~~~

When editing `site.css`, the web server does not necessarily have to recreate beans. If the resource file is updated in the location watched by the runtime, the browser can reload to read the new CSS.

Some template engines cache processed templates by default. Devtools applies development-time defaults that reduce caching for supported integrations, so template changes can appear without restarting.

**Do not equate this with hot-module replacement from a frontend bundler.** LiveReload usually requires reloading the page or resource in the browser; it does not replace a running JavaScript module in-place while preserving all state like a dedicated frontend HMR system.

## 9. LiveReload: When Does the Browser Refresh Automatically?

Devtools can start a LiveReload server when the development application runs. The browser needs a compatible extension, client, or tool to receive the signal and automatically reload.

LiveReload can be disabled:

~~~yaml
spring:
  devtools:
    livereload:
      enabled: false
~~~

Disabling LiveReload does not mean automatic restart is also disabled. These are two separate mechanisms: restart handles the Java/context portion of the application, while LiveReload helps the browser observe changes.

If the browser does not update automatically, you should distinguish:

- Did Devtools detect the resource change?
- Does the application need a context restart or just a page reload?
- Is the LiveReload server enabled?
- Does the browser have a compatible client and is it connected?
- Is browser cache or the frontend build pipeline holding onto an older version of the resource?

LiveReload is helpful in the web development loop, but it does not replace testing the UI under production conditions.

## 10. Controlling Automatic Restart

Devtools allows tuning change tracking to reduce unnecessary restarts.

### Disabling restart via configuration property

If you want to keep other Devtools utilities without automatic restarts, you can configure:

~~~yaml
spring:
  devtools:
    restart:
      enabled: false
~~~

This setting prevents automatic restarts. However, Spring Boot may still initialize the restart classloader mechanism at an early stage even when the property in the config file is set to `false`.

If you need to disable all restart support very early, set the system property **before** calling `SpringApplication.run()`:

~~~java
@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        System.setProperty(
                "spring.devtools.restart.enabled",
                "false"
        );

        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

You can pass the system property when launching the JVM instead of hard-coding it:

~~~bash
java -Dspring.devtools.restart.enabled=false -jar app.jar
~~~

In the final example, the behavior also depends on whether Devtools is actually present and enabled in that runtime. In a standard production executable JAR, Devtools is usually not packaged at all.

### Excluding paths that should not trigger a restart

You can add exclusion patterns:

~~~yaml
spring:
  devtools:
    restart:
      additional-exclude: logs/**,generated/**
~~~

`additional-exclude` allows appending exclusion patterns to the default list. This approach is appropriate when the application writes log files or auto-generated resources into a watched runtime area and causes overly frequent restarts.

Do not use `exclude` to replace the entire default list if your goal is only to add a few paths; using `additional-exclude` preserves the useful default rules.

### Watching an additional directory

In some projects, resources that need watching reside outside standard classpath entries:

~~~yaml
spring:
  devtools:
    restart:
      additional-paths:
        - ../shared-config
~~~

Ensure the path is meaningful relative to the process working directory and accessible by Devtools. When a change is detected, whether it triggers a restart or LiveReload depends on whether that part of the path is excluded from restarts.

### Trigger file: choosing when to restart proactively

In a large project, the IDE may compile classes in multiple batches. If Devtools restarts immediately after every batch update, continuous restarts cause disruption.

A trigger file can be used:

~~~yaml
spring:
  devtools:
    restart:
      trigger-file: .reloadtrigger
~~~

Create a file named `.reloadtrigger` on the classpath; after you finish making multiple changes, update this file's timestamp so Devtools checks the changes and performs a restart if appropriate.

The purpose of a trigger file is to **control when changes are evaluated**, not to replace the compiler. Classes still need to be built beforehand.

## 11. Development-Time Defaults and Caching

Devtools also provides convenient defaults in the development environment. For example, when working with certain template engines, template caching may be disabled by default by Devtools so file changes appear faster.

These defaults are applied through a dedicated property source and can be overridden by appropriate explicit application configuration. The exact list of properties varies by Spring Boot version and integrations on the classpath, so understand the principle rather than assuming every module has identical behavior.

For example, an application using Thymeleaf can explicitly set:

~~~yaml
spring:
  thymeleaf:
    cache: false
~~~

When comparing behavior between development and production, remember that `spring-boot-devtools` can alter caching options. If production does not include Devtools, the application may exhibit the standard caching behavior of Spring Boot / the template engine.

In other words, Devtools makes the development experience faster, but **you should not treat its defaults as a caching contract in production**. Configure important values explicitly in operational environments.

## 12. Does Devtools Work When Running a Packaged JAR?

An important distinction is between running an **exploded classpath** in an IDE/build tool and running a **fully packaged application**.

| Run method | Purpose | Devtools |
|---|---|---|
| Run main class from IDE | Fast iteration when editing code | Suitable, if dependency is present |
| `./gradlew bootRun` | Run project from Gradle | Suitable for development classpath |
| `mvn spring-boot:run` | Run project from Maven | Suitable if dependency is present |
| `java -jar app.jar` after `bootJar`/`repackage` | Run deployment artifact | Devtools is normally excluded from executable archive |
| Production container | Stable operation | Should not have Devtools restart mechanism |

By default, Spring Boot packaging plugins exclude Devtools from executable archives under standard configurations. Even if for some special reason Devtools is retained in a fully packaged application, Spring Boot detects this run mode as a production environment and typically disables development tools.

Do not try to enable Devtools in production to replace rolling deployments, health checks, graceful shutdown, or release processes. Classpath-based automatic restart is not a safe version deployment system across multiple instances.

### Distinguishing "absent from JAR" and "present but disabled"

These are two different situations:

- **Excluded from archive:** the Devtools library is not inside the executable JAR.
- **Disabled in packaged application:** the library may be on the classpath, but Devtools functionality is not activated in the detected production run mode.

Using the proper dependency scope and default packaging aims to achieve the first situation. This is cleaner and easier to control than relying solely on a property to turn off features after bringing the entire library into production.

## 13. Is Devtools Related to the Spring dev Profile?

They are two different concepts:

- `developmentOnly` or `optional` relates to **dependencies and packaging**.
- `spring.profiles.active=dev` relates to **Spring ApplicationContext configuration and beans**.

For example:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=dev'
~~~

The command above runs the application from Gradle and enables the `dev` Spring profile. If Devtools is present on the development classpath, it can operate. However, `--spring.profiles.active=dev` itself **does not add the Devtools dependency**.

Conversely, if Devtools is present without an active `dev` profile, Devtools' development utilities can still function when the application is run in an appropriate mode.

Do not decide whether to package Devtools based solely on Spring profile names. Profiles could be enabled in production deployments due to misconfiguration; dependency scope and packaging configuration must establish an independent boundary.

## 14. Why Shouldn't Devtools Be Deployed to Production?

Devtools is designed to optimize the rapid editing loop, not production operational goals. Risks of trying to keep or enable development features include:

- Unintended restarts when files or resources change.
- Bean memory state being recreated while the application is actively processing work.
- Differences in caching and diagnostic behavior compared to normal environments.
- Unnecessary expansion of configuration surface and classloader interactions.
- Increased risk if remote Devtools control features are enabled or insecurely configured.

**Remote Devtools** is a feature intended for specialized development scenarios and has its own security requirements. Do not open remote control or remote application restart capabilities in production just to update code quickly. To deploy to servers, use build/deploy pipelines, verified artifacts, and platform rollout mechanisms.

Do not hard-code secrets or expose development control endpoints. Ensure the security, network, and dependency configuration of deployment environments do not depend on Devtools.

## 15. Multi-Module Projects and Troubleshooting

In multi-module projects, Devtools may fail to restart when a shared module changes. For example:

~~~text
workspace/
├── common-domain/
├── catalog-core/
└── catalog-app/
~~~

When `catalog-app` depends on `common-domain`, classes from the dependent module may be loaded via a different loader depending on how the IDE/build tool constructs the classpath. If a class has changed but running code still sees the old version, examine the classpath paths and the classloader groups used by Devtools.

Some common errors and troubleshooting steps:

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Java edited but no restart | IDE has not compiled, output classpath unchanged | Build/compile the project; check output directory |
| Continuous restarts | Multiple compilation passes or generated files changing | Add exclusions or a trigger file |
| CSS changed but page does not update | Browser has not reloaded or resource not copied | Check LiveReload, browser cache, resource path |
| Context restarts but bean state is lost | Singleton beans are recreated | Do not store critical state only in dev context memory |
| `ClassCastException` across classloaders | Same-named class loaded by different loaders | Check multi-module classloaders and libraries using static caches |
| Running JAR and Devtools does not work | Packaged application/executable archive excluded Devtools | Use IDE/`bootRun`/`spring-boot:run` during development |
| Spring `dev` profile enabled but no auto-restart | Devtools dependency missing or classpath unchanged | Check scope and compile workflow |
| Development features accidentally appear on deploy | Dependency/packaging misconfigured | Move Devtools to development scope and inspect the artifact |

For classloader-related issues, a `META-INF/spring-devtools.properties` file can use `restart.include.*` and `restart.exclude.*` patterns to adjust which classpath entries belong to the base or restart classloader. This is a tool for specific scenarios and should be used only after understanding the application's classpath structure.

Example configuration format:

~~~properties
restart.include.shared=/common-domain-[\\w.-]+\\.jar
restart.exclude.legacy=/legacy-library-[\\w.-]+\\.jar
~~~

The patterns are illustrative examples and must be adjusted to match actual classpath entries. Do not copy them into a project without a concrete classloader issue.

## 16. A Spring Boot Development Workflow with Devtools

A sensible workflow for a web application:

1. Add `spring-boot-devtools` with `developmentOnly` in Gradle or `optional=true` in Maven.
2. Run the application from the IDE, Gradle `bootRun`, or Maven `spring-boot:run`.
3. Edit Java code and compile so the classpath changes; observe Devtools restart.
4. Edit templates/CSS and use browser reload or LiveReload as appropriate.
5. If restarts occur too frequently, use `additional-exclude` or `trigger-file`.
6. Do not store critical state in in-memory objects that only survive until the next restart.
7. Build the executable archive using the Spring Boot plugin.
8. Verify that the packaging process excludes Devtools from the deployment artifact.
9. Deploy the same artifact through the pipeline, providing environment configuration via properties/profiles/secrets per operational policy.

Gradle example:

~~~bash
# On the developer machine
./gradlew bootRun

# Before deployment
./gradlew clean bootJar
~~~

Maven example:

~~~bash
# On the developer machine
mvn spring-boot:run

# Before deployment
mvn clean package
~~~

These build commands illustrate the workflow. Devtools does not make tests or build steps unnecessary: developers can use restart for quick feedback, while the pipeline still needs to compile, test, and produce release-compliant artifacts.

## 17. Summary of Usage Boundaries

Keep three boundaries in mind:

**Dependency boundary:** Devtools is a development-support tool; use `developmentOnly` with the Spring Boot Gradle plugin or `optional=true` with Maven and keep standard packaging settings.

**Classpath boundary:** Devtools restarts when it sees eligible changes in compiled classes/resources, without automatically compiling Java source. It uses base/restart classloaders to reduce application restart time.

**Environment boundary:** Devtools serves the code-editing loop on a developer machine, not as a required component of a production executable JAR. The Spring `dev` profile does not replace dependency scope, and the Devtools dependency does not automatically enable the `dev` profile.

When you maintain these boundaries, your Spring Boot application achieves fast feedback during development while keeping deployment artifacts clean, controllable, and independent of developer auto-restart mechanisms.
