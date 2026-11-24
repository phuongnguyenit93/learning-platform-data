# Packaging, Development-Only Scope, and Inspecting Deployment Artifacts

During Spring Boot development, applications often run smoothly from an IDE or via `spring-boot:run` and `bootRun`. However, that **does not prove the packaged artifact can be deployed successfully**. An application may run fine on a developer's machine because the IDE supplies classpaths, dependencies, and environment variables, yet when packaged into a JAR, WAR, or container image, it can fail due to missing libraries, mismatched Java versions, unfound resources, leaked internal configs, or bundled development-only tools.

The lesson **"Packaging, Development-Only Scope, and Inspecting Deployment Artifacts"** under **Spring Boot Fundamentals → Developer Tools** focuses on three closely linked topics:

1. **Packaging:** turning source code, resources, and required dependencies into an output runnable in the target environment.
2. **Separating development-only:** keeping developer, test, and build tools out of runtime artifacts when they are unnecessary for production.
3. **Inspecting the actual artifact:** checking the exact file that will be released, rather than relying only on results from running out of source.

The goal is understanding the principles and workflows in both **Maven** and **Gradle**, while building the habit of inspecting exactly what gets shipped to servers or containers.

## 1. What Is a Deployment Artifact?

An **artifact** is a build output that can be stored, handed off, and used in the next stage of the deployment pipeline.

For Spring Boot, common artifacts include:

| Artifact | Purpose | Points to note |
|---|---|---|
| Executable JAR | Run the app via `java -jar` | Contains app code, resources, and runtime libraries following Boot's packaging layout |
| Executable WAR | Run via `java -jar` or deploy to a compatible servlet container | Structure and dependencies differ from JAR; requires proper configuration |
| Plain JAR | Library or standard JAR | Does not inherently contain full runtime dependencies and launcher for standalone execution |
| Container image | Packages the artifact with OS/JVM runtime and image config | Must verify both the JAR and how the image boots |
| Native executable | Binary built via a dedicated native-image process | Does not use executable JAR inspection steps verbatim |

In this lesson, the **executable JAR** is the primary case because it is the most common way to deploy many Spring Boot applications.

An artifact can be a valid file yet **not necessarily deployable**. There are at least four distinct verification layers:

~~~text
Did source code build successfully?
          |
          v
Does the artifact have the right structure and dependencies?
          |
          v
Does the artifact run on the target JDK/JRE and config?
          |
          v
Is the application actually ready to serve required features?
~~~

Each step can succeed or fail independently. Thus release workflows should check sequentially rather than merely looking for `BUILD SUCCESS`.

## 2. From Source Code to Deployed Application

A typical Spring Boot project:

~~~text
src/
  main/
    java/
      com/example/orders/OrdersApplication.java
      com/example/orders/OrderService.java
    resources/
      application.yml
      templates/
        receipt.html
  test/
    java/
      com/example/orders/OrderServiceTest.java
    resources/
      fixtures/
        sample-order.json
pom.xml or build.gradle
~~~

During a build, the tool typically performs steps like:

1. Resolving plugins and dependencies.
2. Compiling application source code.
3. Processing resources destined for runtime.
4. Compiling and running tests per selected lifecycle/tasks.
5. Creating the archive.
6. With the Spring Boot plugin, **repackaging** or building an executable archive with a launcher and required runtime libraries.
7. Placing the artifact in the build directory for release pipelines.

Diagram:

~~~text
src/main/java --------> compile ------+
                                      |
src/main/resources -------------------+--> classes/resources
                                      |
runtime dependencies -----------------+
                                      |
                                      v
                             Spring Boot packaging
                                      |
                                      v
                             executable JAR/WAR
                                      |
                                      v
                        deploy / java -jar / image
~~~

`src/test/java` and `src/test/resources` participate in testing, yet **should not be packaged as production application components** under standard configurations.

A common pitfall: a build can produce **multiple JAR files**. They may not share the same runnability or dependency list. Know precisely which file is the executable artifact intended for deployment.

## 3. How Does a Spring Boot Executable JAR Differ from a Plain JAR?

A regular Java JAR contains classes and resources without bundling all required dependencies. When multiple libraries are needed, the runner must configure the classpath manually.

A Spring Boot executable JAR is designed to run simply:

~~~bash
java -jar orders-api.jar
~~~

In a common Spring Boot layout:

~~~text
orders-api.jar
|
+-- META-INF/
|    +-- MANIFEST.MF
|
+-- BOOT-INF/
|    +-- classes/
|    |    +-- com/example/orders/OrdersApplication.class
|    |    +-- application.yml
|    |    +-- templates/receipt.html
|    |
|    +-- lib/
|         +-- spring-boot-*.jar
|         +-- spring-context-*.jar
|         +-- ...
|
+-- org/springframework/boot/loader/
     +-- ... launcher classes ...
~~~

Exact launcher details and locations of certain files can vary across Spring Boot versions, while the main roles remain:

- **`BOOT-INF/classes`:** application classes and resources.
- **`BOOT-INF/lib`:** bundled runtime dependency JARs.
- **Manifest and launcher:** metadata enabling `java -jar` to launch the app with Boot's dependency layout.

### How important is the manifest?

An executable JAR typically has a manifest containing entries such as:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.orders.OrdersApplication
~~~

This is an example for versions using that launcher package; do not hardcode launcher names as an immutable rule across every Spring Boot version.

**Main-Class** points to the launcher or entry point invoked by the JVM. **Start-Class** points to the Spring Boot application class when using the corresponding packaging layout.

If a JAR reports:

~~~text
no main manifest attribute
~~~

you may be running a **plain JAR** instead of the executable JAR, or packaging configuration failed to generate the right manifest.

### Not every dependency belongs in BOOT-INF/lib

Only dependencies appropriate for runtime packaging should be present. For example, test libraries like JUnit do not belong in a production JAR, annotation processors do not need to run in production processes, and devtools should be excluded from deployment artifacts.

Therefore, inspecting a JAR means checking not only "does it have application classes" but also "does it have the right dependencies without unnecessary extras."

## 4. Two Ways to Run: From Source vs. From Artifact

During development, Maven and Gradle offer convenient commands:

~~~bash
./mvnw spring-boot:run
~~~

~~~bash
./gradlew bootRun
~~~

These two commands run the app using a classpath assembled by the build tool for development tasks. Development-only dependencies can be included on that classpath.

At release time, you typically run:

~~~bash
java -jar orders-api.jar
~~~

This run must rely solely on **what is actually inside the artifact** and its surrounding runtime environment.

Comparison:

| Aspect | Running from build tool | Running executable JAR |
|---|---|---|
| Purpose | Development, debugging, quick checks | Simulating real deployment |
| Classpath | Assembled by Maven/Gradle | Launcher reads packaged dependencies |
| Devtools | May be on development classpath | Normally must be excluded from archive |
| Resources | Often from output directories | Packaged inside the JAR |
| Hidden risks | Locally available dependencies or paths | Exposes packaging/runtime omissions |
| Commands | `spring-boot:run`, `bootRun` | `java -jar` |

**Succeeding with `bootRun` does not guarantee `bootJar` will succeed.** That is why you must inspect the artifact after packaging.

## 5. Packaging Spring Boot with Maven

In a Maven project using the Spring Boot starter parent or proper dependency management, a typical plugin configuration is:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

When using the Spring Boot starter parent, the `repackage` goal execution is usually preconfigured. If **not using the starter parent**, the project may need to declare the plugin execution explicitly so the `repackage` goal runs after creating the standard JAR/WAR.

Example explicit execution when needed:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <executions>
                <execution>
                    <goals>
                        <goal>repackage</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

In a specific project, pick **one consistent plugin configuration**, avoiding redundant duplicate executions.

### The package command

On Linux/macOS, if the project has the Maven Wrapper:

~~~bash
./mvnw clean package
~~~

In Windows PowerShell:

~~~powershell
.\mvnw.cmd clean package
~~~

In a normally configured project, the artifact appears in the `target` directory:

~~~text
target/
  orders-api-0.0.1-SNAPSHOT.jar
  ...
~~~

The filename depends on the project's `artifactId`, `version`, and `finalName`.

Then run the exact file:

~~~bash
java -jar target/orders-api-0.0.1-SNAPSHOT.jar
~~~

Do not take an example filename and assume every project uses that exact name; inspect your project's own `target` directory.

### What does spring-boot:repackage do?

The `repackage` goal takes the project's JAR/WAR and reorganizes it into an executable archive following Spring Boot's model, complete with launcher and eligible dependencies.

In some Maven setups, the build keeps the original JAR as a backup such as `.jar.original`. This file is **not** the executable artifact to hand off to operations just because its name looks similar.

What to verify: which file contains `BOOT-INF/classes`, `BOOT-INF/lib`, and the right manifest for `java -jar`.

### Do not confuse package with compile

~~~bash
./mvnw compile
~~~

is a source compilation step, not proof that an executable JAR was produced. To verify a deployable artifact, run the packaging goal/lifecycle and target **the actual output file**.

Maven `package` also normally runs preceding test phases. In a CI pipeline, never skip tests just to make packaging turn green faster. This lesson describes commands for learners to practice; it does not require running builds or tests at the documentation stage.

## 6. Distinguishing Dependency Scopes in Maven

Maven provides scopes such as `compile`, `runtime`, `provided`, and `test`. They control classpaths across different phases.

| Maven Scope | Mainly used when? | What to think about during packaging? |
|---|---|---|
| `compile` | Dependency needed at compile and usually runtime | Normally included in the corresponding runtime archive |
| `runtime` | Dependency unnecessary at compile time yet needed at runtime | Normally included in the executable JAR |
| `provided` | Dependency expected to be supplied by the environment | Depends on archive type and deployment model |
| `test` | Library solely for compiling/running tests | Must not be placed in production executable JARs as a runtime dependency |

Example:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

When using Spring Boot dependency management, starter versions are managed centrally. There is no need to declare individual versions per starter when managed by a BOM/parent.

### Do not confuse optional with test scope

In Maven, `<optional>true</optional>` serves a different role from `<scope>test</scope>`.

- `test`: dependency intended for the test classpath.
- `optional`: mainly indicates the dependency should not be transitively propagated to projects depending on this artifact. It **does not mean** the dependency is automatically omitted from every packaging format or every run mode.

Therefore, with devtools, you must understand both the dependency declaration and the **devtools exclusion behavior** of the Spring Boot Maven Plugin.

## 7. Packaging Spring Boot with Gradle

In a Gradle project with the Spring Boot plugin configured, the key task is:

~~~bash
./gradlew clean bootJar
~~~

In Windows PowerShell:

~~~powershell
.\gradlew.bat clean bootJar
~~~

`bootJar` builds an executable JAR following Spring Boot's layout. Output usually appears under:

~~~text
build/libs/
  orders-api-0.0.1-SNAPSHOT.jar
  ...
~~~

To run it:

~~~bash
java -jar build/libs/orders-api-0.0.1-SNAPSHOT.jar
~~~

As with Maven, exact filenames depend on project configuration.

### bootJar vs. jar

With the Spring Boot Gradle plugin, you may see two tasks:

- **`jar`:** builds a standard plain Java JAR.
- **`bootJar`:** builds an executable JAR using Spring Boot's structure.

In some projects, both tasks produce outputs. The plain artifact may carry a classifier like `plain` or another name set by Gradle configuration.

Example directory:

~~~text
build/libs/
  orders-api-0.0.1-SNAPSHOT.jar
  orders-api-0.0.1-SNAPSHOT-plain.jar
~~~

Never pick files using wildcards assuming every JAR in the directory is equivalent. Identify which file comes from `bootJar` and use that exact file when building images or releasing.

### Setting a fixed executable JAR name when needed

In Gradle Groovy DSL:

~~~groovy
tasks.named('bootJar') {
    archiveFileName = 'orders-api.jar'
}
~~~

Then the pipeline can reference:

~~~text
build/libs/orders-api.jar
~~~

Using a stable filename simplifies Dockerfiles and scripts, while ensuring artifact names and versions remain recorded in metadata or release tracking for traceability.

### Maven package and Gradle bootJar are not exact equivalents

Maven `package` is a lifecycle phase that normally executes test phases beforehand. Gradle `bootJar` is a task with its own task graph; do not assume calling `bootJar` alone runs `check` or `test`.

A Gradle pipeline might choose:

~~~bash
./gradlew clean check bootJar
~~~

That is an example of a combined verification-and-build workflow, not a command to execute at the current Markdown-authoring step.

## 8. What Does development-only Mean?

A **development-only** dependency supports coding and debugging on a developer machine without being required when the application serves production traffic.

A familiar example is `spring-boot-devtools`, which offers utilities like development restarts and accelerates the edit-and-verify loop.

The goal of separation:

~~~text
Development:
  App classes
  Runtime libraries
  Developer tooling (devtools, ...)
  Test tooling when running tests
            |
            v
Production artifact:
  App classes
  Runtime libraries
  Without development-only extras
~~~

Keeping development tools out of production:

- Reduces components needing management and patching.
- Prevents unnecessary development features from existing in deployment environments.
- Reduces behavior discrepancies introduced by developer tooling.
- Shrinks attack surface and avoids spurious dependency alerts.
- Keeps artifacts reflecting the application's true runtime dependencies.

**Development-only is not a shared syntax name across Maven and Gradle.** Its representation depends on the build tool and plugin.

## 9. spring-boot-devtools in Gradle: developmentOnly

When using the Spring Boot Gradle plugin, the common declaration is:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    developmentOnly 'org.springframework.boot:spring-boot-devtools'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This assumes the project already configures the Spring Boot plugin and dependency management. Do not copy just the `dependencies` block into a build file missing the plugin expecting all configurations to exist automatically.

Here:

- `implementation`: dependencies for main code and corresponding runtime.
- `developmentOnly`: dependencies needed on the development classpath, excluded from packaged executable archives.
- `testImplementation`: dependencies used for compiling and running tests.

A development command:

~~~bash
./gradlew bootRun
~~~

can use development-only dependencies like devtools as wired by the Spring Boot plugin.

When packaging:

~~~bash
./gradlew bootJar
~~~

`spring-boot-devtools` declared under `developmentOnly` should not appear inside the executable JAR built under normal settings.

### Why not use implementation for devtools?

If you write:

~~~groovy
implementation 'org.springframework.boot:spring-boot-devtools'
~~~

you declare it as a regular application dependency, obscuring the development-only separation. Some Boot packaging mechanisms might still have special handling to strip devtools, yet **you should not rely on exceptions to substitute for the right dependency model**.

Declare dependencies according to actual intent. Then inspect the real JAR to confirm exclusion instead of guessing from the build file alone.

## 10. spring-boot-devtools in Maven: optional and Exclusion from Repackage

With Maven, Spring Boot documentation commonly uses:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <scope>runtime</scope>
    <optional>true</optional>
</dependency>
~~~

Here:

- `runtime`: devtools participates in the classpath when running the app during development.
- `optional=true`: avoids imposing this dependency onto other projects as a default transitive dependency.
- **Spring Boot Maven Plugin** excludes `spring-boot-devtools` from repackaged executable JARs/WARs by default under standard settings.

Key point to remember: **`optional` does not inherently mean "devtools is absent from every JAR."** Packaging behavior depends on the Spring Boot plugin and project setup. If a project skips repackaging, uses another plugin, or uses custom assemblies, inspect the result yourself.

### The excludeDevtools option

The Spring Boot Maven Plugin provides an option controlling devtools exclusion from archives, e.g.:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <excludeDevtools>true</excludeDevtools>
    </configuration>
</plugin>
~~~

Normally this is already the default behavior, so the snippet primarily illustrates intent. If a project intentionally overrides settings or uses non-standard packaging, check actual plugin behavior and inspect the output file.

### Does devtools actually operate inside a packaged application?

Devtools is designed for development, and features like automatic restart are not intended for fully packaged production apps. Still, **there is no reason to bundle devtools into an artifact and rely only on its features being disabled**.

The better principle is stripping unnecessary dependencies from the artifact at build time and verifying their absence via archive inspection commands.

## 11. Classifying Dependencies by Practical Purpose

Beyond devtools, builds typically contain several dependency categories.

| Need | Typical Maven | Typical Gradle | Should be in production artifact? |
|---|---|---|---|
| Web framework needed at runtime | default `compile` | `implementation` | Yes, if needed by the app |
| JDBC driver used at runtime | `runtime` or matching | `runtimeOnly` | Yes, if needed by the app |
| Unit test library | `test` | `testImplementation` | No |
| Build-time annotation processor | Compiler plugin annotation processor config | `annotationProcessor` | Not needed at runtime merely because it runs at compile time |
| Compile-time-only API | Depends on project layout | `compileOnly` | No, unless runtime provides it by design |
| Developer tooling | `runtime + optional` paired with Boot plugin exclusion | `developmentOnly` | Should not be |
| Embedded servlet container for Boot JAR | Dependency from web starter | Runtime dependency from web starter | Yes, in corresponding executable JAR layout |

A dependency can play different roles in different projects. Never blindly mark a library `compileOnly` to "shrink JAR size" if code genuinely requires that library's classes at runtime.

### Annotation processor example

With Gradle, a library like Lombok is commonly declared in compile-time roles:

~~~groovy
dependencies {
    compileOnly 'org.projectlombok:lombok'
    annotationProcessor 'org.projectlombok:lombok'

    testCompileOnly 'org.projectlombok:lombok'
    testAnnotationProcessor 'org.projectlombok:lombok'
}
~~~

This snippet assumes version management for Lombok. The aim is running the annotation processor during compilation without bundling that tool into the executable JAR for production execution.

Do not treat Lombok being "absent from the JAR" as a missing dependency if the annotation processor already generated the needed Java bytecode during compilation.

## 12. Development-Only Is Not a Development Profile

These two concepts are easily confused:

**Development-only dependency** is a dependency/classpath scope managed by build tools and plugins.

**Spring profile** is a runtime mechanism for selecting configuration and beans, such as `dev`, `test`, or `prod`.

Example:

~~~yaml
# application-dev.yml
logging:
  level:
    com.example.orders: DEBUG
~~~

~~~yaml
# application-prod.yml
logging:
  level:
    com.example.orders: INFO
~~~

These are profile-specific configurations. They do not automatically strip the `spring-boot-devtools` dependency from an executable archive.

Conversely, when declaring:

~~~groovy
developmentOnly 'org.springframework.boot:spring-boot-devtools'
~~~

you are classifying a dependency for build/runtime classpaths. That neither creates a Spring profile named `developmentOnly` nor activates the `dev` profile.

Comparison:

| Concept | Governs |
|---|---|
| Gradle `developmentOnly` | Which dependencies serve development and stay out of packaged archives |
| Maven `optional` | Whether a dependency propagates transitively by default to dependent projects |
| `spring.profiles.active=dev` | Active configuration/bean set matching the dev profile |
| `application-dev.yml` | Configuration values applied only when the matching profile is active |
| `spring-boot-maven-plugin` / `bootJar` | How executable archives are built and which dependencies are included |

**Naming a profile `prod` does not automatically make an artifact secure.** An `application-dev.yml` containing secrets can still end up inside the JAR if it sits in resources without build-time filtering. Even when inactive, its contents can still be extracted from the archive.

## 13. Which Resources Get Packaged?

With a standard project layout:

~~~text
src/main/resources/
  application.yml
  application-dev.yml
  templates/invoice.html
  data/countries.json

src/test/resources/
  fixtures/test-order.json
~~~

When building a normal executable JAR:

- Resources in `src/main/resources` are placed onto the application's classpath.
- Resources in `src/test/resources` are primarily for tests and normally absent from production artifacts.
- Files in `src/main/resources` live inside `BOOT-INF/classes` rather than as loose files on disk.

Example:

~~~text
BOOT-INF/classes/application.yml
BOOT-INF/classes/application-dev.yml
BOOT-INF/classes/templates/invoice.html
BOOT-INF/classes/data/countries.json
~~~

**Do not use `new File("src/main/resources/...")` to read resources at runtime.** That source path does not exist once the JAR moves to another machine.

When reading bundled resources, use Spring's resource abstraction:

~~~java
Resource resource = resourceLoader.getResource(
        "classpath:data/countries.json"
);

try (InputStream input = resource.getInputStream()) {
    // Parse contents.
}
~~~

A resource inside an executable JAR does not necessarily correspond to a `java.io.File`. Thus, for reading, `getInputStream()` is generally appropriate rather than `getFile()`.

### Do not bundle secrets into resources

Putting passwords, tokens, or private keys in `application-prod.yml` inside a JAR does not make them safe just because the file sits in an archive. Anyone with access to download the file can list or unpack the archive.

Provide secrets through proper deployment-time configuration sources such as environment variables, mounted secret files, or secret management systems.

## 14. Inspecting the Artifact: Start with the Right File

After building, the first step is identifying **the exact file to be released**.

With Maven:

~~~text
target/orders-api-0.0.1-SNAPSHOT.jar
~~~

With Gradle:

~~~text
build/libs/orders-api-0.0.1-SNAPSHOT.jar
~~~

These are illustrative names. Projects can choose different names or emit multiple outputs such as plain JARs, source JARs, and backup JARs.

A thorough inspection workflow answers:

1. Which task/goal produced the chosen file?
2. Is the file size reasonable for the app and its dependencies?
3. Does it have the Spring Boot executable archive structure?
4. Does the manifest have the right startup metadata?
5. Are all required runtime dependencies included?
6. Are unnecessary development/test dependencies excluded?
7. Does it contain secrets or internal files that should not be released?
8. Can this exact file boot in an environment resembling actual deployment?

Do not inspect one JAR and deploy another JAR just because their names look similar.

## 15. Inspecting JAR Contents with jar tf

The JDK includes the `jar` tool. To list contents:

~~~bash
jar tf target/orders-api-0.0.1-SNAPSHOT.jar
~~~

For Gradle:

~~~bash
jar tf build/libs/orders-api-0.0.1-SNAPSHOT.jar
~~~

You can filter quickly on Linux/macOS:

~~~bash
jar tf build/libs/orders-api.jar | grep 'BOOT-INF'
~~~

In PowerShell:

~~~powershell
jar tf .\build\libs\orders-api.jar |
    Select-String 'BOOT-INF'
~~~

In a typical Spring Boot executable JAR, look for:

~~~text
BOOT-INF/classes/com/example/orders/OrdersApplication.class
BOOT-INF/classes/application.yml
BOOT-INF/lib/spring-boot-*.jar
BOOT-INF/lib/spring-context-*.jar
~~~

The listing above shows illustrative entry names, not a fixed mandatory list.

### Checking launcher and manifest

On Linux/macOS you can use archive tools like `unzip` to read the manifest:

~~~bash
unzip -p target/orders-api-0.0.1-SNAPSHOT.jar \
  META-INF/MANIFEST.MF
~~~

On Windows, you can use a suitable archive tool or extract just the manifest using `jar` into a safe temporary directory and inspect it. When using `jar xf`, remember extraction creates files in the current working directory, so pick a separate temp folder rather than running inside the source tree.

Read the manifest to verify:

- Is there a valid entry point for `java -jar`?
- Does `Start-Class` match the expected `main` class?
- Was the file actually repackaged by Spring Boot?

Actual Boot layout can differ for specialized packaging such as WAR or native images. Do not apply `BOOT-INF/lib` checks verbatim to every artifact type.

## 16. Verifying Devtools Did Not Leak into the Artifact

With Gradle:

~~~bash
jar tf build/libs/orders-api.jar | grep 'spring-boot-devtools'
~~~

With PowerShell:

~~~powershell
jar tf .\build\libs\orders-api.jar |
    Select-String 'spring-boot-devtools'
~~~

No matching lines indicate devtools is absent from the archive.

With Maven:

~~~bash
jar tf target/orders-api-0.0.1-SNAPSHOT.jar |
  grep 'spring-boot-devtools'
~~~

In a standard production packaging setup, there **should be no** entry like:

~~~text
BOOT-INF/lib/spring-boot-devtools-*.jar
~~~

Notes:

- Inspect **the exact artifact to be deployed**.
- Having devtools in the Maven/Gradle dependency cache does not mean it is inside the JAR.
- Having devtools on the development classpath is normal.
- Do not merely grep the build file and infer archive contents; packaging plugins can perform exclusions.
- If devtools appears in a production JAR, inspect dependency scopes/configurations and packaging plugins rather than merely disabling a devtools property at runtime.

### Checking test libraries

Similarly, check whether test-only libraries such as JUnit, Mockito, or unintended test fixtures entered the archive.

~~~bash
jar tf build/libs/orders-api.jar |
  grep -E 'junit|mockito|spring-boot-starter-test'
~~~

`spring-boot-starter-test` acts as a build-phase dependency-coordinating starter and may not appear as a JAR of that name; when inspecting, also check its transitive child dependencies.

If a test library is genuinely present in `BOOT-INF/lib` when unused at runtime, trace why it was declared in the wrong scope or pulled transitively by another dependency.

**Do not assume every name containing `test` is harmful**: some production libraries have names or packages that do not follow simple conventions. When encountering an unfamiliar entry, verify its exact module, version, and purpose before removing it.

## 17. Checking Which Dependencies Are Truly Needed at Runtime

A common packaging failure is an app that compiles fine yet fails on `java -jar` with:

~~~text
java.lang.NoClassDefFoundError: ...
~~~

or:

~~~text
java.lang.ClassNotFoundException: ...
~~~

Possible causes:

- Dependency declared as `compileOnly` even though code needs it at runtime.
- Maven used an unsuitable scope.
- A build plugin accidentally excluded a dependency.
- Version conflicts among libraries.
- The app uses reflection or dynamic loading for a class absent from the runtime classpath.
- A plain JAR was picked instead of the executable JAR.

With Maven, inspect the dependency graph via:

~~~bash
./mvnw dependency:tree
~~~

With Gradle, inspect runtime dependencies via:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

These commands reveal how dependencies enter the graph. Still, **dependency graphs do not replace artifact inspection**, because packaging plugins can exclude or transform components.

When troubleshooting, combine:

1. Error signature in the stack trace.
2. Effective dependency graph.
3. JAR contents.
4. Compile/runtime scope definitions.
5. How the app is launched in the real environment.

Do not resolve `ClassNotFound` errors by carelessly moving all dependencies to `implementation` or `compile`.

## 18. Checking Java Version and Runtime Compatibility

A Spring Boot artifact may be built with a newer Java version than the server runtime. When run, the JVM reports:

~~~text
java.lang.UnsupportedClassVersionError
~~~

This typically indicates bytecode compiled for a higher Java version than the active JVM, or a library requiring a newer runtime.

Checks to run:

~~~bash
java -version
~~~

In the build environment you can also check:

~~~bash
./mvnw -version
~~~

or:

~~~bash
./gradlew --version
~~~

Do not assume the IDE's JDK and the build pipeline's JDK match.

For example, a Java 21–targeted Maven project can declare:

~~~xml
<properties>
    <java.version>21</java.version>
</properties>
~~~

In a Gradle project, you can use a Java toolchain:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

These snippets only illustrate specifying Java versions in projects supporting those settings. Actual Java versions must align with your Spring Boot version, dependencies, and deployment environment.

### Build reproducibility and runtime environments

Ideally:

- Compile JDK is controlled.
- Dependency versions are centrally managed.
- Runtime JVM uses a compatible version.
- Docker base images pin clear versions rather than drifting unintentionally.
- Artifacts are built once and promoted across environments rather than rebuilt from source per environment.

That way, differences between staging and production stem mainly from externalized configuration and environment resources rather than differing builds.

## 19. Running a Smoke Test Against the Actual Artifact

A **smoke test** is a brief check confirming the artifact can start and perform minimal functionality in an expected environment.

It does not replace unit tests, integration tests, or load tests.

With an executable JAR:

~~~bash
java -jar target/orders-api-0.0.1-SNAPSHOT.jar
~~~

Or specifying port and profile:

~~~bash
java -jar target/orders-api-0.0.1-SNAPSHOT.jar \
  --server.port=18080 \
  --spring.profiles.active=smoke
~~~

This is an example command for a web app supporting those properties. Ensure the `smoke` profile exists or default configuration allows booting cleanly in a suitable test environment.

From another terminal, call a safe endpoint:

~~~bash
curl -i http://localhost:18080/actuator/health
~~~

The Actuator endpoint is only available if dependencies and exposure settings allow it. Without Actuator, call a project-provided internal ping/health endpoint designed for checks.

### Do not merely check that the process is still running

A service can bind a port while remaining functionally unready because:

- Synchronous runners haven't finished.
- Asynchronous startup tasks are still running.
- Required dependencies lost connectivity.
- Readiness probes still report down.
- Core APIs fail even though the home page returns HTTP 200.

Thus a minimal smoke test should verify:

1. The JVM boots on the right version.
2. No fatal startup exceptions appear.
3. The app reaches an appropriate ready state.
4. A basic functional request returns the expected result.
5. Process shutdown completes cleanly.
6. External configurations outside the artifact load properly without relying on developer-machine files.

Checks in production must follow operational procedures without generating test data or impacting real users.

## 20. Small Example Application Illustrating Packaging

Suppose a project has a Spring Boot application:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

A controller:

~~~java
package com.example.orders;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SystemController {

    @GetMapping("/api/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }
}
~~~

Configuration:

~~~properties
spring.application.name=orders-api
server.port=8080
~~~

If the project uses `spring-boot-starter-web` and the appropriate Boot packaging plugin, you can:

1. Build the executable JAR.
2. Locate the artifact in `target` or `build/libs`.
3. Inspect its structure with `jar tf`.
4. Run `java -jar` from a directory separate from the source tree.
5. Send:

~~~bash
curl -i http://localhost:8080/api/ping
~~~

Illustrative output:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"ok"}
~~~

This verifies that **the controller class and web runtime actually boot from the packaged artifact**, not just inside the IDE.

To prove standalone deployability, it is best to run the JAR from a location outside the source tree so it cannot accidentally pick up local developer files.

## 21. Packaging a JAR for Docker or Container Images

A container image typically holds:

- A compatible Java runtime.
- The actual executable JAR.
- Startup configuration and working directory.
- Mounted directories or appropriate access permissions.

Minimal Dockerfile example:

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app

COPY build/libs/orders-api.jar /app/orders-api.jar

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/orders-api.jar"]
~~~

This assumes:

- The project generates `build/libs/orders-api.jar`, e.g., by setting `archiveFileName` on `bootJar`.
- The artifact was compiled for Java 21 compatibility.
- The app listens on port 8080 or accepts corresponding port config.

**`COPY` must point to the exact executable JAR**, not a plain JAR. Overly broad wildcards like `build/libs/*.jar` can copy the wrong file or behave ambiguously when multiple outputs exist.

### Building an image does not mean the artifact was tested

A Docker build can succeed even if the JAR has the wrong entry point or lacks a runtime-only class. Smoke test the actual image, checking logs and health/readiness just as with a JAR.

Furthermore, an image containing the right JAR can still fail in production due to wrong environment variables, missing CA certificates, or bad mount paths.

### Image security considerations

In practice consider:

- Using a lean, security-patched runtime image.
- Running as a non-root user where possible.
- Copying only the artifact and genuinely needed files.
- Keeping `.env` files containing secrets out of build contexts and images.
- Excluding Maven/Gradle caches, source trees, and test reports from runtime images.
- Supplying configs and secrets from the deployment environment rather than baking them into images.

These practices complement excluding devtools; they do not replace inspecting the JAR's own dependencies.

## 22. Multi-Stage Builds: Separating Build and Runtime Environments

A popular choice is a **multi-stage Dockerfile** that builds inside a Maven/JDK image and then runs inside a JRE-only image.

Example for a Maven project configured to emit a stable executable JAR named `orders-api.jar`:

~~~dockerfile
FROM maven:3.9-eclipse-temurin-21 AS build

WORKDIR /workspace
COPY pom.xml .
COPY src ./src

RUN mvn -B package

FROM eclipse-temurin:21-jre

WORKDIR /app
COPY --from=build /workspace/target/orders-api.jar /app/app.jar

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

For this example to work cleanly, the project must be configured to produce `target/orders-api.jar`—such as via `<finalName>orders-api</finalName>`—and include all build inputs in the Docker context. If the project needs the Maven Wrapper, other modules, a parent POM, extra resources, or build config files, the Dockerfile must copy them too.

Benefits:

~~~text
Build stage:
  Maven + JDK + source + build cache
                  |
                  v
             executable JAR
                  |
                  v
Runtime stage:
  JRE + executable JAR
  No source or Maven needed to operate
~~~

Multi-stage builds avoid shipping build tools and source code in runtime images, yet **do not by themselves prove development-only dependencies were excluded from the JAR**. Verify the artifact copied between stages.

For larger projects, you can use specialized image builders, dependency caching, and Spring Boot's image-building features like Buildpacks. Either way, the inspection target remains **the artifact/image that gets deployed**.

## 23. When to Use a WAR?

Executable JARs fit most standalone Spring Boot deployments. A WAR may be suitable when infrastructure mandates integrating with an external servlet container.

With Maven:

~~~xml
<packaging>war</packaging>
~~~

A traditional application deployed to an external servlet container may need to extend `SpringBootServletInitializer`:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;
import org.springframework.boot.builder.SpringApplicationBuilder;

@SpringBootApplication
public class OrdersApplication extends SpringBootServletInitializer {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application
    ) {
        return application.sources(OrdersApplication.class);
    }
}
~~~

This example targets **Servlet-based** Spring Boot; it does not apply verbatim to pure WebFlux applications or other runtime models.

When deploying a WAR, servlet-container dependencies must be managed to match the external server model, typically using `provided` or equivalent settings. A Spring Boot executable WAR can also structure dependencies to still support `java -jar`, such as placing container-provided dependencies in `WEB-INF/lib-provided`.

**Do not apply blanket rules like "every WAR lacks Tomcat" or "every WAR runs with java -jar."** Check plugin settings, the generated WAR type, and the target servlet container.

Unless infrastructure mandates a WAR, executable JARs generally offer simpler operations: build one artifact and run it on a compatible JVM.

## 24. Artifacts and Externalized Configuration

Packaging aims to build an artifact **portable across environments**. Values changing across development, staging, and production should come from externalized configuration.

Example:

~~~properties
# application.properties inside the JAR
spring.application.name=orders-api
server.port=8080
~~~

In production:

~~~bash
SERVER_PORT=18080 java -jar orders-api.jar
~~~

Or:

~~~bash
java -jar orders-api.jar --server.port=18080
~~~

For database configs or secrets, use environment variables, mounted files, or an appropriate secret manager.

### Do not confuse configuration profiles with separate artifacts

One artifact can hold shared config alongside multiple profile files:

~~~text
application.yml
application-dev.yml
application-prod.yml
~~~

Activate a profile:

~~~bash
java -jar orders-api.jar --spring.profiles.active=prod
~~~

Yet choosing `prod` does not remove secrets inside `application-dev.yml` from the JAR. If a file must not be released, control it during build/resource filtering rather than relying solely on profile selection.

### Smoke tests must reflect real environments

If the production app reads data from:

~~~text
file:/etc/orders/rules.json
~~~

ensure that path exists in the actual container or server and the process has read permission. The file existing on a developer's machine proves nothing for the runtime container.

## 25. Verifying Checksums and Artifact Integrity

When an artifact passes through multiple stages (build → staging → production), verify it remains the exact same file.

On Linux/macOS:

~~~bash
sha256sum orders-api.jar
~~~

In Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 .\orders-api.jar
~~~

A release record might capture:

~~~text
artifact: orders-api.jar
version: 1.2.0
sha256: <SHA-256 value generated by pipeline>
java-runtime: 21
build-commit: <commit hash>
~~~

This is illustrative metadata; replace placeholders with real pipeline values.

Checksums detect file modification across stages. They **do not prove an artifact is secure, from a trusted origin, or that both artifact and checksum weren't swapped**. For stronger supply-chain guarantees, combine artifact repository access controls, signatures/attestations, and release policies.

### Build once, deploy many

A helpful principle:

~~~text
Source commit X
      |
      v
CI build + tests + package
      |
      v
Artifact A (hash H)
      |
      +----> Staging (hash H)
      |
      +----> Production (hash H)
~~~

By promoting the identical artifact, whenever staging and production behave differently, investigators can focus on environments, configuration, and external dependencies instead of guessing how two builds diverged.

## 26. Security Concerns During Packaging

Besides devtools, artifacts can accidentally include sensitive items:

- Private key files or certificates containing secrets not meant for release.
- Passwords hardcoded in `application-prod.yml`.
- Test fixture files containing real user data.
- `.env` or backup files accidentally copied into resources.
- Outdated dependencies with security vulnerabilities.
- Configurations exposing management endpoints improperly.
- Development/diagnostic tools unnecessary at runtime.

Verification should combine:

1. **Archive file listing:** spot resources that should not ship.
2. **Dependency and version listing:** support component auditing and security alerts.
3. **Secret scanning:** prevent secrets in config files, resources, or source.
4. **Access controls and runtime hardening:** protect Actuator, databases, message brokers, and observability systems.
5. **Container image scanning** when distributing artifacts as images.

### Never grep and print secrets to pipeline logs

When suspecting an artifact holds sensitive data, verification steps must avoid leaking those contents into CI/CD logs. Scan by filenames or use secret scanners with masking and proper access controls instead of unpacking and printing entire `application-prod.yml` files to public consoles.

A JAR may hold resources completely valid for production that still require restricted access. Do not judge solely by file extension.

## 27. Dependency Trees and SBOMs

When an application includes starters, runtime libraries enter the classpath **indirectly** as transitive dependencies.

Example:

~~~text
spring-boot-starter-web
    |
    +-- spring-web
    +-- spring-webmvc
    +-- embedded servlet container
    +-- logging dependencies
    +-- ...
~~~

Thus a project may never directly declare a JAR yet still contain it inside `BOOT-INF/lib`.

Two additional sources of truth exist:

- **Maven/Gradle dependency graphs:** show which module pulled in which module.
- **SBOM (Software Bill of Materials):** a software component inventory and release metadata, if your pipeline generates one.

When addressing an outdated or CVE-affected dependency, verify the **actual resolved version inside the runtime artifact**, not just a single dependency line.

If the pipeline generates an SBOM, tie it directly to the exact artifact/image so you never report an inventory from a different build.

## 28. Common Packaging Errors

| Symptom | Possible Cause | Where to investigate |
|---|---|---|
| `no main manifest attribute` | Running plain JAR or missing repackage | Check manifest and producing task/goal |
| `ClassNotFoundException` | Missing runtime dependency or wrong artifact picked | Check `BOOT-INF/lib` and dependency graph |
| `NoClassDefFoundError` | Class present at compile time yet missing at runtime | Check `compileOnly`, `provided`, version conflicts |
| `UnsupportedClassVersionError` | Runtime JVM incompatible with bytecode | Compare build and runtime Java versions |
| Works in IDE, `java -jar` fails to read template | Using `src/main/resources` path or `getFile()` on JAR resource | Use classpath resources and `InputStream` |
| `Port already in use` | Target port already occupied | Adjust `server.port` or infrastructure |
| `Application failed to start` from missing config | Environment variables/secrets missing at runtime | Check configuration sources and profiles |
| Devtools present in JAR | Unsuitable scope or plugin exclusion | Check `developmentOnly` or Maven settings |
| JUnit/Mockito appears in `BOOT-INF/lib` | Test dependency declared in wrong scope | Check scopes/configs and transitive reasons |
| Docker image builds yet container exits immediately | Wrong `ENTRYPOINT`, JRE, or JAR | Check logs, inspect archive, and smoke test |
| Container cannot read mounted file | Container path/permissions differ from host | Check mount path and runtime user |
| WAR fails on external servlet container | Wrong packaging, provided dependencies, or bootstrap | Check `SpringBootServletInitializer` and server compatibility |

Do not try to fix all of these by randomly adding dependencies or tweaking plugins. Identify **which stage failed**: compile, package, startup, readiness, or runtime.

## 29. Never Force Devtools into Production at All Costs

Some teams try enabling devtools in production to debug tough issues. That is not a good default choice.

More controlled alternatives:

- Temporarily adjust log levels for the package under investigation.
- Use metrics and distributed tracing.
- Use secured management endpoints if policy permits.
- Reproduce using the production-like executable artifact in staging.
- Enrich error context at request/job boundaries.
- Release a verified fix or official instrumentation after testing.

If extra diagnostics are truly needed, explicitly weigh risks and scope instead of leaving developer tooling inside runtime artifacts indefinitely.

### Development-only does not mean "cannot affect production under any circumstances"

If a dependency is misdeclared, a build script uses custom packaging, or an image copies an entire runtime classpath directory instead of the executable JAR, development tools can still sneak into deployment environments.

Therefore, **intent in build files must always be verified against actual artifact contents**. That is the single most important takeaway of this lesson.

## 30. A Practical Artifact Inspection Workflow

A team can standardize verification into steps:

### Step 1 — Confirm build tooling

Does the project use Maven or Gradle? Is the appropriate Spring Boot plugin applied? Is the expected artifact an executable JAR, WAR, or native image?

### Step 2 — Classify dependencies

Assign proper scopes for:

- Runtime libraries.
- Test libraries.
- Annotation processors.
- Developer tooling such as devtools.
- External servlet-container-provided dependencies when building WARs.

### Step 3 — Build in a controlled pipeline

Maven example:

~~~bash
./mvnw clean package
~~~

Gradle example:

~~~bash
./gradlew clean check bootJar
~~~

Pipelines may pick varying commands; the core requirement is producing the right output and running all team-mandated checks.

### Step 4 — Select the exact artifact

Never pick `.jar` files blindly. Verify Maven/Gradle output paths and the official archive filename.

### Step 5 — Inspect structure

Use `jar tf` and inspect the manifest to verify the JAR has the right launcher, classes, resources, and runtime dependencies.

### Step 6 — Verify development-only items are omitted

Verify `spring-boot-devtools` and unnecessary test libraries are absent from production archives.

### Step 7 — Verify Java runtime and external configuration

Confirm JVM runtime, profiles, environment variables, mounted files, networking, and critical infrastructure dependencies.

### Step 8 — Smoke test the exact artifact

Run `java -jar` or the real image; verify startup, readiness, and at least one core capability in a safe test environment.

### Step 9 — Record checksums and release

Store version, hash, build commit, and needed metadata. Promote the identical artifact across environments when your workflow permits.

Summarized concisely:

~~~text
Dependency scopes
       |
       v
Reproducible build
       |
       v
Exact executable artifact
       |
       +-- Check structure / manifest
       |
       +-- Check runtime dependencies
       |
       +-- Exclude devtools / test tools
       |
       +-- Check resources / sensitive content
       |
       v
Smoke test artifact / image
       |
       v
Record version + checksum
       |
       v
Deploy
~~~

## 31. Exercise 1 — Distinguishing bootJar and jar

Suppose Gradle produces:

~~~text
build/libs/orders-api-1.0.0.jar
build/libs/orders-api-1.0.0-plain.jar
~~~

Do the following:

1. Identify which task produced each file.
2. Inspect both with `jar tf`.
3. Look for `BOOT-INF/classes` and `BOOT-INF/lib`.
4. Explain which file should be launched via `java -jar`.
5. Inspect the manifest of each corresponding file.

**Key takeaway:** every JAR file is a Java archive, yet not every JAR file is an executable Spring Boot archive bundling runtime dependencies.

## 32. Exercise 2 — Verifying developmentOnly

In a Gradle project with the Spring Boot plugin, add:

~~~groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

Then:

1. Run the app with `bootRun` in development.
2. Package using `bootJar`.
3. List JAR contents.
4. Search for `spring-boot-devtools` in the archive.
5. Explain why a dependency can assist development yet should not appear in production JARs.

Key takeaway: **IDE/build-tool classpaths can differ from the executable archive's classpath**.

## 33. Exercise 3 — Maven optional and test Scope

Suppose a Maven POM contains:

~~~xml
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
~~~

Answer:

1. Is `optional=true` the same as `scope=test`?
2. Which dependency assists development?
3. Which dependency serves testing?
4. Which mechanism removes devtools from the executable JAR when using the Spring Boot Maven Plugin?
5. To verify a clean artifact, should you inspect the POM or the actual JAR file?

**Core answer:** `optional` is not equivalent to `test` scope. Devtools serves development; `starter-test` belongs to `test` scope; the plugin's packaging behavior and actual archive contents must be verified.

## 34. Exercise 4 — Investigating a JAR Execution Failure

An application reads a file:

~~~java
Path path = Path.of("src/main/resources/data/rates.csv");
String content = Files.readString(path);
~~~

It runs in the IDE; when deployed as an executable JAR, it reports file not found.

Fix it to read the packaged resource:

~~~java
Resource resource = resourceLoader.getResource(
        "classpath:data/rates.csv"
);

try (InputStream input = resource.getInputStream()) {
    // Read contents using an appropriate parser.
}
~~~

And explain why `getInputStream()` is preferred over `getFile()` for resources inside a JAR.

## 35. Exercise 5 — Designing a Release Checklist

Given an order-processing service configured with:

~~~text
Java 21
Spring Boot web starter
PostgreSQL JDBC driver
spring-boot-devtools
JUnit / Mockito
application-dev.yml
application-prod.yml
~~~

Design a minimal release checklist:

1. The PostgreSQL JDBC driver must be present at runtime if the app uses PostgreSQL.
2. Devtools and test libraries should not sit inside the executable JAR.
3. Do not bundle secrets into any config file inside the artifact.
4. Verify compatible runtime JVM.
5. Run `java -jar` with externalized configuration from a test environment.
6. Verify readiness and a basic API call.
7. Record the hash of the artifact to be released.

Additional note: having `application-prod.yml` inside the JAR is **not inherently wrong** if it contains only non-sensitive settings; what is wrong is bundling secrets or assuming inactive profiles cannot be read.

## 36. Common Misconceptions

**"If the app runs with bootRun, the artifact is guaranteed to run."** Incorrect. Runtime classpaths and executable JAR layouts differ from build-tool runs.

**"Any JAR works with java -jar."** No. Plain JARs can lack a main manifest and dependencies.

**"Development-only is just the dev profile."** No. Dependency scopes and Spring profiles serve two different purposes.

**"Maven optional=true automatically removes the dependency from every JAR."** No. Optional mainly controls transitive propagation; packaging also depends on plugins.

**"Since devtools is declared developmentOnly, no inspection is needed."** Always inspect the archive, especially with custom packaging.

**"Leaving test dependencies in runtime hurts nothing."** Wrong. It adds bloat, overhead, and unnecessary risk.

**"Testing in the IDE is enough."** No. Smoke test the actual deployment artifact.

**"Since application-dev.yml isn't active, it can't leak secrets."** False. The file can still sit inside the JAR.

**"Having BOOT-INF/lib means the app is functionally ready."** No. Valid JAR structure only proves one layer of packaging.

**"Docker build succeeded so the app works."** No. The image could hold the wrong JAR, wrong JRE, or lack runtime configuration.

**"Checksums prove the app is secure."** No. They are merely an integrity signal; provenance and security checks are still required.

**"Putting every dependency in implementation guarantees enough runtime classes."** That masks scope errors and bloats artifacts. Classify accurately by need.

**"The JAR holds all production configuration."** It should not. Immutable artifacts should pair with externalized config and secret management.

**"Checking packaging removes the need to check deployment."** No. Java runtimes, filesystems, networks, and external services can differ drastically from build environments.

## Conclusion

Spring Boot packaging transforms source code, resources, and runtime dependencies into an **artifact runnable in the target environment**. For executable JARs, the Spring Boot Maven Plugin or Gradle `bootJar` typically organizes classes/resources under `BOOT-INF/classes` and runtime dependencies under `BOOT-INF/lib`, while supplying a launcher suitable for `java -jar`.

**Development-only** keeps developer tooling such as `spring-boot-devtools` supporting rapid code edits without becoming an unwanted component in production. In Gradle, the standard choice is `developmentOnly`; in Maven, devtools is typically declared `runtime` and `optional=true`, paired with the Spring Boot Maven Plugin's devtools exclusion. Do not confuse those settings with the Spring `dev` profile.

Finally, **inspecting deployment artifacts means verifying the exact file or image that will be released**: right launcher, required classes and dependencies, free of unnecessary devtools/test tooling, free of leaked secrets, JVM-compatible, working with externalized config, and passing a proper smoke test. Checking structure with `jar tf`, inspecting manifests, running `java -jar`, and recording checksums dramatically cuts bugs that only surface once an application leaves the developer machine.
