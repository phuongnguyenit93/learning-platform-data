# Compiling One or Multiple Modules with `--module-source-path` in Java

The Java Platform Module System (JPMS), introduced in Java 9, allows an application to declare **named modules** using `module-info.java`. When compiling a source tree containing multiple modules, `javac --module-source-path` tells the compiler **the source location of each module** and how to determine which module a `.java` file belongs to. Combined with `-m` / `--module`, you can compile a single module or multiple dependent modules in one `javac` invocation.

It is important to distinguish four things: **declaring the module in source code** (`module-info.java`), **locating module sources** (`--module-source-path`), **selecting modules to compile** (`-m`), and **locating compiled modules at runtime** (`java --module-path`). They serve different roles.

## 1. What Is a Java Module?

A named module has a name, contains packages, and has a descriptor usually located in a `module-info.java` file at the root of the module's source tree. For example:

~~~java
// module-info.java
module com.example.library {
    exports com.example.api;
}
~~~

- `module com.example.library` declares the module name.
- `exports com.example.api` allows modules that read this module to access **public types** belonging to package `com.example.api` under JPMS rules.
- `requires com.example.library` in another module declares a readability dependency on this module.
- `exports` is not equivalent to `requires`: one specifies which package is exposed, and the other specifies which module needs to be read.
- Module descriptor syntax also includes `requires transitive`, `requires static`, `opens`, `uses`, and `provides ... with ...`. In this lesson, the `requires`/`exports` pair is sufficient to illustrate the compilation workflow.

When compiled, `module-info.java` produces `module-info.class`; classes in packages produce the other `.class` files. Named modules are commonly distributed as an **exploded module directory** or a **modular JAR** containing the descriptor.

For Java code not placed in a named module (unnamed module/classpath), the layout and compilation commands differ; **using `--module-source-path` is not mandatory for every Java program**.

## 2. Map of Options Commonly Used Together

| Option | Where used? | Function |
| --- | --- | --- |
| `javac --module-source-path PATH` | Compile | Specifies how to locate the **source trees of named modules** |
| `javac --module M1,M2` or `javac -m M1,M2` | Compile | Selects the source modules to be compiled |
| `javac -d OUT` | Compile | Specifies where to write `.class` files; when compiling multiple modules, output is separated by module |
| `javac --module-path MODS` / `-p MODS` | Compile | Finds **compiled modules** that source modules depend on |
| `javac --release 17` | Compile | Checks source/API and generates classes compatible with Java 17 |
| `java --module-path MODS` / `-p MODS` | Run | Finds available modules for resolution and launch |
| `java --module M/pack.Main` / `java -m M/pack.Main` | Run | Specifies the module and main class to execute |

**Note the two meanings of `-m`:** in `javac`, `-m` selects **modules to compile**; in `java`, `-m` selects the **module to launch**. Both tools share the option spelling yet perform two different tasks.

`--module-source-path` is neither `--module-path` nor `--source-path`. Specifying a source path while forgetting `-m` or forgetting to list source files does not cause the compiler to compile the entire source tree; the path only states **where to find sources**, whereas the `-m` list or `.java` files specify **the inputs to compile**.

## 3. Laying Out the Source Tree by Module

The simplest approach for a small project is a parent `src/` directory containing **one directory named exactly after each module**. Inside each module are `module-info.java` and the package tree:

~~~text
project/
├── src/
│   ├── com.example.lib/
│   │   ├── module-info.java
│   │   └── com/
│   │       └── example/
│   │           └── lib/
│   │               └── Message.java
│   └── com.example.app/
│       ├── module-info.java
│       └── com/
│           └── example/
│               └── app/
│                   └── Main.java
└── out/                       # Created before javac runs
~~~

With this tree structure, `--module-source-path src` tells `javac` that module source roots lie under `src`, with each subdirectory corresponding to the module of the same name. You do not need to list the source filenames of every class when using `--module` to select modules.

Another view:

~~~text
--module-source-path src
             │
             ├── com.example.lib/ → source of module com.example.lib
             │                         └── module-info.java
             └── com.example.app/ → source of module com.example.app
                                       └── module-info.java

javac -d out
             │
             ├── com.example.lib/ → module-info.class and library classes
             └── com.example.app/ → module-info.class and app classes
~~~

**Package names and module names are distinct.** A module can contain multiple packages and is not required to have its main package match the module name. In this example, they share a prefix solely for clarity.

Place `module-info.java` at the module root. Files declaring `package com.example.lib;` sit in `com/example/lib/` beneath that root. Code in a **named module** must belong to a named package; do not place application classes in the unnamed/default package.

## 4. Complete Example: Two Dependent Modules

Create **four files** matching the directory tree in section 3.

### 4.1. Library descriptor

**File `src/com.example.lib/module-info.java`:**

~~~java
module com.example.lib {
    exports com.example.lib;
}
~~~

The descriptor allows code in other modules to read public types in package `com.example.lib` if those modules declare an appropriate `requires` relationship.

### 4.2. Public library class

**File `src/com.example.lib/com/example/lib/Message.java`:**

~~~java
package com.example.lib;

public final class Message {
    private Message() {
    }

    public static String say() {
        return "hello modular Java";
    }
}
~~~

The `say()` method is public and static, eligible for `com.example.app` to call once both module dependency and export are valid.

### 4.3. Application descriptor

**File `src/com.example.app/module-info.java`:**

~~~java
module com.example.app {
    requires com.example.lib;
}
~~~

If `requires com.example.lib;` is omitted, `com.example.app` lacks a properly declared readability relationship to module `com.example.lib`. Even though the library module has `exports`, the application does not automatically gain permission to use its public API under the JPMS model.

### 4.4. Main class

**File `src/com.example.app/com/example/app/Main.java`:**

~~~java
package com.example.app;

import com.example.lib.Message;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Message.say());
    }
}
~~~

`import com.example.lib.Message;` only lets you use the short name `Message` in source code. It does not replace `requires` and does not automatically add a JAR dependency.

## 5. Compiling Both Modules in One Command

From the `project/` directory containing `src/`, create an empty output directory `out/`, then run:

~~~bash
mkdir out
javac --release 17 -d out --module-source-path src -m com.example.lib,com.example.app
~~~

This command applies to **JDK 17+**. If the `out` directory already exists, skip the `mkdir out` step. Module names in `-m` are separated by **commas**, not the filesystem classpath separator.

Meaning of each part:

1. `--release 17`: targets Java 17 for source/API/bytecode.
2. `-d out`: output location. For multiple named modules, `javac` automatically creates per-module output directories.
3. `--module-source-path src`: path to the **module source hierarchy**, from which the compiler finds `src/com.example.lib/` and `src/com.example.app/`.
4. `-m com.example.lib,com.example.app`: instructs compiling the source code of the selected modules.
5. From `requires com.example.lib`, `javac` knows app depends on the library; it can resolve references across source modules within the same compilation.

**Result:** a successful `javac` run typically **prints nothing to stdout**. The generated files are:

~~~text
out/
├── com.example.lib/
│   ├── module-info.class
│   └── com/example/lib/Message.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
~~~

These are two **exploded named modules**. A directory `out/com.example.lib` is not a JAR file, yet it can be used as a module on the module path because it contains `module-info.class` and the corresponding package tree.

### Running the compiled program

~~~bash
java --module-path out --module com.example.app/com.example.app.Main
~~~

Short form:

~~~bash
java -p out -m com.example.app/com.example.app.Main
~~~

**Exact stdout:**

~~~text
hello modular Java
~~~

`java` takes `out` as the location to find compiled modules; it selects module `com.example.app` and then class `com.example.app.Main`. The JVM resolves the `com.example.lib` dependency and invokes `main`. The `--module-source-path src` option is used during **compilation**, and is not needed at runtime.

This example requires no extra JARs or external libraries because it uses only standard JDK APIs and the two given source modules.

## 6. Compiling a Single Module Using the Same Module Source Path

When you only want to compile the library module:

~~~bash
mkdir lib-out
javac --release 17 -d lib-out --module-source-path src -m com.example.lib
~~~

Output:

~~~text
lib-out/
└── com.example.lib/
    ├── module-info.class
    └── com/example/lib/Message.class
~~~

Specify `-m com.example.lib` to select the library module's sources. If you select a **module with source dependencies** like `com.example.app`, the compiler can also compile the source modules it needs to complete compilation. With the example layout and an empty output directory, the following command can produce both app and lib:

~~~bash
mkdir app-out
javac --release 17 -d app-out --module-source-path src -m com.example.app
~~~

Do not interpret `-m com.example.app` as a guarantee that the output will contain **only** that module. The compiler determines source dependencies from the module graph; when you want an explicit, deliberate build of both modules, specify `-m com.example.lib,com.example.app` as in section 5.

### Sequential compilation with an existing module

You can compile the library first, then make the **compiled library** visible to app via the module path. Using an existing `out` output:

~~~bash
javac --release 17 -d out --module-source-path src -m com.example.lib
javac --release 17 -d out --module-source-path src --module-path out -m com.example.app
java --module-path out -m com.example.app/com.example.app.Main
~~~

`--module-path out` in the second `javac` invocation directs the compiler to locate the compiled library module if present; `--module-source-path src` still points to module sources. When organizing real builds, avoid confusing source path and module path if multiple versions with the same module name might exist; verify which module the compiler prioritizes based on configuration and actual artifacts.

Another option for **a single module** is to specify the `.java` files to compile together with `module-info.java`, and use `--module-path` when depending on already-compiled modules. `--module-source-path` is especially useful when you want the compiler to properly locate multiple source modules within a shared tree.

## 7. Two Syntax Forms of `--module-source-path`

According to the `javac` documentation, the module source path has a **module-pattern form** and a **module-specific form**. They handle different directory structures.

### 7.1. Pattern form: a uniform tree

With the simple tree layout above:

~~~bash
javac --release 17 -d out --module-source-path src -m com.example.lib,com.example.app
~~~

If there is no `*` in the path pattern, `javac` implicitly expects modules directly beneath the path (equivalent to appending `/*` to each appropriate segment). You can write the pattern explicitly:

~~~bash
javac --release 17 -d out --module-source-path "src/*" -m com.example.lib,com.example.app
~~~

In **module-pattern form**, `*` is a **placeholder for the module name**, not merely a wildcard for the shell to expand files. Enclose the pattern in quotes so PowerShell, Bash, or command runners do not interfere with the argument passed to `javac`.

For a common layout where each module also has `src/main/java`:

~~~text
workspace/
├── com.example.lib/
│   └── src/main/java/
│       ├── module-info.java
│       └── com/example/lib/Message.java
└── com.example.app/
    └── src/main/java/
        ├── module-info.java
        └── com/example/app/Main.java
~~~

You can use:

~~~bash
javac --release 17 -d out --module-source-path "*/src/main/java" -m com.example.lib,com.example.app
~~~

Run the command from the `workspace` directory. Each module name is substituted for `*`, so the compiler locates `com.example.lib/src/main/java` and `com.example.app/src/main/java`. If all module directories lie under `modules/`, the corresponding pattern is `"modules/*/src/main/java"`.

**Note:** this is a **module source path** pattern, not a glob to list all `.java` files. Do not write `"src/**/*.java"` as a substitute for `--module-source-path`.

### 7.2. Module-specific form: `module-name=path`

If module sources are not arranged under a uniform convention, or you want exact per-module configuration:

~~~bash
javac --release 17 -d out ^
  --module-source-path com.example.lib=src/com.example.lib ^
  --module-source-path com.example.app=src/com.example.app ^
  -m com.example.lib,com.example.app
~~~

**In the command block above, `^` is a line-continuation character only for Windows CMD**; do not use it verbatim in PowerShell or Bash. To avoid OS differences, you can write it on **a single line**:

~~~bash
javac --release 17 -d out --module-source-path com.example.lib=src/com.example.lib --module-source-path com.example.app=src/com.example.app -m com.example.lib,com.example.app
~~~

This syntax tells `javac` that module `com.example.lib` is at `src/com.example.lib` and module `com.example.app` is at `src/com.example.app`. The path can be enclosed in quotes if it contains spaces (quote the entire argument `"com.example.lib=path with spaces"` so it is passed as a single argument to `javac`).

You can combine **one** pattern with module-specific overrides. When the same module is declared in both ways, the **module-specific** location takes precedence. Do not use two different module-pattern forms in the same invocation and do not specify the module-specific form repeatedly for **the same module**.

### 7.3. Multiple source locations for the same module

The module-specific form can specify a list of search roots for a module when the project design requires multiple source directories. The path-list separator depends on the OS: `;` on Windows, `:` on Linux/macOS. Illustrative example:

~~~text
Windows:  --module-source-path "com.example.lib=src/lib-main;src/lib-generated"
Unix:     --module-source-path "com.example.lib=src/lib-main:src/lib-generated"
~~~

These are path configurations, **to be used only when those directories actually exist and contain the appropriate package trees**; they are not two commands that can run standalone from the `src` example above. The module-pattern form also has rules for separating multiple path segments and expanding curly braces. Avoid scattering redundant options when a simple pattern already describes the source layout.

## 8. Distinguishing `--module-source-path` from Other Paths

### `--source-path`: locating sources by package

In a compilation **that is not multi-module**, `--source-path` or `-sourcepath` describes the location of source files by package tree. It does not fully represent the rules for locating **multiple independent source modules** like `--module-source-path`.

Example of a traditional non-JPMS project:

~~~text
src/com/example/Main.java
~~~

Can be compiled with:

~~~bash
javac --release 17 -d out -sourcepath src src/com/example/Main.java
~~~

This is an example illustrating option differences, **not to be run directly against the four modular files** from section 4.

### `--class-path`: locating classpath entries

The classpath is the world of the **unnamed module**. A library can be used via `-cp` in traditional code, yet it does not automatically create a named module for the library and does not replace a named module's `requires` requirement. Mixing classpath, automatic modules, and named modules has its own readability/export rules; do not assume adding `-cp` can fix all module graph errors.

### `--module-path`: locating compiled modules

`javac --module-path out` lets the compiler see compiled named modules; `java --module-path out` lets the launcher/runtime find modules. It does not replace specifying source roots when you want to compile multiple source modules simultaneously.

If only the library JAR is available, such as `lib/com.example.lib.jar`, and the app source is in a module root, a sequential build can pass that JAR via `--module-path lib` instead of placing the library source on `--module-source-path`. Do not confuse **module path** with **module source path** because they point to two different kinds of inputs.

## 9. Compiling with a List of Source Files Instead of `-m`

`--module-source-path` specifies where to locate sources; to compile, you can specify **module names** with `-m` or specific **file paths**.

For example, to explicitly name the two source files belonging to the library:

~~~bash
javac --release 17 -d out --module-source-path src src/com.example.lib/module-info.java src/com.example.lib/com/example/lib/Message.java
~~~

In multi-module compilation mode, every directly listed source file must lie under valid module roots of the module source path. The command above illustrates specifying source files **belonging to a module**; if compiling app simultaneously as well, you must also list app's files or use `-m` to let the compiler select modules.

When multiple modules have dozens or hundreds of files, `-m` is usually much cleaner than listing all `.java` files. `-m` allows the compiler to determine the source files in the selected modules and the needed dependencies. In build tools, plugins/tasks orchestrate per-module compilation without requiring you to list them manually on the command line.

## 10. Inspecting `.class` and Module Outputs After Compilation

After running the command in section 5:

~~~bash
javap --module-path out --module com.example.lib -p com.example.lib.Message
javap --module-path out --module com.example.app -p com.example.app.Main
~~~

`javap` can inspect classes in named modules with the corresponding module path. If your toolchain does not support that exact pair of options, pass the class file path in `out` directly to inspect the descriptor/bytecode:

~~~bash
javap -p out/com.example.lib/com/example/lib/Message.class
javap -p out/com.example.app/com/example/app/Main.class
~~~

`javap` is for inspecting the bytecode/method signatures of generated artifacts, and **does not fix `requires`/package exports errors**.

You can run:

~~~bash
java --show-module-resolution --module-path out -m com.example.app/com.example.app.Main
~~~

to observe module resolution at runtime. Depending on the JVM and configuration, resolution information is often printed to stderr alongside stdout `hello modular Java`, so when verifying **pure stdout**, run the normal command in section 5.

## 11. Packaging into Modular JARs (Post-Compilation Step)

`--module-source-path` serves **compilation**. Packaging is a separate step; once exploded modules exist in `out`, each module can be packaged into a modular JAR.

Create the `dist` directory and run from `project/`:

~~~bash
mkdir dist
jar --create --file dist/com.example.lib.jar -C out/com.example.lib .
jar --create --file dist/com.example.app.jar --main-class com.example.app.Main -C out/com.example.app .
~~~

Each JAR contains the `module-info.class` of its corresponding module. Specifying `--main-class` in the `jar` command records the entry point for the app module so you can launch the module without writing `/MainClass` when appropriate.

You can run explicitly:

~~~bash
java --module-path dist -m com.example.app/com.example.app.Main
~~~

Stdout remains:

~~~text
hello modular Java
~~~

How this differs from traditional `java -jar`: this is a **named module launch** via the module path, using `requires`/exports and module resolution. Do not assume two modular JARs must be merged into a single fat JAR; JPMS is designed so modules can be distributed and resolved independently.

Do not package the entire `out` directory (containing multiple modules) into one JAR as if it were a single module. Each modular JAR must have the module descriptor and class tree of **that single module** at the JAR root.

## 12. Common Errors and How to Diagnose Them

| Error/symptom | What to check |
| --- | --- |
| `module not found on module source path` | Name in `-m`, module directory name, `module-info.java`, pattern, and working directory |
| `module name ... does not match expected name ...` | Whether the name after `module` in the descriptor matches the module name inferred from the pattern |
| `not in a module on the module source path` | Whether directly specified `.java` files lie under a valid module root |
| `package ... is not visible` | Whether the consumer module has `requires`; whether the provider module `exports` the exact package; whether the type is public |
| `module not found: com.example.lib` | Source module/path or compiled module/path does not yet contain the requested module; check names and contents |
| `class not found` / `Could not find or load main class` | Output path, module path, fully qualified class name, and whether the class has a valid main method |
| Compilation succeeds yet runtime cannot resolve module | `java --module-path` points to the wrong location; missing modular JAR, missing dependency, or incompatible class files |
| Output directory exists but lacks `module-info.class` | Whether the named module was actually compiled; whether output was deleted/overwritten by mistake |
| `invalid flag` / `invalid target release` | Which JDK/compiler is running (`javac -version`), option syntax, and `--release` level |
| `java: Error occurred during initialization of boot layer` | Runtime module graph: descriptors, duplicate modules, missing module, split packages, or related configuration errors |

### 12.1. Module name must match the path pattern

If `src/com.example.lib/module-info.java` declares:

~~~java
module com.example.other {
}
~~~

then it does not match the `com.example.lib` module root logic of the `--module-source-path src` pattern. This is an **intentionally invalid sample**, not a replacement for the main example. Fix the descriptor or source layout so that the module name in `module-info.java` and the module name in `-m`/source hierarchy are consistent.

### 12.2. Missing `exports` cannot be fixed with `import`

If `com.example.lib` does not export `com.example.lib`, even if app writes:

~~~java
import com.example.lib.Message;
~~~

it is still not permitted to use that public type under JPMS. An import only shortens names; **it does not cross module exports boundaries**.

### 12.3. Missing `requires` cannot be fixed with `--module-source-path`

If the app module does not declare `requires com.example.lib;` (or an appropriate module-read mechanism in a special context), simply placing lib's sources next to app's sources does not grant access in the module graph. `--module-source-path` helps the compiler **locate modules**, rather than turning every module into a dependency of all other modules.

### 12.4. Multi-level directory tree with a pattern that is too short

With actual sources at `modules/com.example.lib/src/main/java/`, the pattern `--module-source-path modules` will locate the wrong root. Use:

~~~bash
javac --release 17 -d out --module-source-path "modules/*/src/main/java" -m com.example.lib,com.example.app
~~~

This command is for a **modules/** layout different from `src/` in the main example; use it only when the files have been placed at those exact locations.

### 12.5. A package appearing in multiple modules

JPMS enforces restrictions on split packages, especially when the module graph needs to read different modules containing identically named packages. Do not resolve this by reordering `-m`, merging class files into a single module root, or arbitrarily falling back to the classpath. Organize **package ownership** clearly to avoid ambiguity and configurations that violate the module model.

### 12.6. The command succeeded, yet you see classes for only one module

Check the exact argument to `-m`, which source files were selected, and module dependencies. `javac -m com.example.lib` does not force the compiler to build app as well if app was not requested and is not a dependency of lib.

## 13. Working Reliably in Projects

1. **Choose a clear layout:** each named module has a root and `module-info.java`; package files follow the proper package tree. For a shared layout, use `--module-source-path src` or a pattern matching the directory paths.
2. **Define the module graph:** dependent modules must declare `requires`, and modules providing public APIs must `exports` the exact packages. Do not attempt to fix the module graph with Java imports alone.
3. **Compile to a clean output when verifying:** `javac --release 17 -d out --module-source-path src -m ...`; use an empty output directory to avoid confusion with stale class files.
4. **Inspect output per module:** `out/<module-name>/module-info.class` and class files in the package tree. If annotation processors are used, there may also be separate generated output.
5. **Run via the module path:** `java -p out -m M/package.Main`, checking module resolution and actual stdout.
6. **Package individual modules when needed:** building modular JARs is a separate step and is not part of `--module-source-path`.
7. **In large system builds:** Gradle/Maven can provide appropriate compile tasks, dependency resolution, annotation processing, and packaging. Understanding `javac` directly helps debug build configurations without needing to replace the entire build system with a manual command.

### Quick Cheat Sheet

| You want to... | Core command/option |
| --- | --- |
| Compile only the library from the same source tree | `javac -d out --module-source-path src -m com.example.lib` |
| Compile both the library and app at once | `javac -d out --module-source-path src -m com.example.lib,com.example.app` |
| Use a `module/src/main/java` structure | `javac -d out --module-source-path "*/src/main/java" -m ...` |
| Specify a separate source root per module | `--module-source-path moduleName=path` (repeat per module) |
| Compile app against an already compiled library module | `javac --module-path compiledLibs ...` |
| Run app after compilation | `java -p out -m com.example.app/com.example.app.Main` |
| Package a module as a modular JAR | `jar --create --file ... -C out/moduleName .` |

## 14. Self-Check Questions

**1. Why does `--module-source-path src` automatically locate `com.example.lib`?**  
Because the layout has `src/<module-name>/module-info.java`, and the module-pattern form infers each module's source root from the module name. The descriptor must match.

**2. Does specifying `--module-source-path` automatically compile every module?**  
No. You must select modules via `-m` or specify source files; the compiler may also compile required dependent source modules.

**3. Do `-m` in `javac` and `java` serve the same function?**  
No. One selects source modules to compile; the other selects the module to launch.

**4. If app imports `Message` properly but lacks `requires`, what happens?**  
An import does not create a module read edge. The compiler can reject access to the other module's API; an appropriate descriptor is required.

**5. The library has `exports` yet app still reports the package is not visible—what should you check?**  
Check that app has `requires` for the right module, the exported package name is exact, the type is public, and no duplicate module is causing abnormal resolution.

**6. After compiling two modules, what is the structure of `out`?**  
Each module has an `out/<module-name>/` directory containing `module-info.class` and the package/class file tree.

**7. Why is `java -cp out com.example.app.Main` not equivalent to `java -p out -m com.example.app/com.example.app.Main`?**  
`-cp` uses classpath/unnamed-module lookup; `-p` and `-m` use named modules, descriptors, and module resolution. In this example, module launch must be used.

**8. Can `--module-source-path "modules/*/src/main/java"` be used?**  
Yes, when the actual source tree resides at `modules/<module-name>/src/main/java`. The `*` is a module-name placeholder.

**9. Does placing a compiled module on `--module-path` let the compiler read that module's source code?**  
No. The module path points to compiled modules; the module source path points to module sources.

**10. What effect does `--release 17` have?**  
It sets the language level, Java platform API, and class-file target corresponding to Java 17 as supported by the active JDK, helping catch accidental use of newer features/APIs.

## 15. Official Documentation

- [Oracle JDK 17: The javac Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html) — section *The Module Source Path Option*, compilation configuration, and how modules are located.
- [Oracle JDK 17: The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html) — named module launch syntax, `-p`, and `-m`.
- [Java Language Specification 17, Chapter 7 — Packages and Modules](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html) — module declarations, `requires`, `exports`, and language constraints.

**Conclusion:** `--module-source-path` tells `javac` **where to find the source of each named module**; `-m` specifies **which modules to compile**; `-d` stores class files organized by module; and `java --module-path ... -m ...` runs using the compiled output. Understanding each role helps you handle both single-module projects and multiple interdependent modules.