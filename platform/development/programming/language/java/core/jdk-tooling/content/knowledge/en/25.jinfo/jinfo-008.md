# How to Read jinfo Output in Java

jinfo is a JDK command-line tool used to inspect the configuration of a running Java process. Its output focuses on two groups of data: Java system properties and JVM command-line flags. Knowing how to read these two groups lets you determine which version the JVM is running, which classpath the application is using, which heap/GC options are in effect, and which properties have been passed to the application.

This guide uses JDK 17 or later. The focus is on understanding each section of the output, distinguishing properties from VM flags, reading Boolean and numeric values, finding useful information when troubleshooting, and knowing when to use jcmd instead of jinfo.

> **Tool note:** Oracle marks jinfo as experimental and unsupported; the tool may change or be removed in future JDK releases. For new diagnostics, Oracle recommends using jcmd.

## 1. What Information Does jinfo Collect?

Basic syntax:

~~~text
jinfo [option] pid
~~~

pid is the process ID of the JVM to inspect. The target process must be a Java process that the tool can attach to.

If no option is passed, jinfo prints both groups:

- **Java System Properties:** configuration name-value pairs that can be read in the application via System.getProperty(...).
- **VM Flags:** configuration options of the Java Virtual Machine, typically in the form -XX:Name=value, -XX:+Name, or -XX:-Name.

Commands to read each group separately:

~~~powershell
jinfo -sysprops 12345
jinfo -flags 12345
~~~

Read a single VM flag:

~~~powershell
jinfo -flag MaxHeapSize 12345
jinfo -flag UseG1GC 12345
~~~

View help:

~~~powershell
jinfo -help
~~~

12345 is only an example PID. Replace it with the actual PID of the application on the machine being diagnosed.

## 2. Finding the Right PID Before Reading Output

You can list the JVMs recognized by the JDK using jps:

~~~powershell
jps -l
~~~

Example output:

~~~text
8120 com.example.JInfoTarget
9204 org.apache.catalina.startup.Bootstrap
10440 jdk.jcmd/sun.tools.jps.Jps
~~~

In this example, PID 8120 belongs to the com.example.JInfoTarget application. You can inspect it with:

~~~powershell
jinfo 8120
~~~

If the JVM runs inside a separate Docker/container, jps on the host may not list that process. Find the PID within the appropriate namespace, for example by running ps inside the container or using your container management tool.

Make sure you are using a JDK tool compatible with the target JVM and that your account has permission to attach. Typically, attaching must be performed on the same machine and under a user account that matches the target process's permissions. Security settings, runtime configuration, or container environments may restrict attaching.

## 3. Reading the Default Output: Two Main Sections

Command:

~~~powershell
jinfo 8120
~~~

Abbreviated example output:

~~~text
Attaching to process ID 8120, please wait...
Debugger attached successfully.
Server compiler detected.
JVM version is 17.0.x

Java System Properties:
    java.specification.version=17
    java.version=17.0.x
    java.home=C:\Java\jdk-17
    java.class.path=C:\apps\demo\app.jar
    user.dir=C:\apps\demo
    user.name=service-user
    os.name=Windows 11
    file.encoding=UTF-8
    app.profile=staging
    app.timeoutSeconds=30
    sun.java.command=com.example.JInfoTarget

VM Flags:
    -XX:InitialHeapSize=134217728
    -XX:MaxHeapSize=536870912
    -XX:+UseG1GC
~~~

This is an abbreviated example output to illustrate how to read it. The JDK version, operating system, launch configuration, and default flags may cause the actual output to differ.

You can read it in this order:

1. The attach lines show which PID the tool is connecting to and whether the JVM was recognized.
2. The version line shows the runtime of the target process.
3. The Java System Properties section shows the current properties and their values.
4. The VM Flags section shows the JVM configuration options reported by the tool.

If you need to investigate a specific setting, use -sysprops, -flags, or -flag name to narrow down the output.

## 4. Reading the Java System Properties Section

System properties have the form:

~~~text
property.name=value
~~~

Example:

~~~text
java.version=17.0.x
java.home=C:\Java\jdk-17
java.class.path=C:\apps\demo\app.jar
user.dir=C:\apps\demo
app.profile=staging
app.timeoutSeconds=30
~~~

Properties are commonly read in Java using:

~~~java
String version = System.getProperty("java.version");
String profile = System.getProperty("app.profile");
~~~

Properties can be grouped into several categories.

### 4.1. Version and Runtime Information

| Property | Meaning |
|---|---|
| java.version | Java runtime version |
| java.version.date | Release date of the runtime, if available |
| java.runtime.version | Full version of the runtime |
| java.runtime.name | Runtime name |
| java.vm.name | Java Virtual Machine name |
| java.vm.version | VM version |
| java.vm.vendor | VM vendor |
| java.specification.version | Java SE specification version supported by the runtime |
| java.home | Runtime/JDK installation directory used by the JVM |

This group helps confirm whether the application is running on the expected JDK. In particular, java.home shows the runtime that the process actually loaded; it may differ from the JDK selected in your current terminal.

### 4.2. Classpath and Execution Directory

| Property | Meaning |
|---|---|
| java.class.path | Classpath used by the application |
| user.dir | Current working directory of the process |
| java.library.path | Directories searched when loading native libraries |
| sun.java.command | Main class name or command/JAR used to launch the application |

When encountering ClassNotFoundException or NoClassDefFoundError, check java.class.path and sun.java.command. If a JAR path or class directory is missing, the application may be running with a different classpath than expected.

java.library.path is useful when investigating native library loading errors such as missing DLLs or shared libraries. This value is a list of paths; the separator typically differs between Windows and Unix-like systems.

### 4.3. User and Operating System Information

| Property | Meaning |
|---|---|
| user.name | User name seen by the JVM |
| user.home | User's home directory |
| os.name | Operating system name |
| os.version | Operating system version |
| os.arch | Operating system architecture |
| file.encoding | Default charset used by the runtime for certain APIs |
| file.separator | Directory separator character |
| path.separator | Separator character between entries in a path list |
| line.separator | Platform line-ending character sequence |

These properties are useful when an application behaves differently across development, test, and production machines. For example, user.dir can explain why a relative path finds a file locally but fails when running as a service.

### 4.4. Application-Defined Properties

Properties starting with an application-specific prefix typically come from -D arguments or System.setProperty(...) calls.

Launch example:

~~~powershell
java -Dapp.profile=staging -Dapp.timeoutSeconds=30 -jar app.jar
~~~

The application reads them:

~~~java
String profile = System.getProperty("app.profile", "local");
int timeout = Integer.parseInt(
    System.getProperty("app.timeoutSeconds", "10")
);
~~~

In the output, you may see:

~~~text
app.profile=staging
app.timeoutSeconds=30
~~~

This is evidence that the property is present in the JVM at the time of inspection. If the property does not appear, check the launch command, configuration code, and when the application sets the property.

### 4.5. Caveats When Reading Property Values

- Some values can be very long, such as java.class.path or java.library.path.
- Windows paths may appear with backslashes or escape characters.
- Custom properties may contain equal signs, spaces, or delimited lists.
- sun.* and some jdk.* properties may be implementation details; do not treat them as stable APIs for application logic.
- jinfo -sysprops does not list all operating system environment variables.
- Not all application configuration is stored in system properties; an application may read from files, databases, secret managers, or custom configuration sources.

## 5. Reading the VM Flags Section

A VM flag is a JVM configuration option. Many HotSpot flags use the -XX: prefix. Common output:

~~~text
VM Flags:
    -XX:InitialHeapSize=134217728
    -XX:MaxHeapSize=536870912
    -XX:+UseG1GC
~~~

How to read it:

| Output | Meaning |
|---|---|
| -XX:+UseG1GC | Boolean flag is enabled |
| -XX:-UseG1GC | Boolean flag is disabled |
| -XX:MaxHeapSize=536870912 | Numeric flag with value 536,870,912 bytes |
| -XX:InitialHeapSize=134217728 | Initial heap size is 134,217,728 bytes |

Flags reflect the VM's configuration. Some values come from arguments passed by the operator when starting java; others are chosen by the JVM based on machine resources and ergonomics. Therefore, the output does not necessarily mirror the original command line verbatim.

### 5.1. Boolean Flags: Plus and Minus Signs

For Boolean flags:

- -XX:+FlagName means enabled.
- -XX:-FlagName means disabled.

Example:

~~~text
-XX:+UseG1GC
-XX:-UseBiasedLocking
~~~

The first line indicates that UseG1GC is enabled. The second line indicates that UseBiasedLocking is disabled. Specific flags may vary across JDK versions; do not assume a flag exists or has the same meaning in every version.

### 5.2. Numeric Flags and Memory Sizes

Numeric flags typically have the form:

~~~text
-XX:MaxHeapSize=536870912
~~~

Some memory values are expressed in bytes. To convert to MiB:

\[
\text{MiB} = \frac{\text{bytes}}{1024 \times 1024}
\]

Example:

- 536870912 bytes = 512 MiB.
- 134217728 bytes = 128 MiB.

In the Java launcher, -Xmx512m typically corresponds to a maximum heap limit of 512 MiB, while -Xms128m sets the initial heap to 128 MiB. In VM flags, these values may appear under internal names such as MaxHeapSize and InitialHeapSize.

Do not confuse heap with total process memory. Heap is only one part of JVM memory; metaspace, code cache, thread stacks, direct buffers, and native memory also consume RAM.

## 6. Using -flags to Read the VM Flag List

Command:

~~~powershell
jinfo -flags 8120
~~~

Prints only the VM flags section instead of all system properties.

Abbreviated example output:

~~~text
VM Flags:
-XX:InitialHeapSize=134217728 -XX:MaxHeapSize=536870912 -XX:+UseG1GC
~~~

Use this command when you need to inspect the overall JVM configuration, such as:

- Initial and maximum heap sizes.
- Configured garbage collector.
- JVM options passed at startup.
- Flags to cross-check against deployment configuration.

The list can be long and depends on the VM version. Some values may be defaults or ergonomic values chosen by the JVM. To understand the origin of a flag or whether it can be changed at runtime, consult the documentation for the exact JDK version and VM type.

## 7. Using -sysprops to Read Only Properties

Command:

~~~powershell
jinfo -sysprops 8120
~~~

The output consists of multiple name=value lines:

~~~text
Java System Properties:
    java.version=17.0.x
    java.home=C:\Java\jdk-17
    java.class.path=C:\apps\demo\app.jar
    user.dir=C:\apps\demo
    app.profile=staging
    app.timeoutSeconds=30
~~~

This is the right command when investigating:

- Which JDK version the JVM is using.
- Which directory the application was launched from.
- Whether the classpath contains the expected JARs.
- Whether a profile or custom property has been loaded.
- Whether encoding, architecture, and environment details differ between machines.

If you need to check a property in code, you can call System.getProperty("app.profile") in the application. jinfo gives you visibility into the running process without modifying source code.

## 8. Using -flag to Read a Single VM Flag

Syntax:

~~~text
jinfo -flag flagName pid
~~~

Example reading maximum heap and GC:

~~~powershell
jinfo -flag MaxHeapSize 8120
jinfo -flag UseG1GC 8120
~~~

Example output:

~~~text
-XX:MaxHeapSize=536870912
-XX:+UseG1GC
~~~

The result shows a single specific flag, making it easier to read than the long list from -flags.

If the flag does not exist in the running VM, or the flag name is incorrect, the tool will report an error. Flag names should be checked against the running JDK version.

## 9. Distinguishing Reading Flags from Modifying Flags

The -flag option has both read and write forms:

| Syntax | Effect |
|---|---|
| jinfo -flag MaxHeapSize pid | Read the flag value |
| jinfo -flag +FlagName pid | Request enabling a Boolean flag |
| jinfo -flag -FlagName pid | Request disabling a Boolean flag |
| jinfo -flag FlagName=value pid | Request setting a flag to a new value |

The forms with +, -, or =value modify the JVM state. They are not read-only commands. Only certain flags allow modification while the JVM is running; the VM may reject non-writable flags or invalid values.

Before modifying a flag:

1. Confirm the exact PID and application.
2. Check the flag's documentation for the exact JDK version.
3. Assess the impact on heap, GC, performance, and stability.
4. Follow your approved operational procedure.
5. Re-read the flag to confirm the new value if the operation succeeds.

Do not attempt to modify flags in production just to test syntax. Changing JVM configuration can directly impact the running application.

## 10. Hands-On Example: Creating a JVM to Read jinfo Output

Create JInfoTarget.java:

~~~java
import java.util.concurrent.CountDownLatch;

public class JInfoTarget {
    public static void main(String[] args) throws InterruptedException {
        System.setProperty("app.profile", "staging");
        System.setProperty("app.timeoutSeconds", "30");

        System.out.println("Target JVM is ready.");
        new CountDownLatch(1).await();
    }
}
~~~

The program sets two system properties so they are easy to spot in the output, then keeps the JVM running so you can attach from a second terminal.

Compile:

~~~powershell
javac JInfoTarget.java
~~~

Launch with JVM options:

~~~powershell
java -Xms128m -Xmx512m -XX:+UseG1GC -Dapp.profile=staging -Dapp.timeoutSeconds=30 JInfoTarget
~~~

Stdout:

~~~text
Target JVM is ready.
~~~

Keep this terminal open. Open a second terminal on the same machine and find the PID:

~~~powershell
jps -l
~~~

Find the line with JInfoTarget, then replace <PID> in the following commands with the actual PID number:

~~~powershell
jinfo <PID>
jinfo -sysprops <PID>
jinfo -flags <PID>
jinfo -flag MaxHeapSize <PID>
jinfo -flag UseG1GC <PID>
~~~

In -sysprops, look for:

~~~text
app.profile=staging
app.timeoutSeconds=30
~~~

In -flags, look for values corresponding to:

~~~text
-XX:InitialHeapSize=134217728
-XX:MaxHeapSize=536870912
-XX:+UseG1GC
~~~

Actual flag values may be normalized by the JVM or include additional default flags. Treat this as a representative result to recognize the data format. When finished, return to the first terminal and press Ctrl+C to stop the program.

## 11. Troubleshooting with jinfo Output

### 11.1. Application Using the Wrong JDK

Check:

~~~text
java.version
java.runtime.version
java.home
java.vm.name
~~~

If java.home points to a different runtime than the expected JDK, check the service wrapper, launch script, JAVA_HOME, and PATH of the environment running the application. The PATH in your terminal is not necessarily the same as the service's PATH.

### 11.2. Class Not Found Errors

Check:

~~~text
java.class.path
sun.java.command
user.dir
~~~

Verify the JAR paths, class directories, working directory, and launch command. The classpath can differ between an IDE and a service because each environment builds the command line differently.

### 11.3. Incorrect Heap Configuration

Check:

~~~text
-XX:InitialHeapSize=...
-XX:MaxHeapSize=...
~~~

Convert the byte values to MiB to compare with -Xms and -Xmx. If the values do not match expectations, check the actual service arguments, configuration variables, launch scripts, and JVM ergonomic defaults.

Do not rely on MaxHeapSize alone to conclude that a process is running out of RAM. To evaluate heap usage, GC pauses, or native memory, use dedicated diagnostic tools such as jcmd, JFR, or JDK Mission Control.

### 11.4. Unexpected Garbage Collector

Check the corresponding Boolean flag, for example:

~~~powershell
jinfo -flag UseG1GC <PID>
~~~

A result of -XX:+UseG1GC indicates the flag is enabled; -XX:-UseG1GC indicates it is disabled. The actual GC also depends on the VM version and other options. Read the GC documentation for the exact JDK before changing configuration.

### 11.5. Missing Custom Property

Check with:

~~~powershell
jinfo -sysprops <PID>
~~~

If the property does not appear, check the -D arguments, service configuration, and code calling System.setProperty. If the application loads configuration from a file or secret manager, that value may not appear in system properties.

## 12. What jinfo Does Not Tell You

jinfo is a point-in-time snapshot of configuration when the command is run. It is not a comprehensive profiling or monitoring tool.

It does not directly tell you:

- How many bytes of heap are currently in use.
- How long GC pauses last or how frequently GC runs.
- Which threads are blocked or deadlocked.
- Which methods are consuming CPU.
- Object counts and memory distribution.
- All operating system environment variables.
- Configuration values stored in files, databases, or secret managers if the application does not place them into system properties.

Choose the right tool for your question:

| What you need to know | Appropriate tool |
|---|---|
| System properties and VM flags | jinfo or jcmd |
| JVM launch command line | jcmd <PID> VM.command_line |
| Thread dump | jcmd <PID> Thread.print |
| Heap summary | jcmd <PID> GC.heap_info |
| Flight Recording | jcmd <PID> JFR.start and JFR.dump |
| Analyzing recordings | JDK Mission Control or jfr |

## 13. Using jcmd Instead of jinfo in JDK 17

Oracle recommends jcmd for modern JVM diagnostics. The corresponding commands are:

~~~powershell
jcmd <PID> VM.system_properties
jcmd <PID> VM.flags
jcmd <PID> VM.command_line
~~~

Meaning:

- VM.system_properties: prints system properties.
- VM.flags: prints VM flags and their current values.
- VM.command_line: prints the command line used to launch the JVM.

List the diagnostic commands supported by the JVM:

~~~powershell
jcmd <PID> help
~~~

You can request help for a specific command:

~~~powershell
jcmd <PID> help VM.flags
~~~

Available commands depend on the JVM and its version. jcmd must run on the same machine and with an effective user/group matching the JVM process. For deeper diagnostics, jcmd also provides commands for threads, heap, and Flight Recorder.

## 14. Common Errors When Reading jinfo Output

| Symptom | Common cause | Resolution |
|---|---|---|
| jinfo is not recognized | JDK bin is not in PATH or the machine only has a JRE/runtime | Install an appropriate JDK or invoke jinfo by its full path |
| Unable to open socket file or attach failed | Wrong PID, wrong user, attach restricted, or JVM no longer running | Verify PID, user, host, and process status |
| PID not found with jps | JVM runs in a different container namespace or is not listed | Run ps in the appropriate environment or check the PID namespace |
| Output missing expected system property | Property was not set or application uses another config source | Check -D arguments, config code, and System.setProperty |
| Unrecognized flag | Incorrect flag name or flag not present in this VM version | Use the exact name and consult docs for the right JDK |
| Cannot modify flag | Flag is not writable at runtime or value violates constraints | Check flag type, writability, and valid values |
| Tool error on Windows | Missing debugging components or jvm.dll not found | Check Windows Debugging Tools and PATH requirements per Oracle docs |
| Confusing heap values | Values are printed in bytes | Divide by 1,048,576 to convert to MiB |

If jinfo does not work or is unavailable in the JDK being used, try jcmd with the corresponding commands. For crash dumps, use jhsdb jinfo and provide the matching executable and core file according to the JDK Serviceability Agent documentation.

## 15. Protecting Output When Sharing

System properties and VM flags can expose environment details:

- user.name, user.home, and user.dir reveal account names and internal paths.
- java.class.path and java.library.path may contain project names, directories, or artifact locations.
- sun.java.command can reveal the main class and startup arguments.
- Custom properties may contain endpoints, tokens, or sensitive data if the application is not designed securely.

Before sending output to colleagues, attaching it to a ticket, or posting it on a forum, review and redact sensitive information. Do not share the full default output if only one flag or property is needed; use -flag, -flags, or -sysprops to narrow down what is shown.

Do not treat jinfo output as a stable configuration storage format or an API for parsers to depend on long-term. The formatting and flags may change across JDK versions, VMs, operating systems, and deployment configurations.

## 16. Checklist for Reading jinfo Output

- [ ] Identified the correct PID of the JVM to inspect.
- [ ] Using a compatible JDK tool with permission to attach.
- [ ] Read the JVM version and java.home.
- [ ] Checked java.class.path, sun.java.command, and user.dir when investigating class/file errors.
- [ ] Distinguished system properties from VM flags.
- [ ] Understood the + or - signs on Boolean flags.
- [ ] Converted byte values to MiB when checking heap sizes.
- [ ] Did not confuse flag values with live heap usage or runtime metrics.
- [ ] Did not treat environment variables as system properties.
- [ ] Redacted sensitive information before sharing output.
- [ ] Considered jcmd for new diagnostics.

When reading jinfo output, start with the PID and JVM version, then separate the Java System Properties section from VM Flags. Properties help identify the runtime, classpath, working directory, and application configuration; VM flags show JVM options such as heap and garbage collector. Use -sysprops, -flags, and -flag to focus on the data you need to inspect, while keeping in mind that jinfo is an experimental/unsupported tool and jcmd is Oracle's recommended choice for modern diagnostics.

## References

- Oracle, The jinfo Command, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jinfo.html
- Oracle, The jcmd Command, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Oracle, Diagnostic Tools, Java SE 21 — The jinfo Utility: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle, The java Command, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
