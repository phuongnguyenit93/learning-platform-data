# Explicitly Selecting Source Sets and Source Lookup Paths in Java Compilation

## 1. Why must sources be selected explicitly?

A Java project typically contains production code, tests, internal tools, generator-produced code, and external libraries. They may all contain `.java` files, yet not all of them belong to the same compilation pass. If selected wrongly, test code can leak into production, dependent source code can be missed, or stale classes left over from a previous build can be accidentally reused.

There are two independent questions:

1. **Selected source set (source files/source set):** which `.java` files must be compiled in this phase, such as `main` first and then `test`?
2. **Source lookup path (source path):** if a referenced type does not yet exist as a compiled class, under which source roots may the compiler search for the corresponding `.java` file?

A compiler also needs a path for compiled libraries (**classpath** or **module path**) and a destination for writing outputs (**output directory**). These roles must be declared separately.

~~~text
Explicitly selected .java ───────┐
                                 │
Source path: find related .java  ├── javac ──► -d: .class
Classpath: find .class / JAR ────┤
                                 │
--release, -encoding, ... ───────┘
~~~

The goal of explicit configuration is reproducing identical results from a clean checkout, running tests after main, keeping test code out of the production JAR, and not depending on how an IDE automatically marks folders.

## 2. Source root, source file, package, and output

Consider the project tree:

~~~text
project/
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── demo/
│   │   │       ├── app/Main.java
│   │   │       └── lib/Formatter.java
│   │   └── resources/
│   └── test/
│       ├── java/
│       │   └── demo/test/FormatterSmokeTest.java
│       └── resources/
├── build/generated/sources/model/java/
└── out/
    ├── main/
    └── test/
~~~

- **Source root:** `src/main/java`, `src/test/java`, or a code-generation directory. This is the root for mapping package names to file paths.
- **Source file:** `src/main/java/demo/lib/Formatter.java` is a concrete compilation unit.
- **Package:** `package demo.lib;` declares the namespace; from root `src/main/java`, the file lies at `demo/lib/Formatter.java`.
- **Output:** `out/main/demo/lib/Formatter.class` is compiled bytecode, not Java source.
- **Resources:** files in `src/main/resources` and `src/test/resources` are processed/copied by the build tool; `javac` does not automatically copy resources merely because a directory was placed on the source path.

One source root can contain multiple packages. The same package can sometimes have classes across multiple roots if the build configures it so; however, you should not declare **two definitions with the same fully qualified name** in two places, especially between hand-written source and generated source.

The path to a source root must stop **before** the package directory hierarchy. To locate `demo.lib.Formatter`, put `src/main/java` on the source path, not `src/main/java/demo/lib`.

## 3. javac options and their exact meanings

| Mechanism | Option | Effect |
| --- | --- | --- |
| Selecting files to compile | `Some.java` arguments or `@argfile` | Specifies initial compilation units |
| Finding dependent Java sources | `--source-path`, `-sourcepath` | Looks up additional source files by package when needed |
| Finding classes/JARs on classpath | `--class-path`, `-classpath`, `-cp` | Looks up compiled code and libraries |
| Setting binary output | `-d` | Writes `.class` files |
| Selecting language/platform API | `--release 17` | Restricts syntax, bytecode, and Java SE APIs by version |
| Selecting input encoding | `-encoding UTF-8` | Decodes source files |
| Module source roots | `--module-source-path` | Locates sources of multiple named modules |
| Module dependencies | `--module-path`, `-p` | Locates named modules used during compile/run |
| Output for processor-generated sources | `-s` | Writes Java sources created by annotation processors |
| Finding annotation processors | `--processor-path` | Locates annotation processing tools, separate from the application runtime classpath |

In an example without named modules, a sample command can look like:

~~~text
javac --release 17 -encoding UTF-8 --source-path src/main/java -cp lib/api.jar -d out/main src/main/java/demo/app/Main.java
~~~

This is a syntax template; `lib/api.jar` only applies if the project actually has that dependency. The runnable example in the next section requires no external JARs.

**Key note:** `--source-path src/main/java` does not instruct compiling *every* file under that directory. It only provides a location where the compiler can search for dependent source files. Conversely, if you list the full set of `.java` files directly, the compiler already has the initial compilation units and may not need to search the source path further.

If no source path is declared, `javac` can search for source files on the user classpath. Accidentally putting paths containing `.java` files onto the classpath easily creates unpredictable results; declare source roots and binary dependencies explicitly.

## 4. End-to-end runnable Java 17+ example

Create three files matching the directory tree in section 2. The example intentionally avoids JUnit so it can be verified using only the JDK.

### 4.1. `src/main/java/demo/lib/Formatter.java`

~~~java
package demo.lib;

public final class Formatter {
    private Formatter() {}

    public static String wrap(String text) {
        return "[" + text.trim() + "]";
    }
}
~~~

This is production code. The class's fully qualified name is `demo.lib.Formatter`.

### 4.2. `src/main/java/demo/app/Main.java`

~~~java
package demo.app;

import demo.lib.Formatter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Formatter.wrap(" Java "));
    }
}
~~~

`Main` imports a class from another package, so the compilation pass must find `Formatter` from the source list, source path, or compiled binary dependencies.

### 4.3. `src/test/java/demo/test/FormatterSmokeTest.java`

~~~java
package demo.test;

import demo.lib.Formatter;

public final class FormatterSmokeTest {
    public static void main(String[] args) {
        String actual = Formatter.wrap(" Java ");
        if (!"[Java]".equals(actual)) {
            throw new AssertionError("Expected [Java], got " + actual);
        }
        System.out.println("TEST OK");
    }
}
~~~

This is a **smoke test invoked via `main`**, not a JUnit test auto-discovered by a test runner. It uses `AssertionError` directly so the JVM `-ea` option is unnecessary.

### 4.4. Approach A: explicitly listing all main source files

From the `project/` directory, run in Bash (Linux/macOS/Git Bash):

~~~bash
mkdir -p out/main out/test
javac --release 17 -encoding UTF-8 -d out/main src/main/java/demo/lib/Formatter.java src/main/java/demo/app/Main.java
java -cp out/main demo.app.Main
~~~

Stdout:

~~~text
[Java]
~~~

Both `.java` files are listed explicitly. The compiler writes `out/main/demo/lib/Formatter.class` and `out/main/demo/app/Main.class`. Because all required source files were supplied, this case does not need `--source-path`.

This is the clearest model for observing the **selected source set**. In large projects, the build tool collects all source files of a source set instead of requiring users to type thousands of paths.

### 4.5. Approach B: listing only Main.java, specifying where to look up dependent sources

Use a different output directory to observe separately:

~~~bash
mkdir -p out/by-sourcepath
javac --release 17 -encoding UTF-8 --source-path src/main/java -d out/by-sourcepath src/main/java/demo/app/Main.java
java -cp out/by-sourcepath demo.app.Main
~~~

Stdout:

~~~text
[Java]
~~~

The source file list contains only `Main.java`. Seeing `Main` use `demo.lib.Formatter`, the compiler can find `src/main/java/demo/lib/Formatter.java` from the source path and compile that file implicitly. Thus the output still contains the classes needed to run the program.

**Do not infer that every file in `src/main/java` was compiled.** If you add an `Unused.java` referenced by no class, compiling only `Main.java` with a source path does not force the compiler to discover and compile `Unused.java`. For a complete production build, the full set of input sources must be selected, or let the build tool handle that task.

If a source exists both as `.java` and as `.class` where the compiler searches, selection can also depend on timestamps and compiler options. Do not rely on stale classes to make a build “pass”; test against clean output.

### 4.6. Compiling tests against compiled main classes

Continuing with `out/main` from Approach A:

~~~bash
javac --release 17 -encoding UTF-8 -cp out/main -d out/test src/test/java/demo/test/FormatterSmokeTest.java
java -cp out/main:out/test demo.test.FormatterSmokeTest
~~~

Stdout:

~~~text
TEST OK
~~~

The test compilation takes **test sources** as input; `-cp out/main` points to the compiled production classes. `out/test` contains only test classes. When running tests, the runtime classpath must include both main and test outputs.

On Windows, the path list separator is `;` instead of `:`. PowerShell example:

~~~powershell
java -cp 'out/main;out/test' demo.test.FormatterSmokeTest
~~~

In PowerShell, wrap the `-cp` argument containing a semicolon in quotes so the shell does not treat it as a statement terminator. You can use `New-Item -ItemType Directory -Force out/main, out/test` to create directories instead of Bash's `mkdir -p`.

## 5. When to compile the full source set vs. when to use source lookup?

Distinguish two goals:

**Building an entire library/application:** every Java file belonging to the source set must be processed, including classes that have no callers within the same build. Using `--source-path` to compile only a single entry point is insufficient to prove all source files are valid.

**Compiling a small program or a single file under test:** you can pass specific files and `--source-path` so the compiler locates dependent sources. The result matches that narrower goal.

On the command line, you can store the source list in an **argument file** when there are too many filenames. For example, a text file `main-sources.args` containing:

~~~text
src/main/java/demo/lib/Formatter.java
src/main/java/demo/app/Main.java
~~~

Then run:

~~~bash
javac --release 17 -encoding UTF-8 -d out/main @main-sources.args
~~~

An `@argfile` holds arguments for the compiler and can be generated by a script/build generator from a controlled list of source files. Do not let the list file include test files, or contain paths relying on an unexpected working directory. Argument files have their own quoting/escaping rules when paths contain spaces; in large projects let the build tool handle it.

Additionally, `javac -implicit:none` only controls **writing class files for implicitly discovered sources**. It does not turn `--source-path` into a mechanism to “forbid reading other sources”, and does not replace selecting the full set of input sources.

## 6. Multiple source roots: hand-written code and generated code

A main source set can have multiple source roots:

~~~text
src/main/java/                              # hand-written code
build/generated/sources/models/java/        # generator-created code for main
src/test/java/                              # test code, does not belong to main
build/generated/sources/test-fixtures/java/ # generated code for test
~~~

If a main class depends on a class generated under `build/generated/sources/models/java`, multiple source roots can be declared. Bash command example:

~~~bash
javac --release 17 --source-path 'src/main/java:build/generated/sources/models/java' -d out/main src/main/java/demo/app/Main.java
~~~

This is a **general configuration example**: in section 4's sample program, `Main` does not depend on generated sources so that directory is unnecessary. In real projects, ensure the generator has already run and created the files properly before compilation.

Selection principles:

1. Add only generated code meant for **main** to main source roots; generated code meant for tests belongs to test source roots.
2. Never declare the test directory as a production source path to work around import errors; fix the dependency design if main is importing test code.
3. If a generator emits the same fully qualified class that main source already defines, duplicate-class errors or wrong source selection can occur; assign a single clear owner.
4. Do not let generators write into `src/main/java` without an explicit policy for managing generated sources in Git. Separate build outputs are easier to clean and regenerate.
5. A source root specifies **where to read from**, not **when to generate code**. The build tool must manage task dependencies from the generator to the compiler.

If there is a JAR, put it on the classpath, not the source path. `--source-path` is for source code; `-cp` is for classes/JARs referenced by the compiler.

## 7. Distinguishing source path, compile classpath, and runtime classpath

| Phase | Selected Source Set | Where to Look Up Dependencies | Where to Write / Execute |
| --- | --- | --- | --- |
| Compile main | Main Java files | Main source roots when needed; compile libraries on classpath | Output `out/main` |
| Compile test | Test Java files | Compiled main, test libraries, and test source roots when needed | Output `out/test` |
| Run main | No source compilation (under normal class mode) | Main runtime classpath and runtime dependencies | `java -cp out/main demo.app.Main` |
| Run test | Compiled test classes | Main + test classes and test runtime libraries | `java -cp out/main:out/test ...` |

Several easy-to-confuse mistakes:

- `javac -cp out/main -d out/test src/test/java/demo/test/FormatterSmokeTest.java` is right when main has already been compiled.
- `javac -d out/test src/test/java/demo/test/FormatterSmokeTest.java` on a clean classpath can fail because `demo.lib.Formatter` is not found.
- `java -cp src/main/java demo.app.Main` will not find classes written in `out/main`; Java runtime's `-cp` points to class directories/JARs, not source roots.
- Using `src/test/java` as a source root of `main` can allow test classes or test dependencies to leak into production builds.
- Running `javac -d out/main ...` without separating test output makes it hard to tell which classes belong to the production artifact.

When classes are missing at runtime even though compilation succeeded, inspect the **runtime** classpath or module path; adding a source path to the `java` command does not solve compiled class lookup.

## 8. Selecting source sets in Gradle

Gradle's `java` plugin provides two default source sets: `main` and `test`. By default they use `src/main/java`, `src/main/resources`, `src/test/java`, and `src/test/resources`. They can be declared explicitly in `build.gradle` (Groovy DSL):

~~~groovy
plugins {
    id 'java'
}

sourceSets {
    main {
        java {
            setSrcDirs(['src/main/java'])
        }
        resources {
            setSrcDirs(['src/main/resources'])
        }
    }
    test {
        java {
            setSrcDirs(['src/test/java'])
        }
        resources {
            setSrcDirs(['src/test/resources'])
        }
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}
~~~

`setSrcDirs` **resets** the list of roots for each source set; it is useful when removing unwanted roots. To **add** a root, use `srcDir(...)` or `srcDirs(...)` appropriately instead of accidentally replacing the existing list. With standard default structure, writing `sourceSets` is optional; the example simply makes intent explicit.

Related Gradle tasks:

- `compileJava` compiles selected main files and writes main classes.
- `compileTestJava` compiles test files using main output and test dependencies on the appropriate compile classpath.
- `processResources` and `processTestResources` process resources separately.
- `test` runs tests configured by the framework/runner; the smoke test with a `main` method in section 4 is not automatically detected as a JUnit test.

When the repository includes the Gradle Wrapper, use:

~~~bash
./gradlew compileJava
./gradlew compileTestJava
~~~

On Windows run `gradlew.bat` instead of `./gradlew`.

For generated sources, proper configuration connects the **source-generating task** to the source set. If a `generateModels` task is defined with a valid output directory, an illustrative configuration looks like:

~~~groovy
sourceSets {
    main {
        java.srcDir(tasks.named('generateModels'))
    }
}
~~~

This snippet **cannot run standalone** without defining the `generateModels` task first. The meaning is using the producer task's output as a source directory, enabling Gradle to infer task dependencies; avoid merely hardcoding a `build/generated/...` path and hoping the code-generation task already ran. If generated code serves tests only, attach it to `sourceSets.test`.

If adding another source set like integration tests, configure separate sources, output, dependency classpath, runtime classpath, and execution task; do not merge integration tests into the production source set for convenience.

## 9. Equivalent conventions in Maven

Maven uses corresponding default roots: `src/main/java` and `src/test/java`, resources in `src/main/resources` and `src/test/resources`, and class outputs typically in `target/classes` and `target/test-classes`.

When roots must be changed, `pom.xml` can specify:

~~~xml
<build>
    <sourceDirectory>src/main/java</sourceDirectory>
    <testSourceDirectory>src/test/java</testSourceDirectory>
</build>
~~~

This is a fragment **inside** the POM's `project` element, not a standalone POM. Both values above are defaults and normally do not need declaration.

Generated code in Maven should be bound by plugins/lifecycle to the proper phase (`generate-sources` or `generate-test-sources` as appropriate), while registering the generated source root for main compile or test-compile accordingly. Editing paths only in the IDE does not inform Maven builds that a generator created sources. Test-only dependencies need the appropriate `test` scope.

## 10. Source path of named modules (JPMS) is a different case

When multiple Java modules declare `module-info.java`, `--module-source-path` replaces multi-module source lookup, while `--module-path` locates **compiled/packaged module dependencies**. `-m` or `--module` selects the module to compile.

**Independent** example from section 4:

~~~text
modulesrc/
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

File `modulesrc/com.example.app/module-info.java`:

~~~java
module com.example.app {
}
~~~

File `modulesrc/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println("MODULE OK");
    }
}
~~~

Compile and run:

~~~bash
mkdir -p out/modules
javac --release 17 --module-source-path modulesrc -d out/modules -m com.example.app
java --module-path out/modules -m com.example.app/com.example.app.Main
~~~

Stdout:

~~~text
MODULE OK
~~~

In this layout, `modulesrc` contains subdirectories named after modules, differing from the single source root approach of classpath projects. Do not blindly replace `--module-source-path` with `--source-path`, and do not confuse `--module-path` with a directory containing `.java` files.

## 11. Verifying actual source lookup paths and common errors

The `javac -verbose` command can print details about source files the compiler reads, loaded classes/JARs, and outputs. Example:

~~~bash
javac -verbose --release 17 -encoding UTF-8 --source-path src/main/java -d out/by-sourcepath src/main/java/demo/app/Main.java
~~~

`-verbose` logs vary by JDK version, OS, and project; do not treat the log as a fixed stdout string to match. Look at the **source paths read** to spot whether the compiler is reading files from the wrong root.

| Symptom | Possible Cause | How to Handle |
| --- | --- | --- |
| `cannot find symbol Formatter` | Missing `Formatter.java` in selected sources, source path, or classpath | Check imports, package names, source roots, and binary dependencies |
| A standalone file does not emit `.class` | File is neither in the explicit source list nor referenced | Add the file to the build task's source set |
| File exists on disk yet compiler fails to resolve package | Source path goes too deep into the package tree | Point `--source-path` to the directory above the package tree |
| Test compile cannot see main classes | Missing main output on test compile classpath | Compile main first, add main output to test classpath |
| Main compile demands JUnit | Test sources or test dependencies leaked into main | Separate source sets and dependency scopes |
| IDE works yet CI fails | IDE previously marked generated roots or used stale classes | Run a clean command-line build, declare generator dependencies |
| Duplicate class exists | Same fully qualified name from main/generated code/JAR | Choose one owning source and remove duplicates |
| Running app throws `ClassNotFoundException` | Runtime classpath points to wrong output | Verify fully qualified main class and class/JAR directories |
| Windows fails while Unix passes | Using `:` instead of `;` in path lists | Use the OS-appropriate separator, quote paths |
| Java module not found | Confusing module source path with module path | Check module layout and `--module-source-path`/`--module-path` options |

A reliable build must answer: which files belong to main, which belong to test, which roots the compiler may search for additional sources, which binary dependencies exist, whether generators run before or after, and where `.class` files are written. Verify after `clean` or against fresh output so stale files do not mask missing configuration.

## 12. Self-verification exercises

1. Compile both main files from the **explicit list** in section 4.4 and run `demo.app.Main`; verify stdout is `[Java]`.
2. Use the **source path** approach in section 4.5, naming only `Main.java`; verify the compiler still finds `Formatter`.
3. Create an independent `src/main/java/demo/lib/Unused.java` imported by no class, such as `package demo.lib; public class Unused {}`. Compile only `Main.java` with a source path; observe `Unused.class` does not appear merely by sitting under the root. Add `Unused.java` to the explicit sources list so it gets compiled.
4. Compile tests per section 4.6, then try omitting `-cp out/main` on a clean classpath to observe the dependency error. Restore the classpath and verify `TEST OK`.
5. If using Gradle, inspect `main` and `test` source roots; run a clean build via the wrapper and ensure only main classes/resources enter the production artifact.

After these steps, the distinctions among **files requested for compilation**, **directories allowed for source lookup**, **classpath of compiled classes**, and **output write destination** will be clear through observed results.