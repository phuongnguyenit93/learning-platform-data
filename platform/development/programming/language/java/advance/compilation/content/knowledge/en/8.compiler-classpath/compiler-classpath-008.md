# Diagnosing `cannot find symbol` and `package ... does not exist` Caused by Classpath Configuration

## 1. Two Errors That Look Like Source Code Bugs Yet May Originate from Configuration

In Java, `javac` must locate definitions of the types used by the program to perform **symbol resolution** and type checking. When a class, package, or dependency is absent from the source set and the paths the compiler searches, a syntactically valid `.java` file can still report:

~~~text
error: package com.example.lib does not exist
error: cannot find symbol
~~~

These are **compilation errors**. They differ from `ClassNotFoundException` and `NoClassDefFoundError`, which typically occur when a program **has already compiled** yet the JVM cannot load a required class at runtime.

**Principle:** identify which sources `javac` is compiling, which directories/JARs it receives on the **compile classpath**, and what package/class names exist in those artifacts. Do not rush to edit `import` statements or rename classes before verifying these conditions.

| Diagnostic | Direct meaning | Possible configuration causes |
| --- | --- | --- |
| `package p.q does not exist` | Compiler cannot find a usable package/type in a specific import | Missing dependency, wrong classpath root, wrong JAR, dependency only at runtime, module build not yet run |
| `cannot find symbol` | Compiler cannot resolve a class, variable, method, or member name at the usage site | Class missing from compile path, source omitted from build, failed import; could also be a typo or wrong API |
| `cannot access p.q.Type` | Trace of the type exists, yet compiler cannot read/locate a required dependency validly | Missing transitive dependency class, corrupted JAR, incompatible binary, wrong class version |
| `package p.q is not visible` | Under JPMS, the package may exist, yet the module does not permit reading/exporting | Wrong `module-info.java`, `requires`, `exports`, module path, or flags |
| `class file has wrong version` | Class was found, yet bytecode is newer than compiler supports | Building with a JDK older than the JDK that compiled the dependency |

**One root cause can produce multiple diagnostics.** If the `import` line cannot find `Greeter`, the subsequent `Greeter.message()` line may also report `cannot find symbol`. In this situation, fix the **first dependency/package error** and recompile; do not treat every diagnostic line as an independent bug.

## 2. What Is the Classpath, and Which Paths Does the Compiler Search?

The classpath is a list of **root directories** and **JARs/ZIPs** containing classes (and certain resources), used by the compiler or runtime depending on context. When needing a class with binary name `com.example.lib.Greeter`, a directory on the classpath must contain:

~~~text
<root>/com/example/lib/Greeter.class
~~~

If the directory is structured as follows:

~~~text
project/
  lib/
    out/
      com/
        example/
          lib/
            Greeter.class
  app/
    src/
      com/
        example/
          app/
            App.java
    out/
~~~

then the compile classpath root must be **`lib/out`**, because that is the directory from which the path `com/example/lib/Greeter.class` starts. Specifying `lib/out/com`, `lib/out/com/example`, or a `lib/src` directory with no compiled classes can cause the compiler to report that the package does not exist.

The equivalent JAR must contain the **entry**:

~~~text
com/example/lib/Greeter.class
~~~

The filename `greeter.jar` carries no package information; the internal entry layout determines which types the compiler can find.

Common `javac` options:

- `-cp <path>`, `-classpath <path>`, `--class-path <path>`: specifies the **compile classpath**.
- `-d <directory>`: destination directory for compiled class files, **does not automatically become a classpath for another invocation**.
- `-sourcepath <path>` or `--source-path <path>`: path to search for additional **Java sources**; does not replace a classpath containing compiled dependencies.
- `--module-path <path>`: module path in projects using the Java Platform Module System (JPMS); follows separate module rules, not merely a renamed classpath.
- `--release 17`: constrains language, platform API, and class file target to the chosen release; does not automatically add application dependencies.
- `-encoding UTF-8`: how source bytes are decoded; does not fix classpath issues.

When writing `-cp` with **multiple entries**, the separator depends on the OS:

| Where `javac` / `java` runs | Two-entry classpath |
| --- | --- |
| Linux, macOS (Bash/Zsh) | `lib/out:app/out` |
| Windows (PowerShell/cmd) | `lib/out;app/out` |

The `:` and `;` characters here are **classpath separators**, distinct from `/` or `\` in file paths. Quote the entire classpath value when it contains spaces or special shell characters, e.g., `-cp "lib/out;app/out"` on Windows. In PowerShell, if an argument contains `;`, quoting is especially important so the shell does not split it into separate statements.

## 3. Complete Example: Dependency Exists, Yet javac Cannot See It

The experiment has two components: library `Greeter` and application `App`. They are compiled **in two separate `javac` invocations** to clearly observe classpath-induced errors. Uses JDK 17+.

### 3.1. Source Layout

~~~text
project/
  lib/
    src/com/example/lib/Greeter.java
    out/
  app/
    src/com/example/app/App.java
    out/
~~~

File **`lib/src/com/example/lib/Greeter.java`**:

~~~java
package com.example.lib;

public final class Greeter {
    public static String message() {
        return "Hello, classpath!";
    }
}
~~~

File **`app/src/com/example/app/App.java`**:

~~~java
package com.example.app;

import com.example.lib.Greeter;

public final class App {
    public static void main(String[] args) {
        System.out.println(Greeter.message());
    }
}
~~~

The two classes can be compiled and used independently. The `package` line must match the fully qualified name imported by consumers; the `src/com/example/...` folder layout provides consistent organization that keeps builds clear. It is the package declaration, not merely directory names, that defines a class's binary name.

### 3.2. Compiling the Library

In `project/` in Bash:

~~~bash
mkdir -p lib/out app/out
javac --release 17 -encoding UTF-8 -d lib/out lib/src/com/example/lib/Greeter.java
~~~

Upon success, the compiler produces:

~~~text
lib/out/com/example/lib/Greeter.class
~~~

The command above only creates the library class. Nothing requires a subsequent `javac` invocation to know about `lib/out` automatically.

### 3.3. Intentionally Omitting Classpath to Reproduce the Error

Run:

~~~bash
javac --release 17 -encoding UTF-8 -d app/out app/src/com/example/app/App.java
~~~

Because `javac` has not been given `lib/out`, key diagnostics appear (absolute paths and formatting may vary):

~~~text
App.java:3: error: package com.example.lib does not exist
import com.example.lib.Greeter;
                      ^
App.java:7: error: cannot find symbol
        System.out.println(Greeter.message());
                           ^
  symbol:   variable Greeter
  location: class App
2 errors
~~~

This is an **expected compilation failure**. The second diagnostic does not mean `Greeter` turned into a variable in the Java source; the compiler is simply stating that the name `Greeter` at the expression position does not resolve to a valid symbol. The root cause is that class `Greeter` has not been placed into the compiler's search paths.

If `-cp lib/out` is replaced with `-cp lib/out/com`, the error **still occurs**: the classpath root is set too deep, so the relative path to `com/example/lib/Greeter.class` does not match.

### 3.4. Fixing the Compile Classpath

~~~bash
javac --release 17 -encoding UTF-8 -cp lib/out -d app/out app/src/com/example/app/App.java
~~~

Now `javac` can read `com.example.lib.Greeter` from `lib/out`. In tests on a JDK supporting `--release 17`, the command returns exit code 0 with no diagnostics.

At **runtime**, both directories are needed because the JVM must load `App.class` and `Greeter.class`:

~~~bash
java -cp "app/out:lib/out" com.example.app.App
~~~

On **Windows PowerShell/cmd**, replace `:` in the classpath value with `;`:

~~~powershell
java -cp "app/out;lib/out" com.example.app.App
~~~

Stdout in both cases:

~~~text
Hello, classpath!
~~~

This is an essential principle: **compile classpath and runtime classpath are two separate configurations**. Compiling successfully with `-cp lib/out` does not automatically ensure that running `java -cp app/out ...` lets the JVM find `Greeter`. Missing a runtime library can cause `NoClassDefFoundError: com/example/lib/Greeter`.

### 3.5. Using a JAR Instead of a Class Directory

Create the library JAR from `lib/out`:

~~~bash
jar --create --file greeter.jar -C lib/out .
jar --list --file greeter.jar
~~~

Inside the JAR, the entry `com/example/lib/Greeter.class` must exist. Then:

~~~bash
javac --release 17 -encoding UTF-8 -cp greeter.jar -d app/out app/src/com/example/app/App.java
java -cp "app/out:greeter.jar" com.example.app.App
~~~

The Windows `java` command uses `-cp "app/out;greeter.jar"`. Stdout remains `Hello, classpath!`. These directory and JAR commands have been verified with `javac --release 17`, `jar`, and `java`.

**Common mistake:** creating the JAR by packaging the `out` directory itself as a parent entry, producing `out/com/example/lib/Greeter.class` instead of `com/example/lib/Greeter.class`. If entries lack the right package path, adding that JAR to `-cp` still fails to solve the error.

## 4. Symbol Resolution Mechanism: Finding Package, Then Type and Members

In the snippet:

~~~java
import com.example.lib.Greeter;
System.out.println(Greeter.message());
~~~

The first line is an **excerpt** from `App.java`, and the second line must sit inside a method. `javac` must locate the class named `com.example.lib.Greeter` from sources being compiled, allowed source paths, classpath, or module path depending on configuration. Only afterwards does the compiler resolve the `message()` member of class `Greeter`.

If the class has not been found, the member call cannot be analyzed accurately, so both diagnostics appear together. When the class is found yet the method is missing or inaccessible, the diagnostic changes to `cannot find symbol: method message()` or a corresponding access error. At that point, **stop blindly tweaking the classpath**: inspect the API of the dependency version being used.

Other situations that also produce `cannot find symbol`:

| Unresolved symbol | What to check first |
| --- | --- |
| Class name `Greeter` | Source file, import, package, classpath/module path |
| `Greeter.message()` when class already resolved | Exact method name/casing, parameter list, `static`, library version |
| Variable name `result` | Scope, declaration, and spelling |
| Annotation name | Is the annotation artifact present on the compile path? |
| Type generated by annotation processor | Did the processor actually run, does generated-source output exist, was it included in compilation? |
| Class from Java standard library | Exact JDK and `--release`; e.g., new API absent from older release |

Thus, a `cannot find symbol` message **is not sufficient to conclude the classpath is wrong**. Inspect the `symbol:` line, `location:` line, relevant imports, and build context.

## 5. Common Configuration Causes and Fixes

### 5.1. Dependency Missing from Compile Scope

A library may be included in runtime packaging yet excluded from the **compile classpath**. Build tools use scopes/configurations to control which phase receives each dependency.

- Maven: a `provided` dependency stays on the compile classpath yet is typically not packaged as a runtime dependency; `runtime` omits the dependency from the compile classpath. For an API directly imported by source code, `compile` scope is usually more appropriate than `runtime`.
- Gradle: `implementation` is for code used within the current module, `api` (with the `java-library` plugin) is when the module's public API exposes a dependency to consumers; `runtimeOnly` does not provide the dependency for compiling source.
- IDE: check the right module dependency, version, scope, and IDE compiler settings; **no red squiggles in the IDE does not prove CI compilation shares the same classpath**.

### 5.2. Wrong Classpath Root or Confusing Source Folder with Classes Folder

A classpath used to locate compiled classes must point to the **root of the package hierarchy**. If the artifact is at `build/classes/java/main/com/example/lib/Greeter.class`, the root is `build/classes/java/main`, not `build/classes/java/main/com/example/lib`. If only `Greeter.java` source exists without bytecode yet, compile the library first or configure source path/source sets properly.

Remember that `javac -d lib/out ...` is **output**, whereas `javac -cp lib/out ...` is **input for another invocation**.

### 5.3. Missing a Java Source File in the Current Invocation

If both files belong to the same project and the compiler is invoked manually, you can pass both sources:

~~~bash
javac --release 17 -encoding UTF-8 -d out lib/src/com/example/lib/Greeter.java app/src/com/example/app/App.java
java -cp out com.example.app.App
~~~

When the compiler processes both files directly, there is no need to create `lib/out` and pass `-cp` between two invocations. Nevertheless, in multi-module projects, managing dependencies/compile order through a build tool remains cleaner.

Be careful with `-sourcepath`, working directory, and the fact that `javac` **can** discover sources automatically when the environment permits: do not rely on implicit discovery for reproducible builds. Configuring source sets and explicit classpath/source paths in build scripts is preferable.

### 5.4. Mismatched Package Name, Class Name, and Casing

Check the top of the file:

~~~java
package com.example.lib;
public final class Greeter { /* ... */ }
~~~

This is an abbreviated snippet illustrating a type declaration. Importing `com.example.libs.Greeter` (extra `s`) or `com.example.lib.greeter` (wrong casing) does not point to the same class. Java is case-sensitive; differences between Windows and Linux filesystems can cause errors to appear only in CI.

If the .class file sits in the right directory yet its actual internal binary name differs from the path used, the compiler may report `bad class file` or say the class file contains the wrong class. Check with `javap` and rebuild from the right package declaration.

### 5.5. Wrong JAR or Missing Transitive Dependency

A JAR may exist on the classpath yet **not contain the required class**, or contain that class while missing a dependency it references. Inspect the structure:

~~~bash
jar tf greeter.jar
javap -classpath greeter.jar com.example.lib.Greeter
~~~

`jar tf` lists entries; `javap` looks up a class by binary name on the classpath. If `javap` cannot find the class, verify the artifact/version/package rather than simply re-adding the same path.

If library `A` has a method returning a class from library `B`, consumer source may fail to compile if `B` is missing from the compile path, even if only importing directly from `A`. In build tools, inspect the **resolved dependency graph** and dependency exposure types, not just top-level dependencies.

### 5.6. Stale Build Outputs, Different Output Paths, or Wrong Build Order

A project may compile in the wrong order: module `app` starts before module `lib` creates its output; or one shell uses `out` while the IDE writes to `target/classes` / `build/classes/java/main`. The fix is using **one build pipeline that declares dependency relationships**, running a clean build when stale artifacts are suspected, and checking the actual compile command and new output locations.

Do not randomly copy `.class` files into directories to make errors disappear: that usually introduces duplicates and causes errors to reappear in CI.

## 6. Configuring Maven for a Dependency Between Two Modules

Suppose the library has Maven coordinates:

~~~text
groupId    = com.example
artifactId = greeter-lib
version    = 1.0.0
~~~

In the application module's POM, configure the dependency (this is a **POM snippet**, not the full file):

~~~xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>greeter-lib</artifactId>
        <version>1.0.0</version>
    </dependency>
</dependencies>
~~~

When the library module actually has those coordinates and is included in the Maven reactor or repository used by the build, Maven places the dependency onto the app's default compile classpath.

With a standard **multi-module reactor**, the parent POM must declare the corresponding modules (the folder names below are example names):

~~~xml
<modules>
    <module>lib</module>
    <module>app</module>
</modules>
~~~

These XML blocks describe the **relevant configuration snippets**; a complete POM also needs `modelVersion`, `groupId`, `artifactId`, `version`, `packaging`, and appropriate compiler settings. When using a reactor, `mvn -pl app -am compile` tells Maven to build all dependency modules in the reactor required by `app` (using the project's actual reactor module names). Enforce relationships via module dependencies rather than relying solely on the listing order inside `<modules>`.

Useful inspection commands:

~~~bash
mvn dependency:tree
mvn -X compile
~~~

Read resolved artifacts, scopes, and compiler arguments in the logs; avoid putting `greeter-lib` in `runtime` scope if `App.java` directly imports `Greeter`.

## 7. Configuring Gradle for a Dependency Between Two Modules

Example multi-module Gradle project using the **standard Java plugin layout**: `lib/src/main/java/com/example/lib/Greeter.java`, `app/src/main/java/com/example/app/App.java`.

In **`settings.gradle`** (Groovy DSL):

~~~groovy
rootProject.name = 'classpath-demo'
include 'lib', 'app'
~~~

In **`lib/build.gradle`**:

~~~groovy
plugins {
    id 'java-library'
}
~~~

In **`app/build.gradle`**:

~~~groovy
plugins {
    id 'application'
}

dependencies {
    implementation project(':lib')
}

application {
    mainClass = 'com.example.app.App'
}
~~~

These files show a minimal configuration. With Gradle configured with a compatible JDK/toolchain and sources placed under the plugin's standard paths, run:

~~~bash
./gradlew :app:run
~~~

On Windows you can run `gradlew.bat :app:run`. Gradle automatically builds module `lib`, puts its output onto the app's **compile classpath**, and configures the runtime path according to the dependency. If `implementation project(':lib')` is removed, importing `com.example.lib.Greeter` in app will fail.

A dependency declared solely as `runtimeOnly project(':lib')` will not suffice for app source to use `Greeter` directly at compile time.

To inspect the resolved classpath dependencies:

~~~bash
./gradlew :app:dependencies --configuration compileClasspath
~~~

This command inspects dependencies resolved by Gradle, not a way to fix the build automatically. With Kotlin DSL, the configuration syntax differs slightly.

## 8. Classpath, Module Path, and the Java Platform Module System

Since Java 9, projects may declare `module-info.java`. In that case Java distinguishes:

- **Classpath**: code resides in the *unnamed module* (classic model).
- **Module path**: holds named modules; the compiler checks `requires`, `exports`, and package readability.

For example, if module `com.example.app` wants to use public classes from module `com.example.lib`, it typically needs:

~~~java
module com.example.app {
    requires com.example.lib;
}
~~~

This is the content of the app's **`module-info.java`** in a JPMS project with a properly configured module path; the library also needs a module descriptor or corresponding module mechanism. If the dependency is on the module path yet the app module does not `requires` it, the error may be `package ... is not visible`, which differs from `package ... does not exist`.

Do not solve visibility errors by arbitrarily switching `--module-path` to `-cp` if the project has module descriptors and requires encapsulation. Determine whether the project is classpath-based or module-based and configure consistently.

## 9. Distinguishing Compile-Time and Runtime Classpaths

| Question | At compile time (`javac`) | At runtime (`java`) |
| --- | --- | --- |
| Where must the main class reside? | Passed source, source path, or appropriate classpath/module path | Main class/module must be loadable on the runtime path |
| Dependency used in code is missing? | `package ... does not exist`, `cannot find symbol`, `cannot access` | May be `NoClassDefFoundError`, `ClassNotFoundException`, `ServiceConfigurationError`, etc. |
| Primary option | `javac -cp ... -d ...` | `java -cp ... package.Main` |
| Does configuration carry over automatically to the other side? | No | No |

When running `java -jar app.jar`, the launcher uses the manifest `Main-Class` and dependency lookup tied to the manifest/JAR/class loader; the launcher's `-cp` argument is not applied to locate app classes as in regular `java -cp ... Main` runs while `-jar` is active. To distribute the app, bundle dependencies or declare an appropriate manifest/classpath, using a fat JAR or build-tool distribution as needed.

A runtime failure after a clean compilation is **a different problem**: inspect the runtime launch command, manifest, and actual JARs. It cannot be fixed merely by adding a dependency to `javac -cp` if the runtime still lacks it.

## 10. Ordered Diagnostic Workflow to Avoid Guessing

**Step 1 — Record the exact first diagnostic.** Capture the file path, line number, `symbol`, `location`, package, and build command. If the import fails on line 3 and the symbol fails on line 7, prioritize resolving the import's dependency.

**Step 2 — Verify fully qualified names.** Open the source being compiled to check `package`, `import`, public class name, casing, and whether the API truly exists in that library version. If the class is `com.example.lib.Greeter`, the class file path in the directory/JAR must match this name exactly.

**Step 3 — Verify that the artifact exists.** After compiling lib, `lib/out/com/example/lib/Greeter.class` or a JAR containing that entry must exist. If not, fix the library build, source inclusion, or output path first.

**Step 4 — Check the actual compile classpath.** Directory entries sit **above the package tree**; JAR entries point to the JAR file itself, not just the folder holding JARs. Use the OS-appropriate separator and quote paths. With Maven/Gradle, inspect the resolved configuration.

**Step 5 — Run a minimal compile command.** For the example:

~~~bash
javac --release 17 -encoding UTF-8 -cp lib/out -d app/out app/src/com/example/app/App.java
~~~

If it works manually yet the build tool fails, the issue lies in how the tool constructs the classpath, versions, or source sets. Do not treat a manual workaround as a sustainable CI configuration.

**Step 6 — Check whether the class has the right API.** When package/import resolves yet the method is still missing, use:

~~~bash
javap -classpath lib/out -public com.example.lib.Greeter
~~~

If `message()` is absent or has a different signature, inspect the JAR version, duplicate classes, visibility, and static/instance modifiers.

**Step 7 — Check JDK, modules, and annotation processing.** `--release` can block newer JDK APIs; JPMS can block exports/reads; generated types may be missing because an annotation processor did not run. Each case has its own fix.

**Step 8 — Perform a clean build and run with the right runtime path.** Fix the configuration in the repository, then build on a clean machine/CI. For the example:

~~~bash
java -cp "app/out:lib/out" com.example.app.App
~~~

Replace `:` with `;` on Windows. Verify stdout and artifacts instead of stopping once red underlines disappear in the IDE.

## 11. Easily Missed Classpath Pitfalls

1. **Adding `lib/out/com/example` instead of `lib/out`.** Package lookup always appends the package path relative to the classpath root.
2. **Relying only on the `CLASSPATH` environment variable.** An explicit `-cp` on the invocation sets its own search path; build tools normally override arguments, making environment variables an unreliable configuration mechanism.
3. **Forgetting `.` when setting `-cp` manually.** Once an explicit classpath is given, the current directory is not automatically included just for being the working directory; add `.` as an entry if genuinely needed, though explicit output directories are preferable.
4. **Confusing `-d` with `-cp`.** The output of a prior compile is only an input to the next compile when the path is explicitly passed.
5. **Picking up an artifact of the wrong version.** An old `Greeter.class` may lack a new method, leading to `cannot find symbol` even though the import works.
6. **Classpath contains multiple versions of the same class.** Classpath order affects which class version is found first; check duplicates and the dependency tree.
7. **Assuming wildcard `lib/*` solves everything.** Standard classpath wildcards expand JARs in one directory, do not recurse into subdirectories, and do not turn `.java` sources into compiled classes.
8. **Wrong dependency scope.** `runtimeOnly` or Maven `runtime` is insufficient for classes directly referenced by source in the compile phase.
9. **Paths with spaces.** Failing to quote `-cp` properly or having the shell split at `;` causes the compiler to receive truncated paths.
10. **Mixing module path with classpath.** May resolve imports yet introduce package visibility errors or split packages; distinguish JPMS carefully.
11. **Running `java` at project root assuming the JVM searches all nested `.class` files.** The runtime classpath also requires exact package roots.
12. **Fixing only the IDE without updating build scripts.** CI and teammates still miss the dependency; build configuration must be the source of truth.

## 12. Self-Check Scenarios

**Question 1.** File `build/classes/com/acme/Service.class` exists and source imports `com.acme.Service`. What should be added to the classpath?  
**Answer:** `build/classes`; setting `build/classes/com` is too deep and searches the wrong path.

**Question 2.** `App.java` reports `package com.example.lib does not exist`, then `cannot find symbol: Greeter`. Should you edit two separate lines of code?  
**Answer:** Not yet. Check the compile classpath first; once the dependency is present after fixing the path, both diagnostics may disappear.

**Question 3.** `javac -cp lib/out` succeeds, yet `java -cp app/out com.example.app.App` fails. Why?  
**Answer:** The runtime classpath is missing `lib/out`; use `app/out:lib/out` on Unix or `app/out;lib/out` on Windows.

**Question 4.** `Greeter` imported fine, yet the compiler reports `cannot find symbol: method message()`. What should you do?  
**Answer:** Use `javap` to inspect the actual class on the compile classpath and check signature, visibility, and version; this may be an API mismatch rather than a missing package.

**Question 5.** `jar tf greeter.jar` prints `out/com/example/lib/Greeter.class`. Is `-cp greeter.jar` sufficient?  
**Answer:** No; the entry has the wrong package root. Recreate the JAR using `jar --create --file greeter.jar -C lib/out .`.

**Question 6.** The Maven dependency for an API used in source has scope `runtime`, or Gradle has `runtimeOnly`. Does it apply to compilation?  
**Answer:** No. Switch to a scope/configuration appropriate for the compile path.

**Question 7.** The project has `module-info.java` and the library exists, yet the compiler reports `package ... is not visible`. Should you immediately add the JAR to the classpath?  
**Answer:** Check `requires`, `exports`, module path, and module boundaries first; the error is JPMS visibility, not simply a missing file.

**Question 8.** Compilation succeeds in the IDE yet CI reports the package does not exist. What evidence is most useful?  
**Answer:** The compiler invocation, resolved dependency graph, module/source sets, and actual artifacts in the CI pipeline.

## 13. Official Reference Documentation

- [javac Command — Classpath, source path, module path](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [java Command — classpath and running programs](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Maven: Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Gradle: Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)

**Core takeaway:** `package ... does not exist` usually indicates the compiler could not find the package/class to import; `cannot find symbol` indicates a name failed to resolve and has multiple possible causes. When both appear together, start from **package declaration → class file/JAR entry → classpath root → compile invocation → dependency scope/version**. Fix the build configuration for the appropriate phase and re-verify with clean compile and run commands to avoid relying on an IDE or personal machine.