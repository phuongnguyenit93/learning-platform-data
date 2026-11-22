# Class Loader Diagnostics with jcmd: VM.classloaders, VM.classloader_stats, and VM.class_hierarchy

In a long-running JVM — especially applications with plugins, application servers, Spring Boot, build tools, hot reload, or custom `URLClassLoader` instances — the questions “why is a class not found?”, “which class is loaded by which loader?”, and “why does metaspace grow after each redeploy?” should not be answered by guessing about the classpath.

**`jcmd`** is a tool bundled with the JDK (especially in HotSpot/OpenJDK) to send *diagnostic commands* to **a running JVM process**. Three class-loading-related commands are often used together, yet provide **three different perspectives**:

1. **`VM.classloaders`:** prints the **class loader relationship tree (parent hierarchy)**; optionally, it can list the classes belonging to each loader.
2. **`VM.classloader_stats`:** prints **per-class-loader statistics**: class count, `ClassLoaderData` information, and the sizes of metadata/metaspace chunks/blocks.
3. **`VM.class_hierarchy`:** prints the **class inheritance tree** (superclass/subclass), with the `ClassLoaderData*` identifier of the associated loader; it is **not** the class loader parent tree.

This article belongs to the **Diagnostics** category in Java core – classloader. The content focuses on Java 17+ syntax, a runnable example to create a named class loader, how to read the output, how to combine the three commands to diagnose class-loading errors and class loader leaks, snapshot limitations, and safety notes when attaching to a production JVM.

## 1. Choosing the Right Command for the Question

| What you want to know | Appropriate command | What do you see? | Cannot be concluded directly |
| --- | --- | --- | --- |
| Which **loaders** currently exist in the JVM, and who is the parent? | `VM.classloaders` | Bootstrap/platform/app and custom loaders in the tree | Which object keeps the loader alive, whether binaries are compatible |
| **Which classes** has Loader A loaded? | `VM.classloaders show-classes=true` | Class names displayed under the loader in the tree | Which JAR a class came from in all cases, heap object size |
| How many loaders/classes exist, and how is metadata allocated? | `VM.classloader_stats` | `Classes`, `ChunkSz`, `BlockSz`, `CLD*` per loader | Strong retaining paths and definite unload timing |
| Which class does `plugin.Child` inherit from? | `VM.class_hierarchy plugin.Child` | Superclass chain and loader-data identity | Loader parent chain |
| Which loaded subclasses does `plugin.Base` have? | `VM.class_hierarchy -s plugin.Base` | Superclasses and subclasses of the specified class | Any unloaded classes on the classpath |
| Why is the old loader not reclaimed by GC? | Statistics + heap dump/retaining paths + TCCL | Leak symptoms and reference-retaining paths | A single `jcmd` snapshot alone is not enough to conclude |
| Which class actually came from which JAR/CodeSource? | Class-loading log, `ProtectionDomain`/CodeSource, `javap` | Class source by loader/bytecode | Do not rely solely on the three statistics commands above |

**Key takeaway:** Both `VM.classloaders` and `VM.class_hierarchy` contain the word “hierarchy” in their description, but **their hierarchies are two different types of relationships**.

## 2. Prerequisites for Using jcmd

A typical session:

```bash
jcmd -l
jcmd <PID> help
jcmd <PID> help VM.classloaders
jcmd <PID> help VM.classloader_stats
jcmd <PID> help VM.class_hierarchy
```

In the commands above, **replace `<PID>` with the actual PID number**, for example `14920`; do not type the angle brackets literally into PowerShell/CMD/Bash because the shell may interpret them as redirection.

### Choosing the Appropriate PID and JDK

- `jcmd -l` lists the Java processes visible to the discovery mechanism; the list depends on access permissions and namespaces/containers.
- If you know the service's PID from a process manager, task manager, `ps`, or `ProcessHandle.current().pid()`, use `jcmd PID ...` directly.
- Prefer `jcmd` from the **same JDK version/vendor** as the target JVM, with an environment that supports the corresponding Attach API/diagnostic commands.
- The process must be a running JVM that supports attach; it usually requires the same user/appropriate OS permissions. In Docker/Kubernetes, you also need to consider the PID namespace, container filesystem, and security policy.
- A JVM may be started with a configuration that **disables attach**, for example `-XX:+DisableAttachMechanism` on HotSpot; in that case, `jcmd` will not work in the usual way.
- Do not assume that every Java SE JVM supports these exact three commands. These are **diagnostic commands of HotSpot/OpenJDK and certain compatible runtimes**; always query the target with `help`.

### Standard Syntax

```text
jcmd <PID> <diagnostic_command> [options] [arguments]
```

Examples:

```bash
jcmd 14920 VM.classloaders
jcmd 14920 VM.classloader_stats
jcmd 14920 VM.class_hierarchy plugin.Greeter
```

`14920` is only an illustrative PID. The commands in this article **only read/print information**; however, diagnostic attach still incurs JVM runtime overhead. `VM.classloader_stats` is documented as having *Low impact*; the two tree-printing commands typically have *Medium impact* depending on the number of loaders/classes. On large production JVMs, avoid calling them excessively or listing all classes unnecessarily.

## 3. Checking Availability and Options for Each Command

Run:

```bash
jcmd <PID> help VM.classloaders
```

On a tested HotSpot JVM, help reports:

```text
VM.classloaders
Prints classloader hierarchy.

Options:
  show-classes : Print loaded classes. (BOOLEAN, false)
  verbose      : Print detailed information. (BOOLEAN, false)
  fold         : Show loaders of the same name and class as one.
                 (BOOLEAN, true)
```

The snippet above **omits the header/impact section and shortens the description**, rather than being a verbatim copy of the full terminal output. Options use the `key` or `key=value` format:

```bash
jcmd <PID> VM.classloaders
jcmd <PID> VM.classloaders show-classes=true
jcmd <PID> VM.classloaders verbose=true
jcmd <PID> VM.classloaders fold=false
jcmd <PID> VM.classloaders show-classes=true fold=false
```

In particular, **by default `fold=true` can merge loaders with the same name and class** in the output. When investigating **multiple URLClassLoader instances with the same name**, use `fold=false` to avoid accidentally reading the merged display as “only one loader”.

For statistics:

```bash
jcmd <PID> help VM.classloader_stats
```

Help confirms:

```text
VM.classloader_stats
Print statistics about all ClassLoaders.
Impact: Low
Syntax: VM.classloader_stats
```

This command **does not have `show-classes` or `fold`** in the syntax of the tested JVM version; do not pass `VM.classloaders` options to statistics.

For class hierarchy:

```bash
jcmd <PID> help VM.class_hierarchy
```

Help indicates:

```text
VM.class_hierarchy [options] [<classname>]
  -i : Include inherited interfaces (BOOLEAN, false)
  -s : Show subclasses as well as superclasses when class
       name is supplied (BOOLEAN, false)
  classname : Fully qualified class name (optional)
```

This snippet is also a **summary of help**, preserving the exact meaning of the flags. Usage:

```bash
jcmd <PID> VM.class_hierarchy
jcmd <PID> VM.class_hierarchy plugin.Greeter
jcmd <PID> VM.class_hierarchy -s plugin.Greeter
jcmd <PID> VM.class_hierarchy -i plugin.Greeter
```

If no class name is specified, the command may print the **entire hierarchy of loaded classes**, producing a very large number of lines. Use a class name when possible.

**Note on placement:** `-s` and `-i` are **options of `VM.class_hierarchy`**, not flags of the `jcmd` executable placed before the PID.

## 4. VM.classloaders — Loader Parent Hierarchy Tree

Command:

```bash
jcmd <PID> VM.classloaders
```

A JVM with a custom loader programmatically named `plugin-demo` might display:

```text
+-- <bootstrap>
      |
      +-- "platform", jdk.internal.loader.ClassLoaders$PlatformClassLoader
            |
            +-- "app", jdk.internal.loader.ClassLoaders$AppClassLoader
            |
            +-- "plugin-demo", java.net.URLClassLoader
```

This is an **experimental output excerpt with simplified whitespace**, and the exact format is not guaranteed to be identical across all JDKs/OSes.

Reading the diagram:

- **Bootstrap loader** is at the root; in the `Class.getClassLoader()` API, the bootstrap loader can be represented as `null`.
- **Platform loader** loads platform classes according to the module/runtime configuration.
- **Application loader** is typically responsible for the application classpath.
- **Plugin loader** is a separate `URLClassLoader` instance, which can choose either the platform or application loader as its parent.
- **The tree represents the parent relationship of loaders**, not Java classes extending (`extends`) one another. For example, `URLClassLoader` *extends* `SecureClassLoader` in the class inheritance hierarchy, but the `VM.classloaders` tree does not draw `SecureClassLoader` as a delegation parent merely because of the `extends` relationship.

In the example in this article, the plugin loader is created with **parent = platform loader**, so `plugin-demo` sits on **the same branch under platform** alongside the app loader, **not as a child of app**. Do not assume “plugin created by app ⇒ app is the parent”. The delegation relationship is determined by the **constructor/configuration**.

### Three Special Options of VM.classloaders

**`show-classes=true`:** prints the class names associated with each loader. Useful when you suspect `PluginLoader` has reloaded an API version owned by the parent, or want to verify whether `plugin.Greeter` was actually defined by the plugin loader.

**`verbose=true`:** adds extra details of the loaders/output. You should inspect the output on the target JVM because the fields/display syntax vary across releases.

**`fold=false`:** does not merge loaders that share the same name and class. Very important for plugin reload leaks: multiple URLClassLoader instances with the same name can be folded when `fold=true`, making the hierarchy snapshot less clear about the number of instances.

Example:

```bash
jcmd <PID> VM.classloaders show-classes=true fold=false
```

**Cost:** printing all classes for thousands of loaders can generate massive output and take significant time. In production, start with the default output and only enable `show-classes=true` once you have a specific diagnostic target.

### What VM.classloaders Does Not Tell You

- Does not display **GC roots/retaining paths** leading to the loader.
- Does not prove a loader has leaked merely because it appears in a single snapshot.
- Does not report classes on the filesystem that *can be loaded* but **have not been loaded yet**.
- Does not replace `javap` for inspecting method/field descriptors.
- Does not replace `ModuleLayer`/the JPMS graph for determining exports/opens/readability.

## 5. VM.classloader_stats — Class Counts and Metadata Metrics

Command:

```bash
jcmd <PID> VM.classloader_stats
```

An abbreviated snapshot from a test JVM:

```text
ClassLoader   Parent       CLD*         Classes ChunkSz BlockSz Type
0x...         0x...        0x...             1    5120    1336  java.net.URLClassLoader
0x...         0x...        0x...             1    6144    3440  jdk.internal.loader.ClassLoaders$AppClassLoader
0x...         0x...        0x...           899 4456448  367896  <boot class loader>
...
Total = 4                                   907 4486144  383144
```

**This is an abbreviated output**; the addresses and numbers are only illustrative values from a test JVM. Do not treat these numbers as a benchmark for every Java 17 JVM; the number of classes/core modules varies depending on the JVM/build and running code.

Columns:

| Column | Practical meaning | Caveats |
| --- | --- | --- |
| `ClassLoader` | Address/identifier representing the loader in the VM snapshot; may be `0x0` for bootstrap | Not a Java identity hash code or PID |
| `Parent` | Parent pointer information of the classloader object | Pointer value, not the binary name of the parent class |
| `CLD*` | Internal pointer to HotSpot's **ClassLoaderData** structure | Only an internal runtime identifier; not a stable Java API |
| `Classes` | Number of classes belonging to the corresponding loader/loader-data entry in the statistics | Not the number of object instances created from those classes |
| `ChunkSz` | Total size of metaspace chunks allocated in the statistics group | Not heap memory, and not “live memory solely for classes” |
| `BlockSz` | Total size of metaspace blocks allocated within the chunks | Not the same as RSS or Java heap usage |
| `Type` | Class of the loader (or bootstrap/hidden classes notation) | Multiple instances can share the same `Type` while having different lifetimes |

There may be a **`+ hidden classes`** line attached to a loader/data entry's counters. Hidden classes are used by the JVM for certain implementations such as lambdas/invokedynamic; do not assume they are “classes hidden by a malicious application” or necessarily a leak.

### Notes on Sizes and Summation

`ChunkSz` and `BlockSz` in the observed HotSpot output are size numbers **in bytes** in the tested build; official `jcmd` help describes the statistics format, without guaranteeing that every JVM/version displays the exact same columns. Check the legend immediately below `Total` in the output of the runtime version you are using.

Do not infer:

- “`ChunkSz` = the plugin's live Java heap.”
- “`BlockSz` = the JAR file size on disk.”
- “`ChunkSz - BlockSz` = a guaranteed classloader leak.”
- “A loader having 100 classes means 100 object instances.”
- “After closing a loader, the loader's `Classes` count must drop to 0.”

A URL loader can be **closed** while its objects/classes are still strongly retained by the host, so `VM.classloader_stats` continues to display the loader along with its class count and metadata.

### When Are Statistics Especially Useful?

- Comparing the **number of custom loader instances** and **number of classes per loader** before/after multiple plugin reloads.
- Detecting trends: after each redeploy, another `java.net.URLClassLoader` appears with many classes, and old loaders do not disappear after appropriate GC.
- Confirming that the application accidentally creates hundreds of nearly identical loaders.
- Estimating per-loader metadata pressure (not a replacement for `VM.metaspace`/Native Memory Tracking when detailed metaspace metrics are needed).
- Correlating `CLD*` with class names from `VM.class_hierarchy` on the same target JVM at roughly the same point in time.

**A single snapshot is not enough to prove a leak.** The JVM may have just created a valid loader, GC may not have run yet, or the container may intentionally keep multiple versions running in parallel. You need to compare over time and find the path holding strong references.

## 6. VM.class_hierarchy — Inheritance Tree of Java Classes

Command:

```bash
jcmd <PID> VM.class_hierarchy plugin.Greeter
```

Example on a target that has loaded `plugin.Greeter`:

```text
java.lang.Object/null
|--plugin.Greeter/0x0000...
```

`plugin.Greeter` is a subclass of `java.lang.Object`. The `0x0000...` part is the **ClassLoaderData pointer** of the defining loader, which differs from the Java object identifier/loader name. `null` after `java.lang.Object` in the example means the class was defined by the bootstrap loader.

### Do Not Misread It as a Classloader Tree

This tree is:

```text
java.lang.Object
   |
   +-- plugin.Greeter
```

not:

```text
Bootstrap loader
   |
   +-- Plugin URLClassLoader
```

The **extends/implements relationship between classes** and **parent delegation between loaders** are completely different.

A class `plugin.Greeter` may extend `plugin.Base`; those two classes can be defined by different loaders depending on the model. `VM.class_hierarchy` focuses on class inheritance and also prints the loader-data identity to help distinguish runtime definitions.

### Using -s and -i

```bash
jcmd <PID> VM.class_hierarchy plugin.Greeter
jcmd <PID> VM.class_hierarchy -s plugin.Greeter
jcmd <PID> VM.class_hierarchy -i plugin.Greeter
```

- Without `-s`: when filtering by class name, only superclasses are printed according to the VM's help.
- With `-s`: additionally shows loaded subclasses of the selected class.
- With `-i`: additionally prints applicable inherited interfaces according to the implementation.
- Without passing a name: may print the **entire loaded class hierarchy**, which is very large.

**This command cannot be used to view source code, bytecode, method implementations, or classes on the classpath that have not been loaded yet.** For a `NoSuchMethodError`, you need `javap` to compare binary descriptors; `VM.class_hierarchy` only helps identify the relevant hierarchy/loader-data.

### When the Same Binary Name Exists in Two Loaders

Two independent loaders can each define their own class named `plugin.Greeter`. To the JVM, these are **two different runtime types** (binary name + defining loader). `VM.class_hierarchy` can display them under the same textual name but with **different loader-data identities**; you should combine it with `VM.classloader_stats` or `VM.classloaders show-classes=true fold=false`.

Do not conclude solely from the textual name that they are the same `Class<?>`. You must identify the **defining loader**.

## 7. Java 17+ Example: Creating a Named URLClassLoader and Running All Three Commands

This is an example **compiled with `javac --release 17` and run** on a HotSpot JVM. It creates a `URLClassLoader` named `plugin-demo`, loads the plugin class itself, and keeps the program alive for a period so `jcmd` can attach. You can re-run it on any JDK 17+ with `jcmd`.

### 7.1 Structure

```text
jcmd-loader-demo/
├── src/
│   └── plugin/
│       └── Greeter.java
├── App.java
├── plugin/           (plugin .class output)
└── host/             (host .class output)
```

Create the output directories `plugin` and `host`. **Do not include `plugin` in the host's `-cp`**, so that the plugin class is actually defined by the separate URL loader.

### 7.2 Plugin Class

File `src/plugin/Greeter.java`:

```java
package plugin;

public class Greeter {
    public String say() {
        return "Hello from plugin";
    }
}
```

### 7.3 Host Creating the Named URLClassLoader

File `App.java`:

```java
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class App {
    public static void main(String[] args) throws Exception {
        URLClassLoader loader = new URLClassLoader(
                "plugin-demo",
                new java.net.URL[] {
                    Path.of("plugin").toUri().toURL()
                },
                ClassLoader.getPlatformClassLoader());

        Class<?> clazz = loader.loadClass("plugin.Greeter");
        Object object = clazz.getConstructor().newInstance();

        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("loader=" + clazz.getClassLoader().getName());
        System.out.println("msg=" + clazz.getMethod("say").invoke(object));

        Thread.sleep(30_000);
        loader.close();
    }
}
```

Explanation:

- The `URLClassLoader(String name, URL[] urls, ClassLoader parent)` constructor is available in Java 17 and allows setting a name for easier observation.
- The chosen parent is `ClassLoader.getPlatformClassLoader()`, so `plugin-demo` sits under platform in the delegation tree; it is not a child of the app loader.
- `clazz.getClassLoader().getName()` returns `plugin-demo` to confirm the expected loader.
- `ProcessHandle.current().pid()` prints the actual PID of the target process, avoiding guesswork.
- `Thread.sleep(30_000)` keeps the program alive for about **30 seconds**, just enough for manual commands in the example. This is only an illustrative keep-alive duration, not a long-term server diagnostic procedure.
- `loader.close()` after the sleep only closes the URL loader; it does not force class unloading. The class/object references still remain in the method at the time the example runs.

### 7.4 Compiling and Running

In the `jcmd-loader-demo` directory:

```bash
javac --release 17 -d plugin src/plugin/Greeter.java
javac --release 17 -d host App.java
java -cp host App
```

Observed stdout:

```text
PID=<actual PID of the process>
loader=plugin-demo
msg=Hello from plugin
```

**Do not use `<actual PID of the process>` literally as fixed stdout**: the first line is always the current OS/runtime PID; for example, on the test machine it was a specific number, but it will differ on the learner's machine.

To invoke `jcmd` while the target is still alive, **open a second terminal** while the first terminal is sleeping. For real long-running applications, you do not need to write `Thread.sleep`.

### 7.5 The Three Commands on the Target

In the second terminal:

```bash
jcmd -l
jcmd <PID> help VM.classloaders
jcmd <PID> VM.classloaders show-classes=false
jcmd <PID> VM.classloader_stats
jcmd <PID> VM.class_hierarchy -s plugin.Greeter
```

**Verified on the test JVM:**

- `VM.classloaders` contains `"plugin-demo", java.net.URLClassLoader` under the platform loader.
- `VM.classloader_stats` has a loader entry of type `java.net.URLClassLoader` with at least the plugin class counted, along with `CLD*`, `ChunkSz`, and `BlockSz`.
- `VM.class_hierarchy -s plugin.Greeter` prints `java.lang.Object/null` and `plugin.Greeter/<loader-data-pointer>`.

Because pointers, class counts, heap/metaspace allocations, and bootstrap class counts all depend on the JVM, these are **verified characteristics**, not guarantees of fixed specific numbers on every run.

### 7.6 The Three Commands Answer Three Different Questions

For the same plugin class:

- “Which parent loader does `plugin-demo` have?” → `VM.classloaders`.
- “How many classes has `plugin-demo` defined, and what do its metadata chunks look like?” → `VM.classloader_stats`.
- “Which class does `plugin.Greeter` extend, and which class loader data is associated with this definition?” → `VM.class_hierarchy`.

If you only use one of the three, you may conflate the loader **object**, loader **data**, class **hierarchy**, parent **delegation**, or metaspace **allocation**.

## 8. Correlating CLD* Between Statistics and Class Hierarchy

In the test run, the statistics contained a line similar to:

```text
... CLD*=0x0000020ffe529c10 ... Type=java.net.URLClassLoader
```

The class hierarchy tree had:

```text
|--plugin.Greeter/0x0000020ffe529c10
```

This is an **illustration from a snapshot of the test JVM**, showing that both outputs refer to the same `ClassLoaderData*`. Do not copy this pointer to another process or across JVM restarts: it is a VM-internal address/ID, not a persistent identifier.

A safe way to read them:

1. Use `VM.classloaders fold=false` to identify the custom loader by name and parent.
2. Use `VM.classloader_stats` to find the relevant loader types and `CLD*`; save snapshots over time.
3. Use `VM.class_hierarchy plugin.Greeter` to see the class actually loaded and its CLD pointer.
4. If the pointers match within the same JVM, you have additional evidence linking the loader-data and the class.
5. Do not infer the *CodeSource/JAR file path*, version, or GC retaining path from that pointer alone.

**A subtle point:** `ClassLoaderData` is an internal HotSpot structure, not part of the `java.lang.ClassLoader` or `java.lang.Module` public API. Its correlation is useful for debugging, but the output/addresses/format may differ in other releases.

## 9. Using jcmd Statistics to Narrow Down Suspected Retained Loaders

For plugin reloads, collect `VM.classloaders fold=false` and `VM.classloader_stats` **before and after each deployment generation** within the same JVM. Use `fold=false` to clearly see multiple loaders with the same name/class; read `Classes`, `CLD*`, `ChunkSz`, and `BlockSz` as loader metadata metrics, not object heap bytes.

If the old loader still appears after `close()`, there may still be legitimate in-flight work or strong references from TCCL, tasks, caches, listeners, or providers; the JVM is also not required to unload immediately. Compare trends across multiple cycles and appropriate GCs. To find **what is retaining the loader**, you need a heap dump/MAT Path to GC Roots or equivalent evidence, rather than inferring from a single jcmd snapshot. The JFR/heap dump article covers investigating root paths, distinguishing observation timing, and assessing lifecycle validity.
## 10. Why Does Closing a Loader Not Make It Disappear from Statistics?

`URLClassLoader.close()` only closes the classpath source/JAR handles per its contract. It **does not**:

- Shut down any threads/executors created by the plugin.
- Remove any callbacks/providers/caches held by the host.
- Destroy instances or remove already loaded `Class<?>` objects.
- Force GC to reclaim the loader.
- Force the JVM to unload class metadata.

A closed loader **can still appear** in `VM.classloaders`/`VM.classloader_stats` if it remains reachable or its loader data still exists. This is not evidence that closing failed.

A better plugin stop procedure:

```text
Reject new requests
       |
       v
Await/cancel in-flight plugin tasks
       |
       v
Call plugin.stop() and unregister callbacks/services
       |
       v
Restore TCCL / clear ThreadLocal / close plugin-owned resources
       |
       v
Call URLClassLoader.close()
       |
       v
Release host strong references to old instance/Class/loader
       |
       v
Loader may become eligible for GC
       |
       v
JVM may unload its classes (no guaranteed deadline)
```

**Diagnostic takeaway:** capturing statistics immediately after `close()` without checking tasks/strong references and concluding “classloader leak” is a premature conclusion. Class unloading is subject to reachability conditions and depends on GC decisions.

## 11. Distinguishing Loaded Classes from Observable Classes on the Search Path

`VM.classloaders show-classes=true` and `VM.class_hierarchy` focus on **classes already loaded by the JVM**. If a JAR contains thousands of `.class` files while the application only touches ten classes, the statistics will not automatically list all class files in the JAR.

Distinctions:

| Concept | Example |
| --- | --- |
| **File present on disk** | `plugin.jar!/plugin/Unused.class` exists |
| **Findable by loader** | `URLClassLoader` knows the URL pointing to the plugin JAR |
| **Class loaded/defined** | The JVM already has a runtime `Class<?>` for `plugin.Used` |
| **Class initialized** | The JVM has executed `<clinit>` according to initialization rules |
| **Class eligible for unloading** | The defining loader can be reclaimed by GC |
| **Class unloaded** | The JVM has actually performed unloading, observable via logs/events |

Do not use `VM.class_hierarchy` as a command to “list all loadable classes from the classpath”. Also, do not infer that a class absent from the snapshot means the file is missing: it may simply not have been loaded yet.

To investigate classpath/JAR contents, combine `jar --list`, classloading logs, runtime resource lookup, or `javap`.

## 12. When to Use -Xlog Instead of jcmd?

`jcmd` provides an **on-demand snapshot**, whereas unified JVM logging can record a **sequence of events over time**. With HotSpot:

```bash
java -Xlog:class+load=info,class+unload=info -cp host App
```

This command lets you observe class load and unload events occurring over time if the runtime supports it. Notes:

- `class+load`: class-loading events, not a list of all JAR files.
- `class+unload`: unloading events; only appear **when unloading actually occurs**.
- Not seeing unload logs **does not prove** that `URLClassLoader.close()` failed or that the VM has a leak.
- The runtime may retain the classloader strongly via a callback/TCCL, or GC/unloading may not have occurred yet.
- Detailed logging can generate large output; choose an appropriate log level and write to files according to production policies.

In a production environment, choose appropriately:

- Occasional `jcmd` snapshots to understand the current state.
- `-Xlog:class+load/class+unload` or JFR when a timeline is needed.
- Heap dump/retaining paths when you need to identify a leak.
- `VM.metaspace` or NMT when you need to dig deeper into native/metaspace allocations.

These complementary tools do not diminish the role of the three main commands; they answer **questions that tree/stats snapshots cannot answer**.

## 13. When jcmd Fails to Run or Reports an Attach Error

A few scenarios:

| Symptom | Possible cause | Diagnostic steps |
| --- | --- | --- |
| `jcmd -l` does not list the process | Different user/PID namespace/container, or process does not support discovery | Check the OS PID and run jcmd in the same namespace/with the same permissions |
| `Could not attach` or timeout | Attach mechanism disabled, insufficient permissions, busy/unresponsive JVM, temp filesystem restrictions | Check runtime flags, user, container, and logs |
| `Unknown diagnostic command` | JVM/version/vendor does not support the command name | `jcmd PID help` |
| Command runs but output is too large | `show-classes=true` selected or unfiltered hierarchy | Omit class listing, filter by a specific class |
| Plugin loader not visible | Plugin not loaded yet, already GC'd, folded, or parent defined the class instead | `fold=false`, run at the right time, check code/defining loader |
| `VM.classloader_stats` has multiple rows of the same type | Multiple **loader instances** sharing the same class/type | Compare CLD/loader IDs and lifecycles; do not count by unique type name |
| `VM.class_hierarchy plugin.Foo` does not find the class | Class not loaded yet, wrong binary name, different target JVM, or already unloaded | Verify `getName()`/loader and class-loading logs |
| Class hierarchy output contains `null` | Class defined by the bootstrap loader | Do not misinterpret `null` as a class without a superclass |
| Post-deploy snapshot shows increased `ChunkSz` | More classes/metaspace chunks loaded | Compare across multiple checkpoints and GCs; do not immediately conclude a leak |
| Loader still exists after `close()` | Remaining references or VM has not unloaded yet | Analyze TCCL/caches/tasks/retaining roots |

### Security and Operational Notes

`jcmd` is an administrative tool that interacts with processes. Do not grant attach permissions to untrusted users/automation. Some diagnostic commands can alter VM state or create heap dumps; **only run necessary commands and understand their impact**.

For the three commands in this article, run `help` first and read the output; do not run “`jcmd PID` without a command” or scripts scanning all processes in production without authorization. Also do not store logs containing classnames/plugin internals publicly.

## 14. Common Reasoning Pitfalls

| Premature conclusion | Correct understanding |
| --- | --- |
| “`VM.class_hierarchy` is the parent tree of loaders.” | False; it is the **class inheritance** tree. `VM.classloaders` is the parent loader hierarchy. |
| “`VM.classloader_stats` shows heap bytes per instance.” | False; it reports per-loader/class metadata statistics. |
| “High `ChunkSz` proves a memory leak.” | Insufficient. This is an allocation snapshot; trends and retaining paths are needed. |
| “A loader after calling `close()` must disappear from stats.” | False; closing does not force GC/unloading. |
| “Not seeing the loader in `VM.classloaders` means the corresponding class does not exist.” | The class may have been defined by parent/bootstrap, the loader has not been created yet, it was folded, or it was already GC'd. |
| “If a class is in the JAR, it must be in `VM.class_hierarchy`.” | No; only loaded/defined classes appear. |
| “`fold=true` gives me the exact count of every loader instance.” | It may merge loaders with the same name/class; use `fold=false` when counting instances. |
| “The CLD pointer is a permanent name/ID of the loader.” | No; the VM-internal address is not stable across JVM restarts. |
| “The same ClassLoader name means the same loader.” | No; multiple objects can share the same `getName()`. |
| “`jcmd` can automatically fix the classpath or recompile old classes.” | No; it is a diagnostic tool, not a build/deployment repair tool. |
| “jcmd can only be used for Java classpath, not JPMS.” | Incorrect; a target JVM using named modules still has loaders/classes to diagnose. |
| “Class hierarchy and classloader hierarchy are the same graph.” | False; inheritance and delegation are two different relationships. |

## 15. Self-Check Questions with Answers

**1.** Which command should you use to see whether a plugin loader is a child of the platform or application loader?

**Answer:** `jcmd PID VM.classloaders`; add `fold=false` when you need to distinguish instances with the same name/type.

**2.** Which command should you use to find out which loader is holding a lot of class metadata?

**Answer:** `jcmd PID VM.classloader_stats`. Read `Classes`, `ChunkSz`, `BlockSz`, and `Type`. These numbers are not heap object sizes.

**3.** `VM.class_hierarchy plugin.Greeter` prints `java.lang.Object` above the plugin class. What does that indicate?

**Answer:** `plugin.Greeter` inherits from `java.lang.Object` in the **class hierarchy**; it does not prove that the plugin loader's parent is the bootstrap loader.

**4.** What does `-s` on `VM.class_hierarchy` do?

**Answer:** When a classname is supplied, it requests printing **subclasses** in addition to superclasses.

**5.** What does `-i` mean?

**Answer:** Requests displaying inherited interfaces according to the command's capability.

**6.** Why is `VM.classloaders fold=false` useful when detecting leaks?

**Answer:** By default, fold can merge loaders with the same name/class in the display. When counting multiple loader instances after redeploy, you need to separate them.

**7.** Why does the `VM.classloader_stats` output still show `plugin-demo` after close?

**Answer:** Closing only closes the URL/JAR handles of the URLClassLoader; the loader/class metadata can remain alive via references and the VM has not unloaded it yet.

**8.** What is `CLD*`?

**Answer:** An internal pointer/identifier of HotSpot `ClassLoaderData`; it can correlate commands on the same target JVM, but it is not a durable public Java object ID.

**9.** A class exists in the plugin JAR but does not appear in `VM.class_hierarchy`. Why might that be?

**Answer:** The class has not been loaded yet, rather than the file being missing from the JVM; the command output focuses on loaded classes.

**10.** Does `VM.classloader_stats` showing increasing `Classes` over three deploys guarantee a leak?

**Answer:** Not yet. You need to know whether the application is legitimately running multiple versions, whether GC/unloading has occurred, and whether any strong retaining paths hold the old loaders.

**11.** To find out exactly **what keeps the old loader alive**, are the three commands above enough?

**Answer:** No; you need heap dump/retaining path analysis and to inspect TCCL/ThreadLocal/callbacks/registries.

**12.** When the JVM reports “unknown command”, what is the first step?

**Answer:** `jcmd PID help` and `jcmd PID help VM.classloaders` to check whether the target runtime supports the command/flags.

**13.** Why shouldn't you directly compare `0x...` addresses across two JVM restarts?

**Answer:** They are pointers/VM-internal identities, not stable IDs across processes/restarts.

**14.** Which commands help inspect which class came from which JAR?

**Answer:** Class-loading logs (e.g., `-Xlog:class+load=info`), the CodeSource of `Class<?>` when available, together with `jar --list`/`javap`. `VM.classloader_stats` is not a file-origin resolver.

## 16. Practical Action Checklist

1. Confirm the target's **JDK/HotSpot** and attach capability; use the appropriate `jcmd`.
2. Use `jcmd -l` or retrieve the PID using OS tools; verify the correct target process.
3. Run `jcmd PID help` and `help VM.classloaders/VM.classloader_stats/VM.class_hierarchy`.
4. Capture `VM.classloaders` to inspect the parent tree, without confusing it with class inheritance.
5. Enable `fold=false` if you suspect multiple loader instances with the same name/type.
6. Enable `show-classes=true` only when needed, keeping in mind the high output overhead.
7. Capture `VM.classloader_stats` to inspect `CLD*`, class counts, and metadata allocations.
8. Use `VM.class_hierarchy ClassName` or `-s`/`-i` depending on your inheritance/interface question.
9. Correlate `CLD*` between stats and hierarchy within the same process/snapshot; do not save it as a permanent ID.
10. Compare snapshots **before/after** plugin load/reload/stop and after appropriate GC.
11. Do not treat `URLClassLoader.close()` as a class-unloading command.
12. When a leak is suspected, find root references with a heap dump and check TCCL, ThreadLocal, registries, and active tasks.
13. Use class-loading/unloading logs or JFR if a timeline is needed, and `VM.metaspace` if deep memory analysis is required.
14. Check CodeSource/JAR when suspecting duplicate classes/versions instead of inferring from class names or loader types.
15. Keep attach permissions, runtime impact, and diagnostic data within permitted security/operational boundaries.

## Conclusion

**`VM.classloaders` shows which loader is the parent of which loader; `VM.classloader_stats` shows class counts and metadata statistics per loader; `VM.class_hierarchy` shows the inheritance tree of loaded classes, along with loader-data identity.** They complement one another in diagnosing classloading issues and plugin leaks, yet do not replace each other and cannot substitute for heap retaining paths.

When investigating a JVM with multiple plugins, start with **PID → `VM.classloaders fold=false` → `VM.classloader_stats` → `VM.class_hierarchy ClassName`**, and then use class-loading logs or a heap dump if the question is **which class/JAR was actually loaded** or **which GC root is retaining the old loader**. Do not conclude a “leak” from a single snapshot alone or from the fact that the loader still appears immediately after `close()`.

**Official documentation:**

- [Oracle Java SE 17 — `jcmd` man page](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `VM.classloaders`, `VM.classloader_stats`, `VM.class_hierarchy`, options, and impact.
- [Oracle Java SE 17 — Troubleshooting Guide](https://docs.oracle.com/en/java/javase/17/troubleshoot/): workflows for using tools/JVM diagnostics.
- [`ClassLoader` API — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, named loader.
- [`URLClassLoader` API — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): constructors, `close()`, and limitations.
- [JLS 17 `12.7 — Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7): ability of GC to reclaim the defining loader and class unloading.
