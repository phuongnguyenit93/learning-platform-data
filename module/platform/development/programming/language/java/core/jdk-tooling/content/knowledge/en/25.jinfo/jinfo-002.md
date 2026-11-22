# VM Flags in Java: Reading and Modifying with jinfo

## Objectives

After this lesson, you will be able to explain VM flags and distinguish them from system properties; inspect the configuration of a running JVM using `jinfo`; use the `-flag` syntax to view, enable, disable, or set values; distinguish between startup-only flags and diagnostic options that can be changed dynamically; use `jcmd` as the recommended diagnostic tool; inspect the value, origin, and writeability of VM options using `HotSpotDiagnosticMXBean`; and verify changes before putting a configuration into production.

## 1. What is a VM flag?

A **VM flag** is a configuration option for the Java Virtual Machine (JVM). Flags control how the JVM starts up and manages the heap, garbage collection, JIT compiler, class loading, logging, diagnostics, and many other internal operations.

Example:

~~~bash
java -Xms512m -Xmx2g -XX:+UseG1GC -jar service.jar
~~~

- `-Xms512m` sets the initial heap size.
- `-Xmx2g` sets the maximum heap limit.
- `-XX:+UseG1GC` requests the G1 garbage collector.
- `-jar service.jar` launches the application from the JAR file.

Flags are typically passed at JVM startup. Some flags can be modified while the JVM is running, but most flags that affect VM structure or initialization can only be set at startup.

Flags can hold boolean, numeric, memory size, string, or complex parameter values. Not every flag can be changed dynamically.

### Common flag forms

| Form | Example | Meaning |
|---|---|---|
| Boolean | -XX:+UseG1GC | Enable flag |
| Boolean | -XX:-UseG1GC | Disable flag |
| Size | -Xmx2g | Set maximum heap |
| `-XX` value | -XX:MaxRAMPercentage=75.0 | Set maximum RAM percentage for the heap |
| Stack | -Xss1m | Set stack size per thread |

`-XX` options are primarily HotSpot VM-specific options. They may change across JDK versions and vendors; do not treat them as a stable Java API.

## 2. Distinguishing VM flags and system properties

Both VM flags and system properties can be passed when launching Java, but they serve different purposes.

### VM flag

Flags control the JVM or a runtime feature:

~~~bash
java -Xmx2g -XX:+HeapDumpOnOutOfMemoryError -jar service.jar
~~~

### System property

A system property is a name/value pair passed with `-D`. Applications can read it using `System.getProperty`:

~~~bash
java -Dapp.region=ap-southeast-1 -Dapp.mode=production -jar service.jar
~~~

In Java:

~~~java
String region = System.getProperty("app.region");
~~~

| Aspect | VM flag | System property |
|---|---|---|
| Common syntax | -X..., -XX:... | -Dname=value |
| Purpose | Configure the JVM/HotSpot | Provide configuration for applications and libraries |
| Example | -Xmx2g | -Dapp.region=ap-southeast-1 |
| Reading tools | jinfo -flag, jinfo -flags, jcmd VM.flags | jinfo -sysprops, jcmd VM.system_properties |
| Runtime modification | Only certain flags are allowed | Can be changed via System.setProperty; effect depends on the application |

Changing a system property does not automatically change a VM flag. For example, calling `System.setProperty("java.heap.max", "2g")` does not increase the JVM heap.

## 3. What is jinfo used for?

`jinfo` is a command-line utility included with the JDK that prints configuration information for a Java process. This information includes JVM command-line flags and Java system properties.

`jinfo` can:

- Print both JVM flags and system properties.
- Print the current value of a specific flag.
- Enable or disable a boolean flag that the JVM allows to be modified.
- Set the value of a writeable flag.
- Assist in investigating the configuration of a running Java process.

JDK 26 syntax:

~~~bash
jinfo [option] pid
~~~

Where `pid` is the process ID of the target JVM. `jinfo` requires a running Java process.

**Important note:** Java SE 26 documentation marks `jinfo` as experimental and unsupported. The tool may be removed in a future JDK release. Oracle recommends using `jcmd` for modern JVM diagnostics because it provides more diagnostic commands and reduces overhead compared to older utilities like `jinfo`.

This lesson explains `jinfo` so you understand the tool and VM flag syntax. For new operational workflows, prefer `jcmd` or JMX/`HotSpotDiagnosticMXBean` where appropriate.

## 4. Finding the PID of the JVM to inspect

`jinfo` requires the PID of the Java process. You can use `jcmd` or operating system tools to find the PID.

### Using jcmd

~~~bash
jcmd -l
~~~

Example output:

~~~text
4128 com.example.OrderService
7852 org.apache.catalina.startup.Bootstrap
~~~

Actual PIDs and application names will vary. `jcmd -l` does not list all JVMs in some Docker environments that have separate PID namespaces; in that case, run `ps` inside the appropriate container to find the PID.

### Using operating system tools

Linux:

~~~bash
ps -ef | grep '[j]ava'
~~~

Windows PowerShell:

~~~powershell
Get-CimInstance Win32_Process |
    Where-Object { $_.Name -match '^java(w)?\.exe$' } |
    Select-Object ProcessId, Name, CommandLine
~~~

Verify the exact PID, main class, and application path before running any command that may modify configuration.

## 5. jinfo syntax for reading VM flags

### Print all information

~~~bash
jinfo <PID>
~~~

If no option is specified, `jinfo` prints both command-line flags and system properties in name/value form.

The output can be long because the JVM has many properties. Protect the output carefully, as system properties or the command line may sometimes contain internal endpoints, usernames, or sensitive data.

### Print only command-line flags

~~~bash
jinfo -flags <PID>
~~~

The `-flags` option prints the flags passed when the JVM was started. It is useful when you need to recover startup arguments while the application is running.

Do not confuse this output with all default values and ergonomic values chosen by the JVM based on machine configuration. To view the full set of flags and their current values, use `jcmd VM.flags` or `-XX:+PrintFlagsFinal` when starting a new JVM.

### Print only system properties

~~~bash
jinfo -sysprops <PID>
~~~

This command prints system properties in the format:

~~~text
java.version=...
java.home=...
os.name=...
user.dir=...
app.region=...
~~~

The ellipses are placeholder values for illustration; actual values depend on the process and environment.

### Print a specific VM flag

~~~bash
jinfo -flag HeapDumpOnOutOfMemoryError <PID>
~~~

The `-flag name` syntax prints the name and current value of the specified flag. This is the right choice when you only need to check a single flag rather than printing the entire JVM configuration.

## 6. Enabling, disabling, and setting values with jinfo -flag

`jinfo` supports the following `-flag` syntax forms:

| Syntax | Effect |
|---|---|
| -flag name | Print the flag name and value |
| -flag +name | Enable a boolean flag |
| -flag -name | Disable a boolean flag |
| -flag name=value | Set the flag to the specified value |

### Enable a boolean flag

Example enabling heap dump creation when an `OutOfMemoryError` occurs:

~~~bash
jinfo -flag +HeapDumpOnOutOfMemoryError <PID>
~~~

### Disable a boolean flag

~~~bash
jinfo -flag -HeapDumpOnOutOfMemoryError <PID>
~~~

### Set a value-based flag

For flags that take a value, use the `name=value` syntax:

~~~bash
jinfo -flag HeapDumpPath=./dumps <PID>
~~~

The target directory must exist and the JVM must have write permissions when creating the heap dump. Only change this flag after confirming the storage location, available disk space, and data protection policy.

### Verify after making a change

Read the flag again:

~~~bash
jinfo -flag HeapDumpOnOutOfMemoryError <PID>
~~~

Or use `jcmd`:

~~~bash
jcmd <PID> VM.flags
~~~

Do not assume a change succeeded simply because the command printed no error. Read back the value and verify actual behavior if the flag affects the application.

## 7. Not all VM flags can be changed at runtime

Some flags can be changed dynamically, mainly diagnostic options that the JVM marks as writeable. Other flags only take effect when the JVM initializes.

Examples:

| Flag | Usage | Modifiability |
|---|---|---|
| HeapDumpOnOutOfMemoryError | Automatically create a heap dump on OOME | Diagnostic option dynamically modifiable on supported HotSpot |
| HeapDumpPath | Choose the heap dump location | Diagnostic option dynamically modifiable on supported HotSpot |
| Xms | Initial heap | Set at startup |
| Xmx | Maximum heap | Set at startup; do not use jinfo to change after startup |
| Xss | Thread stack size | Set at startup |
| UseG1GC | Select GC | Configured at startup |
| MaxRAMPercentage | Percentage of RAM used to calculate maximum heap | Configured at startup |

This table lists common cases; exact capabilities depend on the JDK, vendor, and JVM implementation.

A flag may exist but not be writeable. When attempting to change an unsupported flag, `jinfo` or the diagnostic interface will report an error. Do not trial-and-error a batch of flags in production to see which ones work.

### Diagnostic options and writeability

`HotSpotDiagnosticMXBean` provides the list of writeable diagnostic options. This API allows:

- `getDiagnosticOptions()`: retrieves the list of diagnostic options.
- `getVMOption(name)`: retrieves the value and metadata of a VM option.
- `setVMOption(name, value)`: sets a new value if the option is writeable.

A `VMOption` object contains the following information:

- `getName()`: option name.
- `getValue()`: value at the time the object was created.
- `getOrigin()`: origin of the value.
- `isWriteable()`: whether the option can be changed dynamically.

If `isWriteable()` returns `false`, `HotSpotDiagnosticMXBean.setVMOption` cannot be used to change that option.

## 8. Origin of VM option values

A flag's value can come from several sources:

| Origin | Meaning |
|---|---|
| DEFAULT | The JVM is using the default value |
| VM_CREATION | The value was set at JVM creation time, typically via the command line |
| ENVIRON_VAR | The value came from an environment variable |
| CONFIG_FILE | The value came from a configuration file |
| MANAGEMENT | The value was changed via a management interface after JVM startup |
| ERGONOMIC | The JVM chose the value automatically based on the environment and configuration |
| ATTACH_ON_DEMAND | The value was set via the attach framework |
| OTHER | Another source |

The origin helps explain why the current value differs from the default. For example, the maximum heap size may be chosen by the JVM based on machine RAM rather than a value passed directly by a developer.

For configuration auditing, record the flag name, value, origin, JDK version, and collection timestamp.

## 9. Using jcmd instead of jinfo in modern workflows

`jcmd` is the diagnostic command tool recommended by Oracle in place of `jinfo` for modern JVM diagnostics.

### Print flags and current values

~~~bash
jcmd <PID> VM.flags
~~~

`VM.flags` prints VM flags and their current values.

To view all flags supported by the VM:

~~~bash
jcmd <PID> VM.flags -all
~~~

### Modify a writeable flag

~~~bash
jcmd <PID> VM.set_flag HeapDumpOnOutOfMemoryError true
~~~

`VM.set_flag` sets a VM flag by the provided name and value. The flag must exist, the value must be valid, and the JVM must allow dynamic modification.

### Verify again

~~~bash
jcmd <PID> VM.flags -all
~~~

Look for `HeapDumpOnOutOfMemoryError` in the output to confirm the value.

### Read system properties and command line

~~~bash
jcmd <PID> VM.system_properties
jcmd <PID> VM.command_line
~~~

- `VM.system_properties` prints the system properties.
- `VM.command_line` prints the command line used to launch the JVM.

These are useful equivalents when replacing habits of using `jinfo -sysprops` or `jinfo` with no options.

### Discover commands on the target JVM

~~~bash
jcmd <PID> help
jcmd <PID> help VM.set_flag
jcmd <PID> help VM.flags
~~~

The list of diagnostic commands can differ across JDK versions and JVM vendors. Check `help` on the target process itself before putting commands into automation.

## 10. Java example: reading value and writeability with HotSpotDiagnosticMXBean

Java provides an API for managing HotSpot diagnostic options via the `jdk.management` module. The following example reads the value, origin, and writeability of the `HeapDumpOnOutOfMemoryError` flag.

Create `VmFlagInspector.java`:

~~~java
import com.sun.management.HotSpotDiagnosticMXBean;
import com.sun.management.VMOption;
import java.lang.management.ManagementFactory;

public class VmFlagInspector {
    public static void main(String[] args) {
        HotSpotDiagnosticMXBean bean =
                ManagementFactory.getPlatformMXBean(
                        HotSpotDiagnosticMXBean.class);

        VMOption option =
                bean.getVMOption("HeapDumpOnOutOfMemoryError");

        System.out.println("name=" + option.getName());
        System.out.println("value=" + option.getValue());
        System.out.println("writeable=" + option.isWriteable());
        System.out.println("origin=" + option.getOrigin());
    }
}
~~~

Compile and run on JDK 17 or later:

~~~bash
javac --add-modules jdk.management VmFlagInspector.java
java --add-modules jdk.management VmFlagInspector
~~~

With default HotSpot settings, without setting this flag via the command line or management interface, the output is:

~~~text
name=HeapDumpOnOutOfMemoryError
value=false
writeable=true
origin=DEFAULT
~~~

Explanation:

- `value=false`: The JVM currently does not automatically generate a heap dump on `OutOfMemoryError`.
- `writeable=true`: The option can be changed dynamically in a supporting HotSpot implementation.
- `origin=DEFAULT`: The current value comes from the JVM default.

If you run the JVM with `-XX:+HeapDumpOnOutOfMemoryError`, the value and origin will differ from the example above.

This example only reads the configuration of the JVM running the program itself. To inspect another process, use `jinfo`/`jcmd` or connect to a properly configured and secured management interface.

## 11. Hands-on example: changing a VM flag on a running JVM

This example creates a simple Java process so you can attach to it from a second terminal.

Create `FlagTarget.java`:

~~~java
public class FlagTarget {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("vm-flag-target-ready");

        while (true) {
            Thread.sleep(1_000);
        }
    }
}
~~~

### Step 1: compile

~~~bash
javac --release 17 FlagTarget.java
~~~

### Step 2: launch the target JVM

~~~bash
java -XX:-HeapDumpOnOutOfMemoryError FlagTarget
~~~

Exact output:

~~~text
vm-flag-target-ready
~~~

Keep this process running. Open a second terminal to perform the remaining steps.

### Step 3: find the PID

~~~bash
jcmd -l
~~~

Find the line with the main class `FlagTarget` and note its PID.

### Step 4: read the flag with jinfo

~~~bash
jinfo -flag HeapDumpOnOutOfMemoryError <PID>
~~~

The flag is initially set to `false` by the `-XX:-HeapDumpOnOutOfMemoryError` option. The exact output format depends on the version and tool display; what you need to confirm is that the current value is `false`.

### Step 5: enable the flag dynamically

~~~bash
jinfo -flag +HeapDumpOnOutOfMemoryError <PID>
~~~

If `jinfo` is supported in your environment and the JVM allows writing this flag, the value is enabled in the current process.

You can use `jcmd` instead:

~~~bash
jcmd <PID> VM.set_flag HeapDumpOnOutOfMemoryError true
~~~

### Step 6: verify

~~~bash
jcmd <PID> VM.flags -all
~~~

Find `HeapDumpOnOutOfMemoryError` and confirm the value has changed to `true`.

### Step 7: finish

Return to the terminal running `FlagTarget` and press `Ctrl+C`.

This example does not intentionally trigger an `OutOfMemoryError`. The goal is simply to demonstrate that a diagnostic flag can be enabled dynamically and read back. In a real environment, enabling heap dumps can create very large files when an application runs out of heap; confirm the storage location, disk capacity, and permissions before enabling it.

## 12. Runtime changes do not mean startup configuration changes

When `jinfo` or `jcmd` changes a writeable flag, the new value takes effect in the current JVM process.

That change is generally not persisted automatically to:

- Application startup scripts.
- Dockerfiles or container commands.
- Kubernetes manifests.
- `systemd` units.
- Service wrappers.
- Deployment configuration files.
- Environment variables used at startup.

When the process restarts, the JVM re-reads the startup configuration and supported configuration sources. If you do not save the change into the deployment configuration, the dynamic value may revert to the default or the original startup value.

Proper workflow:

1. Use runtime flag changes for investigation or temporary mitigation when appropriate.
2. Record the old value, new value, reason, timestamp, and operator.
3. Verify application behavior.
4. If the change is needed long-term, update the startup configuration through the deployment process.
5. Restart during an approved maintenance window if the flag only applies at startup.
6. Re-check the value after the restart.

Do not treat a successful `jinfo` command as proof that the configuration has been persistently saved.

## 13. Which flags should be set at startup?

Flags that affect heap structure, garbage collector selection, thread stacks, the module system, or VM initialization generally must be set at startup.

Example:

~~~bash
java -Xms512m -Xmx2g -Xss1m -XX:+UseG1GC -jar service.jar
~~~

Do not use `jinfo` to try to change `Xms`, `Xmx`, `Xss`, or collector selection on an already running JVM. If adjustments are needed, update the startup configuration and restart according to your process.

Diagnostic flags such as `HeapDumpOnOutOfMemoryError` or `HeapDumpPath` may be writeable on HotSpot. The actual list of writeable flags should be checked via `HotSpotDiagnosticMXBean` or the JVM's command help.

## 14. How do jinfo, jcmd, and HotSpotDiagnosticMXBean differ?

| Tool/API | Read flags | Modify flags | Best suited for |
|---|---|---|---|
| jinfo | Yes | Some flags | Compatibility and learning legacy syntax; experimental/unsupported |
| jcmd VM.flags | Yes | No, read-only | Diagnosing current values |
| jcmd VM.set_flag | Not primary purpose | Flags permitted by the JVM | Changing flags via diagnostic command |
| HotSpotDiagnosticMXBean | Yes | Writeable diagnostic options | Management integration via Java/JMX |
| java -XX:+PrintFlagsFinal | Prints flags of a new JVM at launch | No | Checking default/ergonomic values of a new initialization |

`jcmd` is the recommended CLI choice for modern diagnostics. `HotSpotDiagnosticMXBean` is suitable when a management application or JMX tool needs to view and modify writeable diagnostic options.

## 15. Common errors and troubleshooting

### jinfo cannot find the process

**Symptom:** The tool reports that it cannot find the PID or that it is not a Java process.

**Cause:** Wrong PID, the process has stopped, the JVM is running in a different PID namespace, or the user lacks access permissions.

**Resolution:** Use `jcmd -l` or OS tools inside the right container/host; verify the PID and runtime environment before attaching.

### jinfo is not in the JDK

**Symptom:** The shell reports `command not found` or the `jinfo` executable cannot be found.

**Cause:** The JDK distribution does not package this tool, or a future version has removed the unsupported tool.

**Resolution:** Use `jcmd VM.flags`, `VM.system_properties`, `VM.command_line`, and `VM.set_flag` if supported by the target JVM. Do not download an unverified `jinfo` binary to run in production.

### jinfo attach does not work on Windows

**Symptom:** Errors related to `dbgeng.dll`, `jvm.dll`, or debugging tools.

**Cause:** The JDK 26 `jinfo` documentation notes that on Windows, a missing `dbgeng.dll` may require installing Debugging Tools for Windows; `PATH` must contain the location of `jvm.dll` for the target process or core dump.

**Resolution:** Verify JDK/tool compatibility, `PATH`, and debugging tools components per platform documentation. If `jinfo` is not required, use `jcmd` supported on that environment.

### Flag does not exist

**Symptom:** `jinfo` or `jcmd` reports that the flag was not found.

**Cause:** Misspelled name, the flag was changed or removed in another JDK version, or the flag is not available on the current vendor/VM.

**Resolution:** Check the JDK version and flag name in the documentation for that exact version; use `jcmd VM.flags -all` to see flags supported by the VM.

### Flag cannot be changed dynamically

**Symptom:** The tool reports that the flag is not writeable, not manageable, or cannot be updated.

**Cause:** The flag only applies at startup, or the JVM does not mark the option as writeable.

**Resolution:** Check `VMOption.isWriteable()` or the `getDiagnosticOptions()` list; if not writeable, change the startup configuration and restart per your process.

### Invalid value

**Symptom:** The JVM rejects the new value.

**Cause:** Wrong type, wrong unit, out of range, or violates constraints between flags.

**Resolution:** Check the flag's help and documentation; use the correct unit, type, and value range. Do not test random values in production.

### Flag changed but the application does not behave as expected

**Symptom:** `jinfo`/`jcmd` reports success, but the application does not change as anticipated.

**Cause:** The flag does not control the observed behavior, the subsystem was already initialized earlier, or the application uses its own configuration.

**Resolution:** Read the flag documentation, verify the value after changing it, and test actual behavior. Some flags only affect subsequent allocations, OOMEs, or operations.

### Value reverts after restart

**Symptom:** The flag was changed at runtime, but after a restart it returns to the old value.

**Cause:** Runtime changes do not update startup scripts/configuration.

**Resolution:** Update the deployment configuration and verify the startup arguments of the new process.

### Confusing flags and system properties

**Symptom:** Using `jinfo -flag` with a property name created with `-D`, or looking for a flag in `-sysprops`.

**Cause:** Mixing up the two types of configuration.

**Resolution:** Use `jinfo -flag` or `jcmd VM.flags` for VM options; use `jinfo -sysprops` or `jcmd VM.system_properties` for system properties.

## 16. Safety when changing VM flags

Changing VM flags can affect performance, memory, garbage collection, logging, or diagnostic artifact generation.

Before changing:

- Confirm the exact PID and environment.
- Record the current value.
- Verify whether the flag is writeable.
- Read documentation on side effects and effective scope.
- Prepare a rollback value.
- Assess disk capacity if the flag generates heap dumps or logs.
- Determine whether the change is temporary or needs to be saved to startup config.
- Check attach permissions and administrative privileges.

After changing:

- Read the flag again to confirm.
- Monitor logs, metrics, and application behavior.
- Document the change in an incident/change record.
- Revert if the goal is not achieved.
- Update the startup configuration if the change must persist across restarts.

Do not use VM flags to disable security checks, bypass certificate validation, or relax policies just to hide errors. Every change should have a clear reason, scope, and recovery plan.

## 17. Checklist for working with VM flags

- [ ] Identify the JDK version and JVM vendor of the target process.
- [ ] Identify the exact PID.
- [ ] Distinguish VM flags from system properties.
- [ ] Use `jinfo -flag name` to read a single flag when `jinfo` is available.
- [ ] Use `jinfo -flags` to view flags passed at startup.
- [ ] Use `jinfo -sysprops` to view system properties.
- [ ] Prefer `jcmd VM.flags` and `VM.system_properties` in modern workflows.
- [ ] Use `jcmd VM.flags -all` to view all flags supported by the VM.
- [ ] Only modify flags that the JVM allows to be written.
- [ ] Check writeability using `HotSpotDiagnosticMXBean` when needed.
- [ ] Use the correct boolean syntax `+name`/`-name` or `name=value`.
- [ ] Read back the value after making a change.
- [ ] Update the startup configuration if the value must persist after a restart.
- [ ] Record the old value, new value, reason, and timestamp of the change.
- [ ] Test actual behavior and have a rollback plan.

## 18. Official references

- [The jinfo Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jinfo.html) — experimental/unsupported status, `-flag`, `-flags`, and `-sysprops` syntax.
- [The jcmd Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html) — `VM.flags`, `VM.set_flag`, `VM.system_properties`, and replacement diagnostic commands.
- [Diagnostic Tools — Java SE 26 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html) — recommendation to use `jcmd` instead of `jinfo` and how to use `jinfo` to inspect JVM configuration.
- [HotSpotDiagnosticMXBean — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.management/com/sun/management/HotSpotDiagnosticMXBean.html) — `getDiagnosticOptions`, `getVMOption`, and `setVMOption`.
- [VMOption — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.management/com/sun/management/VMOption.html) — value, origin, and `isWriteable` of a VM option.
- [VMOption.Origin — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.management/com/sun/management/VMOption.Origin.html) — `DEFAULT`, `VM_CREATION`, `ENVIRON_VAR`, `CONFIG_FILE`, `MANAGEMENT`, and `ERGONOMIC` origins.
- [The java Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — launcher options, JVM flags, and how to verify flag values.

VM flags let you configure JVM behavior. `jinfo` provides a concise syntax to read and modify certain flags, but because the tool is marked unsupported, prefer `jcmd` and `HotSpotDiagnosticMXBean` in modern systems. Only modify writeable options, verify the value afterward, and persist long-term changes to your startup configuration when needed.
