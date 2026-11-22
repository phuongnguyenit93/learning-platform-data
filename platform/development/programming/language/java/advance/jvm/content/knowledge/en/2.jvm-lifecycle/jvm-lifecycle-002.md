# Running a Class, JAR, Module, and Source File: Differences in How the JVM Starts

A Java program can be launched via a **class name**, a **JAR with an entry point**, a **named module**, or directly using a **`.java` source file**. All four ways aim to find the code to execute and invoke the program's entry point, but they differ in **what the Java launcher takes as input**, **how classes and dependencies are located**, **how `main` is selected**, and **whether prior compilation is required**.

Here, "starting the JVM" means running the `java` command in a compatible JDK/runtime. We examine the four modes with syntax supported on **Java 17 and above**, focusing on the lifecycle from the launch command to `main`. To keep examples runnable and consistent, the program entry method uses the familiar Java 17 signature: `public static void main(String[] args)`.

## 1. The Big Picture: The Launcher Chooses How to Find the Program

```text
                    User invokes java command
                               │
          ┌────────────────────┼─────────────────────┐
          │                    │                     │
     Class name on       JAR with manifest       Named module
       classpath             Main-Class         in module path
    java -cp ...           java -jar ...         java -m ...
          │                    │                     │
          └─────────────┬──────┴─────────────────────┘
                        │
                 Find and load main class
                        │
                        ▼
             JVM links/initializes class
                        │
                        ▼
                    Call main(args)
                        │
                        ▼
                  Execute bytecode
             (interpreter/JIT depending on JVM)

  Fourth path: java File.java → compile source code in memory
                     → load main class → run as above
```

The diagram above describes **selecting the launch mode and transferring control to the application**; it does not mean all dependencies are loaded at the same time. The JVM also performs runtime initialization, resolves modules when using modules, loads/links classes on demand, manages threads and memory, and then executes bytecode according to the JVM implementation's mechanism. Calling `main` also does not mean the entire JVM lifecycle ends immediately when this method returns: remaining live threads and process termination conditions still affect when the JVM exits.

### Quick Comparison Table

| Mode | Sample Command | Direct Input | How the Entry Point Is Determined | Prior Compilation Needed? |
| --- | --- | --- | --- | --- |
| **Class** | `java -cp out demo.LaunchDemo` | Fully qualified class name | Class name on the classpath and that class's `main` | Typically yes |
| **Executable JAR** | `java -jar app.jar` | JAR path | `Main-Class` attribute in the manifest | Yes; usually also requires packaging the JAR |
| **Named module** | `java --module-path mods -m com.example.launch/demo.LaunchDemo` | Module name and (optionally) main class | Module is resolved, then the specified or preconfigured main class is selected | Yes; module descriptor and class files |
| **Source file** | `java src/demo/LaunchDemo.java` | `.java` file path | Java launcher compiles the source code in memory, then executes the main class in the file | **No separate `javac` run needed** |

A typical JAR contains `.class` files and resources; **a JAR is not machine code**. "Running a JAR" is a way of distributing/selecting an entry point. "Running a module" is a way of organizing and resolving modules according to the Java Platform Module System (JPMS), not a new type of CPU.

## 2. Preparing a Shared Program for All Four Modes

Create the following project directory and source file (paths relative to the project directory):

```text
project/
└── src/
    └── demo/
        └── LaunchDemo.java
```

Contents of **`src/demo/LaunchDemo.java`**:

```java
package demo;

public class LaunchDemo {
    public static void main(String[] args) {
        String mode = args.length == 0 ? "không truyền" : args[0];
        System.out.println("Chế độ: " + mode);
    }
}
```

The class is in the `demo` package, so **the fully qualified name of the class is `demo.LaunchDemo`**. The program simply prints the first argument passed to `main`; this helps distinguish whether the `java` command treats something as **launcher options** or **application arguments**. All examples below are run from the `project/` directory, using JDK 17+, with `LaunchDemo.java` saved in UTF-8.

```bash
java --version
javac --version
```

If the machine has multiple JDKs, check that both commands use the desired version before interpreting any program errors.

## 3. Mode 1 — Running a Class by Its Fully Qualified Name

### Compile

```bash
mkdir out
javac -encoding UTF-8 -d out src/demo/LaunchDemo.java
```

The `javac` command checks the source code and generates:

```text
out/
└── demo/
    └── LaunchDemo.class
```

The `-d out` option specifies where to place class files; the directory structure underneath follows the package name. In this case, the **`out` directory itself is the classpath root**, while `out/demo` is only the class's package directory.

### Run

```bash
java -cp out demo.LaunchDemo class
```

**Standard output:**

```text
Chế độ: class
```

Command breakdown:

- `java`: starts the Java launcher and runtime.
- `-cp out` (written in full as `-classpath out` or `--class-path out`): provides where to find classes/resources on the **classpath**.
- `demo.LaunchDemo`: the **binary name** of the main class with its package, not a filesystem path.
- `class`: the first application argument, received at `args[0]`, not a class name or a JVM option.

Application classes on the classpath belong to the **unnamed module**. The classpath does not require a `module-info.java` declaration and does not have the `requires`/`exports` boundaries of a named module under JPMS.

**Why might `java LaunchDemo` fail to run?** The sample class declares `package demo;`, so the name to run is `demo.LaunchDemo`. Nor should you use `java out/demo/LaunchDemo.class` in this mode: the launcher expects a **class name**, not a `.class` file path.

### When to Use?

Running directly by class name is convenient for lessons, quickly testing a compiled program, or when a build tool/IDE manages the classpath and knows the exact main class. For programs with many libraries, the classpath needs to include all dependency directories/JARs at runtime. Across different operating systems, the separator between classpath entries differs: typically `;` on Windows and `:` on Linux/macOS. When using complex paths, enclose the classpath string in quotes appropriate for your shell.

## 4. Mode 2 — Running a JAR with `Main-Class`

From the **class file created in step 3**, package the JAR:

```bash
jar --create --file app.jar --main-class demo.LaunchDemo -C out .
```

This command creates `app.jar` containing `demo/LaunchDemo.class` and a manifest with **`Main-Class: demo.LaunchDemo`**. The `-C out .` flag means changing into the `out` directory while adding contents, so that inside the JAR the path is the package path `demo/LaunchDemo.class`, without the `out/` prefix.

Inspect the entries in the JAR:

```bash
jar --list --file app.jar
```

The listing typically includes `META-INF/MANIFEST.MF` and `demo/LaunchDemo.class`. The presence of a class file **does not automatically make a JAR runnable with `-jar`**: the manifest must identify the appropriate main class.

Launch:

```bash
java -jar app.jar jar
```

**Standard output:**

```text
Chế độ: jar
```

In this mode, the launcher opens the JAR and looks up `Main-Class` in the manifest to know which class to launch. As a result, the user does not need to remember the name `demo.LaunchDemo`. `jar` comes after the JAR path, so it becomes `args[0]`.

### Classpath When Using `-jar`

A special point: with `java -jar app.jar`, **the specified JAR is the source for finding the main application class**, and external classpath settings from `-cp`/`CLASSPATH` are not used the way they are in class-name launch mode. Dependent JARs can be declared via the manifest's `Class-Path` or by using an appropriate packaging/distribution strategy. Do not assume that adding `-cp libs/...` to a `java -jar` command will load dependencies as when calling `java -cp`.

Conversely, a JAR **without `Main-Class`** can still be used on the classpath:

```bash
java -cp app.jar demo.LaunchDemo classpath-jar
```

**Standard output:**

```text
Chế độ: classpath-jar
```

This time you explicitly choose the **class name**, using the JAR as a classpath entry; the manifest main class is not needed for a `-cp`-style invocation.

### When to Use?

An executable JAR is suitable for distributing an application with a clear entry point. However, a JAR **does not automatically contain all external libraries**. A "fat JAR" generated by a build tool may have its own structure or specialized launcher; you should consult the documentation of that specific tool rather than extrapolating from the plain JAR example here.

## 5. Mode 3 — Running a Named Module with `--module-path` and `-m`

The **Java Platform Module System (JPMS)** was introduced in Java 9. A named module has a name and a `module-info.java` descriptor; the runtime can use dependency information (`requires`) and inter-module visibility (`exports`, `opens`) when resolving and accessing members. This is the key difference compared to the classpath.

### Add the Descriptor

Create the file **`src/module-info.java`** alongside the `src/demo/` package tree:

```java
module com.example.launch {
}
```

Source tree:

```text
project/
└── src/
    ├── module-info.java
    └── demo/
        └── LaunchDemo.java
```

This module uses `java.base` by default, so `requires java.base;` does not need to be written. It also **does not need `exports demo;` just for the Java launcher to start the module's own main class**. `exports` controls which packages are accessible to other modules; it is not a directive for selecting the main class.

### Compile into an Exploded Module

```bash
mkdir mods
mkdir mods/com.example.launch
javac -encoding UTF-8 -d mods/com.example.launch src/module-info.java src/demo/LaunchDemo.java
```

Output:

```text
mods/
└── com.example.launch/
    ├── module-info.class
    └── demo/
        └── LaunchDemo.class
```

The `mods/com.example.launch` directory is an **exploded module** (a compiled module in directory form); `mods` is the path containing the modules.

### Run the Module and Specify the Main Class

```bash
java --module-path mods -m com.example.launch/demo.LaunchDemo module
```

**Standard output:**

```text
Chế độ: module
```

Explanation:

- `--module-path mods` (abbreviated `-p mods`) tells the JVM where to find the **observable modules** needed.
- `-m` (equivalent to `--module`) selects the module to launch.
- `com.example.launch/demo.LaunchDemo` joins the **module name** and the **main class name** with `/`. This is not a file path.
- `module` at the end of the command is placed into `args[0]`.

In this example, the **module name** is `com.example.launch`, while the **package/class name** is `demo.LaunchDemo`. The two names do not need to match.

Besides the `-m module.name/main.class.Name` syntax, a modular JAR or module can have its main class configured in the module descriptor; in that case, it can be run with `java -m module.name`. The `module-info.java` descriptor written above **does not configure a main class**, so this example **must** specify `/demo.LaunchDemo`.

### How Do Module Path and Classpath Differ?

- **Classpath** lists directories/JARs containing classes; for regular classes, the launcher finds the main class by class name on the classpath.
- **Module path** lets the runtime observe named modules, read module descriptors, resolve dependencies, and enforce module access boundaries.
- The same program can interact with both the classpath and the module path if configured appropriately, but they must not be treated as two path lists with identical behavior.
- **A regular JAR placed on the module path** may be treated as an automatic module under JPMS rules; its behavior differs from a modular JAR that has `module-info.class`. Not every JAR on the module path has an author-declared descriptor.

A module missing a declared dependency or failing to resolve can fail **before reaching `main`**. Therefore, errors related to module path/descriptor are errors at the module graph construction or class loading/linking stage, which is different from `main` throwing an exception once already running.

### Packaging as a Modular JAR (Extension)

From the compiled exploded module, you can create a modular JAR and set its main class:

```bash
jar --create --file launch-module.jar --main-class demo.LaunchDemo -C mods/com.example.launch .
java --module-path launch-module.jar -m com.example.launch modular-jar
```

**Standard output of the `java` command:**

```text
Chế độ: modular-jar
```

The JAR above contains `module-info.class`, so it is recognized as a modular JAR. The `--main-class` option of the `jar` command records the main class information in the appropriate metadata; therefore, the `-m com.example.launch` invocation can omit `/demo.LaunchDemo`. **Do not confuse** the main class representation in the manifest when running `-jar` with the main class metadata used when launching a **named module**: you must check exactly how the packaging tool sets each type.

## 6. Mode 4 — Running a Source File Directly with `java File.java`

Since **Java 11**, the Java launcher supports **source-file mode**: compiling the source file in memory and then executing the main class without **needing to run `javac` separately to produce class files on disk**.

With the `src/demo/LaunchDemo.java` file created in step 2:

```bash
java src/demo/LaunchDemo.java source
```

**Standard output:**

```text
Chế độ: source
```

Unlike `java -cp out demo.LaunchDemo`, the argument after `java` here is an **actual file path** with the `.java` extension; the launcher recognizes source-file mode, uses the runtime's compiler to compile the source into memory, and then runs the main class. Declaring `package demo;` in this source file does not require you to replace the file path with `demo.LaunchDemo` when using source-file mode.

```text
java src/demo/LaunchDemo.java source
          │
          ├─ Recognize source file / select source-file mode
          ├─ Compile source file in memory
          ├─ Load compiled main class
          └─ Call main(new String[]{"source"})
```

You **do not need** to see `out/demo/LaunchDemo.class` after this command: by default, compilation serves only that single launch and does not output class files via `-d out` like `javac`. If the source file has syntax or type errors, compilation errors can appear **directly in the `java File.java` command**, even though you did not explicitly invoke `javac`.

You can specify the source language version (provided the JVM/JDK supports it):

```bash
java --source 17 src/demo/LaunchDemo.java source-17
```

**Standard output:**

```text
Chế độ: source-17
```

Certain source constructs or APIs require an appropriate classpath/module path. Source-file mode is suitable for small examples, scripts, and experiments; it **does not automatically resolve dependencies, build multiple modules, produce distributable JARs, or replace the entire build process**. On Java 17, treat this primarily as a way to run **a single source file as an entry point**, without assuming it automatically scans and compiles an entire multi-file project tree.

### Distinguishing from `java demo.LaunchDemo`

| Command | How does the launcher interpret the argument? |
| --- | --- |
| `java src/demo/LaunchDemo.java` | **Source file path**, going through source-file mode |
| `java -cp out demo.LaunchDemo` | **Compiled class name** on the classpath |
| `java -cp out src/demo/LaunchDemo.java` | The positional launch argument is still a `.java` file path, so it can trigger source-file mode; `-cp out` is a runtime/compiler option and does not turn it into a binary class name |
| `javac src/demo/LaunchDemo.java` | A **compiler** command, not a command to start the JVM and call `main` |

## 7. At Which Lifecycle Stage Do the Real Differences Lie?

Each mode changes **how the entry point is located** and **the preparation before calling `main`**, but the core JVM steps still remain.

### 7.1. Launch Stage: Parsing the Command and Selecting the Entry Point

The launcher reads JVM/launcher options placed **before the launch target** and then decides the mode:

```text
java [options] <main-class> [application-arguments]
java [options] -jar <jar-file> [application-arguments]
java [options] -m <module>[/<main-class>] [application-arguments]
java [options] <source-file>.java [application-arguments]
```

The angle brackets in the diagram are descriptive notation, **not typed literally into the shell**. With the actual syntax in steps 3–6, `class`, `jar`, `module`, and `source` become `args[0]` respectively.

For example, JVM options must come before the class to run:

```bash
java -Xmx256m -cp out demo.LaunchDemo class
```

The result is still `Chế độ: class`. If `-Xmx256m` is placed **after** `demo.LaunchDemo`, the program receives it as the string `args[0]`, and the JVM's maximum memory is not configured by that argument.

### 7.2. Class Finding and Preparation Stage

- **Class launch:** the loader uses the classpath to locate `demo.LaunchDemo`.
- **JAR launch:** the launcher reads `Main-Class` from the JAR's manifest and uses the class lookup mechanism appropriate for `-jar` mode.
- **Module launch:** the runtime resolves the named module from the module path, checks descriptors/dependencies, and finds the main class inside the module.
- **Source-file launch:** the compiler compiles the source code in memory, after which the runtime can load the resulting class for execution.

After locating the class definition, the JVM performs **loading**, **linking** (including verification/preparation and resolution as needed), and **initialization** according to JVM rules. The runtime executes the appropriate static initialization before running the corresponding part of the program. Not all dependent classes are loaded/initialized immediately at startup; much of it happens lazily when the program uses them.

### 7.3. Execution Stage

Once `main` is successfully invoked, all four modes use the same Java semantics for the sample program. Bytecode may be processed by the interpreter or optimized/compiled into machine code by the JIT; distributing classes via directories, JARs, modules, or source files **does not by itself determine whether the program always runs via the interpreter or JIT**.

In this example, the four launch styles differ only in **the argument value passed in**, hence the different stdout lines. If the same argument is passed, the logic of `LaunchDemo.main` produces the same result.

### 7.4. Termination Stage

`main` finishing does not guarantee that the JVM terminates immediately if non-daemon threads are still running. When all process termination conditions are met or `System.exit(...)` is called, the runtime performs the appropriate shutdown sequence. This holds true for all four launch types; there is no rule that "a JAR shuts down the JVM differently from a class" solely because of packaging format.

## 8. Common Errors and How to Diagnose Them

| Symptom | Commonly Related Mode | Check |
| --- | --- | --- |
| `Could not find or load main class` | Class | Does `-cp` point to the **package root directory**? Is the name `demo.LaunchDemo` exact? Has the class been compiled? |
| `no main manifest attribute` | `-jar` | Does the JAR declare `Main-Class`? Was `jar --main-class` or an appropriate manifest creation process used? |
| `ClassNotFoundException` / `NoClassDefFoundError` | Class/JAR and variants | Are dependencies present at runtime? Is the classpath appropriate and complete? Was there an earlier class initialization error? |
| Module not found or module fails to resolve | `-m` | Is the module name right? Does `--module-path` point to the right `mods`/modular JAR? Are dependencies in `requires` sufficient? |
| Main class not found inside module | `-m` | Did you write `-m com.example.launch/demo.LaunchDemo` or set main-class metadata? |
| `javac` error directly when running `java File.java` | Source-file mode | Fix syntax/type errors in source code and dependencies; because the launcher is compiling in memory |
| `UnsupportedClassVersionError` | Running class/JAR/module | Was the class file compiled for a newer Java version than the runtime? Check `java --version` and `javap -verbose` |
| Memory option `-Xmx` has no effect | All modes | Was the JVM option placed **after the launch target** and turned into an application argument? |

### Small Diagnostic Command Set

```bash
javap -classpath out demo.LaunchDemo
jar --list --file app.jar
java --describe-module java.base
java --version
```

- `javap` confirms the compiled class and the `main` signature.
- `jar --list` views the JAR's entries; you can check the manifest when encountering `Main-Class` issues.
- `java --describe-module java.base` shows that the Java runtime understands named modules and provides the base module; for a specific application, describe the target module with the appropriate module path configuration.
- `java --version` checks the runtime in use when encountering bytecode compatibility errors.

## 9. Choosing the Right Launch Method

| Need | Usually Appropriate Method | Reason |
| --- | --- | --- |
| Quickly learn the `.java → .class → JVM` flow, inspect `javap` | `javac`, then `java -cp ... main.Class` | Clearly shows compilation artifacts and package-based class lookup |
| Hand a program with an entry point to someone else to run | `java -jar app.jar` | A single JAR path and entry point in the manifest; still must package/provide dependencies properly |
| A project genuinely designed around JPMS, wanting to declare module dependencies/encapsulation | `java --module-path ... -m ...` | The runtime resolves modules and enforces module boundaries |
| Try out a short source file on a compatible JDK | `java File.java` | No separate `javac` command needed, fewer steps |
| Want to test the effect of packaging | Run the **same class** using `-cp`, `-jar`, `-m` | Helps isolate launch/dependency errors from errors in `main` |

Avoid deciding based solely on the file name: **a JAR can be used as a classpath entry or an executable JAR; a modular JAR can also be launched via the module path**. It is the `java` command that determines which mechanism the launcher chooses.

## 10. Hands-on Exercise to Verify the Four Entry Paths

Using the exact same `LaunchDemo.java` source code from section 2, perform:

1. **Class mode:** compile into `out/`; run `java -cp out demo.LaunchDemo class`; read `Chế độ: class`.
2. **JAR mode:** create `app.jar` from `out/`; run `java -jar app.jar jar`; read `Chế độ: jar`.
3. **Module mode:** add `module-info.java`, compile into `mods/com.example.launch/`; run `java --module-path mods -m com.example.launch/demo.LaunchDemo module`; read `Chế độ: module`.
4. **Source-file mode:** run `java src/demo/LaunchDemo.java source` directly; read `Chế độ: source`.

Controlled experiments:

- Omit `-cp out` in the class-name invocation and observe how class lookup changes. The result also depends on the current directory and classpath environment variable; therefore, check the actual configuration.
- Change `java -jar app.jar jar` to `java -cp app.jar demo.LaunchDemo classpath-jar`; the program runs with the same bytecode, but the launcher takes a **class name** instead of reading `Main-Class`.
- In module mode, replace `com.example.launch` with a nonexistent name; the error occurs during module resolution/selection, **before** the `main` logic begins.
- Introduce a type error into the source (for instance, `int n = "sai";` in `main`) and run source-file mode: this time the `java` command reports a compilation issue because the compiler is invoked implicitly. After fixing it, run again to restore a valid program.

### Self-Check

**1.** Will `java -jar app.jar` launch `demo.LaunchDemo` even if the manifest has no `Main-Class`? **No**; `-jar` mode requires an appropriate entry point in the manifest.

**2.** Why does `java -cp out demo.LaunchDemo` use dots while `java src/demo/LaunchDemo.java` uses slashes? The first uses a **class name within a package**, while the second uses a **source file path**.

**3.** Does `java File.java` skip compilation completely? **No**; source-file mode still compiles the source code, it just **does not require the user to run `javac` separately and does not need to write class files to disk**.

**4.** Do only modular applications run on a JIT-enabled JVM? **No**; JIT is a JVM bytecode execution mechanism, independent of the class/JAR/module/source-file launch choice.

**5.** When does the `-Xmx256m` option become an application argument? When placed **after** the main class/JAR/module/source-file launch target; the launcher passes the subsequent arguments into `main(String[] args)`.

Key point to remember: **class mode** selects the main class from the classpath; **JAR mode** selects via the manifest; **module mode** selects by module name and main class or module metadata; **source-file mode** compiles the source code in memory and then runs it. Simply by looking closely at the target and paths of the `java` command, you will isolate most "fails to start" errors before diving into the application code.