# Identifying Differences Between the Development Classpath and the Archive Classpath

A Spring Boot application may run fine with `./gradlew bootRun` or `mvn spring-boot:run`, yet fail with `ClassNotFoundException`, missing configuration files, or altered behavior when deployed via `java -jar app.jar`. The cause usually lies in the **actual classpath used in each launch path**, how the build tool categorizes dependencies, archive packaging rules, and how the Spring Boot launcher loads classes from nested JARs.

This guide shows how to **identify, explain, and verify** those differences using observable evidence. The goal is not making every classpath identical: some differences, especially development-only tools, are **intentional**. What matters is distinguishing intentional differences from dependencies or resources accidentally omitted during packaging.

## 1. What Is the Classpath and Why Are There Multiple Kinds?

A **Java classpath** is the set of locations (class/resource directories and JARs) a Java class loader searches for classes and resources. A Spring Boot application also uses a launcher/class loader mechanism to handle JAR libraries nested **inside an executable archive**. Consequently, you cannot inspect a single `java.class.path` string and treat it as the complete list of classes Spring Boot loads.

In a standard Java project, Gradle distinguishes these classpaths/configurations:

| Kind | When Used? | Typically Contains? |
| --- | --- | --- |
| `compileClasspath` | Compiling main source code | APIs and compile-time dependencies; may include `compileOnly` |
| `runtimeClasspath` | Running main source code | Compiled classes/resources and runtime dependencies per project config |
| `testCompileClasspath` | Compiling tests | Main dependencies, test dependencies, and test-only libraries |
| `testRuntimeClasspath` | Running tests | Test classes, application classes, and test dependencies |
| `bootRun.classpath` | Running the app via Gradle | Defaults to the main source set's runtime classpath; customizable |
| `bootJar.classpath` | Building the executable Spring Boot JAR | Entries packaged by the task; the plugin may exclude development-only dependencies |

In Maven, scopes like `compile`, `runtime`, `provided`, and `test` serve to classify intent, though they do not map one-to-one onto Gradle configurations. Maven and Gradle plugins can also apply their own packaging rules.

**Questions to separate clearly:**

1. **Does the compiler see the class?** Inspect the compile classpath.
2. **Does the development process see the class/resource?** Inspect the classpath actually used by `bootRun` or `spring-boot:run`.
3. **Does the archive contain the class/resource/JAR?** Inspect the output of `bootJar`, `bootWar`, or Maven `repackage`.
4. **Can the deployment JVM load it?** Run the actual archive with the real Java runtime, configuration, and launcher.

Having a dependency in a build script **does not prove** it enters the executable archive; having a JAR in the archive does not guarantee the target environment has the required configuration, native libraries, or resource permissions.

## 2. Why Does `bootRun` Differ from `java -jar`?

### 2.1. Running from Project Output Directories

With the Spring Boot Gradle plugin and Java plugin, `bootRun` is a task of type `BootRun` (extending `JavaExec`). By default, it uses the main source set's runtime classpath. In a typical project, it references locations similar to:

~~~text
build/classes/java/main/
build/resources/main/
<Gradle cache>/.../spring-boot-*.jar
<Gradle cache>/.../spring-context-*.jar
<Gradle cache>/.../other runtime dependencies
[optional custom directories/JARs added for bootRun]
~~~

This is an illustrative layout, not fixed output. Actual paths depend on Gradle version, OS, source sets, plugins, project paths, and task configuration. `bootRun` does not need to build an executable JAR before running.

Development advantages: freshly built classes/resources run directly, edits apply quickly, and the classpath can include development-only tools such as `spring-boot-devtools`.

### 2.2. Running from an Executable Spring Boot JAR

`bootJar` builds an archive with a distinctive layout:

~~~text
classpath-demo.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...      (Boot launcher)
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/demo/...             (application classes)
    │   ├── application.yml                  (if present)
    │   └── packaged resources
    └── lib/
        ├── spring-boot-*.jar
        ├── spring-context-*.jar
        └── packaged runtime dependencies
~~~

The command:

~~~bash
java -jar build/libs/classpath-demo.jar
~~~

starts the executable archive through the launcher declared in the manifest. The Spring Boot launcher loads classes from `BOOT-INF/classes` and nested JARs in `BOOT-INF/lib`. Standard Java class loaders do not natively load nested JARs in this format; the Boot launcher handles archive-specific loading.

Common differences:

| Aspect | `bootRun` | `java -jar` Executable Boot JAR |
| --- | --- | --- |
| Source of app classes | Output directory of the main source set | `BOOT-INF/classes` inside the archive |
| Dependencies | JAR locations on the task's classpath | Nested JARs packaged in `BOOT-INF/lib` |
| Development-only dependencies | May be present, depending on config | Normally excluded from the archive by default |
| Resources added via `bootRun.classpath` | Visible during run | Not automatically copied into the archive |
| JVM settings | `bootRun`, task JVM args/system properties | JVM args/system properties on the deployment command |
| Code-change turnaround | Convenient for development | Requires rebuilding the artifact to pick up edits |
| Class loading | Primarily development classpath; devtools may add a loader | Boot launcher handles nested JARs |
| Purpose | Running from source/build output | Verifying and distributing a concrete artifact |

**Do not confuse runtime configuration with classpath.** Two runs can share identical library classpaths yet behave differently due to `spring.profiles.active`, environment variables, system properties, Java version, working directory, secrets, networking, or ports. Diagnostics must prove a class or resource is truly missing before blaming the classpath.

## 3. How Are Different Dependency Kinds Included or Excluded?

### 3.1. Common Gradle Configurations

In a Java/Spring Boot Gradle project:

| Declaration | Main Compile | Main Runtime | Typical Executable Boot JAR |
| --- | --- | --- | --- |
| `implementation 'group:artifact'` | Yes | Yes | Usually yes, if in the packaging task's dependencies |
| `compileOnly 'group:artifact'` | Yes | Not added by `compileOnly` alone | Not packaged by `compileOnly` alone |
| `runtimeOnly 'group:artifact'` | Not used to compile main | Yes | Usually packaged |
| `testImplementation 'group:artifact'` | Not used to compile main | No | No; for tests |
| `testRuntimeOnly 'group:artifact'` | No | No | No; for test runtime |
| `annotationProcessor 'group:artifact'` | Runs during compile annotation processing | Does not become a runtime dependency automatically | Not packaged by this configuration alone |
| Boot plugin's `developmentOnly 'group:artifact'` | Not part of standard compilation | Used for development runtime | Excluded from Boot archives by default |

This table describes **important learning defaults**, not universal rules across all custom source sets or plugins. If a build script manually wires a configuration into `bootJar.classpath` or `bootRun.classpath`, outcomes change; inspect the actual task configuration.

Example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    runtimeOnly 'org.postgresql:postgresql'
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This is a **`build.gradle` snippet**, assuming plugins, repositories, and dependency management are already configured. The PostgreSQL JDBC driver is needed at runtime if the app uses PostgreSQL; `spring-boot-devtools` serves development; `starter-test` must not ship inside the production JAR merely because tests pass.

### 3.2. DevTools: An Intentional Discrepancy

`spring-boot-devtools` is the classic example:

~~~groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

With the Spring Boot Gradle plugin's default integration, `developmentOnly` serves the development classpath and **is omitted from executable JAR/WAR files**. The Spring Boot Maven plugin likewise excludes devtools from repackaged archives by default. This keeps development features like restart/reload out of production deliverables.

Nothing is broken when `spring-boot-devtools` appears under `bootRun` yet is **absent** from `BOOT-INF/lib`. That discrepancy is **by design**. When verifying, check plugin/version documentation and open the real archive rather than guessing how dependencies will be packaged.

### 3.3. Cases That Cause Genuine Missing Classes

- **Using `compileOnly` for a runtime-required library:** compiles cleanly, yet `java -jar` lacks the class; development runs may also lack it unless an IDE or other tool adds it inadvertently.
- **Using `testImplementation` for a library needed by main code:** tests pass because the test classpath is broader, while production lacks the dependency.
- **Adding dependencies via IDE/manual classpath:** the IDE runs using manually attached libraries while Gradle/Maven packages strictly from the build script and misses them.
- **Wrong Maven scope:** libraries in `test` or `provided` do not follow the runtime packaging behavior the author assumed.
- **Excluded by packaging rules:** `bootJar`/`repackage`, exclusions, or custom task classpaths drop the module from the archive.
- **Class exists, yet a transitive dependency fails to load:** the class itself is present, while linking/initializing throws `NoClassDefFoundError` because a referenced class is missing.

Never fix this by blindly changing **every** dependency to `implementation`. Determine whether the library is needed at compile, runtime, test, or development only, and set the **proper scope/configuration**.

## 4. Runnable Experiment: Development Resource Present, Absent in Archive

The exercise below creates a **deliberate, measurable difference**: adding a `dev-only/` directory to `bootRun`'s classpath while leaving `bootJar` with normal packaging rules. Java checks resource visibility via the **context class loader** rather than inferring from filesystem paths.

The sample uses Java **17**, Spring Boot **3.3.5**, and Gradle wrapper **8.7** (or a compatible version). Fixed versions are illustrative and do not imply the latest release. No database, HTTP server, or network access is needed once dependencies are cached.

Structure:

~~~text
classpath-demo/
├── settings.gradle
├── build.gradle
├── dev-only/
│   └── dev-only-marker.txt
└── src/
    └── main/
        ├── java/com/example/demo/ClasspathDemoApplication.java
        └── resources/main-marker.txt
~~~

### 4.1. `settings.gradle`

~~~groovy
rootProject.name = 'classpath-demo'
~~~

### 4.2. Complete `build.gradle`

~~~groovy
import org.springframework.boot.gradle.tasks.bundling.BootJar
import org.springframework.boot.gradle.tasks.run.BootRun

plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter'
}

tasks.named('bootRun', BootRun) {
    // Only add this directory to bootRun's classpath.
    classpath files('dev-only')
}

tasks.named('bootJar', BootJar) {
    archiveFileName.set('classpath-demo.jar')
}
~~~

`classpath files('dev-only')` **appends** a classpath entry to `JavaExec` without replacing the main runtime classpath configured by the Spring Boot plugin. `dev-only/` sits at the project root with a single resource file inside. This configuration **does not** add `dev-only` to `sourceSets.main.resources` or `bootJar.classpath`, so it is not copied into the executable JAR.

### 4.3. `src/main/java/com/example/demo/ClasspathDemoApplication.java`

~~~java
package com.example.demo;

import java.net.URL;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ClasspathDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ClasspathDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner checkResources() {
        return args -> {
            ClassLoader loader =
                    Thread.currentThread().getContextClassLoader();

            System.out.println("MAIN_RESOURCE=" +
                    state(loader.getResource("main-marker.txt")));
            System.out.println("DEV_ONLY_RESOURCE=" +
                    state(loader.getResource("dev-only-marker.txt")));
        };
    }

    private static String state(URL resource) {
        return resource == null ? "absent" : "present";
    }
}
~~~

This is a runnable Java 17+ program when combined with the two Gradle files above. Using the context class loader tests whether resources are actually resolvable in the **current runtime**, even when the Spring Boot launcher organizes nested JARs differently from the JVM's standard system classpath.

### 4.4. The Two Resource Files

**`src/main/resources/main-marker.txt`**:

~~~text
main resource
~~~

**`dev-only/dev-only-marker.txt`**:

~~~text
development resource
~~~

Both files contain one UTF-8 text line. The Java code only checks whether they **load via the class loader**, without reading file contents, so trailing newlines do not affect the output.

### 4.5. Running on the Development Classpath

If the project has a Gradle Wrapper:

~~~bash
./gradlew -q bootRun --args='--spring.main.banner-mode=off --logging.level.root=OFF'
~~~

The two lines printed by the app are:

~~~text
MAIN_RESOURCE=present
DEV_ONLY_RESOURCE=present
~~~

`main-marker.txt` appears because `src/main/resources` is processed into main resources. `dev-only-marker.txt` appears because we **added `dev-only/` to `bootRun.classpath`**. Gradle or Spring Boot may print other lines depending on environment settings; these two lines reflect the program's own logic.

### 4.6. Packaging and Running the Executable Archive

~~~bash
./gradlew -q clean bootJar
java -jar build/libs/classpath-demo.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

The two lines printed by the app:

~~~text
MAIN_RESOURCE=present
DEV_ONLY_RESOURCE=absent
~~~

This difference is **designed into the build script**. `main-marker.txt` is copied into the archive under `BOOT-INF/classes`; `dev-only-marker.txt` was added solely to `bootRun` and therefore omitted by `bootJar`. This is not a "Spring Boot bug": the archive contains exactly what the packaging task was instructed to include.

Inspect the JAR directly:

~~~bash
jar tf build/libs/classpath-demo.jar
~~~

Among the entries, you will see:

~~~text
BOOT-INF/classes/com/example/demo/ClasspathDemoApplication.class
BOOT-INF/classes/main-marker.txt
BOOT-INF/lib/spring-boot-*.jar
~~~

Actual library entries include specific version numbers rather than a literal `*`; `BOOT-INF/lib/spring-boot-*.jar` is a **generalized pattern**, not literal `jar tf` output. `BOOT-INF/classes/dev-only-marker.txt` is absent from the archive in this setup.

On Windows PowerShell, use `.\gradlew.bat` instead of `./gradlew`, keep commands on a single line, and adjust argument quoting if required by the shell. If there is no wrapper yet, generate one once using a compatible Gradle (`gradle wrapper --gradle-version 8.7`) and use the wrapper thereafter.

### 4.7. Lesson from the Experiment

Same `main()`, same project, yet different resource visibility because **the classpath is configured per execution path**. If that file is required in production, the proper fix is making it a managed runtime resource in `src/main/resources` or an appropriate external config source—**not** appending it to `bootRun.classpath`. If the resource holds secrets or environment-specific config, never embed it into the archive; use external configuration and secret stores in the target environment.

## 5. Other Differences to Check Beyond Resources

### 5.1. DevTools: Present in Development, Absent in Archive by Default

If added to Gradle:

~~~groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

`bootRun` gains developer tool features while the executable Boot JAR omits the dependency by default. That is intentional. When DevTools uses its restart class loader during development, class-loading issues can also stem from the split between the **base class loader** and the **restart class loader**, not merely a missing JAR. Disabling restart during diagnostics helps isolate loader issues, though you should never enable DevTools in production to "patch" a symptom.

Spring Boot documentation notes that DevTools can cause class-loading issues, particularly in multi-module projects. Always separate **whether a dependency is on the dev classpath** from **which class loader loads a class**.

### 5.2. Excluded Transitive Libraries or Version Conflicts

A single starter can pull in many transitive dependencies. Gradle/Maven resolves versions using declarations, dependency management/BOMs, exclusions, and resolution rules. Runtime classpath and packaged archive can diverge if the packaging task uses a different configuration or applies exclusions.

Symptoms:

- `ClassNotFoundException`: the loader cannot find a class requested by name.
- `NoClassDefFoundError`: a referenced class failed to define/load a required dependency (or previously failed static initialization). Read the **Caused by** chain in the stack trace rather than assuming one cause.
- `NoSuchMethodError` or `NoSuchFieldError`: likely a **binary-incompatibility version mismatch** even though the class name resolves. Compare classpath versions and the JARs actually loaded.

Never fix this by blindly forcing every library into `bootJar`. First identify which module is needed and which version is running.

### 5.3. Resources, Templates, SPI, and Configuration

Files in `src/main/resources` normally go into `build/resources/main` during development and into `BOOT-INF/classes` when packaged. Other resource sources—such as:

- Files placed beside the project folder outside resource source directories.
- Files added manually by an IDE to the development classpath.
- Files created by a generator task not wired into `processResources` or `bootJar`.
- `META-INF/services/...` descriptors read by `ServiceLoader`.
- Templates or assets whose paths shift after packaging.
- Files on the external filesystem accessed via relative paths based on current working directory.

—may work during development yet fail inside the archive. Beyond the classpath, verify **absolute vs. relative file paths**. For instance, `new File("config/local.properties")` looks on disk relative to the working directory; it **does not** read resources inside `BOOT-INF/classes`.

For packaged resources, use a proper classpath API such as:

~~~java
try (var stream = Thread.currentThread()
        .getContextClassLoader()
        .getResourceAsStream("main-marker.txt")) {
    if (stream == null) {
        throw new IllegalStateException("Missing classpath resource");
    }
    byte[] data = stream.readAllBytes();
    System.out.println("RESOURCE_BYTES=" + data.length);
}
~~~

This is an illustrative Java snippet **inside a method permitted to declare/throw `IOException`** or handling exceptions appropriately; it is not a standalone Java file. For resources inside nested JARs, never assume `getResource(...).getFile()` yields a filesystem path openable with `new File(...)`. Using `getResourceAsStream` or Spring `Resource` is far more reliable when you only need to read bytes.

### 5.4. Tests Pass, Yet the Artifact Fails

`testRuntimeClasspath` typically includes test classes and libraries like JUnit, Mockito, or Testcontainers that production omits. If code works in tests thanks to a `testImplementation` dependency that main runtime actually needs, the artifact will lack it. Test helpers, test configs, and mock services generally **should not** enter production; only genuine application dependencies belong in runtime scope.

`bootTestRun` (where supported by plugin/version) launches a test main class with the test runtime classpath; it **does not replace** verifying the executable Boot JAR for production.

### 5.5. WAR Differs from Executable JAR

A Spring Boot executable WAR uses `WEB-INF/classes`, `WEB-INF/lib`, and potentially `WEB-INF/lib-provided` to support both standalone execution and external servlet container deployment. Never apply the `BOOT-INF/classes`/`BOOT-INF/lib` layout of an executable JAR to every `.war` file.

`providedRuntime` in a WAR project differs from `runtimeOnly`; an external servlet container can supply the Servlet API and container runtime. If the app works under `bootRun` yet misses dependencies inside a WAR, inspect **packaging type, scope, and target container**, not only filenames.

### 5.6. Java Version and Runtime Environment

An archive can hold every right class while the production JVM is too old for the compiled bytecode, throwing `UnsupportedClassVersionError`. That is a **Java version compatibility** error, not a missing classpath entry. For native libraries, OS/architecture mismatches can throw `UnsatisfiedLinkError`. Spring profiles, database URLs, certificates, networking, or file permissions can also cause failures even with a complete classpath.

## 6. Methods to Prove Where Classes and Resources Actually Are

### 6.1. Inspecting Gradle's Dependency Graph

In the project directory using the Gradle Wrapper:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-boot-devtools --configuration runtimeClasspath
~~~

- `compileClasspath` shows libraries involved in compiling main sources.
- `runtimeClasspath` shows the configured main runtime graph; it does not automatically match the final archive if the Boot plugin applies packaging exclusions.
- `testRuntimeClasspath` exposes dependencies appearing only when running tests.
- `dependencyInsight` traces dependency paths, version selection reasons, and competing constraints.

Output depends on the project, Gradle version, and repositories; there is no single fixed stdout for every application. In multi-project builds, qualify the project path:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

`:app` is an illustrative subproject name; replace it with the real application module path. The root project does not necessarily share the same dependency graph as a subproject.

### 6.2. Inspecting the Archive Directly

~~~bash
./gradlew clean bootJar
jar tf build/libs/classpath-demo.jar
~~~

Check three entry groups:

1. **`BOOT-INF/classes`:** did the application's classes and resources make it into the archive?
2. **`BOOT-INF/lib`:** did the expected dependency JARs enter the archive at the right versions?
3. **Manifest/launcher:** is this the executable Spring Boot JAR or a plain JAR?

With the Gradle Spring Boot plugin, `jar` and `bootJar` can both exist; modern versions usually produce the plain JAR with the `plain` classifier by default. Accidentally launching `*-plain.jar` fails because you **picked the wrong artifact**, not because `bootJar` packaged incorrectly.

Never treat `./gradlew dependencies` as sole proof of archive contents: that reports configuration resolution, whereas `jar tf` shows **what actually sits inside the generated file**.

### 6.3. Probing the Active Class Loader

To verify whether a class loads at runtime, you can add a small probe:

~~~java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
try {
    Class<?> type = Class.forName(
            "com.example.somepackage.OptionalIntegration", false, loader);
    System.out.println("CLASS_FOUND=" + type.getName());
} catch (ClassNotFoundException ex) {
    System.out.println("CLASS_MISSING=com.example.somepackage.OptionalIntegration");
}
~~~

This is an **illustrative check snippet**—substitute the class of interest inside a Java method. `Class.forName(..., false, loader)` avoids static initialization during the check, though class verification/linking can still surface linkage errors. Finding a class also does not guarantee all of its own dependencies are compatible or functional.

For resources, use:

~~~java
var url = Thread.currentThread()
        .getContextClassLoader()
        .getResource("main-marker.txt");
System.out.println(url == null ? "RESOURCE_MISSING" : "RESOURCE_FOUND");
~~~

Nested JAR URLs use schemes/syntax that vary across Spring Boot versions. **Never parse the URL string and cast it to `File`** when a resource lives inside an archive; read via streams or Spring `Resource` APIs.

### 6.4. Why `System.getProperty("java.class.path")` Is Insufficient

Under `java -jar app.jar`, the Java launcher's system classpath may list only **app.jar**, while the Boot launcher loads nested JARs through its specialized class loader. Under `bootRun`, that property typically lists many individual directories and JARs. Comparing those two strings directly leads to the **false conclusion that all dependencies are missing from the JAR**.

To prove an entry is missing, check **archive entries and runtime class loader resolution**, rather than comparing `java.class.path` lengths.

### 6.5. Checking Maven with `spring-boot:run` and `repackage`

In a Maven project:

~~~bash
mvn dependency:tree
mvn help:effective-pom
mvn clean package
jar tf target/your-app-name.jar
java -jar target/your-app-name.jar
~~~

`mvn dependency:tree` inspects dependencies by scope, while `effective-pom` shows inherited parent/dependencyManagement/plugin configuration. `spring-boot-maven-plugin:repackage` builds the executable archive when bound to the packaging lifecycle; having only the BOM or starter dependencies **does not guarantee** the JAR was repackaged.

Projects using `spring-boot-starter-parent` can declare `spring-boot-maven-plugin` under `<build><plugins>` to inherit the parent's `repackage` execution. Projects that only import the Spring Boot BOM must configure the plugin and execution explicitly. The exact JAR filename in `target/` depends on `artifactId`, `version`, classifier, and plugin settings. `your-app-name.jar` in the snippet is a **placeholder to replace with your real artifact name**, not a literal file generated by Maven.

The Spring Boot Maven plugin excludes devtools from repackaged archives by default, so intentional development vs. runtime differences can arise in Maven too.

## 7. Step-by-Step Diagnostic Workflow

When told "`bootRun` works, yet `java -jar` fails," follow this sequence:

1. **Reproduce both commands** on the exact same source revision. Confirm `bootRun` uses current classes/resources and `bootJar` was rebuilt after the latest edit.
2. **Capture the exact error:** class name or resource path, full exception chain, and failure timing. Separate class-loading errors, version mismatches, file paths, and environment config.
3. **Inspect dependency configurations:** `runtimeClasspath`, `developmentOnly`, `compileOnly`, `testRuntimeClasspath`, transitive exclusions, and resolved versions.
4. **Open the exact artifact to be deployed** with `jar tf`. Inspect classes in `BOOT-INF/classes`, JARs in `BOOT-INF/lib`, resources, and the manifest. Do not confuse `plain.jar` with `bootJar`.
5. **Compare task configurations:** check for custom `bootRun.classpath`, `sourceResources`, `bootJar.classpath`, generated resources, packaging exclusions, custom `sourceSets`, or convention plugins.
6. **Verify Java runtime and launcher:** Java version/architecture, arguments, profiles, working directory, container image, environment/secrets.
7. **Fix at the rightful owner:** change dependency scope if truly runtime-needed; move required packaged resources into main resources; strip dev-only resources from production if they should not ship.
8. **Re-verify:** run `clean bootJar` (or Maven `clean package`), inspect the archive, test the exact `java -jar` command, and run critical tests.

A useful QA report clearly states **what was missing**, **where it was missing**, **which dependency/resource path caused the discrepancy**, **which change fixed it**, and **which commands verified the fix**.

## 8. Common Pitfalls

| Symptom | Hasty Misdiagnosis | Accurate Diagnosis |
| --- | --- | --- |
| `java.class.path` under `java -jar` shows one JAR | "All dependencies were lost" | Inspect nested JARs in `BOOT-INF/lib` and Boot launcher |
| DevTools missing from archive | "`bootJar` packaged incorrectly" | Verify `developmentOnly` and default devtools exclusion |
| Runs in IDE, JAR lacks class | "Production JVM doesn't support Spring" | Compare IDE/run classpath, Gradle runtime config, artifact, and Java version |
| Tests pass, runtime lacks library | "Library is present because tests used it" | Check `testImplementation` vs. runtime dependencies |
| Resource loads via `new File(...)` in dev, fails in JAR | "Spring Boot dropped resources" | Check `BOOT-INF/classes` and switch to classpath resource streams where appropriate |
| `NoClassDefFoundError` | "Definitely missing the class named in message" | Read nested causes, transitive deps, and class initialization failures |
| `NoSuchMethodError` | "Class does not exist at all" | Check version conflicts / binary incompatibility |
| App cannot connect to database | "Missing JDBC driver" | Check driver in archive **and** URL, credentials, network, DB, profile |
| `java -jar` reports no main manifest | "Broken source code" | Likely running the plain JAR instead of the executable Boot JAR |
| Changed `bootRun.classpath`, JAR still lacks resource | "Gradle ignored config" | `bootRun` and `bootJar` are separate tasks with separate classpaths/outputs |
| WAR runs in embedded container, fails in external container | "Corrupt WAR" | Check `providedRuntime`, external container, classpath, and API versions |

### Avoid Blindly Patching with External Classpaths

Adding `-cp` alongside `java -jar` does not behave like launching a main class via `java -cp ...`: with `-jar`, the Java launcher treats the specified JAR as the entry point and does not normally append `-cp` entries to the app classpath. Spring Boot provides specialized launchers/modes for external libraries, yet those should not become a default workaround for missing artifact dependencies.

If a library **truly** belongs to application runtime, fix the build script and rebuild the archive so it contains the right dependency. If supplied by the container/environment, document the deployment contract clearly and verify the container's classloader.

## 9. Comparison Exercises and Answers

**Scenario A.** `build.gradle` contains:

~~~groovy
dependencies {
    compileOnly 'org.example:some-runtime-api:1.0'
}
~~~

Compilation succeeds, yet running the artifact throws a missing-class error for that API. What should you inspect?

**Answer:** `compileOnly` does not add the dependency to runtime by default. If the application truly loads that API at runtime, assign the right runtime scope (usually `implementation` or `runtimeOnly` depending on code usage), verify the version exists, and re-inspect `BOOT-INF/lib`. If provided by an external container, verify the container contract before changing scope.

**Scenario B.** `spring-boot-devtools` is present in `bootRun` but absent from `BOOT-INF/lib`.

**Answer:** This is usually the expected result of `developmentOnly` and Boot packaging rules. Never force devtools into production merely because the two classpaths differ.

**Scenario C.** `src/main/resources/app-marker.txt` can be read via `getResourceAsStream` under `java -jar`, while `new File("src/main/resources/app-marker.txt")` fails inside a container.

**Answer:** `getResourceAsStream` resolves resources via the class loader inside the archive; `new File` opens a physical path relative to the container's working directory. They read from different places; the archive resource is not necessarily missing.

**Scenario D.** `./gradlew dependencies --configuration runtimeClasspath` shows library X, yet `jar tf app.jar` does not show X under `BOOT-INF/lib`.

**Answer:** Verify you opened **the right executable archive from the current build**; check whether the dependency belongs to an excluded configuration such as `developmentOnly`, packaging exclusions, custom `bootJar.classpath`, or filtering. A resolved configuration alone does not prove final archive contents.

**Scenario E.** `java -jar` throws `UnsupportedClassVersionError` even though every JAR is present.

**Answer:** Compare the compiled Java bytecode target against the target Java runtime. This is typically a JVM version mismatch, not a missing packaged dependency. Check `java --version` in the deployment environment.

**Scenario F.** Code throws `ClassNotFoundException` for a JDBC driver only inside one container.

**Answer:** Confirm the driver is inside the archive, whether the container runs the **exact artifact version**, and whether custom loaders, profiles, or Java versions differ. Never assume the cause just because it runs on a developer machine.

## 10. Official Reference Sources

- Spring Boot Gradle Plugin — [Running Your Application](https://docs.spring.io/spring-boot/gradle-plugin/running.html): `bootRun`, runtime classpath, resource reloading, and `JavaExec`.
- Spring Boot Gradle Plugin — [Packaging Executable Archives](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html): `bootJar`, archive contents, and development-only dependencies.
- Spring Boot — [Developer Tools](https://docs.spring.io/spring-boot/reference/using/devtools.html): devtools, restart class loader, and packaged applications.
- Gradle — [Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html): `compileClasspath`, `runtimeClasspath`, and test configurations.
- Gradle — [Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencies` and `dependencyInsight`.
- Spring Boot Maven Plugin — [Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html): `repackage` and executable archive layout.

**Takeaway:** **the development classpath is what the development process actually sees; the archive classpath is what the packaging task places into the artifact and what the Boot launcher loads at runtime.** To reach sound conclusions, compare **dependency graph → task configuration → archive contents → runtime class/resource resolution**. Those measurements distinguish intentional differences from bugs to fix.