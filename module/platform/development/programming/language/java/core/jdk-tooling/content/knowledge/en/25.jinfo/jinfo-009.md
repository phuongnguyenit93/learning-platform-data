# jinfo and jcmd in the JDK

`jinfo` and `jcmd` can both retrieve configuration information from a running JVM. `jinfo` is an older tool focused on VM flags and Java system properties; `jcmd` is a more general diagnostic tool that lets you send many diagnostic commands to the JVM, such as viewing flags, properties, command line, heap, threads, and other runtime data.

In modern JDKs, you should prefer `jcmd` for new work. `jinfo` is still useful when you need to quickly read or change certain VM flags in legacy systems, but Oracle classifies it as experimental/unsupported and recommends using `jcmd` instead.

## 1. What is jinfo used for?

`jinfo` generates a configuration report for a Java process. The information typically includes:

- VM flags and their current values, such as `-Xms`, `-Xmx`, or `-XX` flags.
- Java system properties, such as `java.version`, `java.class.path`, `user.dir`.
- Specific flags by name.
- The ability to enable/disable or change the value of certain VM flags that can be modified while the JVM is running.

Basic syntax:

~~~text
jinfo <option> <pid>
~~~

`pid` is the process ID of the target JVM. You can use `jps -l`, `jcmd -l`, or OS tools to find the process before calling `jinfo`.

`jinfo` works with a running JVM. For a post-crash core dump, use the Serviceability Agent variant `jhsdb jinfo`; do not pass a core file as if it were the PID of a running process.

## 2. Support status and when to use jcmd

`jinfo` is described by Oracle as an experimental and unsupported tool. It may change or be removed in future JDK releases. In the Oracle JDK 24 Troubleshooting Guide, Oracle recommends using `jcmd` instead of the older `jinfo` tool for richer diagnostics and lower overhead.

`jcmd` can:

- List local JVMs.
- Retrieve VM flags, system properties, and command line.
- View JVM version, uptime, and information.
- Send diagnostic commands available on the target JVM.
- Change certain VM flags that are manageable at runtime.
- Run many other diagnostic commands beyond the scope of `jinfo`.

Therefore:

- Use `jinfo` when supporting a legacy system or when you need a quick, familiar operation.
- Use `jcmd` for new diagnostic workflows, operational scripts, and collecting JVM information.
- Check `jcmd <pid> help` because the list of commands depends on the JVM, JDK version, and provider.

## 3. jinfo options

Check the help output:

~~~bash
jinfo -help
~~~

On Azul OpenJDK 24.0.2, the help output shows:

~~~text
Usage:
    jinfo <option> <pid>

where <option> is one of:
    -flag <name>         to print the value of the named VM flag
    -flag [+|-]<name>    to enable or disable the named VM flag
    -flag <name>=<value> to set the named VM flag to the given value
    -flags               to print VM flags
    -sysprops            to print Java system properties
    <no option>          to print both VM flags and system properties
    -? | -h | --help | -help to print this help message
~~~

Main options:

| Option | Function |
|---|---|
| `-flags` | Prints VM flags and their current values. |
| `-sysprops` | Prints Java system properties as name/value pairs. |
| `-flag <name>` | Reads the value of a single VM flag. |
| `-flag +<name>` | Enables a boolean VM flag if it can be changed at runtime. |
| `-flag -<name>` | Disables a boolean VM flag if it can be changed at runtime. |
| `-flag <name>=<value>` | Sets a new value for a VM flag that can be changed at runtime. |
| No option | Prints both VM flags and Java system properties. |
| `-h`, `-help`, `--help`, `-?` | Displays the help message. |

For example, to read the full configuration:

~~~bash
jinfo 49344
~~~

Read only flags:

~~~bash
jinfo -flags 49344
~~~

Read only properties:

~~~bash
jinfo -sysprops 49344
~~~

The commands above are read-only operations. The `-flag +name`, `-flag -name`, and `-flag name=value` forms can alter JVM state, so verify the flag and its impact before running them.

## 4. Reading a specific VM flag

Use `-flag <name>` to read the value of a flag:

~~~bash
jinfo -flag MaxHeapSize 49344
~~~

Actual output on JDK 24.0.2 during testing:

~~~text
-XX:MaxHeapSize=134217728
~~~

That value equals 128 MiB. The `MaxHeapSize` flag represents the maximum heap limit of the JVM for that run.

Another example:

~~~bash
jinfo -flag HeapDumpOnOutOfMemoryError 49344
~~~

Output when the flag is disabled:

~~~text
-XX:-HeapDumpOnOutOfMemoryError
~~~

Output conventions:

- `-XX:+FlagName`: boolean flag is enabled.
- `-XX:-FlagName`: boolean flag is disabled.
- `-XX:FlagName=Value`: flag with a numeric or string value.

Do not assume a flag is writable just because `jinfo` can read it. Readability and mutability are two different things.

## 5. Reading VM flags with -flags

Use:

~~~bash
jinfo -flags 49344
~~~

The output looks like:

~~~text
VM Flags:
-XX:InitialHeapSize=33554432
-XX:MaxHeapSize=134217728
-XX:+UseCompressedOops
-XX:+UseG1GC
...
~~~

The list and order of flags vary by JVM version, collector, hardware, and startup configuration. Some values may be defaults chosen by the JVM rather than options passed directly on the command line by the operator.

`jinfo -flags` is suitable when you want a quick look at the current flag configuration. If you need the full list of flags supported by the VM, use `jcmd`:

~~~bash
jcmd 49344 VM.flags -all
~~~

The `VM.flags -all` command instructs the JVM to print all flags supported by the VM. The output can be very long; filter by flag name when investigating a specific value.

## 6. Reading Java system properties with -sysprops

Java system properties are name/value pairs used by the JVM or the application. They can be set at startup with `-Dname=value` or changed programmatically with `System.setProperty`.

Read all properties:

~~~bash
jinfo -sysprops 49344
~~~

Part of the output from testing:

~~~text
app.profile=qa
app.runtime.mode=diagnostic
java.vm.name=OpenJDK 64-Bit Server VM
java.class.path=...\\out
~~~

For example, an application started with:

~~~bash
java -Dapp.profile=qa -cp out com.acme.JInfoDemo
~~~

will have the property:

~~~text
app.profile=qa
~~~

If the code executes `System.setProperty("app.runtime.mode", "diagnostic")`, that runtime property also appears when running `jinfo -sysprops` while the JVM is running.

Do not confuse Java system properties with environment variables. `System.getProperty("app.profile")` reads a system property; `System.getenv("APP_PROFILE")` reads an environment variable. `jinfo -sysprops` is not a command to list all OS environment variables.

## 7. Printing both flags and properties

If you pass no options:

~~~bash
jinfo 49344
~~~

`jinfo` prints both Java system properties and VM flags. The output typically has sections like:

~~~text
Java System Properties:
app.profile=qa
java.class.path=...
java.version=24.0.2
...

VM Flags:
-XX:InitialHeapSize=33554432
-XX:MaxHeapSize=134217728
...

jvm_args: -Xms32m -Xmx128m -Dapp.profile=qa
~~~

This is a quick way to collect initial configuration data when debugging. However, the output can be long and may contain sensitive information such as classpath, username, internal directories, custom application system properties, or secrets if the application is configured insecurely.

Do not post raw output to public tickets or shared logs before reviewing it for sensitive data.

## 8. Changing a boolean VM flag with jinfo

`jinfo` can enable or disable certain boolean flags while the JVM is running:

~~~bash
jinfo -flag +HeapDumpOnOutOfMemoryError 49344
~~~

Read it back to verify:

~~~bash
jinfo -flag HeapDumpOnOutOfMemoryError 49344
~~~

Output after enabling:

~~~text
-XX:+HeapDumpOnOutOfMemoryError
~~~

Disable it again:

~~~bash
jinfo -flag -HeapDumpOnOutOfMemoryError 49344
~~~

Read it back:

~~~bash
jinfo -flag HeapDumpOnOutOfMemoryError 49344
~~~

Output:

~~~text
-XX:-HeapDumpOnOutOfMemoryError
~~~

`HeapDumpOnOutOfMemoryError` instructs the JVM to write a heap dump when an `OutOfMemoryError` occurs. Enabling this flag can help investigate memory issues, but heap dump files can be very large and contain sensitive application data.

Only enable it once you have verified the output path, disk space, access permissions, and procedures for protecting dump files.

## 9. Setting a flag value with name=value

For a flag that can be changed at runtime, the general syntax is:

~~~bash
jinfo -flag FlagName=NewValue <pid>
~~~

This syntax is used for flags with corresponding types and values, such as numbers or strings. For boolean flags, the plus/minus form is usually easier to read:

~~~bash
jinfo -flag +HeapDumpOnOutOfMemoryError 49344
~~~

Only use `name=value` if the flag supports runtime updates and the new value is valid. Not all `-XX` flags can be changed after the JVM has started. Some flags only take effect during initialization; attempting to change them will fail.

Do not take the fact that `jinfo` has a value-setting syntax as proof that every flag can be modified.

## 10. Why can only some flags be changed?

HotSpot classifies certain VM flags as manageable. These flags are allowed to be updated while the JVM is running. Other flags may be locked at startup because the VM already used them to configure the heap, collector, JIT, or internal structures.

For example:

- `HeapDumpOnOutOfMemoryError` can be changed while the JVM is running.
- `MaxHeapSize` is the maximum heap configuration established at startup and cannot be arbitrarily increased with `jinfo`.
- Other flags must be checked against the documentation for the exact HotSpot version.

Before making a change:

1. Read the current value with `jinfo -flag FlagName <pid>`.
2. Verify that the flag supports runtime changes.
3. Determine the impact and preconditions.
4. Record the old value so you can revert it.
5. Make the change within a controlled scope.
6. Read the flag back to verify.
7. Monitor the application after the change.

Runtime changes typically persist only for the lifetime of the current JVM process. When the process restarts, values may revert to the startup configuration or defaults.

## 11. What is jcmd?

`jcmd` is the JDK's general-purpose diagnostic tool used to send diagnostic commands to a running JVM.

Syntax:

~~~text
jcmd <pid | main-class> <command> [arguments]
~~~

Common forms:

~~~bash
jcmd -l
jcmd 49344 help
jcmd 49344 VM.flags
jcmd 49344 VM.system_properties
jcmd 49344 VM.command_line
~~~

- `jcmd -l` lists local JVMs visible to the tool.
- `jcmd <pid> help` lists diagnostic commands supported by the target JVM.
- `jcmd <pid> VM.flags` reads VM flags.
- `jcmd <pid> VM.system_properties` reads Java system properties.
- `jcmd <pid> VM.command_line` shows the command line used to launch the JVM.

The list of diagnostic commands depends on the JVM version and implementation. Query `help` on the target JVM itself rather than relying on a fixed command list from another machine.

## 12. Using jcmd instead of jinfo read operations

Common read operations can be migrated to `jcmd`:

| Need | jinfo | jcmd |
|---|---|---|
| List local JVMs | Usually use `jps` to find PID | `jcmd -l` |
| Read VM flags | `jinfo -flags <pid>` | `jcmd <pid> VM.flags` |
| Read all supported VM flags | No clear direct equivalent mode | `jcmd <pid> VM.flags -all` |
| Read a specific flag | `jinfo -flag Name <pid>` | `jcmd <pid> VM.flags -all` and filter by name |
| Read system properties | `jinfo -sysprops <pid>` | `jcmd <pid> VM.system_properties` |
| View startup command line | Included in combined report | `jcmd <pid> VM.command_line` |
| Enable/disable a manageable boolean flag | `jinfo -flag +Name/-Name <pid>` | `jcmd <pid> VM.set_flag Name true/false` |
| Set a manageable flag value | `jinfo -flag Name=Value <pid>` | `jcmd <pid> VM.set_flag Name Value` |

Example of retrieving information with `jcmd`:

~~~bash
jcmd 49344 VM.flags
jcmd 49344 VM.system_properties
jcmd 49344 VM.command_line
~~~

Read all flags:

~~~bash
jcmd 49344 VM.flags -all
~~~

Keep in mind that `jinfo` is not a shorthand for every diagnostic command. `jcmd` has many specialized commands for heap, GC, threads, JFR, and VM components that `jinfo` does not provide.

## 13. Changing a VM flag with jcmd VM.set_flag

`jcmd` provides the `VM.set_flag` diagnostic command to set a VM flag:

~~~bash
jcmd 49344 VM.set_flag HeapDumpOnOutOfMemoryError true
~~~

Output when the operation succeeds:

~~~text
49344:
Command executed successfully
~~~

Check the value:

~~~bash
jinfo -flag HeapDumpOnOutOfMemoryError 49344
~~~

Or using `jcmd`:

~~~bash
jcmd 49344 VM.flags
~~~

Disable the flag:

~~~bash
jcmd 49344 VM.set_flag HeapDumpOnOutOfMemoryError false
~~~

In testing on Azul OpenJDK 24.0.2, `jinfo` was able to enable `HeapDumpOnOutOfMemoryError` and `jcmd VM.set_flag` was able to disable it again; a subsequent read confirmed the flag returned to false.

`VM.set_flag` is still subject to HotSpot's manageable flags restrictions. It does not allow arbitrarily changing any JVM configuration after startup.

## 14. Complete example: Java 17+ and jinfo/jcmd

The following example creates a JVM with a system property at startup, then sets an additional property at runtime to test how the tools read configuration.

Structure:

~~~text
jinfo-demo/
└── src/
    └── com/
        └── acme/
            └── JInfoDemo.java
~~~

File `src/com/acme/JInfoDemo.java`:

~~~java
package com.acme;

public class JInfoDemo {
    public static void main(String[] args) throws InterruptedException {
        System.setProperty("app.runtime.mode", "diagnostic");
        System.out.println("JInfoDemo ready");
        Thread.sleep(60_000);
    }
}
~~~

### Step 1: compile

From the `jinfo-demo` root directory:

~~~bash
javac --release 17 -d out src/com/acme/JInfoDemo.java
~~~

### Step 2: run the program

~~~bash
java -Xms32m -Xmx128m -Dapp.profile=qa \
  -cp out com.acme.JInfoDemo --mode=inspect
~~~

Exact stdout:

~~~text
JInfoDemo ready
~~~

The application keeps the JVM alive for 60 seconds to allow time for inspection.

### Step 3: find the PID

Open another terminal:

~~~bash
jcmd -l
~~~

Find the line named `com.acme.JInfoDemo` and note its PID. You can also use `jps -l` if needed.

### Step 4: read configuration with jinfo

~~~bash
jinfo -flags <pid>
jinfo -sysprops <pid>
jinfo -flag MaxHeapSize <pid>
~~~

In system properties, you should see:

~~~text
app.profile=qa
app.runtime.mode=diagnostic
~~~

In VM flags, you should see the maximum heap corresponding to `-Xmx128m`, which is 134217728 bytes.

### Step 5: read with jcmd

~~~bash
jcmd <pid> VM.flags
jcmd <pid> VM.system_properties
jcmd <pid> VM.command_line
~~~

The three separate commands let you inspect flags, properties, and the command line individually.

### Step 6: change a manageable flag

~~~bash
jcmd <pid> VM.set_flag HeapDumpOnOutOfMemoryError true
jinfo -flag HeapDumpOnOutOfMemoryError <pid>
~~~

After confirming the state, you can revert it:

~~~bash
jcmd <pid> VM.set_flag HeapDumpOnOutOfMemoryError false
~~~

The example does not trigger an `OutOfMemoryError`, so no heap dump is created. It only verifies the ability to change the flag and read the state back.

## 15. What permissions do jinfo and jcmd require?

Both tools need to connect to the target JVM to retrieve data or send diagnostic commands. Attaching typically depends on:

- The target JVM still running and supporting the attach mechanism.
- Running the tool on the same machine as the target JVM.
- An account with appropriate permissions; for `jcmd`, Oracle requires the same effective user and group that launched the JVM.
- JVM and OS security policies allowing attach.
- Platform and implementation compatibility between the tool and the target JVM.

If the JVM was launched with `-XX:+DisableAttachMechanism`, tools based on the Attach API may not be able to connect.

In containers, PID namespaces can cause the PID visible from the host to differ from the PID inside the container. `jcmd -l` does not list JVMs running in separate Docker processes; identify the PID in the correct namespace and run the tool in the appropriate environment.

Do not run tools with higher privileges than necessary just to bypass attach errors. First verify the process owner, PID, namespace, and security policies.

## 16. jhsdb jinfo and core dumps

Standard `jinfo` reads configuration from a running process. When you need to analyze a core dump after a crash, use the Serviceability Agent's `jhsdb jinfo`.

General syntax:

~~~bash
jhsdb jinfo --exe /path/to/java --core /path/to/core
~~~

- `--exe` points to the Java executable corresponding to the JVM that produced the core dump.
- `--core` points to the core dump to analyze.

The Java binary and the core dump must belong to the corresponding process/build so that the Serviceability Agent can interpret the data accurately. Core dumps can contain sensitive data from application memory; restrict access permissions and storage capacity.

Core dump analysis is different from attaching to a running process. If you only need to inspect the runtime configuration of a live application, use `jcmd`.

## 17. Security when collecting JVM configuration

`jinfo` and `jcmd` can print internal data:

- System properties containing tokens, passwords, or internal endpoints if the application is configured insecurely.
- Command lines that may contain `-Dsecret=value`.
- Classpaths that may reveal directory structures, library names, and deployment locations.
- Heap dumps and core dumps that may contain sensitive data at the memory level.

Safe practices:

- Only run the tools with an account authorized to access the JVM.
- Do not pass passwords or tokens directly in JVM arguments.
- Review output before attaching it to tickets or logs.
- Restrict read permissions on output files and core dumps.
- Do not store diagnostic artifacts in public directories.
- Record the old flag value before making changes.
- Change one flag at a time, monitor the application, and revert if side effects occur.

In particular, `jinfo` has no option to mask or filter all system properties. When you only need a single value, use `-flag <name>` or a specific diagnostic command instead of printing the entire configuration.

## 18. Common errors and troubleshooting

| Symptom | Common cause | Resolution |
|---|---|---|
| `jinfo is not recognized` | JDK `bin` is not in `PATH` or only a runtime is installed. | Check `java -version` and the tool location in the JDK. |
| `AttachNotSupportedException` or unable to attach | JVM has stopped, different user, attach is disabled, or restricted environment. | Verify PID, user/group, namespace, and `DisableAttachMechanism`. |
| `Could not attach to process` | PID is not a compatible JVM or process is no longer running. | Use `jps -l`/`jcmd -l` to find the process again; verify with OS tools. |
| Unable to read a VM flag | Wrong flag name or flag does not exist in that JVM version. | Check `jinfo -flags` or `jcmd <pid> VM.flags -all`. |
| Can read flag but cannot set it | Flag is not manageable at runtime. | Verify manageable status; update startup configuration and restart if needed. |
| System property missing from output | Property was not set, wrong name, or checking the wrong JVM. | Verify PID and use `jcmd <pid> VM.system_properties`. |
| Flag value reverts after restart | Runtime change was not saved to startup configuration. | Update startup scripts/service configuration if you want it to persist across restarts. |
| `jcmd` lacks expected command | Commands depend on JVM version and implementation. | Run `jcmd <pid> help` on the target. |
| Output contains sensitive data | Properties or JVM arguments contain secrets. | Redact values before sharing, restrict access permissions, and move secrets to a secret manager. |

Do not modify security policies or restart production just to test a diagnostic command. Reproduce in a test environment when verifying an operation that can alter JVM state.

## 19. Recommended diagnostic workflow

When investigating JVM configuration:

1. Find the JVM using `jcmd -l` or `jps -l`.
2. Confirm the PID, main class, and process owner.
3. Run `jcmd <pid> help` to check available commands.
4. Retrieve flags with `jcmd <pid> VM.flags`.
5. Retrieve system properties with `jcmd <pid> VM.system_properties`.
6. Retrieve the command line with `jcmd <pid> VM.command_line`.
7. Only use `VM.set_flag` with flags that are allowed to change at runtime.
8. Record the old value, make controlled changes, and verify again.
9. Protect output and diagnostic artifacts.
10. If deeper investigation is needed, look at `jcmd` commands for heap, threads, GC, and JFR.

`jinfo` can be used to read or adjust certain configurations in legacy systems. For new workflows, `jcmd` is the better choice because it offers command discovery, purpose-separated output, and broader diagnostic capabilities.

## 20. References

- Oracle JDK 24 — [Troubleshooting Guide: The jinfo Utility](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf) — sections *The jinfo Utility* and *Troubleshooting with the jinfo Utility*.
- Oracle JDK 24 — [The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html).
- Oracle JDK 24 — [Diagnostic Tools](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html).
