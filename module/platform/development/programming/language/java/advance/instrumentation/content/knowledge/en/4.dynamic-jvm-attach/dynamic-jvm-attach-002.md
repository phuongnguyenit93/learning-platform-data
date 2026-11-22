# Discovering JVM Processes with VirtualMachine.list() and VirtualMachineDescriptor

A profiler, debugger, or Java agent launcher tool often needs to **find the right running Java process** before deciding whether to connect to that JVM. The Attach API provides `VirtualMachine.list()` to discover JVMs and `VirtualMachineDescriptor` to read identification information provided by an *attach provider*.

This lesson focuses on **the discovery and candidate selection step**: how to retrieve the list, properly understand IDs/display names/providers, filter processes, and handle cases where nothing is found. Listing **does not automatically attach**, does not load an agent, and does not guarantee that a listed process can be attached to successfully.

## 1. Where the discovery step fits in the instrumentation workflow

Typical workflow:

~~~text
Tool application running on the JDK
              |
              v
VirtualMachine.list()
              |
              v
List<VirtualMachineDescriptor>
              |
              v
Inspect id / displayName / provider
              |
              v
Filter and verify the exact target JVM
              |
              v
[Decide to attach in a separate step, if permitted]
~~~

In this workflow:

- **Discover**: find the JVMs that the current attach providers *know about*.
- **Identify**: select the right JVM using identification information; avoid relying solely on the display name.
- **Attach**: a separate operation, performed later using `VirtualMachine.attach(...)`, which can fail even when the Discover phase succeeds.

The main classes reside in the **JDK module `jdk.attach`**:

| API | Role |
| --- | --- |
| `com.sun.tools.attach.VirtualMachine` | Class representing a connection to a JVM after attaching; also contains the static `list()` method |
| `com.sun.tools.attach.VirtualMachineDescriptor` | Identification information for a JVM discovered by a provider; not yet a connection |
| `com.sun.tools.attach.spi.AttachProvider` | Platform/JVM-vendor-dependent mechanism to list and potentially attach |
| `java.lang.ProcessHandle` | Java API for inspecting OS process information; **different** from the Attach API |

Use **JDK 17 or later with the `jdk.attach` module** to compile and run the example. A custom runtime created with `jlink` may not contain this module. If the application has a `module-info.java`, declare `requires jdk.attach;`; the example below is a program on the classpath, so it explicitly uses the `--add-modules jdk.attach` option.

## 2. What exactly does VirtualMachine.list() do?

Method signature:

~~~java
public static List<VirtualMachineDescriptor> list()
~~~

Calling `VirtualMachine.list()` aggregates the `VirtualMachineDescriptor` lists from `listVirtualMachines()` of **every installed attach provider**. If no provider knows of any JVM, the result is an **empty list**. This method does not require passing a PID, a name pattern, or an existing `VirtualMachineDescriptor`.

Key points to understand:

1. **It does not list all OS processes.** The list consists of JVMs that attach providers can detect; browser, database, or non-JVM native processes will not appear because of it.
2. **It is not a guaranteed complete list of every JVM on the machine.** Discoverability depends on the JDK/JVM implementation, provider, operating system, access permissions, containers, and process identification mechanisms.
3. **It is not a check that attach will succeed.** According to the `AttachProvider.listVirtualMachines()` contract, a listed descriptor is only a JVM that the provider **is potentially able** to attach to; there is no guarantee that the actual attach operation will succeed.
4. **The result reflects a point-in-time snapshot.** JVMs may start or stop right after the call. Obtained descriptors must not be treated as connections keeping processes alive.
5. **No default ordering is guaranteed.** If displaying to a user or comparing two scans, sort by a stable criterion yourself.
6. **There are no search arguments in `list()`.** To filter by name/id, filter the `List<VirtualMachineDescriptor>` on the application side.

To find out which providers are currently available:

~~~java
List<AttachProvider> providers = AttachProvider.providers();
~~~

When the number of providers is 0, `list()` has no listing source, so an empty result cannot be interpreted as "no JVM is running on this machine." When providers are present but the list is empty, you still need to check process visibility and runtime environment permissions.

## 3. What information does VirtualMachineDescriptor contain?

A `VirtualMachineDescriptor` is an object describing a **discovered JVM**, not an attached `VirtualMachine` object. Three commonly used methods:

| Method | Return type | Usage and limitations |
| --- | --- | --- |
| `id()` | `String` | Identifier supplied by the provider; **usually a PID as a string**, but may vary by implementation |
| `displayName()` | `String` | Human-readable string for displaying to users; **not guaranteed unique**, not necessarily a class name |
| `provider()` | `AttachProvider` | Provider associated with the descriptor; used to identify the mechanism that can attach to that JVM |

For a provider, `name()` gives the provider name and `type()` gives the mechanism type (for example, on a given platform this could be `sun/windows` or `sun/socket`). These strings depend on the JDK and environment; **do not hard-code** a provider name as a portable identification criterion.

### ID is not always a PID

On many systems, `descriptor.id()` is a numeric string corresponding to the JVM process's PID, such as `"7421"`. However, the Attach API defines it as an **implementation-dependent identifier**. Therefore:

- Keep the ID as a `String` when displaying, storing, or passing it to APIs.
- Do not assume calling `Long.parseLong(descriptor.id())` will work; some providers do not use numeric PIDs.
- Even when the ID is a PID, PIDs can be **reused** when an old process terminates, and the PID seen from a container may differ from the PID on the host.
- If multiple providers return the same ID string, you must consider **the provider as well** to distinguish them; a single ID is not necessarily a global key.

### displayName is not an identifying key

A `displayName()` may look like a main class name, a JAR name, or a startup command provided by the runtime, such as `com.example.OrderService` or `order-service.jar`. That is only display information, with no contract that it must contain a specific class/JAR name. If a provider has no separate display name, the value may **equal `id()`**.

Two JVMs running the same application can have the **same displayName**. Conversely, a specific JVM can be displayed differently depending on how it was launched and the JVM implementation. Therefore, filtering by name is useful to **narrow down the list**, but deciding to attach requires checking the ID, provider, and system context.

### provider() is not an attach action

`descriptor.provider()` returns the provider associated with the descriptor. This call only reads metadata; it does not open a connection. Similarly, `toString()` or `displayName()` does not tell you which version the JVM is running, which user owns it, or whether attach is allowed. Such information is not part of the `VirtualMachineDescriptor` contract.

## 4. Compilable and runnable Java 17+ example

Create the file **`JvmDiscovery.java`**:

~~~java
import com.sun.tools.attach.VirtualMachine;
import com.sun.tools.attach.VirtualMachineDescriptor;
import com.sun.tools.attach.spi.AttachProvider;

import java.util.Comparator;
import java.util.List;
import java.util.Locale;

public final class JvmDiscovery {
    private JvmDiscovery() {
    }

    public static void main(String[] args) {
        if (args.length > 1) {
            System.err.println(
                    "Usage: java --add-modules jdk.attach JvmDiscovery [name-fragment]");
            return;
        }

        String keyword = args.length == 1
                ? args[0].toLowerCase(Locale.ROOT)
                : "";

        List<VirtualMachineDescriptor> discovered =
                VirtualMachine.list();

        List<VirtualMachineDescriptor> matches = discovered.stream()
                .filter(vm -> vm.displayName()
                        .toLowerCase(Locale.ROOT)
                        .contains(keyword))
                .sorted(Comparator
                        .comparing((VirtualMachineDescriptor vm) ->
                                vm.provider().name())
                        .thenComparing(vm -> vm.provider().type())
                        .thenComparing(VirtualMachineDescriptor::id))
                .toList();

        System.out.printf("attachProviders=%d; discovered=%d; matches=%d%n",
                AttachProvider.providers().size(),
                discovered.size(),
                matches.size());

        for (VirtualMachineDescriptor vm : matches) {
            System.out.printf(
                    "id=%s | displayName=%s | provider=%s/%s%n",
                    vm.id(),
                    vm.displayName(),
                    vm.provider().name(),
                    vm.provider().type());
        }

        if (matches.isEmpty()) {
            System.out.println("(no matching JVM)");
        }
    }
}
~~~

From the directory containing the file, compile and run with JDK 17+:

~~~bash
javac --add-modules jdk.attach JvmDiscovery.java
java --add-modules jdk.attach JvmDiscovery
java --add-modules jdk.attach JvmDiscovery OrderService
~~~

**How to read the program:**

1. `VirtualMachine.list()` retrieves the list of visible JVMs from the providers.
2. If no argument is passed, `keyword` is empty, so `contains("")` allows every descriptor to be displayed. If `OrderService` is passed, the program only keeps descriptors whose `displayName()` contains this name fragment, case-insensitively using `Locale.ROOT`.
3. `stream().sorted(...)` sorts the results by provider name, provider type, and then ID for easier comparison. The program does not mutate the list returned by the API.
4. `matches` may contain 0, 1, or many entries. A 1-entry result is only **one candidate matching the filter**, not a definitive confirmation that it is the right application.
5. There are no calls to `VirtualMachine.attach(...)`, `loadAgent(...)`, or `detach()` because this program **only discovers**.

**Illustrative output format example (assuming a machine with 1 provider, 3 visible JVMs, and 1 name match):**

~~~text
attachProviders=1; discovered=3; matches=1
id=7421 | displayName=com.example.OrderService | provider=sun/socket
~~~

The actual number of processes, IDs, display names, provider names/types, and order of JVMs **depend on the machine and runtime**. This is not fixed stdout for verbatim comparison. If no entries match, the program prints the line `(no matching JVM)` after the count line; that alone is not enough to conclude the application is not running.

### Why doesn't the example automatically attach to the first element?

A filter by `displayName` can match two instances of the same application, or contain a similar name. Picking `matches.get(0)` and attaching risks targeting the wrong JVM. A real-world application should **list candidates along with their ID/provider**, prompt for selection or verify the target using more reliable criteria, and then re-check the state right before the attach action.

## 5. Example of analyzing a discovery result

Suppose there are three descriptors like this:

| id | displayName | provider |
| --- | --- | --- |
| `7421` | `com.example.OrderService` | `sun/socket` |
| `7550` | `com.example.OrderService` | `sun/socket` |
| `8992` | `com.example.BatchWorker` | `sun/socket` |

Filtering for `OrderService` yields **two** entries: `7421` and `7550`. The fact that two descriptors share a display name does not prove they are the same process; they could be two JVMs serving two instances or two environments. With multiple providers, the same ID also needs to be accompanied by the provider's name/type or the provider object itself to properly understand the context.

A cautious selection approach:

- Use `displayName` to **find candidates**, not as a unique key.
- Display `id` and `provider` to the operator.
- If the ID is a PID on the current platform, cross-check OS processes or deployment metadata using appropriate tools; do not assume every ID can be cross-checked that way.
- When there are multiple candidates, resolve the ambiguity before moving to the attach step.
- Re-scan immediately before an operation that affects the target, because an old process may have terminated or a PID may have been reused.

A descriptor obtained from a previous scan **does not keep the process alive**; this is the familiar issue of observing a changing system (*time-of-check vs. time-of-use*).

## 6. How do list() and attach() differ?

| Criterion | `VirtualMachine.list()` | `VirtualMachine.attach(descriptor)` |
| --- | --- | --- |
| Input | No parameters | A selected descriptor |
| Result | `List<VirtualMachineDescriptor>` | `VirtualMachine` representing the attached connection |
| Purpose | Discover JVMs and read identification info | Connect to the target JVM |
| Load agent | No | Does not automatically load just by attaching; requires a separate operation |
| Permission/attachability errors | May affect visibility | May cause attach to fail directly |
| Guarantee from previous step | Does not guarantee attachability | Depends on actual state and provider |

There are two overloads: `VirtualMachine.attach(String id)` and `VirtualMachine.attach(VirtualMachineDescriptor descriptor)`. In the next step of a tool using the discovered list, the overload taking a descriptor delegates the operation to **the provider associated with the descriptor**, whereas the overload taking a string ID tries matching providers one by one. This lesson does not perform an attach to avoid affecting running applications.

Errors such as `AttachNotSupportedException` or `IOException` are issues of the **attach step**; having a descriptor in `list()` does not guarantee those errors will not occur. If a different program has attached successfully, a `detach()` procedure is needed when finished, but there is nothing to detach after only calling `list()`.

## 7. Why might the list be empty or missing a JVM?

Several situations need to be distinguished:

| Observation | Reasonable interpretation | Verification action |
| --- | --- | --- |
| `attachProviders=0`, `discovered=0` | No provider to list; **cannot conclude there is no JVM** | Check the JDK/runtime and the `jdk.attach` module |
| `attachProviders>0`, `discovered=0` | Providers exist, but no JVM is seen | Check running processes, permissions, and visibility mechanisms |
| `discovered>0`, `matches=0` | Visible JVMs exist, but **none match the displayName keyword** | Run without a keyword, check the actual names |
| Descriptor exists, attach fails later | Discovery and attach permissions/mechanics are two separate steps | Check permissions, compatible provider, JVM state, attach configuration |
| Same name appears multiple times | Multiple candidates exist; display names are not unique | Compare ID/provider and verify each process |
| Results change across consecutive runs | Processes are starting/stopping during the scan window | Re-scan and record the timestamp |

**Environmental causes that can affect discoverability:**

- **Different JDKs/JVMs:** providers are implemented per vendor, version, OS, or attach mechanism. A single provider is not required to see every kind of JVM.
- **OS permissions:** the application is running under a different user or has restricted access to process/IPC information; exact behavior depends on the platform.
- **Containers, PID namespaces, filesystem namespaces:** a JVM visible from the host may not appear with the same ID or may not be visible from a tool running inside a container.
- **Target attach mechanism:** some JVMs may be configured to disable attach or may not support the current provider. **Do not infer in reverse** that a JVM is absent from `list()` simply because its attach is disabled; discovery and attach may use different checking mechanisms.
- **Process lifecycle:** JVMs stop or start between calls; PIDs may change or be reused.
- **Display name:** the JVM is visible, but `displayName()` does not contain the class/JAR name you expected, causing the filter to miss it.

Do not use a single `discovered=0` as an absolute signal to a monitoring system that "no Java services are running anymore." Combine it with evidence from the runtime, OS tools, or appropriate application monitoring channels.

## 8. Comparison with jps, jcmd, and ProcessHandle

In addition to the Java API example above, the JDK commonly provides command-line tools to aid observation:

~~~bash
jps -l
jcmd -l
~~~

- `jps -l` displays instrumented JVMs detected by the tool, usually along with the main class/JAR in `jps`'s presentation format.
- `jcmd -l` lists JVMs for diagnostic operations on supported platforms/JDKs.
- `ProcessHandle.allProcesses()` is an OS-process-level API that can list non-Java processes as well and is bound by OS access permissions.
- `VirtualMachine.list()` returns **descriptors with their attach providers** as Java objects so a tool can continue a workflow based on the Attach API.

These tools/APIs **have no contract to return the exact same set of processes**. If results differ, first check permissions, JVM implementation, namespaces, JDK environment, and listing mechanisms. Do not assume equivalent line counts across all operating systems.

## 9. Common mistakes when writing a JVM discovery tool

1. **Equating ID with a numeric PID:** code that calls `Long.parseLong(vm.id())` is not portable. With the Attach API, IDs must be treated as strings managed by the provider.
2. **Comparing only `displayName()`:** two instances can have the same name. This is display data, not a unique identifier.
3. **Picking `findFirst()` on `list()` results:** ordering is not guaranteed, and the list can change between scans.
4. **Treating `list()` as an attach action:** it does not call `loadAgent`, does not create an actionable connection, and does not require `detach`.
5. **Assuming having a descriptor guarantees attachability:** the target may exit, be incompatible, or disallow connections.
6. **Hiding provider information completely:** when multiple providers coexist, lacking the provider makes target selection and error handling hard to explain.
7. **Hard-coding `sun/socket`, a PID, or a main class name:** these values are not stable across machines, vendors, and launch configurations.
8. **Reading `discovered=0` as no JVMs:** you need to distinguish 0 providers, lack of visibility permissions, no targets, and environment differences.
9. **Logging `displayName` unchecked:** display names may reflect part of the startup information, so be careful when placing them verbatim into logs/public dashboards.
10. **Scanning once and reusing forever:** the result is a snapshot at listing time; re-verify when you need to act on a JVM.

For a periodic tool program, log **the provider count**, **the discovered descriptor count**, **the filter-matched count**, and the scan timestamp. These numbers help distinguish visibility issues from filter issues, though they still do not replace attach checks or application health checks.

## 10. Practice exercises

**Exercise 1.** Two JVMs both have `displayName()` equal to `com.acme.App`, but their `id()` values are `101` and `102`. How many elements does the filter `displayName().contains("App")` return? Should you automatically attach to the first element?

**Exercise 2.** `VirtualMachine.list()` returns an empty list; `AttachProvider.providers()` is also empty. Can you conclude that no Java application is running? Why?

**Exercise 3.** A descriptor has `id() = "svc-A"`. Which code snippet risks failing and why: `System.out.println(vm.id())` or `Long.parseLong(vm.id())`?

**Exercise 4.** `VirtualMachine.list()` returns a descriptor, but another tool calls `VirtualMachine.attach(descriptor)` and receives `AttachNotSupportedException`. Do the two results contradict the API contract?

**Exercise 5.** Distinguish the use of `VirtualMachineDescriptor`, `VirtualMachine`, and `ProcessHandle` when building a selection list for a JVM process.

### Answers and explanations

1. There are **2** elements. Do not pick `findFirst()` just because the name matches; verify the ID/provider and the right instance.
2. **No**. When there are no attach providers, the API has no listing source; an empty list does not prove there are no JVMs on the machine.
3. `Long.parseLong("svc-A")` throws `NumberFormatException`. `id()` is an implementation-dependent string, not necessarily a numeric PID.
4. **No contradiction**. Listing means the provider knows about the target; attaching successfully is a separate condition that can fail.
5. `VirtualMachineDescriptor` is used to identify **candidates**, `VirtualMachine` represents **the connection after attaching**, and `ProcessHandle` provides information at the **OS process** level and does not replace attach provider information.

## 11. Official references

- [Java 21: `VirtualMachine.list()` and `attach(...)`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html) — contract for listing and attaching.
- [Java 21: `VirtualMachineDescriptor`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachineDescriptor.html) — meaning of `id()`, `displayName()`, and `provider()`.
- [Java 21: `AttachProvider`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/com/sun/tools/attach/spi/AttachProvider.html) — listing source and lack of guarantee that attach will succeed.
- [Java 17: package `com.sun.tools.attach`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/package-summary.html) — Attach API in the `jdk.attach` module.
