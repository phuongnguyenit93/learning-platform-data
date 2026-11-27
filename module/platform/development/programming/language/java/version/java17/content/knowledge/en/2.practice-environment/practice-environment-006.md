# Setting Target Language and API Level with `javac --release 17`

When developing Java applications, the JDK version used to **compile** may be newer than the Java version used to **run** the application. For example, a developer's machine might have JDK 21 or newer installed while the deployment server still runs Java 17. In that case, running plain `javac` with default settings is not enough: the compiler may accept syntax and APIs that only exist in the newer JDK.

The **`javac --release 17`** option compiles source code targeting Java 17 compatibility. This lesson focuses on using that option to control language syntax, Java platform APIs, and bytecode format simultaneously.

## 1. What Does `--release 17` Actually Set?

Suppose you invoke the compiler from a sufficiently recent JDK that supports target `17`:

```bash
javac --release 17 Main.java
```

The compiler enforces three main constraints:

| Aspect | Meaning When Choosing `--release 17` |
| --- | --- |
| **Java language** | Accepts only official language features available in Java 17 or earlier; syntax from later releases is rejected. |
| **Platform APIs** | Type-checks source code against the public APIs provided for Java 17. A method added in Java 21 cannot be called as if it existed in Java 17. |
| **Bytecode** | Produces `.class` files in a Java 17-compatible format, typically **class file major version 61**. |

You can visualize the compilation flow as follows:

```text
JDK used for compilation (supporting --release 17)
                         |
                         v
                javac --release 17
                         |
          +--------------+--------------+
          |              |              |
    Java 17 syntax  Java 17 APIs   Bytecode 61
          |              |              |
          +--------------+--------------+
                         |
                         v
             Application targeting Java 17
```

Key point: `--release` is a **`javac` compiler option**. It does not switch your installed JDK into JDK 17 and does not automatically run your program on Java 17.

## 2. Preparing the Practice Environment

First, open a terminal and check which tools are being invoked:

```bash
javac -version
java -version
```

`javac` must come from a **JDK**, not a runtime-only Java installation. To compile with `--release 17`, use a `javac` version that supports target 17; typically JDK 17 or a newer JDK that still supports this target. Inspect which release targets your `javac` actually supports with:

```bash
javac --help
```

Look for the `--release` option description and the *Supported releases* list. The list depends on your compiler version, so never assume every JDK supports every older release.

`javac -version` and `java -version` can report different versions if `PATH` or JDK installations are inconsistent. Keep a close eye on this when testing programs on Java 17.

## 3. Hands-On: Compiling a Program Targeting Java 17

Create the directory structure:

```text
java17-release-demo/
└── src/
    └── com/
        └── example/
            └── Main.java
```

Contents of `src/com/example/Main.java`:

```java
package com.example;

import java.util.List;

public class Main {
    record Lesson(String title, int level) {}

    public static void main(String[] args) {
        var lessons = List.of(
                new Lesson("Getting started with --release", 17),
                new Lesson("Compatible compilation", 17)
        );

        for (var lesson : lessons) {
            System.out.println(lesson.title() + " - Java " + lesson.level());
        }
    }
}
```

The example uses `record` (standardized in Java 16), `var` (from Java 10), and `List.of` (API from Java 9). All of these are valid when targeting Java 17.

From the `java17-release-demo` root directory, create the output directory and compile:

```bash
mkdir out
javac --release 17 -encoding UTF-8 -d out src/com/example/Main.java
```

Explanation of the command components:

| Component | Effect |
| --- | --- |
| `javac` | Invokes the Java compiler. |
| `--release 17` | Selects Java 17 language level, platform APIs, and bytecode version. |
| `-encoding UTF-8` | Reads source files as UTF-8, avoiding garbled Vietnamese/non-ASCII characters on systems with another default encoding. |
| `-d out` | Places compiled `.class` files in `out`, following package directories. |
| `src/com/example/Main.java` | Source file to compile. |

After successful compilation, `out/com/example/Main.class` is created; the nested `Lesson` record also gets its own `.class` file. Run the program:

```bash
java -cp out com.example.Main
```

Expected output:

```text
Getting started with --release - Java 17
Compatible compilation - Java 17
```

`-cp out` adds the directory containing compiled classes to the classpath; `com.example.Main` is the fully qualified class name including its package. To **verify it actually runs on Java 17**, invoke the Java 17 `java` launcher for this command. Running cleanly on a newer JDK alone does not prove full compatibility with a Java 17 environment.

## 4. Inspecting the Bytecode Version

The `javap` tool can inspect metadata inside a `.class` file:

```bash
javap -verbose -classpath out com.example.Main
```

In the output, look for the line:

```text
major version: 61
```

Java 17 uses class file major version **61**. This is a technical indicator that the class file uses the Java 17 format. However, **having the right major version does not guarantee every API call will work**: you also have to consider library dependencies and the execution environment, as shown next.

## 5. Testing API Constraints: Why `--release` Is Useful

Suppose you write `src/com/example/ApiCheck.java`:

```java
package com.example;

import java.util.List;

public class ApiCheck {
    public static void main(String[] args) {
        var names = List.of("An", "Bình");
        System.out.println(names.getFirst());
    }
}
```

The **`List.getFirst()`** method was added to the platform API in **Java 21**. Because Java 17 does not have this method, the following command will fail to compile:

```bash
javac --release 17 -encoding UTF-8 -d out src/com/example/ApiCheck.java
```

The compiler typically reports an error such as `cannot find symbol` on `getFirst()`. This is a **helpful error**: the compatibility issue is caught at compile time, before deploying the application to a Java 17 environment.

You can fix it with an older API that is valid in Java 17:

```java
System.out.println(names.get(0));
```

Then rerun the compilation command with `--release 17`.

**If you only use `-source 17 -target 17` on a newer JDK:** the compiler may still see the newer JDK's own platform APIs even while emitting bytecode version 61. As a result, a call to a newer API could slip past compilation and fail at runtime on Java 17. `--release 17` closes that exact gap for Java platform APIs.

## 6. Comparing `--release`, `-source`, and `-target`

These three flags are easy to confuse because all relate to Java versions:

| Flag | Directly Controls | Limitation If Used Alone |
| --- | --- | --- |
| `--release 17` | Java 17 syntax level, platform APIs, and bytecode version. | Does not validate third-party library compatibility or runtime behavior. |
| `-source 17` | Java language syntax level. | Does not restrict platform APIs to Java 17. |
| `-target 17` | Output `.class` file format version. | Does not restrict platform APIs or replace choosing the right source level. |

When writing applications to run on Java 17, prefer this syntax:

```bash
javac --release 17 -d out src/com/example/Main.java
```

Do not combine `--release` with `-source` or `-target` in the same invocation; `javac` treats them as conflicting options. If you need to specify project library paths, you can still pass classpath or module path options as appropriate for your application layout.

## 7. What `--release 17` Does Not Guarantee

`--release 17` is an important compile-time safeguard, but it is not a complete compatibility check for the entire application.

**External libraries:** If the application depends on third-party JARs, choose library versions that support Java 17. `--release` does not downgrade the bytecode or rewrite APIs used inside those libraries. A library compiled for a newer JDK can still fail when run on Java 17.

**Runtime behavior:** The compiler does not simulate the exact runtime environment, server configuration, OS, native libraries, network connections, files, or permissions. The program should be run and tested on an actual Java 17 runtime if that is your deployment target.

**Launch configuration:** `javac --release 17` does not automatically pick which `java` executable runs the application. When multiple JDKs exist on a machine, verify the launcher path and version.

**Preview features:** Preview features that have not been finalized should not be treated as part of the standard Java 17 compatibility contract. For stable deployment on Java 17, use finalized features and compile with `--release 17` as shown above.

In multi-module projects, check each module and its dependencies too; setting `--release 17` on the source files currently being compiled does not prove every dependency runs on Java 17.

## 8. Common Errors and How to Fix Them

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| `error: release version 17 not supported` | The `javac` in use does not support target 17, usually because the JDK is too old. | Select a JDK supporting `--release 17`; check `javac -version` and `javac --help`. |
| `javac` is not recognized | JDK is not installed or its `bin` folder is missing from `PATH`. | Check JDK installation and `PATH`; reopen the terminal after editing settings. |
| `cannot find symbol` on a newer API | That API did not exist in Java 17. | Check which Java version introduced the API and use a Java 17 equivalent, e.g., `get(0)` instead of `List.getFirst()`. |
| Error for using `--release` together with `-source`/`-target` | Conflicting flags supplied together. | Keep `--release 17` and remove `-source` and `-target`. |
| `UnsupportedClassVersionError` at runtime | A program class or dependency was compiled for a newer Java than the running runtime. | Identify the offending class, fix the compilation target/dependency, and confirm by running on Java 17. |
| `ClassNotFoundException` at runtime | Missing classpath/module path or wrong class/package name. | Check `-d`, `-cp`, and the fully qualified class name; for modules, configure the proper module path. |

On Windows you can run `where.exe javac` and `where.exe java` to see executables in `PATH`; on macOS or Linux you typically run `which javac` and `which java`. Whenever you suspect the two commands point to different JDKs, check both their paths and version outputs.

## 9. Practice Exercises

1. Create and compile `Main.java` using `javac --release 17 -encoding UTF-8 -d out ...`, then run it on Java 17.
2. Use `javap -verbose` to inspect the class file major version; the expected result is `61`.
3. Try compiling `ApiCheck.java` containing `List.getFirst()` with `--release 17`. Observe the missing API error, then replace it with `List.get(0)` and recompile.
4. If your machine has a JDK newer than Java 17, compare whether `List.getFirst()` is accessible under a plain compile command versus one with `--release 17`; note why checking bytecode version alone is not enough.

When writing applications that must operate on Java 17, standardize the **compilation target** as `javac --release 17`, choose dependencies supporting Java 17, and verify on a **Java 17 runtime**. Together, these three practices reduce the risk of a program compiling on a developer's laptop only to fail in deployment.
