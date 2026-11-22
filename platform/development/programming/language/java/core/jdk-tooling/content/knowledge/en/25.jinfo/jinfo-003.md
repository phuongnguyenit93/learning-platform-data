# Reading System Properties with jinfo

`jinfo` is a diagnostic tool included with the JDK for reading configuration information from a running Java process. For system properties, the key command is `jinfo -sysprops <pid>`: it instructs the target JVM to print system properties as name-value pairs.

System properties affect how Java applications and libraries behave. They can contain information initialized by the JDK, values passed via the `-Dname=value` option at startup, or values set by the application at runtime using `System.setProperty()`. Reading them from a running process helps confirm the configuration the JVM holds at the time of inspection.

Keep in mind that `jinfo` is marked as experimental and unsupported by Oracle in the JDK 21 documentation. The tool may change or be removed in future JDK releases. For modern JDK environments, `jcmd <pid> VM.system_properties` is the appropriate alternative for printing system properties.

## 1. What Is a System Property?

A system property is an entry in the `java.util.Properties` object exposed by the JVM via `System.getProperties()`. Each property has a string name and a string value.

Example:

```java
String version = System.getProperty("java.version");
String workingDirectory = System.getProperty("user.dir");
String profile = System.getProperty("app.profile");
```

Common standard system properties:

| Property | Meaning |
|---|---|
| `java.version` | Java runtime version |
| `java.vendor` | JDK vendor |
| `java.home` | Java installation/runtime directory |
| `java.class.path` | Application classpath |
| `java.library.path` | Path for locating native libraries |
| `user.dir` | Current working directory of the process |
| `user.home` | Home directory of the account running the JVM |
| `user.name` | Operating system account name from the environment |
| `os.name` | Operating system name |
| `os.arch` | Operating system architecture |
| `file.encoding` | Default charset reported by the runtime |
| `line.separator` | Platform-specific line separator |
| `java.io.tmpdir` | Temporary directory |
| `user.timezone` | Time zone property if configured/initialized |

Applications can define custom properties such as `app.profile`, `service.region`, or `feature.checkout.enabled`. Libraries may also read system properties to select behavior.

Specific values depend on the JDK, operating system, launch configuration, and application code. Do not assume every property always exists or has the same value across all environments.

## 2. What Does jinfo -sysprops Do?

Primary syntax:

```sh
jinfo -sysprops <pid>
```

`-sysprops` instructs the tool to print Java system properties as name-value pairs. `<pid>` is the process ID of the JVM to inspect.

Example:

```sh
jinfo -sysprops 24680
```

The output might contain lines like:

```text
java.version=21.0.x
java.home=/opt/jdk-21
java.class.path=out
user.dir=/opt/app
app.profile=staging
app.region=ap-southeast-1
```

This is a truncated illustrative output; the actual order and values depend on the process. The real command typically prints many more properties than shown here.

`jinfo` reads the state of the target JVM at the moment of the query. If the application has modified a property using `System.setProperty()`, the current value may be reflected in the output. However, this only shows the value in the system-properties map; a library that already read and cached the property earlier may still be using the old configuration.

## 3. Finding the PID of a Java Process

`jinfo` requires the PID of a Java process. You can list JVMs using:

```sh
jps -l
```

Example:

```text
24680 com.example.SystemPropertiesDemo
25120 com.example.OrderService
```

After identifying the process, use its PID:

```sh
jinfo -sysprops 24680
```

If `jps` does not display the process, you can use operating system tools.

Linux/macOS:

```sh
ps -ef
```

Windows PowerShell:

```powershell
Get-Process java, javaw -ErrorAction SilentlyContinue
```

In containers, the PID seen from the host may differ from the PID inside the container. Run the tool inside the appropriate container/PID namespace, or determine the PID within the namespace accessible to the tool. `jps` may not list JVMs running inside isolated Docker processes.

Do not pick a PID simply because it appears first. Cross-check the main class/JAR name, command line, or service details to avoid inspecting the wrong application.

## 4. Requirements for Attaching to the Target JVM

`jinfo` must connect to the running JVM to read data. In standard operations:

- Run on the same machine as the target JVM.
- Use an operating system account with appropriate attach permissions; typically, use the same user that launched the JVM.
- Verify that the PID still exists and belongs to the right Java process.
- Use a JDK/tool compatible with the target runtime.
- Ensure the attach mechanism is not disabled or blocked by policies, containers, or the operating system.
- For containers, use the correct PID namespace and process access permissions.

On some Windows configurations, the `jinfo` documentation notes that if `dbgeng.dll` is missing, you need to install Debugging Tools for Windows; the `PATH` environment variable must include the location of `jvm.dll` corresponding to the target process. This is an environment-specific requirement, not a mandatory step on every Windows machine.

If attach fails, check the process, user, JDK, namespace, and error message before concluding that a property does not exist. An attach failure is a process connection issue; it does not prove that the system properties content is wrong.

## 5. Distinguishing -sysprops, -flags, and No Options

`jinfo` can display both system properties and JVM command-line flags.

| Command | Content |
|---|---|
| `jinfo -sysprops <pid>` | Prints only Java system properties |
| `jinfo -flags <pid>` | Prints JVM flags passed at startup |
| `jinfo <pid>` | Prints both JVM flags and system properties |
| `jinfo -flag <name> <pid>` | Prints the value of a specific JVM flag |
| `jinfo -help` | Prints help information |

Example:

```sh
jinfo 24680
```

When run without options, the JDK 21 documentation confirms the tool prints both command-line flags and system property name-value pairs. As a result, the output can be much longer than with `-sysprops`.

Do not confuse the following:

| Example | Type |
|---|---|
| `-Dapp.profile=staging` | System property set from the Java launcher |
| `app.profile=staging` in `-sysprops` output | Current system property value |
| `-Xmx2g` | JVM flag, not a system property |
| `-XX:+UseG1GC` | JVM flag |
| `-XX:MaxRAMPercentage=75` | JVM flag |
| `java.version` | Standard system property |

`-flags` and `-flag` operate on JVM flags. They are not ways to read or update system properties.

## 6. Distinguishing System Properties and Environment Variables

System properties and environment variables are two distinct configuration sources.

| Aspect | System Property | Environment Variable |
|---|---|---|
| Read API | `System.getProperty(name)` | `System.getenv(name)` |
| Passed at startup | `-Dname=value` | Set in shell/service/container |
| Modified in Java | `System.setProperty(name, value)` | No standard Java API to modify the process environment |
| Inspection tool | `jinfo -sysprops` or `jcmd PID VM.system_properties` | Operating system/container tools |
| Scope | JVM process | Inherited process environment |

Example:

```java
String profile = System.getProperty("app.profile");
String region = System.getenv("APP_REGION");
```

If you only set the `APP_REGION` environment variable, do not expect it to appear automatically in `jinfo -sysprops`. The application must read the environment variable and, if needed, explicitly set it as a system property.

Similarly, `System.setProperty("app.profile", "staging")` does not create or modify an operating system environment variable.

## 7. How System Properties Are Created and Modified

There are three common sources.

### 7.1. Properties Initialized by the JVM

The JDK provides standard properties such as `java.version`, `java.home`, `os.name`, and `user.dir`. Their values are determined by the runtime, launcher, and operating system environment.

### 7.2. Properties Passed via -D

Set properties at startup:

```sh
java -Dapp.profile=staging -Dapp.region=ap-southeast-1 -cp out com.example.OrderService
```

The Java launcher places these name-value pairs into the JVM's system properties. They can be read in the application using:

```java
String profile = System.getProperty("app.profile");
String region = System.getProperty("app.region");
```

Once the process is running, you can inspect them:

```sh
jinfo -sysprops <pid>
```

Look for the `app.profile` and `app.region` lines.

### 7.3. Properties Set in Code

The application can set or modify properties at runtime:

```java
System.setProperty("app.runtime.mode", "diagnostic");
```

Read it back:

```java
String mode = System.getProperty("app.runtime.mode");
```

Remove a property:

```java
System.clearProperty("app.runtime.mode");
```

These changes affect the system-properties map in the current JVM. They do not automatically write to the command line, configuration files, or environment variables.

## 8. Java 17+ Example: Observing Runtime Properties with jinfo

The following example creates a long-running JVM, sets one property at startup and another after the program starts. This allows you to inspect both with `jinfo`.

Create `SystemPropertiesDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class SystemPropertiesDemo {
    public static void main(String[] args) throws InterruptedException {
        System.setProperty("app.runtime.mode", "diagnostic");

        System.out.println(
            "PID=" + ProcessHandle.current().pid());
        System.out.println(
            "launch.profile=" + System.getProperty("launch.profile"));
        System.out.println(
            "runtime.mode=" + System.getProperty("app.runtime.mode"));

        new CountDownLatch(1).await();
    }
}
```

Compile:

```sh
javac SystemPropertiesDemo.java
```

Run with a system property from the launcher:

```sh
java -Dlaunch.profile=staging SystemPropertiesDemo
```

Program output:

```text
PID=24680
launch.profile=staging
runtime.mode=diagnostic
```

`24680` is an illustrative PID; the actual value is returned by `ProcessHandle.current().pid()`. The program waits indefinitely so the process remains alive while you open a second terminal.

In the second terminal, run:

```sh
jinfo -sysprops 24680
```

Look for the lines:

```text
launch.profile=staging
app.runtime.mode=diagnostic
```

The full `jinfo` output includes many additional JDK and environment properties. After inspecting, return to the first terminal and press Ctrl+C to stop the demo program.

This example demonstrates that both properties passed via `-D` and properties set via `System.setProperty()` belong to the system-properties map held by the application.

## 9. Reading a Specific Property in an Application

`jinfo -sysprops` prints the entire list, so the output can be long. If you only need a single property, you can filter the output using shell tools.

Linux/macOS:

```sh
jinfo -sysprops 24680 | grep '^app.profile='
```

Windows PowerShell:

```powershell
jinfo -sysprops 24680 | Select-String '^app.profile='
```

Example searching for multiple properties:

```sh
jinfo -sysprops 24680 | grep -E '^(app.profile|app.region|user.dir)='
```

Filtering the output helps you read faster, but it does not alter anything inside the JVM. If a property does not appear, the key may not have been set, may have been cleared, may be misspelled, or the version/tool may not return what you expect. Verify inside the application itself using `System.getProperty()` when needed.

On Windows, `Select-String` is a PowerShell cmdlet; `grep` syntax is typically used on Linux/macOS or in environments with GNU tools.

## 10. jinfo Only Reads System Properties, It Does Not Reconfigure the Application

`jinfo -sysprops` is a read-only command. It provides no option to modify a system property in a running JVM.

If you need to change a property in an application, you must use a configuration mechanism supported by the application, such as:

- Setting `-Dname=value` before the JVM starts.
- Reading a configuration file or configuration service.
- Calling `System.setProperty()` from controlled code.
- Using the application's own management API if available.

Note that `jinfo -flag` can enable/disable or set values for certain JVM flags. That is a separate operation from system properties. For example, `jinfo -flag +PrintGC <pid>` affects a VM flag if the JVM supports that flag; it does not create a `PrintGC` property.

Do not mistakenly use `-flag` syntax to try to modify a line in the `-sysprops` output. Both configuration types have their own APIs and rules.

## 11. System Property Values Can Differ from a Library's Effective Configuration

Being able to read a property does not mean every component in the JVM is using its latest value.

For example:

- The application calls `System.setProperty("app.profile", "production")`; code reading the property afterward sees the new value.
- A library already read `app.profile` during initialization and stored it in a field; it may continue using the old value.
- A JDK API might cache the default charset, timezone, or configuration when a class/object is initialized.
- A framework might only read system properties at startup and then build its own configuration object.

Therefore, when debugging:

1. Use `jinfo -sysprops` to view the value in the system-properties map.
2. Identify which component reads that property and when it reads it.
3. Check whether the component caches the value.
4. Check application logs or configuration endpoints to see the actual value used by the component.
5. If a property is only read at startup, changing it usually requires a restart or a reload via the framework's official mechanism.

Do not conclude that the entire application's configuration has changed based on a single line from `jinfo`.

## 12. System Properties, Security Properties, and JVM Flags

These three groups have different names and inspection tools:

| Group | Examples | How to Read |
|---|---|---|
| System properties | `java.version`, `user.dir`, `app.profile` | `System.getProperty()`, `jinfo -sysprops` |
| Security properties | `keystore.type`, `jdk.tls.disabledAlgorithms` | `Security.getProperty()` |
| JVM flags | `-Xmx2g`, `-XX:+UseG1GC` | `jinfo -flags`, `jinfo -flag`, `jcmd PID VM.flags` |

Security properties are managed by `java.security.Security` and configured in `java.security`. They do not automatically become system properties and are not what `jinfo -sysprops` is designed to print.

JVM flags control the VM, such as heap, GC, or the compiler. They are not name-value pairs in the system-properties map.

If you need to inspect all three groups, use the appropriate tool for each rather than relying on a single command.

## 13. Alternative with jcmd VM.system_properties

Oracle JDK 21 provides the `VM.system_properties` diagnostic command via `jcmd`:

```sh
jcmd 24680 VM.system_properties
```

This command prints the system properties of the specified JVM. It is the right choice for `jcmd`-based diagnostic workflows.

Related commands:

| Command | Purpose |
|---|---|
| `jcmd -l` | Lists observable JVM processes |
| `jcmd <pid> help` | Lists diagnostic commands supported by the JVM |
| `jcmd <pid> VM.system_properties` | Prints system properties |
| `jcmd <pid> VM.flags` | Prints current JVM flags |
| `jcmd <pid> VM.command_line` | Prints the command line used to launch the JVM |

Examples:

```sh
jcmd 24680 VM.system_properties
jcmd 24680 VM.flags
jcmd 24680 VM.command_line
```

Before running a diagnostic command, you can query the target JVM:

```sh
jcmd 24680 help VM.system_properties
```

`jcmd` must run on the same machine as the JVM and use an effective user/group ID compatible with the account that launched the JVM. According to the JDK 21 documentation, `VM.system_properties` has a Low impact.

If you are building new operational workflows, prefer supported `jcmd` commands over `jinfo` because `jinfo` is marked experimental and unsupported.

## 14. Security Considerations When Reading System Properties

System properties may contain sensitive or internal information:

- Deployment paths, user directories, and classpaths.
- Service names, profiles, regions, hostnames, or endpoints.
- Tokens, passwords, or credentials if the application passes them via `-D`.
- Truststore/keystore paths and sometimes passwords if misconfigured.
- Package names, libraries, and internal application structure.

Do not pass secrets directly via:

```sh
java -Ddb.password=secret -Dapi.token=secret ...
```

These values can appear in system-properties dumps, command lines, process inspection, or diagnostic logs. Use a secret manager, credential provider, or protected secret-delivery mechanism.

When sharing `jinfo`/`jcmd` output:

1. Collect only the properties you actually need.
2. Mask passwords, tokens, keys, and sensitive identifiers.
3. Store files in directories with restricted access permissions.
4. Do not attach full dumps to public issues.
5. Delete temporary copies according to retention policies after the investigation.

## 15. Common Errors When Using jinfo -sysprops

| Symptom | Common Cause | Resolution |
|---|---|---|
| `jinfo: command not found` | JDK is not installed or `JAVA_HOME/bin` is not in PATH | Use the correct JDK and check `where jinfo`/`which jinfo` |
| `Could not find process` | Wrong PID, process stopped, or different PID namespace | Use `jps -l`/`ps` to re-identify the process |
| Attach refused | Different user, OS permissions, or attach mechanism blocked | Check account, permissions, and runtime configuration |
| JVM not visible in `jps` | JVM is in a separate container or tool lacks visibility | Find the PID in the right namespace using OS tools |
| Expected property missing | Key not set, misspelled, or cleared | Check key name and `System.getProperty()` in the application |
| Value in dump differs from application logs | Component cached the value or uses another config source | Check when the property is read and the configuration object |
| Used `-flag` but cannot find system property | `-flag` operates on JVM flags, not system properties | Use `-sysprops` to read properties |
| Output is too long | JVM has many standard and custom properties | Filter by the target key or use appropriate parsing tools |
| Windows reports missing `dbgeng.dll` | Missing Debugging Tools for Windows in required environment | Install the appropriate debugging tools and check PATH/`jvm.dll` |
| Tool unavailable in newer JDKs | `jinfo` is experimental/unsupported and may change or be removed | Use `jcmd PID VM.system_properties` if supported by the JVM |

When an error occurs, verify the PID, attach permissions, and tool version first. If attach succeeds but a key is missing, investigate how the application sets the property and when the component reads it.

## 16. Operational Workflow for Checking System Properties

1. Identify the application and PID using `jps -l` or OS process tools.
2. Confirm you are operating in the right host/container and have attach permissions.
3. Run `jinfo -sysprops <pid>` if the environment still supports `jinfo`.
4. Locate the property relevant to the incident.
5. Distinguish between `-D` properties, JDK defaults, and runtime-modified properties.
6. Cross-check with environment variables, config files, and application logs as needed.
7. Check whether the component caches the value.
8. Use `jcmd <pid> VM.system_properties` when an alternative tool is needed.
9. Mask sensitive information before saving or sharing output.
10. Record the JDK version, PID, timestamp, and command used for reproducibility.

Do not modify application configuration based on a single property alone. Identify the component reading the property, configuration precedence rules, and when changes take effect before altering the environment.

## 17. Checklist

- [ ] Identified the correct JVM PID.
- [ ] Confirmed attach permissions and host/container environment.
- [ ] Used `jinfo -sysprops <pid>` to read system properties.
- [ ] Distinguished system properties from JVM flags and security properties.
- [ ] Understood default properties, `-D` properties, and properties set in code.
- [ ] Distinguished system properties from environment variables.
- [ ] Checked whether the property is cached by a component.
- [ ] Used `jcmd <pid> VM.system_properties` when an alternative tool was needed.
- [ ] Avoided using `-flag` to modify a system property.
- [ ] Masked passwords/tokens and sensitive information in output.
- [ ] Recorded the JDK version, PID, and inspection timestamp.

## 18. References

- Oracle JDK 21 Tool Reference — The `jinfo` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jinfo.html
- Oracle JDK 21 Tool Reference — The `jcmd` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Java SE 21 API — `java.lang.System`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html
- Java SE 21 API — `java.util.Properties`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Properties.html

`jinfo -sysprops` helps read the system properties a JVM holds at the time of inspection. Use the right PID, distinguish system properties from JVM flags and environment variables, check for library caching effects, and consider `jcmd PID VM.system_properties` for modern diagnostic workflows.