# What Is the Classpath and How Does the Java Compiler Find Types?

When compiling a Java file, `javac` must determine **every type** used by the program: types declared in the current file, built-in classes of the Java platform, and classes from external sources or libraries. **Classpath** is the set of locations where Java tools can find classes belonging to the classpath mechanism. For `javac`, it is an important input to the process of **name resolution, finding type declarations, and type checking**; for the `java` command, it is one of the sources for finding classes when the application runs.

Understanding the classpath helps explain why a program compiles in an IDE but fails to compile on the terminal, why adding `import` does not fix a missing library error, why the compiler can see `.class` files yet `NoClassDefFoundError` is still reported at runtime, and why changing the order of JARs can produce different results.

This lesson focuses first on Java 17+ programs **without module declarations**; the final section distinguishes the classpath from the module path in JPMS.

## 1. What Is the Classpath?

A classpath can contain multiple **classpath entries**. Common entries are:

- A root directory containing `.class` files organized by package name, such as `build/classes/java/main`.
- A `.jar` file containing `.class` files, for example `lib/utility.jar`.
- A root directory containing `.java` sources when `javac` is allowed to use the classpath to find sources (see `-sourcepath`).
- Certain special entry forms accepted by Java tools, such as the wildcard `lib/*` for JARs directly inside a directory.

For example, a class with the fully qualified name `com.example.tool.Parser` is compiled into:

```text
classes/
└── com/
    └── example/
        └── tool/
            └── Parser.class
```

The classpath entry must be **`classes`**, because the tool appends the package path `com/example/tool/Parser.class` to the *classpath root*. If you pass `classes/com/example/tool` instead of `classes`, looking up `com.example.tool.Parser` will usually fail.

Similarly, a JAR is the root containing the package path:

```text
utility.jar
└── com/
    └── example/
        └── tool/
            └── Parser.class
```

In source code, `import com.example.tool.Parser;` makes the simple name `Parser` available according to import rules. **`import` does not load JARs, does not add directories to the classpath, and does not generate missing classes**. The compiler still has to find the definition of `com.example.tool.Parser` from valid inputs.

## 2. The Classpath Is Used at Two Different Times

There are two different commands, so there are two different lookups:

| Time | Example command | What the tool needs to find | Result |
| --- | --- | --- | --- |
| **Compile time** | `javac -cp lib/example.jar -d out src/Main.java` | Declarations of types, methods, fields, superclasses, and interfaces of dependencies | Syntax/semantic checking, generates `.class` files |
| **Runtime** | `java -cp "out:lib/example.jar" Main` (macOS/Linux) | Classes needed to launch and execute the program | The JVM loads, links, and executes classes |

The classpath for the compiler **is not automatically transferred** into the classpath for the Java launcher in a subsequent run. If the compiler reads `lib/example.jar` but runtime only uses `-cp out`, the program can fail when a class in the JAR is needed.

Conversely, adding a JAR to the runtime classpath does not fix a `javac` error reporting `package ... does not exist` if that JAR is not on the search path at compile time.

Note: the entry separator syntax depends on the operating system:

- **Windows:** semicolon `;`, such as `"out;lib\example.jar"` (the `;` character itself is the separator; no backslash is needed before it).
- **macOS/Linux:** colon `:`, such as `"out:lib/example.jar"`.
- Path names containing spaces should be enclosed in double quotes appropriate for the shell.

Do not confuse `.` used as a classpath entry (the current working directory) with the dot separating packages in a class name like `com.example.Main`.

## 3. How Does `javac` Find Type Definitions?

Suppose the source contains:

```java
package demo.app;

import demo.lib.Message;

public class Main {
    public static void main(String[] args) {
        System.out.println(Message.text());
    }
}
```

When processing `demo.lib.Message`, the compiler needs to find the declaration of that type. You can visualize the processing flow for a project using the classpath as follows:

```text
Main.java (explicit input)
      |
      v
Parse syntax and record declarations
      |
      v
Reference demo.lib.Message
      |
      +--> Is the type already declared in the compilation unit?
      |
      +--> Is it a Java platform type or a type visible via modules?
      |
      +--> Is the type found on the classpath (.class, JAR)?
      |
      +--> Is the corresponding source found on the source path
             or on the classpath when no source path is configured?
      |
      v
Read definition, check accessibility and types
      |
      +--> Valid: continue compilation
      |
      +--> Not found/invalid: diagnostic
```

This is a **conceptual** diagram, not an exact list of internal calls across all `javac` versions. The compiler may defer completing types, read metadata from class files, and traverse inheritance relationships.

Key points:

1. The compiler needs *declaration information* to verify a reference, not necessarily the source for every dependency.
2. A `.class` file in a JAR can provide names, modifiers, superclasses, interfaces, fields, and methods sufficient for checking most calls; there is no need to read the library's original source.
3. The classpath is a **list of search locations**, not a Maven/Gradle-level dependency graph.
4. Having a class file is not enough if access permissions, signatures, types, or module boundaries make the reference invalid.

## 4. Java 17+ Example: Compiling a Library Then Compiling an Application

Create the files and directories below (folder names reflect the packages):

```text
classpath-lab/
├── libsrc/
│   └── demo/
│       └── lib/
│           └── Message.java
├── appsrc/
│   └── demo/
│       └── app/
│           └── Main.java
└── out/
    ├── lib/            (initially empty)
    └── app/            (initially empty)
```

Contents of `libsrc/demo/lib/Message.java`:

```java
package demo.lib;

public final class Message {
    private Message() {}

    public static String text() {
        return "classpath works";
    }
}
```

Contents of `appsrc/demo/app/Main.java`:

```java
package demo.app;

import demo.lib.Message;

public class Main {
    public static void main(String[] args) {
        System.out.println(Message.text());
    }
}
```

Run the following commands **from the `classpath-lab` directory**; before that, create `out/lib` and `out/app`. On macOS/Linux:

```bash
mkdir -p out/lib out/app
javac -encoding UTF-8 -d out/lib libsrc/demo/lib/Message.java
javac -encoding UTF-8 -cp out/lib -d out/app appsrc/demo/app/Main.java
java -cp "out/app:out/lib" demo.app.Main
```

On Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out/lib, out/app | Out-Null
javac -encoding UTF-8 -d out/lib libsrc/demo/lib/Message.java
javac -encoding UTF-8 -cp out/lib -d out/app appsrc/demo/app/Main.java
java -cp "out/app;out/lib" demo.app.Main
```

Exact stdout on both operating systems:

```text
classpath works
```

After the two `javac` commands, the key class files are located at:

```text
out/lib/demo/lib/Message.class
out/app/demo/app/Main.class
```

Breakdown of each command:

- `javac -d out/lib ...Message.java` compiles the library. `-d` selects the **output directory**, not the classpath used to find dependencies.
- `javac -cp out/lib -d out/app ...Main.java` allows the compiler to read `Message.class`. If `-cp out/lib` is omitted in an environment without another suitable search path, `javac` cannot find `demo.lib.Message`.
- `java -cp "out/app:out/lib" demo.app.Main` provides **both** the class containing `main` and the library class. On Windows, use `;`.
- Run `java` using the **binary class name** `demo.app.Main`, not `appsrc/demo/app/Main.java` or `demo/app/Main.class` in this classpath launcher mode.

Experiment: run `java -cp out/app demo.app.Main` after compiling. The JVM may load `Main`, but will fail when `demo.lib.Message` is needed because the runtime classpath does not include `out/lib`. The message is typically `NoClassDefFoundError: demo/lib/Message`; stack trace details may vary by JDK.

## 5. When a Dependency Is Packaged into a JAR

A typical JAR contains the package structure and `.class` files. From the example above, you can package the library:

```bash
jar --create --file out/message.jar -C out/lib .
```

Then the compiler can use the JAR instead of the directory:

```bash
javac -encoding UTF-8 -cp out/message.jar -d out/app appsrc/demo/app/Main.java
```

Run on macOS/Linux:

```bash
java -cp "out/app:out/message.jar" demo.app.Main
```

Run on Windows:

```powershell
java -cp "out/app;out/message.jar" demo.app.Main
```

Stdout is still:

```text
classpath works
```

`jar -C out/lib .` changes the working directory *inside the packaging operation*, so the JAR has the path `demo/lib/Message.class` at the root. If you accidentally package the `out/lib` prefix into the JAR, the compiler will not find the class under the expected package name.

You can inspect the JAR contents with:

```bash
jar --list --file out/message.jar
```

Look for `demo/lib/Message.class` in the listing. A manifest and additional entries may also appear.

For dependencies from third-party libraries, Maven/Gradle usually downloads and configures the corresponding JARs or modules. When invoking `javac` directly, the caller is responsible for providing the corresponding files on a valid search path.

## 6. `-cp`, `-classpath`, and `--class-path`

The following three syntaxes specify the user classpath for `javac`:

```bash
javac -cp out/lib -d out/app appsrc/demo/app/Main.java
javac -classpath out/lib -d out/app appsrc/demo/app/Main.java
javac --class-path out/lib -d out/app appsrc/demo/app/Main.java
```

They have the same meaning for this example. The entries are written as a single path argument, separated by `:` on Unix systems or `;` on Windows.

Example with multiple directories/JARs on macOS/Linux:

```bash
javac -cp "out/lib:lib/a.jar:lib/b.jar" -d out/app appsrc/demo/app/Main.java
```

Equivalent on Windows PowerShell:

```powershell
javac -cp "out/lib;lib/a.jar;lib/b.jar" -d out/app appsrc/demo/app/Main.java
```

Some rules to remember:

- An explicit `-cp` **replaces** the user classpath taken from the `CLASSPATH` environment variable for that command; it does not append by default.
- If `-cp` is not specified, the tool may take the user classpath from `CLASSPATH` if that variable is set; otherwise, the default is usually the current working directory `.`.
- Once `-cp` is specified, **`.` is not automatically added to the list as the user might expect**. To also include the current directory, add `.` as a separate entry.
- `-d out/app` does not automatically place `out/app` onto the user classpath for the compiler to find already-compiled classes; you must specify an appropriate source/classpath for dependent compilations.
- The classpath does not automatically download libraries from the network and does not automatically read Maven/Gradle dependency declaration files.

To avoid developer machines and CI seeing different sets of libraries, declare the classpath and toolchain explicitly in the build instead of relying on a global `CLASSPATH`.

## 7. `-sourcepath`: Where to Find Additional Sources

`-sourcepath` (or `--source-path`) is for the locations where `javac` looks for **additional `.java` source files** when a type's declaration is needed.

Run from the `classpath-lab` directory in the example:

```bash
javac -encoding UTF-8 -sourcepath libsrc -d out/implicit appsrc/demo/app/Main.java
```

Before that, you need to create an empty `out/implicit` directory. `javac` receives one explicit source `Main.java`; when it needs `demo.lib.Message`, it can find `libsrc/demo/lib/Message.java` on the source path. With the default implicit class generation behavior, the compiler can produce both:

```text
out/implicit/demo/app/Main.class
out/implicit/demo/lib/Message.class
```

In this example, calling `java -cp out/implicit demo.app.Main` will print:

```text
classpath works
```

Differences to remember:

| Option | What it contains | Main function |
| --- | --- | --- |
| `-cp` | Directories/JARs containing classes, and possibly sources when no separate source path is set | Find compiled types on the user classpath |
| `-sourcepath` | Root of source directories by package | Find additional `.java` files for compilation |
| `-d` | Output directory | Write generated `.class` files |
| `-processorpath` | Where to find annotation processors | Configure processor discovery in corresponding JDKs/modes |
| `--module-path` | Module directories/JARs | Find named modules under the JPMS system |

When compiling a classpath-based program, if **no source path is specified**, `javac` can search for sources on the user classpath. If both source and class files for the same type exist, by default the compiler usually prefers the newer file by timestamp; `-Xprefer:source` can change this choice. Therefore, overlapping a source tree and old build output on the same search path can cause results to depend on file modification times.

## 8. Implicit Compilation Is Related to the Classpath, But Not Synonymous with the Classpath

Suppose the command only lists:

```bash
javac -sourcepath libsrc -d out/implicit appsrc/demo/app/Main.java
```

`Main.java` is an **explicit source**. `Message.java` is found because `Main` needs the declaration of `Message`, so it is an **implicitly discovered dependency source**.

`javac` has options:

- `-implicit:class`: allows generating `.class` files for implicitly discovered source files.
- `-implicit:none`: does not generate `.class` files for implicitly discovered source files; the compiler **can still read them for analysis and type checking**.

For this example, if run with an empty output directory:

```bash
javac -sourcepath libsrc -implicit:none -d out/none appsrc/demo/app/Main.java
```

then typically only `out/none/demo/app/Main.class` exists. At runtime, `java -cp out/none demo.app.Main` may report missing `Message`. If **both source files are listed explicitly**, `-implicit:none` does not block compiling `Message.java`:

```bash
javac -implicit:none -d out/together libsrc/demo/lib/Message.java appsrc/demo/app/Main.java
```

You must create `out/none` and `out/together` directories before running. Experiments must separate outputs and start from empty directories so old class files do not mask the results.

This distinction explains why "the compiler found the declaration on the source path" and "the class file already exists at runtime" are two independent statements.

## 9. Entry Order and the Risk of Duplicate Classes

When the classpath has multiple locations containing the same binary class name, the search order can determine which version is found. For example:

```text
lib/old.jar  -> demo.lib.Message
lib/new.jar  -> demo.lib.Message
```

If both JARs are added to the classpath, duplicate names can shadow another version. Entry order can cause the compiler or runtime to use a different version than expected.

You should not resolve dependency conflicts simply by "swapping JARs around until the error goes away". You need to check:

1. **Which library has the duplicate class/package name**.
2. **The version** and actual method signatures used at compile time.
3. **The actual classpath** of the compiler command, test runner, and launcher.
4. **The dependency graph** generated by the build tool, including transitive dependencies.
5. Packaging techniques such as shading/relocation if the project requires them and you understand their impact.

For example, `NoSuchMethodError` at runtime can occur when compile time used a version of a class with the required method, but runtime loaded another version lacking that method/signature. This is a **binary compatibility/classpath mismatch** error, not simply a syntax error in source.

When using the wildcard `lib/*`, the set of JARs added can change depending on directory contents; the expansion order of JARs is not guaranteed. You should not rely on wildcard order to select the "right version" if duplicate classes exist.

## 10. Wildcards and JAR Directories: Understanding the Scope Correctly

Classpath syntax such as:

```bash
javac -cp "lib/*" -d out appsrc/demo/app/Main.java
```

can add JARs **directly inside** the `lib` directory to the user classpath. This differs from:

- `-cp lib`: adds the `lib` directory itself to the classpath to look for `lib/demo/pkg/Name.class`; it does not automatically unpack every JAR inside.
- `-cp "lib/*"`: adds direct JARs of `lib`; it does not recursively scan all subdirectories.
- `-cp "lib/a.jar"`: selects one exact JAR.
- `-cp "."`: looks for classes by package path from the current directory; this does not mean finding every JAR file there.

Quote `lib/*` in the shell to prevent the shell from expanding it into multiple arguments; the Java tool handles the classpath wildcard according to its own mechanism. Do not confuse the classpath wildcard with a shell glob `**/*.jar` or with listing sources `*.java`.

If you want to use both the application's class directory and all JARs in `lib`, on macOS/Linux:

```bash
java -cp "out/app:lib/*" demo.app.Main
```

Windows:

```powershell
java -cp "out/app;lib/*" demo.app.Main
```

Note: the example works when `lib/*` actually includes a JAR containing `demo.lib.Message`. In the previous hands-on section, the JAR was created at `out/message.jar`, so you must move or copy that JAR into `lib` if you want to apply this example; do not assume the file already exists there.

## 11. Where Does the Compiler Find JDK Classes?

Platform classes such as `java.lang.String`, `java.util.List`, or `java.nio.file.Path` do not require adding `rt.jar` to the classpath on Java 17+. From Java 9 onward, Java SE classes reside in **platform modules**, for example `java.base`.

`javac` knows how to find platform APIs matching the JDK/compilation configuration. For example:

```java
import java.util.List;

class Example {
    List<String> values = List.of("one", "two");
}
```

The snippet above uses `List` from `java.base`, not a JAR added by the user to `-cp`.

When compiling for another Java version, use `--release` to restrict both syntax and the set of available Java SE APIs to the selected release:

```bash
javac --release 17 -d out Example.java
```

This is different from simply running the compiler with JDK 21 and assuming Java 21 APIs will be compatible with Java 17. `--release 17` does not automatically resolve the versions of third-party libraries on the classpath: those dependencies must also be compatible with the target runtime.

## 12. Classpath and Module Path in Java 9+

Since the introduction of the Java Platform Module System (JPMS), the classpath is still supported. Classes on the regular classpath belong to the **unnamed module** of the corresponding class loader context; named modules are found and configured primarily through the **module path** and `requires`/`exports` rules.

| Concept | Classpath | Module path |
| --- | --- | --- |
| Main mechanism | Finds classes by package/binary name | Finds modules and resolves the module graph |
| Module declaration metadata | Does not require `module-info.class` | Named modules have a descriptor; JARs without a descriptor can be used as automatic modules in appropriate contexts |
| Dependency boundaries | Primarily names, class loaders, access modifiers | Adds module readability and package exports/opens |
| Common option | `-cp`/`--class-path` | `-p`/`--module-path` |
| Launching | `java -cp ... main.Class` | `java --module-path ... --module module/name` |

It is incorrect to say "adding a JAR to `-cp` always lets a named module read every class in the JAR". Named modules have their own *readability* and export constraints. For projects with `module-info.java`, check JPMS rules and how the build tool resolves dependencies.

Conversely, if you are learning with a small Java project without `module-info.java`, the classpath is the appropriate model and there is no need to switch to the module path just to use a JAR.

## 13. What About Running a JAR with `java -jar`?

`java -cp ... com.example.Main` and `java -jar app.jar` are two launch methods with different contracts:

- `java -cp "app.jar:lib/a.jar" com.example.Main` uses the classpath you provide and an explicit main class name.
- `java -jar app.jar` selects the main class from the JAR's manifest. In this mode, the user classpath from `-cp`/`CLASSPATH` is not used to select application classes; external dependencies may have to be declared via the manifest `Class-Path` or packaged differently, or an appropriate launcher must be used.

A fat/uber JAR application may package dependencies differently from a regular JAR. Not every `app.jar` is standalone runnable just because it contains `Main.class`.

When troubleshooting `ClassNotFoundException` or `NoClassDefFoundError` under `java -jar`, check the manifest, packaging approach, and launcher before adding `-cp` to no effect.

## 14. Common Classpath Errors and How to Identify Their Causes

| Symptom | Possible meaning | Check and fix |
| --- | --- | --- |
| `package demo.lib does not exist` during `javac` | Package/type definition is missing from an appropriate search path | Check built JAR/classes, compile classpath, package root |
| `cannot find symbol: class Message` | Name cannot be resolved at the usage site | Check import, package, source/classpath, and typos |
| `class file for X not found` | Information for a dependent type is missing, possibly a transitive dependency | Check indirect dependencies and JAR versions |
| `Error: Could not find or load main class demo.app.Main` | Launcher cannot find/load the main class | Check that `-cp` contains `out/app`, binary class name, and class file |
| `NoClassDefFoundError: demo/lib/Message` | A class needed at runtime is unavailable or cannot be defined/loaded | Check runtime classpath, packaging; read root cause in stack trace |
| `NoSuchMethodError` | Class at runtime lacks the expected bytecode method/signature | Check JAR version, duplicate classes, binary compatibility |
| Works in IDE, fails in terminal | IDE adds source/classpath/module path automatically | Read the actual compiler/launcher command or IDE run configuration |
| Using `-cp lib` fails to see classes inside `lib/a.jar` | Classpath directory does not unpack JARs automatically | Use `-cp lib/a.jar` or `-cp "lib/*"` |
| Source/package looks "right" but compiler still cannot find it | Wrong path root or case mismatch | Ensure `package demo.lib` matches the path under the classpath/source root |
| Builds on this machine, fails on another | Environment classpath, JDK, stale output, timestamps, different dependencies | Configure toolchain, explicit paths, clean build |

A `ClassNotFoundException` is typically thrown by class-loading APIs when a requested class name is not found; `NoClassDefFoundError` is a runtime class linking/definition error and can have causes other than "missing JAR". Always read the full cause chain rather than looking at just a single error line.

## 15. How to Debug `javac`'s Search Path

When the compiler cannot find a type, follow this procedure:

1. **Note the fully qualified name of the type.** `demo.lib.Message` differs from `Message`; check `package` and `import`.
2. **Identify the file containing the class.** Is it `out/lib/demo/lib/Message.class`, `lib/message.jar`, or `libsrc/demo/lib/Message.java`?
3. **Check the path root.** The entry must be `out/lib` or `lib/message.jar`, not the final package directory.
4. **Inspect the full compiler command.** Pay attention to `-cp`, `-sourcepath`, `--module-path`, `--release`, working directory, and Java toolchain.
5. **Check entry order/duplicate classes.** If multiple JARs contain the same binary name, find out which version the compiler selects.
6. **Check stale sources and classes.** A class file from a previous build or a newer source file can change the compiler's decision.
7. **Enable compiler logging when needed.** `javac -verbose` prints information about files parsed/loaded/written; diagnostics may vary by JDK, so do not rely on logs as fixed output.
8. **Recompile into a clean output directory.** Avoid using leftover class files as evidence that the current compilation produced the dependency.
9. **Run with an explicitly declared runtime classpath.** Do not infer the runtime classpath from the compile classpath.

Example to inspect classes in a JAR:

```bash
jar --list --file out/message.jar
```

Example to inspect bytecode, once you have the right classpath:

```bash
javap -classpath out/message.jar demo.lib.Message
```

`javap` reads declarations from class files; it does not replace the compiler and also does not prove the runtime JVM will pick the right JAR when classpaths differ.

If you suspect a class is loaded from an unexpected location, the Java launcher can print class-loading logs with `-Xlog:class+load=info` on JDKs supporting unified logging; the log volume is very large, so use it only for diagnostics and filter for the exact class name of interest.

## 16. Source Organization Errors Related to the Classpath

**Wrong directory level:** placing `demo/lib/Message.class` in `out/lib/demo/lib` and adding `out/lib/demo` to the classpath. The compiler will look for `out/lib/demo/demo/lib/Message.class` and fail. Fix the entry back to `out/lib`.

**Assuming the package is inferred from the folder:** only creating the file `src/demo/lib/Message.java` while its content declares `package other;`. The search path relies on the declared package name, not just the folder name visible in the IDE. Source path and package must be consistent with the project structure.

**Unbuilt library:** `import` is written correctly, but the `.class`/JAR does not exist. You need to compile the dependency or place the appropriate artifact on the classpath first.

**Missing transitive dependency:** a library may contain a method using another type in its signature or supertypes. The compiler needs access to sufficient metadata of related types even if the application source does not mention that type directly.

**Compile/runtime version mismatch:** compiling with a newer JDK or newer JAR, while runtime uses an older class/JVM. `UnsupportedClassVersionError` can indicate a class file requiring a newer JVM; `NoSuchMethodError` can indicate a binary dependency mismatch.

**Using relative paths in the wrong working directory:** `-cp lib/a.jar` depends on the working directory when invoking the command. CI/IDE scripts running in a different directory will point to a different or nonexistent file.

**Relying on the global classpath:** the `CLASSPATH` variable makes a command run on the author's machine, yet it may not exist in CI. Build tools should construct the classpath reproducibly and transparently.

## 17. Classpath in Maven and Gradle

Maven and Gradle provide a higher-level dependency model than `javac -cp`. They resolve artifacts, versions, transitive dependencies, source sets, and tasks; then they provide the appropriate classpath for the compiler/test runner/launcher.

Maven example (one library purely to illustrate dependency syntax):

```xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.14.0</version>
    </dependency>
</dependencies>
```

Gradle Groovy DSL example:

```groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
```

These configuration examples only illustrate how to declare dependencies, **not** parts required to run the `Message`/`Main` program above. Actual versions must be chosen per project and checked for compatibility with the JDK.

Configurations such as `implementation`, `compileOnly`, `runtimeOnly`, `testImplementation` in Gradle have different meanings. For example, a dependency present only on the compile classpath may not be present at runtime if the runtime is not configured accordingly. Maven also distinguishes scopes such as `compile`, `provided`, `runtime`, and `test`. These choices affect the output classpath of each step, not just how the IDE displays imports.

Use the build tool's mechanisms to inspect the dependency tree and task classpath instead of arbitrarily appending JARs to tasks, especially in large projects.

## 18. Self-Study Questions with Answers

**1.** `demo.lib.Message` is located at `build/classes/demo/lib/Message.class`. Which entry must be added to the classpath? **`build/classes`**, because it is the root containing the package path.

**2.** Why does `import demo.lib.Message;` not fix a missing `Message.class` error? Because `import` only assists name resolution in source; it does not generate or download libraries.

**3.** Compiling `Main.java` with `-cp out/lib` succeeds, but `java -cp out/app demo.app.Main` fails. Why? The runtime classpath lacks `out/lib`; the compiler and launcher are two independent commands.

**4.** Does `-d out/app` automatically put `out/app` onto the compile classpath? **No.** It is the output directory. When compiled classes need to be found, an appropriate classpath must be declared.

**5.** Does `-cp lib` automatically find all `lib/*.jar`? **No.** Use a specific JAR or `"lib/*"` if you want to expand direct JARs in the directory.

**6.** If `-sourcepath` is not configured, where can the compiler look for sources? For programs using the classpath, `javac` can also look for `.java` files on the user classpath.

**7.** Does `-implicit:none` prevent the compiler from reading `.java` files from the source path? **No.** It controls generating class files for implicitly discovered sources.

**8.** Why are two versions of the same class in two JARs a risk? Search order and differences between compile/runtime classpaths can make the compiler/JVM choose a different definition than expected.

**9.** Why doesn't the `java.lang.String` class need a `string.jar` in `-cp`? Because platform classes are provided via the JDK's runtime/platform modules.

**10.** When a program has `module-info.java`, is merely adding a JAR to `-cp` enough? That cannot be assumed; named modules also have module readability and package exports, so `--module-path` and descriptors must be considered.

## 19. Long-Term Principles to Remember

For the compiler to find a type, you must identify **the type's fully qualified name**, **where the type's definition is stored**, and **the corresponding search path**. A classpath entry is a package root or JAR, `-sourcepath` is for additional sources, and `-d` is for output; they do not replace one another. `javac` needs dependencies at **compile time**, while `java` needs dependencies at **runtime**. When discrepancies appear, check the exact command, directory roots, entry order, JAR versions, and clean output.

Official references:

- [`javac` JDK 21 — Configuring a Compilation / Searching for Module, Package and Type Declarations](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html).
- [`java` JDK 21 — Java Application Launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).
- [JLS `7 — Packages and Modules](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html).
- [JLS `6 — Names](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html).
