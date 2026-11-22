# Distinguishing JVM Options from Program Arguments in Java

When running Java from the terminal, you might see a command like this:

~~~bash
java -Xmx128m -Dstudy.mode=lab -cp out ArgsBoundaryDemo 45 "Java core" --check
~~~

Here, `-Xmx128m` and `-Dstudy.mode=lab` are options configuring the Java execution environment. `-cp out` tells the **Java launcher** where to look for classes. Meanwhile, `45`, `Java core`, and `--check` are **program arguments**; they are passed to `main(String[] args)`.

This lesson helps you recognize **the boundary between Java runtime configuration and data received by the application**. The examples use **JDK 17 or higher**, requiring only a Windows PowerShell or Linux terminal and a single Java source file.

## 1. Reading the command structure from left to right

In the form that runs a compiled class, the command usually has the structure:

~~~text
java [launcher/JVM options] ClassName [program arguments]
        ^                       ^              ^
  configuration            entry point       args[]
~~~

In the example:

~~~text
java -Xmx128m -Dstudy.mode=lab -cp out ArgsBoundaryDemo 45 "Java core" --check
     └─────────── options ───────────┘ └──── class ───┘ └────── args[] ──────┘
~~~

Some documentation broadly refers to everything before the class name as **“JVM arguments”**. That phrasing is convenient in conversation, yet it is better to distinguish accurately:

| Component | Who handles it? | Effect | Appears in `args[]`? |
| --- | --- | --- | --- |
| `-Xmx128m` | JVM/Java launcher | Configures maximum heap limit | No |
| `-Xms64m` | JVM/Java launcher | Configures initial heap size | No |
| `-Dstudy.mode=lab` | JVM/Java launcher | Sets a Java system property | No |
| `-ea` | JVM/Java launcher | Enables `assert` checks | No |
| `-cp out` | Java launcher | Selects classpath to find classes/libraries | No |
| `ArgsBoundaryDemo` | Java launcher | Selects the class containing the `main` entry point | No |
| `45` | Application | First argument string | Yes: `args[0]` |
| `"Java core"` | Shell then application | A single string containing a space | Yes: `args[1]` |
| `--check` | Application | Flag defined by the application | Yes: `args[2]` |

`-cp` is a **launcher option**, not a JVM memory limit setting. And `-D` creates a **system property**, not an operating system environment variable.

**Practical rule:** Java options such as `-Xmx`, `-D`, and `-cp` must be placed before the class name in this execution form; everything after the class name is treated as application data.

## 2. Creating a demo program to inspect `args[]`

Create the file **`ArgsBoundaryDemo.java`** containing the following Java code:

~~~java
public class ArgsBoundaryDemo {
    public static void main(String[] args) {
        String mode = System.getProperty("study.mode", "default");

        System.out.println("study.mode=" + mode);
        System.out.println("args.length=" + args.length);

        for (int i = 0; i < args.length; i++) {
            System.out.println("args[" + i + "]=" + args[i]);
        }

        if (args.length > 0) {
            try {
                int minutes = Integer.parseInt(args[0]);
                if (minutes < 0) {
                    System.out.println("minutes=INVALID_NEGATIVE");
                } else {
                    System.out.println("minutes=" + minutes);
                }
            } catch (NumberFormatException ex) {
                System.out.println("minutes=INVALID_NUMBER");
            }
        }
    }
}
~~~

Meaning:

- `main(String[] args)` receives an **array of strings**. Even when you type `45`, in `args[0]` it is initially the `String` `"45"`, not an `int`.
- `System.getProperty("study.mode", "default")` reads the configured system property; if the property is not set, it uses the default string `default`.
- The `for` loop prints **each exact string** received along with its index.
- `Integer.parseInt` illustrates that the application parses arguments itself. The Java launcher does not automatically convert application arguments into numbers.
- Negative values and non-numeric strings are handled explicitly; those are **application rules**, not rules of `-Xmx` or `-D`.

This is a standalone Java program, requiring no external libraries, frameworks, or special configuration files.

## 3. Compiling and running on Windows PowerShell or Linux

First check the JDK:

~~~bash
java -version
javac -version
~~~

Save `ArgsBoundaryDemo.java` in a working directory, and open a terminal in that directory.

**Create the output directory on Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force -Path out | Out-Null
~~~

**Create the output directory on Linux/Bash:**

~~~bash
mkdir -p out
~~~

Compile — the command is identical on both operating systems:

~~~bash
javac -encoding UTF-8 -d out ArgsBoundaryDemo.java
~~~

Then run:

~~~bash
java -Xmx128m -Dstudy.mode=lab -cp out ArgsBoundaryDemo 45 "Java core" --check
~~~

**Expected output:**

~~~text
study.mode=lab
args.length=3
args[0]=45
args[1]=Java core
args[2]=--check
minutes=45
~~~

**Why?**

1. The Java launcher accepts `-Xmx128m` to request a maximum heap configuration; this option **does not go into `args[]`**.
2. `-Dstudy.mode=lab` creates the property `study.mode` with value `lab`. The code reads it via `System.getProperty`.
3. `-cp out` points to the directory containing the compiled `ArgsBoundaryDemo` class.
4. `ArgsBoundaryDemo` identifies the class to run.
5. The remaining three strings go into `args[0]`, `args[1]`, and `args[2]`. The quotes around `"Java core"` are used by the **shell** to keep two words as **one argument**, not characters inside the received string content.

Do not rely on actual heap memory figures to verify this example: `-Xmx128m` sets a limit configuration, and does not guarantee the JVM allocates or uses exactly 128 MiB immediately upon launch.

## 4. Placing `-D` in the wrong position: output changes noticeably

Compare two commands containing the exact same text `-Dstudy.mode=lab`:

**Placed before the class name — this is a Java option:**

~~~bash
java -Dstudy.mode=lab -cp out ArgsBoundaryDemo 45
~~~

~~~text
study.mode=lab
args.length=1
args[0]=45
minutes=45
~~~

**Placed after the class name — this is a program argument:**

~~~bash
java -cp out ArgsBoundaryDemo 45 -Dstudy.mode=lab
~~~

~~~text
study.mode=default
args.length=2
args[0]=45
args[1]=-Dstudy.mode=lab
minutes=45
~~~

The second command **does not set the system property** `study.mode`. The string starting with `-D` is merely an element in `args[]`, and because the example application does not parse that string itself, it does not change how the program runs.

Similarly, running:

~~~bash
java -cp out ArgsBoundaryDemo 45 -Xmx128m
~~~

passes the string `-Xmx128m` into application arguments, **without setting a heap limit via that string**. The effect of the `-` character depends on **which parser is reading it**.

This is a common cause of issues like “I added `-D` yet the application still reads the default property.”

## 5. Application arguments do not carry inherent meaning

Java only forwards the strings after the class name to `main`. The program must **decide for itself** what they represent.

Suppose another application specifies:

~~~text
java App 15 --verbose --output=result.txt
~~~

`15` could be a quantity, minutes, or an arbitrary code; `--verbose` could enable logging; `--output=result.txt` could choose a file name. **Those are `App`'s own conventions**, not a standard set of options handled by the JVM.

In `ArgsBoundaryDemo`:

- `45` is interpreted as minutes only because the code explicitly calls `Integer.parseInt(args[0])`.
- `--check` is printed out yet does nothing else because the code has no condition handling it.
- With no arguments, `args.length = 0`; the loop prints no elements, and the parsing block is skipped.
- When `args[0]` is `abc` or a number outside the `int` range, `parseInt` fails; the program prints `minutes=INVALID_NUMBER`.
- When `args[0] = -5`, parsing succeeds yet the application reports `minutes=INVALID_NEGATIVE`.

A parse error and negative data are two different situations: one is a **malformed number format**, and the other is **valid format that violates requirements**.

## 6. How do `-D`, environment variables, and classpath differ?

A system often has **Java system properties**, **environment variables**, and **program arguments**. They do not substitute for one another.

| Mechanism | How it is set / passed | How Java reads it | Characteristics |
| --- | --- | --- | --- |
| System property | `java -Dstudy.mode=lab ...` | `System.getProperty("study.mode")` | Belongs to the JVM process's properties system |
| Environment variable | Set by shell/OS before running | `System.getenv("STUDY_MODE")` | Inherited by the process from the environment |
| Program argument | After the class name | `args[0]`, `args[1]`... | String array received by the application |
| Classpath | `java -cp out ...` | Used by launcher/loader | Specifies where to locate classes and libraries |

Example of setting an **environment variable** only in the current terminal session:

**PowerShell:**

~~~powershell
$env:STUDY_MODE = "lab"
~~~

**Bash/Linux:**

~~~bash
export STUDY_MODE=lab
~~~

If you want to test directly in code, add this call to `main`:

~~~java
System.out.println(
        "env.STUDY_MODE=" + System.getenv("STUDY_MODE"));
~~~

This is an **optional addition**, not included in the standard output in section 3. Setting the `STUDY_MODE` environment variable does not automatically create the Java system property `study.mode`; if you want to support both, the application must explicitly define precedence rules.

Note: a multi-entry classpath uses **`;` on Windows** and **`:` on Linux/macOS** as the separator. The example in this lesson has only one directory `out`, so the same `-cp out` command works on both platforms.

## 7. Other launch modes still share a similar boundary

### Running an executable JAR

If you already have a valid JAR file containing a `Main-Class` configuration, the typical syntax is:

~~~bash
java -Xmx256m -Dstudy.mode=prod -jar app.jar 45 --check
~~~

- `-Xmx256m` and `-Dstudy.mode=prod`: JVM options.
- `-jar app.jar`: the Java launcher selects the JAR and the main class configured in the manifest.
- `45`, `--check`: application arguments passed to `main`.

This is only a **syntax example**: this lesson does not build `app.jar`, so do not run that command without a corresponding JAR. The JAR name is not passed as `args[0]`.

### Running a source file directly on JDK 17+

Java also supports source-file execution mode:

~~~bash
java -Xmx128m -Dstudy.mode=lab ArgsBoundaryDemo.java 45 "Java core" --check
~~~

In this mode, `java` compiles the source code in memory and then runs it; no separate `javac` command is needed. JVM options still go **before the source file**; application data still goes **after the source file**.

The command above assumes you are in the directory containing `ArgsBoundaryDemo.java`. If you specify another path, replace the file name with the actual path.

## 8. Handling common errors

| Symptom | Possible cause | How to check/fix |
| --- | --- | --- |
| `System.getProperty` returns `default` despite typing `-D` | Placed `-D` after class name, wrong key, or not configured | Move `-Dkey=value` before the class name, check spelling |
| `args.length` differs from expected count | Counted the class name or mis-split a string with spaces | Count only strings after the class name; wrap strings with spaces in double quotes |
| `-Xmx...` appears inside `args[]` | Placed the option in the application arguments position | Move it before the class name or file/JAR name |
| JVM reports unrecognized option | Typo in flag or unsupported JDK version | Check `java -version` and `java --help` |
| Main class not found | Missing `-cp out`, wrong classpath, or not yet compiled | Check `.class` files and verify class name |
| `NumberFormatException` | Parsed argument is not a valid `int` | Check the string, numeric range, and message |
| Heap runs out of memory | Data or allocation behavior exceeds JVM capacity | Measure/investigate memory usage, do not just arbitrarily raise `-Xmx` |

To see more launcher options:

~~~bash
java --help
java -X
~~~

Some advanced JVM options take the form `-XX:...`; syntax and support depend on the JVM version/implementation. Do not copy advanced options from another environment without understanding their effect.

### Do not confuse Java errors with shell errors

Before the Java launcher reads arguments, the **shell** has already processed quotes, spaces, environment variables, and certain special characters. PowerShell and Bash do not have identical rules. For example, quoting an argument with spaces using `"Java core"` works in both, yet escaping nested quotes differs.

When diagnosing, start with a simple example and print `args.length` along with each `args[i]` as in the program above. Do not rush to conclude the JVM dropped a string if the shell split it differently from what you expected.

## 9. Self-check exercises

**Exercise 1 — Predict output.** With:

~~~bash
java -Dstudy.mode=study -cp out ArgsBoundaryDemo 20 "bai mot"
~~~

Predict the property, argument count, and value of each argument.

*Answer:* property `study`, `args.length=2`, `args[0]=20`, `args[1]=bai mot`, `minutes=20`.

**Exercise 2 — Spot misplacement.**

~~~bash
java -cp out ArgsBoundaryDemo -Xmx256m 20
~~~

Is the heap limit set by `-Xmx256m` here? What does `args[]` contain?

*Answer:* No. `args[0]="-Xmx256m"`, `args[1]="20"`, and the application prints `minutes=INVALID_NUMBER` because it tries to parse the first element.

**Exercise 3 — Distinguish three mechanisms.** If you want the application to read the `study.mode` configuration via `System.getProperty`, should you use `-D`, an environment variable, or `args[0]`?

*Answer:* Use `-Dstudy.mode=...` before the class name. The other two only work if the application actively reads and maps them.

**Exercise 4 — Fix the run command.** The program needs to receive `45` and `--check` in `args[]`, the requested heap limit is `128m`, and property `study.mode=qa`. Write a valid run command.

*One answer:*

~~~bash
java -Xmx128m -Dstudy.mode=qa -cp out ArgsBoundaryDemo 45 --check
~~~

**Exercise 5 — Test invalid data.** Set `args[0]` to `-1`, `abc`, and `2147483648` in turn. How do they differ?

*Answer:* `-1` parses successfully yet violates the data range; `abc` is not a number; `2147483648` is a properly formatted decimal number yet exceeds the `int` range, so both of the latter two trigger `NumberFormatException`.

## Checklist to remember

- [ ] Know how to distinguish **options before the class/JAR/source file name** from **arguments after the entry point**.
- [ ] Know that `-Xmx` configures heap, `-D` configures system properties, and `-cp` is the launcher's class lookup option.
- [ ] Know that `String[] args` only contains strings passed to the application after the entry point.
- [ ] Know why `"hai tu"` is passed as a single argument in PowerShell/Bash.
- [ ] Know that `System.getProperty` and `System.getenv` read two different configuration sources.
- [ ] Know how to run `javac` followed by `java -cp out ...` on both Windows/Linux and compare with `java TenTep.java`.
- [ ] Can inspect `args.length`, classify parse errors, and fix `-D` placement when configuration takes no effect.

**Conclusion:** View a Java command as two parts: **configuring how Java runs** and **data handed to the application**. Placing each on the right side of the class/JAR/source-file boundary avoids confusion between the JVM, Java launcher, and `main(String[] args)`.
