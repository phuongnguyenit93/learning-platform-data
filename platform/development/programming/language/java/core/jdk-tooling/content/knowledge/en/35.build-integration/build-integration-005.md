# Compile Task in Java

A compile task is the step in a build pipeline that takes Java source code, dependencies, and compiler configuration, and produces `.class` files along with any files generated during compilation. This task can be run directly with `javac`, invoked from the Java Compiler API, or orchestrated by Maven, Gradle, or Apache Ant.

A well-defined compile task must explicitly specify the JDK/compiler used, target Java version, source roots, classpath/module path, annotation processors, output directory, and warning-handling rules. When these inputs are declared consistently, local and CI builds produce reproducible results.

This lesson was tested on Zulu/OpenJDK 24.0.2, Maven 3.9.12, Gradle 9.2.1, and Ant 1.10.15 (Ant libraries bundled with Gradle). The code examples target Java 17; you can adjust the release according to your project's baseline.

## 1. Where does the compile task fit in a build?

The compile task transforms source code into bytecode. It is typically one step in a larger build graph:

~~~text
Source files + dependencies + compiler options
                    |
                    v
              Compile task
                    |
          +---------+----------+
          |                    |
          v                    v
      .class files       Generated sources
          |                    |
          +----------+---------+
                     |
                     v
             Classes / resources
                     |
              +------+------+
              |             |
              v             v
           Test task      Package task
              |             |
              +------+------+
                     |
                     v
                JAR / WAR
~~~

A compile task typically handles:

- Source files in `src/main/java` or declared source roots.
- Dependencies required to type-check the code.
- Compiler version, language release, and encoding.
- Annotation processing and generated sources.
- Compiler diagnostics: errors, warnings, and line positions.
- The directory containing class files.

The compile task does not automatically mean running the application, running unit tests, or packaging a JAR. Build tools wire these tasks together into a lifecycle or task graph.

## 2. Main steps when the compiler processes source

When `javac` compiles a set of source files, the compiler performs these main steps:

1. **Parse:** reads source characters, checks syntax, and builds syntax trees.
2. **Enter:** registers packages, types, members, and symbols so files can reference one another.
3. **Annotation processing:** runs configured processors; processors can generate new sources or resources.
4. **Attribution and type checking:** resolves names, checks types, overloads, accessibility, and generic constraints.
5. **Flow analysis:** checks definite assignment, unreachable code, and control-flow conditions.
6. **Lowering and code generation:** transforms language constructs into appropriate bytecode.
7. **Class file output:** writes `.class` files to the output directory.

The compiler can emit multiple diagnostics in a single run. A compile task is only considered successful when the compiler returns exit code 0 or the API returns a success result; warnings can still appear if the build has not enabled `-Werror`.

## 3. Compiling directly with `javac`

Create `HelloToCompile.java`:

~~~java
public final class HelloToCompile {
    private HelloToCompile() {
    }

    public static void main(String[] args) {
        System.out.println("HELLO_FROM_COMPILE_TASK");
    }
}
~~~

Basic compilation:

~~~text
javac HelloToCompile.java
~~~

By default, the command writes `HelloToCompile.class` next to the source file. In real projects, you should separate class output from source:

~~~text
javac --release 17 -encoding UTF-8 -g -d out HelloToCompile.java
~~~

Run the generated class:

~~~text
java -cp out HelloToCompile
~~~

Stdout:

~~~text
HELLO_FROM_COMPILE_TASK
~~~

In this command:

- `--release 17`: compiles against Java 17 language, bytecode, and APIs.
- `-encoding UTF-8`: specifies the source file encoding.
- `-g`: generates debug information.
- `-d out`: writes class files to the `out` directory.

The output directory is created by the compiler if needed. When running, the classpath must point to the root directory of the package hierarchy, not directly to a `.class` file.

## 4. Common `javac` options

| Option | Purpose |
|---|---|
| `--release 17` | Selects the Java release and corresponding APIs |
| `-source 17` | Selects source syntax/language version |
| `-target 17` | Selects target bytecode level |
| `-d out` | Class output directory |
| `-classpath` / `-cp` | Locates classes and JAR dependencies on the classpath |
| `--module-path` / `-p` | Locates named modules |
| `--source-path` | Locates referenced source files |
| `-encoding UTF-8` | Source encoding |
| `-g` | Generates debug information |
| `-parameters` | Stores parameter names for reflection |
| `-Xlint:all` | Enables compiler warning categories |
| `-Werror` | Treats warnings as build errors |
| `-proc:none` | Disables annotation processing |
| `-proc:only` | Runs annotation processing only, without compiling classes |
| `-proc:full` | Runs both annotation processing and compilation |
| `--processor-path` | Where to find annotation processors |
| `-processor` | Specifies processor class names |
| `-s generated-sources` | Output directory for sources generated by annotation processors |
| `-Akey=value` | Passes custom options to annotation processors |
| `-h native-headers` | Output directory for generated JNI native headers |
| `@args.txt` | Reads options and source paths from an argument file |
| `-J-Xmx1g` | Passes JVM options to the compiler process |

### 4.1. Use `--release` instead of only `-source` and `-target`

`-source` and `-target` alone do not guarantee that code only uses APIs present in an older Java release. For example, a newer compiler might accept Java 17 syntax and emit Java 17 bytecode, while the source still accidentally calls an API introduced in JDK 24.

`--release 17` checks source code against Java 17 language rules and APIs while generating bytecode compatible with that release. Do not combine `--release` with `-source` or `-target` in the same compilation.

### 4.2. Controlling warnings

Example of strict compilation:

~~~text
javac --release 17 -Xlint:all -Werror -d out src\main\java\example\*.java
~~~

`-Xlint:all` enables many warning categories; `-Werror` turns warnings into errors. In existing projects, you can enable specific categories such as `-Xlint:deprecation` or `-Xlint:unchecked`, resolve existing warnings, and then upgrade to `-Werror`.

Do not use `-nowarn` to suppress warnings in CI. Warnings can indicate deprecated APIs, unchecked conversions, raw types, or issues worth fixing before release.

## 5. Compiling multiple source files and dependencies

Suppose we have this source tree:

~~~text
src/
  main/
    java/
      com/example/app/Main.java
      com/example/app/OrderService.java
      com/example/model/Order.java
lib/
  validation-api.jar
~~~

Compile the entire set of sources:

~~~text
javac --release 17 -encoding UTF-8 -cp "lib/validation-api.jar" -d out src/main/java/com/example/app/Main.java src/main/java/com/example/app/OrderService.java src/main/java/com/example/model/Order.java
~~~

`javac` resolves references among sources included in the same compilation. When there are many files, you can use a source path or an argument file.

Example `compile.args`:

~~~text
--release
17
-encoding
UTF-8
-classpath
lib/validation-api.jar
-d
out
src/main/java/com/example/app/Main.java
src/main/java/com/example/app/OrderService.java
src/main/java/com/example/model/Order.java
~~~

Run:

~~~text
javac @compile.args
~~~

The classpath separator depends on the operating system: Windows uses `;`, while Linux/macOS use `:`. Quote paths containing spaces according to the shell you are using.

Do not put all dependencies on the source path. The classpath is for classes/JARs on the classpath; the source path is for locating source files; the module path is for locating named modules.

## 6. Classpath and module path

### Classpath

The classpath is suitable for classpath-based applications or libraries not packaged as named modules.

~~~text
javac --release 17 -cp "lib\library-a.jar;lib\library-b.jar" -d out src\Main.java
~~~

When running, you must pass the required dependencies to the JVM:

~~~text
java -cp "out;lib\library-a.jar;lib\library-b.jar" com.example.Main
~~~

Successful class compilation does not guarantee that the runtime will find dependencies. The compile task and launch task must use matching dependencies.

### Module path

With the Java Platform Module System, dependencies are named modules placed on the module path:

~~~text
javac --release 17 --module-path mods -d out src/module-info.java src/com/example/Main.java
~~~

When compiling multiple modules at once, use `--module-source-path` and a module-based directory structure:

~~~text
javac --module-source-path src -d out -m com.example.core,com.example.app
~~~

Use `--module-path` for compiled modules and `--module-source-path` for a multi-module source tree. Do not mix these concepts with the classpath without understanding the module graph.

## 7. Annotation processing in the compile task

Annotation processors read annotations and the source model during compilation. Processors are commonly used to generate code or metadata, such as mappers, metamodels, serializers, or dependency injection registries.

Relevant options:

- `--processor-path`: dedicated classpath for processors and their dependencies.
- `--processor-module-path`: module path for modular processors.
- `-processor`: specifies concrete processor classes.
- `-proc:full`: runs both processors and compilation.
- `-proc:only`: runs processors only.
- `-proc:none`: disables processors.
- `-s`: output directory for generated source code.
- `-Akey=value`: processor configuration options.

CLI example:

~~~text
javac --release 17 -processorpath tools\my-processor.jar -processor com.example.GenerateMapper -s build\generated\sources -d build\classes src\main\java\com\example\*.java
~~~

In modern JDKs, annotation processing should be explicitly enabled/configured via processor options or `-proc:full`/`-proc:only`. Do not rely on arbitrary processors being discovered automatically on the classpath. With Maven/Gradle, declare processors as dedicated compile-task dependencies.

Processors can generate new sources, which the compiler then processes in subsequent rounds. When compilation fails, check errors from both the original sources and the generated sources. Do not manually edit generated sources, as the next build will regenerate them.

## 8. Invoking the compiler from Java with the `JavaCompiler` API

The Java Compiler API belongs to the `java.compiler` module and provides a standard interface to invoke the compiler from a Java program.

Key components:

- `ToolProvider.getSystemJavaCompiler()`: obtains the compiler from the running JDK.
- `StandardJavaFileManager`: manages source files, class files, and output locations.
- `DiagnosticCollector`: collects warnings/errors and source positions.
- `JavaCompiler.getTask(...)`: creates a `CompilationTask`.
- `CompilationTask.call()`: runs compilation and returns `true` on success.

`ToolProvider.getSystemJavaCompiler()` may return `null` if the program runs on a runtime that does not include the compiler; run the compiler host on a full JDK.

Example `CompilerTaskDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class CompilerTaskDemo {
    private CompilerTaskDemo() {
    }

    public static void main(String[] args) throws Exception {
        Path source = Path.of(args[0]);
        Path output = Path.of(args[1]);
        Files.createDirectories(output);

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A full JDK is required");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager fileManager =
                     compiler.getStandardFileManager(
                             diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
            Iterable<? extends JavaFileObject> units =
                    fileManager.getJavaFileObjects(source.toFile());

            List<String> options = List.of(
                    "--release", "17",
                    "-encoding", "UTF-8",
                    "-Xlint:all",
                    "-d", output.toString());

            boolean success = Boolean.TRUE.equals(
                    compiler.getTask(null, fileManager, diagnostics,
                            options, null, units).call());

            for (Diagnostic<? extends JavaFileObject> diagnostic
                    : diagnostics.getDiagnostics()) {
                System.err.println(diagnostic.getKind() + ":"
                        + diagnostic.getLineNumber() + ":"
                        + diagnostic.getMessage(Locale.ROOT));
            }

            if (!success) {
                throw new IllegalStateException("Compilation failed");
            }
        }

        System.out.println("COMPILATION_TASK_OK");
    }
}
~~~

The program reads the source file and output directory from arguments. `DiagnosticCollector` captures error/warning details so the application can display or store them. Close `StandardJavaFileManager` after compilation to release resources.

The `JavaCompiler` API also supports custom `JavaFileObject`s, in-memory sources, custom file managers, and alternative file systems. For complex use cases, you can keep and reuse `StandardJavaFileManager` across multiple compilation tasks instead of recreating it repeatedly.

## 9. Maven: compile phase and Maven Compiler Plugin

In the Maven lifecycle, compiling main sources happens in the `compile` phase; test sources are compiled in `test-compile`. The Maven Compiler Plugin uses `javac` by default.

A basic POM:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>compile-task-demo</artifactId>
  <version>1.0-SNAPSHOT</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration>
          <release>17</release>
          <showWarnings>true</showWarnings>
          <compilerArgs>
            <arg>-Xlint:all</arg>
            <arg>-Werror</arg>
          </compilerArgs>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Common commands:

~~~text
mvn compile
mvn test-compile
mvn clean compile
mvn package
~~~

- `mvn compile`: runs the lifecycle up to `compile`, including preceding preparation steps.
- `mvn test-compile`: compiles both main sources and test sources.
- `mvn clean compile`: deletes previous outputs and recompiles.
- `mvn package`: runs the lifecycle phases needed to compile, test, and package.

Main sources default to `src/main/java`; test sources to `src/test/java`; class outputs to `target/classes` and `target/test-classes`.

### 9.1. Annotation processors in Maven

Declare processors via `annotationProcessorPaths` on the Maven Compiler Plugin:

~~~xml
<configuration>
  <release>17</release>
  <annotationProcessorPaths>
    <path>
      <groupId>com.example</groupId>
      <artifactId>my-processor</artifactId>
      <version>1.2.0</version>
    </path>
  </annotationProcessorPaths>
</configuration>
~~~

The processor path is separate from the application's runtime dependencies. Only declare processors the project actually uses and pin their versions for stable builds. Inspect generated sources in `target/generated-sources/annotations`.

## 10. Gradle: `JavaCompile`, `compileJava`, and toolchains

When applying the `java` plugin, Gradle creates compile tasks per source set:

- `compileJava`: compiles main sources.
- `compileTestJava`: compiles test sources.
- `classes`: depends on compilation and main resource processing.
- `testClasses`: prepares classes/resources for tests.
- `build`: aggregates verification and packaging tasks.

Example `build.gradle` using Groovy DSL:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
    options.compilerArgs.addAll(['-Xlint:all', '-Werror'])
}
~~~

Run tasks:

~~~text
gradle compileJava
gradle compileTestJava
gradle classes
gradle build
~~~

In CI, prefer the Gradle Wrapper (`gradlew`/`gradlew.bat`) committed with the project to standardize the Gradle version. The toolchain selects the JDK/compiler used for compilation; `options.release` selects the target API and bytecode release.

### 10.1. Annotation processors in Gradle

Declare processors in dedicated configurations:

~~~groovy
dependencies {
    annotationProcessor 'com.example:my-processor:1.2.0'
    testAnnotationProcessor 'com.example:my-test-processor:1.2.0'
}
~~~

Gradle wires processors into the corresponding compile tasks. Generated main sources typically live under `build/generated/sources/annotationProcessor/java/main`; do not commit generated outputs unless the project workflow requires it.

## 11. Apache Ant: `<javac>` task

Ant uses project-defined targets. The `<javac>` task invokes the compiler to compile a source tree.

Example `build.xml`:

~~~xml
<project name="compile-task-demo" default="compile">
  <property name="src.dir" value="src/main/java"/>
  <property name="classes.dir" value="build/classes"/>

  <target name="compile">
    <mkdir dir="${classes.dir}"/>
    <javac srcdir="${src.dir}"
           destdir="${classes.dir}"
           release="17"
           encoding="UTF-8"
           debug="true"
           includeantruntime="false">
      <classpath>
        <pathelement location="lib/example-api.jar"/>
      </classpath>
      <compilerarg value="-Xlint:all"/>
      <compilerarg value="-Werror"/>
    </javac>
  </target>
</project>
~~~

Run:

~~~text
ant compile
~~~

Important attributes:

- `srcdir`: directory containing source files.
- `destdir`: destination directory for class files.
- `release`: target Java release on Ant versions supporting this attribute.
- `encoding`: source encoding.
- `debug`: generates debug information.
- `includeantruntime="false"`: prevents automatically adding the Ant runtime to the compile classpath.
- `<classpath>`: declares dependencies.
- `<compilerarg>`: passes options directly to the compiler.

An Ant target can depend on other targets via `depends`, for example `compile` depending on `init` to create the output directory. Use `fork="true"` when you need to run a separate compiler process; by default Ant may invoke the compiler inside the JVM running Ant. Check the JDK/Ant version and compiler adapter before using specialized options.

## 12. Comparing compile tasks across tools

| Aspect | `javac` | JavaCompiler API | Maven | Gradle | Ant |
|---|---|---|---|---|---|
| Control mechanism | CLI | Java code | Lifecycle/plugin | Task graph | XML target |
| Compiler | `javac` | Compiler SPI | Compiler plugin | `JavaCompile` | `<javac>` |
| Dependencies | `-cp`, module path | File manager/options | Maven dependencies | Configurations | `<classpath>` |
| Default output | Source folder if `-d` is omitted | Controlled by file manager/options | `target/classes` | `build/classes/java/main` | `destdir` |
| Generated sources | `-s` | File manager/processor | Plugin config | Processor configuration | Processor/compiler args |
| Incremental build | Does not orchestrate project graph | Managed by application | Plugin/lifecycle | Task inputs/outputs and compiler analysis | File timestamp checks per task |
| Best suited for | Direct compilation, scripts | Applications invoking compiler | Maven projects | Gradle projects | Existing XML builds |

Choose the tool matching your project's build system. Avoid invoking `javac` manually to replace Maven/Gradle compile tasks, as doing so bypasses the dependency graph, annotation processors, generated sources, toolchains, and incremental state configured by the build.

## 13. Incremental compilation and clean builds

Incremental compilation recompiles only what is necessary based on inputs/outputs and dependency relationships tracked by the build tool. Gradle uses task inputs/outputs and dependency analysis to avoid re-running tasks unnecessarily; Maven Compiler Plugin also has incremental compilation support; Ant `<javac>` compares source/class timestamps to decide which files to compile.

Benefits:

- Reduces build times for small changes.
- Avoids recompiling unrelated modules.
- Keeps the feedback loop fast during development.

However, stale outputs can hide issues if build scripts, annotation processors, generated files, or dependencies change without properly declared task inputs.

When stale classes are suspected:

~~~text
mvn clean compile
~~~

~~~text
gradle clean compileJava
~~~

~~~text
ant clean compile
~~~

A `clean` target must be defined in the Ant build file to use the command above. With Gradle and Maven, the `clean` task/phase is provided by plugins/lifecycles.

Do not run a clean build on every step if the project has reliable incremental builds; use clean builds as a verification step when debugging build caches, generated sources, or inconsistent class outputs.

## 14. Multi-module builds and per-module compile tasks

In multi-module projects, each module has its own compile task, and inter-module dependencies determine execution order.

Maven reactor example:

~~~text
parent
  core
  service
  web
~~~

`service` depends on `core`, and `web` depends on `service`. The Maven reactor builds dependencies first before compiling dependent modules. You can run from the root:

~~~text
mvn compile
~~~

Or select a module and its required dependencies:

~~~text
mvn -pl web -am compile
~~~

In Gradle multi-project builds, task paths can target specific modules:

~~~text
gradle :core:compileJava
gradle :service:compileJava
gradle :web:compileJava
~~~

When building a module directly, ensure project dependencies have been built/resolved. Avoid manually copying another module's class output onto the classpath when the build system already supports project dependencies.

## 15. Toolchains, compiler versions, and Java releases

Three concepts should be distinguished:

- **Build-running JDK:** the JVM executing Maven/Gradle/Ant.
- **Compiler toolchain:** the JDK/compiler actually used for the compile task.
- **Target release:** the Java language/API/bytecode level the artifact must be compatible with.

A build can run on JDK 24, use the JDK 24 compiler, and emit Java 17-compatible classes via `--release 17`. This does not automatically guarantee that all plugins or annotation processors run on every JDK; verify compatibility separately.

Maven can use the Maven Toolchains Plugin to select the appropriate compiler JDK. Gradle provides Java toolchains via `java { toolchain { ... } }`. Ant can select a compiler executable/adapter via configuration and environment.

Explicitly specify the JDK vendor/version, compiler plugin, Gradle Wrapper, and release target in CI. Do not rely on a developer's `JAVA_HOME` when builds must use the exact same compiler across all machines.

## 16. Diagnostics and compile quality control

A compiler diagnostic typically includes:

- Kind: `ERROR`, `WARNING`, `MANDATORY_WARNING`, or `NOTE`.
- Source file or compilation unit.
- Line/column.
- Message describing the issue.

A CI compile task should enable appropriate warnings:

~~~text
javac --release 17 -encoding UTF-8 -Xlint:all -Werror -d out src\main\java\*.java
~~~

If a codebase cannot enable `-Werror` immediately, enable `-Xlint:all`, categorize existing warnings, and address them incrementally. Avoid disabling all warnings just to get a green build.

Useful practices:

- Pin the compiler release and encoding.
- Keep debug information if stack traces/source mapping are needed.
- Use `-parameters` if frameworks require parameter names via reflection.
- Separate the annotation processor path from runtime dependencies.
- Place generated sources/outputs in dedicated directories.
- Ensure CI fails when the compile task fails.
- Do not ignore diagnostics just because a local IDE still compiles.

## 17. Java 17+ example: compiling via CLI and `JavaCompiler` API

Create `HelloToCompile.java`:

~~~java
public final class HelloToCompile {
    private HelloToCompile() {
    }

    public static void main(String[] args) {
        System.out.println("HELLO_FROM_COMPILE_TASK");
    }
}
~~~

Create `CompilerTaskDemo.java` using the code from section 8. Compile the CLI fixture:

~~~text
javac --release 17 -encoding UTF-8 -Xlint:all -Werror -g -d cli-out HelloToCompile.java
java -cp cli-out HelloToCompile
~~~

Stdout:

~~~text
HELLO_FROM_COMPILE_TASK
~~~

Compile the API runner:

~~~text
javac --release 17 -Xlint:all -Werror -d runner-out CompilerTaskDemo.java
~~~

Invoke `CompilationTask` to compile the source:

~~~text
java -cp runner-out CompilerTaskDemo HelloToCompile.java api-out
~~~

Stdout from the compiler runner:

~~~text
COMPILATION_TASK_OK
~~~

Run the class generated by the API:

~~~text
java -cp api-out HelloToCompile
~~~

Stdout:

~~~text
HELLO_FROM_COMPILE_TASK
~~~

This example demonstrates that a compile task can be invoked from the CLI or from Java code. Both approaches require a compiler host and valid output paths.

## 18. Compile task examples in Maven, Gradle, and Ant

A `HelloToCompile.java` fixture like the one in section 17 can be placed in `src/main/java`.

### Maven

Use the POM from section 9 and run:

~~~text
mvn compile
java -cp target/classes HelloToCompile
~~~

Stdout:

~~~text
BUILD_TOOL_COMPILE_OK
~~~

### Gradle

Use the `build.gradle` from section 10, place the source in `src/main/java`, then run:

~~~text
gradle compileJava
java -cp build/classes/java/main HelloToCompile
~~~

Stdout:

~~~text
BUILD_TOOL_COMPILE_OK
~~~

### Ant

Use the `build.xml` from section 11, place the source in `src/main/java`, then run:

~~~text
ant compile
java -cp build/classes HelloToCompile
~~~

Stdout:

~~~text
ANT_COMPILE_OK
~~~

When testing, `HelloToCompile.java` should print the exact line matching each build's fixture. Output directories differ by tool; the `java -cp` command must point to the directory containing the package root.

## 19. Troubleshooting compile tasks

### `cannot find symbol`

**Cause:** missing import, source file not included in compilation, missing dependency on classpath, or wrong type name.

**Resolution:** check source roots, `-cp`, module path, package declarations, and dependency versions. With build tools, inspect the actual task's compile classpath.

### `package ... does not exist`

**Cause:** missing JAR, wrong dependency scope, or a library is a named module placed improperly on the classpath/module path.

**Resolution:** inspect the dependency tree, `--class-path`, `--module-path`, and `module-info.java`.

### `invalid source release` or `release version not supported`

**Cause:** the compiler JDK is too old for the target release.

**Resolution:** select a newer toolchain or lower the release to match the supported baseline. Check `javac -version` and the JDK actually used by Maven/Gradle.

### Code compiles on a newer JDK but fails on an older JDK

**Cause:** using `-source`/`-target` without API restriction, or the build task not applying the release as expected.

**Resolution:** use `--release` or configure `maven.compiler.release`/`options.release`, then run tests on the target runtime.

### `ToolProvider.getSystemJavaCompiler()` returns `null`

**Cause:** the program is running on a runtime without a compiler, or the runtime image stripped the compiler module.

**Resolution:** run the host program on a full JDK that includes `jdk.compiler`, or configure an appropriate compiler service.

### Annotation processor does not run

**Cause:** processor is not on the processor path, processing is disabled, wrong processor class name, or processor dependencies fail to resolve.

**Resolution:** configure `--processor-path`, `--processor-module-path`, `-processor`, or `-proc:full`; declare `annotationProcessorPaths` in Maven or `annotationProcessor` in Gradle.

### Generated sources are not compiled

**Cause:** incorrect generated-source output path, processor did not run, or processor threw an error.

**Resolution:** check `-s`, the generated-source directory, processor diagnostics, and compilation rounds. Do not edit generated files directly.

### Local build succeeds but CI fails

**Cause:** different JDK/toolchain, environment variables, encoding, dependency cache, file case sensitivity, or compiler options.

**Resolution:** use wrappers/toolchains, pin dependency/plugin versions, set UTF-8 encoding, and run a clean build in CI.

### Build does not recompile after changing dependencies or generated sources

**Cause:** incomplete task inputs/outputs or stale incremental state/cache.

**Resolution:** run a clean compile to verify, check dependency and annotation processor declarations, then fix task configuration so incremental builds track all inputs.

### Warnings fail the build

**Cause:** `-Werror` is enabled or warnings are configured as errors.

**Resolution:** read the diagnostic carefully, fix the code, or intentionally adjust lint categories. Do not remove `-Werror` globally just to hide a single warning.

## 20. Process for designing a reliable compile task

1. Choose the JDK/compiler toolchain appropriate for the project.
2. Determine the Java release the artifact must support.
3. Declare source roots and output directories.
4. Distinguish classpath, module path, and processor path.
5. Declare annotation processors and generated-source outputs explicitly.
6. Set source encoding to UTF-8.
7. Enable debug symbols when runtime investigation is needed.
8. Enable appropriate compiler lints; graduate toward `-Werror`.
9. Let the build tool manage the task graph and dependencies instead of assembling classpaths manually.
10. Use incremental compilation for fast development loops.
11. Run clean compiles when verifying compiler, plugin, processor, or dependency changes.
12. Run tests/packaging after compilation to confirm class outputs work in a real runtime.
13. Pin wrapper, plugin, toolchain, and dependency versions in CI.
14. Preserve compiler diagnostics in build logs for traceability.

## 21. Checklist before putting a compile task into CI

- [ ] Build JDK and compiler toolchain are defined.
- [ ] Target release is set via `--release`/`options.release`.
- [ ] Source roots and class output directories are declared.
- [ ] Classpath/module path contains the exact compile dependencies.
- [ ] Annotation processors are explicitly declared with pinned versions.
- [ ] Generated sources have a dedicated directory and are not manually edited.
- [ ] Source encoding is set to UTF-8.
- [ ] Debug information and parameter metadata match runtime requirements.
- [ ] Compiler warnings are enabled and handled intentionally.
- [ ] Compilation failures fail CI.
- [ ] Maven/Gradle/Ant plugins and build tool versions are pinned.
- [ ] Clean build succeeds in CI.
- [ ] Output classes run on the target runtime.
- [ ] Incremental builds do not mask stale sources or generated outputs.

## 22. References

- Oracle JDK 24 — `javac` Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html
- Java SE 24 — `JavaCompiler` API: https://docs.oracle.com/en/java/javase/24/docs/api/java.compiler/javax/tools/JavaCompiler.html
- Java SE 24 — `JavaCompiler.CompilationTask`: https://docs.oracle.com/en/java/javase/24/docs/api/java.compiler/javax/tools/JavaCompiler.CompilationTask.html
- Apache Maven Compiler Plugin: https://maven.apache.org/plugins/maven-compiler-plugin/
- Maven Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Gradle Java Plugin: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle `JavaCompile` API: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.JavaCompile.html
- Apache Ant `<javac>` task: https://ant.apache.org/manual/Tasks/javac.html

A compile task turns source code into bytecode according to the declared compiler, dependencies, and release. `javac` fits direct compilation; the `JavaCompiler` API fits applications that need to invoke the compiler; Maven, Gradle, and Ant orchestrate compile tasks within a build graph. Standardizing toolchains, `--release`, processor paths, diagnostics, and output directories keeps builds reliable from developer machines to CI.