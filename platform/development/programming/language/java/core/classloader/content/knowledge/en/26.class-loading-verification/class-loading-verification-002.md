# Verifying Delegation Order and Class Identity in Java

If a class named `sample.Widget` appears in **both the parent directory and the child directory**, which version will Java load? If two class loaders both load `sample.Widget` from the same bytecode file, are the two results **the same `Class<?>`**? Why can two objects with the same class name still cause a `ClassCastException`?

These are three different questions:

1. **Delegation order:** when a loader receives a request to load a class, does it prioritize asking the **parent** first or searching its own source first?
2. **Defining loader:** **which loader actually defines** the class via JVM behavior such as `defineClass` or a built-in mechanism?
3. **Runtime class identity:** a class is not identified solely by its binary name; according to the JVMS, type identity is bound to the **pair (binary name, defining class loader)**.

Within Java core – classloader, under the **Behavior Verification** group, this article guides verification with **empirical evidence**, rather than just guessing from the classpath. We build **two versions with the same binary name**, one default parent-first loader, and two loaders that adopt scoped child-first; print the method origin, the defining loader, compare `Class<?>` with `==`, and attempt a cast across the two namespaces. The example runs on **JDK 17+**, includes compilation commands, stdout verified against actual execution results, and an analysis of common design mistakes.

## 1. Delegation Rules to Verify

`ClassLoader.loadClass(name)` typically checks `findLoadedClass`, asks the parent, and only then calls `findClass` on the current loader. Therefore, **parent-first** can return the `sample.Widget` version from the parent, even when the child has a file with the same name. This is the default behavior of `URLClassLoader` and `ClassLoader.loadClass`, **not a mandatory requirement for every custom loader**.

This article directly compares parent-first with a **child-first scoped to the `sample.` namespace**, instead of reversing priority for `java.*` classes or the host's shared API. How to organize two JARs with the same name from scratch was illustrated in the previous fixture article.

## 2. Defining Loader and Initiating Loader Are Not Always the Same

Two concepts according to the JVMS:

- **Defining loader:** the loader that **actually defined** the class. Runtime type identity uses the defining loader.
- **Initiating loader:** the loader that **initiates** loading the class; it may define the class itself or delegate to another loader. The JVM can record a loader as an initiating loader of a class that it did not define.

Example:

```text
Child.loadClass("sample.Widget")
            |
            v
      Parent.loadClass(...)
            |
            v
      Parent defines Widget
            |
            v
      Return Class<Widget> to Child
```

Child may be recorded as an initiating loader, **but** `Widget.class.getClassLoader()` returns **Parent** because Parent is the defining loader.

This explains why:

```java
Class<?> result = child.loadClass("sample.Widget");
System.out.println(result.getClassLoader() == child);
```

can print `false` even though **child itself received the request**. The snippet above is an illustration inside a method, assuming `child` is already available and exceptions are handled.

An easily overlooked detail: `ClassLoader.findLoadedClass(name)` does not merely search for classes that the loader **defined itself**; according to the Java 17 API, it finds a class for which the JVM has recorded this loader as an **initiating loader**. That is why `findLoadedClass` is used to prevent duplicate definitions in custom implementations, yet you must not infer that every result it returns was defined by this loader.

## 3. Class Identity When Changing Delegation Policy

The JVM distinguishes types by **(binary name, defining loader)**. If `sample.Widget` is defined by the parent and returned by the child after delegation, `child.loadClass(...).getClassLoader()` is **parent**. If a custom child-first loader actually defines a version with the same name, the two `Class<?>` instances are different even though they have the same `getName()`; `Class.isInstance` and `Class.cast` show that they are not interchangeable.

A package name as a string is also not enough to make two classes belong to the same **runtime package**: different defining loaders can change access control for package-private. A separate article on **Verifying package-private when using two loaders** has an `IllegalAccessError` experiment.

## 4. Creating the Experiment: Parent and Child Have Classes with the Same Name and Different Bytecode

We write:

**Parent version:**

```java
package sample;

public class Widget {
    public String origin() {
        return "PARENT";
    }
}
```

**Child version:**

```java
package sample;

public class Widget {
    public String origin() {
        return "CHILD";
    }
}
```

Both have the same binary name `sample.Widget` and the same public method `origin():String`, but the method bodies intentionally return different values so we can **observe which class is executed**.

Do not compile the two files above in the **same source directory** because that will cause a duplicate class definition. We compile parent and child separately into two output directories, and then the host creates loaders using `URLClassLoader`.

### Project structure

```text
delegation-lab/
├── src-parent/
│   └── sample/
│       └── Widget.java          # returns "PARENT"
├── src-child/
│   └── sample/
│       └── Widget.java          # returns "CHILD"
├── src-host/
│   └── VerifyDelegation.java
├── parent-classes/              # separate output for parent
├── child-classes/               # separate output for child
└── host-classes/                # output for application host
```

Create the three output directories before running the commands. The host **does not directly import `sample.Widget`**, so it can be compiled independently of both versions. When running, only put `host-classes` on the application classpath; if you add the parent/child output to the host's `-cp`, the result may change because the system loader defines the class first.

## 5. Host Creating a Default Loader and a Scoped Child-First Loader

File `src-host/VerifyDelegation.java` (standalone, compilable with JDK 17+):

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class VerifyDelegation {

    static final class SelectiveChildFirst extends URLClassLoader {
        SelectiveChildFirst(
                String name, URL[] urls, ClassLoader parent) {
            super(name, urls, parent);
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {

            // Only reverse the order for the namespace the application actively owns.
            if (!name.startsWith("sample.")) {
                return super.loadClass(name, resolve);
            }

            synchronized (getClassLoadingLock(name)) {
                Class<?> c = findLoadedClass(name);

                if (c == null) {
                    try {
                        c = findClass(name);       // Child tries first.
                    } catch (ClassNotFoundException missing) {
                        c = super.loadClass(name, false); // Fallback.
                    }
                }

                if (resolve) {
                    resolveClass(c);
                }
                return c;
            }
        }
    }

    static Object create(Class<?> type) throws Exception {
        return type.getConstructor().newInstance();
    }

    static String origin(Class<?> type, Object instance)
            throws Exception {
        return (String) type.getMethod("origin").invoke(instance);
    }

    public static void main(String[] args) throws Exception {
        URL[] parentUrls = {
            Path.of("parent-classes").toUri().toURL()
        };
        URL[] childUrls = {
            Path.of("child-classes").toUri().toURL()
        };

        try (URLClassLoader parent = new URLClassLoader(
                     "parent", parentUrls,
                     ClassLoader.getPlatformClassLoader());

             URLClassLoader normal = new URLClassLoader(
                     "normal", childUrls, parent);

             SelectiveChildFirst first = new SelectiveChildFirst(
                     "child-first-A", childUrls, parent);

             SelectiveChildFirst second = new SelectiveChildFirst(
                     "child-first-B", childUrls, parent)) {

            Class<?> p = parent.loadClass("sample.Widget");
            Class<?> n = normal.loadClass("sample.Widget");
            Class<?> a = first.loadClass("sample.Widget");
            Class<?> b = second.loadClass("sample.Widget");

            System.out.println("normal chose parent=" + (n == p));
            System.out.println("normal defining loader="
                    + n.getClassLoader().getName());
            System.out.println("normal origin="
                    + origin(n, create(n)));

            System.out.println("child-first chose child=" + (a != p));
            System.out.println("child-first defining loader="
                    + a.getClassLoader().getName());
            System.out.println("child-first origin="
                    + origin(a, create(a)));

            System.out.println("same binary name="
                    + a.getName().equals(b.getName()));
            System.out.println("distinct Class objects=" + (a != b));

            System.out.println("repeat stable="
                    + (first.loadClass("sample.Widget") == a));

            System.out.println("bootstrap String="
                    + (first.loadClass("java.lang.String")
                        == String.class));

            try {
                a.cast(create(b));
                System.out.println("unexpected cast success");
            } catch (ClassCastException expected) {
                System.out.println("cross-loader cast="
                        + expected.getClass().getSimpleName());
            }
        }
    }
}
```

Read the decisions carefully:

- `parent` has URLs pointing to `parent-classes` and its parent is the **platform loader**.
- `normal` has URLs pointing to `child-classes`, but **parent = parent loader**. This is an ordinary `URLClassLoader` that does not override `loadClass`, so its behavior is parent-first.
- `first` and `second` both use the bytes in `child-classes`, yet they are **two independent loader objects**, each instance having its own name.
- `SelectiveChildFirst` only reverses the order for binary names starting with `sample.`. Names outside that namespace, including `java.lang.String`, still go through default parent-first.
- `findLoadedClass` checks before redefining, preventing duplicate definitions of `sample.Widget` within the same initiating namespace.
- `getClassLoadingLock(name)` protects the load path when multiple threads request the same class. Java ClassLoader has synchronization/parallel-capable constraints; this snippet serves as a demo and **should not automatically be treated as a fully production-safe parallel loader**.
- `findClass` is tried **before** the parent for `sample.`; only when the child does not have the file is `super.loadClass(name, false)` called.
- `resolveClass(c)` is called when `resolve` is requested; this method does not run the `static initializer` like `Class.forName(name, true, loader)`.

**Note on fallback:** do not wrap `LinkageError`/`ClassFormatError`/`SecurityException` in a catch block and silently try the parent. The demo only catches `ClassNotFoundException`, because **the file not existing in the child** is a valid fallback scenario; corrupted bytes, a wrong package, a mismatched name, or problematic bytecode are errors that need to be handled, not “treating it as if the child does not have the class”.

## 6. Compiling and Running

From the `delegation-lab` directory:

```bash
javac --release 17 -d parent-classes src-parent/sample/Widget.java
javac --release 17 -d child-classes src-child/sample/Widget.java
javac --release 17 -d host-classes src-host/VerifyDelegation.java
java -cp host-classes VerifyDelegation
```

The commands do not contain multiple classpath entries, so they are the same on Windows/Linux/macOS.

Stdout **verified after compiling with `javac --release 17` and running the JVM**:

```text
normal chose parent=true
normal defining loader=parent
normal origin=PARENT
child-first chose child=true
child-first defining loader=child-first-A
child-first origin=CHILD
same binary name=true
distinct Class objects=true
repeat stable=true
bootstrap String=true
cross-loader cast=ClassCastException
```

This result is **not guesswork**: the host was compiled independently, the parent and child classes were compiled into two different outputs, the JVM was run, and the stdout matched.

### Experiment A: parent-first chooses the parent's class

```text
normal.loadClass("sample.Widget")
      |
      +-- parent.loadClass(...) -> sample.Widget from parent-classes
      |
      +-- normal.findClass(...) DOES NOT NEED TO BE CALLED
```

The lines:

```text
normal chose parent=true
normal defining loader=parent
normal origin=PARENT
```

prove that `normal.loadClass` returns **the exact `Class<?>` defined by the parent**. The parent loader points to code returning `PARENT`, even though the child also has a `sample.Widget.class` returning `CHILD`.

**Do not say normal “loads both versions and then picks the parent's version”.** It returns the class that the parent found, without needing to define the child version itself.

### Experiment B: child-first chooses the child's class

```text
first.loadClass("sample.Widget")
      |
      +-- first.findLoadedClass(...) -> null the first time
      |
      +-- first.findClass(...) -> sample.Widget from child-classes
      |
      +-- no need to fall back to parent
```

The lines:

```text
child-first chose child=true
child-first defining loader=child-first-A
child-first origin=CHILD
```

prove that `first` defines `sample.Widget` itself even though the parent has a class with the same name.

### Experiment C: two independent child-first loaders define two types

```text
first  -> sample.Widget (child-first-A)
second -> sample.Widget (child-first-B)

getName() are both "sample.Widget"
Class<?> identities differ
```

The lines:

```text
same binary name=true
distinct Class objects=true
```

provide **direct evidence** of JVMS runtime identity. **The same `child-classes` path and the same class-file bytes** do not merge two classes that were defined by two different loaders.

### Experiment D: caching/stability within the same loader

```text
repeat stable=true
```

The second time, `first.loadClass("sample.Widget")` returns **the same `Class<?>`**. A properly functioning loader must not arbitrarily keep defining a new class with the same binary name in the same namespace; the JVM enforces constraints and can throw `LinkageError: attempted duplicate class definition` if a subclass makes a duplicate `defineClass` call.

### Experiment E: not reversing the order for platform classes

```text
bootstrap String=true
```

Because the child-first policy applies only to `sample.`, `java.lang.String` uses default delegation. `String.class` is normally defined by the bootstrap loader, and `Class.getClassLoader()` for a bootstrap-defined class is represented as `null`.

This line **does not prove that every platform loader is always parent-first**; it proves that **the policy written in the example** avoids defining `java.*` itself or interfering with foundational classes.

### Experiment F: cross-casting leads to an error

```text
cross-loader cast=ClassCastException
```

In the demo, `a` is `sample.Widget` defined by loader A; the object `create(b)` belongs to `sample.Widget` defined by loader B. `a.cast(objectOfB)` throws `ClassCastException` even though the class names are identical at the source level. This is a **type identity** error, not a misspelled class name.

**Do not fix this by casting through `Object` and casting back**; the object still belongs to loader B's type. Communication must go through a shared contract/interface, or data must be serialized across an appropriate DTO/API boundary.

## 7. Stronger Evidence: Class Object, Loader, CodeSource, and Resource

A complete verification method includes:

| Observation | API/Command | Helps Confirm |
| --- | --- | --- |
| Binary class name | `clazz.getName()` | Whether two classes have the same name |
| Defining loader | `clazz.getClassLoader()` | **Who defines** the runtime class |
| Loader name | `clazz.getClassLoader().getName()` | Identifying a named loader (not a unique ID) |
| Class identity | `clazzA == clazzB` | Whether two references refer to the same `Class<?>` object |
| Object/type identity | `clazzA.isInstance(objectB)`, `clazzA.cast(objectB)` | Instance of type A or B |
| Origin behavior | Reflectively invoke `origin()` | Whether the selected bytecode runs the parent or child version |
| Parent chain | `loader.getParent()` | Delegation relationship, **not inheritance** |
| Code source | `clazz.getProtectionDomain().getCodeSource()` | Where the class binary may come from (if provided by the runtime) |
| JVM class load | `-Xlog:class+load=info` on HotSpot | Load log line, and loader/source when available |
| Loader hierarchy | `jcmd PID VM.classloaders` | Parent tree in an actual running JVM |

In the example, `getClassLoader().getName()` is easy to observe because the constructors assign the names `parent`/`child-first-A`/`child-first-B`. However, **a loader's name is not a global unique identifier**: two `URLClassLoader` instances can be given the same name. To know whether it is truly the same loader, compare the loader's **object identity** using `==`.

### Printing CodeSource When Investigating JAR Precedence

An illustrative code snippet:

```java
Class<?> type = first.loadClass("sample.Widget");

java.security.ProtectionDomain pd = type.getProtectionDomain();
java.security.CodeSource source =
        pd == null ? null : pd.getCodeSource();

System.out.println(
        source == null ? "<unknown>" : source.getLocation());
```

This is **not a standalone compilable file**; it assumes `first` has already been created and the method handles `ClassNotFoundException`. For an ordinary URLClassLoader, the location may be the file URL of `child-classes`; for the bootstrap loader, a byte-array loader, generated classes, or some custom loaders, CodeSource can be `null`.

**Do not infer from a URL path alone that the class was loaded:** resource `getResource("sample/Widget.class")` can read the file from a URL, while class resolution can delegate and select another loader's class.

## 8. Switching Parent-First to Child-First in Real Applications: When Should You Do It?

Child-first can be useful when a plugin needs to use its own implementation dependency version, for example two plugins simultaneously using two versions of a JSON library. However, **do not make every package child-first**.

Common design:

```text
Host/System loader
  +-- api.Plugin
  +-- api.Message
  +-- shared interfaces, DTOs and framework contracts
          ^
          | parent-first (required to unify shared API identity)
          |
Plugin loader A
  +-- plugin.impl.*
  +-- private dependencies version A
          ^
          |
Plugin loader B
  +-- plugin.impl.*
  +-- private dependencies version B
```

In the proper model:

- **`java.*` and platform API:** let the runtime/platform loader handle them; do not attempt to define them yourself.
- **`api.*` shared contracts:** parent-first so that the host and plugins receive **a single `Class<?>`**.
- **`plugin.*` or private namespace:** scoped child-first can be applied to prevent the parent from shadowing the plugin's class versions.
- **Native libraries/JNI:** have their own lifecycle/loader restrictions; child-first does not automatically isolate native state within the same process.
- **JPMS named modules:** module resolution and exports/opens/readability must also be considered; merely reversing classpath search does not bypass JPMS access controls.
- **Security:** classloader isolation is **not a sandbox** sufficient to run untrusted bytecode.

If the parent has already defined `api.Plugin` and the child defines `api.Plugin` itself via child-first, the child's implementation object may **fail to cast** to the host's interface despite having the same fully qualified name. Therefore, the child-first allowlist must exclude the shared API namespace.

## 9. What Does a Safe Custom Loader Need to Watch Out For?

In the `SelectiveChildFirst` example, the critical section:

```java
synchronized (getClassLoadingLock(name)) {
    Class<?> result = findLoadedClass(name);
    if (result == null) {
        try {
            result = findClass(name);
        } catch (ClassNotFoundException missing) {
            result = super.loadClass(name, false);
        }
    }
    if (resolve) resolveClass(result);
    return result;
}
```

This is an **excerpt** from the file `VerifyDelegation.java`, not a standalone program.

Design requirements:

1. **Avoid duplicate definitions:** check `findLoadedClass` before calling `findClass`/`defineClass`.
2. **Use locking properly:** `getClassLoadingLock(name)` relates to concurrency; pay attention to `registerAsParallelCapable` if you want a parallel-capable loader and understand the JVM constraints for the loader hierarchy.
3. **Do not child-first `java.*`:** a loader must not self-define classes belonging to the restricted `java.*` package, and doing so can create serious conflicts with platform classes.
4. **Keep shared APIs parent-first:** avoid creating two runtime interfaces with the same name.
5. **Fall back only when the class is not found:** do not swallow `LinkageError`/`SecurityException` and silently use the wrong version from the parent.
6. **Preserve the same Class object for the same binary name within the same loader:** do not define duplicates within a single loader.
7. **Manage `Package`:** a custom loader using `defineClass` must respect protection domains, package definition/sealing, and classloader constraints.
8. **Manage lifecycle:** `URLClassLoader.close()` does not immediately unload classes; avoid closing while tasks are still lazy-loading classes/resources.
9. **Keep debugging information:** set the loader name, and log the binary name, selected defining loader, and source when appropriate.
10. **Audit class dependencies:** a type defined by the child may depend on classes defined by the parent, so loader constraints and version compatibility must be ensured.

### About resolveClass

`resolveClass(c)` **links** the class as defined by the ClassLoader API; it does not guarantee that every referenced class has been resolved or that static initializers have run in the order the application assumes. Do not arbitrarily replace `resolveClass` with a call to `Class.forName(name, true, loader)` inside a `loadClass` override, because doing so changes initialization timing and easily introduces recursion/side effects.

### About Name Mismatch Errors

If a custom loader reads bytes itself and calls:

```java
defineClass("sample.Widget", bytes, 0, bytes.length);
```

then the bytes must represent a class with a matching binary name. If they contain `sample.Other` or an invalid package, the JVM may throw `NoClassDefFoundError`/a linkage error. With `URLClassLoader.findClass` in the demo, Java handles file lookup and definition according to URL source rules.

## 10. Resource Lookup Needs a Separate Test

`loadClass` resolves a single runtime class; `getResource` and `getResources` locate one or more resource URLs, whereas `META-INF/services` may contain multiple provider descriptors. Custom child-first class lookup **does not automatically change** resource lookup policy unless the relevant methods are overridden. The article on resources/SPI practices the full lookup and instantiation chain; here we draw conclusions only about class identity from `loadClass`.

## 11. How to Verify Class Identity Yourself Using Reflection

In the main example:

```java
Class<?> a = first.loadClass("sample.Widget");
Class<?> b = second.loadClass("sample.Widget");

System.out.println(a.getName());
System.out.println(b.getName());
System.out.println(a == b);
System.out.println(a.getClassLoader() == b.getClassLoader());
```

This is an **illustrative snippet** to add to the `main` method when `first`/`second` exist. Expected output:

```text
sample.Widget
sample.Widget
false
false
```

Comparison:

- `getName()` only checks binary names.
- `==` compares `Class<?>` objects for true runtime identity.
- `getClassLoader()` compares defining-loader identity.
- `Class.getModule()` also adds a Java 9+ perspective on named/unnamed modules, but module name does not replace the JVM pair of binary name + defining loader.

### ClassCastException and Reflection

```java
Object fromB = b.getConstructor().newInstance();
System.out.println(a.isInstance(fromB));
Object fromA = a.cast(fromB);
```

The illustrative snippet above will print `false` and then throw `ClassCastException`, so the `Object fromA = ...` line does not complete. It is not because the constructor returned the wrong object, but because A and B are **two separate runtime types**.

If the host needs to communicate with two plugin implementations, define an `api.Plugin` interface in the parent and have both child classes implement **that exact parent interface**. The host can then cast to `api.Plugin` without requiring the two implementation classes to be identical.

## 12. Specifying the Loader Explicitly During Reflection

`Class.forName(name, false, loader)` allows choosing a specific loader when looking up a type without requiring initialization. Changing the Thread Context ClassLoader (TCCL) **does not automatically change** the defining loader that the single-argument overload `Class.forName(name)` uses according to caller rules. For a plugin that needs to look up the child's `sample.Widget`, pass the exact child loader and verify `type.getClassLoader()`; see the `loadClass`/`forName` verification article for the corresponding stdout.

## 13. Common Mistakes When Observing Results

| Symptom | Possible Cause | Proper Check |
| --- | --- | --- |
| Expected CHILD but printed PARENT | Loader is still parent-first and parent has the same class name | `clazz.getClassLoader()`, `origin()`, and parent URL |
| Expected parent-first but printed CHILD | Parent cannot see the class or the loader overrides `loadClass` | Call parent `loadClass` directly and inspect the policy |
| Two loaders return the same `Class<?>` | Both delegate to the same parent defining loader | `clazzA == clazzB` and `getClassLoader()` |
| Two loaders use the same file but return different classes | Both loaders **self-define** the same binary name | `getName()` matches, `==` is false, defining loaders differ |
| `ClassCastException` despite identical class names | Runtime class identities differ | Shared parent interface or the same defining loader |
| `LinkageError: duplicate class definition` | Loader redefines the same name | `findLoadedClass` and locking before `defineClass` |
| `NoClassDefFoundError` for a dependency | Child class was defined but the dependency could not be found or prior initialization failed | Stack trace, runtime path, and caller's loader |
| `NoSuchMethodError` between plugin/host | Version skew in shared API; parent shadows the newer version | Bytecode descriptors, defining loader, and CodeSource |
| `IllegalAccessError` for package-private | Same package name, but different runtime packages due to loaders | Package + defining loader, module access |
| `getResource` returns the parent's config | Resource delegation differs from class policy | Print resource URL and loader lookup |
| Error occurs only when callback runs | TCCL/caller loader or late dependency loading | Print loader/context at the callback |
| Already-loaded class still runs after `close()` | Closing does not equate to class unloading | Resource/lifecycle check; do not infer from method calls |

You must distinguish **ClassNotFoundException** when an API calls `loadClass` and cannot find a binary name, from **NoClassDefFoundError** when the VM resolves a missing dependency or initialization failed, and **ClassCastException** when two runtime types are incompatible. These three errors cannot be fixed in the same way.

## 14. Do Not Forget Class-Loading Locks

In a custom loader overriding `loadClass(name, resolve)`, checking `findLoadedClass` and calling `findClass` must hold an appropriate critical section (`getClassLoadingLock(name)`). If two threads concurrently call `defineClass` themselves for the same binary name in **the same loader**, the duplicate definition can trigger a `LinkageError`. The article **Verifying Concurrent Loading and Handling Duplicate Class Names** is dedicated to parallel-capable loaders, per-name locks, and latch-based tests.

## 15. Diagnostics with JVM Tools Beyond printf

When code is already running in a large server and it is inconvenient to add debug prints everywhere, you can use:

**HotSpot class loading log:**

```bash
java -Xlog:class+load=info -cp host-classes VerifyDelegation
```

Look for `sample.Widget` in the log. The load line may indicate the source/loader depending on the runtime and logging level. Warning: the source only indicates where the bytecode came from if reported; it does not replace comparing the defining loader in code.

**jcmd class loader tree:**

```bash
jcmd <PID> VM.classloaders
jcmd <PID> VM.classloaders show-classes=true fold=false
```

Replace `<PID>` with the actual PID of the running JVM, for example from `ProcessHandle.current().pid()`. A very short main example may terminate before `jcmd` attaches; if you want to try it, use a long-running server or add an intentional wait **in test code**.

**jcmd statistics/hierarchy:**

```bash
jcmd <PID> VM.classloader_stats
jcmd <PID> VM.class_hierarchy sample.Widget
```

- `VM.classloader_stats` helps inspect class counts and loader-data.
- `VM.class_hierarchy` displays **class inheritance**, not parent delegation.
- `VM.classloaders` is what shows the **parent loader hierarchy**.
- The same class name defined by different loaders may be associated with different `ClassLoaderData` entries in diagnostics.

**`javap`** reads class files on disk; it does not directly measure which class version the JVM selected. When suspecting `NoSuchMethodError` or an API mismatch, combine `javap -s -p` on the **binaries actually loaded at runtime** with `CodeSource` and classloading logs.

## 16. Practice Exercises with Solution Hints

### Exercise 1 — Point the normal loader directly to the platform parent

Replace:

```java
new URLClassLoader("normal", childUrls, parent)
```

with:

```java
new URLClassLoader(
        "normal", childUrls, ClassLoader.getPlatformClassLoader())
```

This is an **illustrative constructor replacement snippet**, not a complete program. Because the platform loader **does not have `sample.Widget` in the experiment**, URLClassLoader `normal` can find the CHILD version itself when the parent lookup fails. **Parent-first is still parent-first**; the only difference is that the parent does not have the requested class.

Lesson: “Result origin=CHILD” is **not enough to conclude that a classloader is child-first**; you must also check whether the parent has the same class and check the lookup policy.

### Exercise 2 — Remove the child class file

Keep the normal and child-first loaders, but remove `child-classes/sample/Widget.class` before running (ensuring the parent still has the PARENT version).

Expected result: `SelectiveChildFirst.findClass` does not find it in the child, catches `ClassNotFoundException`, falls back to the parent, and returns the **PARENT** version. Lesson: child-first can also return the parent's class.

**This is a conditional prediction exercise**, not the main stdout of the verified demo; when removing the child file, comparisons in main such as `child-first chose child`/`cross-loader cast` also change.

### Exercise 3 — Place the shared API in the parent

Create an `api.Plugin` interface in the parent output, and then have two different child implementations implement that API. Check:

```java
api.Plugin.class.isAssignableFrom(pluginAClass)
api.Plugin.class.isAssignableFrom(pluginBClass)
```

These are **illustrative expressions**, assuming `api.Plugin` has been created in the appropriate classpath/loader. If the implementations delegate `api.Plugin` to the same parent defining loader, both are assignable; if the child defines its own copy of the API, they may not be assignable to the host's `api.Plugin.class`.

### Exercise 4 — Do not use `getName()` to determine identity

Print:

```java
System.out.println(a.getName().equals(b.getName()));
System.out.println(a == b);
```

In the main example, the first line is `true`, and the second line is `false`. The goal is to remind you that **class name equality ≠ class identity**.

### Exercise 5 — Create a new loader from the same directory

After loaders A and B are closed, create a loader C also pointing to `child-classes`. C can self-define a third `sample.Widget`. Do not assume that `URLClassLoader.close()` on A/B has unloaded the old types; class unloading depends on reachability/GC and does not happen immediately.

## 17. Misconceptions to Avoid

| False Statement | Correction |
| --- | --- |
| “Child calling loadClass means child definitely defines the class.” | False. The parent may define the class and return it. |
| “If a class file is in the child directory, the child will prioritize that version.” | Not when it is parent-first and the parent has a class with the same name. |
| “Two `Class<?>` instances with the same `getName()` are definitely the same type.” | False. The defining loader must be considered. |
| “If two loaders read the same bytes, the JVM treats them as the same class.” | False if both define the class themselves. |
| “A loader can redefine the same binary name on every call.” | False; duplicate definitions can throw `LinkageError`. |
| “TCCL makes Class.forName(String) automatically use the child loader.” | False; the single-parameter overload uses the caller's defining loader. |
| “ClassLoader.getResource and loadClass definitely follow the same order.” | No, resource lookup policy must be examined independently. |
| “`resolveClass` runs the static initializer.” | No; linking is different from class initialization. |
| “Equal package names mean package-private access across loaders.” | False; a runtime package also depends on the defining loader. |
| “ClassCastException between plugins is because the compiler does not understand the package name.” | No; type identity in the JVM includes the loader component. |
| “Simply enabling child-first for every package will fix dependency conflicts.” | It can break shared API/platform classes and cause linkage errors. |
| “Closing a URLClassLoader immediately deletes the old Class identity.” | No; the JVM may still retain the loader/class/instances. |

## 18. Self-Check Questions with Answers

**Question 1.** In the demo, both parent and child have `sample.Widget`. Why does `normal` choose the PARENT version?

**Answer:** `normal` is a default parent-first `URLClassLoader`. It delegates to `parent.loadClass` first and receives the class defined by the parent; therefore, `normal.findClass` does not need to be called.

**Question 2.** Why does `first` choose CHILD even though the parent has a class with the same name?

**Answer:** `SelectiveChildFirst` overrides `loadClass` for the `sample.` namespace, calls `findClass` on the child first, and only falls back to the parent if the child does not have the class.

**Question 3.** `a.getName().equals(b.getName())` returns true, and `a == b` returns false. Is this a contradiction?

**Answer:** No. They have the same binary name, but their defining loaders are different, so they are two separate runtime types according to the JVMS.

**Question 4.** What error does `a.cast(objectOfB)` throw, and why?

**Answer:** `ClassCastException`, because objectOfB has a runtime class defined by loader B, not loader A's `Class<?> a`.

**Question 5.** How does an initiating loader differ from a defining loader?

**Answer:** An initiating loader initiates loading (it may delegate); a defining loader actually defines the type. Runtime identity is based on the defining loader.

**Question 6.** Why does calling `first.loadClass("sample.Widget")` a second time return the same class as before?

**Answer:** The loader maintains a namespace/records already-loaded classes, and the implementation checks `findLoadedClass` before defining. This avoids duplicate definitions of the same binary name within one loader.

**Question 7.** Why is merely printing the `origin()` method not enough to verify the loader policy?

**Answer:** If the parent does not have the class, even a parent-first loader falls back to the child and prints CHILD. You need to test with **two versions having the same name** in both parent and child, while also printing the defining loader.

**Question 8.** If two plugins need to communicate with the host through `api.Plugin`, where should the API be defined?

**Answer:** In the parent/shared loader, so that the host and plugins receive **the same runtime interface type**. The separate implementations in the child loaders can still differ.

**Question 9.** What does `Class.getClassLoader() == null` usually indicate?

**Answer:** That the class was defined by the bootstrap loader (for example, `String` in typical JVMs). It does not mean the class does not exist or was unloaded.

**Question 10.** Is using `VM.class_hierarchy` the right way to read the parent loader chain?

**Answer:** No. That is the class inheritance hierarchy; the parent loader tree is viewed using `VM.classloaders`.

**Question 11.** Why are `findLoadedClass` and locking needed when overriding `loadClass`?

**Answer:** To avoid repeatedly loading/defining the same binary name and races between multiple threads. You must understand parallel-capable loader rules if you want to deploy a concurrent production implementation.

**Question 12.** Will `Class.forName("sample.Widget")` inside a host helper definitely use the child-first loader currently set in the TCCL?

**Answer:** No. The single-parameter overload uses the host caller's defining loader; to use a specific loader, pass it to the three-parameter overload.

**Question 13.** If `a.getClassLoader() != b.getClassLoader()`, is `a != b` guaranteed for normal classes?

**Answer:** Yes, because a runtime class has a single definite defining loader; two different defining loaders cannot share the same runtime class definition.

**Question 14.** Can a child-first loader fall back to the parent?

**Answer:** Yes. Child-first only changes **priority**; if the child does not find it, the implementation can ask the parent, as in the `SelectiveChildFirst` demo.

## 19. Verification Checklist for Real Projects

1. **Create two versions with the same binary name** in independent parent/child outputs to distinguish order.
2. **Check the host's runtime classpath** to ensure it does not accidentally contain both versions via the application loader.
3. **Print the parent loader** using `getParent()` and verify the URLs of the parent and child.
4. **Print `getClassLoader()` of the result**, not just the name of the loader that received the request.
5. **Compare `Class<?>` with `==`** when evaluating class identity.
6. **Invoke a method with differing output** between the two versions to prove which version's bytes are being executed.
7. **Repeat `loadClass`** to verify reuse without duplicate definitions.
8. **Inspect the namespace allowlist** for child-first, keeping shared API/platform classes parent-first.
9. **Use reflective `Class.cast` / `isInstance`** when you want to prove type separation.
10. **Check CodeSource and classloading logs** when investigating JAR/classpath precedence.
11. **Read the `ClassLoader.loadClass` contract** before overriding, and do not mistakenly catch linkage errors as a fallback.
12. **Check TCCL separately** if the framework/SPI uses context lookup.
13. **Distinguish `load`, `link`, and `initialize`**; do not assume static initializers run merely because of `loadClass`.
14. **Do not treat `getResource` as proof that a class was defined**; resource policy may differ.
15. **In real plugins**, keep the loader open throughout the lifecycle that requires lazy loading, and clean up callbacks/tasks before closing.
16. **When using JPMS**, include module exports/opens/readability in your analysis.
17. **Test concurrent loading** and classloader constraints if writing a production custom loader.
18. **Record verified results**: class name, loader object, defining loader, origin output, equality/cast, and runtime version.

## Conclusion

**Delegation order** determines **which loader gets the chance to search for the class first**, whereas **the runtime identity of `Class<?>`** depends on **binary name + defining loader**. In the experiment, the parent-first `normal` loader returns the exact class from `parent`; the `child-first-A` loader defines the CHILD version itself; two different child-first loaders define **two runtime types** despite having the same name, and cross-casting throws `ClassCastException`.

To verify properly, do not rely on just a single `System.out.println(clazz.getName())` line. Check **parent chain → loader policy → defining loader → `Class<?>` equality → method origin → instance assignability**. This is also the foundation for designing plugin isolation while still stably sharing interfaces between the host and plugins.

**Official Java 17 Documentation:**

- [ClassLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html) — `loadClass`, `findLoadedClass`, `findClass`, `getClassLoadingLock`, parent delegation, and loader name.
- [URLClassLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html) — URL classpath, named loader constructors, `close`.
- [JVMS 17 5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3) — defining/initiating loader, runtime type identity, loader constraints.
- [JLS 17 12 — Execution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html) — loading, linking, initialization, unloading.
- [Class API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html) — `getName`, `getClassLoader`, `cast`, `isInstance`.
