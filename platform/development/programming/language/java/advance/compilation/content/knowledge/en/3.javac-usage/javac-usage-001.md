# Checking the JDK and Identifying the Exact javac Being Invoked

Multiple JDKs can coexist on a single machine: one for an older project, a newer one for the current project, and a JDK used by an IDE or build tool. The `javac` command that the terminal actually invokes may differ from the one you think is selected; `java` and `javac` can even come from two different installation directories.

Goal of this lesson: **verify that a JDK is present**, **identify the exact version and `javac` executable selected by the shell**, **cross-check `java` against `javac`**, and then **run a test compilation**. This is the foundational diagnostic step before troubleshooting source code or classpath issues.

## 1. Distinguishing JDK, javac, java, and the Shell Environment

| Component | Purpose | What to Verify |
| --- | --- | --- |
| JDK (Java Development Kit) | Development toolkit containing tools such as `javac` and `java` | Where is the JDK installed, and which version is it? |
| `javac` | Compiler from `.java` source code to `.class` | Which version of `javac` is being invoked, and through which path? |
| `java` | Tool that launches the JVM and Java applications | Which JDK does the runtime come from? Does it match the intended version? |
| `JAVA_HOME` | Environment variable commonly used to point to the root directory of a JDK | Is the value correct? Which tools actually read this variable? |
| `PATH` | List of directories searched by the shell/OS when running a command without a path | Are there multiple `bin` directories? What is the precedence order? |
| IDE/build tool | May choose a separate JDK or Java toolchain different from the terminal | Does the tool's configuration differ from the shell? |

**Core note:** `JAVA_HOME` is not the command selector for `javac` in every shell. Normally, when you type `javac` without a path, the shell locates a candidate through its command resolution mechanism and `PATH`; aliases, functions, wrappers, or shims may also be involved. Some build tools/IDEs read `JAVA_HOME` or have their own JDK settings, so you must check the exact place where the error occurs.

The JDK root directory typically contains `bin/java` and `bin/javac` (Windows: `bin\java.exe`, `bin\javac.exe`). `JAVA_HOME` points to the **JDK root**, not to `bin`, `java.exe`, or `javac.exe`.

## 2. The First Three Checks

Open a new terminal in the exact environment where you intend to compile and run:

```text
java -version
javac -version
javac --version
```

`javac --version` works on modern JDKs (Java 9+); on JDK 17 and later, both `-version` and `--version` options work. `java -version` reports the runtime version of the `java` tool found, while `javac -version` reports the version of the compiler found. **Do not use the result of one command to infer the result of the other.**

**Illustrative** example; actual output varies by machine:

```text
$ javac -version
javac 21.0.5
```

An OpenJDK runtime may print additional build, VM, and vendor information when running `java -version`. Update releases may differ in patch numbers; you should not compare character-by-character against the illustrative output.

Results to compare:

- Both `java` and `javac` run successfully, and the version matches the project: good, but **not enough** to be sure they belong to the same installation.
- `java` runs but `javac` is not found: perhaps only a runtime is installed, the compiler is missing, or `PATH` points to a runtime/JDK that does not have `javac` in the current path.
- `javac` outputs version 21 while `java` outputs 17: there is a **mismatch between the compiler and runtime**. You may intentionally support an older version via `--release`, but first verify whether that is the desired configuration.
- `javac` returns a permission error, a shim error, or a non-existent path: you must trace the executable before touching Java code.

Messages such as “command not found”, “not recognized”, “No such file or directory”, and “Access is denied” can differ by operating system and shell. Read **the message content and exit code**, not just the error name.

## 3. Identifying the Exact javac on Windows PowerShell

In **PowerShell**, use the following commands:

```powershell
Get-Command javac
Get-Command javac -All
Get-Command java -All
where.exe javac
where.exe java
$env:JAVA_HOME
$env:Path -split ';'
```

How to interpret:

1. `Get-Command javac` shows **the command resolved by PowerShell** in the current session, including the command type: `Application`, `Alias`, `Function`, or another type. Read `Source`/`Definition` to identify the target corresponding to the command type.
2. `Get-Command javac -All` lists the candidates discovered by PowerShell according to its resolution rules. The first row typically shows the prioritized choice; if there is an alias/function, check its source.
3. `where.exe javac` searches for executable candidates along the Windows search path and lists the results, which is very useful when multiple installations exist. It **does not replace** `Get-Command` if PowerShell has an alias or function with the same name.
4. `$env:JAVA_HOME` checks the JDK configuration in the *current terminal process*. `$env:Path -split ';'` shows the order of `PATH` entries.
5. If `where.exe javac` prints multiple paths, compare the selected path against the `bin` directory of the desired JDK. Pay attention to shim directories, intermediate Java launchers, or version management tools.

To clearly inspect the command objects:

```powershell
Get-Command javac -All | Format-Table CommandType, Name, Source, Definition -AutoSize
Get-Command java -All | Format-Table CommandType, Name, Source, Definition -AutoSize
```

These are **PowerShell commands**. In PowerShell, `where` without the `.exe` suffix can be an alias for `Where-Object`; therefore explicitly use `where.exe` to run the Windows path-finding tool.

### Windows Command Prompt (cmd.exe)

If you work in **cmd**, the syntax differs from PowerShell:

```bat
where javac
where java
echo %JAVA_HOME%
echo %PATH%
javac -version
java -version
```

Do not type `$env:JAVA_HOME` in cmd, or type `echo %JAVA_HOME%` in PowerShell and draw conclusions from the result. The two shells have different syntax and configuration scopes.

### Running the Compiler Directly Using an Absolute Path

Once you know which JDK you want to use, in PowerShell:

```powershell
& "C:\Program Files\Java\jdk-21\bin\javac.exe" -version
& "C:\Program Files\Java\jdk-21\bin\java.exe" -version
```

The path is only an **example**: replace it with the real location. `&` is PowerShell's call operator, allowing execution of files at paths with spaces. Quotation marks only enclose the path; they **do not execute** the string on their own in PowerShell. In cmd, put the EXE path in double quotes and invoke it directly.

Compare the version of the tool pair **invoked via absolute path** with the tool pair **invoked via short name**. If they differ, the issue lies in shell command selection, not in the Java program.

## 4. Identifying javac on Linux

In Bash/zsh (or a POSIX-compatible shell), start with:

```bash
command -v javac
command -v java
type -a javac
type -a java
printf '%s\n' "$JAVA_HOME"
printf '%s\n' "$PATH" | tr ':' '\n'
javac -version
java -version
```

- `command -v` shows how the shell resolves the command name; if the name is an alias/function, the output is not necessarily a path to an executable.
- `type -a` in Bash and zsh is useful to see definitions or candidates that may be shadowed by `PATH` order. In some other shells, the `-a` option may not exist.
- `PATH` on Linux/macOS separates directories with a colon `:`.
- `JAVA_HOME` only reflects the value in the current shell; an empty value does not by itself prove that no JDK is installed.

On Linux with `readlink -f` (GNU/coreutils or a supported environment), you can trace a symlink:

```bash
readlink -f "$(command -v javac)"
readlink -f "$(command -v java)"
```

Only use `readlink -f` when `command -v` actually returns a **file path**. If it returns an alias/function or shell builtin, check `type -a` first. On many Linux distributions, `/usr/bin/javac` may be a symlink through the `alternatives` management system to the actual JDK. On operating systems without `readlink -f`, use the corresponding tool or syntax instead of assuming the command is always available.

**Illustrative** example, not a fixed result:

```text
/usr/bin/javac
/usr/lib/jvm/java-21-openjdk-amd64/bin/javac
```

The first line may be the path found by the shell, and the next line is the target after resolving links. Directory names depend on the distribution and architecture.

## 5. Identifying javac on macOS

Start with standard shell commands:

```bash
command -v javac
command -v java
type -a javac
type -a java
javac -version
java -version
echo "$JAVA_HOME"
```

macOS has a system tool to detect installed JDKs according to the OS mechanism:

```bash
/usr/libexec/java_home -V
/usr/libexec/java_home -v 17 --exec javac -version
```

- `/usr/libexec/java_home -V` lists the Java runtimes/JDKs recognized by the macOS tool along with their versions and paths; this list **is not guaranteed to include every Java installation** installed via every manager.
- `-v 17 --exec javac -version` requests selecting a compatible version per the tool's `17` selector and then runs `javac`. It does not modify `PATH` for all terminals.
- `/usr/bin/javac` on macOS can be a system launcher/stub, not the compiler file located inside the active JDK directory. Therefore, `command -v javac` returning `/usr/bin/javac` **is not enough** to know the final JDK.

If `java_home` cannot find the desired JDK, check how that JDK was installed and recognized by the built-in JDK management tool on macOS. Do not conclude that `javac` is using the right version just from seeing a JDK in the applications folder.

## 6. JAVA_HOME and PATH: Why Is It Easy to Pick the Wrong JDK?

Suppose a machine has two JDK directories:

```text
C:\Java\jdk-17\bin\
C:\Java\jdk-21\bin\
```

For a shell that uses `PATH` to locate applications, if `C:\Java\jdk-17\bin` comes before `C:\Java\jdk-21\bin` and no other alias/shim intervenes, typing `javac` will usually pick the version in the directory that comes first. Changing `JAVA_HOME` to JDK 21 without **updating `PATH`** does not force the typed `javac` command to switch along with it.

Similarly on Linux/macOS, for example:

```text
/usr/local/jdk-17/bin:/usr/local/jdk-21/bin:/usr/bin
```

`PATH` is searched in order, yet in practice there are also aliases, functions, shell command caching, and shims. Therefore, you need to **inspect the command name, path, and version together**.

### Switching the JDK Only in the Current PowerShell Session

When you genuinely need to test a different version, you can set variables for the **currently open shell session**:

```powershell
$env:JAVA_HOME = "C:\Program Files\Java\jdk-21"
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
Get-Command javac
javac -version
java -version
```

Replace the sample path with the **real JDK root**. The line updating `Path` puts the JDK's `bin` at the front of `PATH` in the current session; it does not modify system-wide settings. If an alias/function is still taking precedence, re-check `Get-Command -All`. When the terminal is closed, these session-level changes usually do not persist; a new shell inherits its environment from the parent process or system configuration.

### Switching the JDK Only in the Current cmd Session

```bat
set "JAVA_HOME=C:\Program Files\Java\jdk-21"
set "PATH=%JAVA_HOME%\bin;%PATH%"
where javac
javac -version
java -version
```

The double quotes in the `set "NAME=value"` syntax protect the value from edge spaces and do not become part of the value. The `set` command applies only to the current cmd process and its child processes.

### Switching the JDK Only in the Current Bash/zsh Session

```bash
export JAVA_HOME="/opt/jdk-21"
export PATH="$JAVA_HOME/bin:$PATH"
hash -r
command -v javac
javac -version
java -version
```

`/opt/jdk-21` is just an example; replace it with an existing JDK directory. `hash -r` clears the path lookup table of some shells so the new resolution does not rely on previously cached paths. In zsh, you can use `rehash` if needed. Do not permanently save `PATH` in a shell configuration file before verifying the temporary result.

**Important:** These environment-switching commands are **OS/shell-specific alternatives**; do not run all of them on the same machine. For enterprise or CI environments, you should manage JDK versions through controlled toolchains and configurations rather than arbitrarily modifying `PATH` across multiple profiles.

## 7. How to Verify Without Depending on PATH

To eliminate doubt about search order, invoke the tools directly inside `JAVA_HOME` and compare with the short command.

PowerShell:

```powershell
& "$env:JAVA_HOME\bin\javac.exe" -version
& "$env:JAVA_HOME\bin\java.exe" -version
javac -version
java -version
```

Bash/zsh:

```bash
"$JAVA_HOME/bin/javac" -version
"$JAVA_HOME/bin/java" -version
javac -version
java -version
```

Only run the above commands if `JAVA_HOME` is already set properly and those files actually exist. This is a direct way to inspect **two path groups**:

1. `$JAVA_HOME/bin/javac` (or `$env:JAVA_HOME\bin\javac.exe`) — the compiler inside your designated JDK.
2. `javac` — the compiler the shell picks via alias/function/`PATH`/shim.

If the two results differ, inspect `Get-Command -All` or `type -a` and fix the right command-selection mechanism. If the two results report the same version, you still need to check the paths: **two separate JDKs can share the same version string**.

### Do Not Confuse JVM's java.home with Shell's JAVA_HOME

The following command prints the **Java runtime configuration** and can help with analysis:

```bash
java -XshowSettings:properties -version
```

In the output, look for the `java.home` property. That value reflects the location of the **launched Java runtime** (typically the runtime portion of a JDK); it is not automatically the `JAVA_HOME` environment variable, nor does it by itself tell you exactly which `javac` compiler the shell selects. `-XshowSettings` output has many lines, and the order/format may vary across JVM versions.

In PowerShell or cmd you can also call `java -XshowSettings:properties -version` and look for `java.home` in the output. When copying logs, avoid exposing personal path details or unnecessary internal information.

## 8. Test Compiling for Real to Prove the Tool Works

Correct versions and paths are only the first step. Create the file `CompilerSmoke.java` in the current working directory with the following Java 17+ content:

```java
public class CompilerSmoke {
    public static void main(String[] args) {
        System.out.println("javac works");
    }
}
```

Use the compiler you just verified; with the short command:

```bash
javac -encoding UTF-8 -d out CompilerSmoke.java
java -cp out CompilerSmoke
```

A successful `javac` command creates `out/CompilerSmoke.class`; from modern JDKs onward, the destination directory is created as needed. This is an example without `package`. The `java` command loads the class from the `out` directory and prints the **exact stdout**:

```text
javac works
```

`javac` usually prints nothing to stdout when compilation succeeds. The Java file must be saved with the exact name `CompilerSmoke.java` because of the `public class CompilerSmoke` declaration. If you only run `java CompilerSmoke` without putting `out` on the classpath, you may encounter a class-not-found error. If stale class files exist from a previous run, check the file timestamp and `javac` exit code so you do not mistake an old result for this run's success.

On Windows PowerShell, you can confirm the file and run:

```powershell
Test-Path .\out\CompilerSmoke.class
java -cp out CompilerSmoke
```

If the class file is present, `Test-Path` returns `True`. A `False` result indicates the file is not at the expected location; re-check the working directory, file name, and compilation errors.

On Linux/macOS:

```bash
test -f out/CompilerSmoke.class
echo $?
java -cp out CompilerSmoke
```

`echo $?` immediately after `test` is `0` when the file exists and non-zero when it does not exist. Do not insert another command before checking `$?` if you want to read the status of `test`.

### When You Want to Be Sure Both java and javac Use the Same JDK During Testing

PowerShell:

```powershell
& "$env:JAVA_HOME\bin\javac.exe" -encoding UTF-8 -d out .\CompilerSmoke.java
& "$env:JAVA_HOME\bin\java.exe" -cp out CompilerSmoke
```

Bash/zsh:

```bash
"$JAVA_HOME/bin/javac" -encoding UTF-8 -d out CompilerSmoke.java
"$JAVA_HOME/bin/java" -cp out CompilerSmoke
```

Both examples require `JAVA_HOME` to point to a valid JDK. Using the **same JDK root** for both programs helps avoid accidentally compiling with a newer version and running with an older one. A single successful smoke test by itself does not verify all libraries or APIs that a large project will need.

## 9. When java and javac Have Different Versions: How to Handle It?

Suppose after checking, you get:

```text
javac 21.0.5
java version "17.0.12" ...
```

This is an **example of a mismatch**, not guaranteed output on your machine. When Java 21 compiles by default, the class file may require a Java 21 runtime, whereas the `java` command is running Java 17. When loading the class, the older JVM may report `UnsupportedClassVersionError`.

If the project truly needs to run on Java 17 while the compiler is JDK 21, one option is:

```bash
javac --release 17 -encoding UTF-8 -d out CompilerSmoke.java
```

`--release 17` directs the compiler to the language level, bytecode, and Java SE API of target release 17 supported by the tool. It does not guarantee that **third-party libraries**, native dependencies, or deployment configurations are compatible. `--release` differs from simply renaming a file or changing `JAVA_HOME`, and it cannot target a release newer than what the active compiler supports.

If the project requires JDK 21 for both build and runtime, choose JDK 21 for both and re-check the paths and versions. If the project specifies building with 21 but running on 17, explicitly verify the `--release`/toolchain setting. **Identical versions are a helpful signal, not the sole proof:** vendor, update release, architecture, and JDK configuration can also matter.

## 10. Multiple JDKs on the Machine and IDEs or Build Tools

Some common situations:

- You type `javac -version` in the terminal and get JDK 21, but the IDE shows JDK 17 for the project: the IDE may configure a separate SDK or compiler.
- `java -version` in the terminal is JDK 17, while a Gradle build uses Java toolchain 21: Gradle may run on one JVM and delegate compilation to a compiler from a different JDK.
- An SDK manager such as SDKMAN!, jenv, asdf, or other shims places an executable/wrapper before the JDK directory in `PATH`: you need to check what version that management tool selects in the current directory.
- A shell was opened **before** environment changes were made: the old session may retain the old `PATH`/`JAVA_HOME`. Close the terminal, reopen it, and check again to compare.
- CI runs inside a container or dedicated runner: the JDK on your personal machine does not determine the JDK in the CI job.

To check the Java used to **run Gradle**, you can use `./gradlew -version` on Linux/macOS or `.\gradlew.bat -version` in PowerShell when the project has a Gradle Wrapper. However, the JVM version shown there **does not automatically determine the compiler for all tasks** if the project uses Java toolchains. You need to compare the toolchain configuration, IDE SDK, runner environment, and target task logs.

If you are resolving an error in a specific place, run the verification commands **in the exact terminal/process context** of that place. Avoid changing system-wide configuration when only one project needs a different JDK version.

## 11. Common Errors and How to Isolate Them

| Symptom | Possibility | Next Check |
| --- | --- | --- |
| `javac: command not found` or “javac is not recognized” | JDK not installed, or `bin` is not on `PATH` | Locate a valid JDK; check `PATH` and invoke `bin/javac` directly |
| `java -version` works, `javac -version` errors | Runtime is installed, but compiler is unavailable or not selected | Check the JDK directory, `Get-Command`/`type -a` |
| `JAVA_HOME` is correct, yet `javac` still outputs an old version | `PATH` prioritizes another version, alias/shim/cache | Compare short `javac` against the absolute path |
| `java` and `javac` have different versions | Compiler and runtime are resolved separately | Find both paths and pick a matching pair |
| New terminal is right, old terminal is wrong | Environment variables are inherited at process creation; old session was not updated | Open a new terminal; compare variable values across the two processes |
| `/usr/bin/javac` or shim does not point directly to a JDK | Symlink, wrapper, launcher, or alternatives | Trace the symlink/launcher and compare versions |
| IDE builds wrongly even though terminal is right | IDE/toolchain specifies a separate JDK | Check Project SDK, Gradle/Maven runner, and compiler settings |
| Compiles successfully, but JVM throws `UnsupportedClassVersionError` | Class file is newer than the runtime | Check `java -version`, `javac -version`, `--release` |
| `Access denied` / `Permission denied` | Execution permissions or system policy | Check permissions and actual file path |
| `Could not find or load main class` | Compilation succeeded, but run with wrong classpath/class name | Check `-d`, `-cp`, package, and `.class` location |

Do not handle every error by installing another JDK. What needs to be done is to identify **which command is invoked, where, with which version, and by which process**, then make the minimal change at the right configuration layer.

## 12. Short Diagnostic Workflow Ready for Immediate Use

1. **Run the two version commands:** `java -version` and `javac -version` right inside the terminal where the error occurs.
2. **List the selected path and candidates:** Windows PowerShell `Get-Command javac -All`, `where.exe javac`; Linux/macOS `command -v javac`, `type -a javac`. Repeat for `java`.
3. **Inspect `JAVA_HOME` and `PATH`:** compare against the **desired JDK root**; do not assume the two variables are always in sync.
4. **Run `bin/javac` and `bin/java` directly from the target JDK:** if the absolute command works while the short command fails, focus on alias/function/shim/`PATH`.
5. **Compile `CompilerSmoke.java` and run from `out`:** verify that the compiler, output directory, classpath, and runtime work together.
6. **Compare build/IDE/CI configuration** if the error only occurs outside the terminal being checked.
7. **Make persistent configuration changes only after verification:** the JDK installation location, toolchain, or `PATH` order should be adjusted according to project policy.

### Self-Check

**1. If `JAVA_HOME` points to JDK 21, but `where.exe javac` shows JDK 17 in the priority position, what can be concluded?**

The short `javac` command may still run JDK 17, unless another command-resolution mechanism intervenes. Verify using `Get-Command javac` and `javac -version`.

**2. If `javac -version` and `java -version` both output 21, does that prove the two tools are in the same directory?**

No. Two separate installations can share the same major/patch version. Trace the path of each executable.

**3. Why is `java.home` printed by the JVM different from `JAVA_HOME` in the shell?**

`java.home` is a property of the runtime actually executing, whereas `JAVA_HOME` is an environment variable. The two values can point to different locations; `java.home` does not identify the `javac` version by itself.

**4. Why does the error only appear in Gradle even though typing `javac` in the terminal works fine?**

Gradle may run on a different JVM or select a compiler via a toolchain. Check the configuration and environment of the Gradle task itself.

**5. Why is `javac --release 17` useful when building with JDK 21 to run on Java 17?**

It instructs the compiler to use the language level, platform APIs, and bytecode compatible with Java 17 that the compiler supports. It does not resolve incompatible external libraries or missing runtime configuration.

## References

- [Oracle JDK 21 — javac command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): compiler options such as `-version`, `-d`, `--release`.
- [Oracle JDK 21 — Installation on macOS](https://docs.oracle.com/en/java/javase/21/install/installation-jdk-macos.html): how to use `java_home` to identify and select a JDK.
- [Microsoft Learn — Get started with Java on Windows](https://learn.microsoft.com/en-us/windows/dev-environment/java/): configuring and checking `JAVA_HOME` and Java tools on Windows.

A reliable Java toolchain check must include **the version**, **the actual executable path**, and **a successful compile/run**, all in the exact environment experiencing the issue.