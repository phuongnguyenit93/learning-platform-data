# Configuring and Verifying JAVA_HOME

JAVA_HOME is an environment variable that points to the **root directory of a JDK (Java Development Kit)**. Tools such as Gradle, Maven, Ant, IDEs, and scripts can use this variable to locate the required Java toolchain. Configuring JAVA_HOME properly helps tools use the same JDK and reduces errors when multiple Java versions are installed on the machine.

JAVA_HOME only stores the path to the JDK. The `java` or `javac` commands are found via PATH, so these two variables play related but distinct roles:

- **JAVA_HOME**: the path to the JDK root directory, for example `C:\Program Files\Eclipse Adoptium\jdk-21...` or `/usr/lib/jvm/java-21-openjdk-amd64`.
- **PATH**: the list of directories the operating system searches when running commands. Add the JDK's `bin` directory to PATH to invoke `java` and `javac` from any directory.

A typical installation structure looks like this:

~~~text
<JDK_HOME>/
├── bin/
│   ├── java
│   ├── javac
│   └── ...
├── conf/
├── include/
└── lib/
~~~

On Windows, executable files have the `.exe` extension. The JAVA_HOME directory must be the JDK root directory—not the `bin` directory, and not the path to `java.exe` or `javac.exe`. Use a full JDK; a runtime-only environment can run Java programs but does not include the `javac` compiler.

## 1. Identifying the Correct JDK Directory

Before setting the variable, identify the JDK version you need and its actual installation location. If the machine has multiple JDKs, choose the version appropriate for your project instead of arbitrarily picking the first result.

**Windows (PowerShell):**

~~~powershell
java -version
javac -version
where.exe java
where.exe javac
~~~

`where.exe javac` shows where the compiler is currently being found via PATH. If the output is `C:\...\jdk-21\bin\javac.exe`, the corresponding JAVA_HOME is the `C:\...\jdk-21` directory above `bin`. If there are multiple results, check each path and select the right JDK.

**macOS:**

~~~sh
/usr/libexec/java_home -V
/usr/libexec/java_home -v 21
~~~

The first command lists the JDKs recognized by macOS. The second returns the path to JDK version 21 if that version is installed and registered with the system.

**Linux:**

~~~sh
java -version
javac -version
command -v javac
readlink -f "$(command -v javac)"
~~~

On Linux, `readlink -f` follows symbolic links to find the actual `javac` file. If the result is `/usr/lib/jvm/java-21-openjdk-amd64/bin/javac`, the JDK root directory is `/usr/lib/jvm/java-21-openjdk-amd64`. The exact path varies depending on the distribution and how the JDK was installed.

A valid JDK directory typically contains both `bin/java` and `bin/javac` (or the corresponding `.exe` files on Windows). You can check these two files directly before saving the configuration.

## 2. Configuring on Windows

You can set JAVA_HOME for the current user account or for the entire machine. Start with a user variable if only the current account needs that JDK. Setting a system variable affects multiple accounts and usually requires administrator privileges.

1. Open **Start**, search for **Edit the system environment variables**, then open **Environment Variables**.
2. Under **User variables**, select **New**.
3. Set **Variable name** to `JAVA_HOME`.
4. Set **Variable value** to the JDK root directory path you identified, for example `C:\Program Files\Eclipse Adoptium\jdk-21.0.8.9-hotspot`. Replace this example with the actual path on your machine.
5. In the user variables list, select `Path` → **Edit** → **New**, then add `%JAVA_HOME%\bin`.
6. Confirm the dialogs. Open a new PowerShell or Command Prompt window to pick up the updated environment variables.

Do not add quotation marks to the JAVA_HOME value in the Windows dialog, even if the path contains spaces. In PATH, use `%JAVA_HOME%\bin`; do not point PATH directly to the `java.exe` file.

You can set JAVA_HOME at the user scope using PowerShell with the actual JDK path:

~~~powershell
[Environment]::SetEnvironmentVariable(
    'JAVA_HOME',
    'C:\Program Files\Eclipse Adoptium\jdk-21.0.8.9-hotspot',
    'User'
)
~~~

The command above saves the variable for the current account; it does not automatically update the environment of the currently open PowerShell window. Open a new terminal. You can add `%JAVA_HOME%\bin` to Path through the Environment Variables UI as shown in the steps above.

To test temporarily in the current PowerShell window before saving the configuration permanently:

~~~powershell
$env:JAVA_HOME = 'C:\Program Files\Eclipse Adoptium\jdk-21.0.8.9-hotspot'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
& "$env:JAVA_HOME\bin\java.exe" -version
& "$env:JAVA_HOME\bin\javac.exe" -version
~~~

`$env:` assignments only affect the current PowerShell process and child processes launched from it. Closing the window discards these temporary changes.

## 3. Configuring on macOS

macOS typically uses Zsh as the default shell. If you need JDK 21 and the system already recognizes it, you can use the `java_home` utility to avoid hardcoding an installation directory that might change:

~~~sh
/usr/libexec/java_home -V
export JAVA_HOME=$(/usr/libexec/java_home -v 21)
export PATH="$JAVA_HOME/bin:$PATH"
~~~

The two `export` commands only take effect in the current shell. To persist the configuration for new Zsh sessions, add them to `~/.zshrc` (interactive shells) or the startup file that matches how your terminal launches the shell, such as `~/.zprofile` for login shells. There is no need to add the same configuration multiple times across different files.

After saving the file, reload the configuration:

~~~sh
source ~/.zshrc
~~~

If you placed the configuration in `~/.zprofile`, reload that file or open a new terminal. If you use Bash, place the configuration in the Bash startup file that your environment actually reads, typically `~/.bash_profile` or `~/.bashrc`.

If `java_home -v 21` reports that no matching version was found, install JDK 21 or choose an available JDK version listed by `java_home -V`.

## 4. Configuring on Linux

On Linux, the JDK location depends on the distribution and installation method. You can use `readlink -f "$(command -v javac)"` to locate the `javac` binary, then use the directory above `bin` as JAVA_HOME.

For example, if the JDK is installed at `/usr/lib/jvm/java-21-openjdk-amd64`, add the following two lines to your shell startup file:

~~~sh
export JAVA_HOME="/usr/lib/jvm/java-21-openjdk-amd64"
export PATH="$JAVA_HOME/bin:$PATH"
~~~

Replace the example path with the actual JDK directory. For interactive Bash, the typical file is `~/.bashrc`; for login shells, you may need `~/.profile` or `~/.bash_profile`. If you use Zsh, it is usually placed in `~/.zshrc`.

Reload the corresponding file, for example:

~~~sh
source ~/.bashrc
~~~

Then open a new terminal or re-run the `source` command to apply the configuration. `export` commands only set variables for the current shell and its child processes; adding them to the startup file is what applies the configuration in subsequent shell sessions.

## 5. Verifying the Configuration

After configuring, open a new terminal and verify the JAVA_HOME variable, the executables inside the JDK, and how commands resolve through PATH.

**Windows (PowerShell):**

~~~powershell
$env:JAVA_HOME
Test-Path "$env:JAVA_HOME\bin\java.exe"
Test-Path "$env:JAVA_HOME\bin\javac.exe"
& "$env:JAVA_HOME\bin\java.exe" -version
& "$env:JAVA_HOME\bin\javac.exe" -version
where.exe java
where.exe javac
~~~

Both `Test-Path` commands should return `True`. Running the commands with full paths confirms that the JDK pointed to by JAVA_HOME is executable. `where.exe` shows where `java` and `javac` are found via PATH.

**macOS and Linux:**

~~~sh
printf '%s\n' "$JAVA_HOME"
test -x "$JAVA_HOME/bin/java" && echo "java: OK"
test -x "$JAVA_HOME/bin/javac" && echo "javac: OK"
"$JAVA_HOME/bin/java" -version
"$JAVA_HOME/bin/javac" -version
command -v java
command -v javac
~~~

If the files exist and have execute permissions, the two checks will print `java: OK` and `javac: OK`. Running the commands via full paths verifies the exact JDK specified by JAVA_HOME; `command -v` checks which command the shell selects via PATH.

Expected results:

- JAVA_HOME prints the JDK root directory, not ending in `/bin` or `\bin`.
- `java -version` and `javac -version` display the version matching the chosen JDK.
- `java` and `javac` via PATH point to the desired JDK. On Windows, the first result of `where.exe` is the prioritized path; on macOS/Linux, `command -v` shows the command selected by the shell.

The version output does not have to match online examples character for character: patch numbers and vendor names may differ. What matters is that the version and path match the JDK required by your project.

## 6. Verifying from Build Tools and IDEs

A terminal having the right JAVA_HOME does not guarantee that every tool uses the same JDK. Check directly from the tools running your project:

**Gradle Wrapper:**

~~~sh
./gradlew --version
~~~

On Windows, use:

~~~powershell
.\gradlew.bat --version
~~~

The JVM section in the output shows which JVM Gradle is using to run. If it differs from JAVA_HOME, check overrides such as `org.gradle.java.home` in `gradle.properties`, environment daemon settings, or IDE settings. After changing the JDK, you can stop the old daemon with `./gradlew --stop` (or `.\gradlew.bat --stop` on Windows), then run the Wrapper again.

**Maven:**

~~~sh
mvn -version
~~~

The output displays the Maven version, Java version, and the Java home that Maven is using. If the Java home differs from the expected JAVA_HOME, check the terminal, Maven launch scripts, and environment configuration.

**IDE:** IntelliJ IDEA, Eclipse, and other IDEs may have separate JDK settings for the Project SDK, Gradle JVM, or Maven runner. Check the exact setting your project uses. Changing the operating system's JAVA_HOME does not necessarily update the Project SDK already selected in the IDE.

It is also important to distinguish between the JVM running the build tool and the JDK used to compile source code. Gradle Java Toolchains can select a separate JDK for compilation tasks, even when the JVM running Gradle is a different version. Therefore, if `gradlew --version` is correct but the compiler still uses an unintended version, check the project's toolchain configuration.

## 7. Common Issues and Troubleshooting

| Symptom | Common Cause | Solution |
|---|---|---|
| JAVA_HOME points to a non-existent directory | Typo in the path, or the JDK was upgraded or uninstalled | Re-identify the installation directory and update JAVA_HOME |
| Tool reports Java not found | JAVA_HOME is not set, an old terminal hasn't picked up the variable, or PATH is missing the `bin` directory | Open a new terminal, check JAVA_HOME, and add `%JAVA_HOME%\bin` or `$JAVA_HOME/bin` to PATH |
| `java` is available but `javac` is not | The path points to a runtime without a compiler or to the wrong directory | Install a full JDK and set JAVA_HOME to the correct JDK root directory |
| `java -version` shows a different version than JAVA_HOME | Another JDK appears earlier in PATH | Check `where.exe java` or `command -v java`, then adjust the PATH order |
| Gradle or Maven uses a different JDK | The tool has its own JVM configuration, an old daemon is running, or the IDE overrides the environment | Check `gradlew --version`, `mvn -version`, `org.gradle.java.home`, and the IDE runner configuration |
| Variable was updated but the terminal still sees the old value | The current process keeps a copy of the environment from when it was opened | Open a new terminal; if the IDE was already open, restart the IDE |
| Paths with spaces cause errors | The path was entered incorrectly or shell commands are unquoted | Save the JAVA_HOME value without quotes in the Windows UI; when writing shell commands, quote path variables appropriately |

### Completion Checklist

- [ ] JAVA_HOME points to the root directory of an installed JDK.
- [ ] The `bin` directory inside JAVA_HOME contains both `java` and `javac`.
- [ ] PATH includes the JDK's `bin` directory in the right priority order.
- [ ] A new terminal displays the desired Java version.
- [ ] Build tools and the IDE use the correct JVM/JDK as configured for the project.

When all the steps above are in place, JAVA_HOME is configured and ready for Java tools to use. If a project has a specific JDK requirement, use that version as the baseline when choosing JAVA_HOME and when verifying Gradle, Maven, or your IDE.
