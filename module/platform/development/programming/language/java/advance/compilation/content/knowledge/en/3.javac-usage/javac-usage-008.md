# Working Directory, Environment Variables, and Implicit Configuration When Using javac

With the same set of \`.java\` files and the same \`javac\` command line, a program can compile successfully on one machine yet report missing files or missing classes on another. The cause often does not lie in the Java code: **working directory**, **environment variables**, **implicit paths**, and **how an IDE/build tool invokes the compiler** can alter the actual inputs.

The goal of this lesson is to understand how those factors affect \`javac\`, recognize the difference between the compile phase and runtime, and construct reproducible compile commands. Examples use JDK 17 and above; sections explicitly note the corresponding OS or shell.

## 1. Four Configuration Sources That Determine a javac Command

When typing:

~~~sh
javac -d out src/lab/Main.java
~~~

the result depends on many things beyond the contents of \`Main.java\`:

1. **Working directory (CWD, current working directory):** the current directory of the \`javac\` process. Relative paths \`out\` and \`src/lab/Main.java\` are interpreted relative to this directory.
2. **Command-line arguments:** \`-d\`, \`-classpath\`/\`-cp\`, \`-sourcepath\`, \`--module-path\`, \`-encoding\`, \`--release\`, and other options change how the compiler finds, analyzes, and writes files.
3. **Environment variables:** \`PATH\` helps the shell select the \`javac\` executable; \`CLASSPATH\` can supply a default class path; \`JDK_JAVAC_OPTIONS\` can inject extra options into a \`javac\` command launched via the corresponding launcher.
4. **Invocation context:** terminal, IDE, CI script, or Maven/Gradle may choose different JDKs, working directories, classpaths, and source lists.

Three concepts must be distinguished:

| Concept | What is it used for? | Example |
|---|---|---|
| Source root | Root containing the package tree of source files | \`src\` contains \`src/lab/Main.java\` |
| Compilation output root | Where \`javac\` writes \`.class\` files | \`-d out\` → \`out/lab/Main.class\` |
| Classpath | Directory roots/JARs containing compiled classes to search | \`-cp out\` or \`-cp libs/helper.jar\` |

Source root, output root, and working directory **can be three different directories**. The value \`-d out\` does not mean \`javac\` automatically changes its current directory to \`out\`; compiling also does not automatically make \`out\` the runtime classpath for a subsequent \`java\` command.

## 2. Working Directory: Where Are Relative Paths Resolved From?

The working directory is a process property set by the shell or launching program upon startup. It is **not automatically** the directory containing \`.java\` files, \`.class\` files, the JDK installation directory, or the script file's location.

Example layout:

~~~text
lab-project/
├── src/
│   └── lab/
│       ├── Message.java
│       └── Main.java
├── config/
│   └── flag.txt
├── compiler.args
└── out/                  # created before compiling
~~~

If the terminal is in \`lab-project\`, the path \`src/lab/Main.java\` points to the source file. If you switch into \`lab-project/src\` while still passing that same path string, the compiler will look for \`lab-project/src/src/lab/Main.java\` and normally report file not found.

Commands to inspect working directory:

~~~sh
# Linux/macOS: POSIX shell
pwd
~~~

~~~powershell
# Windows PowerShell
Get-Location
~~~

\`cd\` or \`Set-Location\` changes the current shell's working directory; subsequently spawned processes normally inherit it. With IDEs/CI, you must check the **working directory configured for the task**, because opening a source file in an editor does not necessarily change the working directory.

### 2.1. Verifiable Compile and Run Example

Create \`src/lab/Message.java\`:

~~~java
package lab;

public final class Message {
    public static String text() {
        return "Xin chào javac";
    }
}
~~~

Create \`src/lab/Main.java\`:

~~~java
package lab;

import java.nio.file.Files;
import java.nio.file.Path;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Message.text());
        System.out.println(
            Files.exists(Path.of("config", "flag.txt"))
        );
    }
}
~~~

Create a text file \`config/flag.txt\` with any content, such as \`ok\`. Both Java files and the config file must be at the exact paths above. Open a terminal at **\`lab-project/\`**, and create \`out/\` if it does not yet exist.

On Linux/macOS:

~~~sh
mkdir -p out
javac --release 17 -encoding UTF-8 -d out src/lab/Message.java src/lab/Main.java
java -cp out lab.Main
~~~

On Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Path out -Force | Out-Null
javac --release 17 -encoding UTF-8 -d out src/lab/Message.java src/lab/Main.java
java -cp out lab.Main
~~~

Exact output when running from \`lab-project/\`:

~~~text
Xin chào javac
true
~~~

The \`javac\` command produces \`out/lab/Message.class\` and \`out/lab/Main.class\`. \`--release 17\` instructs the compiler to check code/APIs against Java 17. \`-encoding UTF-8\` sets the encoding for reading sources; \`-d out\` specifies where to write \`.class\` files.

Now move into \`src\` and run the **exact same bytecode** with a classpath adjusted for the new location:

~~~sh
cd src
java -cp ../out lab.Main
~~~

Result:

~~~text
Xin chào javac
false
~~~

The first line stays the same because the JVM finds \`lab.Main\` and \`lab.Message\` in \`../out\`. The second line changes to \`false\` because \`Path.of("config", "flag.txt")\` is resolved relative to **the Java process's working directory at runtime**; this time it looks for \`src/config/flag.txt\`. This is runtime behavior, distinct from when the compiler located \`src/lab/Main.java\`.

To run again with result \`true\`, return to the project root (\`cd ..\`) and run \`java -cp out lab.Main\`. The example was actually verified with \`javac --release 17\` and both \`java\` invocations above.

### 2.2. Types of Paths Commonly Affected

| Input | Example | Base directory when passing a relative path |
|---|---|---|
| \`.java\` file on command line | \`src/lab/Main.java\` | Working directory of \`javac\` |
| Bytecode output location | \`-d out\` | Working directory; create \`out\` beforehand |
| Classpath entry | \`-cp libs/helper.jar\` | Working directory |
| Source path root | \`-sourcepath src\` | Working directory |
| Module path root | \`--module-path mods\` | Working directory |
| Path to argument file | \`@compiler.args\` | Working directory |
| File opened by Java code at runtime | \`Path.of("config/flag.txt")\` | Working directory of the **\`java\`** process |

Absolute paths reduce dependence on the working directory, yet are often harder to port to another machine. A common solution is always running from a **fixed project root** and building consistent relative paths.

## 3. Distinguishing Classpath, Sourcepath, and Output Location

\`javac\` handles both \`.java\` sources and pre-existing \`.class\`/JAR classes. They belong to different concepts:

- \`-classpath\` (abbreviated \`-cp\`): where to look for compiled types and required dependencies during compilation when using the classpath.
- \`-sourcepath\`: where to look for \`.java\` files of referenced types not passed directly on the command line.
- \`-d\`: where to emit new \`.class\` files; does not replace classpath, sourcepath, or working directory.
- \`--module-path\`: where to look for **named modules** for projects using the Java Platform Module System (JPMS); does not simply replace \`-cp\`.

With the two source files in section 2, the clearest way is passing both files in one invocation:

~~~sh
javac --release 17 -encoding UTF-8 -d out src/lab/Message.java src/lab/Main.java
~~~

You can also pass only \`Main.java\` and explicitly specify the root where dependent files are found:

~~~sh
javac --release 17 -encoding UTF-8 -sourcepath src -d out src/lab/Main.java
~~~

In the example layout, the compiler can locate \`src/lab/Message.java\` from \`-sourcepath src\`. When relying on default automatic discovery of dependent sources, behavior depends on search-path configuration and existing \`.class\` files; for practical projects, proactively specify the source set or \`-sourcepath\`.

**Classpath default:** when neither \`-classpath\`/\`-cp\` nor \`--class-path\` is passed, \`javac\` uses the \`CLASSPATH\` value if the environment sets that variable; otherwise, the default classpath is normally the working directory (\`.\`). When an explicit classpath is supplied, the environment \`CLASSPATH\` value is not automatically appended. Do not assume the classpath always includes \`.\` once \`-cp\` is set; if you want to include the current directory, add it explicitly.

\`javac\` can also use the classpath to search for sources when no explicit sourcepath is given, depending on search mode. In projects requiring reproducible results, explicitly specifying sources and classpath is more reliable than relying on automatic lookup behavior.

**At runtime:** \`java -cp out lab.Main\` must have \`out\` on the runtime classpath. Compiler success does not guarantee the JVM finds all libraries at runtime. Additionally, using one JAR version at compile time and another at runtime can cause \`NoClassDefFoundError\` or \`NoSuchMethodError\`.

## 4. Environment Variables Related to javac

### 4.1. \`PATH\`: Which javac Does the Shell Pick?

On a machine with multiple JDKs, \`javac\` is found by the shell via \`PATH\` (or the shell's command resolution rules). Therefore terminal, IDE, and CI might inadvertently use different compiler versions.

Check on Linux/macOS:

~~~sh
command -v javac
javac -version
java -version
printf '%s\n' "$JAVA_HOME"
~~~

Check on Windows PowerShell:

~~~powershell
Get-Command javac
javac -version
java -version
$env:JAVA_HOME
~~~

\`JAVA_HOME\` is a common convention for build tools/scripts to select a JDK, yet **merely setting \`JAVA_HOME\` does not guarantee the shell is using \`$JAVA_HOME/bin/javac\`**. You must verify the actual command on \`PATH\` or invoke the desired JDK path explicitly. For JDK 9 and above, \`--release 17\` can be used to target Java 17; this option does not by itself change which JDK runs the compiler.

### 4.2. \`CLASSPATH\`: Hidden Dependency Paths

\`CLASSPATH\` can cause a compile command without \`-cp\` to succeed on one machine while failing on another. Paths are separated by \`:\` on Linux/macOS and \`;\` on Windows; an element like \`deps\` is a relative path and thus still depends on the working directory.

Suppose we additionally have:

~~~text
lab-project/
├── deps-src/
│   └── addon/
│       └── Marker.java
├── deps/                    # compiled .class files
├── app-src/
│   └── app/
│       └── Runner.java
└── app-out/
~~~

File \`deps-src/addon/Marker.java\`:

~~~java
package addon;

public final class Marker {
    public static String text() {
        return "dependency";
    }
}
~~~

File \`app-src/app/Runner.java\`:

~~~java
package app;

import addon.Marker;

public final class Runner {
    public static void main(String[] args) {
        System.out.println(Marker.text());
    }
}
~~~

At \`lab-project/\`, create \`deps/\` and \`app-out/\`, then compile the library first:

~~~sh
javac --release 17 -d deps deps-src/addon/Marker.java
~~~

At this point \`deps/addon/Marker.class\` exists. On Linux/macOS, a command temporarily setting \`CLASSPATH\` solely for the compiler process is:

~~~sh
CLASSPATH=deps javac --release 17 -d app-out app-src/app/Runner.java
java -cp "app-out:deps" app.Runner
~~~

On Windows PowerShell, you can set the variable only inside the test terminal session:

~~~powershell
$env:CLASSPATH = "deps"
javac --release 17 -d app-out app-src/app/Runner.java
java -cp "app-out;deps" app.Runner
~~~

After testing, restore the original \`CLASSPATH\` value (or close the test terminal). Both runs print:

~~~text
dependency
~~~

If \`CLASSPATH\` does not contain \`deps\`, and \`javac\` is not given another classpath/source containing \`addon.Marker\`, compiling \`Runner.java\` fails to find package \`addon\`. If you add \`-cp app-out\` to the \`javac\` command, that explicit classpath replaces \`CLASSPATH=deps\`; to provide all dependencies you must list every needed entry.

A more stable approach is **passing the classpath explicitly** instead of relying on environment variables:

~~~sh
# Linux/macOS
javac --release 17 -cp deps -d app-out app-src/app/Runner.java
java -cp "app-out:deps" app.Runner
~~~

~~~powershell
# Windows PowerShell
javac --release 17 -cp deps -d app-out app-src/app/Runner.java
java -cp "app-out;deps" app.Runner
~~~

When using \`-cp\`/classpath, remember that \`java\` and \`javac\` are **two processes with two distinct dependency-lookup stages**. Both must be properly configured at each required stage.

### 4.3. \`JDK_JAVAC_OPTIONS\`: Arguments Automatically Injected into javac

Starting in modern JDKs (Java 9 and above), the \`javac\` launcher supports the \`JDK_JAVAC_OPTIONS\` variable. The variable's contents are treated as additional arguments **prepended before command-line arguments**, using proper token/quote syntax. POSIX shell example:

~~~sh
JDK_JAVAC_OPTIONS="-Xlint:deprecation" javac --release 17 -d out src/lab/Message.java src/lab/Main.java
~~~

PowerShell:

~~~powershell
$env:JDK_JAVAC_OPTIONS = "-Xlint:deprecation"
javac --release 17 -d out src/lab/Message.java src/lab/Main.java
~~~

The \`-Xlint:deprecation\` flag requests warnings on usage of APIs marked deprecated. If code does not use any API in that category, the command may print no extra warnings. Not every option is valid inside \`JDK_JAVAC_OPTIONS\`; if the variable contains an invalid option, the command can fail even though what you typed in the terminal has no errors. Reset the variable after testing.

**Point to remember:** the command visible in the terminal is not necessarily the complete set of options the compiler receives. For puzzling errors, check \`JDK_JAVAC_OPTIONS\` before concluding that \`javac\` ignored or invented a flag.

### 4.4. \`JAVA_TOOL_OPTIONS\`, \`JAVA_HOME\`, and Other Environment Variables

\`JAVA_TOOL_OPTIONS\` affects JVMs started through supporting launcher/VM mechanisms, typically used for JVM options, monitoring, or instrumentation. It is **not synonymous** with \`JDK_JAVAC_OPTIONS\` and should not be used to pass language flags like \`--release\` to \`javac\`. JVM settings injected by the environment can affect tool startup or cause tools to fail.

Variables such as \`LANG\` and \`LC_ALL\` (on supporting systems) can affect locale/message display; file systems and default encodings also vary across environments. When sources contain Vietnamese characters, always consider \`-encoding UTF-8\`; when checking target API/language, use an appropriate \`--release\`. Do not rely on a warning or error string having the same language across every machine.

To avoid exposing sensitive data, inspect only compilation-related variables such as \`PATH\`, \`JAVA_HOME\`, \`CLASSPATH\`, and \`JDK_JAVAC_OPTIONS\`; do not post the entire raw environment to public issues/logs.

## 5. @argfile and Settings “Outside” the Command Line

With many files and arguments, \`javac\` can read arguments from an argument file. In the section 2 example, create \`compiler.args\` at the \`lab-project/\` root with contents:

~~~text
--release 17
-encoding UTF-8
-d out
src/lab/Message.java
src/lab/Main.java
~~~

From \`lab-project/\`, run:

~~~sh
javac @compiler.args
java -cp out lab.Main
~~~

The compilation command is equivalent to typing those corresponding arguments directly into the terminal. The file name after \`@\` and relative paths provided inside the argument file must still be interpreted relative to the **working directory of the invocation**; do not automatically assume the argument file's location is the root for all paths. If changing where you run from, update paths or enter the project root first.

Argument files help avoid overly long command lines and can be generated by build tools. When reading logs, a short command like \`javac @compiler.args\` does not immediately reveal the source list and flags; you must inspect the contents of the argument file in use. Arguments with spaces must be wrapped in quotes per supported argument-file syntax; do not treat an argument file as a shell script, because \`javac\` does not execute shell commands inside it.

Some options may also be added by \`JDK_JAVAC_OPTIONS\`, wrapper scripts, or IDEs. When in doubt, inspect the full command **after the build tool constructs it**, the task's working directory, environment variables, and the corresponding argfile contents.

## 6. Implicit Configuration in IDEs, Maven, Gradle, and CI

These tools manage compilation for you, yet also hide many details that must be specified explicitly when invoking \`javac\` directly:

- **IDE:** chooses Project SDK/JDK, compiler output, and classpath per module/project. The working directory of a **Run** configuration may differ from the project root or the **Build** configuration's directory. Clicking Run in the IDE does not guarantee equivalence to \`java -cp out ...\` in a terminal.
- **Maven:** the compiler plugin uses project source roots, dependencies, and build properties; JDK/toolchain versions may be governed by configuration. Do not view a manual \`javac\` command as an exact replica of Maven.
- **Gradle:** the \`JavaCompile\` task uses source sets, \`classpath\`, \`destinationDirectory\`, and Java toolchain per build configuration. The Gradle daemon can persist across commands; when diagnosing JDK or environment changes, check the actual environment/options received by the build process.
- **CI/container:** checkout directory, \`working-directory\` step, container environment, caches, and installed JDKs may differ from a personal machine.

If a terminal run succeeds yet IDE/CI fails, compare step by step: **\`javac\` version → working directory → source file list → compile classpath → sourcepath/module path → output root → environment variables and argument files**. Do not modify Java code before confirming both processes actually receive identical inputs.

## 7. Common Errors and How to Find Root Causes

| Symptom | What to inspect | Resolution direction |
|---|---|---|
| \`error: file not found: src/lab/Main.java\` | Standing in \`lab-project/\` or inside \`src/\`? File name/casing exact? | Use \`pwd\`/\`Get-Location\`, enter the right directory before invoking \`javac\`. |
| \`package addon does not exist\`, \`cannot find symbol\` | Do classpath/sourcepath and source list include \`addon.Marker\`? Implicitly relying on \`CLASSPATH\`? | Pass \`-cp deps\` explicitly, or supply \`Marker.java\` source file. |
| Works on machine A yet fails on machine B | Do the two machines differ in \`PATH\`, \`JAVA_HOME\`, \`CLASSPATH\`, \`JDK_JAVAC_OPTIONS\`, \`@argfile\`? | Specify target JDK, source root, classpath, encoding, and flags explicitly. |
| \`javac\` reports strange option absent from command line | Did \`JDK_JAVAC_OPTIONS\`, wrapper script, or IDE inject flags? | Inspect and temporarily remove injected config; re-run in a controlled environment. |
| \`Could not find or load main class lab.Main\` | Does \`java\` have \`out\` on runtime classpath? Package name exact? | Run \`java -cp out lab.Main\` from project root; check \`.class\` location. |
| Running from IDE reads file, terminal fails to read it | Different runtime working directory? | Use an explicit configured path, or switch working directory to the right root. |
| Compilation succeeds yet runtime reports missing class | Runtime classpath/module path lacks dependency | Declare libraries for both compile and run, avoid mismatched JAR versions. |
| Source character error messages or corrupted Vietnamese text | \`.java\` file encoding and compiler option differ | Save sources in appropriate UTF-8 and use \`-encoding UTF-8\`; avoid BOM when the JDK/compiler does not accept it. |
| \`out\` directory holds stale bytecode, confusing results | Output reused across multiple compilations with different config | Use separate output directory, run controlled clean build, verify dependencies. |

When needing to see the exact paths \`javac\` searches/reads, use \`-verbose\` in a diagnostic run:

~~~sh
javac -verbose --release 17 -encoding UTF-8 -d out src/lab/Message.java src/lab/Main.java
~~~

This option prints substantial details about sources/classes read or written and makes logs long. It is a **diagnostic** tool and should not be kept permanently enabled just for teaching small examples. Use \`javac --help\` and \`javac -X\` to inspect options available in the installed JDK; avoid assuming every JDK supports the exact same flag set.

## 8. Workflow to Make Compilation Results Reproducible

A clear workflow for multi-file exercises:

1. Pick a **fixed project root**; at the start of scripts/build tasks, check or switch to that root.
2. Select and verify a **specific JDK** via \`javac -version\`; use \`--release\` matching the target Java version when appropriate.
3. Explicitly define the source list or source root; ensure packages match the directory structure.
4. Pick a dedicated output root (\`out\`, \`build/classes\`…) and create it before compiling.
5. Explicitly specify compile classpath, module path, and sourcepath when needed; do not depend on a \`CLASSPATH\` accidentally present on the machine.
6. Explicitly pass \`-encoding UTF-8\` if the project saves sources in UTF-8.
7. Check \`JDK_JAVAC_OPTIONS\`, argfiles, and wrappers when the compiler receives unexpected arguments.
8. Configure runtime classpath and runtime working directory separately; confirm \`java\` also runs properly, not just \`javac\` succeeding.
9. In CI and real projects, place settings in version-controlled build configuration (Gradle/Maven), avoiding personal-machine-dependent configuration.

A quick checklist before troubleshooting:

~~~text
Where am I standing?             -> pwd / Get-Location
Which javac am I using?          -> command -v javac / Get-Command javac
Which javac version?             -> javac -version
Where are .java sources?         -> relative path from CWD
Where are dependencies?          -> -cp, -sourcepath, --module-path
Where are .class files written?  -> -d
Any hidden options?              -> CLASSPATH, JDK_JAVAC_OPTIONS, @argfile
What differs when running Java?  -> java -cp, runtime CWD, dependency
~~~

## 9. Practice Questions

1. You are standing in \`lab-project/src\`; why can \`javac -d out src/lab/Main.java\` fail even though \`Main.java\` exists? Fix it in two ways: changing the working directory, or changing the relative paths.
2. On a machine with \`CLASSPATH=deps\`, why can \`javac -d app-out app-src/app/Runner.java\` succeed yet a similar command fail on CI? What is the benefit of adding \`-cp deps\`?
3. With \`java -cp ../out lab.Main\` run from the \`src\` directory, why does checking existence of \`config/flag.txt\` return \`false\` without recompiling a single byte?
4. How does \`JDK_JAVAC_OPTIONS\` differ from \`JAVA_HOME\` and \`CLASSPATH\` in role? Why does checking each variable separately help isolate hard-to-reproduce bugs?
5. If \`compiler.args\` is in directory \`config/\` yet contains \`src/lab/Main.java\`, which directory must you stand in for the source path to mean the same as in the example? What happens if you mistakenly treat the argfile's location as the path root?
6. Why does \`javac -d out\` succeeding not guarantee \`java lab.Main\` runs properly? Which classpath option must be added for runtime?

The ultimate goal is being able to explain the **entire effective configuration** of a compilation run: which \`javac\` executable was chosen, which directory it started in, which explicit and implicit arguments it received, where it found sources/dependencies, where it wrote outputs, and in what context the JVM subsequently located and ran the classes. When these factors are clearly documented, compilation results stabilize and discrepancies between machines, IDEs, terminals, or CI become easy to trace.