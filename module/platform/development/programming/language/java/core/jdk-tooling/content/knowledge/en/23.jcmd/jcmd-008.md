# Inspecting JVM System Properties with jcmd

`jcmd <pid> VM.system_properties` is a JDK diagnostic command used to print the current system properties of a running Java Virtual Machine (JVM). It is useful when you need to inspect the actual runtime configuration of a process without stopping the application or relying solely on build-time configuration.

System properties can be passed at startup using the `-Dkey=value` option, set in code via `System.setProperty`, or added at runtime by libraries and frameworks. `VM.system_properties` displays the current values held by the JVM, including custom properties created by the application.

This command **only reads and prints properties**. It does not add, modify, or remove system properties. To change values after the JVM has started, the application must provide its own runtime configuration mechanism, such as calling `System.setProperty` or exposing a secure management API.

## 1. What Is a System Property?

A system property is a string key/value pair stored in the JVM's `java.util.Properties` object. A Java application can read a property with `System.getProperty` or retrieve the entire set of properties with `System.getProperties`.

Common standard properties:

| Property | Meaning |
|---|---|
| `java.version` | Java runtime version |
| `java.home` | Runtime installation directory |
| `java.class.path` | Application classpath |
| `os.name` | Operating system name |
| `os.arch` | Operating system architecture |
| `user.dir` | Current working directory |
| `user.home` | User home directory |
| `file.encoding` | Default charset reported by the runtime |
| `java.io.tmpdir` | Temporary directory |
| `path.separator` | OS-specific path separator character |

Applications can also define custom properties, typically namespaced by the application, such as `app.profile`, `app.region`, or `service.endpoint`. Using a custom prefix helps avoid conflicts with standard properties or other libraries.

System properties differ from environment variables. Environment variables are provided to the process by the operating system and read in Java via `System.getenv`; they do not automatically become system properties. Only values copied or inserted into `System.getProperties()` by the application appear in the `VM.system_properties` output.

## 2. jcmd Syntax and Selecting the Target JVM

General syntax:

~~~sh
jcmd <pid> <command> [arguments]
~~~

Here, `jcmd` is the diagnostic utility bundled with the JDK, `<pid>` is the process ID of the JVM to inspect, and `<command>` is a diagnostic command supported by the target JVM.

List running JVMs on the machine:

~~~sh
jcmd -l
~~~

Example output:

~~~text
36008 PropertyProbe
51276 com.example.Server
~~~

The PID and main class name depend on the running machine. Use a specific PID to avoid sending commands to the wrong process. You can use the main class name instead of the PID, but if multiple JVMs are running that same class, the command may be sent to all matching processes.

List the commands supported by the target JVM:

~~~sh
jcmd 36008 help
~~~

View the syntax and description of a specific command:

~~~sh
jcmd 36008 help VM.system_properties
~~~

Available diagnostic commands can vary by JVM, JDK, and version. Always run `help` against the target process itself before assuming a command is available.

Do not use PID `0` if you only want to inspect a single application: PID `0` instructs `jcmd` to send the command to all reachable Java processes.

## 3. Printing System Properties with VM.system_properties

Main command:

~~~sh
jcmd 36008 VM.system_properties
~~~

The output may contain hundreds of properties. Abbreviated example:

~~~text
#Tue Nov 10 18:52:44 GMT+07:00 2026
app.mode=diagnostic
app.profile=qa
app.region=test-lab
file.encoding=UTF-8
java.class.version=68.0
java.runtime.version=24.0.2+12
java.specification.version=24
os.arch=amd64
os.name=Windows 11
user.dir=H\:\\projects\\sample
~~~

This is an abbreviated example; the timestamp, Java version, paths, and properties depend on the actual process. The first line may be the report timestamp. Values containing backslashes or special separators may be escaped in a format similar to Java `.properties` files.

`VM.system_properties` reads the system property set inside the selected JVM. If the application called `System.setProperty("app.mode", "diagnostic")` before inspection, that property appears in the report. Values from the `-Dapp.profile=qa` startup option also appear.

To save the full report for analysis:

~~~sh
jcmd 36008 VM.system_properties > vm-properties.txt
~~~

In PowerShell:

~~~powershell
jcmd 36008 VM.system_properties | Out-File -Encoding utf8 vm-properties.txt
~~~

You can filter for a specific group of application properties for quick reading:

~~~sh
jcmd 36008 VM.system_properties | grep '^app\.'
~~~

PowerShell:

~~~powershell
jcmd 36008 VM.system_properties | Select-String '^app\.'
~~~

Filtering the output only reduces the number of displayed lines; the JVM still returns the full property set to the command. Treat the output file as internal configuration data and protect it accordingly.

## 4. Complete Example: Creating a JVM with Properties to Inspect

Create `PropertyProbe.java`:

~~~java
public class PropertyProbe {
    public static void main(String[] args) throws InterruptedException {
        System.setProperty("app.mode", "diagnostic");
        System.setProperty("app.region", "test-lab");

        System.out.println("probe-ready");
        Thread.sleep(120_000);
    }
}
~~~

The program sets two properties at runtime and keeps the JVM running for two minutes so you have time to inspect it from another terminal. `Thread.sleep` only keeps the process alive for this exercise; production applications have their own lifecycle.

Compile:

~~~sh
mkdir -p out
javac -d out PropertyProbe.java
~~~

Start the program with a property passed on the command line:

~~~sh
java -Dapp.profile=qa -cp out PropertyProbe
~~~

Program stdout:

~~~text
probe-ready
~~~

Open a second terminal and list the running JVMs:

~~~sh
jcmd -l
~~~

Find the `PropertyProbe` line to get its PID, then substitute the PID into the command:

~~~sh
jcmd <pid> VM.system_properties
~~~

In the output, look for the three properties:

~~~text
app.mode=diagnostic
app.profile=qa
app.region=test-lab
~~~

`app.profile` comes from `-Dapp.profile=qa` at startup. `app.mode` and `app.region` were set inside the application via `System.setProperty`. This example shows that `VM.system_properties` reflects the properties currently present in the JVM, not just those passed at startup.

When finished inspecting, return to the terminal running `PropertyProbe` and press `Ctrl+C` to stop the program.

## 5. Distinguishing System Properties, VM Flags, and Command Line

`jcmd` provides different commands for different types of information:

| Command | Content |
|---|---|
| `VM.system_properties` | Current JVM system properties |
| `VM.command_line` | Command line and VM arguments used to launch the process |
| `VM.flags` | JVM flags and their current values |
| `VM.version` | JVM version information |
| `VM.uptime` | Time elapsed since the JVM started |

Example:

~~~sh
jcmd 36008 VM.system_properties
jcmd 36008 VM.command_line
jcmd 36008 VM.flags
~~~

Key distinctions:

- `-Dname=value` creates a system property.
- `-Xmx` and `-XX:...` are JVM options/flags, not regular system properties.
- `VM.system_properties` displays properties.
- `VM.flags` displays VM configuration flags.
- `VM.command_line` shows startup arguments; it is not a complete report of current property state.

Do not confuse `VM.set_flag` with setting a system property. `VM.set_flag` applies to certain manageable JVM flags that can be changed at runtime; it does not provide a general-purpose command to set `System.getProperty` values.

## 6. Changing System Properties After the JVM Has Started

`VM.system_properties` is a read-only command. There is no parameter to pass a new key/value pair to it.

An application can update a property within its own process using the Java API:

~~~java
System.setProperty("app.mode", "maintenance");
String mode = System.getProperty("app.mode");
System.out.println(mode);
~~~

Output:

~~~text
maintenance
~~~

If this code runs in the inspected JVM, the next `jcmd <pid> VM.system_properties` call will show `app.mode=maintenance`.

To change runtime configuration externally, the application must explicitly expose a controlled mechanism, such as a JMX MBean, an authenticated admin endpoint, or a configuration reload mechanism. `jcmd` does not create a property-mutation endpoint or turn a property-printing command into a setter.

Note: changing a property does not guarantee that every library will immediately pick up the new value. A framework may have read and cached the property during initialization. Check the relevant component's documentation to see whether a reload, restart, or dedicated configuration API call is required.

## 7. Access Permissions and Attach Conditions

`jcmd` sends diagnostic requests to the JVM over the local attach mechanism. According to the JDK documentation, the tool must run on the same machine as the target JVM and under the same effective user/group that started that JVM.

Conditions that can affect attachment:

- The target JVM has exited or the PID no longer exists.
- The wrong PID is used, or the PID belongs to a non-Java process.
- The current user lacks permission to attach to the target process.
- The JVM was started with `-XX:+DisableAttachMechanism`.
- The process runs inside a container or a different PID namespace, so the host-visible PID does not match the PID inside the container.
- The target JVM does not support the requested diagnostic command.

In containerized environments, identify the PID within the appropriate namespace and run the tool from an environment that can attach to that JVM. `jcmd -l` does not necessarily list JVMs running in separate Docker processes; you may need to look up the PID with OS tools or execute the command inside the container.

Use a JDK matching the target JVM whenever possible. After attaching, run `jcmd <pid> help` to confirm the list of available commands.

## 8. Security When Reading System Properties

System properties are not public data by default. The output may contain:

- Home directory, working directory, temporary directory, and library paths.
- Account names or environment details.
- Internal URLs, endpoints, database names, or service configurations.
- Custom properties inadvertently used by the application to store tokens, passwords, or secrets.

Avoid passing secrets via `-Dpassword=...` or storing credentials in system properties. Properties can be exposed through command lines, diagnostic output, logs, or monitoring tools. Use a secret manager or an appropriate credential mechanism instead.

When sharing output for troubleshooting:

1. Extract only the properties needed, such as filtering by the `app.` prefix.
2. Mask tokens, passwords, URLs containing credentials, and internal identifiers.
3. Do not paste the full `VM.system_properties` output into public tickets or repositories.
4. Restrict read permissions on diagnostic interfaces and output files.
5. Delete temporary files according to your organization's retention policy once the investigation is complete.

## 9. Common Errors and Troubleshooting

| Symptom | Common Cause | Resolution |
|---|---|---|
| `jcmd: command not found` | JDK is not installed or `PATH` is missing the JDK `bin` directory | Check `JAVA_HOME` and `PATH` |
| JVM not listed in `jcmd -l` | Different user, JVM is in a separate container, or process has stopped | Look up the PID with OS tools in the target environment |
| `AttachNotSupportedException` or unable to attach | Attach is disabled, insufficient permissions, or unsupported JVM | Run as the same user, check `-XX:+DisableAttachMechanism`, and inspect error logs |
| `Unknown diagnostic command` | Command is not supported by the target JVM or misspelled | Run `jcmd <pid> help` |
| Custom property missing | Application has not set it yet, wrong key name, or wrong JVM | Verify `System.setProperty`, `-D...`, and the PID |
| Value differs from expected configuration | Startup args, config reload, or runtime code modified the property | Compare `VM.system_properties` with `VM.command_line` and application config |
| Output is too long | JVM has many properties | Redirect output to a file and filter by prefix |
| Property change does not alter application behavior | Library cached the config or does not support reload | Check the component's reload/restart API |

## 10. Workflow for Inspecting System Properties in Production

When you need to verify an application's actual configuration:

1. Identify the correct host/container and Java process to inspect.
2. Use `jcmd -l` or OS tools to find the PID.
3. Run `jcmd <pid> help` to confirm the JVM accepts diagnostic commands.
4. Run `jcmd <pid> VM.system_properties` to retrieve the current values.
5. Filter for the relevant keys and compare them against the expected configuration.
6. If you need to see what was passed at startup, also check `VM.command_line`.
7. If investigating JVM tuning, inspect `VM.flags` separately.
8. If a property does not match expectations, check initialization code, `System.setProperty`, configuration load order, and caching behavior.
9. Protect the output, as it may contain internal or sensitive information.
10. Change configuration only through management mechanisms supported by the application; `VM.system_properties` does not modify values.

### Checklist

- [ ] Identified the exact PID of the target JVM.
- [ ] Used the same machine and matching user/group to attach.
- [ ] Verified available commands with `jcmd <pid> help`.
- [ ] Ran `jcmd <pid> VM.system_properties`.
- [ ] Distinguished system properties from VM flags and environment variables.
- [ ] Compared `-D` startup properties with runtime values.
- [ ] Understood that the command is read-only and does not modify properties.
- [ ] Filtered/masked sensitive information before sharing output.
- [ ] Checked attach/container constraints if the JVM could not be accessed.

`jcmd <pid> VM.system_properties` lets you inspect the actual system properties of a running JVM, including values modified by the application at runtime. Combining the right PID, proper attach permissions, and cross-checking with `VM.command_line` helps diagnose configuration issues accurately without confusing properties, VM flags, and environment variables.

## References

- [Oracle JDK 24 — The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Oracle Java Troubleshooting Guide — jcmd utility](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf)