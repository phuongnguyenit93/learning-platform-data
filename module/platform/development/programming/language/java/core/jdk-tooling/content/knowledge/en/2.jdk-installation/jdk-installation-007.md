# Managing Multiple JDKs on the Same Machine

Installing multiple JDK versions on a single machine is a common practice for developing, maintaining, and testing Java projects with different version requirements. A legacy project might require Java 8 or 11, while a new project uses Java 17 or 21. Developer machines, build servers, and deployment environments may also use different versions.

JDKs can coexist in separate installation directories. What you need to control is **which JDK is selected for each terminal, IDE, and project**. If the configuration is unclear, `java`, `javac`, or build tools may invoke the wrong version, leading to compilation errors, compatibility issues, or inconsistent results between local machines and CI.

## 1. Understanding How Multiple JDKs Coexist

A JDK is typically installed in its own directory, for example:

```text
Windows:
C:\Java\jdk-17
C:\Java\jdk-21

Linux:
/usr/lib/jvm/jdk-17
/usr/lib/jvm/jdk-21

macOS:
/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home
/Library/Java/JavaVirtualMachines/temurin-21.jdk/Contents/Home
```

These are illustrative paths; actual locations depend on the JDK vendor, installer, machine architecture, and operating system. Each directory contains an independent toolset, including the `java` launcher, the `javac` compiler, and other JDK tools.

Installing an additional JDK usually does not automatically break existing JDKs. Conflicts occur when the environment selects the wrong executable or when an application uses a different JDK than the version required by the project.

You should distinguish between three concepts:

- **Installed JDKs:** all JDK installations present on the machine.
- **Terminal default JDK:** the JDK whose `java` and `javac` commands are resolved through the current environment configuration.
- **Project JDK:** the version required by a project to compile, run tests, or package artifacts. IDEs and build tools can select a separate JDK for the project.

A machine can have JDK 17 and JDK 21 installed, use JDK 21 as the terminal default, and still compile a project using a Java 17 toolchain. There is no need to uninstall a JDK just because another project uses a newer version.

### Installing Versions Side by Side

Choose a JDK distribution that fits your team's policy and target platforms. Common OpenJDK distributions include Eclipse Temurin, Oracle JDK, Amazon Corretto, Microsoft Build of OpenJDK, and Azul Zulu. They may differ in release schedules, long-term support, licensing, and packaging; use official download sources and standardize the distribution across the project when reproducibility is needed.

- **Windows:** run the installer for each version and place each JDK in a separate directory, such as `C:\Java\jdk-17` and `C:\Java\jdk-21`. Do not choose the same destination directory for two versions.
- **macOS:** install each JDK package or archive separately. Installers typically register JDKs under `/Library/Java/JavaVirtualMachines`; use `/usr/libexec/java_home -V` to check which versions the system recognizes.
- **Linux:** you can install multiple JDK packages side by side using your package manager if your distribution's repository provides those versions. For example, on Debian/Ubuntu systems this may be `openjdk-17-jdk` and `openjdk-21-jdk`; on Fedora/RHEL it may be `java-17-openjdk-devel` and `java-21-openjdk-devel`. Package names and available versions depend on the repository and OS release.

After installation, verify that each directory contains `bin/java` and `bin/javac`. Package managers may automatically update alternatives or PATH; check the default selection before modifying your configuration.

## 2. The Role of JAVA_HOME and PATH

Two environment variables usually determine which JDK is used:

- **JAVA_HOME** points to the root directory of the selected JDK. For example: `C:\Java\jdk-21` or `/usr/lib/jvm/jdk-21`. Do not append `bin` to the end of the value.
- **PATH** is the list of directories the operating system searches for executables when a user enters a command. To invoke tools from the selected JDK, add `%JAVA_HOME%\bin` on Windows or `$JAVA_HOME/bin` on macOS/Linux to PATH.

When multiple directories containing `java` appear in PATH, the operating system typically uses the first executable found in search order. Therefore, PATH order matters. If the JDK 17 directory appears before JDK 21, the `java` command may still run Java 17 even if JAVA_HOME points to JDK 21.

**JAVA_HOME and PATH are related, but they are not the same thing.** Changing JAVA_HOME alone does not necessarily change which `java` command is invoked; PATH must point to the `bin` directory of the desired JDK. Conversely, PATH can invoke a Java executable even when JAVA_HOME is not set.

In addition, `java` and `javac` should be checked separately. A mixed PATH configuration can cause the launcher to come from one JDK while the compiler comes from another.

## 3. Checking Installed JDKs and the Active Version

Before changing configurations, identify which tools the machine is currently invoking. The following commands are read-only and do not alter installations. Use `-version` for compatibility with older JDK releases such as Java 8.

### On Windows

Open PowerShell:

```powershell
java -version
javac -version

# List java commands found in PATH
where.exe java

# View all resolution results for the java command in PowerShell
Get-Command java -All

# Check the current JAVA_HOME variable
$env:JAVA_HOME
```

Use `where.exe` to invoke the Windows `where` utility; in PowerShell, `where` can also be an alias for `Where-Object`.

### On Linux and macOS

Open a terminal:

```bash
java -version
javac -version

# View the java locations found by the shell
type -a java
type -a javac

# Check JAVA_HOME
echo "$JAVA_HOME"
```

On macOS, you can list the JDKs recognized by the system with:

```bash
/usr/libexec/java_home -V
```

On some Linux distributions that use the alternatives mechanism, you can view Java choices with:

```bash
update-alternatives --list java
update-alternatives --list javac
```

The command name and capabilities of alternatives depend on the distribution. If the command is not available, check the documentation for your package manager.

### Identifying the Actual Runtime Directory

To check where the running JVM is loading its runtime from, use:

```bash
java -XshowSettings:properties -version
```

In the output, look for the `java.home` property. This is the runtime path currently used by the Java process. You can compare it against your intended JDK directory.

Do not rely solely on the installation directory name. Check the versions of both `java` and `javac` as well as the actual path to avoid cases where PATH points to a different installation.

## 4. Switching JDKs Temporarily on Windows

If you only need a different JDK in a single PowerShell window, set the environment variables for that session:

```powershell
$env:JAVA_HOME = 'C:\Java\jdk-21'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

java -version
javac -version
```

Replace the example path with the actual JDK directory on your machine. After running this, the current PowerShell window will prioritize JDK 21's `bin`. Other terminals and system-wide settings remain unchanged.

To switch to JDK 17 in another PowerShell window or in the current one, update JAVA_HOME:

```powershell
$env:JAVA_HOME = 'C:\Java\jdk-17'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

java -version
javac -version
```

Note: if you prepend to PATH multiple times in the same shell session, PATH may accumulate duplicate JDK entries. A cleaner approach is to open a new terminal for each configuration, or update PATH in a controlled manner.

To configure this permanently on Windows:

1. Open **System Properties** and select **Environment Variables**.
2. Create or update the user or system `JAVA_HOME` variable to point to the root directory of your default JDK.
3. In the `Path` variable, add `%JAVA_HOME%\bin`.
4. Place this entry before older Java paths if they might be found first.
5. Open a new terminal and re-verify `java -version`, `javac -version`, and `where.exe java`.

Already-open terminals usually retain the environment copy from when they were launched. After editing environment variables through the Windows UI, open a new terminal to pick up the updated configuration. If Java was installed via multiple installers or package managers, inspect the PATH entries they added so older paths do not take precedence.

## 5. Switching JDKs on macOS

macOS provides the `/usr/libexec/java_home` utility to locate JDKs registered with the system. When multiple JDKs are installed, you can select the desired version:

```bash
# List JDKs recognized by the system
/usr/libexec/java_home -V

# Select JDK 21 for the current terminal
export JAVA_HOME="$(/usr/libexec/java_home -v 21)"
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
```

To switch to JDK 17:

```bash
export JAVA_HOME="$(/usr/libexec/java_home -v 17)"
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
```

The `-v 21` option requests a JDK matching version 21. If no matching installation is found, the command may not return a valid path; check the list with `-V` first.

If you want to set a default for new terminals, you can add the appropriate configuration lines to your shell startup file, typically `~/.zshrc` for zsh or `~/.bash_profile`/`~/.bashrc` for bash depending on your setup. After editing, open a new terminal or reload the configuration file. If you frequently switch versions per project, a Java version manager may be more convenient than repeatedly editing shell files.

## 6. Switching JDKs on Linux

On Linux, JDKs are commonly installed in a directory under `/usr/lib/jvm`, though the location can vary by distribution and installation method. Check the installation directory:

```bash
ls /usr/lib/jvm
```

To select JDK 21 in the current terminal:

```bash
export JAVA_HOME=/usr/lib/jvm/jdk-21
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
```

Replace `/usr/lib/jvm/jdk-21` with the actual path. To persist this configuration for new terminals, add the `export` lines to the appropriate shell startup file such as `~/.bashrc` or `~/.zshrc`.

Some Linux distributions manage default commands through alternatives. On Debian/Ubuntu systems, you can select the paths for `java` and `javac` using:

```bash
sudo update-alternatives --config java
sudo update-alternatives --config javac
```

On systems that use the `alternatives` command, the syntax is typically:

```bash
sudo alternatives --config java
sudo alternatives --config javac
```

Select the desired JDK entry from the list. Check both `java` and `javac`, as changing one command does not guarantee the other switches with it. The alternatives mechanism primarily controls system command symlinks; it does not always update JAVA_HOME automatically. If an application or build tool relies on JAVA_HOME, configure that variable separately.

Changing alternatives usually affects other users on the machine. Only use it when you genuinely want to change the system-wide default Java and have administrative privileges. For a single project or user account, shell configuration or a version manager is less intrusive.

## 7. Using a Java Version Manager

When you need to switch JDKs frequently, you can use a version manager instead of manually editing JAVA_HOME and PATH.

### SDKMAN!

SDKMAN! is popular on Linux and macOS, and can also be used in Linux environments such as WSL. It lets you install multiple JDKs, select one for the current terminal, or set a default version.

A typical workflow:

```bash
# List available Java versions to install
sdk list java

# Install a specific candidate from the list
sdk install java <candidate>

# Switch the JDK version for the current terminal
sdk use java <candidate>

# Set the default version for new terminals
sdk default java <candidate>

# Check the currently active version
java -version
javac -version
```

`<candidate>` is the full version identifier shown by `sdk list java`; do not guess the identifier, as it varies by release and vendor. `sdk use` changes only the current session, whereas `sdk default` sets the default selection.

### jEnv

jEnv is a Java version switcher for macOS/Linux that manages shims and per-directory configurations. It typically does not download and install JDKs itself; first install the JDKs using an installer or package manager, then register the JDK paths with jEnv.

Example workflow after jEnv is installed and configured in your shell:

```bash
# Register an existing JDK on the machine
jenv add /path/to/jdk-21

# List registered versions
jenv versions

# Select the version for the current project directory
jenv local <version>

# Select the user's default version
jenv global <version>

java -version
javac -version
```

Replace `<version>` with the exact version name shown in `jenv versions`. If build tools require JAVA_HOME, you can enable jEnv's export plugin with `jenv enable-plugin export`, then open a new terminal and verify the JAVA_HOME value. `jenv local` typically creates or updates a version configuration file in the current directory; check whether that file should be committed to Git according to your team's conventions.

If one part of a team uses SDKMAN!, another uses jEnv, or PATH is also edited manually at the same time, troubleshooting wrong JDK selection becomes harder. Standardize on a single management mechanism in your team's development environment.

## 8. Selecting a Specific JDK per Project

The terminal's default JDK does not have to be the JDK a project requires. You can configure a toolchain according to the project's requirements so every team member and build machine uses the same target language and API version.

### With Gradle

If a project uses Gradle's Java plugin and the build file uses the Groovy DSL, you can declare a toolchain:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

This configuration instructs Gradle to use a matching Java 21 JDK for Java tasks that support toolchains, such as compilation and testing. Depending on the Gradle configuration and environment, a matching JDK can be auto-detected on the machine or automatically provisioned if the project has toolchain provisioning configured.

Distinguish between the JDK running the Gradle daemon/process itself and the toolchain JDK used to compile or run project tasks. `JAVA_HOME` typically affects the JVM that launches Gradle; toolchains allow the project to select a different JDK for Java tasks. Check `gradle --version` to see which JVM is running Gradle and ensure your Gradle version is compatible with that JVM.

### With Maven

Maven can run on one JDK while selecting another JDK for certain plugins via Maven Toolchains. Teams declare available JDKs in the user's toolchains configuration file, typically at `~/.m2/toolchains.xml`, and then configure the corresponding plugins in the project to request the desired version.

Merely creating `toolchains.xml` does not automatically force every Maven plugin to use that JDK. You must verify the plugin configuration and build output to ensure the toolchain is applied. Running `mvn -version` shows which Java installation Maven is using to launch.

### With an IDE

IDEs typically maintain their own JDK settings at the machine, project, or module level. For example:

- IntelliJ IDEA has a Project SDK as well as separate SDK settings per module or build tool.
- Eclipse manages installed JREs/JDKs under Installed JREs and lets projects select an execution environment.
- Visual Studio Code with Java extensions allows registering Java runtimes and choosing the appropriate runtime.

Configuration labels vary by IDE version. After selecting a JDK, check the Project SDK, language level, build tool configuration, and the runtime used to launch the application. If the terminal runs Java 21 while the IDE builds with Java 17, they likely have separate configurations.

## 9. Compiling for an Older Java Version

A common scenario is having a newer JDK installed while a project must run on an older Java version. You can use `javac`'s `--release` option to target a supported Java version.

For example, using JDK 21 to compile source code targeting Java 17:

```bash
javac --release 17 -d out src/HelloApp.java
```

`--release 17` controls the language version, bytecode version, and Java platform API set allowed for target 17. This helps prevent compiling against APIs introduced only in Java 21 and accidentally deploying to Java 17.

After compiling, test the program on an actual Java 17 runtime. `--release` does not guarantee compatibility for external libraries, native libraries, OS configurations, or runtime behavior.

If you compile with JDK 21 defaults and then run that bytecode on Java 17, you may encounter:

```text
UnsupportedClassVersionError
```

This error usually indicates that the running JVM is too old to understand the class bytecode version. Fix it by running on a sufficiently new runtime or recompiling with the appropriate target version, while also checking APIs and dependencies.

## 10. Common Issues with Multiple JDKs

| Symptom | Common Cause | How to Check or Fix |
|---|---|---|
| `java -version` does not match the expected version | PATH prioritizes another Java directory. | Use `where.exe java` on Windows or `type -a java` on macOS/Linux; fix PATH order. |
| JAVA_HOME is correct, but `java` still runs an old version | PATH does not include `%JAVA_HOME%\bin` or `$JAVA_HOME/bin`, or an older Java entry comes first. | Inspect PATH and open a new terminal after making changes. |
| `javac` and `java` report different versions | The executables are resolved from different directories. | Check the paths of both commands separately and align the configuration. |
| Terminal uses the right JDK, but the IDE uses a different one | The IDE has its own Project SDK or runtime setting. | Check the JDK configuration in the IDE and build tool settings. |
| Maven or Gradle uses a different JDK than the project expects | The build tool is launched with a different JDK or toolchains are not configured. | Run `mvn -version` or `gradle --version` and verify toolchain settings. |
| Opening a new terminal does not reflect the version change | The shell config file was not loaded or system variables still prioritize an older path. | Check the active shell, startup file, and effective PATH. |
| Running the application throws UnsupportedClassVersionError | The runtime is older than the compiled bytecode version. | Select a newer runtime or compile with the appropriate `--release` flag. |
| Tools work on one machine but fail on another | Differences in JDK version, CPU architecture, environment variables, or dependencies. | Document the toolchain in the project and verify CI/deployment environments. |

An important principle is to check the version in the exact execution context. Running `java -version` in a terminal does not prove that your IDE, Maven, Gradle, service, or CI pipeline is using the same JDK.

## 11. Practical Workflow When Switching Between Multiple JDKs

When onboarding to a new project or switching Java versions, you can follow this sequence:

1. **Read project requirements:** identify the minimum Java version, the build version, and the target runtime version.
2. **Check installed JDKs:** run the appropriate listing command for your OS and locate each JDK path.
3. **Choose a management approach:** use JAVA_HOME/PATH for simple setups, or a version manager/toolchain when switching frequently.
4. **Select the terminal JDK:** update environment variables in the appropriate scope and verify `java -version` and `javac -version`.
5. **Configure IDE and build tools:** set the Project SDK, Gradle toolchain, or Maven Toolchains according to project requirements.
6. **Compile and test:** run a clean build, verify the target release, and test on the target runtime.
7. **Document requirements:** record the required Java version in project documentation, build configs, and CI pipelines so other team members can reproduce the environment.

For example, a machine with both JDK 17 and 21 can be organized as follows:

| Scope | Selected JDK | Reason |
|---|---:|---|
| Default terminal | 21 | Used for learning and new projects. |
| Project A | 17 | Project currently maintained on Java 17. |
| Project B | 21 | New project requiring Java 21. |
| Project A CI | 17 | Ensures builds and tests match the target environment. |

The table above is only an example of version assignment; actual values should follow each project's requirements.

## 12. Long-Term Management Principles

- Install each JDK in a separate directory and keep installation paths stable so IDEs, scripts, and build tools have reliable references.
- Choose a clear default JDK for the terminal; avoid leaving multiple unnecessary Java directories competing at the front of PATH.
- Point JAVA_HOME to the JDK root directory and verify that PATH points to its corresponding `bin`.
- Configure per-project toolchains so builds do not depend entirely on a developer's default machine JDK.
- Check the JDK running the IDE/build tool separately from the JDK used to compile and run the application.
- Apply security patches according to your organization's policy; before uninstalling an older version, confirm no projects, IDEs, services, or scripts still depend on it.
- Document the required JDK version in the README, onboarding docs, or CI configuration to keep the team's environments consistent.

Managing multiple JDKs well enables a single development machine to support multiple generations of Java projects simultaneously. When you separate installed JDKs, the terminal's default JDK, and per-project toolchains, switching versions becomes controlled, easy to verify, and far less prone to environment errors.
