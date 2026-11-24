# Setting JAVA_HOME and Verifying the Actual Java on the Command Line

## 1. Goal and Scope

When working with **Spring Boot Build Tooling Packaging**, the Java Development Kit (JDK) is the foundation for compiling and running applications as well as launching build tools like Gradle or Maven. Installing a JDK successfully is **not enough** to confirm that your terminal, IDE, and Gradle Wrapper are using that exact JDK. A machine can hold multiple JDKs, and each tool may resolve a different path.

After this lesson, you will be able to:

1. Distinguish the `JAVA_HOME` environment variable, the `PATH` variable, the `java` and `javac` commands, and the `java.home` property of a running JVM.
2. Configure a JDK for the current terminal session on Windows PowerShell, Windows Command Prompt, Linux, and macOS, and know how to persist the setting for new sessions.
3. Verify exactly which executable the `java` command invokes and which runtime version is actually running.
4. Verify which Gradle version the Gradle Wrapper uses, which launcher/daemon JVM runs, and why the build JVM can differ from the compile JDK via Java Toolchains.
5. Diagnose wrong-Java-version errors, invalid `JAVA_HOME`, missing `javac`, or CLI results differing from the IDE/CI.

**Example convention:** **JDK 21** is used for illustration. That is a configuration example, not a claim that every project requires Java 21. Which version to install must be based on your project requirements and the corresponding Gradle/Spring Boot compatibility tables. Paths vary by machine; only substitute examples with an **actually installed JDK path**.

## 2. Understanding Four Key Pieces of Java Information

| Name | Role | Common Misconception |
| --- | --- | --- |
| `JAVA_HOME` | Environment variable pointing to the **JDK root directory** so tools can find Java, e.g., `C:\Program Files\Java\jdk-21` or `/usr/lib/jvm/java-21-openjdk-amd64` | Setting `JAVA_HOME` does not automatically guarantee `java` on `PATH` matches that JDK |
| `PATH` | List of directories the shell searches when you type a program name like `java` or `javac` | If an older JDK folder appears earlier, the shell may invoke the older version |
| `java -version` and `javac -version` | Reports the version of the **executable actually invoked by the shell** when running each command | `java` and `javac` can even point to two different versions |
| `java.home` | System property reported by a **running JVM** for its own runtime directory | Not another name for the `JAVA_HOME` environment variable |

A **JDK** contains the Java runtime plus development tools, including the `javac` compiler. A minimal Java runtime can run programs but does not provide `javac`. Therefore, when preparing a Spring Boot build environment, choose a **JDK**, not merely a runtime.

**Rule of thumb:** `JAVA_HOME` is what you *want tools to use*; `PATH` affects which `java`/`javac` the shell *will select*; `java.home` verifies *where a JVM actually launched from*. With Gradle, there is also the JVM running Gradle and the Java toolchain used for compiling/testing; they can be two different versions.

### 2.1. What Does a Valid JAVA_HOME Value Look Like?

Valid examples:

- Windows: `C:\Program Files\Java\jdk-21`
- Linux (typical Ubuntu/Debian): `/usr/lib/jvm/java-21-openjdk-amd64`
- macOS (bundle-installed JDK): `/Library/Java/JavaVirtualMachines/temurin-21.jdk/Contents/Home`

These are **examples**; vendor and path depend on the machine. `JAVA_HOME` must point to the directory containing `bin/java` and `bin/javac` (on Windows, `bin\java.exe` and `bin\javac.exe`). **Do not** set `JAVA_HOME` to the `java.exe` file itself, the `bin` folder, or a parent directory that does not contain the executables in the right place. When saving environment variables in an OS GUI, the value itself is the raw path; quotation marks are shell syntax for protecting spaces, not part of the directory name.

### 2.2. A Common Scenario

Suppose JDK 21 is set in `JAVA_HOME`, yet `jdk-17/bin` precedes `jdk-21/bin` in `PATH`. When you type `java -version`, the terminal can still invoke Java 17. If you execute the Java binary directly inside `JAVA_HOME/bin`, the result will be JDK 21. That is why you must check **both the environment variable and the actual executable** after every change.

## 3. General Verification Command Set: Verify Instead of Guessing

After opening the appropriate terminal, run these steps in order:

1. Print `JAVA_HOME` to see what value the shell sees.
2. Locate the `java` and `javac` executables the shell would invoke.
3. Run `java -version` and `javac -version`.
4. Run `java` and `javac` **directly** under `JAVA_HOME/bin` to cross-check.
5. Query the running JVM for `java.home`, `java.version`, and `java.vendor`.

A JVM inspection command that works on any OS:

~~~text
java -XshowSettings:properties -version
~~~

Look for the lines `java.home = ...`, `java.version = ...`, and `java.vendor = ...`. That is information reported by the newly launched Java process itself, not inferred from folder names. This command and `java -version` typically write diagnostic output to **stderr**, so when filtering or redirecting, include `2>&1`.

If `java -version` reports the right major version yet `java.home` points to a different folder than expected, you have uncovered an important mismatch. Two JDKs with the same major version can still differ in vendor, patch version, or architecture.

## 4. Windows PowerShell

### 4.1. Checking Current State

Open **PowerShell** and run:

~~~powershell
$env:JAVA_HOME
$env:Path -split ';'
Get-Command java -All | Select-Object CommandType, Source
Get-Command javac -All | Select-Object CommandType, Source
where.exe java
where.exe javac
java -version
javac -version
java -XshowSettings:properties -version 2>&1 | Select-String 'java.home|java.version|java.vendor'
~~~

Meaning:

- `Get-Command java -All` shows how **PowerShell** resolves the command name; it can display aliases/functions as well as applications if present.
- `where.exe java` searches for executables in directories on `PATH` in lookup order. In PowerShell, **you must write `where.exe`** to invoke this Windows utility: bare `where` can be an alias for `Where-Object`.
- `java -version` shows the Java executed by the shell; `javac -version` confirms the compiler exists and shares the major version you intend to use.
- `java.home` provides additional proof of the actual JVM.

If `Get-Command` reveals an alias or function named `java`, execution may differ from `where.exe`. In that case, read the shell's actual resolution result carefully.

### 4.2. Temporary Configuration for a Single PowerShell Session

Assuming you confirmed the JDK is at `C:\Program Files\Java\jdk-21`:

~~~powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-21'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

Test-Path "$env:JAVA_HOME\bin\java.exe"
Test-Path "$env:JAVA_HOME\bin\javac.exe"
& "$env:JAVA_HOME\bin\java.exe" -version
& "$env:JAVA_HOME\bin\javac.exe" -version

Get-Command java -All | Select-Object CommandType, Source
where.exe java
java -version
javac -version
~~~

Both `Test-Path` commands must return `True` if the path is valid and contains the tools. `&` is PowerShell's **call operator**, used to execute a path stored in a string containing spaces. Prepending `JAVA_HOME\bin` to the **front** of `PATH` prioritizes it ahead of older JDK directories for normal external commands.

Settings made with `$env:...` live only in the **current PowerShell process** and its child processes. After closing the terminal or opening a new independent window, these changes do not necessarily persist.

### 4.3. Persistent Configuration on Windows

Use the Windows **Environment Variables** dialog (e.g., `System Properties → Advanced → Environment Variables`):

1. Under the appropriate **User variables** or **System variables**, create/edit `JAVA_HOME` to the verified JDK root path.
2. In `Path`, add `%JAVA_HOME%\bin`. Place it ahead of other Java paths if this JDK needs priority.
3. Open a **new terminal** and re-run the verification set from Section 4.1. Already-open apps, IDEs, or old terminals may retain the previously loaded environment.

Choose User scope when only changing settings for your own account; System affects the whole machine and may require administrator rights. Do not run a command that overwrites the entire `Path` variable just to switch a JDK. When `setx` is used, it only affects processes started **later**, without modifying the current PowerShell session's environment; rewriting `Path` with `setx` can also truncate or alter unintended entries.

### 4.4. Windows Command Prompt (cmd.exe)

`cmd.exe` syntax differs from PowerShell. To set variables temporarily for one `cmd` session:

~~~bat
set "JAVA_HOME=C:\Program Files\Java\jdk-21"
set "PATH=%JAVA_HOME%\bin;%PATH%"
echo %JAVA_HOME%
where java
where javac
"%JAVA_HOME%\bin\java.exe" -version
"%JAVA_HOME%\bin\javac.exe" -version
java -version
javac -version
~~~

`set` and `%JAVA_HOME%` are `cmd.exe` syntax; pasting a `set ...` line verbatim into PowerShell will not mean the same thing. When invoking executables via paths with spaces, keep double quotes around the path.

## 5. Linux (bash and Compatible Shells)

### 5.1. Finding the Java Currently in Use

~~~bash
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
printf '%s\n' "$PATH" | tr ':' '\n'
command -v java
command -v javac
type -a java
type -a javac
java -version
javac -version
readlink -f "$(command -v java)"
java -XshowSettings:properties -version 2>&1 | grep -E 'java.home|java.version|java.vendor'
~~~

`readlink -f` is common on Linux/GNU: it resolves symlinks down to the final target, which is very useful when `/usr/bin/java` points through `update-alternatives`. If `command -v` reports an alias or function, `readlink -f` on that name is meaningless; inspect `type -a` to identify the executable path. The `readlink -f` usage here is **not for default macOS**.

### 5.2. Configuring a Terminal Session

Suppose the actual JDK is installed at `/usr/lib/jvm/java-21-openjdk-amd64`:

~~~bash
export JAVA_HOME="/usr/lib/jvm/java-21-openjdk-amd64"
export PATH="$JAVA_HOME/bin:$PATH"

test -x "$JAVA_HOME/bin/java" && echo 'java executable exists'
test -x "$JAVA_HOME/bin/javac" && echo 'javac executable exists'
"$JAVA_HOME/bin/java" -version
"$JAVA_HOME/bin/javac" -version

command -v java
command -v javac
java -version
javac -version
~~~

`export` lets child processes inherit `JAVA_HOME` and `PATH`. Adjusting them in a terminal does not automatically change the JDK of already-started IDEs, servers, or other terminals.

To preserve settings across new terminals, append the two `export` lines to the shell startup file **actually sourced by your shell session**, such as `~/.bashrc` for interactive bash or `~/.zshrc` for zsh. For login shells or CI, the sourced file can differ; check your shell and session type before editing and verify in a fresh session. Systems using package managers or `update-alternatives` may have additional Java management mechanisms; changing a system symlink and setting `JAVA_HOME` are two distinct operations.

## 6. macOS (zsh)

macOS provides the `/usr/libexec/java_home` utility to locate JDKs recognized by the system:

~~~zsh
/usr/libexec/java_home -V
/usr/libexec/java_home -v 21
java -version
javac -version
which -a java
which -a javac
java -XshowSettings:properties -version 2>&1 | grep -E 'java.home|java.version|java.vendor'
~~~

Here `-V` lists recognized JDKs, while `-v 21` requests one matching Java 21. If none is found, install/register an appropriate JDK before configuring.

Set the variables for the current zsh session:

~~~zsh
export JAVA_HOME=$(/usr/libexec/java_home -v 21)
export PATH="$JAVA_HOME/bin:$PATH"

printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
"$JAVA_HOME/bin/java" -version
"$JAVA_HOME/bin/javac" -version
java -version
javac -version
~~~

To apply in new interactive zsh sessions, you can add the two `export` lines to `~/.zshrc`, then open a new terminal and verify again. For other shells or processes launched by an IDE, environment loading can behave differently.

**macOS note:** `/usr/bin/java` can be an OS-managed launcher stub, so merely seeing that path via `which` is not enough to conclude which JDK was actually invoked. Combine `java -version`, `java.home`, and `/usr/libexec/java_home` to verify.

## 7. Verifying with a Runnable Java Program

Shell commands are the first layer of verification. To see what **the Java process itself** sees, create `RuntimeIdentity.java` with the full contents:

~~~java
public class RuntimeIdentity {
    public static void main(String[] args) {
        System.out.println("JAVA_HOME=" + System.getenv("JAVA_HOME"));
        System.out.println("java.home=" + System.getProperty("java.home"));
        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("java.vendor=" + System.getProperty("java.vendor"));
    }
}
~~~

In the directory containing the file, run:

~~~bash
javac RuntimeIdentity.java
java RuntimeIdentity
~~~

This example is compatible with Java 17+ and also runs on other standard JDK versions. `javac` compiles the file into `RuntimeIdentity.class`, then `java` launches the main class. The output consists of **four lines in the exact order in the code**; values depend on the real machine, so no fixed version or directory can be hardcoded as universal stdout.

Compare the `JAVA_HOME=...` line with `java.home=...`. If they differ, that is not automatically an error: it shows that **the environment variable passed by the shell** does not necessarily match **the process's actual runtime**. If the environment requires using the exact same JDK, continue checking `PATH`, aliases, and how the process was launched.

To cross-check without relying on `PATH`, after compiling, replace `java RuntimeIdentity` with the executable under `JAVA_HOME`:

- PowerShell: `& "$env:JAVA_HOME\bin\java.exe" RuntimeIdentity`
- cmd.exe: `"%JAVA_HOME%\bin\java.exe" RuntimeIdentity`
- Linux/macOS: `"$JAVA_HOME/bin/java" RuntimeIdentity`

The output may differ if the default `java` command resolved a different JDK. Running a class file with a runtime older than its compiled version can cause `UnsupportedClassVersionError`; this error typically indicates a compile/runtime Java compatibility mismatch.

## 8. JAVA_HOME, Gradle Wrapper, Gradle JVM, and Java Toolchains

### 8.1. The Wrapper Pins the Gradle Version, Not Every Java Setting

In a project that already has the **Gradle Wrapper**, invoke it from the project root:

~~~bash
# Linux/macOS
./gradlew --version
~~~

~~~powershell
# Windows PowerShell
.\gradlew.bat --version
~~~

The Wrapper consists of `gradlew`/`gradlew.bat` and the files under `gradle/wrapper`; `gradle/wrapper/gradle-wrapper.properties` identifies the **Gradle distribution** to run. The Wrapper can download that Gradle distribution if it is not yet cached. It does not automatically install a JDK for all tasks, nor does it guarantee that the JDK running Gradle is the JDK used for compilation.

`./gradlew --version` or `.\gradlew.bat --version` displays Gradle and JVM/launcher details depending on the Gradle version. However, a system can run a **Gradle Daemon** with a separately specified JVM. In newer Gradle versions, launcher and daemon JVM information may be displayed separately. Therefore, do not deduce all compile/test Java versions from a single line of Wrapper version output.

Gradle typically picks the build JVM from the launch environment (`JAVA_HOME` or `java` on `PATH`) **unless** overridden by settings such as `org.gradle.java.home` or **Daemon JVM criteria**. In current Gradle, Daemon JVM criteria (when configured) can take precedence over both `JAVA_HOME` and `org.gradle.java.home`. `org.gradle.java.home` controls the Java home of the build/daemon process rather than directly changing the JVM that starts the Gradle client. Hence changing `JAVA_HOME` may not immediately move the daemon to the new JDK.

### 8.2. The JVM Running Gradle Can Differ from the Compile JDK

Suppose a project uses the Gradle Java plugin and declares in `build.gradle` (Groovy DSL):

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

This is a **minimal Gradle build snippet illustrating Java Toolchains**, not a complete configuration for a Spring Boot application. When eligible Java tasks use this toolchain, Gradle picks JDK 21 for compilation; the JVM running Gradle itself can still be a different version, as long as it is compatible with the Gradle version in use. Toolchains can auto-detect installed JDKs or download a JDK if the environment and a toolchain repository are configured.

In a project with Java toolchain support, one way to inspect the Java installations Gradle detects is:

~~~bash
./gradlew -q javaToolchains
~~~

On Windows, use `.\gradlew.bat -q javaToolchains`. The list Gradle sees is **not** proof that every task definitely uses the same JDK; check toolchain declarations, `JavaCompile`, `Test`, and any overrides.

A comparison table worth remembering:

| Component | Common Controlling Setting | How to Verify |
| --- | --- | --- |
| `java` called from terminal | Shell command resolution, `PATH`, alias | `where.exe` / `Get-Command` / `type -a`, `java -version`, `java.home` |
| Gradle distribution | Wrapper properties | `gradlew --version` |
| JVM running Gradle build/daemon | Environment, `org.gradle.java.home`, Daemon JVM criteria, or IDE Gradle JVM | Gradle JVM info and corresponding daemon configuration |
| Gradle compile/test JDK | Java Toolchains or task configuration | `javaToolchains`, build declarations, and task execution info |
| JVM running packaged artifact | Launch command and deployment environment | `java -version` where it actually runs, `java.home`, startup logs when relevant |

A Java **toolchain** can determine the compile/test JDK independently of `JAVA_HOME`. Meanwhile, `sourceCompatibility` or `targetCompatibility` sets language/bytecode compatibility levels but **does not select the compiler JDK**; when you need to prevent calling APIs newer than the target runtime, consider the compiler's `--release` option and toolchain policy.

If you recently changed Gradle JVM settings yet the daemon still shows old behavior, check the daemon configuration and then use `./gradlew --stop` / `.\gradlew.bat --stop` to stop Gradle daemons for that Gradle version before re-verifying. Only do this when genuinely needed, as it affects active builds/daemons on the machine.

### 8.3. Maven Wrapper Also Needs Java

For projects using the Maven Wrapper, `./mvnw -version` (Linux/macOS) or `.\mvnw.cmd -version` (Windows PowerShell) shows the running Maven version and the Java runtime Maven uses. The Wrapper helps the project select the Maven version; it does not mean `JAVA_HOME` and toolchains automatically match across environments. With Maven toolchains or IDE launchers, inspect the project's specific configuration as well.

## 9. Environments Where Results Easily Differ

- **Terminal and IDE:** Project SDK, IDE Gradle JVM, and terminal `java` can all differ. When running Gradle through IntelliJ IDEA, check Gradle JVM in IDE settings; open a new integrated terminal if you just changed environment variables. Do not treat `java -version` in a terminal as sole proof for a build launched by the IDE.
- **CI/CD:** each runner/job has its own environment variables and Java paths. Print Java details inside the **exact job/step** running the build; Java settings on a developer machine do not carry over to the runner. If CI has a JDK setup step, check step ordering and which job executes the build.
- **Docker/Containers:** the host machine's `JAVA_HOME` does not determine the Java inside the image. Check Java from inside the container or corresponding build stage.
- **WSL:** Windows PowerShell and the Linux shell inside WSL are two separate environments. Use the JDK, environment variables, and shell syntax belonging to the side building the application.
- **Multiple JDKs and version managers:** SDKMAN!, asdf, jEnv, or similar tools can alter `PATH`/`JAVA_HOME` upon entering directories or opening shells. After every version switch, re-verify the actual executable and JVM.
- **Shell caching program locations:** some shells remember previously resolved commands. If you changed `PATH` and results have not updated, open a new session or refresh the shell's hash table (e.g., `hash -r` in bash) and check again.

## 10. Common Error Troubleshooting Table

| Symptom | Possible Cause | Resolution and Evidence |
| --- | --- | --- |
| `java` is not recognized | JDK not installed or `PATH` lacks the right `bin` folder | Confirm the Java executable actually exists, add the proper path, open a new terminal, and locate the executable again |
| `JAVA_HOME is set to an invalid directory` | `JAVA_HOME` points to `bin`, the `java` binary, a moved JDK, or a bad path | Point it back to the **JDK root directory**; verify `bin/java` and `bin/javac` exist |
| `java -version` still shows an old version | Older Java precedes it on `PATH`, alias/function, stale terminal, or version manager overrides it | Check `Get-Command`/`where.exe`/`type -a`, `PATH`, and `java.home`; cross-check the Java binary directly inside `JAVA_HOME` |
| `javac` does not exist while `java` works | Minimal runtime, incomplete JDK, or compiler not on `PATH` | Install/switch to a JDK containing `javac`; test using the direct path |
| `javac -version` differs from `java -version` | Compiler and runtime come from two different directories | Locate each executable; fix `PATH` and `JAVA_HOME`, and verify both |
| Gradle/Wrapper reports current Java is unsupported | Gradle or plugin version is incompatible with the JVM launching the build | Read the exact error, check Gradle wrapper version and compatibility table; pick a matching JVM or upgrade Gradle per project process |
| Gradle still compiles with a JDK different from `JAVA_HOME` | Java Toolchains, `org.gradle.java.home`, Daemon JVM criteria, or a different IDE JVM | Inspect the exact setting and task; distinguish daemon JVM from compiler toolchain |
| Build succeeds on machine A but throws `UnsupportedClassVersionError` on machine B | Machine B's runtime is older than the compiled class-file version | Check machine B's actual runtime and the build's bytecode target; adjust toolchain/target or runtime |
| Changed `JAVA_HOME` but IDE/CI build did not change | Process hasn't picked up the new variable or environment is isolated | Restart the relevant process or update the right CI job/IDE setting; re-run verification where the build executes |

**Do not handle a wrong-JDK issue by blindly deleting other JDKs, overwriting the entire `PATH`, skipping tests, or editing unrelated Spring Boot application configuration.** First establish exactly which tool is running which Java version.

## 11. Short Pre-Build Verification Workflow for Spring Boot

### When Using the Gradle Wrapper

1. Confirm the target JDK actually contains `bin/java` and `bin/javac`.
2. Set `JAVA_HOME` to the **JDK root** and ensure `PATH` prioritizes `JAVA_HOME/bin` if you want shell `java` to match it.
3. Print `JAVA_HOME` and executable locations; run `java -version`, `javac -version`, and `java -XshowSettings:properties -version`.
4. In the project directory, run `./gradlew --version` or `.\gradlew.bat --version` to verify the Gradle/JVM version; check against compatibility limits.
5. If the project uses Java Toolchains, inspect the toolchain config and `javaToolchains` when available. When you need to confirm the actual compile/test JVM, check the appropriate task/build logs.
6. **Only after** confirming the right toolchain and build command, run the project's build/packaging tasks. If the app uses `bootJar`, remember that the JVM running `java -jar` in the deployment environment also needs separate verification.

For learners, the most valuable way to interpret output is: "Where is this terminal calling `java` from, and what version does it report? Which JDK does `JAVA_HOME` point to? Which JVM runs Gradle? Which JDK does Gradle compile with?" Once you can answer those four questions with evidence, diagnosing Java and Wrapper issues becomes clear.

## 12. Official References

- Gradle — The Gradle Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html
- Gradle — Toolchains for JVM Projects: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle — Gradle Daemon: https://docs.gradle.org/current/userguide/gradle_daemon.html
- Gradle — Build Environment Configuration: https://docs.gradle.org/current/userguide/build_environment.html
- Gradle — Java Compatibility: https://docs.gradle.org/current/userguide/compatibility.html
- Oracle JDK 21 — `java` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Oracle JDK 21 — `javac` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html

Commands, terminal interfaces, Gradle daemon behavior, and supported Java levels can vary by operating system and tool version. Therefore, results on your **real machine and job** together with version-specific documentation are always the final authority.
