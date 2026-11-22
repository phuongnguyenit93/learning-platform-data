# Identifying Class Not Found and Version Mismatch Errors

## 1. Objective: read the error accurately before fixing

A Java program can **compile successfully yet fail to start**, or run on a development machine yet fail on another machine. Two very common categories of causes are:

- **Class not found:** The Java launcher or class loader cannot find a class by the configured name and search locations; or the main class exists yet a dependent class is missing.
- **Version incompatibility:** Bytecode was compiled for a newer Java level than the running JVM can read, causing `UnsupportedClassVersionError`.

Do not rush to edit business logic. First determine: did the error occur during **`javac`**, when **`java` looked for the main class**, or when **the JVM loaded a dependent class**.

~~~mermaid
flowchart TD
    START["Java command fails"] --> PHASE{"Which command reported the error?"}
    PHASE -->|"javac"| BUILD["Check source code,<br/>compile-time dependencies"]
    PHASE -->|"java"| MSG{"Main message?"}
    MSG -->|"Could not find or load main class"| NAME["Class name, package,<br/>classpath root"]
    MSG -->|"NoClassDefFoundError"| DEP["Missing runtime dependency<br/>or class definition/initialization error"]
    MSG -->|"UnsupportedClassVersionError"| VER["Running JVM is too old<br/>for the class file"]
    MSG -->|"Main method not found"| MAIN["Check main signature"]
    NAME --> AGAIN["Fix the right cause<br/>and run again"]
    DEP --> AGAIN
    VER --> AGAIN
    MAIN --> AGAIN
~~~

Full messages can vary by JVM and environment; the diagram is an initial diagnostic guide, not a conclusion drawn from a single line of stack trace.

## 2. Three easily confused places: source, bytecode, and runtime

| Component | Example | Purpose |
|---|---|---|
| Source file | `src/demo/Hello.java` | Input to `javac` |
| Class file | `out/demo/Hello.class` | Bytecode the JVM can load |
| Fully qualified class name | `demo.Hello` | Name specified when running in class mode |
| Classpath root | `out` | Where the JVM begins looking for `demo/Hello.class` |
| Java runtime | `java` and accompanying JVM | Loads, verifies, and executes bytecode |
| Compiler | `javac` | Selects language/API/class-file level at build time |

**Rule:** with `package demo;` and `public class Hello`, after compiling to `out/demo/Hello.class`, the right way to run is **`java -cp out demo.Hello`**, not `java -cp out Hello` or `java -cp out/demo demo.Hello`.

The classpath specifies the **search root**, whereas the package is part of the **class identifier name**. `.java` and `.class` file names must not be passed instead of the class name in class mode.

## 3. Building a working example on Java 17+

Create the following structure:

~~~text
classpath-demo/
└── src/
    └── demo/
        └── Hello.java
~~~

Contents of `src/demo/Hello.java`:

~~~java
package demo;

public final class Hello {
    private Hello() {}

    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println("Hello, " + name);
    }
}
~~~

From the `classpath-demo` directory, create the output directory, compile, and then run.

**Bash (Linux/macOS):**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out src/demo/Hello.java
java -cp out demo.Hello
java -cp out demo.Hello Lan
~~~

**PowerShell (Windows):**

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out .\src\demo\Hello.java
java -cp out demo.Hello
java -cp out demo.Hello Lan
~~~

Expected output from the **two run commands**:

~~~text
Hello, Java
Hello, Lan
~~~

Generated file:

~~~text
out/
└── demo/
    └── Hello.class
~~~

`javac -d out` preserves the package structure in the output. `java -cp out demo.Hello` loads the corresponding bytecode, then invokes `main(String[] args)`.

**Intentional error test:** run `java -cp out Hello`. The launcher searches for `Hello` in the default package rather than `demo.Hello`, so it typically reports:

~~~text
Error: Could not find or load main class Hello
Caused by: java.lang.ClassNotFoundException: Hello
~~~

The fix is to **change the run command** to `java -cp out demo.Hello`. There is no need to rename the source, delete class files, or add another package.

## 4. Main class not found error: what to check?

A typical error:

~~~text
Error: Could not find or load main class demo.Hello
Caused by: java.lang.ClassNotFoundException: demo.Hello
~~~

Check in sequence:

1. **Did compilation succeed?** If `javac` reported an error, the new `.class` may not have been created; old bytecode files can remain and cause confusion.
2. **Is the class in the right place?** With name `demo.Hello` and classpath `out`, `out/demo/Hello.class` must exist.
3. **Which directory are you in?** The path `out` is relative to the current working directory.
4. **Does the class name include the full package?** `Hello` differs from `demo.Hello`; uppercase/lowercase letters in class names also matter.
5. **Does `-cp` point to the right root?** `out/demo` is not the root for class `demo.Hello`.
6. **Did you accidentally run source mode?** `java Hello.java` means something different from `java Hello` on JDKs supporting direct source execution.

Commands to inspect files and current directory:

| Bash | PowerShell |
|---|---|
| `pwd` | `Get-Location` |
| `ls out/demo/Hello.class` | `Get-Item .\out\demo\Hello.class` |
| `ls out` | `Get-ChildItem .\out` |

If both compiler and runtime locate the class yet the launcher reports missing **`main`**, that is a different error. For standard class execution on Java 17, the entry point is normally:

~~~java
public static void main(String[] args) {
    // ...
}
~~~

A class without `main` can still compile successfully; it simply cannot launch as a standalone program this way.

## 5. Distinguishing ClassNotFoundException and NoClassDefFoundError

Two similar-looking names usually indicate **different situations**:

| Error | Common meaning | When is it encountered? |
|---|---|---|
| `ClassNotFoundException` | An API loading a class **by name**, such as `Class.forName` or `ClassLoader.loadClass`, cannot find the class | Dynamic loading, reflection, or the underlying cause when the launcher cannot find the main class |
| `NoClassDefFoundError` | The JVM needs to define/complete use of a class yet lacks the required definition, or the class previously failed initialization | Missing JAR/class at runtime, classpath mismatch, or class initialization error |

Example of a class missing only **at runtime**:

- Compile `demo.App` referencing `lib.Helper` while `lib.jar` exists on the build classpath.
- At runtime, forget to include `lib.jar` on the runtime classpath.
- The JVM tries to use `lib.Helper` and may throw `NoClassDefFoundError: lib/Helper` (often with `ClassNotFoundException` in the cause chain).

**Do not try to solve every `NoClassDefFoundError` by adding a JAR.** If the stack trace mentions `Could not initialize class` or `ExceptionInInitializerError`, the class may have been found yet **earlier static initialization failed**. In that case, inspect the root error from the static initializer, not just file lookup.

`NoClassDefFoundError` belongs to `Error`, not a business exception to catch with `try/catch` and continue normally. The usual fix is proper configuration and eliminating startup initialization errors.

## 6. Class exists but wrong package name: “wrong name”

If the JVM is looking for `Hello` in the default package while the bytecode actually contains the binary name `demo.Hello`, some environments show a related error:

~~~text
java.lang.NoClassDefFoundError: Hello (wrong name: demo/Hello)
~~~

This differs from “file missing.” **The file may exist**, yet the location and class name requested by the JVM **do not match the identifier name inside the class file**.

Do not resort to renaming `Hello.class` or randomly moving it to the root directory. Confirm `package demo;` in the contents, run with `demo.Hello`, and point `-cp` to the exact root directory.

You can use the JDK tool:

~~~bash
javap -classpath out demo.Hello
~~~

If this command displays class `demo.Hello`, it is evidence that `javap` found the class beneath root `out` under that name (it does not prove `main` or all runtime dependencies are correct).

## 7. UnsupportedClassVersionError: new bytecode, old JVM

Example scenario:

- A project is **compiled for Java 17**, generating class-file major version **61**.
- You try running that class with **Java 11**, whose runtime only supports class-file major versions up to **55**.
- The JVM may report `UnsupportedClassVersionError`.

The message typically reads along the lines of:

~~~text
java.lang.UnsupportedClassVersionError: demo/Hello
has been compiled by a more recent version of the Java Runtime
(class file version 61.0);
this version of the Java Runtime only recognizes class file versions up to 55.0
~~~

Messages can vary across JVMs; the two numbers are standard examples for Java 17 and Java 11.

Common reference table:

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

**Do not confuse `javac -version` with `java -version`.** The two commands can point to different JDKs/runtimes if multiple versions are installed on the machine or PATH configuration is inconsistent.

You also cannot run a newer class-file version by **renaming files**, editing packages, or adding `-cp`. This is a bytecode/runtime format compatibility issue, not a missing path.

## 8. Diagnosing versions with real commands

**In Bash:**

~~~bash
java -version
javac -version
type -a java
type -a javac
~~~

**In PowerShell:**

~~~powershell
java -version
javac -version
Get-Command java
Get-Command javac
where.exe java
where.exe javac
~~~

These commands verify **which executables are found on PATH**. On Windows, `where.exe` differs from PowerShell's `where` alias.

To check the version of a `.class` file, with the compiled demo:

~~~bash
javap -verbose -classpath out demo.Hello
~~~

Look for lines near the top:

~~~text
Classfile .../demo/Hello.class
  ...
  major version: 61
~~~

`major version: 61` corresponds to a class file for Java 17. Paths and other details may vary by platform/JDK.

If using a JDK that supports Java 17 and needing to run on a Java 17 runtime, compile with:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/demo/Hello.java
~~~

`--release 17` simultaneously selects the language level, bytecode target, and **permitted standard APIs** corresponding to Java 17. If the compiler is too old to support the requested release, it reports an error; you need to install a suitable JDK.

## 9. Three ways to fix version errors — choose by situation

### Approach A: Upgrade the runtime

If the environment allows upgrading the JDK/runtime, select a runtime **that supports the new class files**, while testing the application, libraries, and configuration. This is usually the right approach when the project genuinely needs newer Java APIs/features.

**Do not assume** upgrading the runtime is risk-free: frameworks, JVM flags, security settings, and native dependencies may require updates.

### Approach B: Compile for an older release

If the environment requires Java 17 yet you are building with JDK 21 (and the code does not depend on Java 21 features), try:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/demo/Hello.java
~~~

The requested release level must be **supported by the `javac` version in use**. For this example, the output class file will carry major 61. Use `javap -verbose` to verify yourself.

You cannot simply change `--release` while keeping syntax or APIs exclusive to newer Java: the compiler will reject it, and you must refactor code or choose a newer runtime.

### Approach C: Align build and runtime environments

Document the required Java version in project configuration, CI, and run instructions. If building with Maven or Gradle, configure the Java toolchain and target release consistently. If deploying containers, check the **runtime base image**, not just the JDK on the development machine.

An application running on a laptop is not sufficient proof that the image/server will run it: you must run a smoke test on the **actual target runtime**.

## 10. Compile-time classpath differs from runtime classpath

Consider an application depending on a JAR library. You might compile successfully thanks to `javac`'s `-cp` flag, yet forget to include that library in `java -cp` when running.

Syntax example, assuming **`lib/helper.jar` actually exists** and contains classes needed by the application:

**Bash on Linux/macOS:**

~~~bash
javac -cp "lib/helper.jar" -d out src/demo/App.java
java -cp "out:lib/helper.jar" demo.App
~~~

**PowerShell on Windows:**

~~~powershell
javac -cp "lib/helper.jar" -d out .\src\demo\App.java
java -cp "out;lib/helper.jar" demo.App
~~~

The separator for multiple classpath entries is **`:` on Linux/macOS** and **`;` on Windows** (depending on the JVM's OS, not merely the terminal type). This is a **syntax example**, not a complete project: class `App` and `helper.jar` must be present for the commands to run.

Another error is missing **transitive** dependencies: the application has `library-a.jar`, yet library A additionally requires library B at runtime. Read **the stack trace down to the deepest cause**, inspect the dependency tree or JAR contents, instead of guessing library names from the first line.

**Note on `java -jar`:** executable JAR mode has its own entry-point and classpath rules; `-cp` specified by you is normally ignored when using `-jar`. When dependencies are missing, inspect the manifest, packaging mechanism, and build documentation of the application instead of mechanically applying `java -cp ... Main` to every JAR file.

## 11. Easily misdiagnosed cases

| Symptom | Do not immediately conclude | What to verify |
|---|---|---|
| `Could not find or load main class` | “Java code has syntax errors” | Full class name, classpath root, `.class` location |
| `ClassNotFoundException` | “Always a missing dependency JAR” | Requested class name, class loader being used |
| `NoClassDefFoundError` | “Definitely a missing file” | Is there a `Caused by`, `wrong name`, or `Could not initialize class`? |
| `UnsupportedClassVersionError` | “Fix source syntax” | Class-file major version vs. runtime `java -version` |
| `cannot find symbol` from `javac` | “Missing runtime classpath” | Source/build dependencies at compile time |
| `Main method not found` | “Class does not exist” | Was the main class found yet lacking an entry point? |
| Error appears only on server | “Server Java is broken” | JDK/JVM version, container image, PATH, working directory, packaging |
| Still prints old output after build | “JVM cached the wrong code” | Are you running an old class/JAR or a different output directory? |

**Further distinction:** `ClassNotFoundException` is a checked exception when a class-loading-by-name API fails to find a class. `NoClassDefFoundError` is a runtime class linking/definition error; a class initialization error can cause subsequent uses to report this error. Do not treat the two as synonyms.

## 12. 6-step troubleshooting workflow

1. **Copy the full error and command** that failed (including `-cp`, `-jar`, current working directory).
2. **Identify the phase**: `javac`, launcher looking up the main class, loading dependent classes, or initialization.
3. **Check versions**: `java -version`, `javac -version`, and `javap -verbose` on the relevant class if needed.
4. **Check paths**: full name, package, classpath root, `.class`/JAR files, and relative paths.
5. **Make one minimal change**: fix `-cp`, add a runtime dependency, align JDKs, or change `--release`. Do not change multiple factors at once and lose track of the cause.
6. **Re-run on the target environment**, save the working command, and add a smoke test check to deployment/CI instructions.

### Quick checklist example for the demo

~~~bash
java -version
javac -version
javap -verbose -classpath out demo.Hello
java -cp out demo.Hello
~~~

In PowerShell, these four commands have similar syntax. If `javap` cannot find `demo.Hello`, prioritize checking **the output root and class name**. If `javap` shows major 61 while the runtime is Java 11, prioritize **upgrading the runtime or rebuilding with a release supported by the runtime**.

## 13. Exercises with answers

### Exercise A — find the classpath error

You have `out/demo/Hello.class`, with internal package `demo`. Run:

~~~bash
java -cp out/demo Hello
~~~

**Answer:** wrong classpath root for class `demo.Hello`; fix to `java -cp out demo.Hello`.

### Exercise B — identify the version error

The class has `major version: 65`, and the target machine runs a Java 17 JVM. Why might it fail?

**Answer:** major 65 is Java 21, whereas Java 17 normally supports only up to major 61. `UnsupportedClassVersionError` may occur. Fix: run with a Java 21-capable runtime, or recompile for release 17 after ensuring code/API compatibility.

### Exercise C — classify missing dependency error

The build included `helper.jar`, at runtime you forgot to put the JAR on the classpath, and the application only fails when calling a specific feature.

**Answer:** this is suspected **missing class dependency at runtime**, likely reporting `NoClassDefFoundError`. Check runtime classpath and stack trace; do not just edit source or main class name.

### Exercise D — distinguish two message types

1. `java -cp out demo.Hello` reports `Could not find or load main class demo.Hello`.
2. `java -cp out demo.Hello` finds the class yet reports `Main method not found`.

**Answer:** (1) check classpath root/full name/file; (2) check the `main` signature of the found class. The two cases require two different fixes.

### Exercise E — build with newer JDK, run on older JVM

You build with JDK 21 and deploy to Java 17. List three questions to ask before fixing.

**Suggested answer:** (i) what is the current class-file major version? (ii) are the source and APIs compatible with Java 17? (iii) can the target runtime be upgraded or must `--release 17` be used? After making changes, verify with `javap` and run a smoke test on an actual Java 17 JVM.

## 14. Acceptance checklist

- [ ] Distinguish **main class not found**, **missing dependent class**, **wrong package name**, **missing main**, and **class-file version mismatch**.
- [ ] Compile and run the `demo.Hello` example using the right classpath root.
- [ ] Know that `javac` and `java` are two commands with different roles; can check both versions.
- [ ] Use `javap -verbose` to read major version and understand 52/55/61/65.
- [ ] Know that a Java 17 class (major 61) cannot run on a Java 11 JVM.
- [ ] Distinguish build classpath and runtime classpath.
- [ ] Know that `java -jar` handles classpath differently from class mode.
- [ ] Know to read `Caused by` lines and initialization errors before concluding a JAR is missing.
- [ ] Can fix one cause at a time and re-verify on the target runtime.

**Conclusion:** when encountering a Java startup error, separate three questions: **Which class name is the JVM looking for? From which classpath root is it searching? Is the bytecode compatible with the running JVM?** Answering those three questions accurately eliminates most guesswork fixes like renaming files, copying random JARs, or switching Java versions without basis.
