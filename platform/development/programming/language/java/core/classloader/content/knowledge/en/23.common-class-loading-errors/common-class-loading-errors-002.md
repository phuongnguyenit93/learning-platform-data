# NoClassDefFoundError Due to Missing Dependency Class or Wrong Name

## 1. What is NoClassDefFoundError?

`java.lang.NoClassDefFoundError` is a `LinkageError` that occurs when the JVM or a ClassLoader needs to define, link, or use a class but **cannot find the required definition in the runtime context**, even though the program or bytecode already has a dependency on that class. The message may indicate the missing class name, a name mismatch, or that the class **previously failed to initialize**.

In Java ClassLoader practice, two scenarios that are especially important to recognize are:

1. **Missing dependency class at runtime:** Class A is on the classpath, but when executing A, the JVM needs class B and B is not in the search path of the loader actually used to resolve the dependency.
2. **Wrong binary name of the class:** The loader is asked to define the name `demo.fake.Thing` from a file `demo/fake/Thing.class`, but the bytecode content declares `demo.real.Thing`; the JVM rejects the definition due to the mismatched name.

A typical message on OpenJDK/HotSpot 17:

~~~text
java.lang.NoClassDefFoundError: demo/dep/Helper
~~~

or:

~~~text
java.lang.NoClassDefFoundError: demo/fake/Thing (wrong name: demo/real/Thing)
~~~

These are **example message formats**, not a mandatory contract requiring every JDK/JVM to use the exact same punctuation and content. To diagnose accurately, read the **full stack trace**, nested causes (`Caused by`), and the actual ClassLoader configuration.

### Two Pieces of Information Not to Equate

- "Having the `X.class` file inside a JAR" **does not prove** that the loader resolving the dependency can see that file.
- "The filename on disk looks correct" **does not prove** that the binary name compiled **inside the bytecode** is also correct.

## 2. Distinguishing NoClassDefFoundError from ClassNotFoundException

| Aspect | `ClassNotFoundException` | `NoClassDefFoundError` |
|---|---|---|
| Error category | Checked `Exception` | `Error`, subclass of `LinkageError` |
| Common scenario | Code calls `Class.forName("pkg.Type")` or `loader.loadClass("pkg.Type")` but it is not found | The JVM needs a dependency class already referenced by bytecode, but cannot define/link that class |
| Typical handling | Can be caught and handled as an expected failed lookup | Usually a serious deployment/configuration error; must fix the runtime dependency or binary mismatch |
| Can it involve a class loader? | Yes | Yes |
| Can they appear together in a causal chain? | Yes | Yes |

An illustrative example:

~~~java
// Illustration, not a standalone program.
try {
    Class.forName("demo.dep.Helper");
} catch (ClassNotFoundException notFound) {
    System.out.println("Explicit lookup did not find Helper");
}
~~~

This is an **explicit** lookup by name; if not found, the `Class.forName` API typically reports `ClassNotFoundException`.

Whereas the following snippet is compiled when `Helper` is available:

~~~java
// Illustration: Feature is a class whose bytecode calls Helper.
System.out.println(Feature.message());
~~~

If at runtime `Helper.class` is no longer found by the loader, the JVM may throw `NoClassDefFoundError` when executing the instruction that needs to resolve `Helper`. There is no contradiction: **the code path and failure phase are different**.

`ClassNotFoundException` can also be the **cause** inside a `NoClassDefFoundError`, depending on the loader/JVM mechanism, but do not assume that cause is always present or always absent.

## 3. Why Does Compilation Succeed While Runtime Fails?

In practice, there are usually at least three different configurations:

~~~text
Compile-time classpath
  ├── lib.jar
  └── dep.jar       ← visible to javac

Runtime classpath / loader graph
  └── lib.jar       ← dep.jar is missing

Bytecode Feature.class
  └── symbolic reference to demo/dep/Helper
                   |
        JVM resolves when needed
                   |
       loader cannot find Helper
                   |
           NoClassDefFoundError
~~~

`javac` checks and records references to types/methods into bytecode based on compile-time dependencies. It **does not automatically package** all dependent JARs into the application's output class/JAR.

At runtime, the JVM uses the **runtime classpath/module path and the ClassLoader delegation at that time**. A class may be loaded successfully first, but when a dependent method or field is used for the first time, the resolution process requires another class and fails.

Therefore:

- `Compilation successful` does not mean `runtime dependencies complete`.
- The error can appear **late**, only when a code path is hit.
- Changing the JAR order or putting the right JAR into the wrong loader will not necessarily fix it.
- If a class has already been defined by a loader, replacing the file on disk does not cause the JVM to automatically reload the new version.

## 4. Java 17+ Example 1: Missing Dependency JAR at Runtime

The example consists of three layers:

1. `demo.dep.Helper` is in `dep.jar`.
2. `demo.lib.Feature` is in `lib.jar` and calls Helper.
3. `demo.host.App` is the entry point on the application classpath.

We compile properly with the full dependencies, then intentionally omit `dep.jar` from the runtime `-cp` to reproduce the error.

### 4.1. Directory Structure

~~~text
missing-dependency-demo/
├── dep-src/
│   └── demo/dep/Helper.java
├── lib-src/
│   └── demo/lib/Feature.java
└── host-src/
    └── demo/host/App.java
~~~

### 4.2. Helper.java File

Create **`dep-src/demo/dep/Helper.java`**:

~~~java
package demo.dep;

public final class Helper {
    private Helper() {
    }

    public static String value() {
        return "DEP_OK";
    }
}
~~~

### 4.3. Feature.java File

Create **`lib-src/demo/lib/Feature.java`**:

~~~java
package demo.lib;

import demo.dep.Helper;

public final class Feature {
    private Feature() {
    }

    public static String message() {
        return Helper.value();
    }
}
~~~

Class `Feature` has a **direct dependency inside its method body** on `demo.dep.Helper`. The `Feature.class` file compiles successfully, but when `message()` runs, the JVM needs to resolve class `Helper`.

### 4.4. App.java File

Create **`host-src/demo/host/App.java`**:

~~~java
package demo.host;

import demo.lib.Feature;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Start");

        try {
            System.out.println("Feature: " + Feature.message());
        } catch (NoClassDefFoundError failure) {
            System.out.println("Failure type: "
                    + failure.getClass().getSimpleName());
            System.out.println("Missing name: "
                    + failure.getMessage());
        }
    }
}
~~~

**Why catch `NoClassDefFoundError` here?** Only so the experiment prints short and deterministic output. Production code generally **should not catch it and continue operating** after a serious linkage error if the runtime dependency has not been fixed. In a real application, log the stack trace/cause and stop or isolate the failing plugin.

### 4.5. Compiling and Packaging JARs in Bash

Open a terminal in the `missing-dependency-demo/` directory, using JDK 17+:

~~~bash
mkdir -p build/dep build/lib build/host dist

javac -encoding UTF-8 -d build/dep \
  dep-src/demo/dep/Helper.java

jar --create --file dist/dep.jar -C build/dep .

javac -encoding UTF-8 -cp dist/dep.jar \
  -d build/lib lib-src/demo/lib/Feature.java

jar --create --file dist/lib.jar -C build/lib .

javac -encoding UTF-8 \
  -cp "dist/lib.jar:dist/dep.jar" \
  -d build/host host-src/demo/host/App.java
~~~

### 4.6. Compiling and Packaging JARs on Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force build/dep,build/lib,build/host,dist | Out-Null

javac -encoding UTF-8 -d build/dep dep-src/demo/dep/Helper.java

jar --create --file dist/dep.jar -C build/dep .

javac -encoding UTF-8 -cp dist/dep.jar -d build/lib lib-src/demo/lib/Feature.java

jar --create --file dist/lib.jar -C build/lib .

javac -encoding UTF-8 -cp "dist/lib.jar;dist/dep.jar" -d build/host host-src/demo/host/App.java
~~~

### 4.7. Running with Full Dependencies

**Linux/macOS/Git Bash:**

~~~bash
java -cp "build/host:dist/lib.jar:dist/dep.jar" demo.host.App
~~~

**Windows PowerShell:**

~~~powershell
java -cp "build/host;dist/lib.jar;dist/dep.jar" demo.host.App
~~~

Stdout:

~~~text
Start
Feature: DEP_OK
~~~

### 4.8. Omitting dep.jar from Runtime

**Linux/macOS/Git Bash:**

~~~bash
java -cp "build/host:dist/lib.jar" demo.host.App
~~~

**Windows PowerShell:**

~~~powershell
java -cp "build/host;dist/lib.jar" demo.host.App
~~~

Stdout on standard JDK 17:

~~~text
Start
Failure type: NoClassDefFoundError
Missing name: demo/dep/Helper
~~~

**Step-by-step explanation:**

1. The JVM locates and loads `App` from `build/host`.
2. `App` calls `Feature.message()`; `Feature` is in `dist/lib.jar`, so it is found.
3. The bytecode of `Feature.message()` calls `Helper.value()`, which requires class `demo.dep.Helper`.
4. The loader used to resolve that dependency cannot find `Helper` because `dep.jar` was omitted from the runtime classpath.
5. `NoClassDefFoundError` occurs **even though `Feature.class` is on the classpath and the application compiled successfully**.

### 4.9. How to Fix

Keep the code as is and add the **correct** `dep.jar` to the loader's runtime search path:

~~~bash
java -cp "build/host:dist/lib.jar:dist/dep.jar" demo.host.App
~~~

On Windows, use `;` instead of `:`. In applications packaged with Maven/Gradle, check the *runtime dependency graph*, transitive dependencies, scope/configuration, and the classpath of the exact process/test runner, not only the compile dependencies.

## 5. Java 17+ Example 2: Class Located at the Wrong Path Relative to Binary Name

Not every `NoClassDefFoundError` is a "missing file". The JVM verifies that the **requested class name** is consistent with the **binary name recorded in the class file**.

For example, the compiled class is:

~~~java
package demo.real;

public final class Thing {
}
~~~

The bytecode has the internal name `demo/real/Thing`. If you merely **copy or rename the file** to:

~~~text
build/wrong/demo/fake/Thing.class
~~~

and a ClassLoader then tries to define the name `demo.fake.Thing` from that file, the JVM sees:

~~~text
Requested name: demo/fake/Thing
Name in bytecode: demo/real/Thing
Result: NoClassDefFoundError (wrong name: ...)
~~~

Renaming the directory/file does not fix `package`/`this_class` in the bytecode. This is a common error when implementing `findClass` yourself, manually extracting JARs, copying bytecode, or getting the package wrong.

### 5.1. Structure

~~~text
wrong-name-demo/
├── thing-src/
│   └── demo/real/Thing.java
└── host-src/
    └── WrongNameProbe.java
~~~

Create **`thing-src/demo/real/Thing.java`**:

~~~java
package demo.real;

public final class Thing {
    public Thing() {
    }
}
~~~

Create **`host-src/WrongNameProbe.java`**:

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;

public final class WrongNameProbe {
    private WrongNameProbe() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: WrongNameProbe <wrong-class-root>");
        }

        Path root = Path.of(args[0]).toAbsolutePath().normalize();
        if (!Files.isDirectory(root)) {
            throw new IllegalArgumentException("Missing class root");
        }

        URL[] urls = {root.toUri().toURL()};
        try (URLClassLoader child = new URLClassLoader(
                urls, WrongNameProbe.class.getClassLoader())) {
            try {
                Class.forName("demo.fake.Thing", false, child);
                System.out.println("Wrong name detected: false");
            } catch (NoClassDefFoundError failure) {
                System.out.println("Error type: "
                        + failure.getClass().getSimpleName());
                System.out.println("Wrong name detected: "
                        + String.valueOf(failure.getMessage())
                                .contains("wrong name"));
            }
        }
    }
}
~~~

To focus on the wrong name, the host **does not place Thing.class on the application classpath** and only lets `URLClassLoader` read the `build/wrong` directory.

### 5.2. Bash: Compile and Intentionally Copy to the Wrong Location

~~~bash
mkdir -p build/real build/wrong/demo/fake build/host

javac -encoding UTF-8 -d build/real \
  thing-src/demo/real/Thing.java

javac -encoding UTF-8 -d build/host \
  host-src/WrongNameProbe.java

cp build/real/demo/real/Thing.class \
  build/wrong/demo/fake/Thing.class

java -cp build/host WrongNameProbe build/wrong
~~~

### 5.3. Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force build/real,build/wrong/demo/fake,build/host | Out-Null

javac -encoding UTF-8 -d build/real thing-src/demo/real/Thing.java

javac -encoding UTF-8 -d build/host host-src/WrongNameProbe.java

Copy-Item build/real/demo/real/Thing.class build/wrong/demo/fake/Thing.class

java -cp build/host WrongNameProbe build/wrong
~~~

Stdout on OpenJDK/HotSpot 17:

~~~text
Error type: NoClassDefFoundError
Wrong name detected: true
~~~

`WrongNameProbe` prints a boolean instead of the full `getMessage()`, because the error message format can vary across JVMs. On HotSpot, the message portion typically contains `wrong name: demo/real/Thing`.

**Proper fix:** Keep `Thing.class` at `demo/real/Thing.class` and request `demo.real.Thing`; or change `package demo.real;` to `package demo.fake;` **in the source**, recompile, and store the output at `demo/fake/Thing.class`. Do not fix it merely by renaming the `.class` file.

## 6. How ClassNotFoundException Differs from "wrong name"

With the same `WrongNameProbe` above, if the child loader cannot find the `demo/fake/Thing.class` file in the first place, `Class.forName("demo.fake.Thing", false, child)` typically throws **`ClassNotFoundException`**.

However, when the loader **finds the file on a valid search path**, and then the JVM discovers that the class name in the bytecode does not match the requested name, the result can be **`NoClassDefFoundError` with "wrong name"**.

~~~text
No URL / bytes found for the requested name
    → ClassNotFoundException (lookup failure)

Bytes found, but the class file declares a different binary name
    → NoClassDefFoundError (wrong name)

Bytes found, matching name, but invalid class file content
    → May be ClassFormatError or a corresponding linkage error
~~~

A custom loader should read the bytes corresponding to the exact binary name and then call `defineClass(name, bytes, 0, length)`. If bytes of a different class are passed, the JVM can detect a name mismatch.

For the module path, named module package ownership also affects class lookup; do not infer from seeing a class file inside a modular JAR that any loader/module is allowed to use it.

## 7. Other Common Causes of NoClassDefFoundError

Although this article focuses on missing dependencies and wrong names, you need to recognize the variants to avoid misdiagnosis:

| Symptom | Possible Cause | What to Check |
|---|---|---|
| `NoClassDefFoundError: pkg/Dependency` | Dependency missing from the runtime classpath/module path, or not visible from the loader | Runtime dependency graph and loader topology |
| `NoClassDefFoundError: pkg/X (wrong name: pkg/Y)` | `.class` placed at the wrong package path; custom loader defines the wrong name | `package`, internal binary name, JAR entry |
| `NoClassDefFoundError: Could not initialize class ...` | The class previously failed to initialize, and subsequent usage sees the class in an erroneous state | Find the first static initialization exception |
| `NoClassDefFoundError` after plugin reload | Old loader is closed or dependency/version has changed; requests are still using the old generation | In-flight tasks, lifecycle/leases, `close()` |
| `NoClassDefFoundError` only on server/test | Compile/test classpath differs from actual runtime; the class resides in another loader | Container-specific loaders, packaging, launcher |
| `NoClassDefFoundError` with a class name different from the one the code is calling | The direct class is present, but a deeper dependency is missing | Cause chain and the class actually being resolved |

Do not fix it by **catching every `NoClassDefFoundError` and continuing**. If an application is missing a runtime dependency, the error may reappear on another code path. If class initialization breaks, the JVM mechanism does not "retry the static initializer" just because code caught the error.

## 8. Do Not Confuse a Missing Class with a Class That Failed Initialization

A class whose `static` initializer throws an exception can transition to the **erroneous** state. On the first active use, the JVM typically throws `ExceptionInInitializerError` (if the initializer throws a non-`Error`); subsequent attempts that require initializing the **same runtime class** typically throw `NoClassDefFoundError: Could not initialize class ...`. In this case, **the bytecode and JAR may still exist intact**.

Key diagnostic clues are the *Could not initialize class* message, the `<clinit>`/first exception record, and superclass initialization relationships. Merely fixing the JAR file or `java.class.path` does not reset an erroneous class inside a live loader.

The separate article **NoClassDefFoundError After Class Initialization Failure** includes a Java 17+ lab reproducing first failure → repeat failure, distinguishing `Class.forName(..., false, loader)` from initialization, and testing a new loader after fixing the configuration. The current article focuses on **missing dependencies and files carrying the wrong binary name**, which require different fixes.

## 9. Binary Name and Class Path Rules

In Java:

~~~java
package demo.real;

public class Thing {
}
~~~

The binary name is `demo.real.Thing`. In a standard classpath directory/JAR, the corresponding entry is:

~~~text
demo/real/Thing.class
~~~

In bytecode, the constant pool and `this_class` use the internal form with slashes, for example `demo/real/Thing`. Placing the file at `demo/fake/Thing.class` does not change this metadata.

Common types of name mismatches:

- Changing the directory or `.class` file without recompiling the `package`.
- The loader uses `name.replace('.', '/')` incorrectly or strips off a prefix.
- A bytecode class generator sets `this_class` incorrectly for the requested name.
- Passing a class byte array to `defineClass(otherName, bytes, ...)`.
- Mistaking a nested class name such as `Outer$Inner` for `Outer.Inner` in an API that expects a binary name.
- Mixing up case-sensitive package/class names across OSes with different filename handling.

A nested class example: source `demo.Outer.Inner` can have the binary name `demo.Outer$Inner`, so the lookup name via reflection is typically `demo.Outer$Inner`. This is **not** a reason to edit filenames manually; use `javac`, the proper output root, and `Class.getName()` to verify.

## 10. Step-by-Step Diagnosis: At Which Step Did It Fail?

When encountering `NoClassDefFoundError`, follow this sequence:

1. **Obtain the full stack trace** of the first failure, including `Caused by` and suppressed exceptions if present.
2. **Read the name after the colon:** Is it a dependency name like `demo/dep/Helper`, a `wrong name` message, or `Could not initialize class`?
3. **Identify the timing:** Does it fail when launching the main class, calling a method, creating a plugin instance, opening ServiceLoader, or after a reload?
4. **Inspect the runtime launcher:** `java -cp`, `--module-path`, scripts, container classpath, environment, dependency scopes.
5. **Inspect the actual source:** Which JAR contains the exact entry, and which loader is used to resolve the class?
6. **Cross-check class identity:** `getClassLoader()` for loaded classes; parent-first/child-first and module mapping.
7. **If "wrong name":** Compare the requested name, the JAR entry/path, and `this_class` inside the bytecode.
8. **If "Could not initialize class":** Trace the first static initialization failure.
9. **Recover and verify:** Rerun with the fixed runtime classpath or package mapping; do not fix only the compile classpath.

Do not automatically take the current class via `SomeClass.class.getClassLoader()` and conclude that all application dependencies reside in that loader: frameworks/plugins can create multiple defining loaders with different delegations.

## 11. Commands to Inspect JARs and Bytecode

For the missing dependency example:

~~~bash
jar --list --file dist/lib.jar
jar --list --file dist/dep.jar
~~~

`lib.jar` needs to contain `demo/lib/Feature.class`, while `dep.jar` contains `demo/dep/Helper.class`.

Use `javap` to read the compiled bytecode:

~~~bash
javap -c -classpath dist/lib.jar demo.lib.Feature
~~~

You can see the call referencing `demo/dep/Helper.value` in the disassembly. This `javap` command does not prove that Helper is available at runtime; it only shows the symbolic reference recorded in the bytecode.

For wrong name:

~~~bash
javap -verbose -classpath build/real demo.real.Thing
~~~

In the output, there is metadata regarding `this_class` and the internal name `demo/real/Thing`. Compare it against the entry you defined at `build/wrong/demo/fake/Thing.class`.

Observing class loading on Java 17:

~~~bash
java -Xlog:class+load=info \
  -cp "build/host:dist/lib.jar:dist/dep.jar" demo.host.App
~~~

The log lines emitted by the JVM can be numerous, contain machine-specific paths, and do not produce deterministic output like the demo stdout. They are useful when you need to know from which source a class was **actually** loaded by the JVM, though they should be combined with the stack trace and classloader configuration.

On Windows, the `-cp` separator is `;`. The `javap -verbose` command has verbose and JDK-dependent output, so do not treat it as part of the expected stdout.

## 12. NoClassDefFoundError in Multi-ClassLoader Systems

A plugin host can create a child loader:

~~~java
// Illustrative code, not a standalone program.
URLClassLoader child =
        new URLClassLoader(pluginUrls, apiParentLoader);
Class<?> provider = child.loadClass("demo.plugin.PluginImpl");
~~~

`PluginImpl` is defined by the child but depends on `demo.dep.Helper`. The classloader that resolves those references must have an appropriate search path for Helper; if Helper only resides in **a sibling loader that is not delegated to**, it can still fail even though the JVM has already loaded Helper in another loader.

### Key Points to Remember

- **A child sees its parent** under the default parent-first model; **a parent does not automatically search the child's own classes**.
- **Sibling loaders** do not automatically see one another.
- Two loaders defining the same FQCN create distinct runtime classes; this can also cause `ClassCastException` / loader constraint `LinkageError`.
- Adding the JAR to **another loader's classpath** is not guaranteed to fix the error in the resolving loader.
- With `URLClassLoader.close()`, already-loaded classes remain, but the closed loader's source for finding new classes is no longer available.
- With JPMS named modules, module readability, loader mapping, and exports/opens are additional constraints; do not infer from a class existing inside a module JAR that every loader can find it.

A stable design approach: place the shared API in the parent, place the plugin's implementation and runtime dependencies on the plugin loader's search path or in the parent according to compatibility policy, and manage the generation lifecycle explicitly.

## 13. Common Mistakes When Fixing

| Incorrect Fix | Why It Is Insufficient/Incorrect | Replace With |
|---|---|---|
| "The `Feature.class` file is present, so what could be missing?" | Feature depends on Helper during runtime resolution | Inspect the entire dependency graph |
| Fixing only the compile classpath | `java` still runs with a different classpath | Fix the actual runtime classpath/module path |
| Adding dep.jar to an arbitrary directory | The loader does not automatically scan every directory | Place the dependency into the right loader URL/launcher |
| Renaming `Thing.class` or the directory manually | The bytecode still declares the old binary name | Fix `package` and recompile |
| Catching `NoClassDefFoundError` and continuing | The linkage error can recur | Fix packaging/configuration or isolate the plugin |
| Looking only at the last exception | The first initialization failure may be masked | Check the log from the first failure and `Caused by` |
| Closing the loader immediately after plugin cutover | Older requests may still need classes/resources | Drain in-flight tasks, then close |
| Placing a dependency in a sibling loader and expecting automatic visibility | There is no default delegation between siblings | Design parent/delegation properly |
| Relying on wildcard classpath ordering | Expansion order of `lib/*` is not guaranteed to be stable | Remove duplicates and lock dependencies |
| Relying on the class name alone | Runtime identity also includes the defining loader | Inspect `Class.getClassLoader()` |

## 14. Production Error Recovery Checklist

**Upon receiving an error:**

1. Capture the full stack trace and the version/runtime launch command.
2. Identify the failing class name and the keyword `wrong name` or `Could not initialize class`.
3. Verify JAR packaging with `jar --list` and bytecode with `javap`.
4. Check compile-time vs. runtime dependency scopes.
5. Identify the caller's defining loader and the actual loader graph.
6. Verify that no dependency was improperly excluded/shaded and that there are no conflicting transitive versions.
7. Fix packaging; rebuild reproducibly, and test using the exact production command.
8. If plugin hot reload is used, inspect old/new generations, in-flight requests, and `close()` timing.
9. If it is an initialization failure, fix the root cause in the static initializer instead of merely adding JARs.
10. Add an integration test that launches with the **exact runtime artifacts** to catch errors before release.

In Maven/Gradle, use dependency-insight/dependency-tree and runtime classpath reporting to detect missing dependencies or duplicate versions. Do not force every error into a "missing library" explanation when the message already indicates a name mismatch or initialization failure.

## 15. Self-Check Questions

**Question 1.** `App` and `Feature` are on the runtime classpath, while `Helper` was only available at compile time. Which error is likely to occur when calling `Feature.message()`?

**Answer:** `NoClassDefFoundError` for `demo/dep/Helper` when the JVM needs to resolve the dependency and cannot find the class.

**Question 2.** When calling `Class.forName("demo.dep.Helper")` directly and the class is not found, which error is typically thrown?

**Answer:** `ClassNotFoundException` (a checked exception), which differs from the bytecode resolution error path.

**Question 3.** Does renaming the file `demo/real/Thing.class` to `demo/fake/Thing.class` also change the binary name?

**Answer:** No. The name inside the bytecode remains `demo/real/Thing`; if a loader attempts to define the name `demo.fake.Thing`, `NoClassDefFoundError (wrong name)` can occur.

**Question 4.** Why must you check the runtime classpath instead of only `javac -cp`?

**Answer:** Compile-time dependencies do not automatically appear at runtime; the JVM loads classes using the runtime loader's search path.

**Question 5.** The first use of a class fails in the static initializer, and the next attempt reports `NoClassDefFoundError`. Does that necessarily mean a JAR is missing?

**Answer:** No. The class may have been marked as initialization failed; you must trace the first exception.

**Question 6.** `Helper` is located in a sibling loader of the plugin, but the plugin does not delegate to it. Is finding Helper when listing all JARs across the JVM enough?

**Answer:** No. The loader used to resolve the dependency must actually have a search path to the appropriate class.

**Question 7.** Should you catch `NoClassDefFoundError` and continue in order to "self-recover" in production?

**Answer:** Usually no. You should fix the dependency/name mismatch or isolate/disable the failing plugin under a clear policy, rather than ignoring linkage errors.

## 16. Official References

- [Java SE 17 — NoClassDefFoundError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html): meaning of the error when the JVM/ClassLoader needs to define a class but cannot find an appropriate definition.
- [Java SE 17 — ClassNotFoundException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassNotFoundException.html): explicit class lookup error.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): delegation, `loadClass`, `findClass`, and `defineClass`.
- [Java SE 17 — ExceptionInInitializerError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ExceptionInInitializerError.html): static initialization error.
- [Java Virtual Machine Specification 17, Chapter 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): loading, linking, initialization, and loading constraints.
- [Java SE 17 — Java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): runtime `--class-path`, module path, and class loading logs.

**Key takeaway:** `NoClassDefFoundError` does not have just one cause. For a **missing dependency** error, compare the runtime loader/classpath against which class the bytecode requires. For **wrong name**, cross-check the package, file path, and binary name inside `.class`, then recompile properly. Always distinguish it from `ClassNotFoundException` from an explicit lookup and `NoClassDefFoundError` occurring **after a class initialization failure**.
