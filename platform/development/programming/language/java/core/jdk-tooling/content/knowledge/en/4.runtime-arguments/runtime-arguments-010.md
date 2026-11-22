# Inspecting Effective Java Runtime Arguments

## Objectives

After this lesson, you will be able to distinguish between Java launcher, JVM, and application arguments; identify sources that add arguments at startup; inspect the configuration of a running Java process using `jcmd`; read system properties and VM flags from within an application; and determine why the effective values differ from the configuration you thought you passed in.

## 1. What Are “Effective Runtime Arguments”?

When a Java application runs, multiple groups of arguments together affect how the program behaves. Not all of them are a single type of “JVM argument”.

| Group | Example | Where Handled |
|---|---|---|
| Java launcher options | -cp, --module-path, -jar, --add-modules | Java launcher |
| JVM options / VM flags | -Xms, -Xmx, -Xss, -XX:+UseG1GC | JVM implementation |
| System properties | -Dapp.mode=prod, -Duser.timezone=UTC | Java runtime, read via System.getProperty |
| Environment variables | JAVA_TOOL_OPTIONS, JDK_JAVA_OPTIONS, CLASSPATH | Shell, launcher, or custom JVM |
| Application arguments | --mode prod, input.csv | main method or application argument parser |
| Application configuration | application.yml, config.properties, framework command-line options | The application itself or framework |

An example:

~~~bash
java -Xms256m -Xmx1g -Dapp.mode=prod -cp app.jar com.example.Main --port 8080
~~~

In this command:

- -Xms256m and -Xmx1g configure the initial heap and maximum heap.
- -Dapp.mode=prod sets a system property named app.mode.
- -cp app.jar configures the classpath for the launcher.
- com.example.Main is the main class.
- --port 8080 are two application arguments, passed into main(String[] args).

Therefore, when inspecting arguments, you must first determine whether you want to know the **launch command**, the **currently effective VM flags**, the **current system properties**, or the **arguments received by the application**. A single inspection command does not fully answer all four questions.

## 2. Declared Values vs. Effective Values

There are three types of information that are often confused:

1. **Intended configuration:** arguments written in a script, Dockerfile, service unit, IDE, or configuration file.
2. **Startup arguments:** the launcher/JVM options actually supplied when the process starts.
3. **Current runtime state:** the values currently used by the JVM or system properties after the application may have modified them.

For example, the application launch file might specify -Xmx2g, but the running service is actually started by another script with -Xmx1g. Or the JVM starts with -Dapp.mode=dev, but application code calls System.setProperty("app.mode", "prod") afterward. In that case, the current value of the system property is prod, even though the initial startup argument was dev.

To verify, cross-check the configuration source against the running process. When you need to know the current heap limit, read the VM flags of the exact PID. When you need to know the property that the code is reading, read System.getProperty or VM.system_properties. When you need to know the application arguments, inspect args or application logs.

## 3. Places Where Arguments Can Be Added

### 3.1. The java Command Line

Arguments can be written directly in the launch command:

~~~bash
java -Xms256m -Xmx1g -Dapp.mode=prod -jar app.jar --port 8080
~~~

Order matters: JVM and launcher options go before the execution target; application arguments go after the class, JAR, module, or source file.

### 3.2. JDK_JAVA_OPTIONS

JDK_JAVA_OPTIONS is an environment variable read by the Java launcher. Its contents are prepended before the options passed directly on the java command line.

Example on Linux/macOS:

~~~bash
export JDK_JAVA_OPTIONS="-Xms256m -Dapp.mode=staging"
java -Xmx1g -jar app.jar
~~~

The launcher processes them as if the options from the environment variable were placed before the direct options. When this variable is set, the launcher prints a notice on stderr.

Check the variable:

~~~bash
echo "$JDK_JAVA_OPTIONS"
~~~

On Windows PowerShell:

~~~powershell
$env:JDK_JAVA_OPTIONS
~~~

### 3.3. JAVA_TOOL_OPTIONS

JAVA_TOOL_OPTIONS is processed when the JVM is created through the JNI Invocation API. It is useful when the launch command line is hard to access, such as an application embedding a JVM or a process started through multiple layers of scripts.

Example:

~~~bash
export JAVA_TOOL_OPTIONS="-Dapp.region=ap-southeast-1 -Xmx1g"
~~~

This variable adds options to the JVM at initialization time. It does not replace options handled by the Java launcher such as selecting the class, -jar, or classpath. In some environments, JAVA_TOOL_OPTIONS may be disabled for security reasons.

Check the variable:

~~~bash
echo "$JAVA_TOOL_OPTIONS"
~~~

On Windows PowerShell:

~~~powershell
$env:JAVA_TOOL_OPTIONS
~~~

### 3.4. @argfile Argument Files

When the command line is long, the Java launcher allows placing options into a file and passing the filename prefixed with @.

Example jvm.args file:

~~~text
-Xms256m
-Xmx1g
-Dapp.mode=prod
-Duser.timezone=UTC
~~~

Launch:

~~~bash
java @jvm.args -jar app.jar
~~~

The options in the file are expanded by the launcher before processing the command line. Therefore, when a script only contains the line java @jvm.args, you need to read the jvm.args file as well to know the actual arguments.

Relative paths in an argument file are resolved from the process's current working directory, not the directory containing the argument file.

### 3.5. Scripts, Services, and Build Tools

Arguments can also reside in:

- .bat, .cmd, .ps1, or shell scripts.
- Dockerfile, docker-compose, or Kubernetes configurations.
- Windows Services, systemd units, or other service managers.
- IDE run configurations.
- Gradle/Maven configurations and application-running plugins.
- Framework-specific configuration files.

Variables such as JAVA_OPTS, MAVEN_OPTS, or GRADLE_OPTS are often used by scripts/build tools by their own conventions. They are not a universal standard set of environment variables for all Java launchers. Read the script or documentation of the tool that spawns the process.

In particular, the JVM running the Gradle daemon may differ from the JVM running the application. When an application is run via a Gradle task, find the exact PID of the application process instead of only inspecting the Gradle daemon.

## 4. Finding the Java Process to Inspect

Before reading arguments, you must identify the right PID. A machine can run multiple JVMs simultaneously: applications, Gradle daemons, Maven, IDEs, servers, and other Java tools.

### Using jcmd

The following command lists the JVMs that the tool can detect:

~~~bash
jcmd -l
~~~

Illustrative example output:

~~~text
18420 com.example.OrderApplication
19210 org.gradle.launcher.daemon.bootstrap.GradleDaemon
~~~

Select the PID of the application to inspect. Do not confuse the PID of a Gradle daemon or IDE with the PID of the application process.

You can run jcmd with no arguments instead of jcmd -l.

### Using jps

The JDK also includes the jps tool:

~~~bash
jps -lmv
~~~

Options:

| Option | Information |
|---|---|
| -l | Full name of the main class or JAR path |
| -m | Arguments passed to the main method |
| -v | Arguments passed to the JVM |

jps is marked by Oracle as an experimental and unsupported tool; its output format may change and should not be used to build scripts that depend on parsing its output. Prefer jcmd for routine inspection workflows.

### When the Application Runs in Docker

jcmd -l on the host may not list JVMs running in a separate Docker process. Inspect from inside the container:

~~~bash
docker exec -it <container-name> sh
jcmd -l
~~~

Then run jcmd with the PID visible inside the container. If the image lacks a shell or JDK diagnostic tools, use tools appropriate for the image/runtime or inspect the PID from the right process namespace on the host.

## 5. Inspecting the Command Line of a Running JVM

Once you have the PID, use:

~~~bash
jcmd <pid> VM.command_line
~~~

This command prints the command line used to start the VM. It is a good starting point to look for arguments such as:

- -Xms and -Xmx.
- -Dproperty=value.
- -XX:+UseG1GC or other GC options.
- -javaagent or -agentlib.
- Class, JAR, or execution target.

Illustrative example output:

~~~text
VM Arguments:
jvm_args: -Xms256m -Xmx1g -Dapp.mode=prod
java_command: com.example.OrderApplication --port 8080
java_class_path (initial): app.jar
~~~

Field names and formatting may vary by version/JVM. Read the returned content rather than relying on a fixed output string.

Note: the command line shows startup information. It does not necessarily reflect all configuration changes made after the JVM has started.

## 6. Inspecting Effective VM Flags

Use:

~~~bash
jcmd <pid> VM.flags
~~~

This command prints VM flags and their current values. To view all flags supported by the VM, use:

~~~bash
jcmd <pid> VM.flags -all
~~~

Some commonly inspected flags:

| Flag | Meaning |
|---|---|
| InitialHeapSize | Initial heap used by the JVM |
| MaxHeapSize | Maximum heap limit |
| ThreadStackSize | Default stack size for Java threads |
| UseG1GC | Usage status of the G1 garbage collector |
| UseZGC | Usage status of ZGC if supported by the JVM |
| ActiveProcessorCount | Number of CPUs the JVM uses for certain internal decisions |
| MaxMetaspaceSize | Metaspace limit if configured |

Example:

~~~bash
jcmd 18420 VM.flags -all
~~~

Look for lines related to heap or GC in the output. If you need to determine the exact value of a flag, read the flag name and value directly from the result.

Not every JVM/vendor supports the same set of flags. Some flags are HotSpot-specific and may be removed or changed across versions. Use:

~~~bash
jcmd <pid> help
~~~

to see the diagnostic commands supported by the target JVM.

## 7. Inspecting System Properties

System properties are name/value pairs accessed from Java code via System.getProperty().

Example setting properties at startup:

~~~bash
java -Dapp.mode=prod -Dapp.region=ap-southeast-1 -jar app.jar
~~~

To view the current system properties of the process:

~~~bash
jcmd <pid> VM.system_properties
~~~

Example partial output:

~~~text
app.mode=prod
app.region=ap-southeast-1
java.home=/opt/jdk
java.version=25
java.vendor=Eclipse Adoptium
user.timezone=UTC
~~~

The example values are for illustration only. Actual output depends on the JDK, operating system, configuration, and application.

Inside the application, you can read a specific property:

~~~java
String mode = System.getProperty("app.mode", "local");
System.out.println("app.mode = " + mode);
~~~

System.getProperties() returns the current set of system properties. An application can call System.setProperty() to change values at runtime. Therefore, the current property does not necessarily match the literal -D argument at startup.

## 8. Inspecting from Inside the Application with RuntimeMXBean

The Java Management API provides RuntimeMXBean to read various details about the running JVM.

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.RuntimeMXBean;
import java.util.Arrays;

public class RuntimeParametersDemo {
    public static void main(String[] args) {
        RuntimeMXBean runtime =
                ManagementFactory.getRuntimeMXBean();

        System.out.println("PID: " + runtime.getPid());
        System.out.println("VM input arguments: "
                + runtime.getInputArguments());
        System.out.println("Application arguments: "
                + Arrays.toString(args));
        System.out.println("app.mode: "
                + System.getProperty("app.mode"));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac RuntimeParametersDemo.java
java -Xms128m -Xmx512m -Dapp.mode=demo RuntimeParametersDemo --mode test "two words"
~~~

Illustrative output:

~~~text
PID: <pid>
VM input arguments: [-Xms128m, -Xmx512m, -Dapp.mode=demo]
Application arguments: [--mode, test, two words]
app.mode: demo
~~~

The PID changes on each run. The VM input arguments may include additional elements if the environment injects extra arguments.

### Limitations of getInputArguments()

RuntimeMXBean.getInputArguments() returns the arguments passed to the JVM and does not include arguments passed to the main method. This API may return an empty list if there are no VM input arguments.

Some JVMs receive options from multiple sources such as the java command, environment variables, or configuration files. Not all options on the java command are forwarded as VM input arguments. Therefore:

- Use getInputArguments() to see the VM input arguments reported by the runtime.
- Use args in main to see application arguments.
- Use jcmd VM.command_line to inspect the launch command line.
- Use jcmd VM.flags to inspect current VM flag values.

Do not use getInputArguments() as the sole evidence for the entire command line.

### Reading All System Properties via API

RuntimeMXBean also has getSystemProperties(), which returns a map of current system properties:

~~~java
runtime.getSystemProperties().forEach((key, value) ->
        System.out.println(key + "=" + value));
~~~

Do not print all properties in production logs without filtering the data first. Some applications may store sensitive information in properties.

## 9. Testing a New JVM Before Deployment

If you want to know how a new JDK will choose VM flag values, you can launch a separate test JVM.

### Printing VM Settings

~~~bash
java -XshowSettings:vm -version
~~~

View system properties as well:

~~~bash
java -XshowSettings:properties -version
~~~

These commands create a new JVM and then exit. They show the configuration of that test run, not the configuration of a running application.

### Printing All VM Flags at Startup

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

This option is useful for checking the final values of many HotSpot VM flags in the newly created JVM. You can filter the output by flag name using OS tools.

Example on Linux/macOS:

~~~bash
java -XX:+PrintFlagsFinal -version 2>&1 | grep -E 'InitialHeapSize|MaxHeapSize|UseG1GC'
~~~

Example on Windows PowerShell:

~~~powershell
java -XX:+PrintFlagsFinal -version 2>&1 |
    Select-String 'InitialHeapSize|MaxHeapSize|UseG1GC'
~~~

To see flags chosen by the JVM via ergonomics, you can use:

~~~bash
java -XX:+PrintCommandLineFlags -version
~~~

The values automatically chosen by the JVM may depend on RAM, CPU, container limits, operating system, and JDK version. Do not assume default values on a development machine will match the production environment.

## 10. Cross-Checking Configuration Sources

When effective values do not match expectations, check according to the following table:

| What to Verify | How to Check |
|---|---|
| Java executable invoked | where java / Get-Command java -All / command -v java |
| Application PID | jcmd -l; OS process tools; PID in logs |
| Launch command line | jcmd <pid> VM.command_line |
| Current VM flags | jcmd <pid> VM.flags -all |
| Current system properties | jcmd <pid> VM.system_properties |
| VM input arguments from code | RuntimeMXBean.getInputArguments() |
| Application arguments | main(String[] args) |
| Environment variables | Get-ChildItem Env:... or printenv/echo |
| Build tool JVM configuration | Gradle/Maven/IDE config and the exact launched process |
| Container/service configuration | Docker/Kubernetes/service unit/launch script |

Example checking environment variables on Windows PowerShell:

~~~powershell
Get-ChildItem Env:JDK_JAVA_OPTIONS,Env:JAVA_TOOL_OPTIONS,Env:CLASSPATH
~~~

On Linux/macOS:

~~~bash
printenv JDK_JAVA_OPTIONS
printenv JAVA_TOOL_OPTIONS
printenv CLASSPATH
~~~

If the corresponding variable is not set, the command may print no value. CLASSPATH is typically only used as the default classpath when the command line does not specify -cp or --class-path.

If you need to view the process command line at the OS level:

Linux:

~~~bash
ps -ww -p <pid> -o pid,args
~~~

Windows PowerShell:

~~~powershell
Get-CimInstance Win32_Process -Filter "ProcessId = <pid>" |
    Select-Object ProcessId, Name, CommandLine
~~~

OS output depends on permissions and may be truncated or represented differently depending on the platform. The command line may also contain passwords, tokens, or sensitive data if the application passes them directly as arguments.

## 11. Diagnostic Workflow When Arguments Are Wrong

Suppose an application is expected to run with a 1 GB maximum heap, but logs show a lower limit.

Proceed step by step:

1. Identify the exact PID of the affected application.
2. Run jcmd <pid> VM.command_line to see the startup command line.
3. Run jcmd <pid> VM.flags to see the current heap values.
4. Check JDK_JAVA_OPTIONS and JAVA_TOOL_OPTIONS in the environment that spawned the process.
5. Read the script, service unit, Dockerfile, or orchestrator configuration that actually created the process.
6. If the application runs via Gradle/Maven/IDE, determine which JVM runs the build and which JVM runs the application.
7. After finding the wrong source, fix the right configuration source and restart the process.
8. Repeat the check on the new PID to confirm the value has changed.

Not all JVM options can be changed after the process has started. Startup parameters such as initial/maximum heap need to be configured before creating the JVM and usually require restarting the application. Some HotSpot diagnostic flags can be changed dynamically if the flag allows it; this depends on the flag and JVM, not a rule that applies to all parameters.

## 12. Common Pitfalls

### Inspecting the Wrong PID

**Symptom:** jcmd returns arguments of the Gradle daemon, IDE, or another application.

**Cause:** the machine has multiple JVMs; short process names or the PID changed after a restart.

**Solution:** match the PID with the main class/JAR and startup logs. Always re-check after a service restart because the new PID may differ.

### getInputArguments() Does Not Show -cp

**Cause:** getInputArguments() returns VM input arguments and is not guaranteed to include every Java launcher option.

**Solution:** use jcmd VM.command_line and inspect the launcher/classpath configuration separately.

### System.getProperty() Does Not Have the Expected Value

**Cause:** the property was not set, the name is misspelled, the -D argument was placed after the main class so it became an application argument, or the application overwrote the property.

**Solution:** check the position of -D, read jcmd VM.system_properties, and search for System.setProperty calls in the code.

### jcmd Cannot Attach to the Process

**Common causes:**

- The user running jcmd does not have the same effective user/group as the target process.
- The tool is running on a different machine or process namespace.
- The JVM disallows attach or the attach listener is not available.
- The PID no longer exists or the process just restarted.
- The runtime/vendor does not support the required diagnostic command.

**Solution:** run jcmd with the right user permissions on the same machine/container, verify the new PID, and check jcmd <pid> help. If the tool does not support that command, use JMX or the vendor's official diagnostic documentation.

### jps Cannot Find the Application in a Container

**Cause:** jps does not list JVMs running in a separate Docker process when invoked from the host.

**Solution:** run the tool inside the container or obtain the PID from the right process namespace.

### Heap Value Differs from the Number in the Script

**Cause:** the script is not the actual source, arguments were added from environment variables, the JVM chose ergonomic values automatically, or you are reading a different PID.

**Solution:** cross-check the command line with VM.flags. For heap, check InitialHeapSize and MaxHeapSize instead of only searching for -Xms/-Xmx strings in the script.

### jinfo Does Not Work

jinfo is an experimental and unsupported tool in current JDK documentation; it may be unavailable or change in future releases.

**Solution:** prefer jcmd VM.command_line, VM.flags, and VM.system_properties.

## 13. Security When Inspecting Arguments

Runtime arguments may contain sensitive information such as access tokens, passwords, internal paths, connection details, or agent configurations. Therefore:

- Only read the command line and properties of processes you are authorized to inspect.
- Do not copy the entire output into public tickets/logs without reviewing it first.
- Do not pass passwords/tokens via command-line arguments if a safer configuration option exists.
- Do not open a public JMX remote port just to view RuntimeMXBean; if remote monitoring is needed, configure appropriate authentication, encryption, and network access.
- Only grant attach/diagnostic permissions to authorized operators.

## 14. Practice Checklist

- [ ] Distinguish between launcher options, JVM flags, system properties, and application arguments.
- [ ] Identify the exact PID of the application.
- [ ] Inspect the command line with jcmd VM.command_line.
- [ ] Inspect VM flags with jcmd VM.flags or VM.flags -all.
- [ ] Inspect system properties with jcmd VM.system_properties.
- [ ] Read RuntimeMXBean.getInputArguments() and understand the API's limitations.
- [ ] Inspect args in the main method.
- [ ] Check JDK_JAVA_OPTIONS, JAVA_TOOL_OPTIONS, and @argfile files.
- [ ] Cross-check the script/service/container/IDE/build tool that created the process.
- [ ] Restart and verify the new PID after modifying startup arguments.
- [ ] Remove or mask sensitive data before sharing output.

## 15. Official References

- [jcmd — Java SE 25 Tool Specification](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html) — listing JVM processes and diagnostic commands such as VM.command_line, VM.flags, VM.system_properties.
- [RuntimeMXBean — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/RuntimeMXBean.html) — getInputArguments(), getSystemProperties(), PID, and runtime information.
- [java — Java SE 26 Tool Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — launcher options, JDK_JAVA_OPTIONS, argument files, -XshowSettings, and HotSpot VM flags.
- [jps — Java SE 26 Tool Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jps.html) — how to list JVMs and the meaning of -l, -m, -v options.
- [jinfo — Java SE 26 Tool Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jinfo.html) — experimental/unsupported status of jinfo.
- [Troubleshooting Guide — JAVA_TOOL_OPTIONS](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-guide.pdf) — how the environment variable appends options when the JVM is created.

Diagnostic commands and VM flags may vary by vendor/JVM and JDK version. When working with a specific process, use jcmd <pid> help to confirm the commands supported by that particular JVM.