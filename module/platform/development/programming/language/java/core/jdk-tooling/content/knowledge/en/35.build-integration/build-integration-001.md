# Invoking javac from a Build

## 1. What is build integration?

Build integration is the practice of incorporating Java compilation into a repeatable build workflow. Instead of running `javac` manually every time, a build script or build tool defines the source files, dependencies, compiler options, output directory, and the order of steps to execute.

A typical Java build workflow consists of:

1. Selecting the JDK and compiler version.
2. Discovering source files in the source set.
3. Preparing the classpath, module path, and annotation processors if applicable.
4. Invoking the compiler with consistent options.
5. Copying resources into the output directory.
6. Compiling test sources and running tests.
7. Packaging classes into a JAR or other artifact.

`javac` is responsible for compiling source files into `.class` bytecode. It does not manage dependencies, resources, tests, packaging, versioning, or the task graph on its own. The build tool orchestrates those parts.

You can invoke the compiler directly from a script, or use a build tool such as Apache Ant, Maven, or Gradle. With Maven and Gradle, distinguish between using the Java Compiler API inside the build process versus forking a separate `javac` process. If the goal is to invoke the external executable, enable the corresponding fork mode.

## 2. Selecting the JDK and identifying the compiler

Before integrating, check which tools the build actually uses:

~~~bash
java --version
javac --version
mvn --version
gradle --version
~~~

`java --version` shows the runtime of the `java` command. `javac --version` shows the compiler found on `PATH`. `mvn --version` and `gradle --version` show the JDK running the build tool itself.

These three versions can differ if multiple JDKs are installed on the machine or if the build tool uses its own toolchain. For example, Maven can run on JDK 24 while the compiler is configured from a different JDK.

Clearly distinguish two targets:

- **Compiler JDK:** the JDK providing the `javac` executable or Java Compiler API used by the build tool.
- **Target Java release:** the Java version with which the source code and bytecode must be compatible.

Using `--release 17` with `javac 24` can still produce class files for Java 17, provided JDK 24 supports that release. `--release` does not select the compiler JDK itself; the toolchain or `PATH` determines which compiler is invoked.

In CI, pin the JDK/toolchain and build plugin versions so that all build machines use the same environment.

## 3. Source and output directory structure

A common layout:

~~~text
javac-build-demo/
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/example/
│   │   │       ├── Main.java
│   │   │       └── Greeting.java
│   │   └── resources/
│   │       └── message.txt
│   └── test/
│       ├── java/
│       └── resources/
├── build/
└── pom.xml or build.gradle or build.xml
~~~

`src/main/java` contains the main source code. `src/main/resources` contains configuration files, templates, images, or other resources that need to be copied to the class output. `src/test/java` and `src/test/resources` are for tests.

Keep output separate from source:

| Build tool | Main class output | Common artifact |
|---|---|---|
| javac script | `build/classes` | Packaged manually or into a JAR. |
| Ant | `build/classes` | Defined by targets in `build.xml`. |
| Maven | `target/classes` | `target/*.jar`. |
| Gradle | `build/classes/java/main` | `build/libs/*.jar`. |

Do not write `.class` files into the source directory. On clean, the build can delete old outputs without affecting source code.

## 4. Basic javac command in a build

General syntax:

~~~bash
javac [options] source-files
~~~

A common command:

~~~bash
javac --release 17 -encoding UTF-8 -g -d build/classes src/main/java/com/example/Greeting.java src/main/java/com/example/Main.java
~~~

Meaning:

| Option | Effect |
|---|---|
| `--release 17` | Compiles against Java 17 language, Java SE APIs, and class file format. |
| `-encoding UTF-8` | Reads source files using UTF-8. |
| `-g` | Generates debug information such as line numbers and local variables. |
| `-d build/classes` | Writes class files to the output directory. |
| Source paths | The `.java` files to compile. |

If the source declares `package com.example`, the compiler creates the `com/example` directory inside the output directory.

After compiling, run the program with:

~~~bash
java -cp build/classes com.example.Main
~~~

The main class name is the fully qualified name including the package. Do not pass the `Main.class` file path to the `java` command.

## 5. Important options when invoking javac

### Selecting the Java version

Use:

~~~bash
javac --release 17 ...
~~~

`--release` controls the source language, available Java SE APIs, and target class file version. This is usually the best choice when a build needs compatibility with a specific Java version.

Do not combine `--release` with `-source` or `-target` in the same command. Those older options do not provide full API targeting like `--release`.

### Encoding and debug information

~~~bash
javac --release 17 -encoding UTF-8 -g ...
~~~

Use UTF-8 consistently for source code. `-g` helps debuggers display lines and local variables. If you want finer control:

- `-g:lines`: line numbers.
- `-g:vars`: local variables.
- `-g:source`: source file information.
- `-g:none`: generate no debug information.

### Warnings and compiler diagnostics

~~~bash
javac --release 17 -Xlint:all ...
~~~

`-Xlint:all` enables all supported compiler warnings. You can combine it with `-Werror` to turn warnings into build errors:

~~~bash
javac --release 17 -Xlint:all -Werror ...
~~~

Only enable `-Werror` when the project handles warnings consistently. A new warning from a JDK or dependency update can fail the build even though the source still compiles.

### Class output and generated files

- `-d`: where to write class files.
- `-s`: where to write source files generated by annotation processors.
- `-h`: where to write native header files generated by `javac`.
- `-parameters`: stores method/constructor parameter names so reflection can read them.
- `-proc:none`: disables annotation processing.
- `-processorpath`: where to find annotation processors.

Separate generated sources from developer-written sources so clean and incremental builds remain predictable.

## 6. Classpath and dependencies

When sources reference classes from JARs or another output directory, the compiler needs to know where to find dependencies:

~~~bash
javac --release 17 -cp "lib/*" -d build/classes @build/sources.args
~~~

`-cp` and `--class-path` are equivalent. The wildcard `lib/*` includes all JARs in the `lib` directory on the classpath. This wildcard does not search subdirectories recursively.

The classpath separator depends on the operating system:

| Operating system | Example |
|---|---|
| Windows | `build/classes;lib/a.jar;lib/b.jar` |
| Linux/macOS | `build/classes:lib/a.jar:lib/b.jar` |

When running the application, the runtime also needs the dependencies:

~~~bash
# Windows
java -cp "build/classes;lib/*" com.example.Main

# Linux/macOS
java -cp "build/classes:lib/*" com.example.Main
~~~

If the compiler found a dependency but the runtime command omits it, the program may fail with `NoClassDefFoundError` or `ClassNotFoundException`.

Maven and Gradle construct the classpath automatically from declared dependencies. This is a key reason to delegate dependency resolution to a build tool rather than concatenating classpath strings manually in a script.

## 7. Module path when building JPMS projects

Projects using the Java Platform Module System may require `--module-path` instead of the traditional classpath.

Example for a module:

~~~bash
javac --release 17 --module-path lib -d build/modules --module-source-path src -m com.example.app
~~~

In a module source layout, each module has its own directory and `module-info.java` file. `--module-source-path` points to the root containing module sources; `-m` selects the module to compile.

Common options:

- `--module-path`: where to find compiled modules or modular JARs.
- `--module-source-path`: where to find sources for multiple modules.
- `--add-modules`: adds root modules to the resolved module set.
- `--patch-module`: augments or overrides the contents of a module.

Do not mix the classpath and module path arbitrarily. Determine whether each dependency is a module or a classpath artifact and configure it consistently at both compile time and runtime.

## 8. Using argument files to invoke javac

When a project has many source files or the command line becomes too long, use an argument file:

~~~bash
javac @build/javac.args
~~~

Example contents of `build/javac.args`:

~~~text
--release
17
-encoding
UTF-8
-g
-d
"build/classes"
"src/main/java/com/example/Greeting.java"
"src/main/java/com/example/Main.java"
~~~

Each line is an argument. Enclose paths containing spaces in double quotes. Options and their values can be placed on separate lines as shown.

Argument files are useful because they:

- Avoid shell or OS command-line length limits.
- Are easy to generate as a source list from a build script.
- Make it easy to inspect the exact files passed to the compiler.
- Keep the compiler invocation command short and stable.

On Windows, backslashes in an argument file are treated as escape characters. Use forward slashes in paths and quote paths containing spaces to prevent path separators from disappearing. Pass an argument file path containing spaces as a properly quoted argument from the shell.

Do not write a UTF-8 BOM to an argument file if the compiler environment does not handle BOMs. When creating files from PowerShell 5.1, `Set-Content -Encoding utf8` writes a BOM; you can use `System.IO.File.WriteAllLines` with `UTF8Encoding(false)` to write UTF-8 without BOM.

## 9. Invoking javac with a PowerShell build script

A script can discover sources, generate an argument file, invoke the compiler, check the exit code, and copy resources.

Example `build.ps1` in the project root:

~~~powershell
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$sourceRoot = Join-Path $root 'src/main/java'
$resourceRoot = Join-Path $root 'src/main/resources'
$classesDir = Join-Path $root 'build/classes'
$argFile = Join-Path $root 'build/javac.args'

New-Item -ItemType Directory -Force -Path $classesDir | Out-Null

$sourceArgs = Get-ChildItem $sourceRoot -Recurse -Filter '*.java' |
    ForEach-Object {
        '"' + $_.FullName.Replace('\', '/') + '"'
    }

$compilerArgs = @(
    '--release', '17',
    '-encoding', 'UTF-8',
    '-g',
    '-d', ('"' + $classesDir.Replace('\', '/') + '"')
) + $sourceArgs

[System.IO.File]::WriteAllLines(
    $argFile,
    [string[]]$compilerArgs,
    [System.Text.UTF8Encoding]::new($false)
)

& javac "@$argFile"
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if (Test-Path $resourceRoot) {
    Get-ChildItem $resourceRoot -Force |
        Copy-Item -Destination $classesDir -Recurse -Force
}

& java -cp $classesDir com.example.Main
exit $LASTEXITCODE
~~~

Run:

~~~powershell
.\build.ps1
~~~

The script uses absolute paths so it does not depend on which directory the terminal was opened from. The argument file handles source paths containing spaces. The build stops immediately if the compiler returns a non-zero exit code; do not run the application with stale class output after a failed compilation.

In PowerShell 7, you can use the `utf8NoBOM` encoding for text files. In PowerShell 5.1, pay attention to the encoding differences between `Set-Content` and `Out-File`.

## 10. Invoking javac from Apache Ant

Ant provides a `javac` task to compile a source directory:

~~~xml
<project name="javac-build-demo" default="compile">
    <target name="clean">
        <delete dir="build"/>
    </target>

    <target name="compile">
        <mkdir dir="build/classes"/>
        <javac
            srcdir="src/main/java"
            destdir="build/classes"
            release="17"
            encoding="UTF-8"
            debug="true"
            includeantruntime="false"
            fork="true"/>
        <copy todir="build/classes">
            <fileset dir="src/main/resources"/>
        </copy>
    </target>
</project>
~~~

Run:

~~~bash
ant clean compile
~~~

Key attributes:

- `srcdir`: root directory containing source files.
- `destdir`: where to write class files.
- `release`: target Java release to compile for.
- `encoding`: source file encoding.
- `debug`: generate debug information.
- `includeantruntime="false"`: prevents automatically adding the Ant runtime to the compile classpath.
- `fork="true"`: runs the compiler in a separate process.

If `fork` is false, Ant can use the compiler API inside the JVM running Ant. When you need to invoke the external `javac` executable, set `fork="true"`. Ant can use the compiler from `PATH`; if you need a specific JDK, configure `executable` appropriately for your OS.

Ant supports incremental compilation based on source/class timestamps and task attributes. The `clean` target removes old classes before a clean build.

## 11. Invoking javac from Maven

Maven uses the standard directory layout and the Maven Compiler Plugin to compile sources in `src/main/java`. Example `pom.xml` configuration:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>javac-build-demo</artifactId>
    <version>1.0.0</version>

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
                    <encoding>UTF-8</encoding>
                    <fork>true</fork>
                    <showWarnings>true</showWarnings>
                    <compilerArgs>
                        <arg>-Xlint:all</arg>
                    </compilerArgs>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Run:

~~~bash
mvn clean verify
~~~

Maven automatically executes the necessary phases, including resource processing, compile, test compile, test, and package according to the lifecycle. The default class output is `target/classes`; JARs are created in `target`.

By default, the Maven Compiler Plugin can use the Java Compiler API inside the Maven process. `fork=true` instructs the plugin to launch a separate compiler process. When fork is enabled, you can specify `executable` in the plugin configuration if you want a specific compiler; ensure the path matches Windows/Linux/macOS or use Maven Toolchains to select the JDK.

In a lab with JDK 24.0.2, Maven 3.9.12 and Compiler Plugin 3.13.0 printed:

~~~text
Compiling 2 source files with javac [forked debug release 17] to target\classes
BUILD SUCCESS
~~~

A subsequent build reported `Nothing to compile - all classes are up to date` when sources had not changed. This is the incremental behavior of the compiler plugin in that run.

Dependencies declared in `dependencies` are resolved by Maven and placed on the compiler classpath. You do not need to manually concatenate JAR paths.

## 12. Invoking javac from Gradle

The Gradle Java Plugin provides the `compileJava` task and `JavaCompile` type. Example `build.gradle`:

~~~groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
    options.debug = true
    options.fork = true
    options.compilerArgs.addAll(['-Xlint:all'])
}
~~~

Run:

~~~bash
gradle clean build
~~~

Or use the Gradle Wrapper committed with the project:

~~~bash
./gradlew clean build
~~~

On Windows:

~~~powershell
.\gradlew.bat clean build
~~~

`java.toolchain` selects the JDK providing the compiler. The build machine needs a matching JDK or a configured toolchain resolver to provision one. `options.release` determines the target API and bytecode. You can use a newer compiler JDK with an older release if that JDK supports the required release.

`options.fork=true` tells Gradle to run the compiler in a separate process. Without fork, Gradle can use the compiler API via a worker process. You do not need to build command lines for every source file; Gradle manages source sets, dependency classpaths, resources, and outputs.

Default outputs:

- Main classes: `build/classes/java/main`.
- Main resources: `build/resources/main`.
- Test classes: `build/classes/java/test`.
- JAR: `build/libs`.

In the lab, Gradle 9.2.1 used JDK 24.0.2 as the toolchain with `options.release=17`. The `compileJava` and `jar` tasks succeeded; the next build reported `UP-TO-DATE` when inputs were unchanged.

## 13. Comparing compiler invocation across build tools

| Build tool | Configuration | Compiler invocation |
|---|---|---|
| Script | Invoke `javac` and check exit code. | Direct external process. |
| Ant | `<javac fork="true"/>`. | External process when fork is enabled. |
| Maven | `maven-compiler-plugin` with `fork=true`. | External process when fork is enabled; can use compiler API by default. |
| Gradle | `JavaCompile.options.fork=true`. | External compiler process when fork is enabled; can use compiler API by default. |

Choose the approach that fits the project:

- Use a script when the project is small, has few dependencies, and needs a simple build command.
- Use Ant when you need custom targets and explicit XML build rules.
- Use Maven when you want standard lifecycles, dependency management, and project conventions.
- Use Gradle when you need a flexible build graph, custom tasks, and toolchain integration.

Do not build a separate wrapper around `javac` if Maven or Gradle already manages the compile task. You can add tasks or compiler options to the existing build tool while preserving the dependency graph and incremental behavior.

## 14. Annotation processing and generated sources

Annotation processors run during compilation to inspect annotations and generate additional sources or classes—for example, processors that generate metamodels, mappers, serializers, or boilerplate code.

When invoking `javac` directly, configure the processor path and output directory:

~~~bash
javac --release 17 \
  -processorpath tools/processor.jar \
  -processor com.example.GenerateProcessor \
  -s build/generated-sources \
  -d build/classes \
  @build/sources.args
~~~

Options:

- `-processorpath`: classpath for annotation processors.
- `-processor`: name of the processor to run.
- `-s`: where to write generated source files.
- `-Akey=value`: passes an option to the processor.

Starting with JDK 23, annotation processing no longer runs automatically just because a processor happens to be on the classpath. Declare processors explicitly via `-processor`, `-processor-path`, `--processor-module-path`, or select `-proc:full` mode when annotation processing is genuinely needed.

In Maven, declare processors via `annotationProcessorPaths` in the Maven Compiler Plugin. In Gradle, use the dedicated `annotationProcessor` configuration. Keep processors separate from runtime dependencies so the application classpath does not include unnecessary build tools.

## 15. Compiling tests and copying resources

`javac` only compiles Java source files. It does not automatically copy files from `src/main/resources` into the output directory.

With a script or Ant, add a resource copy step after compilation. With Maven, the resources plugin handles this during the lifecycle. With Gradle, the `processResources` task handles the resources source set.

Test sources need their own compile classpath, including the main classes and test dependencies. Maven uses `maven-compiler-plugin` for `testCompile`; Gradle uses the `compileTestJava` task.

Do not mix test classes into production output unless intentional. Keep separate:

- Main sources and main resources.
- Test sources and test resources.
- Generated sources.
- Main class output and test class output.

This separation allows packaging production artifacts without bundling test frameworks or test fixtures into the runtime.

## 16. Incremental builds and clean

Incremental builds only re-run tasks affected by changed inputs. The Maven Compiler Plugin can detect modified sources; Gradle uses task input/output tracking to mark tasks `UP-TO-DATE`; Ant `javac` uses timestamp checks.

Some key principles:

- Keep source inputs and output directories separate.
- Do not edit files directly inside `target/classes` or `build/classes`.
- Declare dependencies and compiler options in the build file so tasks can track them.
- Place generated sources in a dedicated directory.
- Use `clean` when you need to verify a build from an empty state.

Common clean commands:

~~~bash
# Maven
mvn clean verify

# Gradle
gradle clean build

# Ant
ant clean compile
~~~

If an old class remains after its source file is deleted or moved to another package, the build output may contain stale artifacts. A clean build helps catch these issues.

Do not run `clean` before every compile unnecessarily. Incremental builds are faster and accurately determine which tasks need to re-run.

## 17. Verifying output and Java release

After compiling, verify that class files were created in the expected location. Run the application from the class output:

~~~bash
java -cp build/classes com.example.Main
~~~

You can use `javap` to inspect a class file:

~~~bash
javap -verbose -classpath build/classes com.example.Main
~~~

Look for the `major version` line. Common values:

| Java release | Class file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 24 | 68 |

`javap` confirms the actual target bytecode version. However, a matching class file version does not prove that all dependencies are compatible with the target runtime; always test on the target JDK.

In the lab, all four compilation methods—javac argument file, Ant, Maven, and Gradle—produced class files with major version 61 when configured with `--release 17` or its equivalent.

## 18. Common errors when invoking javac from a build

| Symptom | Common cause | Resolution |
|---|---|---|
| `javac is not recognized` | JDK `bin` is not in `PATH` or `JAVA_HOME` is incorrect. | Check `javac --version` and toolchain configuration. |
| `invalid source release` | Compiler is too old for the requested release. | Select a newer JDK that supports that release. |
| `file not found` | Incorrect source list or working directory. | Verify the root directory and paths in the argument file. |
| `illegal character: '\ufeff'` on first line | UTF-8 source has a BOM that the compiler does not strip. | Save source files as UTF-8 without BOM. |
| Path with spaces split into multiple arguments | Missing quotes in command or argument file. | Quote the full path; use an argfile. |
| Windows path loses backslashes in argfile | Backslashes are interpreted as escape characters. | Use forward slashes and quote paths. |
| `package does not exist` | Missing dependency on compile classpath or module path. | Declare the dependency in the build tool or pass `-cp`/`--module-path`. |
| `cannot find symbol` | Missing source file, dependency, or generated source. | Check source sets, compile order, and annotation processors. |
| `NoClassDefFoundError` at runtime | Runtime classpath is missing a dependency. | Add the dependency to the runtime classpath or use proper artifact packaging. |
| `class file has wrong version` | Bytecode was compiled for a newer release than the runtime. | Lower the target via `--release` and check dependencies. |
| Annotation processor does not run | Processor not explicitly declared or wrong processor path. | Configure processor path/processor in the build tool. |
| Compile passes but resources are missing | Only `javac` was invoked without a resource processing step. | Add a resource copy step or use the build tool's resource task. |
| Build uses wrong JDK | Build tool and shell use different JDKs. | Check `mvn --version`, `gradle --version`, and toolchains. |
| Build does not recompile source | Task inputs/outputs or timestamps are not updated properly. | Check source sets, generated files, and run a clean build to compare. |
| Old classes still run after changing source | Stale classes remain in the output directory. | Clean the output and rebuild. |

## 19. Complete lab: one application, multiple build approaches

Create two source files.

`src/main/java/com/example/Greeting.java`:

~~~java
package com.example;

public final class Greeting {
    private Greeting() {
    }

    public static String message(String name) {
        return "Xin chào, " + name;
    }
}
~~~

`src/main/java/com/example/Main.java`:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Build integration ready");
        System.out.println(Greeting.message("javac"));
    }
}
~~~

Compile with `javac`:

~~~bash
javac --release 17 -encoding UTF-8 -g -d build/classes \
  src/main/java/com/example/Greeting.java \
  src/main/java/com/example/Main.java
~~~

Run:

~~~bash
java -cp build/classes com.example.Main
~~~

Exact stdout:

~~~text
Build integration ready
Xin chào, javac
~~~

You can use these same two source files in Ant, Maven, or Gradle. The difference lies in how each build tool discovers sources, builds the classpath, invokes the compiler, processes resources, and packages the output.

Verified results on Windows 11 with:

| Component | Version |
|---|---|
| JDK/compiler | 24.0.2 |
| Maven | 3.9.12 |
| Maven Compiler Plugin | 3.13.0 |
| Gradle | 9.2.1 |
| Ant runtime | 1.10.15 |

The test project was placed in a directory containing spaces to verify quoting. Direct `javac` argument file, Ant `<javac fork="true"/>`, Maven `fork=true`, and Gradle `options.fork=true` all compiled successfully. All four outputs ran with the stdout above and produced class files with major version 61. Second builds in Maven and Gradle detected that the compile task did not need to re-run when sources were unchanged.

## 20. Stable build workflow in CI

A CI build can follow this sequence:

1. Select the JDK using a toolchain or pinned build image.
2. Print Java, `javac`, and build tool versions to the build log.
3. Resolve dependencies according to declared locks/versions.
4. Run a clean build when verifying from a fresh state.
5. Compile main and test sources.
6. Run tests.
7. Copy resources and package the JAR.
8. Inspect artifacts and archive build outputs.

Example:

~~~bash
# Maven
mvn -B clean verify

# Gradle Wrapper
./gradlew --no-daemon clean build
~~~

Principles for repeatable builds:

- Pin Maven/Gradle plugin versions.
- Use Maven Wrapper or Gradle Wrapper to standardize the build tool.
- Select the JDK via toolchains rather than relying on whatever JDK happens to be on `PATH`.
- Explicitly specify `--release` and encoding.
- Declare dependencies and annotation processors in the build file.
- Do not commit class outputs or temporary compiler-generated files.
- Never ignore the compiler's exit code.
- Only enable `-Werror` when the project's warning policy is stable.
- Keep build logs detailed enough to identify which compiler and options were used.

## 21. References

- [The javac Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html)
- [Java Compiler API — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.compiler/javax/tools/JavaCompiler.html)
- [Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/)
- [Gradle Java Plugin and JavaCompile](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Gradle Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [Apache Ant javac Task](https://ant.apache.org/manual/Tasks/javac.html)

Build integration ensures the compiler runs consistently alongside dependencies, resources, tests, and packaging. With scripts, manage source lists, argument files, and exit codes. With Ant, Maven, or Gradle, declare the release, encoding, toolchain, and fork mode in the build file. Inspect class outputs and run tests on the target JDK to confirm actual compatibility.
