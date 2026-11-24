# Identifying Types by Binary Name and Defining Class Loader in Java

In Java, two `.class` files with the **same package name, the same class name, and even identical bytes of Java bytecode** can still be **two different runtime types**. Conversely, two class-loading calls passing through **two different `ClassLoader` objects** can still return **the exact same single type** if both delegate to the same loader that defined the class.

The core rule of the Java Virtual Machine Specification (JVMS §5.3) for ordinary classes/interfaces is:

~~~text
Runtime type identity = (binary name, defining class loader)
~~~

Both components must be considered **together**. A string name, a JAR location, a library version, or a class loader participating in the lookup does not by itself determine type identity. This is the foundation for understanding why plugin systems can load multiple library versions simultaneously, and why a `ClassCastException` such as "class X cannot be cast to class X" sometimes occurs.

## 1. What Is a Binary Name?

A **binary name** is the name the JVM uses to identify a class/interface in bytecode structures and class-loading calls. For ordinary classes/interfaces (not arrays or hidden classes), `Class.getName()` returns the binary name.

| Declaration kind | Name as written in source | Typical binary name |
| --- | --- | --- |
| Top-level class | `package demo.api; class Service {}` | `demo.api.Service` |
| Top-level interface | `package demo.api; interface Plugin {}` | `demo.api.Plugin` |
| Member class | `class Outer { static class Inner {} }` | `demo.api.Outer$Inner` |
| Nested interface | `Outer.Nested` | `demo.api.Outer$Nested` |
| Class in default package | `class Example {}` | `Example` |

The `$` character in a member class name is critical: `Class.forName("demo.api.Outer.Inner")` cannot substitute for `Class.forName("demo.api.Outer$Inner")`. Local/anonymous class names can contain compiler-generated markers and should not be treated as stable API.

Three concepts to distinguish:

- **Simple name**: the short name, e.g., `Inner`, which can collide across packages.
- **Canonical name**: the language-level name used to refer to a class if one exists, e.g., `demo.api.Outer.Inner`; not identical to the binary name of a member class.
- **Binary name**: e.g., `demo.api.Outer$Inner`, used when calling `ClassLoader.loadClass(String)` or `Class.forName(String, boolean, ClassLoader)` for ordinary classes.

Inside a class file or JAR, the resource path is typically `demo/api/Service.class`, whereas the string passed to `loadClass` is `demo.api.Service`. Do not use slash-separated paths as class names when calling this API.

**Notable exceptions:** `String[].class.getName()` returns `[Ljava.lang.String;`, and `int[].class.getName()` returns `[I`. That is the array class naming syntax, not a top-level ordinary binary name. `int.class` is a primitive type and has no `int.class` file for a custom loader to define. Hidden classes defined via specialized APIs also have their own naming and lookup rules; `Class.forName` is not a mechanism for finding hidden classes by name.

## 2. Defining Loader Differs from Initiating Loader

This is the most important distinction of the topic.

- **Defining class loader**: the loader that actually **defines** the class/interface from its binary representation, typically via `defineClass(...)`. For an ordinary class defined by a user-defined loader, `SomeClass.class.getClassLoader()` identifies that loader. Classes loaded by the bootstrap loader normally return `null`.
- **Initiating class loader**: the loader that **starts** a class-loading request. It may define the class itself, or delegate to another loader and receive back the same `Class<?>` object. A class may be recorded as having been initiated by multiple loaders, yet there is still only one defining loader for that class.

The standard flow of `ClassLoader.loadClass(name, resolve)`, unless overridden by a subclass, is:

~~~text
L.loadClass("demo.lib.Widget")
    |
    +-- findLoadedClass(name): has L already loaded a class with this name?
    |
    +-- parent.loadClass(name): ask the parent first
    |       |
    |       +-- if parent finds it: return Class defined by parent/ancestor
    |
    +-- findClass(name): if parent cannot find it, L tries to locate and define it
            |
            +-- defineClass(...) -> Class defined by L
~~~

That is the **parent-first delegation** principle of the default implementation. `URLClassLoader` also follows this behavior if left unaltered. A custom class loader can implement another strategy (such as child-first for plugin-private packages), but it must uphold JVM rules, type consistency, and API boundaries.

Consequence:

~~~java
Class<?> value = Class.forName("demo.lib.Widget", false, childLoader);
ClassLoader defining = value.getClassLoader();
~~~

`childLoader` is **the loader asked to start the search**, not necessarily `defining`. If the child delegates to its parent and the parent already has `demo.lib.Widget`, then `defining` is the parent. The `false` argument in `Class.forName(name, initialize, loader)` only means **do not request class initialization right then**; it does not assert that no loading/linking activity has occurred.

Example where two different loaders `left` and `right` both succeed via the parent:

~~~text
left.loadClass("demo.lib.Widget")  ---+
                                      +--> parent-defined Widget.class
right.loadClass("demo.lib.Widget") ---+
~~~

The result can be `leftResult == rightResult`. Therefore, the statement "two different class loaders necessarily mean two different types" is **false if both loaders are merely delegating**.

## 3. How to Check Whether Two Runtime Types Truly Match

For ordinary classes/interfaces, we have the table:

| Binary name | Defining loader | Type identity conclusion |
| --- | --- | --- |
| Different | Any | Two different types |
| Same | Same defining loader | Same runtime type (same `Class` object in the JVM) |
| Same | Two different defining loaders | **Two different types** even if source/bytecode are identical |
| Same | Two different initiating loaders delegating to one defining loader | **Still the same type** |

In Java, the simplest and most accurate way to compare the identity of **already loaded** types is:

~~~java
boolean sameRuntimeType = a == b;  // a, b are Class<?>.
~~~

Do not use `a.getName().equals(b.getName())` in place of the comparison above. Two equal names only prove the same **name**, not the same **type**.

Different type identities directly affect:

- **`instanceof`/`Class.isInstance` and casts**: an instance created from type A cannot automatically be assigned to type B merely because the two classes share the same string name.
- **Reflection**: parameter types for `getMethod`, `getDeclaredMethod`, and `Method.invoke` must match the actual `Class` objects; signatures written with the same string name in two loaders do not make the two types equal.
- **Field/method signatures and bytecode linking**: the JVM enforces loader constraints to preserve type consistency in inheritance and linked methods; violations can lead to `LinkageError`.
- **Runtime package access**: the runtime package of a class/interface is determined by **package name and defining loader**. Two classes that both declare `package demo.spi;` but are defined by two different defining loaders are not members of the same runtime package; having the same package string does not grant package-private access across that boundary.
- **Per-class caches/registries**: using the binary name string as the sole key in a multi-loader system can cause collisions. Once you have `Class<?>`, use that object itself as the key when lifecycle permits; if stored long-term, account for the risk of strongly retaining old class loaders.

### Does "Same Class File" Guarantee the Same Type?

No. Identical bytecode is a condition about **content**, not about **runtime identity**. Two separate `URLClassLoader` instances can both read the same directory containing one `.class` file and each loader can define its own class. The JVM treats the two resulting `Class` objects as two different types.

### Is "Same Class Loader" Enough?

If you mean the exact **defining loader** and the same **class/interface binary name**, then yes. A JVM does not let one loader redefine the same binary name into two independent ordinary classes. If you mean "the same loader that I called `loadClass` on," that might only be the initiating loader, so you must look at `Class.getClassLoader()` on the result.

## 4. Complete Java 17 Example: Two Loaders Defining the Same Class Name

The goal of this example is to demonstrate a controlled scenario:

1. The host shares an interface `demo.api.Action`.
2. The plugin has a class `demo.plugin.ActionImpl`; the host **does not** put this class on the parent classpath.
3. The host creates **two independent URLClassLoader instances** pointing to the same directory containing `ActionImpl.class`.
4. Each `URLClassLoader` must define `ActionImpl` itself because the parent cannot see that class.
5. The two classes have the same binary name but different runtime identities; instances can still be used through the shared API interface.

Initial directory tree:

~~~text
src/
└── demo/
    ├── api/
    │   └── Action.java
    ├── plugin/
    │   └── ActionImpl.java
    └── host/
        └── ClassIdentityDemo.java
~~~

### 4.1. Public Interface Owned by the Host

File `src/demo/api/Action.java`:

~~~java
package demo.api;

public interface Action {
    String run();
}
~~~

In a plugin architecture, the shared API must be defined once at a boundary visible to both host and plugins. In this example, `Action.class` is loaded from the application classpath. Both plugin loaders use `Action`'s own loader as their parent so they see the exact same interface `Class` object.

### 4.2. Implementation Isolated in the Plugin

File `src/demo/plugin/ActionImpl.java`:

~~~java
package demo.plugin;

import demo.api.Action;

public final class ActionImpl implements Action {
    @Override
    public String run() {
        return "ready";
    }
}
~~~

This class is compiled into a separate `out-plugin` directory without putting `out-plugin` on the classpath when running the host. Both loaders see the bytecode from the same directory, yet each loader has its own runtime namespace for classes it defines itself.

### 4.3. Host Discovering and Comparing Types

File `src/demo/host/ClassIdentityDemo.java`:

~~~java
package demo.host;

import demo.api.Action;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class ClassIdentityDemo {
    private static final String NAME = "demo.plugin.ActionImpl";

    public static void main(String[] args) throws Exception {
        URL url = Path.of("out-plugin").toAbsolutePath().toUri().toURL();
        ClassLoader apiLoader = Action.class.getClassLoader();

        try (URLClassLoader left = new URLClassLoader("plugin-left", new URL[]{url}, apiLoader);
             URLClassLoader right = new URLClassLoader("plugin-right", new URL[]{url}, apiLoader)) {
            Class<?> a = Class.forName(NAME, false, left);
            Class<?> b = Class.forName(NAME, false, right);

            System.out.println("binary names equal: " + a.getName().equals(b.getName()));
            System.out.println("Class objects identical: " + (a == b));
            System.out.println("defining loaders different: " + (a.getClassLoader() != b.getClassLoader()));
            System.out.println("left defined by left: " + (a.getClassLoader() == left));
            System.out.println("right defined by right: " + (b.getClassLoader() == right));
            System.out.println("shared API: " + (Action.class.isAssignableFrom(a)
                    && Action.class.isAssignableFrom(b)));

            Object instanceB = b.getDeclaredConstructor().newInstance();
            System.out.println("left accepts right instance: " + a.isInstance(instanceB));
            System.out.println("as common API: " + ((Action) instanceB).run());

            try {
                a.cast(instanceB);
                System.out.println("cross cast succeeded");
            } catch (ClassCastException expected) {
                System.out.println("cross cast: ClassCastException");
            }
        }
    }
}
~~~

**Explanation of key choices:**

- `Class.forName(NAME, false, left/right)` uses **the same binary name** in both loads; the result is two `Class` objects. The `false` flag avoids requesting class initialization right at the lookup step.
- `Action.class.getClassLoader()` is used as the parent for both `URLClassLoader` instances, so the shared API is not loaded twice.
- `out-plugin` sits only in each loader's own search URL, not on the host classpath. This guarantees the parent loader does not load `ActionImpl` first and defeat the experiment.
- `a.isInstance(instanceB)` checks whether an instance from the right loader belongs to the type defined by the left loader. The `false` result does not depend on whether the bytecode is identical.
- `(Action) instanceB` succeeds because both implementations point to **one** shared `Action` type.
- `a.cast(instanceB)` throws `ClassCastException` because `a` and `b` are two distinct runtime types despite having the same string name.

### 4.4. Compiling with Java 17 and Running

From the directory containing `src`, using PowerShell on Windows:

~~~powershell
javac --release 17 -d out-api src/demo/api/Action.java
javac --release 17 -cp out-api -d out-plugin src/demo/plugin/ActionImpl.java
javac --release 17 -cp out-api -d out-host src/demo/host/ClassIdentityDemo.java
java -cp "out-api;out-host" demo.host.ClassIdentityDemo
~~~

On Linux/macOS, simply replace the classpath separator in the `java` command with a colon:

~~~bash
java -cp "out-api:out-host" demo.host.ClassIdentityDemo
~~~

Remember **not to add `out-plugin` to `-cp`** for the host in the main run; the host code finds the plugin via the two `URLClassLoader` instances. The working directory when running must be the one containing `out-plugin` because the code calls `Path.of("out-plugin")`.

Exact stdout (compiled with `--release 17` and verified on the JVM):

~~~text
binary names equal: true
Class objects identical: false
defining loaders different: true
left defined by left: true
right defined by right: true
shared API: true
left accepts right instance: false
as common API: ready
cross cast: ClassCastException
~~~

This is direct proof: `a.getName().equals(b.getName())` is `true`, yet `a == b` is `false`; the defining loaders differ. The instances are incompatible under the implementation class, while the shared interface contract still works.

### 4.5. Reverse Experiment: Two Loaders but Only One Type

In the same example directory, if you deliberately add `out-plugin` to the host's classpath:

~~~powershell
java -cp "out-api;out-host;out-plugin" demo.host.ClassIdentityDemo
~~~

then the parent class loader now sees `demo.plugin.ActionImpl`. Because `URLClassLoader` defaults to parent-first, both `left` and `right` can delegate and find **the same `Class` defined by the parent**. Under this sample setup, you can expect `Class objects identical: true`, `defining loaders different: false`, and `a.cast(instanceB)` to succeed; the two lines `left defined by left`/`right defined by right` will be `false`.

That experiment explains why simply "creating two loaders" is not enough to assert there will be two types. You must control **the loading path, the parent classpath, and where the class is actually defined**.

## 5. Impact on Plugin Systems and SPI Contracts

A common plugin architecture looks like this:

~~~text
Host / application loader
    |
    +-- shared API: demo.api.Action
    |       (one shared type identity)
    |
    +-- plugin loader A
    |       +-- demo.plugin.ActionImpl  -> type A
    |
    +-- plugin loader B
            +-- demo.plugin.ActionImpl  -> type B

type A != type B
type A implements shared Action
type B implements shared Action
~~~

If you accidentally package `demo.api.Action` into each plugin and use a child-first strategy that also loads each plugin's copy of the API, then the host, plugin A, and plugin B can end up with **three separate `Class` objects for the same binary name `demo.api.Action`**. The host receiving an object and trying to cast it to its own `Action` can fail, or `ServiceLoader` may report that the provider is "not a subtype" because the service interface does not share the same type identity.

**Architectural rules:**

1. Place **service interfaces, DTOs, and types crossing the host–plugin boundary** in a shared class loader (typically the parent of plugin loaders).
2. Separate implementation code and plugin-specific dependencies so each plugin loader owns them when isolation is needed.
3. Do not let a plugin implementation class become a parameter/return type that the host must directly cast to. Communicate through shared interfaces/DTOs.
4. When a plugin is reloaded, the new version may be a new runtime type even with an identical binary name. Do not cast objects from the old version to the implementation class of the new version.
5. Registries should store structured plugin metadata (ID, version, source, loader/lifecycle); do not rely on `getName()` alone as a unique key if plugins can define classes with colliding names.

**Caveat:** identical names do not automatically mean two plugins behave identically; likewise, different names do not automatically express service compatibility. Both the API contract and type identity matter.

## 6. Runtime Packages and Access Boundaries

According to the JVMS, a runtime package is determined by **package name + defining class loader**. Consider:

~~~text
Loader A -> package demo.internal; class Helper
Loader B -> package demo.internal; class Bridge
~~~

Even though both declare `package demo.internal;`, the two classes belong to **two different runtime packages** if they are defined by loader A and loader B. You cannot deduce that `Bridge` may access package-private members of `Helper` merely because the package strings match.

If bytecode creates an illegal access linkage, the JVM may raise `IllegalAccessError` during actual resolution/linking. Whether an error is raised can depend on the linkage type and when the JVM performs checks; diagnose using the actual defining loaders rather than looking only at source packages.

In JPMS, `Module` and `ModuleLayer` additionally govern package readability/exports/opens, but they **do not replace the fundamental identity rule based on binary name and defining loader**. Two different module layers can use different loaders and create different type identities; however, being in two different layers alone is not sufficient proof of two different type identities if the class is actually shared/delegated.

## 7. Special Cases: Arrays, Primitives, Bootstrap, and Hidden Classes

The name-and-loader pair rule directly explains ordinary classes/interfaces. For special forms, note:

- **Array classes** have no separate bytecode file for `URLClassLoader.findClass` to read like ordinary classes; the JVM creates the corresponding array type. For an array whose elements are a reference type, the array's loader reflects the loader that defined that reference element type. Two `demo.plugin.ActionImpl[]` arrays whose component classes come from two different defining loaders are also two different array types. `Class.getName()` of the array uses the form `[Ldemo.plugin.ActionImpl;`.
- **Primitive types** such as `int` and `boolean` have special `Class` objects and are not defined by custom loaders. `int.class.getClassLoader()` returns `null`; `int[].class.getName()` is `[I`.
- **The bootstrap loader** is handled specially by the JVM and `Class.getClassLoader()` normally returns `null`, as for `String.class`. Do not infer that `null` means "no loader," nor compare the string `"bootstrap"` against a `ClassLoader` object.
- **Hidden classes** (`MethodHandles.Lookup.defineHiddenClass` API) are not ordinary classes that can be looked up through `Class.forName` by name alone. The name shown by `getName()` has a special suffix. Do not use hidden-class naming to design string-based plugin identifiers.

The common principle remains: once you have a `Class<?>`, use the identity of the `Class` object itself to check type equality; do not simulate comparison logic by slicing name strings.

## 8. Diagnosing Errors Arising from Multiple Class Loaders

To investigate an issue, log the **class name, defining loader object, module, and code source** (if available) for both sides. A helper function:

~~~java
import java.security.CodeSource;

static void inspect(Class<?> type) {
    ClassLoader loader = type.getClassLoader();
    CodeSource source = type.getProtectionDomain() == null
            ? null
            : type.getProtectionDomain().getCodeSource();

    System.out.println("name=" + type.getName());
    System.out.println("loader=" + (loader == null ? "<bootstrap>" : loader));
    System.out.println("module=" + type.getModule());
    System.out.println("source=" + (source == null ? "<unknown>" : source.getLocation()));
}
~~~

This is an **illustrative snippet placed inside a class**, not a standalone Java program with `main()`. The output of `loader.toString()`/`module.toString()` can vary by JDK and how the loader was created; do not use that display string as an identity key in your system. `CodeSource` may be `null` (or provide no location), so do not rely unconditionally on file paths.

| Symptom | Class loader cause worth checking | How to investigate |
| --- | --- | --- |
| `ClassCastException` with two seemingly identical class names | Same binary name but different defining loaders; or incompatible type relationship | Print `getClass()` and `getClassLoader()` of object/target class; compare `Class` with `==` |
| `ServiceConfigurationError: ... not a subtype` | Provider and host may have loaded two copies of the SPI interface with the same binary name | Inspect loaders of the host interface and provider interface; move shared API to parent |
| `NoClassDefFoundError` | Dependency could not be found/loaded in the needed loader; or caused by an earlier initialization failure | Inspect cause, classpath/module path, parent delegation, and prior error logs |
| `ClassNotFoundException` in `Class.forName` | Requested loader could not find the binary name via its lookup mechanism | Check `$` names, plugin URLs/JARs, and the loader passed in |
| `LinkageError` or loader constraint error | Signatures/interactions require the same runtime type, but loaders resolved incompatible types | Inspect types in field/method signatures and the loader of each type |
| `IllegalAccessError` across package/module boundary | Different runtime packages or accessibility/export violation | Check defining loader, module graph, exports/opens |
| Old class/plugin not unloaded after reload | Strong references remain to loader, class, instance, thread, listener, or `ThreadLocal` | Stop jobs/listeners, clear registries/caches, inspect heap dump and TCCL |

Errors that appear only during deployment or hot reload are often tied to **differences in classpath, class loader hierarchy, or already-loaded class state** compared to the build/test environment. Do not rush to patch around them with casts or reflection before pinpointing the exact defining loader on each side.

### Is the Context ClassLoader the Defining Loader?

Not necessarily. `Thread.currentThread().getContextClassLoader()` is a useful context for frameworks to find plugins or services depending on the API, but it **does not by itself determine** which loader will actually define a class. A call using the context loader can still delegate to a parent. If you temporarily swap the Thread Context ClassLoader to discover providers, always restore the old value in `finally`, especially on thread pools.

## 9. Design and Testing Checklist

When building a type-identity-safe plugin loading mechanism, verify:

1. **Input names are valid binary names**, especially for nested classes: `Outer$Inner`, not canonical names when the API requires binary names.
2. **Defining loader is verified** via `Class.getClassLoader()` on the result, not assumed from the loader passed to `loadClass`.
3. **Parent delegation and plugin paths are explicit**: verify implementation classes do not accidentally leak onto the parent classpath if isolation is the goal.
4. **Shared API has only one identity** wherever host/plugins reference it. Use `Action.class.isAssignableFrom(pluginClass)` or `Action.class.isInstance(instance)` to check before casting.
5. **Test same-named classes across two loaders**: compare `getName()`, `Class ==`, `getClassLoader()`, `isInstance()`, and casting via the shared interface.
6. **Test parent delegation**: create two different loaders where the class is actually defined by the parent; confirm the resulting `Class` objects are equal.
7. **Do not use just the name string as a runtime ID** in registries supporting multiple loaders or multiple plugin versions.
8. **Specify lifecycle and unloading**: stop accepting requests, drain in-flight work, release callbacks and reference holders, and close `URLClassLoader` to release open resources. `close()` **does not force GC/class unloading** and does not make already-created objects vanish immediately; the JVM can only reclaim them when reachability/reference conditions allow.
9. **Share types intentionally**: anything crossing the extension boundary (interfaces, DTOs, public exceptions) is loaded from the same API space; implementation dependencies can be isolated.

## 10. Knowledge Self-Check

**Scenario A:** Two different `URLClassLoader` instances both call `loadClass("demo.api.Action")`, and both delegate to their parent. Are they two types?

No. If both results are defined by the parent, `a == b` is `true` even though the initiating loaders differ.

**Scenario B:** Two `URLClassLoader` instances each read the exact same `demo/plugin/ActionImpl.class` file without delegating the implementation class to the parent. Can you cast an instance of A directly to B's `ActionImpl`?

No. Same binary name and bytecode, but different defining loaders, so different runtime types. You can use a shared interface if that interface has the same type identity on both sides.

**Scenario C:** Two classes both declare `package demo.internal;` but are defined by different loaders. Can they automatically use each other's package-private members?

No. A runtime package also depends on the defining loader, not just the package name string.

**Scenario D:** Calling `Class.forName(name, false, child)` yields `result.getClassLoader() == parent`. Did the JVM pick the wrong loader?

No. Child was the initiating loader; parent defined the class according to delegation rules.

## Authoritative References

- [JVMS 17, §5.3 – Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3): class/interface identity by binary name and defining loader; initiating loaders, constraints, and runtime packages.
- [ClassLoader – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findLoadedClass`, `findClass`, `defineClass`, delegation model.
- [Class – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getName()`, `getClassLoader()`, `isInstance()`, `isAssignableFrom()`, and `cast()`.
- [URLClassLoader – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): loading bytecode from URLs and releasing resources on close.
