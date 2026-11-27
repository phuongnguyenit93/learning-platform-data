# Locations of Generated Sources, Classes, and Resources by Maven or Gradle

When building a **Spring Boot** application into a **GraalVM Native Image**, Maven and Gradle produce several kinds of outputs: AOT source code, compiled Java code, copied resources, metadata for Native Image, a JAR, and a native executable. Without distinguishing these types, it is easy to look in the wrong file, edit build-generated outputs, or mistakenly conclude that a resource was packaged simply because it appears in the build directory.

In the **Build Artifacts** chapter of the **`SPRING_BOOT_NATIVE_IMAGE`** module, this lesson helps you read Maven/Gradle output directory structures, identify where Spring AOT places generated sources and classes, trace resources and metadata, and verify the final artifact. This is an essential skill when inspecting reflection/resources, troubleshooting native build errors, packaging containers, and operating native builds.

> **Note on paths:** the directories below follow common Maven, Gradle, and Spring Boot conventions. Plugin versions, source sets, output directory configurations, modules, and specific tasks can change these paths. Verify them on your actual project using task logs and build configuration; do not treat an illustrative path as an invariant guarantee across all versions.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish **input sources**, **generated sources**, **class files**, **resources**, **Native Image metadata**, and **final artifacts**.
- Read Maven's `target/` and Gradle's `build/` directory trees.
- Locate sources, classes, and resources generated during Spring AOT processing.
- Know when an output is included in a JAR or native executable versus when it is only an intermediate file.
- Use Maven, Gradle, and OS commands to trace outputs.
- Handle stale outputs, build cache issues, wrong source sets, or missing resources during native compilation.

## 2. Four Data Groups to Distinguish

A Spring Boot Native Image build can produce many files, but they fall into four main groups:

| Group | Examples | Role |
|---|---|---|
| **Developer-managed inputs** | `src/main/java`, `src/main/resources`, `src/test/java` | Project input code and resources |
| **Build-generated sources** | Generated sources from annotation processors, Spring AOT sources | Java code automatically created by tools, typically compiled in a later step |
| **Compiled/intermediate outputs** | `.class`, copied resources, metadata, temporary files | Inputs for packaging or Native Image |
| **Distributable artifacts** | Executable JAR, native executable, OCI/container image | Products used for running, deploying, or distributing |

Key point: **a file inside `target/` or `build/` is not necessarily the final artifact**. A `.java` file in generated sources may get compiled into a `.class`; a resource file may be copied into class output; only a subset of them ends up packaged into the JAR/native executable depending on configuration and reachability analysis.

### Overall Flow

~~~mermaid
flowchart TD
    S["src/main/java + src/main/resources"] --> C["Java compile / process resources"]
    T["src/test/java + src/test/resources"] --> TC["Test compile / process test resources"]
    A["Annotation processors / Spring AOT"] --> G["Generated Java sources + generated resources"]
    G --> GC["Compile generated Java"]
    C --> O["Main classes + resources"]
    GC --> O
    TC --> TO["Test classes + test resources"]
    O --> P["JAR packaging or Native Image analysis"]
    TO --> NT["Test execution / native test image"]
    P --> N["Native executable"]
    P --> J["Executable JAR"]
    N --> R["Run native / container"]
    J --> JVM["Run on JVM"]
~~~

This diagram is a logical model. A plugin may merge or split tasks, and some outputs are moved into separate directories before being placed on the classpath.

## 3. Input Structure of a Spring Boot Project

Typically, source code managed by the development team lives under `src/`:

~~~text
my-spring-app/
├── pom.xml                    # or build.gradle / build.gradle.kts
├── src/
│   ├── main/
│   │   ├── java/              # Application source code
│   │   └── resources/         # application.yml, templates, static, ...
│   └── test/
│       ├── java/              # JUnit tests
│       └── resources/         # fixtures, test configuration, sample data
└── ...
~~~

Meaning:

- `src/main/java`: primary Java code of the application, such as controllers, services, repositories, and Spring configurations.
- `src/main/resources`: resources that run with the application, such as `application.yml`, SQL migrations, templates, static files, and configuration data.
- `src/test/java`: test code, typically using JUnit, Spring Test, Mockito, and testing libraries.
- `src/test/resources`: data and configuration specific to tests; normally not packaged into production artifacts.

**Do not place auto-generated files into `src/main/java` just so the IDE can see them.** Maven and Gradle provide mechanisms to register generated source roots. If a plugin already generates code into an output directory, use the plugin/source-set configuration instead of manually copying files into main sources.

## 4. Maven: Reading the `target/` Directory

Maven typically places a module's outputs in the `target/` directory. For a Spring Boot project, a conceptual directory tree might look like this:

~~~text
my-spring-app/
├── src/
│   ├── main/java/
│   ├── main/resources/
│   ├── test/java/
│   └── test/resources/
└── target/
    ├── classes/                         # Main .class + copied resources
    ├── test-classes/                    # Test .class + test resources
    ├── generated-sources/
    │   └── annotations/                 # Annotation processor output
    ├── generated-test-sources/
    │   └── test-annotations/
    ├── spring-aot/
    │   └── main/
    │       ├── sources/                 # Spring AOT generated Java
    │       ├── resources/               # AOT-generated resources
    │       └── classes/                 # AOT compile output, depending on configuration
    ├── surefire-reports/                # JVM test reports
    ├── my-spring-app.jar                # Executable JAR, if packaged
    └── ...                              # Intermediate native/build outputs
~~~

This is an **illustrative tree**, not a mandatory directory list. For instance, `spring-aot/` only appears when running the AOT goal; the exact location and class output integration depend on the Spring Boot Maven Plugin version. If a project uses different plugins or custom output paths, directories will differ.

### 4.1. `target/classes/`

This is an important directory containing **main class files and copied resources** from the main source set after the compile/process-resources phases.

Example:

~~~text
target/classes/
├── com/example/demo/DemoApplication.class
├── com/example/demo/service/OrderService.class
├── application.yml
├── db/migration/V1__init.sql
└── templates/order.html
~~~

This forms part of the input classpath when running the application on the JVM and when plugins perform subsequent steps. However, a resource appearing in `target/classes/` is not enough to prove Native Image will keep that resource in the executable: it also depends on how the resource is accessed and whether metadata/hints are appropriate.

### 4.2. `target/test-classes/`

This directory contains test class files and test resources after `test-compile`/`process-test-resources`. It enables Maven Surefire or Native Build Tools to consume test classes as inputs.

Test resources normally **do not belong in the production artifact**. If production code accidentally depends on a file in `src/test/resources`, JVM tests may pass while the JAR or native application lacks that file.

### 4.3. `target/generated-sources/` and `target/generated-test-sources/`

This is usually where plugins or annotation processors generate Java sources. For example:

- Annotation processors generating implementations or metamodels.
- Code generators from schemas/APIs.
- Plugins generating code for serialization or mapping.

These directories are added to the compiler's source roots through plugin configuration. Not every generated source comes from Spring AOT; you must identify **which task/goal owns the file**.

### 4.4. `target/spring-aot/`

When running Spring Boot Maven Plugin AOT, you may see application-specific outputs, commonly under `target/spring-aot/main/` in default configurations across many versions:

- `sources/`: Java code generated by Spring AOT from analyzing the application's configuration/beans.
- `resources/`: resources created during the AOT process, if any.
- `classes/`: class files compiled from generated sources in pipelines/configurations that include this step.

Exact directories depend on the plugin version and how the project runs AOT. Use the `spring-boot:process-aot` goal log to determine the actual output directory.

**Generated AOT sources are not source code you should edit directly.** When changing beans, configuration, or Runtime Hints in the real sources, re-run AOT to generate fresh output.

### 4.5. `target/surefire-reports/`

Maven Surefire usually writes JVM test reports here, such as XML and text reports. If native tests use a different execution or plugin, reports may appear in a different location or format. Do not rely on the presence of `surefire-reports` to conclude that native tests ran.

## 5. Gradle: Reading the `build/` Directory

Gradle usually places each project's outputs in `build/`. Conceptual directory tree:

~~~text
my-spring-app/
├── src/
│   ├── main/java/
│   ├── main/resources/
│   ├── test/java/
│   └── test/resources/
└── build/
    ├── classes/
    │   └── java/
    │       ├── main/                  # Main class files
    │       └── test/                  # Test class files
    ├── resources/
    │   ├── main/                      # Copied main resources
    │   └── test/                      # Copied test resources
    ├── generated/
    │   ├── sources/                   # Generated sources by plugin/task
    │   ├── aotSources/                # Spring AOT sources, if generated
    │   └── aotResources/              # Spring AOT resources, if generated
    ├── reports/
    │   └── tests/                     # Gradle test reports
    ├── libs/
    │   └── my-spring-app.jar          # JAR if bootJar/jar has run
    └── native/                        # Native output by plugin/configuration
~~~

The directories `generated/aotSources`, `generated/aotResources`, and `native/` are common illustrative locations; plugins or Gradle versions may use different structures.

### 5.1. `build/classes/java/main/` and `build/classes/java/test/`

The Gradle Java plugin normally places class files for the `main` and `test` source sets into these two directories. These are outputs from `compileJava` and `compileTestJava`, not input source code.

### 5.2. `build/resources/main/` and `build/resources/test/`

`processResources` and `processTestResources` copy the corresponding resources here. If `application.yml` appears in `build/resources/main/`, it shows the resource was processed in the main source set; you still need to check packaging or native reachability if you want to confirm it is available at runtime.

### 5.3. `build/generated/`

Gradle and its plugins can produce various separate sources under `generated/`, such as annotation processor outputs, schema generator code, or Spring AOT outputs.

The Spring Boot Gradle plugin provides AOT tasks such as `processAot` and related compile/process output tasks. In many configurations, directories named `aotSources`/`aotResources` can be observed. **Do not guess output names or locations solely from task names**; run tasks with `--info` and read logs/configuration to find actual paths.

### 5.4. `build/reports/tests/`

Gradle Test normally writes reports under `build/reports/tests/` and XML results under `build/test-results/`. These are test execution results, not test classes or native executables.

### 5.5. `build/libs/`

This is typically where JARs produced by the `jar` or `bootJar` tasks reside. With Spring Boot, an executable JAR usually has its own layout, such as `BOOT-INF/classes` for application code and `BOOT-INF/lib` for dependencies.

## 6. Comparing Maven and Gradle

| Purpose | Maven (common) | Gradle (common) |
|---|---|---|
| Main classes | `target/classes/` | `build/classes/java/main/` |
| Main resources | `target/classes/` | `build/resources/main/` |
| Test classes | `target/test-classes/` | `build/classes/java/test/` |
| Test resources | `target/test-classes/` | `build/resources/test/` |
| Annotation processor sources | `target/generated-sources/annotations/` | `build/generated/sources/annotationProcessor/java/main/` |
| Spring AOT sources | Usually under `target/spring-aot/main/sources/` | Usually in generated AOT tree like `build/generated/aotSources/` |
| Test reports | `target/surefire-reports/` (Surefire) | `build/reports/tests/`, `build/test-results/` |
| JAR | Usually in `target/` | Usually in `build/libs/` |
| Native executable | Per configuration/plugin, usually under `target/` or a subdirectory | Per configuration/plugin, usually under `build/` or a subdirectory |

Both tools have different output conventions but follow the same logic: **source set → generated source/resource → compile/process → package/native build → artifact**. Do not translate Maven output paths to Gradle simply by replacing `target` with `build` without checking the plugins.

## 7. What Does Spring AOT Generate and Where Is It Used?

Spring AOT analyzes Spring configuration at build time and generates components that enable more efficient application initialization when running natively. Its outputs can be categorized into:

1. **Generated Java source:** code supporting bean initialization, configuration, and analyzed Spring components.
2. **Generated resources:** resources produced during AOT or by downstream tools.
3. **Compiled generated classes:** class files produced when compiling generated sources.
4. **Runtime hints/reachability metadata:** information for Native Image to retain elements needed for reflection, resources, serialization, proxies, or JNI.

Not every type of metadata is represented as a separate file in the same AOT directory. Some hints are encoded in generated code; dependency metadata may live inside dependency JARs; manual Native Image configuration may sit in `META-INF/native-image/`. Therefore, when investigating missing reflection/resources, inspect both project outputs and dependencies plus hint configurations.

### Runtime Hints in Source Code

Example declaring a resource hint with Spring:

~~~java
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.ImportRuntimeHints;

class AppRuntimeHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("templates/*.html");
    }
}
~~~

Then register the registrar through an appropriate application configuration, such as the `@ImportRuntimeHints(AppRuntimeHints.class)` annotation on a configuration class.

This snippet only illustrates the idea: hints must be registered from **built source code** so Spring AOT/Native Image recognizes them. Avoid overly broad patterns when unnecessary. For reflection, proxies, or serialization, use the corresponding hint APIs and run native tests to verify.

### Metadata Can Come from Dependencies

A library can carry reachability metadata under paths such as `META-INF/native-image/`. When the dependency is on the classpath, Native Image can read that metadata following GraalVM conventions. So if you look for a reflection configuration and do not find it in `src/main/resources`, it may reside inside a dependency JAR or be generated by a plugin.

## 8. How Do a JAR and a Native Executable Differ?

An **Executable JAR** is a package containing bytecode, resources, and dependencies structured so the Spring Boot Loader understands it. It requires a compatible JVM to run, for example:

~~~bash
java -jar target/my-spring-app.jar
~~~

With Gradle, the path is typically similar:

~~~bash
java -jar build/libs/my-spring-app.jar
~~~

A **Native executable** is a machine-code program created by GraalVM Native Image, not a JAR to be run with `java -jar`. Example:

~~~bash
./target/my-spring-app
# or
./build/native/nativeCompile/my-spring-app
~~~

The two native paths above are illustrative; actual names and directories must be taken from logs or plugin configuration. On Windows, the binary usually has a `.exe` extension; a Linux binary does not run directly as a Windows executable.

| Characteristic | Executable JAR | Native executable |
|---|---|---|
| Primary contents | Bytecode, resources, dependencies | Machine code and required runtime data |
| Run command | `java -jar ...` | Invoke executable directly |
| Requires JVM on target machine | Yes | Does not need a full JVM the way a JAR does |
| Build step | Java compile and package | AOT + Native Image analysis/compile/link |
| Platform characteristics | Relatively portable across compatible JVMs | Tied to target OS/CPU/ABI |

Do not confuse a directory containing `*.class` files with the final native artifact. A project may retain all intermediate classes and generated sources in the output directory while producing only a single native binary after the Native Image step.

## 9. Finding Outputs with Maven

### 9.1. Running Basic Phases

~~~bash
# Clean old module outputs
./mvnw clean

# Compile main code and process resources
./mvnw compile

# Compile test classes
./mvnw test-compile

# Package JAR if project configuration supports it
./mvnw package
~~~

After each command, inspect `target/` to identify new outputs. `compile` does not necessarily produce a JAR; `package` reaches the packaging phase.

### 9.2. Running Spring AOT

In a project with the Spring Boot Maven Plugin and appropriate AOT configuration:

~~~bash
./mvnw spring-boot:process-aot
~~~

Or run within the project's native profile, for example:

~~~bash
./mvnw -Pnative package
~~~

Profile names and executions depend on the POM. When the AOT goal runs, inspect the log to locate generated source/resource outputs. Do not assume the AOT goal ran simply because the JAR build succeeded.

### 9.3. Building a Native Image

In a project configured with Native Build Tools:

~~~bash
./mvnw -Pnative native:compile
~~~

Inspect the log to see:

- Whether the Spring AOT goal ran.
- Which path/version of the Native Image compiler was invoked.
- Where the output executable was placed.
- Whether there were metadata/resource errors or native linker errors.

If using `spring-boot:build-image`, the final output is a container image in the daemon/registry according to the buildpack configuration; there is not necessarily a visible native executable in the same location on the host. Read the builder log and image configuration.

## 10. Finding Outputs with Gradle

### 10.1. Running Java Tasks

~~~bash
# Remove old outputs
./gradlew clean

# Compile main sources and copy resources
./gradlew classes

# Compile test sources and copy test resources
./gradlew testClasses

# Package executable JAR per Spring Boot configuration
./gradlew bootJar
~~~

After these tasks, inspect `build/classes`, `build/resources`, and `build/libs`.

### 10.2. Running Spring AOT

~~~bash
./gradlew processAot
~~~

The AOT task requires the Spring Boot plugin and appropriate configuration. Use:

~~~bash
./gradlew processAot --info
~~~

to see which tasks actually ran and the generated output paths. If the task does not exist, check whether the Spring Boot Gradle plugin has been applied to the right project/subproject.

### 10.3. Building a Native Image

~~~bash
./gradlew nativeCompile --info
~~~

With GraalVM Native Build Tools, the native task typically invokes the Native Image tool and produces the executable per configuration. The output directory can be customized; do not assume `build/native/nativeCompile/` is always right.

For container builds via Spring Boot/Buildpacks:

~~~bash
./gradlew bootBuildImage
~~~

The builder image can run the native toolchain inside a container. `build/` on the host may only contain Gradle intermediates, while the container artifact is stored in the Docker daemon or registry. Distinguish **local file outputs** from **container images**.

## 11. Tracing Files on Linux, macOS, and Windows

### Linux/macOS

List output directories:

~~~bash
find target -maxdepth 4 -type d
find target -type f | sort

find build -maxdepth 5 -type d
find build -type f | sort
~~~

Find commonly inspected files:

~~~bash
find target build -type f \( -name '*.class' -o -name '*.jar' -o -name '*.json' -o -name '*.properties' \)
~~~

The command may print an error if one of the two directories does not exist yet; that simply indicates the corresponding task has not created output or the other build tool is in use.

### Windows PowerShell

~~~powershell
# List Maven/Gradle output tree if the directory already exists
Get-ChildItem -Path .\target -Recurse -File -ErrorAction SilentlyContinue
Get-ChildItem -Path .\build -Recurse -File -ErrorAction SilentlyContinue

# Find classes, JARs, and JSON metadata
Get-ChildItem -Path .\target, .\build -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in '.class', '.jar', '.json', '.properties' } |
    Select-Object FullName, Length
~~~

When there are too many outputs, filter by directory/file name or inspect only the area under investigation. There is no need to print the entire `build/` directory on every debug run.

### Searching Inside a JAR

Because a JAR is a ZIP archive, you can list its contents:

~~~bash
jar tf target/my-spring-app.jar
~~~

Or a Gradle JAR:

~~~bash
jar tf build/libs/my-spring-app.jar
~~~

Look under `BOOT-INF/classes/` to inspect main resources/classes and `BOOT-INF/lib/` for dependencies. `META-INF/native-image/` metadata may reside in dependency JARs or packaged outputs depending on libraries and plugins.

## 12. Diagnosing Errors by Identifying Which Output Is Missing

| Symptom | Check First | Possible Cause |
|---|---|---|
| Application class missing from `target/classes`/`build/classes` | Source set, package, compile task, compiler log | Source has not been compiled or task did not run |
| Resource missing from main output | `src/main/resources`, resource filtering, `process-resources`/`processResources` | Wrong path, include/exclude rule, or resource configuration |
| Generated source missing | Annotation processor or AOT task log | Plugin not applied, task did not run, AOT condition not enabled |
| AOT source exists without corresponding classes | AOT compile task and compile log | Generated source not added to source set or compilation failed |
| File exists in output but missing from JAR | JAR packaging, includes/excludes, source set | Packaging excludes output or resource belongs to test source set |
| File exists in JAR but cannot be read in native | Reachability metadata/Runtime Hints and Native Image log | Resource not registered/retained appropriately |
| Native executable not in expected directory | Native task log, `outputDirectory`, binary name | Plugin uses a different output directory or build did not reach native step |
| Source changed but binary still shows old behavior | Incremental build/cache and output file | Stale output or task did not re-run as expected |

### Ordered Investigation Workflow

1. Confirm input files exist in the right place: `src/main/java`, `src/main/resources`, `src/test/...`.
2. Confirm the responsible task/goal ran: `compile`, `processResources`, `processAot`, `nativeCompile`, or the equivalent Maven goal.
3. Inspect intermediate outputs: classes, generated sources/resources.
4. Inspect the packaged JAR or Native Image log.
5. Run runtime tests to distinguish packaging bugs from reachability or environment configuration errors.

**Do not jump straight to concluding that reflection metadata is missing** when the resource has not even been copied into main output. Identify which stage the failure occurs in.

## 13. Stale Outputs, Incremental Builds, and `clean`

Both Maven and Gradle optimize builds by re-running only necessary tasks. This speeds up builds, but when changing plugin versions, source sets, AOT configuration, or native build arguments, stale outputs can complicate troubleshooting.

### Maven

~~~bash
./mvnw clean
./mvnw -Pnative package
~~~

`clean` normally deletes the module's `target/`; rebuilding regenerates outputs from scratch. In multi-module builds, the scope of `clean` depends on the reactor and where the command is run.

### Gradle

~~~bash
./gradlew clean
./gradlew nativeCompile
~~~

`clean` deletes the project's build directory per Gradle configuration. The Gradle Build Cache may reuse valid outputs afterward; that does not mean stale outputs are broken. When suspecting cache issues, check task outcomes/logs before disabling caching broadly.

**Do not use `clean` as a reflex for every error.** Use it when you need to verify a clean build, when intermediate outputs are stale, or when configuration changes make state hard to reason about. In CI, a clean build is one verification option, while a managed cache can help save time.

## 14. Should You Edit or Commit Generated Outputs?

Typically:

- **Edit input sources** in `src/main/java`, `src/main/resources`, test sources, or build configuration.
- **Do not manually edit** `.java`/`.class` files generated by AOT or annotation processors in `target/`/`build/`; they can be overwritten on the next build.
- **Do not commit** standard output directories like `target/` and `build/`, unless the repository has a clearly defined special convention.
- **Commit Runtime Hints source code or Native Image configuration written by your team** if they are part of managed sources/configuration.
- **Do not delete dependency metadata** just because you do not see it in `src/`; inspect JAR contents and packaging flow first.

For code generated by tools outside Spring AOT, rules may differ if a project intentionally manages generated sources in the repository. Follow your project's own conventions rather than applying a single policy to every code generator.

## 15. Practice Exercises

**Exercise 1 — Distinguishing main/test resources:** `fixtures/customer.json` exists only in `src/test/resources`. Why can JVM tests read it while the production native executable lacks the file?

**Hint:** the resource belongs to the test source set, usually copied into `target/test-classes` or `build/resources/test`, not the main output used for production packaging.

**Exercise 2 — Finding Spring AOT outputs:** After running `./mvnw -Pnative package`, you do not see `target/spring-aot/`. Can you conclude Spring AOT generated no code?

**Hint:** not yet. Check the profile, the `process-aot` goal, logs, and the output directory configuration for your plugin version. AOT might not have been activated or outputs might reside elsewhere.

**Exercise 3 — Generated source not compiled:** A Java file appears under the generated source directory without a corresponding class file. What should you check?

**Hint:** whether the source root was registered, whether the AOT/generated-source compile task ran, whether the compiler reported errors, and whether task dependencies are ordered properly.

**Exercise 4 — Resource present in JAR but missing in native:** Outline the investigation steps.

**Hint:** check the resource name/path in the JAR; locate the code accessing the resource; check Spring Runtime Hints/reachability metadata; read Native Image diagnostics; re-run the executable and tests.

**Exercise 5 — Distinguishing artifacts:** What are `build/libs/app.jar` and `build/native/nativeCompile/app`?

**Hint:** the JAR contains bytecode/resources for the JVM to run; the second is an example native executable produced by Native Image, with the actual path depending on plugin/configuration.

## 16. Checklist When Handing Off Build Artifacts

- [ ] Identify main/test source sets and input resources correctly.
- [ ] Know where main/test classes are generated under `target/` or `build/`.
- [ ] Confirm annotation processor/Spring AOT tasks ran when needed.
- [ ] Verify generated sources/resources paths using actual logs.
- [ ] Check that generated Java sources are compiled into class files.
- [ ] Distinguish resources copied to class output from resources retained in Native Image.
- [ ] Confirm reachability metadata/Runtime Hints match reflection and resource usage.
- [ ] Inspect JAR contents or the native executable path.
- [ ] Run smoke/integration tests against the exact artifact type to be deployed.
- [ ] Record JDK/GraalVM, Maven/Gradle plugin versions, and the build platform.
- [ ] Do not manually edit or commit standard generated outputs.

**Takeaway:** Maven typically places outputs in `target/`, while Gradle typically places outputs in `build/`. Inside them can be auto-generated sources, class files, copied resources, AOT outputs, test reports, and artifacts. Trace by task/goal and inspect each stage to know which files are inputs, which are intermediates, and which are actually packaged into the JAR or native executable.
