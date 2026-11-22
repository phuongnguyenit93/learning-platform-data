# ClassCastException Due to Different Loader Identities

## 1. Why Can a Class Seemingly Not Be Cast to "Itself"?

When a Java application has multiple `ClassLoader`s, you sometimes encounter a confusing error:

~~~text
java.lang.ClassCastException:
class plugin.Worker cannot be cast to class plugin.Worker
~~~

On newer JDKs, the message usually appends the **module and loader** name on each side; the exact content can vary across environments, so you should not write tests that rely on the entire exception string.

Reason: in the JVM, **the class name is not the entirety of a type's identity**. For an ordinary class/interface, the runtime identity is the pair:

~~~text
(binary name, defining class loader)
~~~

For example:

~~~text
("plugin.Worker", LoaderA) != ("plugin.Worker", LoaderB)
~~~

Even when two loaders read **the exact same `plugin/Worker.class` file with identical bytecode**, if both actually define the class, the JVM creates **two different runtime classes**.

Consequences:

- `classA.getName().equals(classB.getName())` can return `true`.
- `classA == classB` returns `false` if the defining loaders are different.
- `classA.isInstance(objectB)` returns `false` if objectB belongs to a different class copy with no subtype relationship recognized by the JVM.
- `classA.cast(objectB)` throws `ClassCastException`.
- The same interface used in source code can also be **defined twice**, making the plugin's implementation unable to be cast to the interface on the host.

This is a **runtime type identity** error, not an error caused by misspelling a package name or the Java compiler failing to understand `import`.

## 2. Defining Loader and Initiating Loader

To debug accurately, you must distinguish:

| Concept | Meaning |
| --- | --- |
| **Binary name** | The binary name of the class, for example `plugin.Worker`. |
| **Defining class loader** | The loader that actually defines the class in the JVM; it is part of the runtime identity. |
| **Initiating class loader** | The loader that initiates the request to load the class; it may delegate to another loader to define it. |
| **Parent-first delegation** | The child asks the parent first, then searches its own sources only if the parent does not find it. |
| **Class object** | The `Class<?>` object representing one specific runtime type, not merely a name string. |

Illustrative example:

~~~java
Class<?> type = child.loadClass("api.Task");
ClassLoader definingLoader = type.getClassLoader();
~~~

You must not infer `definingLoader == child`. With parent-first, if the parent has already loaded `api.Task`, `child.loadClass` returns **the parent's Class**.

Therefore, merely having a copy of `api.Task.class` inside the plugin JAR is **not enough to conclude there is a conflict**. If the child always delegates to the parent for the interface and the parent has that class, the copy may never be used. The error occurs when **two copies are actually defined by two loaders**.

### Two Separate Implementation Classes and One Shared API

~~~text
             Host / Application Loader
             ├── api.Task
             └── PluginManager
                       |
          +------------+------------+
          |                         |
       Loader A                  Loader B
       plugin.Worker             plugin.Worker
       implements api.Task       implements api.Task
       (Task from parent)        (Task from parent)
~~~

The two `plugin.Worker` classes of A/B are two different types; however, **both can be cast to the same `api.Task` interface** if they use the Task copy defined by the parent. That is the standard model of a plugin system.

## 3. Two Different ClassCastException Scenarios

### Scenario A — Casting Between Two Same-Named Implementation Copies

~~~java
Class<?> fromA = loaderA.loadClass("plugin.Worker");
Class<?> fromB = loaderB.loadClass("plugin.Worker");
Object objectB = fromB.getDeclaredConstructor().newInstance();

System.out.println(fromA.getName().equals(fromB.getName())); // true
System.out.println(fromA == fromB);                          // false
System.out.println(fromA.isInstance(objectB));               // false
fromA.cast(objectB); // ClassCastException
~~~

This is an illustrative snippet in a context where two loaders genuinely define `plugin.Worker` separately and the constructor is accessible. Use the complete code in section 6 to reproduce it.

Even if plugins A and B are compiled from the same source, a Worker instance from B does not automatically become a Worker instance of A. If the host needs to use both, interact through a **shared interface** rather than casting from one loader's concrete class to another loader's concrete class.

### Scenario B — The API Interface Itself Is Also Duplicated

~~~text
Host loader:
  api.Task            -- interface expected by the host

Isolated plugin loader:
  api.Task            -- interface copy defined by the plugin
  plugin.Worker       -- implements Task inside the isolated loader
~~~

A cast like:

~~~java
api.Task task = (api.Task) isolatedObject;
~~~

can throw `ClassCastException`, even though the plugin code has `implements api.Task`. The reason: the `api.Task` symbol in the plugin bytecode resolves to **the isolated loader's Task**, whereas the host's cast references **the host loader's Task**. Same name, different runtime interface.

This is a trickier scenario because reading the source/JAR makes the type name look completely reasonable.

## 4. Duplicate JARs, Delegation, and Choosing a Package Policy

| Scenario | Possible Outcome |
| --- | --- |
| Plugin JAR contains `api.Task.class`, child is parent-first, and parent has Task | May still use **the parent's Task**; not necessarily a cast error. |
| Child-first including `api.*` | Child may define a different Task copy; risk of ClassCastException. |
| Child has platform/bootstrap as parent and cannot see host API | Child defines Task itself from the plugin archive; different from host's Task. |
| Two sibling loaders each define `plugin.Worker` | Two different Worker runtime types despite identical bytes. |
| Host accidentally adds the plugin JAR to the application classpath | Parent may load the implementation early, reversing the expected defining loader result. |
| Plugin reload creates loader v2 | Worker v1 and Worker v2 are not the same concrete type, even with the same binary name. |

Solutions for SPI/API:

1. Place the **shared interfaces/contracts** (and the types passing through public method signatures) on the host's classpath/module or in a shared parent loader.
2. Keep the child **parent-first for the shared API packages**.
3. Use child-first only selectively for implementation packages or dependencies that need isolation.
4. Do not cast concrete classes across plugin versions/loaders.
5. If separate classes need to communicate, use a shared API, adapter, shared DTO, or serialization with a clear contract.

**Note:** `ClassLoader.getParent()` only returns the direct parent; in practice, a custom loader can override lookup, so do not rely on a simple loader tree to guess class identity. Check `clazz.getClassLoader()` and `clazz == otherClazz` directly at runtime.

## 5. Class.cast, instanceof, and isAssignableFrom

These operations have related goals but differ in form:

| Check | Used For | When Type Identity Is Incompatible |
| --- | --- | --- |
| `TargetType.class.isInstance(object)` | Checking whether an object belongs to a specific type/subtype | Returns `false` |
| `TargetType.class.cast(object)` | Dynamic casting via a Class object | Throws `ClassCastException` for an incompatible non-null object |
| `object instanceof TargetType` | Checking runtime type in Java code | `false` |
| `TargetType.class.isAssignableFrom(otherClass)` | Checking whether another class/interface is assignable to this type | `false` |
| `clazzA == clazzB` | Checking whether two references are the exact **same runtime Class object** | `false` |
| `clazzA.getName().equals(clazzB.getName())` | Comparing binary name strings | Can be `true` even though casting fails |

Do not use string comparison of class names as a substitute for `isAssignableFrom`. For a plugin API, the real question is **whether the implementation class is compatible with the host's interface Class**, not whether the implementation and interface have matching names.

Regarding `Class.cast(null)`, just like an ordinary reference cast, `null` does not cause a ClassCastException; the examples in this article intentionally use real instances for illustration.

## 6. Standalone Java 17+ Program: Cast Error and Proper Shared API

The program consists of **three source files**. Specifically, we will compile `api.Task` into **two different output folders** so that an API copy can be created when the isolated loader reads the plugin root.

Structure:

~~~text
example/
├── src/
│   ├── api/Task.java
│   ├── plugin/Worker.java
│   └── host/IdentityDemo.java
└── out/
    ├── host/           (Task + IdentityDemo)
    └── plugin/         (Task + Worker)
~~~

**Only `out/host` is placed on the application classpath at runtime.** `out/plugin` is passed via an argument, not added to `-cp`.

### src/api/Task.java

~~~java
package api;

public interface Task {
    String run();
}
~~~

### src/plugin/Worker.java

~~~java
package plugin;

import api.Task;

public final class Worker implements Task {
    @Override
    public String run() {
        return "plugin-ok";
    }
}
~~~

### src/host/IdentityDemo.java

~~~java
import api.Task;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class IdentityDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("plugin class root");
        }

        URL root = Path.of(args[0]).toAbsolutePath()
                .normalize().toUri().toURL();
        ClassLoader host = IdentityDemo.class.getClassLoader();

        try (URLClassLoader a = new URLClassLoader(
                     new URL[]{root}, host);
             URLClassLoader b = new URLClassLoader(
                     new URL[]{root}, host);
             URLClassLoader isolated = new URLClassLoader(
                     new URL[]{root},
                     ClassLoader.getPlatformClassLoader())) {

            Class<?> classA = a.loadClass("plugin.Worker");
            Class<?> classB = b.loadClass("plugin.Worker");

            Object objectA =
                    classA.getDeclaredConstructor().newInstance();
            Object objectB =
                    classB.getDeclaredConstructor().newInstance();

            System.out.println("same binary name: "
                    + classA.getName().equals(classB.getName()));
            System.out.println("same runtime Class: "
                    + (classA == classB));
            System.out.println("defined by A/B: "
                    + (classA.getClassLoader() == a
                    && classB.getClassLoader() == b));
            System.out.println("A isInstance(B): "
                    + classA.isInstance(objectB));

            try {
                classA.cast(objectB);
                System.out.println("unexpected cast success");
            } catch (ClassCastException expected) {
                System.out.println(
                        "cross-loader cast: ClassCastException");
            }

            System.out.println("shared API A: "
                    + (a.loadClass("api.Task") == Task.class));
            System.out.println("shared API B: "
                    + (b.loadClass("api.Task") == Task.class));

            System.out.println("A via API: "
                    + ((Task) objectA).run());
            System.out.println("B via API: "
                    + ((Task) objectB).run());

            Class<?> copyApi = isolated.loadClass("api.Task");
            Object isolatedObject =
                    isolated.loadClass("plugin.Worker")
                            .getDeclaredConstructor().newInstance();

            System.out.println("isolated API same: "
                    + (copyApi == Task.class));
            System.out.println("isolated implements host API: "
                    + (isolatedObject instanceof Task));

            try {
                Task invalid = (Task) isolatedObject;
                System.out.println(
                        "unexpected API cast success: " + invalid.run());
            } catch (ClassCastException expected) {
                System.out.println(
                        "isolated API cast: ClassCastException");
            }
        }
    }
}
~~~

**Mechanism of each loader:**

- `a` and `b` use the **host loader as their parent**. For `api.Task`, both delegate to the host. However, the parent does not have `plugin.Worker`, so they each define different Workers themselves.
- `isolated` uses the **platform loader as its parent**, not the host's application loader. When it needs `api.Task`, its parent cannot see the application's Task, so isolated defines Task from `out/plugin`.
- All three loaders point to the same `out/plugin` directory URL; the difference comes from **parent/delegation and the defining loader**, not from different file names.
- `try-with-resources` closes the loaders after the experiment; closing them does not guarantee that classes are immediately unloaded.

### Linux/macOS Commands

From inside the `example` directory containing the three source files:

~~~bash
mkdir -p out/host out/plugin

javac --release 17 -d out/host \
  src/api/Task.java src/host/IdentityDemo.java

javac --release 17 -d out/plugin \
  src/api/Task.java src/plugin/Worker.java

java -cp out/host IdentityDemo out/plugin
~~~

### Windows PowerShell Commands

~~~powershell
New-Item -ItemType Directory -Force out\host, out\plugin | Out-Null
javac --release 17 -d out\host src\api\Task.java src\host\IdentityDemo.java
javac --release 17 -d out\plugin src\api\Task.java src\plugin\Worker.java
java -cp out\host IdentityDemo out\plugin
~~~

Compiling `Task.java` twice is **intentional to create a copy** for the experiment. In a real build, the API contract should be defined consistently in the parent, and the child must not define a second runtime copy.

### Verified Exact Stdout

~~~text
same binary name: true
same runtime Class: false
defined by A/B: true
A isInstance(B): false
cross-loader cast: ClassCastException
shared API A: true
shared API B: true
A via API: plugin-ok
B via API: plugin-ok
isolated API same: false
isolated implements host API: false
isolated API cast: ClassCastException
~~~

This example was compiled with `javac --release 17` and run on OpenJDK 21. The output above matches line for line.

### Interpreting the Results

1. **same binary name: true** — Both A and B load `plugin.Worker`.
2. **same runtime Class: false** — The Workers are created by two different defining loaders.
3. **defined by A/B: true** — The two implementations are genuinely defined separately.
4. **A isInstance(B): false** — B's object does not belong to A's concrete class.
5. **cross-loader cast: ClassCastException** — Cross-loader concrete class casting fails as expected.
6. **shared API A/B: true** — Both A and B receive the host's `api.Task` copy due to parent-first delegation.
7. **A/B via API: plugin-ok** — The host can still communicate with both Workers through the same Task interface.
8. **isolated API same: false** — The isolated loader defined its own Task from the plugin root.
9. **isolated implements host API: false** — A Worker implementing the isolated Task is not an instance of the host Task.
10. **isolated API cast: ClassCastException** — Casting to the host interface fails.

This reproduces **two distinct identity errors**: casting between concrete implementations A ↔ B, and casting an implementation with a copied interface to the host's interface.

## 7. How to Fix This in a Real Plugin Application

The architecture should have one **shared API package** and separate implementation loaders:

~~~text
Parent / Host ClassLoader
  ├── api.Task       (a single runtime interface)
  └── PluginManager
      |
      +--- Plugin Loader v1
      |       plugin.Worker
      |
      +--- Plugin Loader v2
              plugin.Worker
~~~

The host depends only on the API:

~~~java
Class<?> impl = pluginLoader.loadClass("plugin.Worker");
api.Task task = (api.Task) impl
        .getDeclaredConstructor().newInstance();

System.out.println(task.run());
~~~

This is an illustrative snippet inside a method, assuming a valid `pluginLoader`, Task interface, and constructor/method. Implementations v1 and v2 **do not need to be cast to each other**.

Practical measures:

- **Single API owner:** Keep the `api.*` package in the parent loader; plugins compile against that API, while at runtime they use the parent's copy.
- **Parent-first for API/shared types:** If you choose child-first to isolate plugin dependencies, exclude the contract packages from the child-first policy.
- **Do not pass concrete objects across the boundary unnecessarily:** Use interfaces, shared DTOs, primitives/strings, or messages/serialization.
- **Unify types in signatures:** Exceptions, return values, method parameters, DTOs, and parent interfaces need consistent class identity when crossing the boundary.
- **Test plugin isolation:** Verify that `pluginLoader.loadClass("api.Task") == api.Task.class` and `api.Task.class.isAssignableFrom(impl)`.
- **Do not rely solely on fixing dependency scope:** Maven `provided` or Gradle `compileOnly` can prevent packaging a second runtime copy of the API, but the host **must actually provide the API** and the loader policy must delegate properly.
- **Use JAR shading/relocation carefully:** Isolating private dependencies under separate package names can avoid conflicts, but do not relocate shared API interfaces if the host needs to cast through them.

A plugin JAR containing a same-named API **does not necessarily cause an error** when the child is parent-first; conversely, a misconfigured child-first custom loader can create a duplicate even when the build tree looks "clean". Always verify using runtime facts.

## 8. Practical Debugging: Print the Exact Class and Defining Loader

When a ClassCastException occurs, do not just print the names of the two classes. Print the full details:

~~~java
static void inspect(Object actualObject, Class<?> expected) {
    Class<?> actual = actualObject.getClass();

    System.out.println("actual: " + actual.getName());
    System.out.println("expected: " + expected.getName());
    System.out.println("same Class: " + (actual == expected));
    System.out.println("compatible: "
            + expected.isInstance(actualObject));
    System.out.println("actual loader: " + actual.getClassLoader());
    System.out.println("expected loader: " + expected.getClassLoader());
    System.out.println("actual module: " + actual.getModule());
    System.out.println("expected module: " + expected.getModule());
}
~~~

This is an **illustrative helper**, not a standalone runnable program. The loader name/identity string and module may vary across JVMs.

**Important:** If `expected` is an interface, `actual == expected` is normally false even when the cast is **valid** (an implementation class differs from the interface). Therefore, check `expected.isInstance(actualObject)` and **the identity of the interface actually loaded by the implementation**:

~~~java
Class<?> taskSeenByPlugin =
        pluginLoader.loadClass("api.Task");

System.out.println(taskSeenByPlugin == api.Task.class);
~~~

A false result is a strong indicator of two different interface classes. However, a true result only proves that the **Task identity** is shared; you still need to check that the implementation actually implements Task and that there are no other constructor/linking errors.

### Inspecting CodeSource and Modules

When you need to identify the physical JAR:

~~~java
Class<?> type = actualObject.getClass();
var domain = type.getProtectionDomain();
var source = domain == null ? null : domain.getCodeSource();

System.out.println(source == null
        ? "(unknown source)"
        : source.getLocation());
~~~

There is no guarantee that every class has a useful CodeSource URL; custom loaders may provide different metadata or null. **CodeSource only helps investigate the byte source**, whereas the defining loader remains the essential factor for type identity.

`Class.getModule()` helps distinguish named/unnamed modules on Java 9+, but **having the same module name does not automatically make two classes with different defining loaders the same type**. Classes belonging to the bootstrap loader may return `getClassLoader() == null`; null here does **not** mean the class has not been loaded.

### Class Loading Logs

On JDK 17+, you can use:

~~~bash
java -Xlog:class+load=info -cp out/host IdentityDemo out/plugin
~~~

This is a diagnostic command; the output will be long and vary between JDKs, so filter by `plugin.Worker` and `api.Task`. Do not treat the full log as fixed stdout for this article.

## 9. Distinguishing ClassCastException from Other Loader Errors

| Exception/Error | Symptom | What to Investigate |
| --- | --- | --- |
| `ClassNotFoundException` | Lookup by name cannot find the class. | Which sources/URLs/modules does the queried loader have? |
| `NoClassDefFoundError` | A dependency cannot be defined when needed, or the class had an earlier initialization failure. | The cause and the defining loader of the class containing the symbolic reference. |
| `ClassCastException` | The object is incompatible with the runtime target type. | Do the two classes/interfaces share the same defining loader identity? |
| `LinkageError: loader constraint violation` | The JVM detects inconsistent type identity requirements across loaders during linking. | Shared method/field signature types and loading constraints. |
| `NoSuchMethodError` | The resolved runtime method does not match the compiled version. | Parent-vs-child version/dependencies. |
| `IllegalAccessError` | JVM access checks fail. | Module exports, package access, JVM linking. |

ClassCastException can also be an **ordinary cast error unrelated to multiple loaders**, for example casting an Integer to a String. Only conclude a loader conflict when the metadata of the two runtime types proves it.

Conversely, in some cross-loader interactions, the JVM enforces **loading constraints** on type names in method/field signatures to protect type safety. An error may appear as a `LinkageError` **before** any explicit cast takes place.

## 10. Plugin Reloads and ClassCastException After Deployment

A hot reload process typically creates a new loader for a different version:

~~~text
Loader L1: plugin.Worker (v1)
Loader L2: plugin.Worker (v2)
~~~

If the host holds onto an object from L1 and tries to cast it to **L2's concrete Class**, the error can easily happen, even if v1 and v2 have similar code.

Safe procedure:

1. Design the host–plugin boundary using interfaces/DTOs in the parent.
2. Load v2 into a new loader, attempt to instantiate it, and cast through the **shared interface**.
3. Switch routing for new requests to v2 after a health check.
4. Wait for in-flight v1 requests to finish; stop callbacks, tasks, and threads, unregister, and close v1 resources.
5. Close loader v1 when appropriate; remove old references from caches/registries/ThreadLocal/TCCL.
6. Do not cast an implementation object from v1 to concrete class v2.

`URLClassLoader.close()` does not automatically remove already-loaded classes/objects. Class unloading also depends on reachability and GC. Do not use `System.gc()` or restart the JVM as a default workaround if the real bug is mixing runtime class identities; fix the sharing boundary and lifecycle first.

## 11. Thread Context ClassLoader and ServiceLoader

The thread context class loader (TCCL) is a loader that a framework can **actively select** to locate services/resources:

~~~java
Thread current = Thread.currentThread();
ClassLoader old = current.getContextClassLoader();

try {
    current.setContextClassLoader(pluginLoader);
    // Call a framework/API whose contract locates services via the TCCL.
} finally {
    current.setContextClassLoader(old);
}
~~~

This illustrative snippet requires the `pluginLoader` variable to exist. One example of an API that actively uses the TCCL is `ServiceLoader.load(ServiceType.class)`. However, the TCCL **cannot fix type identity** if the provider implements a different copy of the interface. A plugin discovered via the TCCL must still be compatible with the service Class on the host.

Do not confuse the TCCL with the defining loader: when the JVM resolves symbolic references in bytecode, it relies on the defining loader of the class containing the reference along with loading constraints; it does not automatically consult the TCCL for every dependency.

For JPMS applications, `exports` and `opens` control access/reflection across module boundaries, but they do not merge two Class objects created by two different defining loaders. Trying to fix a loader conflict with `--add-opens` usually addresses the wrong cause.

## 12. Diagnostic and Review Checklist

Diagnostic steps when a cast fails:

1. **Which object** is being cast and what is the **target Class**?
2. What are the binary names of the two classes? Do they merely share the same name?
3. What are the defining loaders of the actual class and the expected type?
4. If the target is an interface, is the plugin using the parent's exact **interface Class**?
5. Is there a duplicate API JAR in the plugin, a shaded JAR, or overly broad child-first delegation?
6. Did the parent loader accidentally load the plugin implementation from the application classpath?
7. After a reload, is a v1 object being mixed with a v2 Class?
8. Can casting to a concrete implementation be replaced with casting through a shared interface?
9. If a LinkageError/NoSuchMethodError occurs, are dependency versions or loading constraints inconsistent?
10. With JPMS, is an access failure due to exports/opens being confused with a ClassCastException?
11. Are any caches, callbacks, TCCLs, ThreadLocals, or registries still holding references to the old loader?
12. Have you tested runtime class identity using `==`, `isInstance`, and `isAssignableFrom`?

### Self-Check Questions

**Question 1.** Two loaders both read the Worker bytecode and return a class named `plugin.Worker`. Why is `classA == classB` false?

**Answer:** The JVM distinguishes runtime classes by **binary name and defining loader**. Identical bytecode/names do not make two definitions the same.

**Question 2.** Can Workers from Loader A and Loader B both be cast to `api.Task`?

**Answer:** Yes, if both implementations actually implement **the same runtime Task interface** defined by a shared loader.

**Question 3.** The plugin source has `implements api.Task`, yet the host fails when casting the object to Task. Why?

**Answer:** The plugin may have used **a Task defined by its own loader**, different from the host's Task; matching imports/names are not enough.

**Question 4.** Will a JAR containing a copy of Task definitely cause a cast error?

**Answer:** No. If parent-first delegates to the Task defined by the parent, the copy in the child may never be loaded.

**Question 5.** Can `--add-opens` be used to merge two classes with the same name from different loaders?

**Answer:** No. Opens only affects JPMS access/reflection; it does not change Class identity.

**Question 6.** Is casting concrete implementations between two plugin versions after a reload always valid if both versions come from the same source?

**Answer:** No. If they are defined by two different defining loaders, the concrete runtime classes are different. Use a shared API boundary instead.

## Authoritative References

- [JVMS Java SE 21 §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): class identity by binary name and defining loader.
- [JVMS Java SE 21 §5.3.4 — Loading Constraints](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3.4): preserving type safety across multiple loaders.
- [JLS Java SE 21 §12.2.2 — Class Loader Consistency](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.2.2): class loader consistency.
- [Java SE 21 — java.lang.Class](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `cast`, `isInstance`, `isAssignableFrom`, and `getClassLoader`.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): delegation and defining loader.
- [Java SE 21 — ClassCastException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassCastException.html): incompatible runtime cast exception.
