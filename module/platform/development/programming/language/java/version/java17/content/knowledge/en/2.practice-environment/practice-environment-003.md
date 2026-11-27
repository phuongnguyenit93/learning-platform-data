# Setting Up `JAVA_HOME`, `PATH`, and Verifying `java` and `javac` with Java 17

To practice Java 17 programming on a personal machine, you need **JDK 17** and a terminal that can locate the exact toolset of that JDK. This lesson walks through configuring the environment on **Windows, macOS, and Linux**, then verifying both `java` (to run programs) and `javac` (to compile source code).

The desired outcome is:

- `JAVA_HOME` points to **the root directory of JDK 17**.
- `PATH` allows the terminal to find `java` and `javac` from the desired JDK.
- `java --version` and `javac --version` both report version **17**.
- You can compile and run a simple `.java` file.

> **Scope:** Examples use Java 17. If the machine has multiple JDKs, pick the appropriate **17.x** release instead of defaulting to the newest Java version. Installation paths depend on the operating system, JDK distribution, and update version; use the **actual path on your machine** rather than illustrative paths.

## 1. Understanding JDK, `JAVA_HOME`, and `PATH`

| Component | Meaning | Example |
| --- | --- | --- |
| **JDK (Java Development Kit)** | Development toolkit, including the `java` launcher and the `javac` compiler. | JDK 17 from Eclipse Temurin, Oracle, or another compatible distribution. |
| **`JAVA_HOME`** | Environment variable pointing to the **root directory** of the JDK. Many build tools read this variable to locate Java. | `C:\Program Files\Java\jdk-17` |
| **`PATH`** (Windows may display `Path`) | List of directories the terminal searches when you type a command name. | `%JAVA_HOME%\bin` on Windows or `$JAVA_HOME/bin` on macOS/Linux. |
| **`java`** | Command that launches a Java application (JVM). | `java --version` |
| **`javac`** | Compiler that turns `.java` files into `.class` files. | `javac --version` |

Suppose the JDK is installed in the `jdk-17` directory:

```text
jdk-17/                   <-- JAVA_HOME points here
├── bin/
│   ├── java              <-- Windows: java.exe
│   └── javac             <-- Windows: javac.exe
├── conf/
├── legal/
└── lib/
```

**Do not append `bin` to `JAVA_HOME`**: if you set `JAVA_HOME` to `.../jdk-17/bin`, tools that append `/bin` will mistakenly look for `.../jdk-17/bin/bin`. Conversely, `PATH` must include the **`bin` directory** so the terminal can invoke `java` and `javac` without typing the full path.

`java` and `javac` are resolved via the operating system's command lookup path (typically via `PATH`), so **setting `JAVA_HOME` properly alone does not guarantee those two commands use that JDK**. Both settings must be verified together.

## 2. Locating the JDK 17 Installation Directory

Before editing environment variables, install a **JDK 17** matching your operating system and CPU architecture (x64 or ARM64 if applicable). You can use JDK 17 from [Eclipse Adoptium](https://adoptium.net/temurin/releases/?version=17), [Oracle](https://www.oracle.com/java/technologies/downloads/archive/), or a JDK distribution approved by your project. Installing only a Java runtime without a compiler will not satisfy the practice exercises.

**Windows:** Open the JDK folder in File Explorer, such as `C:\Program Files\Java\jdk-17`. Confirm that it contains `bin\java.exe` and `bin\javac.exe`. The actual folder name may include a patch number or vendor name, such as the Eclipse Temurin folder.

**macOS:** After installing JDK 17, open Terminal and run:

```bash
/usr/libexec/java_home -V
/usr/libexec/java_home -v 17
```

The first command lists JDKs recognized by macOS; the second returns the root directory of a version 17 JDK, typically ending in `.../Contents/Home`. If the second command reports that no matching JDK was found, inspect or reinstall JDK 17 before configuring.

**Linux:** The path depends on the distribution and installation method. For instance, an Ubuntu/Debian machine might install the JDK under `/usr/lib/jvm/java-17-openjdk-amd64`. If `javac` is already in `PATH`, you can find the real file that the symbolic link points to:

```bash
readlink -f "$(command -v javac)"
```

For example, if the result is `/usr/lib/jvm/java-17-openjdk-amd64/bin/javac`, the corresponding root directory is `/usr/lib/jvm/java-17-openjdk-amd64`. If `javac` is not yet available, check the installed JDK 17 package with your OS package manager; do not guess a nonexistent path.

## 3. Configuration on Windows 10/11

### 3.1. Saving Configuration for Future Terminal Windows

1. Press **Start**, search for **Edit the system environment variables**, open **System Properties**, and click **Environment Variables…**.
2. Choose the appropriate scope: **User variables** applies only to your account; **System variables** applies system-wide and usually requires administrator privileges to edit. Prefer **User variables** if only practicing under your personal account.
3. Create or edit the `JAVA_HOME` variable and set its value to **the actual path to the JDK 17 root directory**, for example:

   ```text
   JAVA_HOME = C:\Program Files\Java\jdk-17
   ```

   In the Windows dialog input box, type the plain path **without surrounding double quotes** and **without appending `\bin`**.

4. In the **same scope's** variable list, select `Path` → **Edit** → **New** and add an entry:

   ```text
   %JAVA_HOME%\bin
   ```

5. If another JDK path exists in `Path`, reorder the entries so the desired JDK 17 takes precedence during command lookup. Note that the effective `Path` combines entries from both System and User variables; if another version is still selected, use the diagnostic commands in Section 6 to locate the preceding entry.
6. Click **OK** to save, **close old terminals, and open a new PowerShell/CMD window**. Running processes generally keep a snapshot of environment variables from when they were started.

### 3.2. Testing Temporary Changes in a PowerShell Window

If you want to test quickly without changing persistent settings:

```powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-17'
$env:Path = "$($env:JAVA_HOME)\bin;$env:Path"

$env:JAVA_HOME
java --version
javac --version
```

In **Command Prompt (CMD)**, the equivalent syntax for the current session is:

```bat
set "JAVA_HOME=C:\Program Files\Java\jdk-17"
set "PATH=%JAVA_HOME%\bin;%PATH%"

echo %JAVA_HOME%
java --version
javac --version
```

Both snippets only affect the current terminal window and its child processes. To persist the settings across new terminals, follow **Section 3.1**.

## 4. Configuration on macOS

macOS provides `/usr/libexec/java_home` to locate installed JDKs. With **zsh** (the default shell on many current macOS releases), open Terminal and run:

```bash
export JAVA_HOME="$(/usr/libexec/java_home -v 17)"
export PATH="$JAVA_HOME/bin:$PATH"

printf '%s\n' "$JAVA_HOME"
java --version
javac --version
```

So that subsequent **interactive zsh** sessions also use JDK 17, append those same two `export` lines to `~/.zshrc` and reload:

```bash
source ~/.zshrc
```

If you use **bash** instead of zsh, place those two `export` lines into the bash startup file appropriate for how you open your shell (typically `~/.bash_profile` for login shells on macOS) and open a new terminal.

> **Note:** JDK paths on macOS typically end with `/Contents/Home`; do not use the outer `.jdk` bundle folder as `JAVA_HOME`. If multiple JDKs exist, `/usr/libexec/java_home -v 17` selects the version 17 line. An IDE launched from the graphical desktop may use its own JDK setting, so also check **Project SDK/JDK** inside the IDE if it reports a different version.

## 5. Configuration on Linux

Suppose JDK 17 is confirmed to be at `/usr/lib/jvm/java-17-openjdk-amd64` on an Ubuntu/Debian machine. In **bash**, run:

```bash
export JAVA_HOME="/usr/lib/jvm/java-17-openjdk-amd64"
export PATH="$JAVA_HOME/bin:$PATH"

printf '%s\n' "$JAVA_HOME"
java --version
javac --version
```

Replace `JAVA_HOME` with your **actual** JDK 17 directory if the path differs. For interactive bash, add those two `export` lines to `~/.bashrc` and reload with:

```bash
source ~/.bashrc
```

If using zsh, configure `~/.zshrc` similarly. Other shells or login sessions may read different startup files; open a new terminal the way you normally do and re-verify.

Linux systems may already manage `java` and `javac` through symlinks or the distribution's version-selection mechanism. In that case, prepending `$JAVA_HOME/bin` to the **front** of `PATH` for your practice session prioritizes the specified JDK while leaving the system-wide default managed separately. Do not modify or delete system links solely to complete this lesson.

## 6. Verifying the Environment After Setup

### 6.1. Checking the Two Key Versions

Open a **new terminal** and run the two commands below (works across all three operating systems):

```text
java --version
javac --version
```

Example of expected output for Java 17:

```text
openjdk 17.0.x ...
OpenJDK Runtime Environment ...
OpenJDK 64-Bit Server VM ...

javac 17.0.x
```

Descriptive lines, patch numbers, and vendor names may vary. What you need to verify is that **both `java` and `javac` belong to line 17**. The `x` in the example is a placeholder, not literal output. You can also use `java -version` and `javac -version`, which still work on JDK 17.

### 6.2. Checking `JAVA_HOME` and Executables

**PowerShell (Windows):**

```powershell
$env:JAVA_HOME
Test-Path "$env:JAVA_HOME\bin\java.exe"
Test-Path "$env:JAVA_HOME\bin\javac.exe"
Get-Command java -All | Select-Object -ExpandProperty Source
Get-Command javac -All | Select-Object -ExpandProperty Source
```

Both `Test-Path` commands must return `True`. `Get-Command ... -All` reveals all command locations that could be selected; the first entry is typically the one PowerShell runs.

**CMD (Windows):**

```bat
echo %JAVA_HOME%
where java
where javac
```

In PowerShell, use `where.exe java` if you want to invoke Windows' `where` utility directly; plain `where` without `.exe` is aliased to a different PowerShell command.

**macOS/Linux (bash or zsh):**

```bash
printf '%s\n' "$JAVA_HOME"
test -x "$JAVA_HOME/bin/java" && echo "java: OK"
test -x "$JAVA_HOME/bin/javac" && echo "javac: OK"
command -v java
command -v javac
"$JAVA_HOME/bin/java" --version
"$JAVA_HOME/bin/javac" --version
```

Both `test -x` checks verify executable files in the selected JDK. `command -v` shows what path the shell resolves the command name to; on some OSes, the result may be a symlink or wrapper rather than the direct JDK path. Therefore, also compare the version printed via `PATH` with the version printed when calling `"$JAVA_HOME/bin/java"` and `"$JAVA_HOME/bin/javac"` directly.

### 6.3. Compiling and Running Your First Program

Create a practice folder, open a terminal **in that folder**, and create `HelloJava17.java` with these contents:

```java
public class HelloJava17 {
    public static void main(String[] args) {
        System.out.println("Running Java " + Runtime.version().feature());
    }
}
```

Compile and run (PowerShell, CMD, bash, and zsh use the same syntax):

```text
javac HelloJava17.java
java -cp . HelloJava17
```

Expected output:

```text
Running Java 17
```

The first command generates `HelloJava17.class` upon successful compilation. The second runs the compiled class, with `-cp .` specifying the current directory as the classpath. **Do not append `.class` to the class name when running**. If `javac` succeeds but `java` reports a class file version error, check whether the two commands point to different JDK versions.

## 7. Troubleshooting Common Configuration Errors

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `java` or `javac` is not recognized as a command | `PATH` does not contain the right `bin` folder, or the terminal was not reopened. | Check `JAVA_HOME`, `PATH` entries, and open a new terminal; on Windows use `where.exe`, on macOS/Linux use `command -v`. |
| `java` runs but `javac` is missing | Using a runtime-only environment, incomplete JDK installation, or `PATH` points elsewhere. | Confirm `JAVA_HOME/bin/javac` (`javac.exe` on Windows) exists, install **JDK 17**, and fix the command path. |
| `java --version` reports 21/25 or another version even though `JAVA_HOME` is JDK 17 | Another Java folder appears earlier in `PATH`, or the shell/IDE uses its own JDK selector. | Inspect path ordering and resolved command paths, place `JAVA_HOME/bin` ahead; check the IDE's selected JDK if inside an IDE. |
| `java` is 17 but `javac` is not 17 | The two commands resolve to two different JDK folders. | Check **both** command paths; ensure JDK 17 provides both `java` and `javac`. |
| Tool reports `JAVA_HOME` is invalid | `JAVA_HOME` mistakenly points to `bin`, a nonexistent JDK folder, or `.jdk` instead of `Contents/Home` on macOS. | Point to the actual **root directory** containing `bin/java` and `bin/javac`. |
| Just edited environment variables, but terminal still sees old values | The terminal process was opened before the configuration changed. | Close and reopen the terminal; if using an IDE-integrated terminal, restart the IDE window if needed. |
| Program compiles but fails to run or throws `UnsupportedClassVersionError` | The Java used to run is older than the Java used to compile, or the classpath/class name is wrong. | Compare `java` and `javac` versions; run `java -cp . ClassName` in the folder containing `.class`. |

**A common misconception:** `JAVA_HOME` is a conventional environment variable used by many development tools; typing `java` in a terminal primarily relies on the shell's command lookup and `PATH`. Therefore, checking `JAVA_HOME` alone is **not enough** to confirm the setup is correct.

## 8. Self-Check Completion Criteria

Before moving on to the next Java 17 lesson, verify you can answer all four questions:

1. Which JDK 17 directory does `JAVA_HOME` point to? Does that directory contain `bin/java` and `bin/javac`?
2. Does `PATH` locate both commands from the right JDK? If multiple JDKs exist, which path takes precedence?
3. Do `java --version` and `javac --version` both belong to line **17**?
4. Do `javac HelloJava17.java` and `java -cp . HelloJava17` succeed and print `Running Java 17`?

If all four pass, your machine's terminal environment is ready for Java 17 hands-on exercises.

### Official References

- [Oracle JDK 17 — Installation on Microsoft Windows](https://docs.oracle.com/en/java/javase/17/install/installation-jdk-microsoft-windows-platforms.html)
- [Oracle JDK 17 — Installation on macOS](https://docs.oracle.com/en/java/javase/17/install/installation-jdk-macos.html)
- [Microsoft Learn — Set up Java on Windows](https://learn.microsoft.com/en-us/windows/dev-environment/java/)
- [Microsoft Learn — PowerShell and Environment Variables](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_Environment_Variables)
- [Eclipse Adoptium — Installing Eclipse Temurin](https://adoptium.net/installation/)
