# Checking the Version of `java` and `javac`

> **Module:** Java core — language-basics  
> **Section:** Tools and Execution  
> **Objective:** Use the terminal to accurately identify the **running Java runtime** version and the **invoked Java compiler** version, find the cause when they differ, check whether `.class` files can run, and know when to use `javac --release`.

## 1. Two similarly named commands with different functions

When learning Java, you usually need two command-line programs:

- **`java`:** The Java launcher, which starts the runtime environment to run a Java program. The version displayed by `java -version` indicates the launcher/runtime that the terminal is currently invoking.
- **`javac`:** The compiler in the **JDK**, which translates Java source code (`.java`) into bytecode (`.class`). The version in `javac -version` indicates the compiler being invoked.

The term **JDK** (*Java Development Kit*) refers to the development toolkit, which normally contains **both** `java` and `javac`. A machine that only has a runtime to run applications might have the `java` command without `javac`.

| Question | Check with | Meaning |
| --- | --- | --- |
| Which Java version is the terminal starting? | `java -version` | The launcher/runtime version found through the current environment |
| Which Java compiler is the terminal selecting? | `javac -version` | The `javac` version currently being found |
| Can `Hello.java` be compiled? | `javac Hello.java` | Practical check that a compiler exists and the source code is valid |
| Can `Hello.class` be run? | `java Hello` | Check the JVM/runtime along with the appropriate classpath and entry point |

**Note:** `java -version` does **not** tell you which compiler compiled a `.class` file. Conversely, `javac -version` does **not** prove the machine will use that same JDK when you type `java`. The two commands may come from two different installation directories.

## 2. Run the version check directly in the terminal

Open Terminal (macOS/Linux), Command Prompt, or PowerShell (Windows), and run in turn:

~~~bash
java -version
javac -version
~~~

Example illustrating **a JDK 17 environment**, not a fixed result for every machine:

~~~text
openjdk version "17.0.x" ...
OpenJDK Runtime Environment ...
OpenJDK 64-Bit Server VM ...
javac 17.0.x
~~~

In actual output, `...` and `x` are replaced by specific version/build/vendor information. You may see distribution names such as Oracle, Eclipse Temurin, Microsoft, Amazon Corretto, or another OpenJDK build.

How to read it:

1. Find the **major feature version** (*feature version*): for example `17` in `17.0.x` or `21` in `21.0.x`.
2. The remaining parts usually indicate maintenance updates and builds. Two machines both running “Java 17” may have different patches/builds.
3. Record **both check lines**. If they differ, identify the cause instead of assuming Java is broken.
4. Do not infer the latest release or security status solely from the major version number: support/update policies depend on the vendor and timing.

### `-version` or `--version`?

With modern Java, you can use:

~~~bash
java --version
javac --version
~~~

`--version` is the standard syntax from **Java 9 onward**. To check across many older installations as well, especially Java 8, `-version` is the familiar and more compatible choice. Do not rush to conclude “Java is missing” if an older version does not understand `--version`: try `-version`.

With Java 8 releases, the version name is sometimes printed in the form `1.8.0_...`. **Java 8 ≈ 1.8**, not Java 1 in modern version naming.

## 3. Reading the results correctly: examples of three scenarios

| `java -version` | `javac -version` | Initial conclusion |
| --- | --- | --- |
| `17.0.x` | `17.0.x` | Runtime and compiler are in the same version 17 line; still check paths if multiple JDKs exist |
| `11.0.x` | `17.0.x` | The compiler may produce bytecode newer than JVM 11 understands, unless configured with an appropriate target |
| Prints version, runs | “command not found”/“not recognized” | A runtime was found, but `javac` cannot be found through the current terminal |

It is **not mandatory** for every system to have both version numbers match down to every patch. A newer compiler can be configured to build programs for an older runtime; however, you must control the **bytecode version, standard APIs, and library dependencies**.

Conversely, `java` and `javac` both reporting “17” is **not enough** to prove they reside in the same JDK directory. For example, one command might be an alias, wrapper, or shim pointing to another installation. That is when you need to inspect the **actual paths**.

## 4. Finding where the terminal locates `java` and `javac`

### Windows — PowerShell

~~~powershell
where.exe java
where.exe javac
Get-Command java -All
Get-Command javac -All
$env:JAVA_HOME
~~~

- `where.exe` shows the executables with matching names found on `PATH` according to Windows' lookup mechanism.
- `Get-Command ... -All` is useful in PowerShell because it can also detect aliases/functions/commands prioritized by PowerShell.
- `$env:JAVA_HOME` prints the environment variable value in the **current PowerShell session** if set.

**You must use `where.exe`**, not just `where` in PowerShell: `where` can be an alias for `Where-Object`, not the path-lookup program.

### macOS / Linux — shell

~~~bash
command -v java
command -v javac
type -a java
type -a javac
echo "$JAVA_HOME"
~~~

`command -v` shows which command the shell resolves; `type -a` (in Bash and many common shells) can list multiple matches/aliases/functions.

Additional OS-specific references:

~~~bash
# Linux with readlink supporting -f:
readlink -f "$(command -v java)"
~~~

~~~bash
# macOS: list JDK installations known to java_home:
 /usr/libexec/java_home -V
~~~

The macOS command above has **an unnecessary leading space**; when typing it, use `/usr/libexec/java_home -V`. `readlink -f` is not a portable option across all macOS versions, so do not mechanically apply the Linux command.

### Why might the paths not be what you expect?

Suppose a machine has JDK 11 and JDK 17 installed. When you type `java`, the OS/shell looks up the command based on the current environment (usually the order in `PATH`), rather than automatically choosing the JDK that matches the source code you intend to run.

In addition:

- An IDE may be configured to use a different JDK from the terminal.
- Maven/Gradle may be configured with its own JDK/toolchain; the terminal commands above only describe the environment you just checked and **do not automatically prove every build tool uses the same JDK**.
- Launchers via wrappers, aliases, or executable managers may select Java based on their own configuration.
- Running a program inside a container, CI, or SSH is **a different environment** from the terminal on your personal machine.

## 5. `JAVA_HOME`, `PATH`, and Java version: three different things

| Component | Role | What you should not assume |
| --- | --- | --- |
| `JAVA_HOME` | Environment variable usually pointing to the JDK directory for build tools and scripts | Does not guarantee the `java` command in the terminal is using that exact directory |
| `PATH` | List of locations searched for executables when typing a command name | Does not guarantee there is only one Java installation or no wrapper |
| `java.home` (Java runtime property) | The runtime directory of the **Java process actually running** | Does not necessarily equal the `JAVA_HOME` value or the location of the JDK used for compilation |

A way to adjust this **temporarily in the current terminal session**:

**Windows PowerShell (the path is only an example, replace it with an actual JDK):**

~~~powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-17'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
java -version
javac -version
~~~

**macOS/Linux, Bash or similar shell:**

~~~bash
export JAVA_HOME="/duong-dan/toi/jdk-17"
export PATH="$JAVA_HOME/bin:$PATH"
java -version
javac -version
~~~

These commands **do not install Java**; they only change how the current shell session locates the tools. Do not copy the example path if that directory does not exist. On some shells that cache command paths, you may need to open a new terminal or run `hash -r` (Bash) after changing `PATH`.

**Diagnostic rule:** check version → check path → check `JAVA_HOME` and build tool configuration. Do not edit system-wide environment variables before knowing where the issue lies.

## 6. Runnable Java example: confirming the version from inside the program

The `java -version` command reflects the Java invoked by the terminal. We can also ask the **running program itself** about its runtime.

Create the file **VersionEnvironmentDemo.java**:

~~~java
public class VersionEnvironmentDemo {
    public static void main(String[] args) {
        System.out.println("Java version : "
                + System.getProperty("java.version"));
        System.out.println("Runtime name : "
                + System.getProperty("java.runtime.name"));
        System.out.println("Java vendor  : "
                + System.getProperty("java.vendor"));
        System.out.println("VM name      : "
                + System.getProperty("java.vm.name"));
        System.out.println("Runtime home : "
                + System.getProperty("java.home"));
        System.out.println("Feature      : "
                + Runtime.version().feature());
    }
}
~~~

This is **Java 9+** code because of `Runtime.version()`; to study in a common environment, use **JDK 11 or 17 or higher**.

Compile and run in the directory containing the file:

~~~bash
javac VersionEnvironmentDemo.java
java VersionEnvironmentDemo
~~~

Illustrative output:

~~~text
Java version : 17.0.x
Runtime name : OpenJDK Runtime Environment
Java vendor  : <runtime vendor>
VM name      : OpenJDK 64-Bit Server VM
Runtime home : <current runtime path>
Feature      : 17
~~~

Actual values depend on the environment; not every JVM prints the exact example names above. If running in an IDE, compare the example's output **in the terminal** and **in the IDE** to check whether they select different runtimes.

Important points:

- `System.getProperty("java.version")` and `Runtime.version().feature()` measure the runtime **executing the code**.
- `java.home` measures the runtime location being used **inside the process**, not necessarily the JDK location that ran `javac`.
- A program does not automatically know which exact `javac` compiler produced the class file; to know which compiler you invoked, you need to check the build command and its configuration.

### What happens if there is only `java` without `javac`?

If `java -version` succeeds but `javac -version` reports command not found, the machine might only have a runtime, or the compiler is not on `PATH`. When you need to study or build from `.java`, install/select a compatible **JDK**, then re-verify both commands.

Do not use a successful `java -version` message to claim that you definitely have the full set of development tools.

## 7. Compiler version vs. class file version

This is the most important cause of the error “Java on the running machine is too old.”

When compiling, `javac` generates `.class` bytecode according to a **class-file version**. An older Java runtime may not be able to read a newer format.

| Target Java level | Common class-file major version |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

For example, a program built for **Java 17 (major 61)** cannot be loaded by a runtime that only supports up to **Java 11 (major 55)**. In that case, you may receive:

~~~text
java.lang.UnsupportedClassVersionError:
  ... has been compiled by a more recent version
  of the Java Runtime (class file version 61.0);
  this runtime only recognizes class file versions up to 55.0
~~~

This is an **illustrative message**, not necessarily identical to every vendor's message.

### Checking a class file with `javap`

After compiling `VersionEnvironmentDemo.java` with the JDK:

~~~bash
javap -verbose VersionEnvironmentDemo
~~~

Look for a line such as:

~~~text
major version: 61
~~~

`javap` is the JDK tool for viewing class/bytecode information. **The major version line of a class file** indicates the format level of that class, and does not directly prove which specific compiler version generated the file.

### Compiling for a target runtime version

If using a newer compiler, you can instruct it to build for an older Java level that the compiler still supports. For example, using **JDK 17** to target **Java 11**:

~~~bash
javac --release 11 VersionEnvironmentDemo.java
javap -verbose VersionEnvironmentDemo
java VersionEnvironmentDemo
~~~

For this example, the expected major version is **55**, because the selected target is Java 11. To prove it can run on Java 11, you must still **actually run the program with a Java 11 runtime**, not just with runtime 17 on the build machine.

`--release` simultaneously controls the language level, class-file target, and **standard Java APIs** available in the target release (within the compiler's supported range). It helps avoid the common mistake when using `-source`/`-target` of accidentally calling a standard Java API that only exists in a newer runtime.

**Important limitation:** `--release` does not make third-party libraries automatically compatible with older Java, does not handle native libraries or other runtime environment differences, and cannot ask a compiler to support a release it does not know. For example, JDK 8 does not understand `--release 11`.

### Checking the actual build and runtime path

A proper verification needs at least three pieces of information:

1. The **compiler** version used to build (`javac -version` or build tool information).
2. The target level of the `.class` file (`javap -verbose` or `--release` configuration).
3. The **actual runtime version used when running** (`java -version` on the target machine).

These three pieces of information are related, but **must not be conflated**.

## 8. Version errors and how to handle them

| Symptom | Possible cause | Check / resolution |
| --- | --- | --- |
| `java: command not found` or “not recognized” | Runtime/launcher not installed, wrong `PATH`, different shell environment | Locate the Java executable; check installation and `PATH` |
| `javac: command not found` while `java` works | Only a runtime is installed, or `PATH` does not point to JDK `bin` | Verify `javac` location, choose an appropriate JDK |
| `java` reports 11, `javac` reports 17 | The two executables may be picked from different installations | Check the path of each command and the build/runtime targets |
| `UnsupportedClassVersionError` | Bytecode is newer than the running runtime | Use an appropriate runtime or rebuild with the right `--release` |
| `invalid flag: --release` | Compiler is too old or does not support the flag | Check `javac -version`, select an appropriate compiler |
| `error: release version 21 not supported` | Current compiler does not support target 21 | Cannot compile Java 21 with an overly old compiler; use a supporting JDK |
| `NoSuchMethodError` after changing runtime/libraries | May be running with an API/library version mismatch compared to build time | Check dependencies/classpath, runtime APIs, and the actual library version loaded |
| IDE runs differently from terminal | IDE selects a separate Project SDK/Run Configuration | Check JDK settings in both the IDE and terminal |
| Works on personal machine, fails in Docker/CI | Container/runner has a different runtime/JDK | Check versions **inside** the container/runner, not just on the host |

**Do not treat the wrong symptom:** `Could not find or load main class` usually relates to **classpath or the main class name**, not necessarily a version error. Syntax errors in source code are compile errors; `UnsupportedClassVersionError` is a bytecode compatibility error at runtime.

## 9. Quick check workflow before starting a project

When opening a Java project for the first time or receiving a request to run code, follow this sequence:

~~~mermaid
flowchart TD
    A["Open terminal in the environment to check"] --> B["java -version and javac -version"]
    B --> C{"Are both commands present?"}
    C -->|No| D["Check JDK, PATH, alias/wrapper"]
    C -->|Yes| E["Record major versions"]
    E --> F["Check paths of java/javac"]
    F --> G["Identify project's Java target"]
    G --> H["Compile with appropriate configuration"]
    H --> I["Run using target runtime"]
    I --> J{"Result okay?"}
    J -->|No| K["Read error: classpath, bytecode, or API"]
    K --> F
    J -->|Yes| L["Environment confirmed"]
~~~

Short checklist:

- [ ] `java -version` produces output and you know which version you are using.
- [ ] `javac -version` produces output if you need to compile Java code.
- [ ] Checked executable locations, especially when multiple JDKs are installed.
- [ ] Know which Java runtime the project requires; do not pick a version at random.
- [ ] If using `--release`, know the compilation target and its limitations.
- [ ] Test running with the **target runtime**, not just the runtime on the development machine.

## 10. Practice exercises

**Exercise 1 — Reading versions:** Suppose `java -version` gives `11.0.x` while `javac -version` gives `17.0.x`. Does that mean the Java 17 compiler cannot be used?

*Hint:* You cannot conclude that yet. Compiler 17 can generate target 11 classes with `--release 11` if the code and APIs are compatible. Verify the build command and test running the artifact on an actual 11 runtime.

**Exercise 2 — Identifying paths:** On a machine with two JDKs, list the locations of `java` and `javac` using the OS-appropriate commands. Compare with `JAVA_HOME` and explain why they differ.

**Exercise 3 — Inspecting class files:** Compile `VersionEnvironmentDemo.java`, use `javap -verbose` to identify the major version. Then (if the compiler supports it) build with `--release 11` and check the difference.

**Exercise 4 — Identifying errors:** You deploy a Java 17 target `.class` file to a Java 11 machine and get `UnsupportedClassVersionError`. Propose **two** valid solutions and describe the library dependency risk if you choose to build targeting Java 11.

**Exercise 5 — IDE vs. terminal:** An application runs in the IDE but fails when run in the terminal. Check the runtime printed by `VersionEnvironmentDemo` in both places, the path of `java` in the terminal, and the IDE's Run/SDK configuration.

## 11. Self-assessment

You understand this lesson when you can explain:

1. Why you must run **both `java -version` and `javac -version`** instead of just one command.
2. Why `JAVA_HOME` does not automatically prove the `java` command is using that exact JDK.
3. The difference between **compiler version**, **class-file target**, and **runtime version**.
4. When encountering `UnsupportedClassVersionError`, why you need to check `--release` and the target runtime instead of just renaming files.
5. How to verify on Windows/macOS/Linux using simple commands without altering application data.

**Conclusion:** `java -version` checks the **execution** environment, `javac -version` checks the **compilation** tool. For a Java program to run properly, you need to combine both with the actual executable paths, target configuration, and testing on the runtime the application will use.
