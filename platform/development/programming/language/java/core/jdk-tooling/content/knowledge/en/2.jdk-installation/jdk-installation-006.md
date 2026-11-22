# Verifying the JDK Installation

After installing the Java Development Kit (JDK), you need to verify that the system finds the right Java executable, has the `javac` compiler available, and can compile and run a simple program. Checking with a few terminal commands helps catch installation issues, `PATH` or `JAVA_HOME` misconfigurations, or conflicts between multiple installed Java versions early.

## 1. Open the Appropriate Terminal

Open a new terminal window after installing the JDK or changing environment variables:

- **Windows:** Command Prompt (CMD) or Windows PowerShell.
- **macOS:** Terminal or the built-in terminal in your IDE.
- **Linux:** your desktop environment's terminal or a remote terminal.

Commands run in the terminal may use a different Java version than the one configured in your IDE or build tool. Therefore, be sure to check the exact environment you intend to use.

## 2. Check the Java Command

Run:

```bash
java -version
```

This command invokes the first `java` launcher that the operating system finds under the current configuration. The output typically shows:

- The Java version, for example `17.0.12`.
- The distribution vendor, such as OpenJDK or another vendor's build.
- Runtime and virtual machine architecture details.

For example, the output might start like this:

```text
openjdk version "17.0.12"
OpenJDK Runtime Environment
OpenJDK 64-Bit Server VM
```

This is only an example; the exact output varies by vendor and update release. What you need to verify is that the command runs successfully and that the version matches your project requirements.

You can use `java -version` on both older and newer Java versions. The `java --version` syntax is also supported starting from Java 9.

If the terminal reports that the `java` command is not found, check your installation and `PATH` variable in the sections below.

## 3. Check the javac Compiler

Run:

```bash
javac -version
```

Example output:

```text
javac 17.0.12
```

`javac` is the compiler that compiles Java source code into bytecode and is provided by the JDK. Therefore, this is an important step to confirm that the machine has Java development tools installed.

Interpreting the results:

- **Both `java` and `javac` run:** the system found both the runtime and the compiler.
- **`java` runs but `javac` is not recognized:** you may have installed a runtime-only package, or `PATH` does not point to the JDK's `bin` directory.
- **Neither runs:** the JDK may not be installed yet, the path may not be configured, or the terminal may not have reloaded environment variables.

For a development environment, the major versions of `java` and `javac` should be compatible—typically from the same JDK version. If the two commands show different major versions, check whether they are pointing to two separate Java installations.

Note on version formatting:

- Java 9 and later typically display the major version directly, for example `17.0.12`.
- Java 8 typically displays a format starting with `1.8`, for example `1.8.0_402`.

## 4. Identify Which Java Executable Is Being Used

A machine can have multiple JDKs installed, such as Java 8, Java 17, and Java 21. The `java` and `javac` commands are selected based on the operating system's search order, especially the order of directories in `PATH`.

### Windows

In CMD or PowerShell, run:

```powershell
where.exe java
where.exe javac
```

The command may return one or more paths, for example:

```text
C:\Program Files\Java\jdk-17\bin\java.exe
C:\Program Files\Java\jdk-21\bin\java.exe
```

When there are multiple results, the first entry found in the search order is usually the executable invoked when you type the command name. Use this output together with `java -version` and `javac -version` to identify the active installation.

In PowerShell, you can also inspect how PowerShell resolves the commands:

```powershell
Get-Command java -All
Get-Command javac -All
```

### macOS and Linux

Run:

```bash
type -a java
type -a javac
```

This command displays all locations found by the shell. To see the path selected first:

```bash
command -v java
command -v javac
```

If the paths for `java` and `javac` belong to two different JDK directories, adjust `PATH` so that both point to the desired installation.

## 5. Check the JAVA_HOME Environment Variable

Many development tools such as Maven, Gradle, and some IDEs use the `JAVA_HOME` environment variable to locate the JDK.

**`JAVA_HOME` should point to the JDK root directory**, not directly to the `bin` directory.

Example installation structure:

```text
jdk-17/
  bin/
    java
    javac
  conf/
  include/
  jmods/
  lib/
```

In this example, `JAVA_HOME` points to `jdk-17`; the directory containing the executables is `%JAVA_HOME%\bin` on Windows or `$JAVA_HOME/bin` on macOS/Linux.

### Windows PowerShell

View the current value:

```powershell
$env:JAVA_HOME
```

Check the executables inside the configured JDK:

```powershell
Test-Path "$env:JAVA_HOME\bin\java.exe"
Test-Path "$env:JAVA_HOME\bin\javac.exe"
```

If both return `True`, the corresponding files exist at that location. You can invoke them directly to verify the exact JDK that `JAVA_HOME` points to:

```powershell
& "$env:JAVA_HOME\bin\java.exe" -version
& "$env:JAVA_HOME\bin\javac.exe" -version
```

### Windows CMD

View the variable value:

```bat
echo %JAVA_HOME%
```

After confirming the variable points to the JDK root directory, invoke directly:

```bat
"%JAVA_HOME%\bin\java.exe" -version
"%JAVA_HOME%\bin\javac.exe" -version
```

### macOS and Linux

View the variable value:

```bash
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
```

If the variable is set, check the executables inside it:

```bash
test -x "$JAVA_HOME/bin/java" && "$JAVA_HOME/bin/java" -version
test -x "$JAVA_HOME/bin/javac" && "$JAVA_HOME/bin/javac" -version
```

If `JAVA_HOME` is empty or the corresponding files do not exist, reconfigure the variable to point to the actual JDK directory.

## 6. Check PATH

`PATH` is the list of directories that the operating system searches when you type a command like `java` or `javac`.

To invoke JDK tools from any working directory, the JDK's `bin` directory must be in `PATH`.

For example, if the JDK is installed at:

```text
C:\Program Files\Java\jdk-17
```

then the directory to add to `PATH` is:

```text
C:\Program Files\Java\jdk-17\bin
```

On macOS/Linux, if the JDK is at `/opt/jdk-17`, the directory to add is `/opt/jdk-17/bin`.

### Temporary Configuration in Windows PowerShell

The following example only affects the current PowerShell window. Replace the sample path with where your JDK is actually installed:

```powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-17'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
java -version
javac -version
```

### Temporary Configuration in macOS/Linux

The following example only affects the current terminal session. Replace the sample path with where your JDK is actually installed:

```bash
export JAVA_HOME=/opt/jdk-17
export PATH="$JAVA_HOME/bin:$PATH"
java -version
javac -version
```

To configure this permanently, update the environment variables in Windows Environment Variables or in your shell configuration file on macOS/Linux, such as `~/.zshrc` or `~/.bashrc`. After saving the configuration, open a new terminal to reload the values.

`JAVA_HOME` is not strictly required to run the `java` command; however, many build tools and IDEs rely on this variable. Configuring `JAVA_HOME` and `PATH` consistently helps prevent different tools from using different JDKs.

## 7. Verify by Compiling and Running a Real Program

Checking the two version commands alone does not prove that the entire development workflow works. Create a small program to test both compilation and execution.

Create the file **`JdkCheck.java`**:

```java
public class JdkCheck {
    public static void main(String[] args) {
        System.out.println("JDK installation OK");
    }
}
```

Open a terminal in the directory containing the file and run:

```bash
javac JdkCheck.java
java -cp . JdkCheck
```

Expected output:

```text
JDK installation OK
```

Explanation:

1. `javac JdkCheck.java` compiles the source code and produces `JdkCheck.class`.
2. `java -cp . JdkCheck` launches the `JdkCheck` class.
3. `-cp .` puts the current directory (`.`) on the classpath so the JVM can find the compiled class file.
4. If the message appears exactly as expected, the compiler, classpath, and runtime are all working for this example.

If `javac` succeeds but `java` reports that it cannot find the class, check that you are in the right directory containing `JdkCheck.class` and that you typed the class name correctly. If the file declares a package, you must run the class using its fully qualified package name and matching directory structure.

## 8. Common Verification Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `java` is not recognized | Java is not installed or the `bin` directory is missing from `PATH` | Check where the JDK is installed and add the correct `bin` directory to `PATH` |
| `javac` is not recognized | Only a runtime is installed, or `PATH` points to a runtime/different installation | Install a full JDK and place the desired JDK's `bin` directory at the right position in `PATH` |
| `java` and `javac` have different major versions | Multiple Java installations exist or `PATH` order is not as expected | Use `where.exe` or `type -a` to find the paths, then adjust the configuration |
| `JAVA_HOME` is invalid | Points to a nonexistent directory, the `bin` directory, or a runtime without a compiler | Reset it to the root directory of a full JDK |
| Updated `PATH` but commands still use the old version | Terminal or IDE is holding onto the old environment; another directory comes earlier in `PATH` | Open a new terminal, check the path order, and restart the IDE if needed |
| Terminal works properly but IDE reports missing JDK | IDE or build tool is using its own JDK configuration | Check Project SDK, Gradle JVM, or the JDK configured in the build tool |
| `UnsupportedClassVersionError` | The running runtime is older than the bytecode version required by the program | Use a compatible runtime or compile targeting the appropriate version |

Do not rely solely on directory names or the value of `JAVA_HOME` to conclude that commands are running the right Java version. Cross-check both the version and the actual paths of both `java` and `javac`.

## 9. Checklist to Confirm the JDK Is Ready

You can check off each item in order:

- [ ] `java -version` runs successfully and displays the expected version.
- [ ] `javac -version` runs successfully and displays the expected compiler version.
- [ ] The paths for `java` and `javac` belong to the intended JDK.
- [ ] `JAVA_HOME` (if used) points to the JDK root directory.
- [ ] `PATH` includes the desired JDK's `bin` directory.
- [ ] The `JdkCheck.java` program compiles and runs successfully.

Once all items relevant to your project environment pass, the JDK is ready for learning, compiling, and running Java programs. For Maven, Gradle, or IDEs, also check each tool's own JDK configuration to ensure they all use the same expected version.
