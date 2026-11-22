# Compiling and Running Your First Program Outside an IDE

## What Will You Be Able to Do?

After this lesson, you will be able to create a Java 17+ program yourself using a text editor, use the terminal to **compile with `javac`**, run with `java`, understand why you must configure the classpath, and handle basic errors. You will also know how to compile code with a `package` and, as an extension step, package the program into a runnable JAR.

This lesson focuses on **practical hands-on steps outside an IDE**: you do not need IntelliJ IDEA, Eclipse, or VS Code to complete it. A terminal, a JDK, and a text editor capable of saving UTF-8 text files are enough.

## 1. The Three-Step Workflow

```text
Write source code             Compile                      Execute
src/HelloApp.java --javac--> out/HelloApp.class --java--> JVM runs main(...)
                       ^                                  |
               Command from JDK                     Display result
```

- **`HelloApp.java`** contains human-readable source code, which is what you edit yourself.
- **`javac`** (the Java compiler in the JDK) checks syntax/types and translates source into `.class`, meaning **JVM bytecode**, not a directly executable machine-code file.
- **`java`** is the launcher that starts the JVM, loads class files, and invokes the application entry point. The JVM may use an interpreter and mechanisms such as JIT when appropriate.
- **`out/`** is the output directory you choose with `-d out`; this is not a directory name required by Java.

You **do not need to recompile** just to run the program multiple times if the source and dependencies have not changed. When you modify the source, run `javac` again to update the class file before running.

## 2. Preparing the JDK and Terminal

Install **JDK 17 or newer**, such as JDK 17 or 21, and open a terminal:

- Windows: PowerShell, Command Prompt, or Windows Terminal.
- macOS/Linux: Terminal with Bash, Zsh, or a common shell.

Check:

```bash
java -version
javac -version
```

Actual output contains the **version, vendor, and build information** of the installed JDK; for example, the output of `javac -version` on a JDK 21 looks like `javac 21.0.x`. Do not treat an example version as a mandatory result on every machine.

If **both commands run**, you have the necessary tools. If the terminal reports that a command cannot be found:

1. Confirm that a **JDK** is installed, not just a runtime missing `javac`.
2. Check whether the `PATH` environment variable points to the JDK's `bin` directory.
3. Open a new terminal after changing environment configuration.
4. Check the standalone JDK configuration of your IDE, Gradle, or Maven if you use those tools.

In PowerShell, inspect which executables are being found:

```powershell
Get-Command java
Get-Command javac
```

In Bash/Zsh:

```bash
command -v java
command -v javac
```

The `JAVA_HOME` variable is commonly used by build tools to select a JDK, but the `java`/`javac` commands in the terminal are also affected by `PATH`. Do not assume they always point to the same installation.

### 2.1 Opening the Right Project Directory

Create a `java-terminal-demo` directory in a location where you have write permission and **open the terminal inside that directory**. We will have the structure:

```text
java-terminal-demo/
└── src/
    └── HelloApp.java
```

Create the `src` directory using one of the two commands:

**PowerShell:**

```powershell
New-Item -ItemType Directory -Force src | Out-Null
```

**Bash/Zsh:**

```bash
mkdir -p src
```

If you are in the wrong directory, use `cd` to go to `java-terminal-demo`. To confirm the current directory: `Get-Location` (PowerShell) or `pwd` (Bash/Zsh). The paths `src/` and `out/` in this lesson are **relative paths from the current directory**.

## 3. First Java Program: Create, Compile, Run

Use any text editor to create the exact file **`src/HelloApp.java`** and save it with **UTF-8** encoding:

```java
public class HelloApp {
    public static void main(String[] args) {
        System.out.println("Xin chào từ terminal!");
        System.out.println("Số đối số: " + args.length);

        for (int i = 0; i < args.length; i++) {
            System.out.println("args[" + i + "] = " + args[i]);
        }
    }
}
```

Quick breakdown of the code:

- `public class HelloApp` declares a public class. According to the file-naming rule for a top-level public class, the file must be named **`HelloApp.java`** with exact uppercase/lowercase matching.
- `public static void main(String[] args)` is the familiar entry-point signature long supported by the Java launcher; `args` holds the arguments you pass when running, **and does not contain** the class name.
- `System.out.println(...)` prints to standard output followed by a newline.
- The `for` loop prints each element of `args`; if there are no arguments, the loop does not execute.

### 3.1 Compiling with `javac`

Standing at the **`java-terminal-demo` root directory**, run:

```bash
javac -encoding UTF-8 -d out src/HelloApp.java
```

A successful compilation command normally **prints nothing** to the terminal. Check the new structure:

```text
java-terminal-demo/
├── src/
│   └── HelloApp.java
└── out/
    └── HelloApp.class
```

Meaning of each part:

| Command part | Meaning |
| --- | --- |
| `javac` | Invokes the Java compiler in the JDK |
| `-encoding UTF-8` | Reads source as UTF-8, avoiding reliance on the default charset of some environments |
| `-d out` | Places generated class files in the output directory `out`, following the package structure |
| `src/HelloApp.java` | Path to the source file to compile |

`javac` **can automatically create** the `out` output directory if it does not yet exist, but the parent directory must be available and writable. Normally, exit code 0 means the compiler completed successfully; syntax/type errors result in diagnostics and a non-zero exit code.

### 3.2 Running with `java`

```bash
java -cp out HelloApp
```

Exact output of the code above when **no arguments are passed**:

```text
Xin chào từ terminal!
Số đối số: 0
```

Run again with **two arguments**:

```bash
java -cp out HelloApp Lan Java
```

Output of the code above:

```text
Xin chào từ terminal!
Số đối số: 2
args[0] = Lan
args[1] = Java
```

Explanation:

- `-cp` (full forms `-classpath` or `--class-path`) sets the **classpath** for the Java launcher to locate classes.
- `out` is the root directory containing `HelloApp.class`, not the path to the `.class` file.
- `HelloApp` is the **class name** to run; without a `.java` or `.class` suffix.
- `Lan Java` is two space-separated arguments. If you want to pass **one** argument containing a space, use quotes: `"Lan Java"`.

**Note when checking Vietnamese output:** the source was read by the compiler as UTF-8 thanks to `-encoding UTF-8`, but how the terminal renders characters also depends on font/encoding and console configuration. If you see garbled characters even though the program runs, check your terminal's Unicode display capability.

### 3.3 One Edit → Compile → Run Cycle

Change the first line in the source to:

```java
System.out.println("Chạy Java không cần IDE!");
```

Then re-run **both steps**:

```bash
javac -encoding UTF-8 -d out src/HelloApp.java
java -cp out HelloApp
```

New output (without passing arguments):

```text
Chạy Java không cần IDE!
Số đối số: 0
```

If you only edit `.java` and run `java` **without recompiling**, the JVM may still run the **old class file**, so you will not see the change yet. This is a very common mistake when leaving an IDE, because an IDE automatically performs the compile step in many workflows.

## 4. What Happens Behind the Two Commands?

### `javac` Performs the Compile-Time Step

The compiler reads the source, parses syntax, resolves names/types, and generates class files. For valid code, you get `HelloApp.class` containing bytecode along with class and method metadata. Errors such as missing `;`, type mismatches, calling a non-existent method name, and so on are typically reported at this step.

### `java` Performs the Runtime Step

The launcher creates the JVM, provides the classpath, locates/loads the `HelloApp` class, and calls `main`. From there the program interacts with the standard library, the operating system, and the terminal. Errors such as missing arguments, invalid operations, file read errors, or resource configuration issues typically only manifest at runtime.

How to distinguish the two commands:

```text
javac ...    ==> Source (.java) to bytecode (.class)
java ...     ==> JVM loads class and runs the main method
```

Success at the `javac` step **does not guarantee** that every execution path of the program is valid. For example, code that accesses `args[0]` without checking length may compile normally yet throw `ArrayIndexOutOfBoundsException` when run with no arguments.

## 5. Inspecting Your First Bytecode with `javap`

A useful tool included in the JDK is `javap`:

```bash
javap -classpath out HelloApp
javap -c -classpath out HelloApp
```

- The first command displays the class description along with signatures of selected members, such as the constructor and `main`.
- `-c` displays the bytecode instructions of methods that have code, such as `getstatic`, `invokevirtual`, `arraylength`, `iinc`, or jump instructions.
- Detailed output, instruction order, and constant-pool indices are the result of the actual compiler/class file; **you should not memorize fixed offsets**.

`javap` reads a compiled class file; it **does not run `main`** and **does not perform JIT duties**. Use it to understand the boundary from Java source code to bytecode.

## 6. When an Application Has Packages and Multiple Files

In a real project, Java classes usually reside in a `package` rather than the default package. This is where you need to clearly understand the difference between **source path**, **output structure**, and **fully qualified class name**.

Create the structure:

```text
java-terminal-demo/
└── src/
    └── com/
        └── example/
            ├── GreetingApp.java
            └── text/
                └── Greeting.java
```

You can create the parent directories using a file manager or the corresponding command.

**File `src/com/example/text/Greeting.java`:**

```java
package com.example.text;

public class Greeting {
    public static String message(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

**File `src/com/example/GreetingApp.java`:**

```java
package com.example;

import com.example.text.Greeting;

public class GreetingApp {
    public static void main(String[] args) {
        String name = args.length > 0 ? args[0] : "Java";
        System.out.println(Greeting.message(name));
    }
}
```

Compile **both source files** in a single invocation:

```bash
javac -encoding UTF-8 -d out src/com/example/text/Greeting.java src/com/example/GreetingApp.java
```

The command uses spaces to separate paths; it works in PowerShell, Bash, or Command Prompt when the project is in a directory whose path contains no spaces. If a path contains spaces, wrap each path in double quotes.

After compilation, `out` contains:

```text
out/
└── com/
    └── example/
        ├── GreetingApp.class
        └── text/
            └── Greeting.class
```

Run with the exact **fully qualified class name**:

```bash
java -cp out com.example.GreetingApp Minh
```

Output:

```text
Xin chào, Minh!
```

**Key points:**

- `package com.example;` is part of the class name. The launcher needs `com.example.GreetingApp`, not just `GreetingApp`.
- `-cp out` points to the **root of the package tree**. Do not use `-cp out/com/example` to run `com.example.GreetingApp`.
- `-d out` instructs the compiler to create the directory structure matching the package.
- `import` lets source code reference class names conveniently; it does not automatically add JARs or files to the runtime classpath.
- Both classes can be compiled together or supplied via an appropriate sourcepath/classpath; in this example we pass both source files so the command is clear and reproducible.

### 6.1 Distinguishing Compiler and Runtime `classpath`

Suppose `Greeting.class` has already been compiled into `out`, and you want to recompile `GreetingApp.java` alone. You can use:

```bash
javac -encoding UTF-8 -cp out -d out src/com/example/GreetingApp.java
java -cp out com.example.GreetingApp Minh
```

Here:

- `javac -cp out` tells the compiler where to find **already-compiled dependencies**.
- `java -cp out` tells the JVM where to find classes **at runtime**.

If the compile-time and runtime classpaths differ, the code may build successfully and then hit `ClassNotFoundException` or `NoClassDefFoundError` when run, depending on the cause and class-loading mechanism.

With multiple entries in the classpath, the separator depends on the operating system:

- macOS/Linux: `-cp "out:libs/example.jar"`.
- Windows: `-cp "out;libs/example.jar"`.

This is the **separator between entries in the classpath**, not the directory separator. For the first exercise that only has `out`, you do not need to handle this difference.

## 7. Extension: Creating a JAR and Running Without Specifying a Classpath

JAR is an archive format, usually containing class files/resources. The `GreetingApp` exercise can be packaged into an **executable JAR** with `Main-Class` information in the manifest.

After successfully compiling the two files in section 6, create the `build` directory:

**PowerShell:**

```powershell
New-Item -ItemType Directory -Force build | Out-Null
```

**Bash/Zsh:**

```bash
mkdir -p build
```

Package using the `jar` tool included in JDK 17+:

```bash
jar --create --file build/greeting-app.jar --main-class com.example.GreetingApp -C out .
```

Explanation:

- `--create` creates a JAR.
- `--file build/greeting-app.jar` specifies the JAR file path.
- `--main-class com.example.GreetingApp` writes the entry point into the manifest.
- `-C out .` tells `jar` to change to `out` and package the files inside, without carrying the `out/` prefix into entry paths.

Run:

```bash
java -jar build/greeting-app.jar Minh
```

Example output:

```text
Xin chào, Minh!
```

At this point, the launcher gets the main class name from the manifest; you do not need to type `com.example.GreetingApp` yourself. However, **`java -jar` does not automatically load dependencies outside the JAR**. If the application uses external libraries, an appropriate packaging strategy or classpath is still needed; this section only uses the two classes packaged together.

To inspect the JAR contents:

```bash
jar --list --file build/greeting-app.jar
```

The listing includes the manifest and class files; entry order should not be used as a test assertion. Do not confuse a **JAR with `Main-Class`** with every library JAR: many JARs only provide classes and have no entry point for `java -jar`.

## 8. Common Errors and How to Self-Diagnose

| Symptom | Common Cause | How to Check and Fix |
| --- | --- | --- |
| `javac: command not found` / `'javac' is not recognized` | Compiler is not in the environment or `PATH` is wrong | Check the JDK installation and the location containing `bin/javac`; open a new terminal |
| `error: file not found: src/HelloApp.java` | Wrong current directory, wrong file name, or file not yet saved | Use `pwd`/`Get-Location`; check the `src` directory and actual file name |
| `class HelloApp is public, should be declared in a file named HelloApp.java` | File and top-level public class do not have the same name | Rename the file to `HelloApp.java` with exact capitalization |
| `';' expected`, `cannot find symbol` | Syntax error, invalid variable/class name, or reference | Check the path and line number reported by the compiler, fix the source, and recompile |
| `Could not find or load main class HelloApp` | Wrong classpath or class name does not match package | Check `out/HelloApp.class`, use `java -cp out HelloApp` |
| `Could not find or load main class com.example.GreetingApp` | Wrong fully qualified name or classpath root when running | Use `java -cp out com.example.GreetingApp`, check the `out/com/example` tree |
| `Main method not found in class ...` | No valid entry point for the launcher mode being used | Use `public static void main(String[] args)` in Java 17+ examples |
| `UnsupportedClassVersionError` | Class file compiled at a newer JVM level than the runtime | Check `java -version`, `javac -version`; use a matching runtime or `--release` when compiling |
| `NoClassDefFoundError` | Missing a class / unable to finish loading or initializing a required class | Review the runtime classpath, dependencies, and `Caused by` reason |
| Runs and prints **old output** | Did not recompile or running class from a different directory | Recompile; check the output path and the launcher's classpath |
| Garbled Vietnamese characters | Console font/encoding does not support it or file saved with wrong encoding | Save source as UTF-8; use `-encoding UTF-8`; adjust terminal Unicode settings |
| `Unable to access jarfile ...` | JAR file not created yet, wrong path, or missing access permission | Check the `build/greeting-app.jar` path, rebuild, and then run |

### 8.1 Reading Compiler Diagnostics

Suppose you accidentally omit a `;`:

```java
public class Broken {
    public static void main(String[] args) {
        System.out.println("Hello")
    }
}
```

Running `javac Broken.java` may produce a diagnostic pointing to the line missing `;` and reporting `';' expected`. Line numbers/format depend on the JDK; the key takeaway is that **the compiler does not produce a valid program from broken source**. Fix it:

```java
System.out.println("Hello");
```

and then recompile.

### 8.2 Argument Order of `java` Is Very Important

Correct:

```bash
java -cp out HelloApp Lan
```

Wrong in intent:

```bash
java HelloApp -cp out
```

In the second invocation, after the main class name, `-cp` and `out` are **application arguments**, no longer launcher options to set the classpath. If the JVM did not already find the class beforehand, the program still fails.

An easy-to-remember pattern is:

```text
java [JVM/launcher options] -cp <classpath> <fully.qualified.class.name> [application arguments]
```

Square brackets in the line above indicate **optional parts in syntax notation**; do not type them into actual commands.

### 8.3 Understanding the Difference Between File Path and Class Name

With source `src/com/example/GreetingApp.java`:

- `javac ... src/com/example/GreetingApp.java` takes a **source file path**.
- `java -cp out com.example.GreetingApp` takes the **fully qualified binary name of the class** and the classpath root.
- `java -jar build/greeting-app.jar` takes a **JAR file path**, then finds the main class via the manifest.

Do not swap `.java`, `.class`, `.jar`, or class names across modes.

## 9. Options to Know After Running the Examples

| Command / Option | Purpose |
| --- | --- |
| `javac -help` | View help and available compiler options |
| `java --help` | View how to run a class, JAR, module, or source according to version |
| `javac -d out ...` | Set the root output directory for classes |
| `javac -encoding UTF-8 ...` | Specify the charset for reading source |
| `javac --release 17 -d out ...` | On supporting JDKs, compile source/API/bytecode targeting Java 17 |
| `javac -cp out ...` | Let the compiler locate compiled dependencies |
| `java -cp out ...` | Let the JVM locate classes at runtime |
| `javap -c -classpath out ...` | View bytecode instructions |
| `jar --create --file ...` | Create a JAR |
| `java -jar ...` | Run an executable JAR according to the manifest |

Example when using **JDK 21** to compile source for a Java 17 runtime:

```bash
javac --release 17 -encoding UTF-8 -d out src/HelloApp.java
java -cp out HelloApp
```

`--release 17` restricts syntax, Java platform APIs, and the class-file target to the specified release; this does not guarantee that an external library remains compatible or that the application has no runtime errors. In particular, running the compiler on an older JDK **cannot** select a release newer than what it supports.

**Source-file mode does not replace this practice exercise.** On an appropriate JDK, a command like `java src/HelloApp.java` can compile and execute a source file directly. However, to understand the workflow outside an IDE, perform `javac ...` and `java -cp ...` separately first; that is the easiest way to observe `.class` outputs, the classpath, and the effect of modifying source code.

## 10. Self-Practice Exercises with Verified Answers

### Exercise 1: Compute the Sum of Two Integers

Create file **`src/SumApp.java`**:

```java
public class SumApp {
    public static void main(String[] args) {
        int a = 7;
        int b = 12;
        System.out.println("Tổng = " + (a + b));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 -d out src/SumApp.java
java -cp out SumApp
```

Expected result:

```text
Tổng = 19
```

Question: If you only change `b` to `20` and immediately call `java -cp out SumApp` without recompiling, why can the result still be `19`? Because the JVM uses the old `SumApp.class`. After recompiling, the new result is `Tổng = 27`.

### Exercise 2: Pass an Argument with Spaces

Using `HelloApp` from section 3, run:

```bash
java -cp out HelloApp "Nguyen Van A"
```

If you are still using the initial source, the output is:

```text
Xin chào từ terminal!
Số đối số: 1
args[0] = Nguyen Van A
```

If you modified the source as in section 3.3 and recompiled, the first line will be `Chạy Java không cần IDE!`; the two argument lines stay unchanged. This is a way to verify for yourself the exact version of the class file being used.

### Exercise 3: Explain the Classpath Error

After compiling `HelloApp` into `out`, try:

```bash
java -cp src HelloApp
```

This command usually fails to find `HelloApp` because `src` contains source files rather than compiled class files. Fix it to:

```bash
java -cp out HelloApp
```

Key point: the classpath in class-execution mode indicates **where bytecode and runtime dependencies are located**, rather than searching all source code in the project by default.

### Exercise 4: Verify Package Behavior

Compile the two files in section 6, then try invoking `java -cp out GreetingApp`. Explain the error and rewrite the correct command:

```bash
java -cp out com.example.GreetingApp
```

Output if no name is passed:

```text
Xin chào, Java!
```

Reason: the package is part of the class name; `GreetingApp` here actually has the fully qualified name `com.example.GreetingApp`.

## 11. Completion Checklist

- [ ] `java -version` and `javac -version` run in the terminal.
- [ ] Created exact `src/HelloApp.java` saved as UTF-8.
- [ ] Compiled with `javac -encoding UTF-8 -d out src/HelloApp.java` and saw `out/HelloApp.class`.
- [ ] Ran `java -cp out HelloApp`, confirmed output with no arguments.
- [ ] Ran with two arguments and explained `args.length`.
- [ ] Edited source, recompiled, and saw the new output.
- [ ] Used `javap -c` to see that the class file contains bytecode.
- [ ] Compiled/ran `com.example.GreetingApp` using its fully qualified class name.
- [ ] Resolved a wrong-classpath/wrong-filename error yourself without using IDE actions.
- [ ] (Extension) Created and ran `build/greeting-app.jar`.

## Key Takeaway

**`javac` takes source paths to produce bytecode; `java` takes a class name along with the classpath to run bytecode in the JVM.** When you perform both steps yourself outside an IDE, you clearly see which files are generated, where the JVM is looking for classes, how arguments are passed, and why editing code must be accompanied by recompilation. These skills are the foundation for later understanding Gradle/Maven, dependency errors, build-time/run-time differences, and deploying Java applications on servers.