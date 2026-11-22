# Working Directory, Output Directory, and Classpath in Java

> **Module:** Java core — language-basics  
> **Topic:** Tools and Execution  
> **Objective:** Distinguish the process working directory, compilation output directory, and classpath. Compile and run a Java project with `package`, multiple `.java` files, a data file, and a classpath resource; explain why the JVM can find a class while the program fails to find a file, or vice versa.

## 1. Three types of paths to distinguish

A Java program can both load `.class` bytecode and read files on disk. Those are **two different lookup mechanisms**, plus a third mechanism when the compiler writes output:

| Concept | Purpose | Example |
| --- | --- | --- |
| **Working directory** (CWD) | Where **relative** file paths are resolved when the process runs | `Path.of("data", "customer.txt")` reads from the `data` directory under CWD |
| **Output directory** | Where `javac -d` writes `.class` files according to the package tree | `javac -d out ...` writes `out/demo/app/Main.class` |
| **Classpath** | List of directories or JARs used to locate classes and classpath resources | `java -cp 'out:resources' demo.app.Main` on Linux/macOS |

Using `javac -d out` does **not** make the program automatically run from `out`, nor does it automatically add `out` to the classpath of another `java` command. Using `java -cp ...` does **not** change the working directory to any directory listed.

~~~mermaid
flowchart TD
    A["src/main/java: source code"] --> B["javac -d out"]
    B --> C["out: .class bytecode"]
    C --> D["Classpath: out + resources"]
    R["resources: files inside classpath"] --> D
    D --> J["JVM: loads classes, resources"]
    W["Working directory: path-lab"] --> F["data/customer.txt: relative file"]
    J --> F
    J --> O["Execution result"]
~~~

**Memory tip:** `-d` answers “where does the compiler **write**?”, `-cp` answers “where do the JVM/compiler **look for classes**?”, and CWD answers “where do **relative** file paths start from?”.

## 2. Sample project and directory tree

Let's create a `path-lab` directory containing Java 11+ code without external dependencies:

~~~text
path-lab/
├── src/
│   └── main/
│       └── java/
│           └── demo/
│               ├── app/
│               │   └── Main.java
│               └── lib/
│                   └── GreetingFormatter.java
├── data/
│   └── customer.txt
└── resources/
    └── messages/
        └── greeting.txt
~~~

Upon compilation, the program will additionally use the `out` directory. The `src/main/java` tree is an **organizational convention**; it is the `package` keyword in each file that determines the fully qualified class name and how Java organizes output under `-d`.

Two text files to create first:

**`data/customer.txt`**

~~~text
Lan
~~~

**`resources/messages/greeting.txt`**

~~~text
Xin chào
~~~

Save with UTF-8. Both are text files, yet **how the program finds them differs**: `customer.txt` relies on the working directory, while `greeting.txt` will be looked up via the classpath.

## 3. Writing Java code for the project

### 3.1. GreetingFormatter.java

File `src/main/java/demo/lib/GreetingFormatter.java`:

~~~java
package demo.lib;

public final class GreetingFormatter {
    private GreetingFormatter() { }

    public static String format(String greeting, String customer) {
        if (greeting == null || greeting.isBlank()
                || customer == null || customer.isBlank()) {
            throw new IllegalArgumentException("Missing text");
        }
        return greeting + ", " + customer + "!";
    }
}
~~~

The class has the fully qualified name `demo.lib.GreetingFormatter`. `package demo.lib;` is not part of the Java command's directory path; the JVM will use the package name to locate the class file beneath each **classpath root**.

### 3.2. Main.java

File `src/main/java/demo/app/Main.java`:

~~~java
package demo.app;

import demo.lib.GreetingFormatter;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class Main {
    private static String readGreeting() throws IOException {
        try (InputStream in =
                Main.class.getResourceAsStream("/messages/greeting.txt")) {
            if (in == null) {
                throw new IllegalStateException(
                        "Missing classpath resource: /messages/greeting.txt");
            }
            return new String(
                    in.readAllBytes(), StandardCharsets.UTF_8).strip();
        }
    }

    public static void main(String[] args) throws IOException {
        Path workingDir = Path.of("").toAbsolutePath().normalize();
        System.out.println("Working directory: " + workingDir);

        // External file: relative to working directory.
        Path customerFile = Path.of("data", "customer.txt");
        String customer = Files.readString(
                customerFile, StandardCharsets.UTF_8).strip();

        // Resource: looked up via classpath, not CWD.
        String greeting = readGreeting();
        System.out.println("Customer file: "
                + customerFile.toAbsolutePath().normalize());
        System.out.println(GreetingFormatter.format(greeting, customer));
    }
}
~~~

Read the differences carefully:

- `Files.readString(Path.of("data", "customer.txt"), UTF_8)` opens the file relative to the working directory. If the file does not exist yet, Java may throw `NoSuchFileException`.
- `Main.class.getResourceAsStream("/messages/greeting.txt")` looks up the resource from the **resource lookup root** for this class. In this **traditional classpath** example, that is the `resources` entry or a resource packaged in a JAR. When not found, the API returns `null` and the program explicitly throws `IllegalStateException`.
- `import demo.lib.GreetingFormatter;` means the program uses another class; this class must be available at compile time and when the runtime loads it.

`Main.java` uses `Path.of`, `Files.readString`, `String.strip`, and `InputStream.readAllBytes`, so it requires **Java 11 or higher**. This is a simplified **console** project for observing paths, not a complete Maven/Gradle configuration.

## 4. Compiling and running with Bash on macOS/Linux

From the **parent directory** of `path-lab`:

~~~bash
cd path-lab
mkdir -p out

javac -encoding UTF-8 -d out \
  src/main/java/demo/lib/GreetingFormatter.java \
  src/main/java/demo/app/Main.java

java -cp 'out:resources' demo.app.Main
~~~

`mkdir -p out` creates the root directory for output. When using `javac -d out`, create `out` beforehand; the compiler will create the package subdirectories inside it. After successful compilation, you will have:

~~~text
out/
└── demo/
    ├── app/
    │   └── Main.class
    └── lib/
        └── GreetingFormatter.class
~~~

`-cp 'out:resources'` provides **two** classpath entries: `out` to find the two classes and `resources` to find `messages/greeting.txt`. A **colon** is the classpath separator on macOS/Linux.

Example output:

~~~text
Working directory: <absolute path to path-lab>
Customer file: <absolute path to path-lab/data/customer.txt>
Xin chào, Lan!
~~~

The two paths depend on the actual location on your machine; the last line must be `Xin chào, Lan!`.

**Do not run `java Main`** when the class has `package demo.app;`. The class name to run is `demo.app.Main`, without `.java` or `.class`.

## 5. Compiling and running on Windows PowerShell

From the parent directory of `path-lab`:

~~~powershell
Set-Location path-lab
New-Item -ItemType Directory -Force -Path out | Out-Null
javac -encoding UTF-8 -d out src/main/java/demo/lib/GreetingFormatter.java src/main/java/demo/app/Main.java
java -cp 'out;resources' demo.app.Main
~~~

The difference: **Windows uses a semicolon** to separate classpath entries, hence `out;resources`, not `out:resources`. In PowerShell, wrap the entire classpath string in single quotes so the shell passes it intact as **a single argument**.

You can use forward slashes in paths passed to Java tools on Windows as in the example, or use the corresponding Windows path style. Avoid confusing the **OS path separator** with the **separator between multiple classpath elements**.

If a directory contains spaces such as `C:\Java Projects\path-lab`, you must quote source/destination paths containing spaces. For example, `java -cp 'C:\Java Projects\path-lab\out;C:\Java Projects\path-lab\resources' demo.app.Main` is a Windows classpath with two entries; even when using absolute paths, the working directory **still does not change automatically**.

## 6. Experiment: is the error in the classpath or the working directory?

### Case A: classes are present, but resource is missing

From the exact `path-lab` directory, run:

~~~bash
java -cp out demo.app.Main
~~~

- Java loads `Main.class` and `GreetingFormatter.class` in `out` successfully.
- `data/customer.txt` can still be read because the working directory is right.
- However, `messages/greeting.txt` is not inside `out`, so `getResourceAsStream` returns `null` and the program reports a missing classpath resource.

**Fix:** add `resources` to `-cp`, or package the resource into a JAR at the right path. Do not merely change CWD hoping the JVM will find classpath resources automatically.

### Case B: resource is present, but class is missing

~~~bash
java -cp resources demo.app.Main
~~~

The JVM only searches inside `resources` and does not find `demo/app/Main.class`. The program fails at the **main class loading** step, before running the file-reading logic. Add `out` to the classpath so the JVM can find the classes.

### Case C: classpath is right, but CWD is wrong

Suppose you are in the **parent** directory of `path-lab`. If you pass a valid classpath from there, for instance on macOS/Linux:

~~~bash
java -cp 'path-lab/out:path-lab/resources' demo.app.Main
~~~

The JVM can locate both the classes and the resource. However, `Path.of("data", "customer.txt")` now points to `data/customer.txt` **under the parent directory**, not `path-lab/data/customer.txt`. The program will report a missing file if that file does not exist at the location being searched.

There are two sensible solutions: **run from the right working directory** or **pass the configuration file path explicitly** (absolute or relative, handled by contract). Do not hardcode an absolute path to one developer's machine into shared source code.

## 7. Classpath root and package structure

The class in the example declares:

~~~java
package demo.app;

public final class Main {
    public static void main(String[] args) { }
}
~~~

When output is placed in `out`, bytecode lives at `out/demo/app/Main.class`. Therefore:

| Command | Evaluation | Reason |
| --- | --- | --- |
| `java -cp out demo.app.Main` | Finds main class | Classpath root is `out`; Java maps `demo.app.Main` to `demo/app/Main.class` |
| `java -cp out/demo/app Main` | Wrong for the example class | `Main` is not in the default package; in bytecode the class name is still `demo.app.Main` |
| `java -cp resources demo.app.Main` | Missing classpath for code | `resources` does not contain the main class bytecode |

The **package** name is determined by the `package` declaration, not automatically generated from the terminal's current directory. Place source files following the package tree because it keeps code and build tools clear; `javac -d` places output according to the package name.

## 8. How does `javac -cp` differ from `java -cp`?

Both are options for setting the class lookup path, but the **timing** differs:

- `javac -cp ...` tells the **compiler** where to find already-compiled classes or JARs needed to resolve imports/types.
- `java -cp ...` tells the **runtime** where to find the main class, dependent classes, and classpath resources.

In the initial example, we passed **both source files** to `javac` at once so the compiler could compile them together. If compiling each file separately:

~~~bash
# Run from path-lab, after out already exists.
javac -encoding UTF-8 -d out src/main/java/demo/lib/GreetingFormatter.java
javac -encoding UTF-8 -cp out -d out src/main/java/demo/app/Main.java
~~~

The second compilation pass needs to see `GreetingFormatter.class` inside `out`. Yet after building, the run command still needs **both `out` and `resources`** for the program to work properly.

If there is an external library `lib/helper.jar`, in a real project, both compiler and runtime may need that JAR added to the classpath:

~~~bash
# Syntax illustration on macOS/Linux; replace source and class names for a real project.
javac -cp 'lib/helper.jar' -d out YourFile.java
java -cp 'out:resources:lib/helper.jar' your.package.Main
~~~

On Windows, use `;` instead of `:` when separating multiple classpath elements. This line is **not a run command for the sample project** because the sample project has no `lib/helper.jar` or `YourFile.java`.

When specifying `-cp` explicitly, do not assume Java will automatically include `out`, `resources`, all existing JARs, or the current directory. `CLASSPATH` is an optional environment variable, but configuring with `-cp` is usually clearer per command.

## 9. Packaging classes and resources into a JAR

After compiling, create a JAR with an entry point and resources:

**Bash (macOS/Linux):**

~~~bash
jar --create --file demo.jar \
  --main-class demo.app.Main \
  -C out . -C resources .
java -jar demo.jar
~~~

**PowerShell (Windows):**

~~~powershell
jar --create --file demo.jar --main-class demo.app.Main -C out . -C resources .
java -jar demo.jar
~~~

The `-C out .` option places the class files inside `out` at the root of the JAR, preserving the package tree. The `-C resources .` option places `messages/greeting.txt` at the right path inside the JAR. `--main-class demo.app.Main` writes the main class info into the JAR's manifest.

When running `java -jar`, the JVM uses the main class from the manifest. **Do not assume** placing `-cp` alongside `-jar` will automatically add external libraries to the class lookup path; applications with multiple dependencies must package or declare them appropriately.

**Key takeaway:** `data/customer.txt` **remains an external file**. Running `java -jar demo.jar` from `path-lab` can still read that file; running the JAR from another working directory may fail to read it, even though the classes and greeting resource are already inside the JAR.

## 10. Common error diagnosis table

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| `javac -d out` cannot write classes | `out` does not exist yet or lacks write permissions | Create `out` first, check permissions |
| `Could not find or load main class` | `-cp` missing output root or wrong package name | Check `out/demo/app/Main.class` and run `demo.app.Main` |
| `NoClassDefFoundError` | Missing dependent class at runtime, or another loading/initialization error | Check classpath, dependencies, and the `Caused by` section |
| `package demo.lib does not exist` when compiling | Compiler cannot see internal library source or classes | Compile both sources or add `-cp out` on the second pass |
| `NoSuchFileException: data/customer.txt` | Wrong working directory or file does not exist yet | Check CWD and actual path, not just classpath |
| `Missing classpath resource` | Missing `resources` on classpath/JAR, wrong resource name | Check classpath root and `messages/greeting.txt` |
| Works in IDE but fails in terminal | IDE sets a different working directory, output, or classpath | Inspect Run Configuration and compare the three values |
| `UnsupportedClassVersionError` | Bytecode built for newer Java than runtime supports | Check build JDK, runtime, and appropriate target |

**Distinguish errors across three layers:** `javac` not finding a type is a **compile-time** error; `java` not finding the main class is a **program loading** error; `Files.readString` failing to open a file is a **runtime I/O** error. These three errors require three different checks.

### Notable edge cases

- **Spaces in paths:** quote classpath and path arguments. In Bash, `;` has special meaning to the shell.
- **Case sensitivity:** operating systems may have different case-sensitivity rules; `Main.class`, package, and resource names must match accurately.
- **Relative paths in an IDE:** an IDE may default the working directory to the project root, module root, or another configured directory. Do not assume it matches the terminal.
- **Runtime directory vs. JDK directory:** `JAVA_HOME`, `java.home`, CWD, and classpath are independent concepts.
- **Classpath vs. module path:** this lesson uses the classpath and a project **without `module-info.java`**. Applications using the Java Platform Module System have their own module path loading rules.

## 11. Quick checklist when the project does not run

1. **Check CWD:** Bash uses `pwd`, PowerShell uses `Get-Location`. When Java runs, the program can print `Path.of("").toAbsolutePath()` to aid diagnosis.
2. **Check bytecode output:** are `.class` files under the directory passed to `-d`, and is the package tree right?
3. **Check runtime classpath:** does the first entry contain the package root of the main class? Have needed resources/JARs been added?
4. **Check data files:** does `data/customer.txt` exist **relative to CWD**?
5. **Read the entire error message:** compile errors, class-loading errors, and file-opening errors are three different layers.
6. **Change one factor per attempt:** do not change classpath, CWD, and package simultaneously and guess the cause.

## 12. Exercises with guided answers

**Exercise 1 — Classes present but resource missing.** Predict what happens when running `java -cp out demo.app.Main` from `path-lab`.

*Hint:* It loads the `.class` files and reads `data/customer.txt`, but lacks `resources` to find `/messages/greeting.txt`.

**Exercise 2 — Classpath right but file not found.** Run from the parent directory with `-cp 'path-lab/out:path-lab/resources'` on macOS/Linux. Why might `Files.readString` fail?

*Hint:* CWD is the parent directory; the relative path points to `data` under the parent directory, not under `path-lab`.

**Exercise 3 — Try two-pass compilation.** Compile `GreetingFormatter.java` first, then `Main.java`. Which option must be added on the second pass for the compiler to find the already generated class?

*Hint:* Use `javac -cp out -d out ...`.

**Exercise 4 — JAR packaging.** Create `demo.jar` containing both classes and `messages/greeting.txt`. Run from the project root and from another directory. Which parts are inside the JAR, and which part still depends on CWD?

**Exercise 5 — Design improvement.** Have the program accept the `customer.txt` path via `args[0]` instead of hardcoding `data/customer.txt`. Check missing-argument, missing-file, and relative-path cases. Discuss when an absolute path should be used.

### Self-assessment

You understand this lesson when you can answer on your own: where `javac -d` creates `.class`; where `java -cp` looks up `demo.app.Main` and resources; which directory `Path.of("data","customer.txt")` depends on; why Java packages require an FQCN when running; and why packaging a JAR **does not automatically turn an external file into an internal JAR resource**.
