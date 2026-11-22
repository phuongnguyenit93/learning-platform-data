# Unchangeable Flags in jinfo

**`jinfo`** is a JDK diagnostic tool used to inspect the configuration of a running JVM, including VM flags and Java system properties. The tool can also modify certain VM flags while the JVM is running. However, **not every flag can be changed after the JVM has started**.

Flags that do not support dynamic modification typically must be set before starting the application. If you attempt to change them, `jinfo` may return an error such as:

```text
flag 'MaxHeapSize' cannot be changed
```

Understanding the difference between flags that can be managed at runtime (*manageable*) and flags that only take effect at startup helps avoid confusion when configuring the heap, garbage collector, or other runtime components.

## 1. What is a VM flag?

A VM flag is an option that controls the behavior of the Java Virtual Machine (JVM). Most flags are passed when launching the application with `java`, usually prefixed with `-X` or `-XX:`.

Example:

```bash
java -Xms256m -Xmx2g -XX:+UseG1GC -Dapp.profile=production -jar app.jar
```

Meaning:

- `-Xms256m`: initial heap size.
- `-Xmx2g`: maximum heap limit.
- `-XX:+UseG1GC`: requests the use of the G1 garbage collector.
- `-Dapp.profile=production`: sets a Java system property for the application.

Flags can control:

- Heap and garbage collection.
- JIT compiler and code cache.
- Threads, stacks, and runtime.
- Native memory and class metadata.
- Diagnostic logging and heap dumps.
- Other JVM features.

Not all flags can be changed while the application is running. Some values are used by the JVM to allocate memory structures or initialize runtime components from the start.

## 2. What operations does jinfo support?

General syntax:

```text
jinfo <option> <pid>
```

Where `pid` is the process ID of the running JVM.

View help:

```bash
jinfo -h
```

Main options:

| Command | Purpose |
| --- | --- |
| `jinfo <pid>` | Prints VM flags and Java system properties |
| `jinfo -flags <pid>` | Prints VM flags |
| `jinfo -flag <name> <pid>` | Reads the value of a VM flag |
| `jinfo -flag +<name> <pid>` | Enables a Boolean VM flag |
| `jinfo -flag -<name> <pid>` | Disables a Boolean VM flag |
| `jinfo -flag <name>=<value> <pid>` | Sets the value of a VM flag if the flag supports modification |
| `jinfo -sysprops <pid>` | Prints Java system properties |

Example reading the heap limit:

```bash
jinfo -flag MaxHeapSize 18420
```

Example reading a Boolean flag:

```bash
jinfo -flag UseG1GC 18420
```

Example reading system properties:

```bash
jinfo -sysprops 18420
```

The commands above only query state; they do not modify the JVM configuration.

## 3. Why can't some flags be changed?

Some VM flags are only read during JVM initialization. The JVM needs these values to create the heap, select the garbage collector, set up memory regions, or configure runtime components.

Once the process is running, changing a value may require restructuring resources that the JVM does not support replacing safely.

A typical example is `MaxHeapSize`, usually set via `-Xmx` at startup. The JVM uses this limit to establish the heap region. You can read the current value with `jinfo`, but you cannot arbitrarily increase or decrease it in a running process.

Other flags can be changed dynamically if the JVM marks them as manageable. Modifiability depends on the specific flag, JVM version, and implementation/provider.

**Do not infer from the flag name or the `-XX:` prefix alone.** You need to check the flag's metadata on the actual running JVM.

## 4. Distinguishing manageable and non-manageable flags

HotSpot classifies certain flags as **manageable**. These flags are designed to be modifiable through a management interface while the JVM is running.

Flags without the manageable attribute are generally not allowed to be changed dynamically via `jinfo` or `jcmd VM.set_flag`.

| Type | Meaning | How to handle |
| --- | --- | --- |
| Manageable | The JVM allows changing the value at runtime | You can use `jinfo -flag name=value` or `jcmd VM.set_flag` if the command and value are supported |
| Non-manageable | Does not support changing via the management interface at runtime | Set the value at JVM startup and restart the application |
| Unknown/unsupported | The current JVM does not recognize the flag or does not support the operation | Check the flag name, JDK version, and provider |

You can use `jcmd <pid> VM.flags -all` to view flag metadata. Example output:

```text
size_t MaxHeapSize       = 268435456  {product} {command line}
uintx MinHeapFreeRatio   = 20         {manageable} {default}
```

This is illustrative output. The attributes in curly braces have different meanings:

- `{manageable}`: the flag is marked by the JVM as manageable/dynamically modifiable.
- `{product}`: flag classification in HotSpot.
- `{command line}`: the value source was set from the command line.
- `{default}` or `{ergonomic}`: the value source is default or automatically selected by the JVM.

Do not confuse `{product}` with `{manageable}`. A product flag can still disallow dynamic modification.

## 5. Reading the value of an unchangeable flag

Use `jinfo -flag` to read the current value:

```bash
jinfo -flag MaxHeapSize 18420
```

Illustrative output:

```text
-XX:MaxHeapSize=268435456
```

The value `268435456` bytes corresponds to 256 MiB.

You can view all flags:

```bash
jinfo -flags 18420
```

Or use the newer command:

```bash
jcmd 18420 VM.flags -all
```

In the `VM.flags -all` output, locate the flag name and check whether it has the `{manageable}` attribute.

Being able to read a value does not mean it can be changed. `jinfo -flag MaxHeapSize <pid>` succeeding only confirms that the tool can query the flag.

## 6. Attempting to change a non-manageable flag

For example, suppose a JVM is running with:

```bash
java -Xms64m -Xmx256m -cp out FlagTarget
```

Read the value:

```bash
jinfo -flag MaxHeapSize 18420
```

Output:

```text
-XX:MaxHeapSize=268435456
```

Attempt to set the heap limit to 512 MiB:

```bash
jinfo -flag MaxHeapSize=536870912 18420
```

The JVM returns an error similar to:

```text
Exception in thread "main" com.sun.tools.attach.AttachOperationFailedException:
flag 'MaxHeapSize' cannot be changed
```

This error indicates that the flag does not support dynamic modification. The current process retains its original heap limit.

There is no `jinfo` syntax that can force the JVM to change a flag marked as non-writeable. To use the new limit, you must restart the application with the appropriate option.

## 7. Changing a manageable flag while the JVM is running

For example, `MinHeapFreeRatio` is a flag marked as manageable by HotSpot on the test JVM.

Read the current value:

```bash
jinfo -flag MinHeapFreeRatio 18420
```

Output:

```text
-XX:MinHeapFreeRatio=20
```

Change it from 20 to 25:

```bash
jinfo -flag MinHeapFreeRatio=25 18420
```

Read it again:

```bash
jinfo -flag MinHeapFreeRatio 18420
```

Output:

```text
-XX:MinHeapFreeRatio=25
```

The new value is applied to the running JVM. This example shows that `jinfo` can change certain flags; that capability depends on each flag's manageable attribute.

To verify the metadata again:

```bash
jcmd 18420 VM.flags -all
```

The corresponding line may display:

```text
uintx MinHeapFreeRatio = 25 {manageable} {management}
```

Reset the value to 20 if this was only a test operation:

```bash
jinfo -flag MinHeapFreeRatio=20 18420
```

Do not change production flags just to experiment. Before modifying a manageable flag, read the flag's documentation and evaluate its impact on the workload.

## 8. Using jcmd instead of jinfo

`jinfo` is an experimental and unsupported tool according to the JDK documentation. Oracle recommends using `jcmd` for modern JVM diagnostics.

Read all VM flags and metadata:

```bash
jcmd 18420 VM.flags -all
```

Read specific flags:

```bash
jcmd 18420 VM.flags
```

Change a manageable flag:

```bash
jcmd 18420 VM.set_flag MinHeapFreeRatio 25
```

Then verify:

```bash
jcmd 18420 VM.flags -all
```

If you attempt to change a non-writeable flag:

```bash
jcmd 18420 VM.set_flag MaxHeapSize 536870912
```

The JVM may return the message:

```text
only 'writeable' flags can be set
```

This message indicates that the flag is not allowed to be modified through the runtime management mechanism.

`jcmd` is the better choice for modern diagnostic workflows. However, it also cannot change non-manageable flags; the limitation lies in the JVM's capabilities, not in the tool's syntax.

## 9. What to do when a flag cannot be changed?

If a flag is non-manageable, the solution is to update the startup configuration and restart the JVM.

For example, if the application is running with:

```bash
java -Xms64m -Xmx256m -jar app.jar
```

To increase the maximum heap to 512 MiB, update the launch command:

```bash
java -Xms64m -Xmx512m -jar app.jar
```

Operational steps:

1. Read the current value using `jinfo -flag` or `jcmd VM.flags -all`.
2. Determine whether the flag has the manageable attribute.
3. If non-manageable, update the startup configuration of the service/container/script.
4. Evaluate host memory and container limits before increasing the heap.
5. Schedule a restart according to the deployment process.
6. Restart the JVM with the new value.
7. Verify using `jcmd <pid> VM.flags -all` or `jinfo -flag`.

For applications managed by systemd, Docker, Kubernetes, or a service manager, change the configuration where the process is managed. Editing a one-off terminal command does not change the configuration that the orchestrator will use on the next restart.

## 10. Java 17 hands-on example: inspecting flags on a running JVM

Create **`FlagTarget.java`**:

```java
public final class FlagTarget {
    private FlagTarget() {
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("READY=" + ProcessHandle.current().pid());
        Thread.sleep(120_000);
    }
}
```

The program prints its PID and keeps the JVM alive for 120 seconds so diagnostic commands can be sent from another terminal.

Compile:

```bash
javac --release 17 FlagTarget.java
```

Run with a 256 MiB heap and a manageable flag:

```bash
java -Xms64m -Xmx256m -XX:MinHeapFreeRatio=20 FlagTarget
```

Output:

```text
READY=18420
```

The PID is dynamic; use the actual PID printed by the program.

Open a second terminal and inspect:

```bash
jinfo -flag MaxHeapSize 18420
jinfo -flag MinHeapFreeRatio 18420
jcmd 18420 VM.flags -all
```

Try changing the manageable flag:

```bash
jinfo -flag MinHeapFreeRatio=25 18420
jinfo -flag MinHeapFreeRatio 18420
```

Expected result:

```text
-XX:MinHeapFreeRatio=25
```

Try changing `MaxHeapSize`:

```bash
jinfo -flag MaxHeapSize=536870912 18420
```

The expected result is the error `flag 'MaxHeapSize' cannot be changed`.

Check the heap value again:

```bash
jinfo -flag MaxHeapSize 18420
```

The value remains:

```text
-XX:MaxHeapSize=268435456
```

After testing, stop the process with Ctrl+C in the terminal running `FlagTarget`. This example was compiled with `javac --release 17` and tested on HotSpot JDK 24.0.2; flag details may vary by JVM version.

## 11. Distinguishing VM flags and Java system properties

A common misconception is treating Java system properties and VM flags as the same type of configuration.

| Type | Example | How to read |
| --- | --- | --- |
| VM flag | `MaxHeapSize`, `MinHeapFreeRatio`, `UseG1GC` | `jinfo -flag`, `jinfo -flags`, `jcmd VM.flags` |
| Java system property | `app.profile`, `java.io.tmpdir`, `user.timezone` | `jinfo -sysprops`, `jcmd VM.system_properties`, `System.getProperty()` |

Set a system property at startup:

```bash
java -Dapp.profile=production -jar app.jar
```

Read the property in Java:

```java
String profile = System.getProperty("app.profile");
```

Application code can call `System.setProperty("app.profile", "staging")` to change a property in the current process. However, libraries that already read and cached the previous value may not automatically update. Changing a system property also does not change VM flags like `MaxHeapSize`.

`jinfo -sysprops <pid>` only prints system properties; it is not a command for changing properties.

## 12. Boolean flags and value-based flags

`jinfo` has two forms for changing flags:

**Boolean flag:**

```bash
jinfo -flag +HeapDumpOnOutOfMemoryError 18420
jinfo -flag -HeapDumpOnOutOfMemoryError 18420
```

The `+` form enables the flag; the `-` form disables the flag. Use this only if the specific flag supports dynamic modification and the JVM permits the operation.

**Value-based flag:**

```bash
jinfo -flag MinHeapFreeRatio=25 18420
```

The value can be a number or a string depending on the flag type. The JVM validates the type and bounds of the value. Even a manageable flag can reject values outside the valid range.

Before changing:

1. Check the flag name and current value.
2. Confirm the flag is marked as manageable.
3. Read the description and valid value range.
4. Record the initial value so it can be restored.
5. Make the change within controlled limits.
6. Read the value back and observe the impact.

Do not use `+` or `-` with non-Boolean flags.

## 13. Why shouldn't you try to force-change non-manageable flags?

A flag being unchangeable is a JVM design constraint. Trying to bypass this limitation can lead to an inconsistent runtime configuration or application instability.

For example, the maximum heap affects how the JVM manages the heap. If changed arbitrarily after the runtime has initialized, the JVM might have to alter memory structures and assumptions that the collector relies on.

When a flag cannot be changed:

- Do not retry the command with random values.
- Do not change related flags just to work around the error.
- Do not disable attach or security mechanisms to try to force a write.
- Do not edit a running process's configuration file expecting the JVM to reload it automatically.
- Update the startup configuration and restart according to operational procedures.

The `cannot be changed` error is a signal to switch to the startup configuration update workflow.

## 14. Common errors

| Symptom | Common cause | How to resolve |
| --- | --- | --- |
| `flag 'MaxHeapSize' cannot be changed` | The flag does not support dynamic modification | Set a new `-Xmx` and restart the JVM |
| `only 'writeable' flags can be set` | The flag is not marked as writeable by the JVM | Check `VM.flags -all`, use a manageable flag, or restart |
| Flag not found | Wrong name or the flag does not exist in the current JVM | Check `jcmd <pid> VM.flags -all` |
| Value rejected | Wrong type or out-of-range value | Read the flag help/documentation and use a valid value |
| Cannot attach to process | Wrong PID, different user, or attach is disabled | Verify PID, permissions, and JVM configuration |
| Change succeeded but behavior did not change | The flag only affects future operations or the application is unaffected under the current workload | Re-verify the value and observe the workload |
| Flag not visible in default output | The flag is omitted in compact mode or requires viewing full metadata | Use `jcmd <pid> VM.flags -all` |
| Cannot read system property | Confusing system properties with VM flags or the process disallows attach | Use `jinfo -sysprops` or `jcmd VM.system_properties` |

## 15. Notes on versions and tools

`jinfo` is marked as **experimental and unsupported** in the JDK documentation. The tool may change or be removed in future JDK releases. Oracle recommends using `jcmd` for modern JVM diagnostics.

In addition:

- Use a JDK tool that matches the target JVM version.
- Attaching requires process access permissions according to OS policy.
- A JVM may be launched with `-XX:+DisableAttachMechanism`, in which case attach tools will not work.
- Inside containers, pay attention to the PID namespace and the user running the JVM.
- Some flags or options are HotSpot-specific and may not exist in other JVMs.
- Do not parse tool output as a stable format for automation without version control.

For new operational workflows, prefer `jcmd` and supported management interfaces. Regardless of the tool used, non-manageable flags still need to be set at startup.

## 16. Workflow for handling unchangeable flags

When encountering an error that a flag cannot be changed:

1. Record the PID, JDK version, and flag name.
2. Read the current value using `jinfo -flag` or `jcmd VM.flags -all`.
3. Check the `{manageable}` metadata.
4. If the flag is manageable, verify the type, value, and update syntax.
5. If the flag is non-manageable, identify the corresponding startup option.
6. Update the service/container/deployment configuration.
7. Evaluate resources and schedule a restart.
8. Restart the JVM with the new value.
9. Verify the value after the restart.
10. Monitor heap, GC, latency, and related metrics after the change.

Example when needing to increase the heap:

```bash
# Old configuration
java -Xms64m -Xmx256m -jar app.jar

# New configuration after updating startup configuration
java -Xms64m -Xmx512m -jar app.jar
```

After restarting, inspect:

```bash
jcmd <new-pid> VM.flags -all
```

Confirm that `MaxHeapSize` reflects the new configuration. The PID may change after a restart.

## 17. Key takeaways

- `jinfo` reads VM flags and system properties of a running JVM.
- `jinfo -flag <name> <pid>` reads the value of a single flag.
- `jinfo -flag <name>=<value> <pid>` only modifies flags that support runtime management.
- Flags with the `{manageable}` attribute can be changed dynamically if the value is valid.
- Non-manageable flags like `MaxHeapSize` cannot be changed in the current process.
- The error `flag 'MaxHeapSize' cannot be changed` means you need to update the startup option and restart.
- Use `jcmd <pid> VM.flags -all` to view flag values and metadata.
- Use `jcmd <pid> VM.set_flag <name> <value>` for writeable flags.
- VM flags are different from Java system properties; `jinfo -sysprops` only reads system properties.
- `jinfo` is an experimental/unsupported tool; prefer `jcmd` in new workflows.

Understanding which flags can be changed and which can only be set at startup helps you tune the JVM properly, avoiding application disruption from attempting to modify unsupported runtime configurations.
