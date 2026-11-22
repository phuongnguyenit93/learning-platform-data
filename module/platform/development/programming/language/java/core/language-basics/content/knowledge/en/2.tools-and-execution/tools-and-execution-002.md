# Creating a Source File and Compiling with javac

For a computer to execute a Java program, you first need to write **source code** in a file with the `.java` extension, then use the JDK's **`javac` compiler** to generate **bytecode** in a `.class` file. After that, the `java` command starts the JVM to run the class that has a `main` method.

This lesson guides you through the workflow from scratch using **JDK 17 or higher**, with a Windows PowerShell or Linux terminal. No IDE, Maven, Gradle, or external libraries are needed.

## 1. Distinguishing three easily confused things

| Component | What is it for? | Example |
| --- | --- | --- |
| `.java` source file | Contains the code written by the programmer | `HelloCompiler.java` |
| `javac` command | Parses code, checks for many errors, and generates bytecode | `javac HelloCompiler.java` |
| `.class` file | Compilation output for the JVM | `HelloCompiler.class` |
| `java` command | Runs the class via the JVM; in this example invokes `main` | `java HelloCompiler` |
| JDK | Java Development Kit, including `javac` and tools to run Java | JDK 17+ |

**`javac` does not run the program.** A successful compilation also does not prove an algorithm is correct for all inputs. It mainly confirms that the code satisfies the syntax, type, and semantic rules that the compiler can check.

General workflow:

~~~text
Source code HelloCompiler.java
         |
         | javac -encoding UTF-8 -d out src/HelloCompiler.java
         v
Bytecode out/HelloCompiler.class
         |
         | java -cp out HelloCompiler
         v
JVM executes -> Output in terminal
~~~

## 2. Checking the JDK before writing code

Open **PowerShell** on Windows or a **terminal** on Linux, and run:

~~~bash
java -version
javac -version
~~~

Example output for JDK 17 might look like:

~~~text
openjdk version "17.0.x" ...
javac 17.0.x
~~~

The `x` represents the patch number; actual output varies by JDK distribution. What needs to be confirmed is that **both `java` and `javac` can be invoked** and their versions meet the requirement.

If you see a message that `javac` is not recognized:

- Check that a **JDK** is installed, rather than only a Java runtime.
- Check that the `PATH` environment variable includes the `bin` directory of the appropriate JDK.
- Open a new terminal after changing environment settings.
- Check whether `java` and `javac` are pointing to two different JDKs.

On Windows PowerShell, you can view command paths with `Get-Command java, javac`; on Linux, use `command -v java` and `command -v javac`. These are environment inspection commands, not compilation commands.

## 3. Creating a simple project directory

Choose a directory as a practice space, for example `java-compile-demo`, then open a terminal **directly inside this directory**. Desired structure:

~~~text
java-compile-demo/
├── src/
│   └── HelloCompiler.java
└── out/                 (contains .class after compilation)
~~~

Create the directories:

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force -Path src, out | Out-Null
~~~

**Linux (Bash):**

~~~bash
mkdir -p src out
~~~

Use a text editor to create the file **`src/HelloCompiler.java`**. Save it as **UTF-8**, choosing the exact `.java` extension; avoid accidentally saving it as `HelloCompiler.java.txt` on Windows.

## 4. Writing the first Java program

Complete contents of `src/HelloCompiler.java`:

~~~java
public class HelloCompiler {
    public static void main(String[] args) {
        String visitor = args.length > 0 ? args[0] : "ban";
        System.out.println("Xin chao, " + visitor + "!");
    }
}
~~~

Components to understand:

- `public class HelloCompiler` declares a public class. The file containing this public class must be named `HelloCompiler.java` (matching uppercase/lowercase exactly).
- Curly braces `{ }` mark class blocks and method blocks.
- `public static void main(String[] args)` is the starting point when running a Java program in the way shown in this lesson.
- `args` is the array of arguments you pass after the class name when running.
- The ternary operator `?:` picks the first argument if present; otherwise it uses the default string `"ban"`.
- `System.out.println(...)` prints a line to the terminal.
- The semicolon `;` terminates the corresponding Java statements.

There is no need to write `package` for this first example: the class resides in the **unnamed package** to keep compile and run commands simple.

## 5. Compiling from source code into bytecode

From the `java-compile-demo` directory, run **the same command** in PowerShell or Bash:

~~~bash
javac -encoding UTF-8 -d out src/HelloCompiler.java
~~~

Meaning of the arguments:

| Component | Meaning |
| --- | --- |
| `javac` | Invokes the Java compiler |
| `-encoding UTF-8` | Specifies how to read source code characters |
| `-d out` | Sets the root directory to store generated `.class` files |
| `src/HelloCompiler.java` | Path of the source file to compile |

If successful, `javac` usually **prints no message**. Check the `out` directory: you will see `HelloCompiler.class`.

Note: because the command specified `-d out`, the `out` directory must exist before running. For code **without a package**, the output file is placed directly inside `out`. There is no need to manually move `.class` files.

### Running the compiled result

~~~bash
java -cp out HelloCompiler
~~~

Output:

~~~text
Xin chao, ban!
~~~

Try passing a name:

~~~bash
java -cp out HelloCompiler Minh
~~~

Output:

~~~text
Xin chao, Minh!
~~~

Explanation:

- `-cp out` (written in full as `-classpath out`) tells the JVM where to look for the program's classes.
- `HelloCompiler` is the **class name**, not the file name `HelloCompiler.java` or `HelloCompiler.class`.
- `Minh` is a command-line argument, appearing in `args[0]`.

Using `/` in the paths in the examples above works for these Java commands on both Windows and Linux. If an actual path contains spaces, enclose the **entire path** in double quotes.

## 6. Editing code, recompiling, and running again

Try changing the line:

~~~java
System.out.println("Xin chao, " + visitor + "!");
~~~

to:

~~~java
System.out.println("Chuc ban hoc Java tot, " + visitor + "!");
~~~

After **saving the source file**, run again:

~~~bash
javac -encoding UTF-8 -d out src/HelloCompiler.java
java -cp out HelloCompiler Minh
~~~

New output:

~~~text
Chuc ban hoc Java tot, Minh!
~~~

Only editing `.java` and re-running `java` **without recompiling** can cause you to see **stale bytecode** in `.class`. Especially if a new compilation fails while the old `.class` file still remains, the JVM can still run the old class. Therefore, when testing code edits, read the compilation result before trusting that the new version ran.

## 7. When a program has a `package`

The `package` keyword defines a class's namespace. This next example is independent of `HelloCompiler`.

Create the `src/tutorial` directory:

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force -Path src/tutorial | Out-Null
~~~

**Linux:**

~~~bash
mkdir -p src/tutorial
~~~

Save the following code to **`src/tutorial/PackageHello.java`**:

~~~java
package tutorial;

public class PackageHello {
    public static void main(String[] args) {
        System.out.println("Package works");
    }
}
~~~

Compile:

~~~bash
javac -encoding UTF-8 -d out src/tutorial/PackageHello.java
~~~

Because the class declares `package tutorial;`, the compiler creates the file:

~~~text
out/
└── tutorial/
    └── PackageHello.class
~~~

Run with the **full class name including the package**:

~~~bash
java -cp out tutorial.PackageHello
~~~

Output:

~~~text
Package works
~~~

Do not run with `java -cp out PackageHello` because this class does not belong to the unnamed package. When using `-d out`, `javac` organizes output by package; `java` needs to find the class by its qualified name.

**Distinction:** the `src/tutorial` folder is where the source file is organized by good convention; the `package tutorial;` declaration inside the code is what defines the Java package. In a small project, let the directory structure mirror the package for clarity and ease of building.

## 8. Some common compilation errors

You can try each of the following errors, **fixing only one place each time** and then recompiling.

| Situation | Common symptom | How to fix |
| --- | --- | --- |
| Saved file as `HelloCompiler.java.txt` | `.java` file not found | Show file extensions and rename properly |
| Wrote `public class HelloCompilor` in `HelloCompiler.java` | Public class name does not match file error | Rename the class or file to match |
| Missing `;` or `}` | `';' expected` or syntax error | Check statements and braces |
| Assigning `int count = "3";` | `incompatible types` | Fix the type or parse the string properly |
| Running `javac` in the wrong directory | `file not found` | Check current working directory and source path |
| Running `java HelloCompiler.class` | Could not find suitable class | Use class name `HelloCompiler`, omit file extension |
| Forgot `-cp out` when `-d out` was used | JVM cannot find class | Add `-cp out` |
| Has `package tutorial;` but run with short name | Main class not found | Run `tutorial.PackageHello` |
| `java` is older than the version used to compile | `UnsupportedClassVersionError` at runtime | Use a compatible runtime or compile for the target version |

Messages may differ depending on the JDK version and operating system. What matters is **categorizing the cause**: class name, directory, syntax, data type, package, or version.

### Trying an intentional compiler error yourself

In `HelloCompiler.java`, add the following line **inside `main`**:

~~~java
int hours = "two"; // Error: String cannot be assigned to int.
~~~

Run `javac -encoding UTF-8 -d out src/HelloCompiler.java`, and you will get a data type error. Fix it to:

~~~java
int hours = 2;
~~~

Then recompile. This illustrates that `javac` can reject code **before the program runs**.

## 9. Useful `javac` options once the basics work

| Command or option | When is it useful? |
| --- | --- |
| `javac -version` | Verify compiler version |
| `javac -encoding UTF-8 ...` | Specify source input encoding |
| `javac -d out ...` | Separate `.class` files from the source directory |
| `javac -Xlint:all ...` | Display additional compiler warnings (depending on code) |
| `javac --release 17 ...` | When using a newer JDK to target Java 17 APIs/language |
| `javac -cp libs/something.jar ...` | When actually needing to compile with an external library; path is just an example |

Example of compiling targeting Java 17 when using a JDK that supports this option:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/HelloCompiler.java
~~~

`--release 17` constrains the language level and Java platform APIs corresponding to the supported release. However, it does not automatically guarantee that **every third-party library** or your runtime configuration is compatible; dependencies must be checked separately.

There is no need to add complex arguments when the problem only has a single source file.

## 10. Practice exercises

**Exercise 1 — Compile without an IDE.** Create a new directory, save `src/HelloCompiler.java` with the exact name, then run `javac` and `java`. Record the name of the created `.class` file. Explain why the run step does not use `.java` as the class argument.

**Exercise 2 — Passing arguments.** Run `java -cp out HelloCompiler Lan`. Predict the exact single line of output before running. Try omitting the argument and explain the `args.length > 0` branch.

**Exercise 3 — Finding errors.** Rename the class to `HelloCompilor` while keeping the file name unchanged. Predict at which step `javac` reports an error and the minimal fix. After the exercise, restore the correct name.

**Exercise 4 — Package.** Compile `src/tutorial/PackageHello.java` and explain why the output lands in `out/tutorial/`. Compare `java -cp out PackageHello` with `java -cp out tutorial.PackageHello`.

**Exercise 5 — Running after editing source.** Change the printed sentence to the terminal, run the program, and intentionally skip the `javac` step. Describe why the output may still be the old sentence. Then recompile and compare.

### Checklist before moving to the next Java lesson

- [ ] Installed JDK and can invoke both `java` and `javac`.
- [ ] Created a `.java` source file with UTF-8.
- [ ] Understand the relationship between file name and `public` class name.
- [ ] Compiled with `javac -encoding UTF-8 -d out ...`.
- [ ] Run with `java -cp out TenLop`.
- [ ] Correctly explain `package` and full class name when a package is present.
- [ ] Distinguish compile-time errors, runtime errors, and running a stale `.class` file.
- [ ] Fixed at least one `javac` error yourself, then recompiled and ran successfully.

## Remember

**`.java` is source code, `javac` compiles source code into `.class`, and `java` starts the JVM to run the compiled class.** Once comfortable with the **create file → compile → fix errors → run → verify output** workflow, you can learn Java syntax without depending on an IDE's Run button.
