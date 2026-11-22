# getAllLoadedClasses Returns a Snapshot of Classes Loaded by the JVM

**Topic:** Java Advance → instrumentation → **Runtime Inspection**.

`Instrumentation.getAllLoadedClasses()` is the API for a Java agent to **observe which classes are currently loaded by the JVM**. A single call returns **a `Class<?>[]` array**, where each element represents a runtime type existing at the moment of inspection. This array helps answer “Which classes does the JVM currently know about?”, such as when diagnosing plugins, class loaders, metaspace memory, or selecting candidates for retransformation.

Important contract: this is a **snapshot list**, not a continuous event stream, not a list of all classes discoverable in JARs/classpath, not a list of `new` objects created, nor does it mean those classes have all been **initialized**. The API returns **`Class<?>` objects**, not class file bytes.

In JDK 17+, the Javadoc explicitly states that the array includes **classes, interfaces, hidden classes/interfaces, and array classes**. The way to get “classes that a loader can find by name” is `getInitiatedClasses(loader)`, which has different criteria.

> **Example environment:** JDK 17 or later with `javac`, `jar`, and `java`. This lesson uses a Java agent started via `-javaagent` to receive `Instrumentation`, without needing to attach to another process, register a transformer, or modify bytecode itself.

## 1. Which API does `getAllLoadedClasses()` belong to?

Signature in `java.lang.instrument.Instrumentation`:

```java
Class[] getAllLoadedClasses();
```

In modern Java code, the result should be held in a variable with a generic wildcard to avoid raw type operations:

```java
Class<?>[] snapshot = instrumentation.getAllLoadedClasses();
```

The two lines above are an **API fragment**, not a standalone program: `instrumentation` needs to be passed by the JVM to the agent via `premain` or `agentmain`. You cannot create a valid `Instrumentation` yourself using `new Instrumentation()`; it is an interface provided by the JVM.

Return value:

- **A new array for each inspection** containing the `Class` objects currently in the set of loaded classes reported by the JVM at the time of the call.
- **Loaded classes and interfaces**, including hidden types and array types per the JDK 17 Javadoc.
- **A zero-length array** by contract if no classes are reported (on a real Java JVM running a program, this almost never happens).
- **No ordering contract** for applications to rely on: do not interpret `snapshot[0]` as “the first loaded class”, and do not expect two calls to be sorted the same way.

A `Class<?>` element can provide:

| Question | API read from `Class<?>` |
| --- | --- |
| Runtime type name | `clazz.getName()` |
| Defining class loader | `clazz.getClassLoader()`; `null` usually indicates bootstrap |
| Module | `clazz.getModule()` |
| Is it an interface? | `clazz.isInterface()` |
| Is it an array type? | `clazz.isArray()` |
| Component type if it is an array | `clazz.getComponentType()` |
| Is it a hidden class? | `clazz.isHidden()` (JDK 15+) |
| Is it an enum/record/annotation? | `isEnum()` / `isRecord()` / `isAnnotation()` |
| Can it be used for redefinition/retransformation? | **Do not infer from class membership**; ask `instrumentation.isModifiableClass(clazz)` separately |

**Note:** `clazz.getName()` can be identical between two different `Class<?>` objects due to two different defining loaders; the unique key at runtime is **the `Class<?>` object/identity itself and the loader**, not just the name string.

## 2. “Loaded” does not mean “initialized”

A class has JVM-related phases: **loading → linking (verification/preparation/resolution) → initialization**. The JVM may have loaded a class without having run its `static` blocks or initialized static fields according to application logic.

Example (illustrative fragment only):

```java
Class<?> clazz = Class.forName(
        "demo.LoadedLater",
        false,
        ClassLoader.getSystemClassLoader());
```

- The second parameter `false` requests **not to initialize** the class at this statement if it has not been initialized yet.
- The class can still be **loaded** and appear in `getAllLoadedClasses()`.
- When using `Class.forName(name, true, loader)`, the JVM will initialize the class if it has not been initialized yet.
- Do not confuse seeing `Class<?>` in the snapshot with `static { ... }` having run.

A snapshot scan **is not** a mechanism to ask “has this class been initialized yet?” via the standard `Class<?>` API. Using a lab with a static initializer that prints a marker will make the difference clear.

### 2.1. Not every class is loaded just because a `.class` file exists

Suppose a JAR contains classes `A`, `B`, and `C`. If the JVM has not actually loaded `C`, the `C.class` file may still sit on the classpath yet **not appear in the snapshot**. Conversely, a dynamically generated class, hidden class, or array type may be present without a corresponding standalone `.class` file on disk in the way build tools usually store them.

The snapshot reflects **runtime state**, not the contents of a directory, JAR, or module path.

## 3. A “snapshot” has time and scope limits

```text
T0: JVM has loaded A, B
       │
       ▼
S1 = getAllLoadedClasses()   -> contains A, B, ... other classes
       │
T1: program loads C
       │
       ▼
S2 = getAllLoadedClasses()   -> contains A, B, C, ... at the new point in time
       │
T2: D's loader may be GC'd/unloaded (if eligible)
       │
       ▼
S3 = getAllLoadedClasses()   -> the result set may continue to change
```

S1 **does not automatically update** when C is loaded. To know the new state, you must call the API again. Two calls can differ in:

- **Number of classes:** agents, JIT/runtime support, reflection, serialization, frameworks, and the inspection code itself can trigger loading additional types.
- **Membership:** new classes are loaded; some old loaders/types can unload when no longer reachable.
- **Order:** never use array position as identity or a class loading timeline.
- **Loader/module distribution:** the application can create or tear down plugin loaders.

There is no guarantee that **two snapshots form a fixed transaction of the entire application** when multiple threads are loading/unloading concurrently. A diff is observational evidence **at two points in time**; you cannot deduce the complete order of every event that occurred in between.

**Important for memory:** If an agent holds `Class<?>[]` for a long time in a static field/cache, the `Class<?>` references can keep classes/defining loaders from being reclaimed as expected. Therefore, an “inspector” can also **cause class-loader retention** if it stores full snapshots forever. Keep only appropriate metrics/summaries or short-lived snapshots; release references after analysis.

## 4. Runnable Java 17+ Project: Observing a Class Before/After Loading

We will build a **read-only Java agent**. When the application runs, it:

1. Takes a snapshot of loaded classes before the application intentionally loads `demo.LoadedLater`.
2. Calls `Class.forName(..., false, ...)` to **load without initializing**.
3. Takes another snapshot and checks that the class has appeared.
4. Calls `Class.forName(..., true, ...)` to trigger the static initializer.
5. Confirms that class identity does not change due to initialization.

### 4.1. Directory Structure

```text
loaded-classes-lab/
├── agent.mf
├── src/
│   └── demo/
│       ├── CensusAgent.java
│       ├── LoadedLater.java
│       ├── SnapshotMain.java
│       └── LoaderIdentityMain.java
└── plugin-src/
    └── plug/
        └── SideBySide.java
```

Compiling will create `out/` and `plugin-out/`. No third-party libraries are needed, and you do not need to create a separate workspace/repository for understanding this lesson: this is a description of the files you can create on your learning machine.

### 4.2. Agent — `src/demo/CensusAgent.java`

```java
package demo;

import java.lang.instrument.Instrumentation;

public final class CensusAgent {
    private static volatile Instrumentation instrumentation;

    private CensusAgent() {}

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
    }

    public static Class<?>[] snapshot() {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException(
                    "Run with -javaagent:census-agent.jar");
        }
        return inst.getAllLoadedClasses();
    }

    public static Class<?>[] initiatedBy(ClassLoader loader) {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Agent not initialized");
        }
        return inst.getInitiatedClasses(loader);
    }
}
```

`premain` runs **before the application's `main`** when started with `-javaagent`. The `Instrumentation` variable is stored in a `static volatile` field so application code can read it after the JVM has called `premain`. In a sequential lab, `volatile` is not essential for the printed result, but it is good practice for safely publishing a reference when multiple threads may access it.

Here we **do not call `addTransformer`, `redefineClasses`, or `retransformClasses`**: the goal is observation only. `getAllLoadedClasses` itself does not attach hooks to methods and does not alter class definitions.

### 4.3. Late-Loaded Class — `src/demo/LoadedLater.java`

```java
package demo;

public final class LoadedLater {
    static {
        System.out.println("INIT=LoadedLater");
    }

    private LoadedLater() {}

    public static String message() {
        return "ready";
    }
}
```

The line `INIT=LoadedLater` only prints when **the class initializer is executed**. Merely referencing the class name with the **string literal** `"demo.LoadedLater"` does not mean the JVM is forced to load that class from the start.

### 4.4. Main Program — `src/demo/SnapshotMain.java`

```java
package demo;

import java.util.Arrays;

public final class SnapshotMain {
    private SnapshotMain() {}

    private static boolean contains(
            Class<?>[] snapshot, String name, ClassLoader loader) {
        for (Class<?> type : snapshot) {
            if (type.getName().equals(name)
                    && type.getClassLoader() == loader) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args) throws Exception {
        ClassLoader applicationLoader =
                SnapshotMain.class.getClassLoader();
        String className = "demo.LoadedLater";

        Class<?>[] before = CensusAgent.snapshot();
        System.out.println("BEFORE_PRESENT="
                + contains(before, className, applicationLoader));

        Class<?> loaded = Class.forName(
                className, false, applicationLoader);

        Class<?>[] afterLoad = CensusAgent.snapshot();
        System.out.println("AFTER_PRESENT="
                + contains(afterLoad, className, applicationLoader));
        System.out.println("FOUND_SAME_CLASS="
                + Arrays.asList(afterLoad).contains(loaded));

        Class<?> initialized = Class.forName(
                className, true, applicationLoader);
        System.out.println("SAME_AFTER_INIT="
                + (loaded == initialized));
    }
}
```

**Why filter by both name and loader?** In case loader A and loader B both define `demo.LoadedLater`, calling only `getName().equals(...)` could pick the wrong class. In this lab the loader is the application loader, so we filter by `getClassLoader() == applicationLoader` to identify the exact runtime class.

`Arrays.asList(afterLoad).contains(loaded)` compares by `Class.equals` (by `Class` identity) to prove the returned element is the exact `Class<?>` object returned by `Class.forName`. It does not rely on array position.

### 4.5. Agent Manifest — `agent.mf`

Create a plain-text manifest file with a **trailing newline**:

```text
Manifest-Version: 1.0
Premain-Class: demo.CensusAgent
```

Because the agent only takes a snapshot list, the manifest attributes `Can-Retransform-Classes` or `Can-Redefine-Classes` are **not needed**. Those capabilities serve bytecode modification, not a prerequisite for `getAllLoadedClasses()`.

### 4.6. Compile and Run

From the `loaded-classes-lab` directory. On Linux/macOS, create the output directory:

```bash
mkdir -p out
javac --release 17 -d out src/demo/CensusAgent.java src/demo/LoadedLater.java src/demo/SnapshotMain.java
jar --create --file census-agent.jar --manifest agent.mf -C out demo/CensusAgent.class
java -javaagent:census-agent.jar -cp out demo.SnapshotMain
```

On Windows PowerShell, replace the directory creation command with:

```powershell
New-Item -ItemType Directory -Force out
```

The remaining `javac`, `jar`, and `java` commands work similarly on Windows. With this project and **no other agent/component proactively loading `demo.LoadedLater` before `SnapshotMain`**, the stdout of the Java command is:

```text
BEFORE_PRESENT=false
AFTER_PRESENT=true
FOUND_SAME_CLASS=true
INIT=LoadedLater
SAME_AFTER_INIT=true
```

Exact sequence explanation:

1. `BEFORE_PRESENT=false`: that specific class had not yet been loaded into the application loader at the time of the lab's first snapshot.
2. `Class.forName(name, false, loader)` loads the class **without** running the `static` block; `INIT=LoadedLater` has not appeared yet.
3. `AFTER_PRESENT=true`: the second snapshot now contains the class.
4. `FOUND_SAME_CLASS=true`: the found `Class<?>` element has the **exact same identity**.
5. `Class.forName(name, true, loader)` triggers initialization, so **`INIT=LoadedLater`** appears after the snapshot results.
6. `SAME_AFTER_INIT=true`: initialization **does not create a new class identity**.

If another agent/framework has already loaded that class beforehand, the `BEFORE_PRESENT` line may be `true`. That should not be considered an API bug; run in a clean lab process and check other hooks and inspection boundaries. `getAllLoadedClasses` itself does not distinguish “why a class was loaded”.

### 4.7. Why not print the total class count as a fixed value?

The result `snapshot.length` depends on the JVM vendor/version, JDK modules, agent libraries, how the program is launched, and GC/loading timing. **There is no standard number like “a JVM must have 1,000 classes”**. The example deliberately prints only booleans with clear conditions, without fabricating loaded class counts.

If you want to inspect the actual count on your machine, add these lines to `SnapshotMain`:

```java
// Fragment: variables before and afterLoad were declared above.
System.out.println("COUNT_BEFORE=" + before.length);
System.out.println("COUNT_AFTER=" + afterLoad.length);
```

This is an **additional fragment for the program**, so the two count output lines **depend on the runtime**. Do not write a unit test expecting an exact number across all JDKs.

## 5. Special Case: Different Class Loaders with the Same Class Name

Plugin or hot-reload systems can load **two classes with the same binary name** using two different defining class loaders. `getAllLoadedClasses` can return **both `Class<?>` objects**; if you convert them into a `Set<String>` by `getName()`, you will accidentally **merge two runtime types into one**.

### 5.1. Plugin Class — `plugin-src/plug/SideBySide.java`

```java
package plug;

public final class SideBySide {
    public String version() {
        return "one";
    }
}
```

We will use **the same class file** but load it through **two separate loaders**. There is no need to compile two different source versions to demonstrate class identity.

### 5.2. Program — `src/demo/LoaderIdentityMain.java`

```java
package demo;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.Arrays;

public final class LoaderIdentityMain {
    private LoaderIdentityMain() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: LoaderIdentityMain <plugin-classes-dir>");
        }

        URL[] urls = {
                Path.of(args[0]).toAbsolutePath().toUri().toURL()
        };
        ClassLoader parent = ClassLoader.getPlatformClassLoader();

        try (URLClassLoader first = new URLClassLoader(urls, parent);
             URLClassLoader second = new URLClassLoader(urls, parent)) {

            Class<?> a = Class.forName("plug.SideBySide", false, first);
            Class<?> b = Class.forName("plug.SideBySide", false, second);
            Class<?>[] snapshot = CensusAgent.snapshot();

            System.out.println("SAME_NAME="
                    + a.getName().equals(b.getName()));
            System.out.println("SAME_CLASS=" + (a == b));
            System.out.println("DIFFERENT_LOADERS="
                    + (a.getClassLoader() != b.getClassLoader()));
            System.out.println("SEES_A="
                    + Arrays.asList(snapshot).contains(a));
            System.out.println("SEES_B="
                    + Arrays.asList(snapshot).contains(b));
        }
    }
}
```

**Reason for using the platform loader as parent:** prevents the application/system loader (running `LoaderIdentityMain` on `out`) from accidentally defining `plug.SideBySide` first and delegating both child loaders to the same class. This is a lab design, not a recommendation to use the platform parent for all real-world plugins: applications need to share API/SPI in a parent loader and manage dependency visibility according to their architecture.

### 5.3. Running the Loader Identity Experiment

After creating `census-agent.jar` in section 4:

```bash
mkdir -p plugin-out
javac --release 17 -d plugin-out plugin-src/plug/SideBySide.java
javac --release 17 -cp out -d out src/demo/LoaderIdentityMain.java
java -javaagent:census-agent.jar -cp out demo.LoaderIdentityMain plugin-out
```

On Windows PowerShell, you can create `plugin-out` with `New-Item -ItemType Directory -Force plugin-out`; `javac` and `java` remain the same.

Stdout on a JDK supporting `-javaagent`, with the plugin class only in `plugin-out` and no other loading mechanism interfering:

```text
SAME_NAME=true
SAME_CLASS=false
DIFFERENT_LOADERS=true
SEES_A=true
SEES_B=true
```

Although `a.getName()` and `b.getName()` both return `plug.SideBySide`, the JVM treats them as **two class identities**. The snapshot contains two separate `Class<?>` references. This explains why:

- Counting `snapshot.length` differs from counting **unique class names**.
- A `String name` key is not enough to assign a class to the right loader.
- `isModifiableClass(a)` and `isModifiableClass(b)` may need to be queried **separately**, since they are two runtime types.
- When removing a plugin, references to old `Class<?>` objects and classloaders must be released if you want the old classes to become eligible for unloading.

Calling `URLClassLoader.close()` closes loader resources appropriately, and **does not force the JVM to unload** classes still held by other references.

## 6. How does `getAllLoadedClasses` differ from `getInitiatedClasses(loader)`?

Both APIs return `Class[]` but answer **two different questions**:

| API | Question | Scope and Limits |
| --- | --- | --- |
| `getAllLoadedClasses()` | “What runtime classes currently exist across the entire JVM?” | Includes classes, interfaces, hidden types, and arrays per Javadoc |
| `getInitiatedClasses(loader)` | “Which classes can this loader find by name via the load/link mechanism?” | Classes for which the loader has been recorded as an **initiating loader**; if `loader == null`, it is bootstrap |
| `Class.getClassLoader()` | “Who is the defining loader of **a single Class<?>**?” | Property of each class, **not** the list of initiating loaders |

`getInitiatedClasses(loader)` can contain classes **defined by a parent** that the child **initiated** via delegation. You must not assume every returned element is a class with `clazz.getClassLoader() == loader`.

The JDK 17 Javadoc further states: `getInitiatedClasses` **does not include hidden classes/interfaces and array classes whose component type is a hidden class/interface**, because they cannot be found by name by a loader in the normal way. Conversely, `getAllLoadedClasses` **includes** them.

### 6.1. A fragment reading initiated classes

```java
// Fragment: taken from the CensusAgent class and the known main class.
ClassLoader loader = SnapshotMain.class.getClassLoader();
Class<?>[] initiated = CensusAgent.initiatedBy(loader);
System.out.println("INITIATED_COUNT=" + initiated.length);
```

**This is a fragment**, not a fixed stdout line. The list and count can change within the same JVM as loading/linking occurs. Do not confuse the initiating loader with the defining loader in plugin analysis.

### 6.2. Bootstrap loader and `null`

`Class.getClassLoader() == null` usually indicates a class defined by the **bootstrap loader**. `getInitiatedClasses(null)` means querying classes that the bootstrap loader can find by name; it does **not** mean “no filter needed”, and is **not** synonymous with the entire JVM.

When logging, you should use a clear marker like `<bootstrap>` for a `null` loader, because the string `null` is easily mistaken for missing data. This is a display choice, not the actual name of a Java `ClassLoader` object.

## 7. Hidden classes, array classes, interfaces, and primitives

### 7.1. Hidden classes

`Class.isHidden()` identifies a class defined via the hidden class mechanism (JDK 15+). Hidden classes typically serve runtime frameworks/language mechanisms; they do not have a normal binary name for `Class.forName` to load directly. Therefore:

- They can **appear in `getAllLoadedClasses`**.
- Do not assume the name can be used verbatim to reload via `Class.forName`.
- Do not treat them as normal candidates for every kind of redefinition/retransformation.
- They can increase the loaded class count even though you do not see a corresponding `.class` file in build output.
- If logging names, pay attention to names with dynamically generated/runtime-specific components and security policies.

**Do not** assume every lambda on every JDK/vendor is implemented with the same hidden classes mechanism. Observe `clazz.isHidden()` instead of guessing from name patterns.

### 7.2. Array classes

Arrays `String[]`, `int[]`, and `int[][]` all have `Class<?>` objects. When appearing in a snapshot, `clazz.isArray()` is `true`. An array class's `getName()` can be in descriptor-like form such as `[Ljava.lang.String;` or `[I` instead of the source syntax `java.lang.String[]`.

For an array class, `getComponentType()` lets you step down to the element/component type:

```java
// Fragment: arrayType is Class<?> and was checked beforehand.
if (arrayType.isArray()) {
    Class<?> component = arrayType.getComponentType();
    System.out.println(component.getName());
}
```

An array class **is not** a class with its own methods to arbitrarily retransform. Per the `Instrumentation.isModifiableClass` Javadoc, **array classes and primitive classes are never modifiable**. Thus *“being in the snapshot” does not imply “allowed to modify bytecode”*.

### 7.3. Interfaces and primitive types

`getAllLoadedClasses` also returns interfaces: `clazz.isInterface()` distinguishes them. For primitive types (e.g., `int.class`, `void.class`), the `Class<?>` objects representing primitives do not mean a Java class file has been loaded/defined like a reference class. Do not design a “scan loaded classes” tool based on the assumption that primitives have class-file bodies or are retransformable targets.

If you want to classify every element, prefer the API characteristics `isArray()`, `isHidden()`, `isInterface()`, `isPrimitive()` instead of string matching like `"["` or `"lambda"`.

## 8. Scanning the whole JVM: filtering, sorting, and reporting safely

To produce a readable report, take a snapshot once, filter by the right package/module/loader, extract the needed fields, and then **release the array** after processing. Some example fragments:

```java
Class<?>[] snapshot = CensusAgent.snapshot();

long arrayCount = Arrays.stream(snapshot)
        .filter(Class::isArray)
        .count();

long hiddenCount = Arrays.stream(snapshot)
        .filter(Class::isHidden)
        .count();

long interfaceCount = Arrays.stream(snapshot)
        .filter(Class::isInterface)
        .count();
```

**Fragment:** requires `import java.util.Arrays;` and an active `CensusAgent`. The counts depend on each JVM/program and **can change over time**; there is no reliable fixed stdout for this example.

### 8.1. Do not use `getName()` as the sole key

If grouping is needed:

```text
Actual class identity:
  Class<?> reference
  + defining ClassLoader identity
  + name/module for display
```

With `HashMap<Class<?>, ...>` or `Set<Class<?>>`, the `Class<?>` references themselves distinguish two types with the same name. A `Map<String, Class<?>>` keyed by `getName()` can overwrite one entry when two plugin loaders define the same binary name.

For stable display, **sort a copy of the filtered list** by name + loader description rather than expecting ordering from `getAllLoadedClasses`. Do not mutate internal JVM arrays; the returned array is a separate observation container, though the classes inside are runtime objects. Even when sorting for display, do not confuse the sorted position with the actual order in which classes were loaded by the JVM.

### 8.2. Common filtering criteria

| Criterion | Example | Warning |
| --- | --- | --- |
| Package prefix | `getName().startsWith("com.example.")` | Hidden/arrays have different naming; prefix may miss them |
| Loader identity | `clazz.getClassLoader() == targetLoader` | Selects defining loader, different from initiating loader |
| Named module | `clazz.getModule().getName()` | Unnamed module returns `null`; must be handled |
| Array/hidden | `isArray()`, `isHidden()` | Not every runtime type has a standalone class file |
| Capability | `inst.isModifiableClass(clazz)` | Can be false; necessary but not sufficient for retransform to succeed |
| Annotation/reflection | `getDeclaredMethods()`, `getAnnotations()` | May trigger loading of other types; can be costly/violate access |

Reports should limit line count, use sampling/batching, and avoid continuously printing tens of thousands of class names to stdout on the application's hot path. **Class/module/loader names** can also reveal application structure or dependencies; protect logs appropriately.

## 9. A snapshot is not a stream of load/unload events

If you take snapshots at T1 and T2 and compute:

```text
added = S2 - S1
removed = S1 - S2
```

this is a **membership difference between two observations**, not a complete event log. A class could be loaded and then unloaded between the two calls and **not appear in either snapshot**. When multiple loaders share the same name, subtraction must use **class identity**, not just name.

In particular:

- **Do not infer load order** from array element order.
- **Do not infer load time** from a `Class<?>` (there is no standard `loadedAt` field).
- **Do not infer why a class was loaded** or its bytecode source from a `Class<?>` object.
- **Do not claim a class is initialized** just because it appears in the array.
- **Do not claim there is no leak** just because the class count did not increase between two measurements.
- **Do not infer the number of objects** of a class from the fact that the class appears only once in the snapshot.

To record **events whenever a class is defined**, use an appropriate tool such as `ClassFileTransformer` at load time, JVMTI events, or JFR events (depending on the event and runtime capabilities), instead of using `getAllLoadedClasses` as a callback. If you need to capture the current list when an agent is attached **after the program is already running**, this API is especially useful because it does not miss classes that already existed before the agent started observing.

### 9.1. When does a snapshot differ from ClassFileTransformer?

| Need | Tool / Path |
| --- | --- |
| Get the list of classes **currently loaded** | `Instrumentation.getAllLoadedClasses()` |
| See classes a loader has initiated | `Instrumentation.getInitiatedClasses(loader)` |
| Inspect class bytes **in a callback** during load/redefine/retransform | `ClassFileTransformer.transform` |
| Modify method bytecode of an already loaded class | `retransformClasses` / `redefineClasses` if capabilities/target allow |
| Inspect a class file from a JAR or directory on disk | `jar`, `javap`, `Files.readAllBytes` |
| Analyze class file bytecode via a typed API | ASM; or `java.lang.classfile` on JDK 24+ |
| Observe loading/unloading over time | JFR/JVMTI logging/events or an appropriate agent callback |

**Do not confuse:** `getAllLoadedClasses` **does not return bytecode** and **does not create a `ClassFileTransformer` callback**. Wanting to “dump every loaded class file” is not just writing `Class<?>[] classes = getAllLoadedClasses()` and serializing `clazz`.

## 10. Checking class modifiability after taking a snapshot

A common step in instrumentation is getting the classes and then selecting targets for `retransformClasses`. Follow the proper sequence:

1. Capture `Class<?>[]`.
2. Select classes to analyze by **identity + loader + class name + policy**.
3. Call `isModifiableClass(type)` for that specific class.
4. Check `isRetransformClassesSupported()` and the agent manifest if you want to retransform.
5. Register a transformer with `addTransformer(transformer, true)` when appropriate, ensuring valid class file output.
6. Call `retransformClasses` only on valid and modifiable targets, with proper error handling/rollback.

A fragment:

```java
// Fragment: inst is the Instrumentation provided to the agent.
if (inst.isRetransformClassesSupported()
        && inst.isModifiableClass(candidate)) {
    inst.retransformClasses(candidate);
}
```

`candidate` must be a selected `Class<?>`; this snippet needs handling for `UnmodifiableClassException`, `UnsupportedOperationException`, and other bytecode errors in real code. Do not infer that **every class seen in the snapshot can be retransformed**. Arrays/primitives are not modifiable; some other classes are also not modifiable depending on the JVM. Merely calling `getAllLoadedClasses` grants no capabilities.

In JVMs after JDK 21, dynamic agent loading has version-specific warnings/policies; this lesson's experiment uses **startup `-javaagent`**, so it does not require configuring attach/self-attach permissions.

## 11. Performance, memory, and security considerations

### 11.1. Cost of creating the array repeatedly

A snapshot can contain **tens of thousands of `Class<?>` objects** in a large application. Calling the API in a tight loop causes:

- JVM overhead to traverse/collect the list.
- Allocation of `Class<?>[]` and GC garbage.
- Filtering/sorting/logging overhead, which can exceed the cost of obtaining the array.
- Long-lived references that hinder class unloading.
- Risk of contention/safepoint/latency impact depending on VM, timing, and scale.

**Do not** call `getAllLoadedClasses()` on **every request**, **every method invocation**, or inside a `transform` callback for every class. Prefer diagnostic triggers, sufficiently sparse intervals, rate limiting, caching aggregated metrics, and limiting output.

### 11.2. Side effects of inspection

Calling `getAllLoadedClasses` to get `Class<?>[]` does not mean “initializing all classes”. However, if code subsequently calls `Class.forName(name)`, `getDeclaredMethods()`, queries annotations, or creates instances, those operations can lead to loading/linking/initialization, class access checks, or their own exceptions. **Separate the enumeration step from the reflective deep inspection step**, and document the impact clearly.

### 11.3. Sensitive data

Class and loader names can reveal frameworks, internal packages, technologies, or deployed modules. If snapshots are used for operations, export only necessary information, control viewing permissions, redact names/exclude sensitive packages, and do not log data from object instances.

## 12. Distinguishing by loader, module, and runtime identity

With the same name `com.acme.Plugin`, there can be:

```text
com.acme.Plugin @ LoaderPluginA
com.acme.Plugin @ LoaderPluginB
com.acme.Plugin @ LoaderPluginC
```

These are **three runtime class identities** if the three defining loaders actually define separate types. `Class.getModule()` helps group by JPMS module; unnamed modules can differ by loader even when the module's `getName()` returns `null`.

Do not just build a `Map<String, Boolean> loadedByName` dictionary to check if a plugin is loaded: the result may report “loaded” because of loader A while the application actually needs loader B. Alongside the name, store a **separate loader ID for reporting** (by object identity or an internal identifier) instead of `loader.toString()` as a long-term unique key.

If you need to track **unloading**, do not keep `Class<?>` or loaders in an unbounded strong static map. You can use metrics detached from object references, weak references where appropriate, or specialized tools; still, understand that GC has no guaranteed unloading time.

## 13. Common Misconceptions

| Misconception | Why it is wrong | Correct understanding |
| --- | --- | --- |
| “The snapshot contains every class on the classpath” | Classpath is the set of resources that *can* be loaded | The API lists only classes **currently loaded** |
| “A loaded class means its static initializer has run” | Loading and initialization are different phases | `Class.forName(name,false,loader)` can load without initializing |
| “The returned array will update itself later” | The array is the result of that single call | Call again to get a new snapshot |
| “The order in the array is the load order” | The Javadoc specifies no such order | Do not infer a timeline from indices |
| “A class name appears only once” | Two defining loaders can create two runtime types with the same name | Compare `Class<?>` identity and loader |
| “If a class is visible, it can definitely be retransformed” | Many classes are not modifiable | Check capability and `isModifiableClass` |
| “Taking a snapshot returns raw .class bytes” | The API returns `Class[]` | Use callbacks/bytecode tooling for bytes |
| “getInitiatedClasses(loader) is all classes the loader itself defined” | An initiating loader may be a child delegating to a parent | Distinguish initiating and defining |
| “Hidden types are not part of the snapshot” | `getAllLoadedClasses` includes hidden types on JDK 17+ | Use `isHidden` to classify |
| “Every hidden class can be reloaded by name” | A hidden class is not findable by name | Do not `Class.forName` it like a normal type |
| “Arrays do not have Class objects” | Array types have `Class<?>` objects | `isArray` and component type |
| “Snapshot count is the number of object instances” | A class can have 0 or millions of objects | Snapshots measure **types**, not instances |
| “Keeping snapshots has no memory impact” | `Class<?>` references can keep loaders alive | Release snapshots, avoid long-lived strong refs |
| “Diffing two snapshots is a complete load/unload log” | Events can occur between two calls | Conclude only membership differences |
| “Counting unique names is the number of runtime classes” | Merges same-named types from multiple loaders | Count `Class<?>` identities |
| “Not seeing a class means the JVM never loaded it” | It may have unloaded before the snapshot | A snapshot describes only **the present** |
| “Calling enumerate adds a transformer” | This is an observation API | No bytecode transformation occurs unless another API is registered/called |

## 14. Checklist for testing a class scanner

- [ ] Agent `premain`/`agentmain` receives `Instrumentation` properly; does not try to `new` this interface.
- [ ] Snapshot is captured in the right **JVM process** and at the intended time.
- [ ] Uses `Class<?>[]`, not treating entries as class names or class bytes.
- [ ] Can see interfaces, hidden classes, and array classes; code classifies them properly.
- [ ] Does not assume static initialization occurred when a class appears.
- [ ] Distinguishes the same binary name with different defining loaders.
- [ ] Does not rely on snapshot ordering.
- [ ] If comparing two snapshots, uses identity-based set/diff and accounts for load/unload timing.
- [ ] Does not use a string-name-only map to represent a runtime class.
- [ ] Does not hold full `Class<?>[]` arrays long-term in static caches.
- [ ] Does not call scan at very high frequency or on every method invocation.
- [ ] Has package/module filtering scope, log size limits, and data sensitivity controls.
- [ ] For retransformation, checks capability, manifest, and `isModifiableClass` separately.
- [ ] Does not use raw hashes/classpath file lists as evidence of loaded runtime classes.
- [ ] Tests behavior on the target JVM vendor and version, without hardcoding total class count.

## 15. Self-check questions

1. **Does `getAllLoadedClasses` return file bytes or `Class<?>[]`?**  
   It returns `Class<?>[]`: a list of runtime class objects.

2. **Is a class in a JAR that has not been loaded yet listed?**  
   Not just because it is in the JAR/classpath. It must be loaded by the JVM.

3. **Why does the snapshot contain `demo.LoadedLater` before `INIT=LoadedLater` is printed?**  
   `Class.forName(name,false,loader)` loads the class without requesting initialization.

4. **Can `snapshot[0]` be used to know the first class loaded by the JVM?**  
   No. Array order is not a class loading order contract.

5. **Are two classes with the same `getName()` but different defining loaders the same class?**  
   No. They are two runtime identities; even with the same name they can be different `Class<?>` objects.

6. **Can `getInitiatedClasses(loader)` contain a class defined by a parent?**  
   Yes. An “initiating” loader can delegate to a parent to define the class.

7. **Can a hidden class be in `getAllLoadedClasses` but not in `getInitiatedClasses`?**  
   Yes, per the JDK 17+ Javadoc, because hidden types cannot be looked up by name in the normal way.

8. **Must each snapshot strictly increase in count compared to the previous one?**  
   No. The JVM can load/unload, and observation does not guarantee the count only increases.

9. **Does `getAllLoadedClasses` transform classes or run static initializers of all classes?**  
   It has no such behavior. It is an observation API, not a transformer or initializer.

10. **Can every class in a snapshot be passed to `retransformClasses`?**  
    No. You must check `isModifiableClass` and `isRetransformClassesSupported`; array/primitive classes are not modifiable.

11. **What is the risk if `Class<?>[]` is kept in a static cache forever?**  
    Strong references to `Class`/loaders can keep classes/plugin loaders alive, bloating memory.

12. **Can a class that loaded and unloaded between T1/T2 while being absent in both snapshots be detected?**  
    Not by comparing two snapshots; an appropriate event stream/logging is needed.

13. **Why is `getName()` not a sufficient key for a plugin inventory?**  
    Multiple defining loaders can define the same binary name; loader/identity is required.

14. **How does `Class.forName("demo.LoadedLater",true,loader)` differ from the `false` parameter?**  
    `true` requests initialization if not yet initialized; `false` does not request running the initializer.

15. **What must be done to see the bytecode of an already loaded class?**  
    Use a path that collects class-file bytes via transformer/retransform or appropriate JVMTI/diagnostic tooling, not by taking `Class<?>[]` and casting to bytes.

## 16. Official Documentation

- **Oracle JDK 17 — `Instrumentation.getAllLoadedClasses`, `getInitiatedClasses`, `isModifiableClass`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- **Oracle JDK 25 — `Instrumentation`** (comparing API in newer JDK versions): https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- **Oracle JDK 17 — `java.lang.instrument` package**, `premain`/`agentmain`, manifest `Premain-Class`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- **Oracle JDK 17 — `Class.forName(name, initialize, loader)`** and `Class<?>` inspection methods: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **Oracle JDK 17 — `ClassLoader`**, parent delegation and defining loader: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Oracle JDK 17 — `URLClassLoader`** and `close()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- **JVMS 17 — Chapter 5: Loading, Linking, and Initializing**, class identity and runtime packages: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html

**Conclusion:** `Instrumentation.getAllLoadedClasses()` is the way to take **a snapshot of runtime classes currently present in the JVM**. The result is a `Class<?>[]` including interfaces, hidden types, and arrays; it is not a list of every class file on disk, does not prove initialization or retransformability, has no class loading order, and does not update itself. Match by **class identity + defining loader**, take snapshots only when needed, and release references after analysis.
