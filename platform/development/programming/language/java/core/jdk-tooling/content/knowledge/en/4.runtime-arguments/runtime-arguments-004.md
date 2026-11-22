# Environment Variables in the Java Runtime

Environment variables are name–value pairs that the operating system provides to a process. When running a Java application, this environment can affect locating the JDK, selecting the Java executable, determining the default classpath, passing options to the JVM, or configuring build tools. Some variables are recognized directly by the Java launcher or JVM; others only have meaning for the shell, IDE, Maven, Gradle, or the application itself.

It is important to distinguish between an **environment variable**, a **JVM option**, and a **Java system property**:

- An environment variable belongs to the process's environment, for example `JAVA_HOME` or `APP_ENV`.
- A JVM option is an argument passed when launching the JVM, for example `-Xmx1g`, `-ea`, or `-Dapp.mode=prod`.
- A system property is a value the JVM stores in its properties system, which can be read with `System.getProperty("app.mode")`.
- A Java application reads an environment variable using `System.getenv("APP_ENV")`.

An environment variable affects Java only when the launcher, JVM, a library, an external tool, or the application itself is designed to read that variable. Not every environment variable automatically becomes a system property.

## 1. How Does the Process Environment Work?

When a user opens a terminal, the shell has an environment consisting of multiple variables. When the shell launches `java`, the Java process typically receives a copy of the environment inherited from the parent process. Child processes created by Java also typically inherit the Java process's environment, unless the application explicitly modifies the environment when creating the process.

For example, if the terminal has:

~~~text
APP_ENV=staging
~~~

then a Java program launched from that terminal can read `APP_ENV` using `System.getenv("APP_ENV")`.

Key points to remember:

- Changing an environment variable in one terminal usually affects only that terminal and child processes created after the change.
- Changing the environment in the current terminal does not automatically update the environment of an IDE that was opened earlier.
- Each process has its own environment; a Java process cannot modify the environment of the parent process running it.
- Environment variables are inherited at the time of process creation. If you modify a variable in the shell after Java has already started, the running Java process does not automatically pick up the new value.
- Environment variable names are case-sensitive on Unix-like systems; on Windows, variable names are generally case-insensitive. Using uppercase names consistently makes configurations easier to read.

This model explains why a command may work in one terminal but fail in another terminal, an IDE, a system service, or a container: those processes may receive different environments.

## 2. Important Environment Variables in Java Development

### 2.1. `JAVA_HOME`

`JAVA_HOME` is commonly used to specify the root directory of the JDK that a project or build tool should use. This is a widespread convention in the Java ecosystem, and many external tools read this variable.

Example paths:

~~~text
Windows:  C:\Program Files\Java\jdk-17
macOS:    /Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home
Linux:    /usr/lib/jvm/jdk-17
~~~

These paths are examples only; the actual directory depends on the vendor, installation method, and operating system.

`JAVA_HOME` should point to the JDK root directory, where directories such as `bin`, `lib`, and other components reside. Do not set it to point directly to `bin`.

`JAVA_HOME` is often used by build tools such as Maven, the Gradle wrapper, or project scripts to locate the JDK. The Java launcher itself does not need `JAVA_HOME` if the shell already finds the right `java` executable via PATH. Therefore, setting `JAVA_HOME` correctly does not automatically guarantee that the `java` and `javac` commands are being selected from the same JDK.

### 2.2. `PATH`

`PATH` is the list of directories that the shell or operating system searches when the user runs a command without specifying its full path. Adding the JDK's `bin` directory to PATH allows calling `java`, `javac`, `jar`, `javadoc`, and other tools from any working directory.

For example, if `JAVA_HOME` points to the JDK, the directory to add is typically:

~~~text
Windows:  %JAVA_HOME%\bin
macOS/Linux: $JAVA_HOME/bin
~~~

When multiple Java installations exist, the order of directories in PATH determines which executable is found first. Because of this, `java --version` and `javac --version` may reflect a different JDK than `JAVA_HOME`.

Check on Windows:

~~~powershell
where.exe java
where.exe javac
Get-Command java
~~~

Check on macOS/Linux:

~~~sh
command -v java
command -v javac
which -a java
which -a javac
~~~

If multiple paths are returned, check the PATH order and the IDE/build tool configuration. Avoid assuming that the first Java version displayed is the one used by every tool on the machine.

### 2.3. `CLASSPATH`

`CLASSPATH` can provide a default classpath for the Java launcher when a standard class-running command does not specify `-cp`, `-classpath`, or `--class-path`.

The classpath specifies the directories and JARs that the JVM uses to locate classes and resources. For example:

~~~text
Windows:  .;lib/app.jar;lib/*
macOS/Linux: .:lib/app.jar:lib/*
~~~

The entry separator character depends on the operating system:

- Windows uses a semicolon `;`.
- macOS/Linux uses a colon `:`.

The dot `.` represents the current working directory. The pattern `lib/*` adds the JARs in the `lib` directory to the classpath.

In projects with a build tool, let Maven/Gradle or the run script provide the required classpath instead of relying on a global CLASSPATH. A pre-configured CLASSPATH can cause the application to pick up an unintended library version.

`java -cp ...` or `--class-path ...` specifies an explicit classpath for that run and overrides the default value from the CLASSPATH variable. When using `java -jar app.jar`, the default classpath from CLASSPATH is not used to supplement dependencies as in standard class-running mode; configure dependencies according to the JAR packaging or an appropriate launch method.

## 3. Environment Variables for Passing JVM Options

### 3.1. `JDK_JAVA_OPTIONS`

`JDK_JAVA_OPTIONS` has been supported by the Java launcher since JDK 9. The contents of this variable are prepended by the launcher before the command-line options and arguments when starting Java.

Example:

~~~text
JDK_JAVA_OPTIONS=-Dapp.mode=staging -Xmx512m
~~~

When running:

~~~text
java -cp out Main
~~~

the JVM receives the system property `app.mode=staging` and a maximum heap of 512 MB. The application can read the property with `System.getProperty("app.mode")`.

This variable is useful when you want to apply a group of options to multiple `java` commands in the same environment, such as logging configuration or a shared system property. However, because the launcher automatically prepends these options, operators might not realize why the application has a different configuration than what is visible in the script's command.

A few notes:

- The content is parsed into arguments according to the launcher's rules; paths containing spaces must be properly quoted.
- Options in the variable are added before command-line options. For repeated options, how the final value is handled depends on the rules of that specific option; do not assume every flag follows the same override rule.
- The Java launcher may print a message indicating that `JDK_JAVA_OPTIONS` is being used.
- This variable applies to Java launcher invocations created in an environment that inherits it. If the application launches a child Java process, the child process may continue to receive this variable.

When a command behaves unexpectedly, check `JDK_JAVA_OPTIONS` before concluding that the script is missing options.

### 3.2. `JAVA_TOOL_OPTIONS`

`JAVA_TOOL_OPTIONS` is inspected by the JVM when a virtual machine is created. It allows adding JVM options even in scenarios where the JVM is initialized by an application or embedded environment where the user does not directly control the Java launcher command line.

Example:

~~~text
JAVA_TOOL_OPTIONS=-Dfile.encoding=UTF-8 -Xmx512m
~~~

A common use case is configuring a Java agent:

~~~text
JAVA_TOOL_OPTIONS=-javaagent:/opt/agents/monitoring-agent.jar
~~~

A Java agent can be used for monitoring, instrumentation, or application diagnostics. Only enable an agent when you trust its source and understand its impact.

Notes:

- The JVM typically prints the message `Picked up JAVA_TOOL_OPTIONS` when the variable is applied.
- This variable can affect multiple Java processes in the same environment, including build tools, child applications, or embedded JVMs.
- Some options are restricted in this context; not every launcher flag can be placed here.
- On some systems, the JVM may ignore this variable when the process runs with an effective user/group identity different from the real identity to mitigate security risks.
- If an agent or option is added unintentionally, the application may start slowly, consume extra memory, or change its behavior.

Do not set `JAVA_TOOL_OPTIONS` globally for the entire machine if only one application needs that configuration. Scope it to the corresponding script, service, or container.

### 3.3. Differences Between `JDK_JAVA_OPTIONS` and `JAVA_TOOL_OPTIONS`

Both variables can add options to the JVM, but they are applied at different layers:

| Variable | Component Reading It | When Applied | Typical Scope |
|---|---|---|---|
| `JDK_JAVA_OPTIONS` | Java launcher | When the launcher processes the command line, before directly passed options | Processes launched via the Java launcher that inherit the variable |
| `JAVA_TOOL_OPTIONS` | JVM upon VM creation | During JVM initialization | Both cases where the JVM is created by the launcher or a compatible embedded environment |

When you need to customize the `java` command in an application run script, `JDK_JAVA_OPTIONS` is usually easier to understand because it belongs to the launcher layer. When you need to supply options to a JVM initialized by another application, `JAVA_TOOL_OPTIONS` may be more appropriate.

Do not place the same option in both variables without understanding how the launcher/JVM handles duplicate values. Repeating `-D`, `-Xmx`, or `-javaagent` can cause confusion or change the outcome depending on processing order.

### 3.4. `_JAVA_OPTIONS`

`_JAVA_OPTIONS` appears in some JVM implementations, particularly HotSpot-based ones, as a mechanism for adding options. It is not a standard, portable Java environment interface specified like `JDK_JAVA_OPTIONS` or `JAVA_TOOL_OPTIONS`.

You may encounter the message `Picked up _JAVA_OPTIONS` in the terminal. If you see this message without knowing its origin, check your environment variables and system configuration.

Do not build deployment workflows that depend on `_JAVA_OPTIONS`, as its portability and behavior are implementation-dependent. Prefer explicit options in the run command or variables supported by the current JDK documentation.

## 4. Build-Tool-Specific Variables

Not every variable containing `JAVA` is processed directly by the Java launcher or JVM. Some variables are read by other tools:

| Variable | Commonly Used By | Purpose |
|---|---|---|
| `MAVEN_OPTS` | Maven | JVM options for the Maven process |
| `JAVA_HOME` | Maven, Gradle, IDEs, and scripts | Selecting the JDK installation |
| `GRADLE_OPTS` | Gradle launcher | JVM options for the Gradle client process |
| `JAVA_OPTS` | Many scripts or applications | Conventional name; meaning depends on the script |
| `JDK_JAVA_OPTIONS` | Java launcher | Adding options to the Java command |
| `JAVA_TOOL_OPTIONS` | JVM | Adding options when creating the VM |

Do not confuse `JAVA_OPTS` with a standard variable automatically read by the JVM. A script may expand `$JAVA_OPTS` when invoking `java`, but a standalone `java` command is under no obligation to read this variable.

With Gradle, JVM settings for the Gradle daemon can also come from `org.gradle.jvmargs` in `gradle.properties`. With an IDE, the JDK used to run the IDE, the JDK used to build, and the JDK used to run the application can be three separate configurations.

When changing the JDK version, check the terminal, IDE, Maven/Gradle wrapper, CI, and the application's runtime configuration.

## 5. Setting Environment Variables on Windows

### 5.1. Setting for the Current PowerShell Session Only

In PowerShell:

~~~powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-17'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
$env:APP_ENV = 'staging'
$env:JDK_JAVA_OPTIONS = '-Dapp.mode=debug -Xmx512m'
~~~

Then verify:

~~~powershell
java --version
javac --version
$env:JAVA_HOME
$env:APP_ENV
$env:JDK_JAVA_OPTIONS
where.exe java
where.exe javac
~~~

Changes via `$env:` apply only to the current PowerShell process and child processes launched from it. Closing the terminal ends the scope of these temporary changes.

Remove a variable from the current PowerShell environment:

~~~powershell
Remove-Item Env:JDK_JAVA_OPTIONS
~~~

### 5.2. Setting Persistent Variables for a User Account

You can set a variable at the User scope using PowerShell:

~~~powershell
[Environment]::SetEnvironmentVariable(
    'JAVA_HOME',
    'C:\Program Files\Java\jdk-17',
    'User'
)
~~~

To modify PATH persistently, be careful to preserve existing entries. You can use the Windows Environment Variables UI to add `%JAVA_HOME%\bin` to the user PATH. After making changes, open a new terminal or IDE so the process picks up the updated environment.

Do not overwrite the entire PATH with a value containing only the JDK directory, as this can prevent other commands from being found. When a machine has multiple JDKs, intentionally order PATH and re-verify with `where.exe java` and `where.exe javac`.

## 6. Setting Environment Variables on macOS and Linux

In Bash or Zsh, you can set variables for the current terminal using `export`:

~~~sh
export JAVA_HOME=/path/to/jdk-17
export PATH="$JAVA_HOME/bin:$PATH"
export APP_ENV=staging
export JDK_JAVA_OPTIONS="-Dapp.mode=debug -Xmx512m"
~~~

Verify:

~~~sh
java --version
javac --version
printf '%s\n' "$JAVA_HOME" "$APP_ENV" "$JDK_JAVA_OPTIONS"
command -v java
command -v javac
~~~

Remove a variable in the current shell:

~~~sh
unset JDK_JAVA_OPTIONS
~~~

On macOS, you can retrieve the appropriate JDK path using the system utility:

~~~sh
/usr/libexec/java_home -V
/usr/libexec/java_home -v 17
export JAVA_HOME="$(/usr/libexec/java_home -v 17)"
export PATH="$JAVA_HOME/bin:$PATH"
~~~

To set variables persistently for the shell, add the appropriate export commands to the configuration file used by your shell, such as `~/.zshrc` or `~/.bashrc`. Which file to edit depends on the shell and how the terminal initializes login/non-login shells.

For system services, do not assume the service will read a user's shell configuration file. Set variables in the service manager configuration, container, or service startup script.

## 7. Reading Environment Variables and System Properties in Java

A Java application has two different APIs for reading these two types of configuration:

- `System.getenv("NAME")` reads an environment variable.
- `System.getProperty("name")` reads a JVM system property.

Create the file `Main.java`:

~~~java
public class Main {
    public static void main(String[] args) {
        String env = System.getenv().getOrDefault("APP_ENV", "local");
        String mode = System.getProperty("app.mode", "default");

        System.out.println("APP_ENV=" + env);
        System.out.println("app.mode=" + mode);
    }
}
~~~

Compile:

~~~text
javac Main.java
~~~

Run on PowerShell:

~~~powershell
$env:APP_ENV = 'staging'
java -Dapp.mode=debug Main
~~~

Run on macOS/Linux:

~~~sh
APP_ENV=staging java -Dapp.mode=debug Main
~~~

Stdout output in both cases:

~~~text
APP_ENV=staging
app.mode=debug
~~~

In this example:

- `APP_ENV` is set in the process environment by the shell and read by Java using `System.getenv`.
- `app.mode` is passed via the `-D` option and read by Java using `System.getProperty`.
- The default values `local` and `default` are used if the respective configurations do not exist.

Do not use `System.getenv()` to read a system property, and do not use `System.getProperty()` to read an environment variable. The names and value-setting mechanisms of these two configuration types do not automatically map to each other.

### When to Use an Environment Variable vs. a System Property?

| Criterion | Environment Variable | System Property |
|---|---|---|
| Scope | The process environment and inherited child processes | A specific JVM |
| How to read in Java | `System.getenv("APP_ENV")` | `System.getProperty("app.mode")` |
| How to pass | Shell, service manager, container, or OS | `-Dapp.mode=value` or Java code |
| Suitable for | Deployment configuration, environment info, tool locations | JVM/application configuration for a single run |
| Inheritance | Usually inherited by child processes | Not automatically passed to child JVMs |

There is no rule that one is always better than the other. Choose based on the required scope and how the application is operated.

## 8. Inspecting and Diagnosing the Java Environment

When an application runs the wrong Java version or receives unexpected configuration, check in this order:

1. **Actual executable:** use `where.exe java`/`where.exe javac` on Windows or `command -v`/`which -a` on macOS/Linux.
2. **Runtime and compiler versions:** run `java --version` and `javac --version`.
3. **JAVA_HOME:** verify whether this variable points to the right JDK root directory.
4. **PATH:** determine which JDK comes first in the search order.
5. **Option-adding variables:** check `JDK_JAVA_OPTIONS`, `JAVA_TOOL_OPTIONS`, and `_JAVA_OPTIONS` if present.
6. **Default classpath:** check `CLASSPATH` if the command does not specify `-cp`.
7. **Tool configuration:** check the JDK of the IDE, Maven, Gradle, CI runner, or service.
8. **Process environment:** confirm that the terminal, service, or container actually receives the variables you just set.

To view some JVM properties:

~~~text
java -XshowSettings:properties -version
~~~

This command displays system properties and useful runtime information such as `java.home`, `java.version`, `os.name`, `user.dir`, and `file.encoding`. It is not a complete list of environment variables. To view environment variables inside an application, use `System.getenv()` or read specific variables individually.

You can run a small diagnostic snippet:

~~~java
public class EnvironmentCheck {
    public static void main(String[] args) {
        System.out.println("java.home=" + System.getProperty("java.home"));
        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("user.dir=" + System.getProperty("user.dir"));
        System.out.println("JAVA_HOME=" + System.getenv("JAVA_HOME"));
        System.out.println("CLASSPATH=" + System.getenv("CLASSPATH"));
        System.out.println("JDK_JAVA_OPTIONS=" + System.getenv("JDK_JAVA_OPTIONS"));
        System.out.println("JAVA_TOOL_OPTIONS=" + System.getenv("JAVA_TOOL_OPTIONS"));
    }
}
~~~

This is a diagnostic example; when sharing logs, be mindful of sensitive data that may appear in environment variables. Do not print the entire environment to production logs without filtering values.

## 9. Environment Differences Across Terminal, IDE, Service, and Container

### Terminal and IDE

An IDE is usually launched from the desktop environment or a shortcut, so it does not necessarily inherit variables you just set in a terminal. An IDE can also store separate JDKs for:

- The IDE's own runtime.
- The Project SDK or Java toolchain used for compilation.
- The JRE/JDK used to run Run/Debug configurations.
- The Maven/Gradle importer or daemon.

If the terminal runs Java 17 while the IDE runs Java 21, check each configuration independently. After changing User/System-level environment variables, restart the IDE so it picks up the new environment.

### System Services

A service running under a dedicated account may have a different PATH, JAVA_HOME, and permissions than a logged-in user. Service configuration must declare environment variables in the appropriate service manager or wrapper. Do not rely on `.bashrc`, `.zshrc`, or interactive profiles if the service does not run that shell.

### CI/CD

In CI, explicitly declare the JDK in the toolchain setup step and verify the version directly in the job. Do not assume runners always have the same JAVA_HOME or PATH across images/agents. If build caching is enabled, ensure the cache does not mix artifacts built by incompatible JDK versions.

### Containers

In a container, set JAVA_HOME and PATH in the image or runtime configuration according to the chosen base image. If using a variable like `JDK_JAVA_OPTIONS`, clearly identify which container should receive it and whether it affects auxiliary Java processes. Environment variables declared in a container can be viewed via metadata/container inspection; do not use environment variables as a secrets store if the platform provides a dedicated secret manager.

## 10. Security and Operations

Environment variables are convenient for configuration, but they are not an absolute secrets store.

- Avoid placing passwords, long-lived tokens, or private keys directly in environment variables if a suitable secret management solution is available.
- Environment variables can be exposed through diagnostic tools, logs, crash reports, CI configurations, or process-reading permissions depending on the operating system.
- `JDK_JAVA_OPTIONS` and `JAVA_TOOL_OPTIONS` can silently attach agents or alter heap, system properties, and JVM behavior. Strictly control where these two variables are set.
- A Java agent can execute code inside the application process. Only use agents from trusted sources and manage agent versions as critical dependencies.
- Avoid logging the entire environment. Only log allowlisted names and values, and mask sensitive information.
- When running an application with a service account, container, or CI runner, restrict read/write permissions and secret access according to the principle of least privilege.

For production environments, document the required configuration variables, safe default values, and their management sources. Configuration changes must be auditable and reproducible.

## 11. Common Errors

### `JAVA_HOME` Points to the Wrong Directory

**Symptom:** Maven/Gradle or a script reports that Java cannot be found, even though the `java` command works.

**Cause:** JAVA_HOME points to `bin`, an old JRE, or a JDK directory that no longer exists.

**Solution:** Set JAVA_HOME to the JDK root directory, verify the `bin` directory inside it, and re-run the tool from a new terminal.

### `java` and `javac` Use Two Different JDKs

**Symptom:** The compiler reports one version while the runtime displays another; class version errors may occur.

**Cause:** PATH contains multiple JDKs, or JAVA_HOME and PATH are out of sync.

**Solution:** List all paths using `where.exe` or `which -a`, adjust the PATH order, and configure the IDE/build tool to use the right JDK.

### JVM Picks Up Unintended Options

**Symptom:** The terminal prints `Picked up ...`; the application has a heap size or system property different from the script.

**Cause:** `JDK_JAVA_OPTIONS`, `JAVA_TOOL_OPTIONS`, or `_JAVA_OPTIONS` is set in the user, service, or container environment.

**Solution:** Check each variable in the actual parent process; remove or adjust the variable at its configuration source. Start a new process after making changes and verify again with the run command.

### `ClassNotFoundException` or `NoClassDefFoundError`

**Symptom:** The application cannot find a class or dependency at runtime.

**Cause:** Incorrect CLASSPATH, missing JAR, unexpected working directory, or classpath affected by an environment variable.

**Solution:** Check `CLASSPATH`, use `-cp` explicitly, and verify paths to packages/JARs. For an executable JAR, check the manifest and how dependencies are packaged.

### Works in Terminal, Fails in IDE

**Symptom:** The same command or project runs from the terminal but fails in the IDE.

**Cause:** The IDE uses its own stored environment or JDK, or has not been restarted after updating environment variables.

**Solution:** Check the Project SDK, Run Configuration, and Maven/Gradle JDK, and restart the IDE if necessary.

### Variable Changed, but Running Java Process Does Not Update

**Symptom:** Updating a variable in the terminal leaves the running application using the old value.

**Cause:** The process received a copy of the environment when it was created.

**Solution:** Restart the Java process from the updated environment. Changing the shell's environment does not retroactively update an existing child process.

## 12. Java Runtime Configuration Checklist

Before running an application or investigating an issue, check:

- [ ] `JAVA_HOME` points to the root directory of the desired JDK.
- [ ] PATH prioritizes the right `bin` directory.
- [ ] `java --version` and `javac --version` reflect the expected versions.
- [ ] `CLASSPATH` does not accidentally introduce old dependencies into the application.
- [ ] `JDK_JAVA_OPTIONS` and `JAVA_TOOL_OPTIONS` contain only intentionally applied options.
- [ ] Workflows requiring portability do not depend on `_JAVA_OPTIONS`.
- [ ] Environment variables for the IDE, service, CI, and container are configured in the right scope.
- [ ] Sensitive configurations are managed securely and not written to logs.
- [ ] The run command and required environment can be reproduced on another machine.

Environment variables are part of the runtime configuration because they affect how tools locate the JDK, how the launcher starts the JVM, and how the application receives configuration. When you clearly distinguish `JAVA_HOME`, `PATH`, `CLASSPATH`, `JDK_JAVA_OPTIONS`, `JAVA_TOOL_OPTIONS`, and build-tool-specific variables, you gain better control over the Java environment and can diagnose issues faster.
