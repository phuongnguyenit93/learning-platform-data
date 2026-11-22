# Differences Between Build Tool Dependencies and Actual JVM Paths

## 1. Scenario: A dependency is declared, yet the JVM still cannot find the class

A Java application declares a library in Gradle `build.gradle` or Maven `pom.xml`, compiles successfully, and even its unit tests pass. However, when taking the JAR file to another machine and running `java -jar app.jar`, the application may encounter:

~~~text
java.lang.NoClassDefFoundError: com/example/lib/Service
~~~

This is not a contradiction. **Dependencies managed by the build tool** and **classes/JARs that the JVM can locate at runtime** are two separate layers of responsibility:

- **Build tool** (Gradle, Maven) reads the configuration, selects versions, downloads artifacts, resolves transitive dependencies, and assembles file sets for compilation, testing, running tasks, or packaging.
- **Java compiler** (`javac`) checks the source code against the provided **compile classpath** (or module path).
- **Java launcher and ClassLoader** locate bytecode at runtime based on the **runtime classpath/module path, module resolution, manifest, packaging layout, launcher, and custom ClassLoaders**. The JVM does not read `pom.xml`/`build.gradle` on its own to find libraries.
- **Published artifact** may contain only the application code, or include libraries alongside it, or use a special boot/shaded loader. The exact result depends on the actual packaging task/plugin.

**Lesson objective:** be able to distinguish between "a library is in the build graph" and "a class can be found by a loader at runtime"; know how to inspect scopes/configurations, launch commands, JAR/distribution contents, and actual versions; and fix the root cause in the right place instead of blindly adding dependencies.

## 2. Four layers to track from source to runtime

~~~text
Build declarations:
  implementation / compileOnly / runtimeOnly / api / Maven scope
                        |
                        v
Build tool resolves into FILES and MODULES
  compileClasspath ----> javac
  runtimeClasspath ----> Gradle run / test task / packaging task (if configured)
                        |
                        v
Actual artifact and deployment
  classes + separate JAR / app.jar + lib/*.jar / distribution / custom executable JAR
                        |
                        v
JVM launch command
  java -cp ... Main
  java -jar ... (manifest/launcher)
  java --module-path ... --module ...
                        |
                        v
ClassLoader at runtime
  classpath URLs / resolved modules / parent delegation / custom loaders
                        |
                        v
Class<?> and ClassNotFoundException / NoClassDefFoundError / LinkageError
~~~

Each arrow represents **a different configuration step**. An artifact downloaded into the Gradle cache or Maven local repository does **not** automatically become part of the classpath of a standalone `java` process. Similarly, having a JAR inside an image/container is not enough: the launcher and ClassLoader must actually see it.

### Key terms to distinguish

| Term | Description |
|---|---|
| **Declared dependency** | The project's intent in the build file; does not yet confirm a specific JAR has been resolved |
| **Resolved dependency** | The specific artifact/version selected by the build tool based on repositories, variants, scopes, and conflict rules |
| **Compile classpath** | The set of classes `javac` uses to compile source code; may differ from the set of files at runtime |
| **Runtime classpath** | The set of entries intended for running the application in a given launch configuration |
| **Module path** | The path of modules for JPMS, used with module resolution/visibility; not synonymous with classpath |
| **Artifact/distribution** | The JAR file, directory, ZIP, image, or layout produced by a build task |
| **Actual JVM launch** | Command line, working directory, JVM options, environment, launcher script, and class loader policies |
| **Defining ClassLoader** | The loader that actually defines the class; a file existing on another path does not force this loader to see it |

A dependency may appear in the **test runtimeClasspath** but not in the **production runtimeClasspath**. A dependency can also be in Gradle's `runtimeClasspath` yet not end up in a plain JAR when you only run the `jar` task.

## 3. Gradle: configurations describe needs for each phase

For a project applying Gradle's `java` or `java-library` plugin, common configurations are:

| Gradle configuration | Main code compile | Main code runtime | Meaning |
|---|---|---|---|
| `implementation` | Yes | Yes | Library needed by main code to compile and run; excluded by default from consumers' public compile API when using `java-library` |
| `api` (**java-library**) | Yes | Yes | Library part of the public API, exposed to consumers' compile classpath and needed at runtime |
| `compileOnly` | Yes | No | Needed only at compile time; runtime must provide it if the code actually uses it at runtime |
| `runtimeOnly` | No | Yes | Needed at runtime, not directly needed to compile main code |
| `annotationProcessor` | Used for annotation processing | Not a regular runtime dependency | Processor runs during the compilation phase |
| `testImplementation` | For test compile/runtime | Not a production runtime dependency just because it exists | Library for test code |
| `testRuntimeOnly` | Not for compiling tests | Present in test runtime | Dependency used only during test execution |

Example with Groovy DSL:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation 'org.example:api-client:1.2.0'
    compileOnly 'org.example:provided-api:1.2.0'
    runtimeOnly 'org.example:provider-impl:1.2.0'
    testImplementation 'org.example:testing-kit:1.2.0'
}
~~~

**This is illustrative configuration code**; the `org.example` coordinates are conceptual examples and should not be treated as existing libraries to download. Replace them with real dependencies in your project.

Gradle uses resolvable configurations, notably:

~~~text
compileClasspath  <= implementation + compileOnly (and corresponding plugin relationships)
runtimeClasspath  <= implementation + runtimeOnly
test...Classpath  <= testImplementation / testRuntimeOnly and inherited dependencies
~~~

This is the **core model of the Java plugin**. Additional plugins and custom configurations can alter the actual dependency graph. To verify, inspect the output of the actual configuration/task rather than inferring solely from the word `implementation`.

### Gradle inspection commands

On Linux/macOS:

~~~sh
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency api-client --configuration runtimeClasspath
~~~

On Windows PowerShell/CMD, use `gradlew.bat` accordingly:

~~~powershell
.\gradlew.bat dependencies --configuration compileClasspath
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency api-client --configuration runtimeClasspath
~~~

`dependencies` shows the graph for the requested configuration. `dependencyInsight` helps find **why** a dependency/version was selected. Both prove build-side resolution; they **do not prove** that the artifact was copied into a Docker image or placed on the classpath of a `java` command outside Gradle.

### `run` and `jar` are not the same

- Gradle's `application` plugin provides a `run` task that uses the configured application runtime classpath; distribution tasks can bundle dependencies alongside in a dedicated layout.
- The Java plugin's `jar` task essentially builds a JAR containing the project's own classes/resources; it **does not automatically merge all `implementation` and `runtimeOnly` JARs** into a fat/uber JAR.
- If you copy **only** the JAR produced by `jar` to another machine and run it with `java -jar` or `-cp` without the external dependencies, class visibility at runtime will differ from `gradlew run`.
- If you use another packaging task/plugin (shadow, bootJar, distribution, container plugin, etc.), you must check the contract and contents of **that specific artifact**. Do not assume all tasks behave the same.

A common case: `compileOnly` makes sense for the Servlet API provided by a servlet container; running standalone without the container will fail due to missing classes. Conversely, changing every dependency to `implementation` does not guarantee a plain JAR will bundle them.

## 4. Maven: dependency scopes are not auto-generated JVM paths

A `pom.xml` may declare:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.example</groupId>
    <artifactId>core-lib</artifactId>
    <version>1.0.0</version>
  </dependency>

  <dependency>
    <groupId>org.example</groupId>
    <artifactId>container-api</artifactId>
    <version>1.0.0</version>
    <scope>provided</scope>
  </dependency>

  <dependency>
    <groupId>org.example</groupId>
    <artifactId>driver</artifactId>
    <version>1.0.0</version>
    <scope>runtime</scope>
  </dependency>
</dependencies>
~~~

**This is an illustrative configuration**; the `org.example` coordinates are not guaranteed to have real artifacts. It clarifies the three scope meanings rather than serving as a runnable Maven sample project.

| Maven scope | Compile | Main code runtime | Test | Notes |
|---|---|---|---|---|
| `compile` (default) | Yes | Yes | Yes | Commonly used; dependencies may propagate through the dependency graph per transitivity rules |
| `provided` | Yes | No | Yes | Assumes the environment/JDK/container provides it at runtime |
| `runtime` | No | Yes | Yes | Example: a JDBC driver when application code uses standard APIs to connect |
| `test` | No | No | Yes | Not for production runtime |

Other scopes like `system`/`import` serve special contexts; do not treat them as the default runtime classpath of a `java` program. Transitive dependency rules and dependency management can also cause the actual version/artifact to differ from expectations.

**Key takeaway:** Maven `compile` means the artifact is a candidate for **the classpath of Maven's tasks**. Standard packaging tasks may still produce a JAR containing only the project's own classes. Running a plain JAR with a standalone launcher requires runtime dependencies to be published/referenced separately or bundled via a configured plugin.

### Inspecting Maven

~~~sh
mvn dependency:tree
mvn dependency:tree -Dscope=runtime
~~~

The dependency tree answers "which dependencies did Maven select" by scope/filter. To know what the **final deployed artifact** contains, inspect `target/*.jar`, the distribution directory, or the container layout. Do not infer packaging solely from a dependency appearing in `dependency:tree`.

## 5. Gradle Hands-On: the `run` task vs. a plain `jar`

A pure Java `javac`/`java` example was covered in **Compile-Time Classpath vs. Runtime Classpath**. To see the specific role of the build tool, this experiment uses the **same code and same dependency**, but runs via `gradle run` and then compares it with `java -jar` on the artifact produced by the `jar` task.

### 5.1. Prepare the project (no internet downloads needed)

Create the structure:

~~~text
build-path-demo/
├── settings.gradle
├── build.gradle
├── helper-src/demo/lib/Greeting.java
└── src/main/java/demo/app/Main.java
~~~

**`settings.gradle`:**

~~~groovy
rootProject.name = 'build-path-demo'
~~~

**`helper-src/demo/lib/Greeting.java`:**

~~~java
package demo.lib;

public final class Greeting {
    private Greeting() {}

    public static String message() {
        return "LIB_READY";
    }
}
~~~

**`src/main/java/demo/app/Main.java`:**

~~~java
package demo.app;

import demo.lib.Greeting;

public final class Main {
    public static void main(String[] args) {
        System.out.println("mainLoaded=true");
        System.out.println("library=" + Greeting.message());
    }
}
~~~

**`build.gradle` (Groovy DSL):**

~~~groovy
plugins {
    id 'application'
}

application {
    mainClass = 'demo.app.Main'
}

dependencies {
    implementation files('lib/greeting.jar')
}

tasks.named('jar') {
    manifest {
        attributes('Main-Class': 'demo.app.Main')
    }
}
~~~

Build the library locally using JDK 17+ at the example root:

~~~bash
mkdir -p out/helper lib
javac --release 17 -d out/helper helper-src/demo/lib/Greeting.java
jar --create --file lib/greeting.jar -C out/helper .
~~~

On PowerShell, replace `mkdir -p` with `New-Item -ItemType Directory -Force out/helper,lib | Out-Null`; the Java commands remain the same. Use `jar --list --file lib/greeting.jar` to verify the `demo/lib/Greeting.class` entry.

### 5.2. One dependency, two execution paths

With Gradle installed or a wrapper available (if a wrapper exists, use `./gradlew` instead of `gradle`):

~~~bash
gradle run
gradle jar
java -jar build/libs/build-path-demo.jar
~~~

The `run` task uses the `application` plugin's runtime classpath, so stdout prints:

~~~text
mainLoaded=true
library=LIB_READY
~~~

Even though `implementation files('lib/greeting.jar')` puts the library on `compileClasspath` and `runtimeClasspath`, the default `jar` task **only packages the project's own classes/resources**. The plain JAR at `build/libs/build-path-demo.jar` has a `Main-Class` manifest attribute, but neither embeds `Greeting.class` nor has a `Class-Path` manifest entry pointing to `greeting.jar`. When run with `java -jar`, the application may throw `NoClassDefFoundError: demo/lib/Greeting`. The exact resolution timing and stack trace details depend on the JVM; read the actual error instead of predicting every line of output.

Now run the same JAR with an explicit classpath:

~~~bash
# Linux/macOS
java -cp "build/libs/build-path-demo.jar:lib/greeting.jar" demo.app.Main
~~~

~~~powershell
# Windows
java -cp "build/libs/build-path-demo.jar;lib/greeting.jar" demo.app.Main
~~~

The output again shows `mainLoaded=true` and `library=LIB_READY`. The source code and dependency did not change; **packaging and the launch command** were the variables in this experiment.

### 5.3. Tracing to the right layer

| Question | Check |
| --- | --- |
| Did Gradle resolve the library for runtime? | `gradle dependencies --configuration runtimeClasspath` |
| Does the `run` task see the library? | `gradle run` and the `LIB_READY` line |
| What does the plain JAR actually contain? | `jar --list --file build/libs/build-path-demo.jar` |
| How is the JVM classpath configured? | Compare `java -jar ...` with `java -cp ... demo.app.Main` |

With Spring Boot/Shadow/application distributions or Docker, packaging and launchers can differ. Inspect the actual published artifact rather than assuming every task builds a fat JAR.

## 6. Through which paths does the JVM locate classes?

### 6.1. Launcher classpath

When running:

~~~sh
java -cp "out/classes:lib/a.jar:lib/b.jar" demo.app.Main
~~~

On systems using `:`, entries are separated by colons. An entry can be a **root directory containing a package hierarchy**, a JAR/ZIP, or another entry matching the launcher contract. On Windows, `;` is used.

- For a class named `demo.lib.Greeting` and a classpath root `out/classes`, the JVM expects the corresponding path `out/classes/demo/lib/Greeting.class`.
- The file `lib/a.jar` only aids lookup when it is an entry used by the launcher or a ClassLoader.
- A directory containing `a.jar` does not mean that JAR is on the classpath. With the classpath wildcard syntax `lib/*`, the Java launcher expands to `.jar`/`.JAR` files directly inside that directory; do not assume subdirectories are scanned recursively.
- When creating a `URLClassLoader` manually, it can use completely different URLs from the launcher's classpath.

### 6.2. ClassLoaders can delegate and isolate

The three familiar names—bootstrap, platform, and application/system—only describe the built-in loader group. Frameworks can create custom loaders for plugins, servlet applications, module layers, or dynamic loading.

Therefore:

- `System.getProperty("java.class.path")` usually shows the user classpath set by the launcher, **not** the complete list of all URLs/modules that custom loaders might use.
- `SomeClass.class.getClassLoader()` identifies the **defining loader** of the class; for certain core classes defined by the bootstrap loader, `null` is a valid return value.
- A JAR existing on the process's filesystem does not guarantee the **requesting** loader has visibility to it.
- Two different loaders can define two classes with the same binary name, resulting in distinct type identities; do not "fix" issues by copying JARs everywhere without considering isolation mechanisms.

### 6.3. The module path is not a simple second classpath

When using JPMS/named modules, the launcher typically looks like:

~~~sh
java --module-path mods --module com.example.app/com.example.app.Main
~~~

Modules are located/resolved based on root modules, `requires`, and configuration; having a JAR on the module path does not mean **every** module in the directory will be resolved. `exports`/`opens`/readability rules also affect access after a class is found.

Example breakdown:

~~~text
build tool resolves JAR
  -> selected for the module path?
  -> is the module resolved?
  -> which module does the class belong to?
  -> which loader is the module mapped to?
  -> is the package/class accessible?
~~~

Thus, if the classpath is already correct but a modular application still reports access errors or unresolved modules, inspect JPMS specifically instead of continuing to add entries to `-cp`.

## 7. Transitive dependencies, versions, and packaging

### 7.1. Transitive dependencies do not automatically enter every artifact

Example:

~~~text
app -> client.jar -> codec.jar
~~~

The build tool can resolve both `client.jar` and `codec.jar` into the runtime configuration using metadata. However, when running manually:

~~~sh
java -cp "app.jar:client.jar" demo.app.Main
~~~

and `client.jar` actually needs `codec.jar`, the runtime will still be missing `codec.jar`. **A classpath you specify manually does not re-read Maven/Gradle dependency metadata to download or include missing files.**

You must include all required artifacts on the runtime classpath/module path or use a supported distribution/packaging mechanism.

### 7.2. Compile version and runtime version can differ

Suppose the build compiles against `client-v2.jar` containing the method `Client.newFeature()`. At runtime, `client-v1.jar` is used, which has the `Client` class but **lacks that method**. The ClassLoader can still find the class, but invoking the method may throw `NoSuchMethodError`.

| Symptom | Possible cause | What to verify |
|---|---|---|
| `ClassNotFoundException` | Lookup by name did not find the class | Runtime entries, binary name, loader |
| `NoClassDefFoundError` | JVM lacks the required class definition, or a prior initialization failure occurred | Cause/stack trace; runtime classpath, initializer, version |
| `NoSuchMethodError` / `NoSuchFieldError` | Binary ABI mismatch between compile and runtime | Actual version/JAR, member signature in the class |
| `UnsupportedClassVersionError` | Classfile was compiled for a newer JVM than the runtime | `java -version`, compiler target |
| `ClassCastException` with identical class names | Different defining loaders or invalid cast logic | Actual `Class` objects and defining loaders |
| `ServiceConfigurationError` | Broken `ServiceLoader` provider declaration/class/dependency | `META-INF/services`/`provides` metadata and runtime visibility |

**Do not assume every `NoClassDefFoundError` is caused by a missing JAR.** A class that failed during static initialization can also cause subsequent uses to throw this error. Read the `Caused by` and the first error in the logs.

### 7.3. Plain JAR, fat JAR, executable JAR, and distribution

- **Plain JAR:** typically contains only the project's classes/resources; dependencies reside in other JARs.
- **Fat/uber/shaded JAR:** the build process merges classes/dependencies into one archive according to specific rules; may involve package *relocation* or resource conflicts if misconfigured.
- **Framework executable JAR:** may contain nested libraries and use a **custom launcher/ClassLoader** to locate them; do not assume `java -cp framework.jar SomeClass` has the same effect as `java -jar framework.jar`.
- **Application distribution:** may consist of a `lib/` directory, launcher scripts, and configuration files; the script constructs the classpath at launch.
- **Container image:** must contain all required artifacts and use the correct `ENTRYPOINT`/`CMD` or script; an image missing `lib/` will still fail even if the local build succeeded.

There is no reliable way to infer "the dependency is in the build file, so it is in the output" without knowing the specific packaging task.

## 8. Checklist to verify the actual path the JVM uses

When an error occurs after deployment, follow these steps in order:

1. **Identify the actual launch command:** `java -cp` or `java -jar`? Are `--module-path`/`--module` used? Which working directory does the process run from? If using a launcher script, container, or IDE, inspect the exact command they generate.
2. **Compare compile/runtime dependencies:** in Gradle, compare `compileClasspath` vs. `runtimeClasspath`; in Maven, check dependency scopes and effective resolution.
3. **Inspect the actual artifact:** `jar --list --file ...` and the deployment directory layout; were libraries copied/embedded into the JAR properly?
4. **Match binary name and path:** does the package path in the directory/JAR match the class name reported in the error?
5. **Verify the JVM/JDK and versions:** `java -version`, compiler release target, dependency JAR metadata, and differences between local and container environments.
6. **Identify the active loader:** custom ClassLoaders, classloader isolation, or plugin/servlet containers may ignore the user classpath or use a different parent.
7. **If using named modules:** check the module path, resolution, readability, `exports`, and which module the class belongs to.
8. **Narrow down to a minimal reproduction command:** run with a minimal classpath, add the missing dependency, and compare results. Keep the source unchanged to confirm the issue is in runtime wiring.

### Diagnostics via commands and APIs

On JVMs supporting unified logging (e.g., HotSpot 17+), you can try:

~~~sh
java -Xlog:class+load=info -cp "build/app:build/lib.jar" demo.app.Main
~~~

The log shows **which class was loaded from which source**; the volume is large, so filter by the class name under investigation. Log output varies across runtimes/vendors, so do **not** rely on it as fixed stdout in tests.

Inside a Java method, you can inspect:

~~~java
System.out.println(System.getProperty("java.class.path"));
System.out.println(demo.app.Main.class.getClassLoader());
System.out.println(demo.app.Main.class.getModule().getName());
~~~

This is **illustrative code**, not a standalone program. `java.class.path` does not list the full classpath of custom loaders. `getModule().getName()` may be `null` for an unnamed module; `getClassLoader()` may be `null` for a bootstrap-defined class. These are valid values that should be interpreted in context.

### Practical decision table

| Observation | Sound inference | Next step |
|---|---|---|
| Dependency is in `compileClasspath`, not in `runtimeClasspath` | Scope/configuration excludes the library from main code runtime | Check `compileOnly`/`provided` and what the environment supplies |
| Present in `runtimeClasspath`, missing in deployment | Packaging/distribution/CI did not include the artifact in output | Check JAR/image build tasks and copy/upload steps |
| Present in deployment directory, but launcher cannot see it | `-cp`/manifest/working directory does not reference it properly | Fix the launcher or distribution script |
| Class is in the JAR, yet `ClassNotFoundException` occurs | A different loader is searching, or module/path/name is wrong | Print the loader, binary name, and URL/module layout |
| Class is found, but `NoSuchMethodError` occurs | Likely an incompatible version is being used at runtime | Check which artifact/version is actually loaded |
| Works with Gradle `run` task, fails with `java -jar` | Task runtime wiring differs from the executable JAR/deployment | Compare classpaths and launcher/packaging |
| Works locally, fails in container | File copy, workdir, launch command, or Java version differs | Inspect image filesystem and runtime command |

## 9. Common misconceptions to avoid

1. **"Having `implementation` means the application JAR includes the dependency."** False for a plain `jar`; runtime configuration and packaging are separate steps.
2. **"If `compileOnly` compiles successfully, it is guaranteed to be available at runtime."** False: the dependency was intentionally excluded from the main code's runtime classpath.
3. **"Maven `provided` automatically installs the library onto the server."** False: the scope only expresses the expectation that the environment provides it; you must still ensure the environment has the right library.
4. **"`testImplementation` makes the dependency available in production."** False under standard Java plugin configuration.
5. **"`gradlew dependencies` proves the image packaged the JAR."** It only proves the graph per configuration, not the deployed artifact.
6. **"Running `java -jar app.jar -cp lib.jar` adds the library."** False: arguments after the JAR name go into `main`'s `args`; `-jar` and the app classpath must be configured per the launcher contract.
7. **"Putting a JAR in the same directory makes the JVM find it automatically."** False unless the launcher references it via classpath/manifest/loader or a suitable mechanism.
8. **"Every class error means a missing file."** It could be a version mismatch, initialization failure, JPMS access rules, or classloader identity.
9. **"`java.class.path` contains every class the JVM can see."** False for bootstrap/platform modules or custom loaders.
10. **"Putting the same class name into multiple ClassLoaders just makes it easier to find."** It can create two distinct runtime types, leading to `ClassCastException`/`LinkageError`.
11. **"`--module-path` means all JARs are already loaded."** Module resolution and class loading are still separate steps.
12. **"Building on a newer JDK will run on an older runtime JDK as long as the classpath is right."** It can fail due to classfile version, missing APIs, or module compatibility.

## 10. Practice exercises

1. A Gradle project declares `compileOnly 'org.example:api:1.0'`. The code compiles, but running standalone throws `NoClassDefFoundError`. Which configuration do you check first and why?
2. Why does `./gradlew run` succeed while `java -jar build/libs/app.jar` is missing classes, even without changing any source code?
3. Does Maven `scope=provided` mean the packaged JAR always contains the library? What environments typically supply such dependencies?
4. In the hands-on example, why does `gradle run` see `Greeting` while `java -jar build/libs/build-path-demo.jar` is missing the library?
5. Write the runtime classpath containing `build/libs/build-path-demo.jar` and `lib/greeting.jar` on Linux and Windows; how do the separators differ?
6. Why does `java -jar build/app.jar` still lack libraries after creating a manifest with `Main-Class`?
7. If a project depends on A and A depends on B, why might copying only `A.jar` to the server still not be enough?
8. If a class is found but a method is missing, why should you check `NoSuchMethodError` and the runtime version?
9. How do you check whether a JAR contains a specific class? How do you check whether Gradle resolved a library for runtime?
10. Why do `Class.getClassLoader()` and `Module.getName()` help diagnose issues that `System.getProperty("java.class.path")` cannot fully explain?
11. An app running from the module path hits an `exports` error; is simply adding the dependency to the build file guaranteed to solve it?
12. For a container image, describe three things that must align: copied files, runtime command, and dependency/loader visibility.

**Completion criteria:** accurately run both cases of the Java 17+ example; explain why compilation succeeds while runtime lacks classes; distinguish build configuration, artifact packaging, launcher, and defining loader; and know how to choose the right check when an error occurs on a deployment machine.

## 11. Official documentation

- [Gradle Java Plugin — Dependency management](https://docs.gradle.org/current/userguide/java_plugin.html): `compileClasspath`, `runtimeClasspath`, and dependency configurations for main/test code.
- [Gradle Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): distinguishing `api`, `implementation`, and exposing dependencies to consumers.
- [Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): `compile`, `provided`, `runtime`, `test` scopes and dependency transitivity.
- [Java Launcher — `java`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `-classpath`, `-jar`, `--module-path`, `--module`, and launch mechanics.
- [JAR File Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html): `Main-Class`, `Class-Path` manifest attributes, and archive structure.
- [Java SE 21 — `ClassLoader` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): delegation, defining loaders, and class lookup.

This lesson focuses on **the path from build tool dependencies to runtime class lookup**. The examples use standard Java and do not assume a specific framework, packaging plugin, or CI system.