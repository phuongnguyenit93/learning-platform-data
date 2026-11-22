# `getInitiatedClasses` Reflects Initiating Loaders, Not Just Defining Loaders

When analyzing class loading in Java instrumentation, two questions sound similar but are fundamentally different:

1. **Defining loader**: which class loader actually **defined** the class?
2. **Initiating loader**: which class loaders has the JVM recorded as **initiating the loading** of that class, possibly by delegating to another loader?

`Instrumentation.getInitiatedClasses(ClassLoader loader)` answers the second question. A class **defined by a parent loader** can still appear in the result for a **child loader** when the child initiated loading/linkage and the parent performed the definition.

A common mistake is taking `getInitiatedClasses(child).length` and calling it "the number of classes defined by child." That is incorrect according to the JVM contract.

This lesson belongs to the **Runtime Inspection** section of Java Advance — instrumentation. Its contents cover the Java 17 API contract, definitions in JVMS §5.3, a practically verified Java 17+ agent example, differences from `getAllLoadedClasses`, bootstrap/array/hidden classes, how to read output, and common analysis mistakes.

## 1. Distinguishing Three Important APIs

In a Java agent method, once you have the variables `Instrumentation inst`, `ClassLoader loader`, and `Class<?> clazz`, you can call:

```java
Class<?>[] initiated = inst.getInitiatedClasses(loader);
ClassLoader defining = clazz.getClassLoader();
Class<?>[] allLoaded = inst.getAllLoadedClasses();
```

These are just **three illustrative lines** using already-declared variables, not a standalone program.

| API | Question Answered | Notes |
|---|---|---|
| `getInitiatedClasses(loader)` | Which classes has the JVM recorded this loader as an *initiating loader* for? | Returned classes are **not necessarily** defined by this loader |
| `clazz.getClassLoader()` | Which **defining loader** does this runtime class have? | `null` represents the bootstrap loader |
| `getAllLoadedClasses()` | Which classes are currently loaded in the JVM? | JVM-wide scope, including hidden classes and array classes |

An example of a completely valid result:

```text
defining loader of demo.Model = parent
demo.Model in getInitiatedClasses(child) = true
```

The two lines above do not contradict each other. They describe **two different relationships of the same `Class<?>` object**.

## 2. The JDK 17 `getInitiatedClasses(ClassLoader)` Contract

Full signature:

```java
Class<?>[] getInitiatedClasses(ClassLoader loader);
```

This method belongs to the `java.lang.instrument.Instrumentation` interface, in the `java.instrument` module. According to the Oracle JDK 17 Javadoc, it returns an array of classes for which the JVM **has recorded** `loader` as an initiating loader; these are classes that can be found by name through mechanisms such as `ClassLoader.loadClass`, `Class.forName`, and **bytecode linkage**.

Key points to remember:

- The parameter is a **loader object**, not a class name or module name.
- **Passing `null` is valid**: it queries classes recorded with the **bootstrap class loader**, rather than throwing `NullPointerException` by default.
- The result is a `Class<?>[]` array; the array may be empty.
- The returned set of classes is **not a list of all classes that could later be loaded** from the loader's URLs, JARs, classpath, or module path.
- The API **does not load all classes itself** to build the list.
- **Hidden** classes and array classes whose element type is a hidden class/interface **are not returned** because they cannot be found by name through a loader.
- The API **does not guarantee ordering by class loading time**. Do not treat array position as the sequence of `loadClass` calls or linkage instructions.
- The returned array is data at a **point-in-time snapshot**; classes may continue to be loaded on other threads.

If you want to inspect without transforming bytecode, you **do not need** to call `addTransformer` or `retransformClasses`. You only need a valid `Instrumentation` instance from a Java agent.

### 2.1. How to Obtain `Instrumentation`?

Typically, the JVM passes it into the agent's entry point:

```java
package agent;

import java.lang.instrument.Instrumentation;

public final class InspectAgent {
    public static void premain(String args, Instrumentation inst) {
        ClassLoader appLoader = ClassLoader.getSystemClassLoader();
        Class<?>[] snapshot = inst.getInitiatedClasses(appLoader);
        System.out.println("initiated count = " + snapshot.length);
    }
}
```

This is an **illustrative class** without a manifest/launcher. The count varies depending on the JVM, when classes are resolved, and other agents, so there is no reliable specific stdout number across all runtimes.

When running with `-javaagent`, the JAR must have `Premain-Class: agent.InspectAgent`. If using the Attach API, the entry point is `agentmain`. `Instrumentation` is not created via a regular public constructor in a Java application.

## 3. According to the Java Virtual Machine Specification: "define" and "initiate"

JVMS §5.3 describes two forms of class loading:

- If loader `L` **directly** locates the binary representation and causes the JVM to define the class, `L` is the **defining loader**.
- If loader `L` **initiates** loading, directly or **indirectly through delegation**, `L` may be recorded by the JVM as an **initiating loader**.

To identify a runtime class `C`, you can picture it as:

```text
<binaryName, definingLoader>
```

For example:

```text
<demo.Model, ParentLoader>
```

Two loaders can both initiate this class, yet there is still only **one runtime `Class<?>` object** with `ParentLoader` as its defining loader.

### 3.1. Visualizing Parent Delegation

```text
                        ParentLoader
                           |
                    defines demo.Model
                           ^
                           |
                        delegates
                           |
                        ChildLoader
                           |
                    defines demo.Entry
                           |
                           v
               Entry.invoke() calls Model.value()
```

When the JVM executes the bytecode of `demo.Entry.invoke()`:

1. `Entry` has already been defined by **ChildLoader**.
2. The bytecode of `Entry` references `demo.Model`.
3. The JVM needs to resolve the symbolic reference according to the class loading mechanism associated with `Entry`.
4. `ChildLoader` initiates loading and delegates to `ParentLoader`.
5. `ParentLoader` defines (or has already defined) `demo.Model`.
6. The JVM records the appropriate initiating relationships for child and parent.

After that event, we can observe:

| Runtime class | Defining loader | Recorded initiating loaders |
|---|---|---|
| `demo.Entry` | ChildLoader | ChildLoader |
| `demo.Model` | ParentLoader | ParentLoader **and** ChildLoader |

This is the central model of this lesson: **a parent's class appears in the child's initiated set** even though the child did **not** define the class.

### 3.2. One Defining Loader, Potentially Multiple Initiating Loaders

If the child delegates to the parent, the two calls:

```java
Class<?> a = parent.loadClass("demo.Model");
Class<?> b = child.loadClass("demo.Model");
System.out.println(a == b);
```

are a **snippet** in a context where `parent` and `child` already exist. With the example's parent-first delegation, the result is `true`: there are not two copies of `demo.Model`.

Conversely, when two **independent** class loaders each define the same binary name:

```text
<demo.Model, LoaderA> != <demo.Model, LoaderB>
```

They are two different runtime types. Comparing `Class.getName()` alone is not enough; when exact identity is needed, compare `Class<?>` using `==` and record the defining loader.

### 3.3. Intermediate Loaders in a Delegation Chain Are Not Automatically Initiators

JVMS §5.3 also emphasizes a detail:

```text
L1 (initiating) -> Lmiddle -> L2 (defining)
```

According to the specification, **intermediate** loaders between the initiating loader `L1` and the defining loader `L2` are **not automatically** considered initiating loaders of that class. An intermediate loader may have an initiating relationship due to **another initiation event**, but this must not be inferred simply because it lies on the parent chain.

Therefore, `getInitiatedClasses(loader)` is not an operation that retrieves **all classes of the loader and all its ancestors**. It reflects **initiating relationships recorded by the JVM**.

## 4. Runnable Java 17+ Example with Both Defining and Initiating

This lab creates a **startup Java agent** to obtain `Instrumentation`. We set up two `URLClassLoader` instances:

- `parent`: sees `out/model`, containing `demo.Model`.
- `child`: sees `out/child`, containing `demo.Entry`, with `parent` as its parent.
- `Entry.invoke()` executes a call to `Model.value()`. This is the **bytecode linkage** path that causes `child` to initiate `Model`.

In addition, there is a simple application launcher so the JVM runs `main()` after `premain` finishes.

### 4.1. Directory Structure

```text
initiated-demo/
├── src/
│   ├── demo/
│   │   └── Model.java
│   ├── child/
│   │   └── demo/
│   │       └── Entry.java
│   ├── probe/
│   │   └── Probe.java
│   └── App.java
├── agent.mf
├── out/
│   ├── model/
│   ├── child/
│   └── agent/
└── probe-agent.jar
```

`out` and `probe-agent.jar` are outputs, created after the compile/JAR packaging steps. **Do not** put `out/model` or `out/child` on the runtime `-cp`; the program will create separate loaders for them.

### 4.2. File `src/demo/Model.java`

```java
package demo;

public final class Model {
    public static String value() {
        return "ok";
    }
}
```

`Model` does not depend on other application code. It resides in a directory whose search URL is **given only to `parent`**.

### 4.3. File `src/child/demo/Entry.java`

```java
package demo;

public final class Entry {
    public static String invoke() {
        return Model.value();
    }
}
```

Because both classes have the same package name in source code, `Entry` does not need an import statement for `Model`. The call `Model.value()` becomes a **symbolic reference** in `Entry`'s bytecode. When the JVM resolves it from `Entry` defined by `child`, `parent` can supply `Model`.

`Model.value()` is `public static`, so the two classes belonging to **different runtime packages** (different defining loaders) can still call it validly without relying on package-private access.

### 4.4. File `src/probe/Probe.java`

```java
package probe;

import java.lang.instrument.Instrumentation;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class Probe {
    public static void premain(String options, Instrumentation inst)
            throws Exception {

        URL[] parentUrls = {
                Path.of("out", "model")
                        .toAbsolutePath().toUri().toURL()
        };
        URL[] childUrls = {
                Path.of("out", "child")
                        .toAbsolutePath().toUri().toURL()
        };

        try (URLClassLoader parent =
                     new URLClassLoader(parentUrls, null);
             URLClassLoader child =
                     new URLClassLoader(childUrls, parent)) {

            System.out.println("[agent] beforeChildModel="
                    + contains(inst.getInitiatedClasses(child),
                            "demo.Model"));

            Class<?> entry =
                    Class.forName("demo.Entry", true, child);

            System.out.println("[agent] entryDefinedChild="
                    + (entry.getClassLoader() == child));

            System.out.println("[agent] result="
                    + entry.getMethod("invoke").invoke(null));

            Class<?> model = parent.loadClass("demo.Model");

            System.out.println("[agent] modelDefinedParent="
                    + (model.getClassLoader() == parent));

            System.out.println("[agent] modelInitiatedChild="
                    + has(inst.getInitiatedClasses(child), model));

            System.out.println("[agent] modelInitiatedParent="
                    + has(inst.getInitiatedClasses(parent), model));

            System.out.println("[agent] modelFoundByChild="
                    + (child.loadClass("demo.Model") == model));

            System.out.println("[agent] modelDefinedChild="
                    + (model.getClassLoader() == child));
        }
    }

    private static boolean has(Class<?>[] classes, Class<?> wanted) {
        for (Class<?> c : classes) {
            if (c == wanted) {
                return true;
            }
        }
        return false;
    }

    private static boolean contains(Class<?>[] classes, String binaryName) {
        for (Class<?> c : classes) {
            if (c.getName().equals(binaryName)) {
                return true;
            }
        }
        return false;
    }
}
```

`Probe` is a **complete standalone file**. It does not use ASM or Byte Buddy. The `has` helper compares using **object identity** (`==`), avoiding mistakenly conflating two classes with different loaders but the same name. The `contains` helper uses `getName()` only because it is asking "before the test step, has a class with **this name** appeared yet?".

### 4.5. Important Details in the Code

**Creating the two loaders:**

```java
new URLClassLoader(parentUrls, null);
new URLClassLoader(childUrls, parent);
```

The second argument to the `URLClassLoader` constructor is the **parent loader**. In the first loader, `null` sets bootstrap as the parent at the lookup mechanism level; in the second loader, the parent is the `URLClassLoader` just created. `parent` only sees files in `out/model`, while `child` only has a URL to `out/child`.

**Measuring the prior state:**

```java
contains(inst.getInitiatedClasses(child), "demo.Model")
```

In this fixture, before the deliberate call from `Entry`, `child` has not initiated `Model`.

**Loading the `Entry` class:**

```java
Class.forName("demo.Entry", true, child);
```

`parent` does not have the `Entry` file, so `child` finds and defines it from `out/child`. Note that the code does not use `Entry.class` inside the agent, because that could accidentally use the system loader instead of `child`.

**Executing bytecode belonging to `child`:**

```java
entry.getMethod("invoke").invoke(null);
```

Inside `Entry.invoke()`, there is a reference to `Model.value()`; the JVM resolves `Model` via `child -> parent`. This is the key point that a simple class-name lookup cannot substitute for.

**Checking the two relationships:**

```java
model.getClassLoader() == parent;
has(inst.getInitiatedClasses(child), model);
```

Both expressions can be `true` simultaneously, showing that `child` initiated while `parent` defined.

### 4.6. File `src/App.java`

```java
public class App {
    public static void main(String[] args) {
        System.out.println("[app] done");
    }
}
```

`App` does not import or call `Model` or `Entry`, so it does not interfere with the class loading sequence that the agent is inspecting.

### 4.7. Manifest `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: probe.Probe

```

`Premain-Class` points to the exact agent class. Keep a blank line at the end of the manifest's main section. Because the agent **only observes** and does not retransform/redefine, there is no need to declare the `Can-Retransform-Classes` capability.

### 4.8. Compiling and Packaging the JAR

Open a terminal in the `initiated-demo` directory and use **JDK 17+**:

```bash
mkdir out
mkdir out/model
mkdir out/child
mkdir out/agent
```

You only need to create the directories the first time. Compile in order:

```bash
javac --release 17 -encoding UTF-8 -d out/model src/demo/Model.java

javac --release 17 -encoding UTF-8 -cp out/model -d out/child src/child/demo/Entry.java

javac --release 17 -encoding UTF-8 -d out/agent src/probe/Probe.java src/App.java
```

**Why doesn't the compile-time `-cp out/model` in the second command invalidate the experiment?** The compiler needs to see `Model` to check the `value()` method, but the `.class` file for `Entry` is still saved **separately** in `out/child`. At runtime, `Model` is only provided to the `parent` loader.

Create the agent JAR:

```bash
jar --create --file probe-agent.jar --manifest agent.mf -C out/agent probe/Probe.class
```

Only `probe/Probe.class` and the manifest are needed in the agent JAR. `App.class` is loaded from `out/agent` when the JVM runs the application; it does not have to be packaged into the agent JAR.

### 4.9. Running and Reading Stdout

```bash
java -javaagent:probe-agent.jar -cp out/agent App
```

**Observed stdout on OpenJDK 24.0.2, source compiled with `javac --release 17`:**

```text
[agent] beforeChildModel=false
[agent] entryDefinedChild=true
[agent] result=ok
[agent] modelDefinedParent=true
[agent] modelInitiatedChild=true
[agent] modelInitiatedParent=true
[agent] modelFoundByChild=true
[agent] modelDefinedChild=false
[app] done
```

These are the **nine lines of stdout** from the tested fixture. Depending on the JVM, you may see additional VM information on stderr; do not merge diagnostic stderr into the example's standard stdout.

| Line | Explanation |
|---|---|
| `beforeChildModel=false` | No initiation record for `child` on `Model` at the initial snapshot |
| `entryDefinedChild=true` | `child` defined `Entry` |
| `result=ok` | `Entry`'s bytecode executed `Model.value()` |
| `modelDefinedParent=true` | `parent` defined `Model` |
| `modelInitiatedChild=true` | **`child` is an initiating loader of that same `Model` class** |
| `modelInitiatedParent=true` | `parent` is also an initiating loader |
| `modelFoundByChild=true` | `child` lookup returns the same `Class<?>` that `parent` defined |
| `modelDefinedChild=false` | `child` did **not** directly define `Model` |
| `app done` | Launcher continues after the agent finishes |

Experimental conclusion: **`modelInitiatedChild=true` while `modelDefinedChild=false`**. Therefore, you **cannot** take the `getInitiatedClasses(child)` list and claim every class in it is a "class of child" in the defining-loader sense.

### 4.10. Why Use Bytecode Linkage Instead of Just Calling `child.loadClass`?

A subtle detail is that **calling a Java `loadClass` method and receiving a `Class<?>`** does not necessarily mean the JVM has recorded an initiating entry for that exact loader at the moment you inspect it.

In a side experiment on OpenJDK 24.0.2, if the agent calls `child.loadClass("demo.Model")` **directly** without symbolic resolution belonging to a class defined by `child`, the child loader can **return** the parent's class, yet `getInitiatedClasses(child)` still does **not** contain it. This reflects that the API is defined in terms of the **JVM's initiating loader records**, rather than a counter of all `loadClass` calls in Java code.

Therefore, the main demo uses `Entry.invoke()` to create a symbolic reference **inside a class defined by `child`**, then observes the state after linkage. Do not extrapolate that every way of calling `loadClass` on every JVM must produce identical initiated-set output.

## 5. Bootstrap Loader: Passing `null` Is Valid

The `Instrumentation.getInitiatedClasses` Javadoc specifies:

```java
Class<?>[] fromBootstrap = inst.getInitiatedClasses(null);
```

Here, `null` **represents the bootstrap class loader**. Unlike other methods that reject `null`, this API accepts `null` intentionally.

Comparison example:

```java
Class<?>[] bootstrap = inst.getInitiatedClasses(null);
Class<?>[] system = inst.getInitiatedClasses(
        ClassLoader.getSystemClassLoader());
```

This is a snippet inside an agent method with `inst`; the two arrays **do not have to be equal**. A class like `java.lang.String` is defined by bootstrap, but system/child loaders can still initiate references to it.

`Class.getClassLoader()` also has the `null` convention for bootstrap-defined classes:

```java
boolean stringDefinedByBootstrap =
        String.class.getClassLoader() == null;
```

Do not replace `getInitiatedClasses(null)` with `getInitiatedClasses(ClassLoader.getSystemClassLoader())` just because the two sets may share many elements.

## 6. Differences from `getAllLoadedClasses`

`Instrumentation.getAllLoadedClasses()` returns an array of classes currently loaded in the JVM. It is suitable for a **runtime inventory**, not for the specific relationships of a single initiating loader.

```java
Class<?>[] all = inst.getAllLoadedClasses();
Class<?>[] initiatedByChild = inst.getInitiatedClasses(child);
```

The two arrays may contain the same elements, but **they cannot be treated as two versions with the same scope**.

| Characteristic | `getAllLoadedClasses()` | `getInitiatedClasses(loader)` |
|---|---|---|
| Scope | JVM-wide | One initiating loader |
| Parameter | None | One `ClassLoader` or `null` |
| Reflects classes defined by parent but initiated by child | May contain them | May contain them when querying child |
| Hidden classes/interfaces | Yes, per Java 17 Javadoc | No |
| Array classes | Includes array classes of all kinds | May include arrays findable by name; excludes hidden-element arrays |
| Equivalent to file list in JAR? | No | No |
| Has event chronological order? | Not guaranteed | Not guaranteed |
| Used to conclude defining loader? | Must filter `getClassLoader()` | **Do not** rely on membership alone |

If you need **the classes actually defined by a loader**, filter on **`Class.getClassLoader()`**, but remember `getInitiatedClasses` excludes hidden classes, so filtering it will **not** give a complete inventory of all special classes.

### 6.1. Counting `defined here` and `initiated elsewhere`

A clear way to interpret the data:

```java
Class<?>[] classes = inst.getInitiatedClasses(loader);

long definedHere = java.util.Arrays.stream(classes)
        .filter(c -> c.getClassLoader() == loader)
        .count();

long initiatedButDefinedElsewhere =
        java.util.Arrays.stream(classes)
                .filter(c -> c.getClassLoader() != loader)
                .count();
```

This is a **snippet** with `inst` and `loader`. `definedHere` is the number of elements **in this initiated set** whose defining loader also equals the queried loader. `initiatedButDefinedElsewhere` reflects classes defined by parent/bootstrap/other loaders.

Do not treat the sum of these two groups as the number of classes in a JAR, the number of classes the JVM can load, or the total number of objects in the application. A single class can appear in **multiple initiated sets**, so summing counts across loaders will lead to **double counting** if you are counting distinct class objects.

## 7. Array Classes: Array Classes Have a Defining Loader Based on Their Component Type

An array class has no regular `.class` file for `URLClassLoader` to read; it is created by the JVM according to the rules of §5.3.3.

- Array with a **reference component type**: its defining loader equals the defining loader of the component type.
- Array with a **primitive component type**: its defining loader is considered bootstrap.
- The JVM may also record an initiating loader for an array class when a loader initiates its creation/resolution.

Example:

```java
System.out.println(String[].class.getClassLoader() == null);
System.out.println(int[].class.getClassLoader() == null);
```

This can be placed in a `main`; on a typical JVM, both lines print `true`. `String` and `String[]` are associated with bootstrap; the primitive array `int[]` is also associated with bootstrap.

If `demo.Model` is defined by `parent`, then its array type also has a defining loader based on `Model`. However, **do not assume the array type is already in `child`'s initiated set just because `Model` is there**: you need to check whether the array has actually been created/resolved by the JVM in the corresponding context.

## 8. Hidden Classes: Intentional Limitation of the Initiating List

The Oracle Java 17 Javadoc states that `getInitiatedClasses` does **not** include:

- Hidden classes and hidden interfaces.
- Array classes that have a hidden class/interface as their element type.

They are not found by name through a loader in the usual way. Therefore, a diagnostic tool that wants to see **every currently existing class** may need `getAllLoadedClasses()` or JVMTI/JFR depending on the specific scope and goal.

Do not interpret "hidden class is not in `getInitiatedClasses(loader)`" as "the JVM does not have that class" or "the loader has nothing to do with it." This is a **limitation by API definition**.

## 9. Modules Do Not Replace the Concept of Loaders

Since Java 9, the same runtime class also belongs to a `java.lang.Module`:

```java
ClassLoader defining = clazz.getClassLoader();
Module runtimeModule = clazz.getModule();
```

This is an illustrative snippet with the variable `clazz`. You need to keep three attributes separate:

1. **Defining loader:** who created the runtime class.
2. **Initiating loader(s):** who the JVM recorded as initiating the loading of the class.
3. **Runtime module:** which module the class belongs to.

`getInitiatedClasses(child)` containing a class does **not** mean that class resides in `child`'s unnamed module. In the demo, `demo.Model` belongs to the module managed by the defining loader `parent`, while `demo.Entry` belongs to `child`'s module.

Java access control also evaluates module readability, `exports`, and `opens` separately. Do not use initiating membership to infer reflection permissions or permission to link to a non-exported package.

## 10. A Snapshot Is Not an Event Stream

Comparing before and after a call is useful:

```text
T0: child has not initiated demo.Model
T1: JVM resolves Model from Entry.invoke()
T2: child has initiated demo.Model
```

However, this is not an automatic class-loading timeline. `getInitiatedClasses` does not return timestamps, stack traces, causes, thread IDs, or chronological element ordering.

In a multi-threaded JVM, other classes may be loaded between two calls; class unloading can also change later observations. If you need a true timeline, use JFR/JVMTI class-loading events or appropriate logging/instrumentation mechanisms, and combine them with snapshot results for analysis.

### 10.1. Designing a Proper Diagnostic Table

If a UI displays classes initiated by the `child` loader, separate the fields:

| Field | Example |
|---|---|
| Class binary name | `demo.Model` |
| Queried initiating loader | ChildLoader |
| Actual defining loader | ParentLoader |
| Module | Unnamed module of ParentLoader |
| Is defining == initiating? | `false` |
| Observation time | Snapshot timestamp recorded by the tool |
| Class identity | Stable `Class<?>` reference/identifier within the measurement |

If a UI label simply says "Classes owned by ChildLoader" for the entire `getInitiatedClasses(child)` result, it can mislead investigations into memory leaks, classloader retention, and dependency graphs.

## 11. When Debugging Class Loaders, Do Not Infer from a Single Metric

Common symptoms:

| Observation | Explanation / Investigation Direction |
|---|---|
| Parent's class appears in child initiated list | May be due to child initiating and delegating per rules |
| `getInitiatedClasses(child)` does not contain a class that exists on parent | Child has not been recorded by the JVM as initiating it; not enough to prove parent cannot load it |
| Two loaders initiated the same `Class<?>` | Does not mean the JVM created two runtime class objects |
| Two classes have the same `getName()` but `== false` | Likely due to different defining loaders |
| `ClassNotFoundException` | Loader could not find the class along the requested path |
| `NoClassDefFoundError` when a method runs | Symbolic reference or dependency could not be resolved |
| `LinkageError` | May involve loading constraints, linkage, or class identity |
| `ClassCastException` with the same class name | Possible existence of two runtime types with different defining loaders |
| Initiated count decreases/increases between snapshots | Class loading/unloading and different observation times; do not infer events from counts |
| Bootstrap-defined class seen in child initiated set | Not a contradiction: defining loader differs from initiating loader |

To investigate thoroughly, record:

- Class name and **`Class<?>` identity**.
- `Class.getClassLoader()` and the loader being queried with `getInitiatedClasses`.
- Actual loader parent/delegation chain.
- Module and runtime package if it is an access error.
- Class loading time/stack evidence if available.
- JVM/JDK version and active agents.
- Root exceptions, stack traces, and class loader context.

**Do not** use `getInitiatedClasses` to conclude a loader leak simply because the number of initiated classes is large. Parent-delegated classes can make this count large without `child` defining or exclusively retaining those classes.

## 12. Common Misconceptions and Corrections

### Misconception 1 — "Initiated means it called `defineClass` itself"

Incorrect. Initiation can go through delegation and be defined by another loader.

### Misconception 2 — "A class has only one initiating loader"

Incorrect. A runtime class has one **defining loader**, but the JVM can record **multiple initiating loaders**.

### Misconception 3 — "Parent always contains all initiated classes of child"

You must not infer that. You need to examine the defining loader, the actual delegation path, and JVMS initiation recording rules. Intermediate loaders also do not automatically get recorded.

### Misconception 4 — "If it can be loaded from the classpath, it must be in the initiated set"

Incorrect. A loader may have permission to find the `.class` file, yet the JVM has never initiated loading that class.

### Misconception 5 — "Every Java `loadClass()` call grows the initiating set"

Do not assume this. The side experiment on OpenJDK 24.0.2 showed that direct `loadClass` from an agent and JVM bytecode linkage from a class defined by `child` can yield different initiated-set observations.

### Misconception 6 — "The `getInitiatedClasses` array is in chronological order"

There is no such guarantee; do not use array indices as timestamps.

### Misconception 7 — "`getInitiatedClasses(null)` is equivalent to the system loader"

Wrong. `null` means the **bootstrap loader**.

### Misconception 8 — "Hidden classes definitely appear in the initiated set"

Wrong. The Java 17 Javadoc excludes hidden classes/interfaces and arrays with hidden elements.

### Misconception 9 — "The sum of initiated array lengths is the total unique classes"

Wrong, because one class can be initiated by multiple loaders, leading to double counting.

### Misconception 10 — "The defining loader changes after child initiates"

No. A class object is tied to its defining loader. Delegation does not rewrite defining identity.

## 13. Knowledge Check Exercises

**1.** `demo.Model` is defined by `parent`, and `child` initiates it via delegation. Can it be in `getInitiatedClasses(child)`?

**Answer:** Yes. That is the purpose of the API.

**2.** Can `model.getClassLoader() == parent` and `getInitiatedClasses(child)` containing `model` both be true at the same time?

**Answer:** Yes. Defining and initiating are two different relationships.

**3.** To know who actually defined `Class<?> clazz`, which method do you use?

**Answer:** `clazz.getClassLoader()`; `null` represents the bootstrap loader.

**4.** To get a JVM-wide class inventory, which method do you use?

**Answer:** `Instrumentation.getAllLoadedClasses()`; do not equate it with an initiated set.

**5.** What does passing `null` to `getInitiatedClasses` mean?

**Answer:** Queries classes whose initiating loader is the bootstrap loader.

**6.** Why is `Entry.invoke()` used to produce strong evidence of initiating?

**Answer:** Because there is a symbolic reference to `demo.Model` in the bytecode of `Entry` defined by `child`; the JVM must perform class resolution in this context.

**7.** Why does `modelFoundByChild=true` not prove that `child` defined the class?

**Answer:** `child` can delegate to `parent` and receive the same `Class<?>` defined by `parent`.

**8.** If two independent loaders both define `demo.Model`, is comparing their two `getName()` values enough to know whether they are the same type?

**Answer:** No. You must check the defining loaders or compare `Class<?>` identity.

**9.** Does `getInitiatedClasses` contain hidden classes?

**Answer:** No, according to the Java 17 API.

**10.** Is an intermediate loader in a delegation chain automatically recorded as initiating?

**Answer:** Not by default. The JVMS explicitly states that intermediate loaders are not automatically initiating just because they are on the delegation path.

**11.** Can you add the initiated counts of `parent` and `child` together as the number of unique classes?

**Answer:** No. A single `Class<?>` can appear in multiple initiated sets.

**12.** If a class exists on the filesystem but the JVM has never been asked to load/resolve it, is the initiated set guaranteed to contain it?

**Answer:** No; classpath availability is different from an initiating record.

## 14. Inspection Tool Implementation Checklist

| Check | Meaning |
|---|---|
| Use `Instrumentation` from `premain`/`agentmain` | Valid API, no transformer needed |
| Record binary name **and** class identity | Do not conflate classes with the same name |
| Record defining loader via `getClassLoader()` | Avoid calling the initiated list "owned classes" |
| Record the queried initiating loader | Know which loader the table is describing |
| Support `null` for bootstrap | Do not report false errors |
| Inspect parent delegation and actual linkage | Explain why child initiates parent's classes |
| Do not automatically add all intermediate loaders | Comply with JVMS §5.3 |
| Do not use initiated count as class count | Avoid double counting |
| Combine with `getAllLoadedClasses` when inventory is needed | JVM-wide view |
| Note hidden/array exclusions | Know the API scope |
| Do not assume array order is chronological | Avoid wrong timeline inferences |
| Verify with explicit classloader experiments | Avoid errors from system loader accidentally seeing classes |
| Do not treat every `loadClass` call as a JVM initiating event | Maintain distinction between Java call and VM record |

## 15. Conclusion

- `getInitiatedClasses(loader)` returns classes that the JVM has **recorded `loader` as initiating**, not only classes **defined by `loader`**.
- The defining loader of a `Class<?>` is known via `clazz.getClassLoader()`. A class has **one defining loader** but may have **multiple initiating loaders**.
- With parent delegation, **`child` can initiate `demo.Model` even though `parent` defines this class**.
- The experiment proved `modelInitiatedChild=true` simultaneously with `modelDefinedChild=false` via **JVM bytecode linkage**.
- `getInitiatedClasses(null)` observes the bootstrap loader; `getAllLoadedClasses()` provides a broader inventory and includes hidden classes.
- An initiated set is not a JAR/classpath listing, not a timeline, and does not have the same meaning as module ownership.
- For accurate runtime analysis, always cross-check **class identity, defining loader, initiating loader, module, and observation time**.

## Official References

- Oracle JDK 17 — [`Instrumentation.getInitiatedClasses` and `getAllLoadedClasses`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html).
- Oracle Java SE 17 — [JVMS §5.3: Creation and Loading, defining/initiating loaders](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3).
- Oracle Java SE 17 — [JVMS §5.3.2: Loading Using a User-defined Class Loader](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.2).
- Oracle Java SE 17 — [JVMS §5.3.3: Creating Array Classes](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.3).
- Oracle Java SE 17 — [JVMS §5.3.4: Loading Constraints](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.4).
- Oracle JDK 17 — [`ClassLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html).
- Oracle JDK 17 — [`Class.getClassLoader()` and `Class.getModule()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html).
- Oracle JDK 17 — [Java agent package specification](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html).
