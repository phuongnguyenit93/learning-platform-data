# Using `javac -d` to Organize the Output Directory

When compiling a Java program, you usually want to keep `.java` source code separate from `.class` bytecode. The **`-d` (destination directory)** option of `javac` solves this: it chooses the **root directory holding the generated class files** and places each class file into a directory tree matching its **package name** (and module name if compiling multiple modules).

A good habit is to write code in `src/`, send bytecode to `build/classes/` or `out/`, and when running specify **the exact bytecode root directory**. This lesson focuses on how `-d` organizes files, how to compile/run, and common path-related mistakes.

## 1. Exact Syntax and Meaning

```text
javac -d <destination-dir> <java-file-list>
```

Example:

```sh
javac --release 17 -encoding UTF-8 -d out src/demo/Main.java
```

Meaning of each part:

- `javac`: the Java compiler in the JDK.
- `--release 17`: uses the language, class-file target, and platform APIs corresponding to Java 17 (when the active JDK supports this target).
- `-encoding UTF-8`: reads source code using UTF-8.
- **`-d out`**: sets the **output root** at directory `out`, resolved relative to the current working directory.
- `src/demo/Main.java`: source file being compiled; `-d` **does not replace** passing sources to `javac`.

With JDK 17 and later according to current `javac` documentation, `javac` can create the destination directory and missing package directories. Very old JDK guides may require pre-creating the root directory; if writing scripts that need to support multiple JDK versions, pre-creating the destination is a clear and reliable practice.

`-d` only specifies **where to write class files**. It does not rename packages, run `main`, package JARs, download libraries, or delete old files upon recompilation.

### When `-d` Is Omitted

With traditional source compilation (not compiling multiple modules), `javac` by default places class files **next to the source file**. For instance, if the source file is `src/demo/Main.java`, `javac src/demo/Main.java` typically generates `src/demo/Main.class`. This easily mixes both source and build output in the `src/` tree.

| Invocation | Output Location of Class File for `package demo; class Main` |
| --- | --- |
| `javac src/demo/Main.java` | `src/demo/Main.class` |
| `javac -d out src/demo/Main.java` | `out/demo/Main.class` |
| `javac -d build/classes src/demo/Main.java` | `build/classes/demo/Main.class` |

The paths in the table assume the source is a valid file and compilation succeeds. Forward slashes `/` show directory structure in a general readable way; Windows uses backslashes `\` when displaying system paths.

## 2. Key Rule: Directories Follow the Package, Not the `.java` Location

Suppose the source code declares:

```java
package com.acme.tools;

public class Greeter {
}
```

If that `Greeter.java` file is compiled with `-d build/classes`, the corresponding output path is:

```text
build/
└── classes/
    └── com/
        └── acme/
            └── tools/
                └── Greeter.class
```

Formula for a typical top-level type:

```text
<class-output-root>/<package-dots-as-directories>/<ClassName>.class
```

Therefore:

- **`-d build/classes` chooses the root**, which does not mean all `.class` files are placed flat right inside this directory.
- **`package com.acme.tools;` creates the `com/acme/tools/` branch**. `javac` relies on the type's package declaration, not on the `src` directory name or source file path, to determine the package.
- If a class **declares no package** (unnamed/default package), the class file is placed directly under the output root, for example `build/classes/Plain.class`.
- One source file can produce **multiple** class files: secondary top-level classes, nested classes, anonymous classes, or other language constructs can generate additional files. You should not enforce a rule of "one `.class` per `.java`".

In real projects, organize sources by package so they are easy to find, such as `src/com/acme/tools/Greeter.java`. That is a helpful source-organization convention; **`-d` controls the output**, not a tool for fixing source structure.

## 3. Complete Java 17 Example: Source in `src/`, Bytecode in `build/classes/`

Create a project with **two separate packages**:

```text
project/
└── src/
    └── com/
        └── example/
            ├── util/
            │   └── Greeting.java
            └── app/
                └── Main.java
```

Contents of `src/com/example/util/Greeting.java`:

```java
package com.example.util;

public final class Greeting {
    private Greeting() {
    }

    public static String message() {
        return "Hello from -d";
    }
}
```

Contents of `src/com/example/app/Main.java`:

```java
package com.example.app;

import com.example.util.Greeting;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
```

From the `project` directory, use JDK 17+ and compile both files in a single invocation:

```sh
javac --release 17 -encoding UTF-8 -d build/classes src/com/example/util/Greeting.java src/com/example/app/Main.java
```

If successful, the `javac` command normally prints nothing to the terminal. Output tree:

```text
project/
├── src/
│   └── com/
│       └── example/
│           ├── util/Greeting.java
│           └── app/Main.java
└── build/
    └── classes/
        └── com/
            └── example/
                ├── util/Greeting.class
                └── app/Main.class
```

When running, use the **output root `build/classes`** as the runtime classpath and the fully qualified main class name:

```sh
java -cp build/classes com.example.app.Main
```

**Exact stdout:**

```text
Hello from -d
```

Why does the command run properly?

1. `-d build/classes` instructs the compiler to place class files under the `build/classes` directory.
2. `package com.example.app;` makes the full name `com.example.app.Main`; the class file sits at `build/classes/com/example/app/Main.class`.
3. `java -cp build/classes ...` puts the **directory containing the root of the package tree** on the classpath; the JVM maps the name `com.example.app.Main` to the file along the corresponding path.
4. `Greeting` is in another package, yet it also sits under **the same output root**, so the runtime finds it through that classpath.

A commonly seen **wrong** command:

```sh
java -cp build/classes/com/example/app Main
```

In the example above, `Main` **does not belong to the default package**. Specifying a directory too deep and calling it by the short name `Main` will not match the compiled class name. The correct command is `java -cp build/classes com.example.app.Main`.

> **Note:** `-d` can accept a relative path like `out` or an absolute path. Relative paths are resolved from the **current working directory of the `javac` process**; running the command from another directory can put output elsewhere. If a path contains spaces, quote it according to your shell, e.g., `-d "build/java classes"`.

## 4. Relationship Between `-d`, `-cp`, and `-sourcepath`

Three easily confused options have different responsibilities:

| Option | Function | Example |
| --- | --- | --- |
| `-d` | Specifies **where to write** class files from the compilation | `-d build/classes` |
| `-cp` / `--class-path` | Specifies **where to look for** classes/libraries for compilation; `java -cp` sets the runtime classpath | `-cp build/classes` |
| `-sourcepath` / `--source-path` | Specifies the path to look for **dependent source code** so the compiler can compile it when needed | `-sourcepath src` |

They are not equivalent. Specifically, in a Java project **not compiled as a named module**, the `-d` directory **is not automatically added to `javac`'s own classpath**. Therefore, when you split compilation into multiple passes, you must explicitly tell the compiler how to find already-generated `.class` files.

### Two-Pass Compilation Example Reusing Prior Output

Using **the exact same two files `Greeting.java` and `Main.java` from section 3**, you can execute:

```sh
javac --release 17 -encoding UTF-8 -d build/classes src/com/example/util/Greeting.java
javac --release 17 -encoding UTF-8 -cp build/classes -d build/classes src/com/example/app/Main.java
java -cp build/classes com.example.app.Main
```

Stdout of the last command:

```text
Hello from -d
```

The first pass generates `Greeting.class`. The second pass **reads `Greeting.class` from `-cp build/classes`** and writes `Main.class` to the same directory via `-d build/classes`. If you omit `-cp build/classes`, the second pass may encounter errors like `package com.example.util does not exist` or `cannot find symbol`, depending on source layout, classpath, and other settings.

When using external JAR libraries, add them to the **compile classpath** and ensure the **runtime classpath** also includes the required dependencies. If multiple classpath entries are needed, the separator is `;` on Windows and `:` on Linux/macOS. To reduce errors while learning `-d`, the main example does not use external libraries.

### `-d` Does Not Determine a Class's Namespace

Run:

```sh
javap -classpath build/classes com.example.app.Main
```

`javap` reads bytecode on the classpath and helps inspect a compiled class. `Main`'s package information is still `com.example.app`, because that is the declaration in source code. Changing `-d build/classes` to `-d out` only changes **the output storage location**; it does not change the class's fully qualified name.

## 5. Why Use a Separate Output Directory?

**Clear separation of concerns:** `src/` contains source code edited by humans; `build/classes/` only contains bytecode generated by compilation. You can spot generated files, inspect logs, and package more cleanly.

**Stable execution path:** use a clear classpath root, such as `java -cp build/classes com.example.app.Main`, instead of guessing individual directories containing `.class` files.

**Easy JAR packaging:** after successfully compiling the example in section 3, you can package all class files under the output root:

```sh
jar --create --file build/app.jar -C build/classes .
java -cp build/app.jar com.example.app.Main
```

Stdout of the run command is still:

```text
Hello from -d
```

Here, `jar -C build/classes .` puts the contents **inside** the `build/classes` tree at the JAR root, so the JAR has entries `com/example/app/Main.class` and `com/example/util/Greeting.class`. The `jar` command is a **separate packaging step**, not an effect of `javac -d`. The example does not write `Main-Class` into the manifest, so it runs via `java -cp build/app.jar ...`; do not assume `java -jar build/app.jar` will work.

**Verifiable output:** use your OS file-listing command, `jar --list --file build/app.jar` to inspect a JAR, or `javap -classpath build/classes com.example.app.Main` to inspect a class. This verifies the actual output location instead of guessing from a terminal that prints no errors.

**Easy handoff to build tools:** Maven and Gradle typically manage class output directories, generated sources, resources, and packaged artifacts separately. `-d` is the corresponding concept at the `javac` command level, even though exact directory names are decided by the build tool.

## 6. Output Cases You Need to Know

### 6.1. Class Without a `package`

File `src/Plain.java`:

```java
public class Plain {
    public static void main(String[] args) {
        System.out.println("Plain class");
    }
}
```

Compile and run:

```sh
javac --release 17 -d out src/Plain.java
java -cp out Plain
```

The class output is `out/Plain.class`, and stdout is:

```text
Plain class
```

Because the class declares no package, there is no `out/src/` or `out/Plain/` branch. This is a simple case to test whether you are passing the **right class name** to `java`. In large applications, explicit packages are usually easier to manage than the default package.

### 6.2. Nested Classes Produce Multiple `.class` Files

Given a file like:

```java
package sample;

public class Container {
    public static class Nested {
    }
}
```

If `Container.java` is compiled with `-d out`, typical class files are:

```text
out/
└── sample/
    ├── Container.class
    └── Container$Nested.class
```

The `$` character is part of the binary file name for the nested type in this example. `-d` still only selects the `out` root; the compiler determines the number and names of class files corresponding to types in the source. Examples with lambdas, local/anonymous classes, or other constructs may produce auxiliary files in ways you should not hard-code assumptions about.

### 6.3. Compiling Named Modules

When compiling multiple **named modules** in a single invocation with an appropriate module source path configuration, the `-d` directory may be organized with an extra **module name** level before the package tree:

```text
out/
├── com.example.alpha/
│   ├── module-info.class
│   └── com/example/alpha/...
└── com.example.beta/
    ├── module-info.class
    └── com/example/beta/...
```

This is an **illustrative structure diagram** for multi-module output, not the result of the earlier classpath example commands. Do not impose the multi-module tree onto every `javac -d` command; for regular Java lessons without `module-info.java`, you will see a package tree as in sections 2–3.

When **compiling modules**, `javac` looks up class files in the class output differently from non-modular mode; therefore, the note in section 4 that `-d` is not automatically added to the classpath applies to traditional classpath mode.

### 6.4. Generated Sources, Native Headers, and Resources

- `-d <dir>`: directory holding **class files**.
- `-s <dir>`: directory holding **source files generated by annotation processors** when a processor generates sources.
- `-h <dir>`: destination for **native headers** generated in applicable cases.
- Configuration files, images, `.properties`, and other resources are typically handled by a **separate resource-copying step**; `javac -d` does not copy the entire contents of `src/` to the output by default.

Therefore, “having run `javac -d build/classes`” does not mean “having created a ready-to-run application with all resources and JARs in every environment”.

## 7. Common Errors and How to Find the Root Cause

| Situation | Why It Happens | How to Fix |
| --- | --- | --- |
| No `.class` found directly inside `out/` | The class has a `package`, so it resides in `out/<package-path>/` | Check the `package` declaration, open the matching directory branch |
| `Could not find or load main class` | Wrong classpath root or wrong fully qualified class name | `java -cp build/classes com.example.app.Main` in the example |
| Second compilation pass reports missing `Greeting` | `-d` does not automatically add output to non-modular compile classpath | Pass `-cp build/classes` on the second pass |
| `.class` files sit next to `.java` | `-d` was not passed | Use `-d out` or `-d build/classes` |
| Output appears in an unexpected location | The `-d` path is relative and the working directory changed | Check the current directory, use an explicit path |
| Compilation reports unable to write file | Wrong permissions, destination path is a regular file, invalid path, or system restriction | Check the path, write permissions, and original error message |
| Passed `-d` and expected a JAR | `-d` only outputs class files | Run `jar` or the build tool's packaging task |
| Ran before, new build still uses old class | Output directory contains stale files; new compilation does not clean automatically | Check classpath, exit code, and clean/build workflow |
| Class file exists, yet running fails due to missing resource | Resources are not copied by `javac` via `-d` | Configure a resource-copying step, ensure resources sit on the proper runtime classpath |

### Why Can Stale Output Cause Misunderstandings?

Suppose yesterday `build/classes/com/example/app/Main.class` already existed, but today you edited the code with a syntax error and ran `javac`, which failed. Yesterday's `Main.class` file **may still remain intact**. Running `java -cp build/classes com.example.app.Main` may still execute the old bytecode. Therefore:

1. Check `javac`'s exit code.
2. Compile into an explicitly managed output; in CI/builds you can use a clean directory for verification.
3. Do not conclude “the current code is valid” just because `java` runs.
4. When renaming packages/classes, check for old `.class` files that may remain in the output tree and need to be removed by a clean process.

**Data preservation note:** cleaning is destructive; only delete build output directories actually owned by the project, and do not apply delete commands indiscriminately to directories containing source code or documentation.

## 8. Choosing Output Paths in Practice

Names such as `out/`, `classes/`, `build/classes/`, and `target/classes/` are only **conventions**. `javac` does not require a special name; what matters is that within a build process you maintain **the same bytecode root** across compiling, running, testing, and packaging.

A sample structure for a small project:

```text
project/
├── src/
│   └── com/example/app/Main.java
├── resources/
│   └── application.properties
└── build/
    ├── classes/
    │   └── com/example/app/Main.class
    └── app.jar
```

This is an illustrative structure. `javac -d build/classes` is only responsible for **class files**; getting `application.properties` onto the runtime classpath requires a separate resource-copying step; getting `app.jar` requires a separate packaging step. Do not invent phantom steps that the `javac` command does not actually perform.

For multi-source projects, do not write a separate `javac` command for each file hoping dependencies are resolved in order. You can list all sources for the compilation pass, use an argument file for long lists, or let Maven/Gradle configure source sets, dependencies, and outputs. In all cases, understand the **output path** the compiler actually uses.

## 9. Quick Checks Before Concluding `-d` Is Right

1. **Does the compile command include `-d`?** Which directory does it point to, relative to which working directory?
2. **Which `package` does the source have?** Derive the exact `<output-root>/<package-path>/` branch.
3. **Which classes are generated?** Are there inner classes, multiple top-level types, or additional sources compiled by the compiler?
4. **Did the compilation succeed?** Check errors, important warnings, and the exit code instead of merely checking whether files exist.
5. **If compiling in multiple passes, does the compiler know where old classes are?** Add `-cp <output-root>` or configure modules appropriately.
6. **When running, are the classpath root and main class name correct?** Use `java -cp <output-root> <fully.qualified.Main>`.
7. **If packaging, are the contents *inside* the output root placed into the JAR properly?** Inspect with `jar --list`.
8. **Are there stale files or unprocessed resources?** Distinguish outputs created by `javac` from other build steps.

One sentence to remember: **`-d` selects the root of the class-file tree; `package` declarations determine the subdirectories; `-cp` or the module path helps the compiler/JVM find those class files later.**

### Official Reference

Oracle JDK 21 `javac` command documentation: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html — see sections `-d`, `--class-path`, `-s`, and “Configuring a Compilation”.