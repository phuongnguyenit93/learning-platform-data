# Changing Dynamic JVM Flags with jinfo

`jinfo` is a JDK tool for inspecting the configuration of a Java process, including JVM command-line flags and system properties. Its `-flag` option also lets you read or modify **certain VM flags while the JVM is running**.

A dynamic flag is a VM flag that HotSpot allows changing at runtime. Not every flag can be modified dynamically. Only flags marked as `manageable` can be updated through this mechanism. Startup-only flags, such as the garbage collector selection or initial heap size, typically require updating the launch command and restarting the JVM.

You need to understand this limitation before running `jinfo -flag` against a live production process. Changing a flag can affect the heap, garbage collection, logs, or dump files; always check the current value, mutability, blast radius, and rollback plan before making a change.

## 1. What Is a JVM Flag?

A JVM flag is a configuration option for the Java Virtual Machine. Many HotSpot flags are passed at startup with the `-XX:` prefix. For example:

~~~sh
java -XX:MaxHeapFreeRatio=75 -cp out FlagProbe
java -XX:+HeapDumpOnOutOfMemoryError -cp out FlagProbe
java -XX:-UseG1GC -cp out FlagProbe
~~~

The examples above illustrate the syntax:

- `-XX:MaxHeapFreeRatio=75` sets a numeric value.
- `-XX:+HeapDumpOnOutOfMemoryError` enables a boolean flag.
- `-XX:-UseG1GC` disables a boolean flag if that flag is supported and valid for the JVM.

Not every flag can be changed after the JVM has started. Some values are read during VM initialization or affect data structures that have already been allocated, so they can only be configured before the application starts.

A flag that can be changed dynamically is typically marked `manageable` by the JVM. This attribute indicates that the VM allows updating the value at runtime via the diagnostic interface. Other flags may be marked `product`, `diagnostic`, or belong to startup-only categories; do not assume every flag is mutable just because `jinfo` provides a setter option.

## 2. Inspecting Java Processes and Current Flags

General syntax:

~~~sh
jinfo <option> <pid>
~~~

`<pid>` is the process ID of the target JVM. You can list running Java processes with:

~~~sh
jcmd -l
~~~

Or:

~~~sh
jps -l
~~~

Example output:

~~~text
60236 FlagProbe
51276 com.example.Server
~~~

Verify the exact PID before running a command. If multiple Java applications are running, using the wrong PID can alter the configuration of a different process.

To read a specific flag:

~~~sh
jinfo -flag MaxHeapFreeRatio 60236
~~~

Example output:

~~~text
-XX:MaxHeapFreeRatio=70
~~~

`jinfo -flag <name> <pid>` only reads the current value. You do not need to include the `-XX:` prefix in the flag name; the output is typically displayed in `-XX:...` form.

To print VM flags:

~~~sh
jinfo -flags 60236
~~~

To print system properties:

~~~sh
jinfo -sysprops 60236
~~~

If no option is specified, `jinfo <pid>` prints both VM flags and system property pairs. These two categories are distinct: `-XX:...` are VM flags, whereas `-Dname=value` typically defines Java system properties.

## 3. Distinguishing Mutable Flags from Startup-Only Flags

On HotSpot, use `jcmd` to inspect all flags and their attributes:

~~~sh
jcmd 60236 VM.flags -all
~~~

Locate the flag you want to check. Sample lines from the output:

~~~text
bool HeapDumpOnOutOfMemoryError = false {manageable} {default}
uintx MaxHeapFreeRatio = 70 {manageable} {default}
bool UseG1GC = true {product} {ergonomic}
~~~

In this example:

- `HeapDumpOnOutOfMemoryError` and `MaxHeapFreeRatio` carry the `{manageable}` label, so they can be changed dynamically on a JVM that supports them.
- `UseG1GC` does not have the `{manageable}` label; it selects the VM's garbage collector and cannot be changed with `jinfo -flag` on a running process.

Actual output and values depend on the JDK version, JVM vendor, and process configuration. Always inspect the output on the target JVM itself rather than copying flag lists from another machine.

If you attempt to change a flag that is not dynamically manageable, the command may fail with an error similar to:

~~~text
AttachOperationFailedException:
flag 'UseG1GC' cannot be changed
~~~

This error indicates that the flag does not support runtime updates. Set the flag at JVM startup if your JDK version and configuration allow it, then restart the application following your operational procedures.

## 4. Changing Numeric Flags with -flag name=value

Syntax:

~~~sh
jinfo -flag <name>=<value> <pid>
~~~

Example changing `MaxHeapFreeRatio` to 75:

~~~sh
jinfo -flag MaxHeapFreeRatio=75 60236
~~~

Read it back to confirm:

~~~sh
jinfo -flag MaxHeapFreeRatio 60236
~~~

Example output:

~~~text
-XX:MaxHeapFreeRatio=75
~~~

In testing on JDK 24.0.2, this flag started at 70, was changed to 75, and read back successfully. `MaxHeapFreeRatio` is one example of a manageable flag; do not assume all numeric flags are mutable.

The value must match the data type and bounds required by the flag. If you pass an invalid name, wrong type, out-of-range value, or a non-manageable flag, the JVM may reject the change. Do not rely solely on the absence of an error message; always query the value again after setting it.

Some flags have constraints relative to other flags. For example, minimum and maximum heap ratio thresholds must maintain a valid ordering. Check the documentation for the specific flag and inspect related values before making changes.

## 5. Enabling or Disabling Boolean Flags

For boolean flags, use `+` to enable and `-` to disable:

~~~sh
jinfo -flag +HeapDumpOnOutOfMemoryError 60236
jinfo -flag HeapDumpOnOutOfMemoryError 60236
~~~

The first line enables the flag; the second reads its value back. Example output:

~~~text
-XX:+HeapDumpOnOutOfMemoryError
~~~

To disable it:

~~~sh
jinfo -flag -HeapDumpOnOutOfMemoryError 60236
jinfo -flag HeapDumpOnOutOfMemoryError 60236
~~~

Output after disabling:

~~~text
-XX:-HeapDumpOnOutOfMemoryError
~~~

In testing on JDK 24.0.2, `HeapDumpOnOutOfMemoryError` is marked manageable and switched from false to true successfully. This flag causes the JVM to write a heap dump when an `OutOfMemoryError` occurs. Heap dumps can be very large; before enabling this in production, verify available disk space, the target dump path, write permissions, and data protection policies.

Only use the `+name` or `-name` form for boolean flags. For numeric or string flags, use `name=value`.

## 6. Complete Hands-On Example

Create `FlagProbe.java`:

~~~java
public class FlagProbe {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("flag-probe-ready");
        Thread.sleep(120_000);
    }
}
~~~

The program prints a single line and keeps the JVM alive for two minutes so you have time to run commands from another terminal.

Compile:

~~~sh
mkdir -p out
javac -d out FlagProbe.java
~~~

Run:

~~~sh
java -cp out FlagProbe
~~~

Exact stdout:

~~~text
flag-probe-ready
~~~

Open a second terminal and find the PID:

~~~sh
jcmd -l
~~~

Suppose the PID is `60236`. Check the initial value:

~~~sh
jinfo -flag MaxHeapFreeRatio 60236
~~~

Change the value:

~~~sh
jinfo -flag MaxHeapFreeRatio=75 60236
~~~

Confirm:

~~~sh
jinfo -flag MaxHeapFreeRatio 60236
~~~

Check the metadata to confirm the flag is manageable:

~~~sh
jcmd 60236 VM.flags -all
~~~

Find the `MaxHeapFreeRatio` line and confirm it has the `{manageable}` label. When finished, return to the terminal running `FlagProbe` and press `Ctrl+C` to stop the process.

The PID shown here is only an example. Use the actual PID returned by `jcmd -l` on your machine.

## 7. Using jcmd as the Modern Diagnostic Alternative

Oracle recommends using `jcmd` instead of the older `jinfo` utility for new diagnostic workflows. `jinfo` is classified in the JDK documentation as experimental and unsupported; it may be removed in a future JDK release.

With `jcmd`, you can read flags:

~~~sh
jcmd 60236 VM.flags -all
~~~

View the syntax for the flag-setting command:

~~~sh
jcmd 60236 help VM.set_flag
~~~

Change a numeric flag:

~~~sh
jcmd 60236 VM.set_flag MaxHeapFreeRatio 80
~~~

Read it back using `jinfo` or `jcmd`:

~~~sh
jinfo -flag MaxHeapFreeRatio 60236
jcmd 60236 VM.flags -all
~~~

In testing on JDK 24.0.2, `jcmd <pid> VM.set_flag MaxHeapFreeRatio 80` returned `Command executed successfully`, and `jinfo` read back the value 80.

`jcmd` also attaches to the target JVM. Run `jcmd <pid> help` to see the commands available on that JVM version. For new automation workflows, prefer the diagnostic command interface supported by current JDK releases and always verify the result after making a change.

## 8. Dynamic Flags Do Not Persist Across Restarts

A change made with `jinfo -flag` or `jcmd VM.set_flag` applies only to the running JVM. It does not modify launch scripts, service units, Docker images, Gradle/Maven configurations, or deployment parameters.

When the process stops and restarts, the JVM picks up flags from its startup configuration or falls back to defaults. To persist a change across restarts, update the startup configuration through your application's deployment process, for example:

~~~sh
java -XX:MaxHeapFreeRatio=75 -cp out FlagProbe
~~~

For a boolean flag:

~~~sh
java -XX:+HeapDumpOnOutOfMemoryError -cp out FlagProbe
~~~

Never treat a runtime change as a permanently saved configuration. Document the desired value, where startup configuration is managed, and how to roll back.

In addition, some flags are read when a subsystem initializes. Changing the value afterward does not necessarily cause an already-initialized component to reconfigure itself. The exact behavior depends on the flag; check the flag's documentation before expecting an immediate effect.

## 9. Permissions and Attach Requirements

`jinfo` connects to a running Java process through the attach mechanism. Several conditions can cause the command to fail:

- The PID does not exist, the process has exited, or the PID is not a JVM.
- The current user lacks permission to access the target process.
- The JVM was started with `-XX:+DisableAttachMechanism`.
- The tool and target JVM are incompatible or running in different environments.
- The JVM is running inside a container or separate PID namespace, so the host PID differs from the PID inside the container.
- The platform is missing required attach support components.

Run the tool on the same host and under an account with appropriate attach permissions. For containers, determine the PID within the right namespace and execute the command from an environment that can see the target JVM.

On some Windows configurations, the `jinfo` documentation also notes a requirement for Debugging Tools for Windows when `dbgeng.dll` is missing, as well as ensuring `PATH` includes the target JVM's `jvm.dll`. If attach fails on Windows, inspect the specific error message and verify the machine's JDK and native debugging tools configuration.

## 10. Common Errors and Troubleshooting

| Symptom | Common Cause | Resolution |
|---|---|---|
| `jinfo: command not found` | JDK is not installed or JDK `bin` is missing from `PATH` | Check `JAVA_HOME` and `PATH` |
| `flag 'UseG1GC' cannot be changed` | Flag does not support dynamic changes | Check `VM.flags -all`; configure at startup if needed |
| Cannot read PID | Wrong PID, JVM has exited, or running in another container | Use `jcmd -l` and verify the PID in the correct namespace |
| `AttachNotSupportedException` | Attach is disabled or insufficient permissions | Check user account, `DisableAttachMechanism`, and attach environment |
| Flag value does not change | Command rejected, flag is not manageable, or invalid value | Read the error, check metadata, and query again with `-flag <name>` |
| Value reverts to default after restart | Change applied only to the current process | Update startup parameters and redeploy |
| Effect does not appear immediately | Flag only affects events/operations after the change, or component cached the config | Read the flag description and inspect the related component's behavior |
| Flag change causes unexpected impact | Inappropriate flag selected or impact not evaluated | Restore the previous value if still supported and follow rollback procedures |

## 11. Safe Workflow for Changing Dynamic Flags

When you need to change a JVM flag at runtime, follow these steps in order:

1. Identify the exact host, container, and application PID.
2. Record the running JDK/JVM version.
3. Read the current value with `jinfo -flag <name> <pid>`.
4. Run `jcmd <pid> VM.flags -all` to verify whether the flag is labeled `manageable`.
5. Read the flag documentation and check any constraints with related flags.
6. Record the previous value so you can roll back.
7. Change only the specific flag needed using `jinfo -flag` or `jcmd VM.set_flag`.
8. Query the flag again to confirm the new value.
9. Monitor logs, metrics, and application behavior after the change.
10. Update startup configuration if the value must persist across restarts.

Avoid changing multiple flags at once during an incident investigation, as it makes it difficult to isolate which change caused an effect. If a flag is not manageable, stop runtime attempts and plan a restart with the appropriate startup configuration.

### Checklist

- [ ] Verified the correct target PID and JVM.
- [ ] Recorded the JDK/JVM version.
- [ ] Read the current flag value.
- [ ] Confirmed the flag has the `manageable` attribute.
- [ ] Understood the flag's data type, valid range, and impact.
- [ ] Recorded the previous value for rollback.
- [ ] Used the correct syntax: `+/-name` for booleans or `name=value` for other types.
- [ ] Queried the value again after setting it.
- [ ] Monitored the application after the change.
- [ ] Updated startup configuration if the change must persist across restarts.
- [ ] Considered using `jcmd` for new diagnostic workflows.

`jinfo -flag` can read and modify certain JVM flags while a process is running. Checking the `manageable` label, verifying the value after setting it, and remembering that runtime changes do not persist across restarts are the three essential steps to using dynamic flags safely.

## References

- [Oracle JDK 24 — The jinfo Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jinfo.html)
- [Oracle JDK 24 — Troubleshooting Guide, The jinfo Utility](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf)
- [Oracle JDK 24 — The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
