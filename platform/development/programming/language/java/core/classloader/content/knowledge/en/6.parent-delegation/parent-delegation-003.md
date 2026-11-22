# The Role of a null Parent When Delegating to the Bootstrap Class Loader

## 1. The Problem to Understand

When creating a custom `ClassLoader` in Java, you can pass `null` as the parent:

```java
ClassLoader loader = new ClassLoader(null) { };
```

Many people read this snippet and conclude that "the loader has no parent, so it delegates to no one." That conclusion is **wrong for the default mechanism of `java.lang.ClassLoader`**.

In the `ClassLoader` contract, **a `null` parent is how the API represents delegation to the bootstrap class loader**. The bootstrap is the layer that loads the JVM's core classes; it is not directly represented by a regular `ClassLoader` instance. Therefore:

- `new ClassLoader(null) { }` creates a **new custom loader object**.
- `loader.getParent() == null` indicates that there is no **Java parent object**; when using the default `loadClass` algorithm, it will attempt to use the **bootstrap class loader** for the delegation step.
- It **does not turn the new loader into the bootstrap class loader**, does not disable the bootstrap loader, and does not give the new loader the ability to find application classes on the class path.
- After the bootstrap loader fails to find a class, the new loader can try to find the class itself via `findClass` if implemented; the default `findClass` inherited from `ClassLoader` throws `ClassNotFoundException`.

Key distinction: `null` is a **special marker in the Java API**, whereas the bootstrap class loader is a **real runtime mechanism** for loading foundational classes.

## 2. What Is a Parent and Why Is Bootstrap Represented by null?

A class loader can ask a higher-level loader to try finding a class first, following **parent delegation**. This mechanism allows classes across different loaders to share foundational types, such as `java.lang.Object` and `java.lang.String`.

In JDK 17, there are three commonly encountered built-in tiers:

```text
Bootstrap class loader
    (no public Java ClassLoader object)
                   ^
                   |  getParent() == null on the loader below
                   |
Platform class loader
                   ^
                   |
Application / system class loader
                   ^
                   |
Custom loader (if app is chosen as parent)
```

A typical example:

```java
ClassLoader platform = ClassLoader.getPlatformClassLoader();
ClassLoader system = ClassLoader.getSystemClassLoader();

System.out.println(platform.getParent() == null);
System.out.println(system.getParent() == platform);
```

In the default configuration of OpenJDK/HotSpot 17, the two lines typically print `true`, `true`. Details of the system loader can be configured or changed; do not infer the actual chain of every runtime solely from the diagram.

**Why not create `BootstrapClassLoader extends ClassLoader`?** In mainstream JVMs, the bootstrap loader is implemented at the JVM/native layer and is not exposed as a regular `ClassLoader` instance. Therefore, the API uses `null` in places like `getClassLoader()` and `getParent()` to represent that layer.

Do not confuse the **parent relationship in the class loading mechanism** with Java's `extends`: two class loader objects do not need to inherit from each other for one loader to be set as the parent of another.

## 3. The Default `ClassLoader.loadClass` Algorithm When the Parent Is null

For the default `ClassLoader.loadClass(String name, boolean resolve)`, the main mechanism can be expressed as follows:

1. Check whether the class has already been recorded as loaded by the current loader, using `findLoadedClass(name)`.
2. If not, try asking the **parent** to load the class. If the parent is `null`, execute the branch that loads via the **bootstrap class loader**.
3. If the parent/bootstrap cannot find the class, call `findClass(name)` on the current loader to give it a chance to define the class itself.
4. If `resolve=true` is requested, perform resolution per the API; return the found `Class<?>`. If all steps fail, throw `ClassNotFoundException`.

The following pseudocode only illustrates the mechanism and **is not an override that can be copied verbatim into Java**:

```text
loadClass(name, resolve):
    c = findLoadedClass(name)

    if c == null:
        if parent != null:
            try c = parent.loadClass(name)
        else:
            try c = bootstrap.loadClass(name)  // pseudocode:
                                               // there is no API variable "bootstrap"
        if c is still == null:
            c = findClass(name)

    if resolve:
        resolveClass(c)
    return c
```

In the actual Java implementation, `loadClass` also involves synchronization/parallel-capable loader rules and internal conditions. The pseudocode is intended to clarify **the delegation path when the parent is null**, not to replace the Java API documentation.

An example to trace through:

```text
customLoader = new ClassLoader(null) { }

customLoader.loadClass("java.lang.String")
    -> not yet loaded by customLoader itself
    -> parent == null -> ask bootstrap
    -> bootstrap already knows/defines String
    -> return String.class

customLoader.loadClass("com.example.App")
    -> not yet loaded by customLoader itself
    -> parent == null -> ask bootstrap
    -> bootstrap does not find this app class
    -> call customLoader.findClass("com.example.App")
    -> default findClass implementation has no way to locate this class
    -> ClassNotFoundException
```

The example results above assume that `com.example.App` is an application class not belonging to the bootstrap loader and that the loader has not been given custom `findClass` logic. If you implement `findClass` or choose a different parent, the outcome can change.

### Is Delegation Always Strictly Parent-First?

No. `ClassLoader.loadClass` provides the default parent-first algorithm. A subclass can override `loadClass` to implement a different lookup policy, provided it adheres to the relevant JVM/Java contracts. Therefore, a `null` parent **does not guarantee** that every custom loader follows the exact pseudocode branch above if it overrides the loading algorithm itself.

However, for `new ClassLoader(null) { }` **without overriding** `loadClass` and `findClass`, the behavior described above is what you need to understand.

## 4. Java 17 Program: A null Parent Still Loads Bootstrap Classes

Create the file **`NullParentDemo.java`**:

```java
public class NullParentDemo {
    public static void main(String[] args)
            throws ClassNotFoundException {

        ClassLoader isolated = new ClassLoader(null) { };
        ClassLoader app = NullParentDemo.class.getClassLoader();
        ClassLoader appChild = new ClassLoader(app) { };

        System.out.println("Parent is null: "
                + (isolated.getParent() == null));

        Class<?> str = isolated.loadClass("java.lang.String");
        Class<?> obj = isolated.loadClass("java.lang.Object");

        System.out.println("Delegated String: "
                + (str == String.class));
        System.out.println("Delegated Object: "
                + (obj == Object.class));

        System.out.println("String defining loader is bootstrap: "
                + (str.getClassLoader() == null));

        try {
            isolated.loadClass("NullParentDemo");
            System.out.println("Application class found");
        } catch (ClassNotFoundException expected) {
            System.out.println("Application class not visible");
        }

        System.out.println("App-parent finds application class: "
                + (appChild.loadClass("NullParentDemo")
                        == NullParentDemo.class));
    }
}
```

Compile and run with **JDK 17 from a standard class path**:

```bash
javac NullParentDemo.java
java NullParentDemo
```

Correct stdout in the stated environment:

```text
Parent is null: true
Delegated String: true
Delegated Object: true
String defining loader is bootstrap: true
Application class not visible
App-parent finds application class: true
```

Explanation of each output:

1. `isolated.getParent() == null` confirms that the new loader has an API parent of `null`.
2. `isolated.loadClass("java.lang.String")` and `loadClass("java.lang.Object")` succeed thanks to the bootstrap branch of the default algorithm.
3. `str == String.class` and `obj == Object.class` demonstrate that the loader receives **the same runtime class identity** as the existing core types; it does not create a new copy of `String` or `Object`.
4. `str.getClassLoader() == null` indicates that the **defining class loader** is the bootstrap loader. Do not confuse this with the `isolated` loader object, which **initiated** the `loadClass` call.
5. `isolated.loadClass("NullParentDemo")` fails because the bootstrap loader does not look up this application class, and the custom loader has no additional `findClass` implementation.
6. `appChild` uses the application loader as its parent, so it can delegate to find the application class itself; the resulting `Class<?>` equals `NullParentDemo.class`.

The example clearly distinguishes two properties:

- **Being able to call a loader to request loading a class** does not mean that loader itself **defines** the returned class.
- **Not seeing an application class** does not mean the bootstrap loader is broken. The loader simply does not have the right search path for the requested class.

## 5. Four Places Where null Appears That Commonly Cause Confusion

It is the same `null` symbol, but the API context determines its meaning.

| Expression | Meaning to Understand |
|---|---|
| `new ClassLoader(null) { }` | Creates a custom loader whose API-level parent is the bootstrap loader; it is still a separate loader object. |
| `loader.getParent() == null` | No parent `ClassLoader` object is returned; in the loader API model, null represents bootstrap. |
| `String.class.getClassLoader() == null` | The `String` class was defined by the bootstrap loader. Do not infer that String is not loaded yet. |
| `Class.forName("java.lang.String", false, null)` | Passing null as the loader: uses the bootstrap loader to find/load the type; `false` does not request initialization. |

### Null in `Class.getClassLoader()` Is Not Null in `getParent()`

`Class.getClassLoader()` reports the loader that **defined the represented runtime type** (for arrays, following the component type's loader rule). `ClassLoader.getParent()` reports the parent of **a specific loader object**.

Therefore:

```java
ClassLoader custom = new ClassLoader(null) { };
Class<?> type = custom.loadClass("java.lang.String");
```

Here:

- `custom` is **not null**: a new loader object has been created.
- `custom.getParent()` is **null**: it delegates up to the bootstrap layer via the default algorithm.
- `type.getClassLoader()` is **null**: the `String` definition is provided by the bootstrap loader.
- `custom == type.getClassLoader()` is `false`, because the left side is an object while the right side is `null`.

This is an important distinction when debugging class loaders: separate the **initiating loader** (where the request starts/is recorded) from the **defining loader** (which actually defines the class).

### Null in `Class.forName`

With the three-parameter overload:

```java
Class<?> c = Class.forName("java.lang.String", false, null);
```

The last parameter `null` requests lookup via the bootstrap loader. Meanwhile, `false` is the flag **not to request initializing** the class; that is different from "not loading."

For a class that exists only on the application class path, such as `NullParentDemo`, calling `Class.forName("NullParentDemo", false, null)` typically throws `ClassNotFoundException`, because the bootstrap loader is not responsible for searching the application class path.

## 6. Bootstrap Loader and System Loader Are Different

In a typical JDK 17 configuration:

- **Bootstrap loader** handles foundational classes such as `java.lang.Object` and `java.lang.String`; there is no public `ClassLoader` object representing it.
- **Platform loader** can be obtained via `ClassLoader.getPlatformClassLoader()`; it loads a subset of classes belonging to the JDK's platform modules.
- **System/application loader** is obtained via `ClassLoader.getSystemClassLoader()`; it typically handles the application class path and modules within its assigned scope.

Among the built-in loaders, **bootstrap sits at the very top** in the delegation model. However, do not generalize that every package starting with `java.` is always defined by bootstrap: JDK classes belonging to different modules may have different defining loaders. Check the actual class if you want to be sure.

Comparison table:

| Custom Loader Configuration | What Happens with Default `loadClass`? | Use Case |
|---|---|---|
| `new ClassLoader(null) { }` | Bootstrap first; then custom `findClass` (if any). Does not automatically see application classes. | An isolated loader that needs to explicitly define its own classes while sharing core classes. |
| `new ClassLoader(ClassLoader.getPlatformClassLoader()) { }` | The platform parent participates in delegation, which can continue to bootstrap. | Wanting access to foundational classes through the platform loader without using the application loader. |
| `new ClassLoader(ClassLoader.getSystemClassLoader()) { }` | Typically sees the classes that the system loader can provide, and only then falls back to custom logic. | A plugin or additional loader that needs to inherit the application's visibility. |
| `new ClassLoader() { }` | The no-argument constructor typically selects the system class loader as parent per the API. | A standard custom loader using the default parent. |

**Caution:** "seeing a class" in the table refers to **loader-based lookup/visibility**; it does not guarantee bypassing access constraints, module exports/opens, package integrity, or other JVM rules. In particular, the class loader mechanism is not a comprehensive security sandbox.

## 7. A null Parent Does Not Isolate Everything

A null-parent loader may not see other application classes under the default mechanism, yet it can still use `java.lang.Object`, `java.lang.String`, and many other bootstrap types. That is intentional in Java: all application types need to share the foundational runtime.

Implications:

- **It is not a "no Java core" environment.** Classes defined by the custom loader must still be verified/linked according to JVM semantics and can reference required core types.
- **JARs are not loaded automatically.** `new ClassLoader(null) { }` has no built-in mechanism to scan directories/JARs; when needed, you need an appropriate parent or a class-finding mechanism such as `URLClassLoader`/`findClass`.
- **It does not create a completely independent namespace.** Two runtime classes with the same binary name are considered the same type only if their runtime identities match (especially the defining loader); sharing `Object`/`String` does not turn application classes defined by two different loaders into the same type.
- **It is not a security boundary for running untrusted code.** Code is subject to bytecode verification, access rules, module boundaries, and other control mechanisms; a null parent does not replace a dedicated sandbox.

Example plugin scenario:

A host application provides the interface `com.example.api.Plugin` from the application loader; each plugin is loaded by a null-parent custom loader. When a plugin has a class `MyPlugin implements Plugin`, the JVM must resolve the name `com.example.api.Plugin` for the plugin class. If the null-parent loader cannot find this API interface, linking/lookup can fail even though the bootstrap loader already found `java.lang.Object`.

A common design is to have the plugin loader **delegate to the loader containing the shared API** or allow controlled lookup/shared packages. You must ensure that both the host and the plugin use **the same runtime definition** of the `Plugin` interface. If the plugin defines its own copy of the interface with the same name under a different loader, type compatibility issues will arise.

You should not set the parent to null merely because you want "isolated plugins" while overlooking dependency visibility and runtime type identity.

## 8. Additional Example: Inspecting the Bootstrap Layer and Parent Chain

Create the file **`LoaderChainDemo.java`**:

```java
public class LoaderChainDemo {
    public static void main(String[] args) {
        ClassLoader platform = ClassLoader.getPlatformClassLoader();
        ClassLoader system = ClassLoader.getSystemClassLoader();

        System.out.println("Object bootstrap: "
                + (Object.class.getClassLoader() == null));
        System.out.println("String[] bootstrap: "
                + (String[].class.getClassLoader() == null));
        System.out.println("Platform parent bootstrap: "
                + (platform.getParent() == null));

        System.out.println("System parent platform: "
                + (system.getParent() == platform));
        System.out.println("Main defined by system: "
                + (LoaderChainDemo.class.getClassLoader() == system));
    }
}
```

Run from the default class path using JDK 17 HotSpot/OpenJDK, without a custom system loader configuration:

```bash
javac LoaderChainDemo.java
java LoaderChainDemo
```

Stdout:

```text
Object bootstrap: true
String[] bootstrap: true
Platform parent bootstrap: true
System parent platform: true
Main defined by system: true
```

Because `String` belongs to the bootstrap loader, the array class `String[]` also has the corresponding defining loader; `String[].class.getClassLoader()` returns `null`. For arrays, the JVM creates the runtime array type according to its own rules; this is not a `String[].class` class file located on the class path.

The example uses `==` to check loader relationships rather than printing `toString()` or the loader's class name, because implementation names like `jdk.internal.loader.ClassLoaders$AppClassLoader` can change and are not a stable public contract.

**Example limitations:** a custom system class loader, a different module execution environment, or a different JVM implementation may cause some application-layer checks to produce different results. The takeaway to preserve is the null convention for bootstrap and the meaning of delegation.

## 9. A null Parent and the Loading, Linking, and Initialization Phases

`loadClass` locates/obtains a runtime class; it does not mean an instance has been created or the static initializer has run.

Three distinct activities:

1. **Loading:** finding/defining the runtime class via the appropriate loader.
2. **Linking:** verification, preparation, and resolution according to JVM rules.
3. **Initialization:** running the class's `<clinit>` upon an appropriate active use.

The statement:

```java
Class<?> type = isolated.loadClass("java.lang.String");
```

does not create a new `String` object. It obtains the `Class<?>` corresponding to the `String` type.

Similarly, `Class.forName("java.lang.String", false, null)` requests lookup via the bootstrap loader but does not request initialization because the flag is `false`. Do not confuse the initialization flag with the loader parameter: they control **two different dimensions**.

If the new loader's `findClass` defines an application class, the JVM still must verify/link/initialize the class according to its own rules; having a null parent does not bypass verification or grant special access privileges.

## 10. Common Pitfalls and How to Fix Them

### Pitfall: "null parent = no delegation"

**Reality:** The default `ClassLoader.loadClass` delegates through the bootstrap loader when the parent is null.

**How to verify:** `new ClassLoader(null) {}.loadClass("java.lang.String") == String.class` in a syntactically valid program; see the `NullParentDemo` example.

### Pitfall: "`getParent() == null` means the custom loader itself is the bootstrap loader"

**Reality:** `getParent()` returns the parent relationship, not the defining-loader identity of the loader object itself. The custom loader is still a separate `ClassLoader` instance.

**How to verify:** call `isolated.getClass()` or check `isolated != null`; it is still an existing object with its own `loadClass` method.

### Pitfall: "Creating `ClassLoader(null)` is enough to load the project's class files"

**Reality:** The default `findClass` throws `ClassNotFoundException`. The bootstrap loader does not arbitrarily scan the application's class path.

**How to fix:** choose a parent that sees the required classes, or write a loader that knows how to locate/define bytes from the appropriate source; ensure all shared types use the correct runtime identity.

### Pitfall: "Failing to load an application class means the bootstrap loader is not working"

**Reality:** The bootstrap loader is specifically tasked with loading the runtime's foundational classes. Getting `ClassNotFoundException` when requesting `NullParentDemo` from a null-parent loader that has not implemented a finder is expected.

**How to verify:** separate the question "can bootstrap find `String`?" from "can the custom loader find the application class?" Those two steps reveal which component lacks visibility.

### Pitfall: "Two classes with the same binary name in two loaders are guaranteed to be compatible"

**Reality:** The JVM determines runtime identity by **binary name + defining class loader**. `ClassCastException` or `LinkageError` can occur when loaders define incompatible copies.

**How to fix:** identify the loader that owns the shared API so that the plugin and host agree on how shared types are resolved; avoid accidentally duplicating API libraries across multiple loaders.

### Pitfall: "Parent-first is a mandatory rule enforced for every custom loader"

**Reality:** It is the default mechanism; a subclass can override `loadClass`. Customization must account for VM constraints and avoid breaking shared types.

**How to fix:** read the actual `loadClass` code of the custom loader instead of guessing solely from `getParent()`. If overriding, clearly document which cases prioritize the parent, which prioritize the child, and how foundational packages are protected.

### Pitfall: "`Class.getClassLoader() == null` means the Class object is null"

**Reality:** `String.class` is a real `Class<?>` object; only the defining loader property is represented by `null` in the API. Do not infer from a nullable loader that the class or object does not exist.

## 11. How to Choose a Parent in Practical Design

Before choosing `new ClassLoader(null)`, answer three questions:

1. **Which classes does this class loader need to see?** If it needs the application's shared API, choose an appropriate parent (e.g., the loader that defines the shared API); a null parent is usually insufficient.
2. **Which types must share the same runtime identity?** Interfaces/DTOs passed across the boundary between host and plugin should be provided consistently from a shared loader.
3. **How are the loader's own classes located?** Without a suitable finder, the new loader only receives classes from its parent/bootstrap and will not automatically load a new JAR.

Decision table:

| Goal | Potentially Suitable Setup | What to Check |
|---|---|---|
| Use JVM core classes | Null parent + default delegation may be sufficient | Do not expect application classes from bootstrap. |
| Plugin uses host's shared API | Parent is a loader that sees the shared API | The shared API must use the same defining loader. |
| Load classes from a separate JAR | Custom loader that knows how to find bytes/JARs, with parent chosen based on APIs to share | Avoid duplicate definitions of shared types. |
| Only obtain metadata of a core class | Use `Class.forName(name, false, null)` if the name belongs to bootstrap | The `false` flag relates to initialization; verify the exact class name. |
| Investigate `ClassNotFoundException` | Check the invoked loader, parent chain, `findClass`, and class/module path | Pinpoint the failure at the actual lookup layer. |

**Technical note:** Loading classes with `URLClassLoader` can be useful in some traditional Java applications, but for module systems or complex plugin loaders, you must consider module boundaries and lifecycle (for example, closing URLClassLoader resources when appropriate). A null parent does not automatically design a safe and consistent module/plugin system for you.

## 12. Self-Check Exercises

**Question 1.** Why can `new ClassLoader(null) { }` still load `java.lang.String`?

**Answer:** The default `loadClass` uses the bootstrap loader when the parent is `null`. The bootstrap loader supplies the runtime's `String` definition; the custom loader returns that `Class<?>`.

**Question 2.** Does calling `loader.getParent() == null` prove that `loader` itself is the bootstrap loader?

**Answer:** No. It only reflects the parent in the API of a loader object. Bootstrap is not represented by a regular `ClassLoader` object like a custom loader.

**Question 3.** Why does `new ClassLoader(null) { }.loadClass("com.example.App")` usually fail for an application class on the class path?

**Answer:** The bootstrap loader is not tasked with finding that application class; the custom loader has no finder if it does not override `findClass`. This is a loader lookup/visibility failure, not evidence that `App`'s bytecode is invalid.

**Question 4.** Are `ClassLoader.getSystemClassLoader()` and the bootstrap loader the same?

**Answer:** No. The system loader is the API loader that handles application classes in common configurations; the bootstrap loader is the foundational layer represented by `null` in the relevant APIs.

**Question 5.** A null-parent custom loader calls `loadClass("java.lang.Object")` and succeeds. Is the defining loader of `Object` the custom loader or bootstrap?

**Answer:** Bootstrap. The custom loader initiates the lookup and can be considered the initiating loader; the defining loader of `Object` is the bootstrap loader.

**Question 6.** If `loadClass` is overridden, does a null parent force the loader to consult bootstrap first?

**Answer:** This cannot be assumed solely from the parent property. The default parent-first algorithm does so; an override can change the lookup order, so you must inspect the code and JVM constraints.

**Question 7.** You need to call an interface `com.example.api.Plugin` on the host class path from a plugin class loader. What should you check before choosing a null parent?

**Answer:** The loader must be able to resolve the interface from the shared definition so that the plugin class can link and have a runtime type identity compatible with the host. A null parent only sees foundational classes unless an additional finder or shared lookup is provided.

## 13. Key Takeaways and References

- **`parent == null` in `ClassLoader`:** default delegation goes to **bootstrap**, rather than blocking all delegation.
- **`getParent() == null`:** represents a loader relationship; **`SomeClass.class.getClassLoader() == null`:** represents a class defined by the bootstrap loader.
- **`new ClassLoader(null) { }`:** creates a normal custom loader object; without a custom `findClass`, it cannot automatically load application classes absent from the bootstrap loader.
- **Having a non-null parent:** the default loader can see the set of classes visible to the parent. Choose the parent based on shared APIs and type identity.
- **Class identity:** binary name **plus** defining loader; the requesting loader may not be the defining loader.
- **Delegation ≠ initialization:** `loadClass` does not mean running `<clinit>` or creating an instance.

Further reading from the official documentation:

1. [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): constructor with parent, `getParent`, `loadClass`, `findClass`, platform/system loaders.
2. [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getClassLoader` and `forName`, representing bootstrap as null.
3. [JVM Specification 17 — Chapter 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): loading, linking, initialization, class loader identity, and linking constraints.
4. [JEP 261 — Module System](https://openjdk.org/jeps/261): built-in class loader model and runtime modules starting in Java 9.
