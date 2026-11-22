# Reflection and Choosing a Loader for a Class Name

## 1. The Core Problem: A Class Name Alone Does Not Determine the Runtime Class

In Java, reflection allows looking up a class by a string name, inspecting constructors/methods/fields, and creating instances or invoking methods at runtime. However, the question **"which name to use to look up the class?"** must always be accompanied by the question **"which class loader to use for the lookup?"**.

For example, the string `"plugin.OnlyChild"` is only a **binary name**. If that class resides in a plugin JAR/directory visible only to a child loader, the host's application loader may not be able to find it. In fact, two different loaders can define **two different runtime classes with the same binary name**.

According to the JVM model, the identity of an ordinary class is based on its **binary name + defining class loader**, not just the name string.

~~~text
                    Host / Application Loader
                    ├── ReflectionLoaderDemo
                    └── Shared API
                               |
              +----------------+----------------+
              |                                 |
       URLClassLoader A                   URLClassLoader B
       plugin.OnlyChild                   plugin.OnlyChild
         (Class A)                           (Class B)
              |                                 |
           same name and same bytes, but Class A != Class B
~~~

Therefore, the choice of loader affects:

- **ClassNotFoundException**: a loader cannot see the class even though the class exists in another source.
- **ClassCastException**: an instance of a class defined by loader B cannot be cast to the class of the same name defined by loader A.
- **Dependency linking**: whichever loader defines a class, the symbolic references in its bytecode are resolved by the JVM through the appropriate defining loader, not automatically through the loader of the code using reflection.
- **Initialization**: some class lookup APIs only load the class, while others actively initialize it, causing the `static { ... }` block to run.
- **Module access**: finding a `Class<?>` object does not guarantee permission to invoke a constructor or access private members.

This lesson focuses on **choosing a loader for a binary name when using reflection**, distinguishing `Class.forName`, `ClassLoader.loadClass`, TCCL, and class identity.

## 2. Class Lookup APIs by Name to Distinguish

| API | Loader used for lookup | Requests initialization? | When not found |
| --- | --- | --- | --- |
| `Class.forName("pkg.Type")` | Defining loader of **the calling class** | **Yes** | `ClassNotFoundException` |
| `Class.forName("pkg.Type", false, loader)` | Explicit `loader` | **Does not** actively initialize | `ClassNotFoundException` |
| `Class.forName("pkg.Type", true, loader)` | Explicit `loader` | **Yes**, if not yet initialized | `ClassNotFoundException` |
| `loader.loadClass("pkg.Type")` | The invoked `loader`, following its delegation policy | **Does not** actively initialize | `ClassNotFoundException` |
| `Class.forName(module, "pkg.Type")` | The module and the loader mechanism associated with that module | **Does not** link or initialize per this overload's contract | **`null`** when no matching class is found in the module |
| `SomeType.class` | Class literal known to the compiler/JVM through the current bytecode | Not a string-based lookup; does not actively initialize merely from using the literal | Appropriate compile/linkage error if the type is unavailable |

**Do not infer** that `Class.forName(name)` is equivalent to `Class.forName(name, true, Thread.currentThread().getContextClassLoader())`. According to the Java API, the single-argument overload uses the **defining class loader of the calling class** and **does not automatically use the TCCL**.

Similarly, `ClassLoader.loadClass(name)` is equivalent to the `loadClass(name, false)` overload by default per the API: it does not actively run the static initializer. The term `resolve` in the protected `loadClass(name, boolean resolve)` overload refers to **linking**, not the `initialize` flag of `Class.forName`.

### When Choosing loader=null

~~~java
Class<?> jdk = Class.forName("java.lang.String", false, null);
~~~

The snippet above illustrates the three-argument overload: `loader == null` here means requesting the **bootstrap class loader**, not retrieving the TCCL or automatically choosing the application loader. For application/plugin classes not visible to the bootstrap loader, passing `null` usually fails to find them.

For the same reason, `String.class.getClassLoader()` typically returns `null`: that is the Java API representation of the bootstrap loader, **not an indication that String has not been loaded**.

## 3. How to Choose a Loader Between Host and Plugin?

Suppose the host is run with:

~~~text
java -cp out/host ReflectionLoaderDemo out/plugin
~~~

The plugin files are located at:

~~~text
out/plugin/plugin/OnlyChild.class
~~~

The host application can create a dedicated `URLClassLoader` with root `out/plugin`:

~~~java
URL source = Path.of("out/plugin").toAbsolutePath().toUri().toURL();

try (URLClassLoader pluginLoader = new URLClassLoader(
        new URL[]{source}, Host.class.getClassLoader())) {
    Class<?> pluginClass = Class.forName(
            "plugin.OnlyChild", false, pluginLoader);
}
~~~

This is an **illustrative** snippet assuming `Host` and the corresponding imports exist; the complete program is in Section 6. By default, `URLClassLoader` uses parent-first delegation:

~~~text
Class.forName(name, false, pluginLoader)
                   |
                   v
          pluginLoader.loadClass(name)
                   |
        already loaded this name?
                   |
           ask parent loader
               /       \
          has class     no
              |           |
        return parent   search plugin URL
                          |
                        defineClass
~~~

Key points to remember:

- **Specifying `pluginLoader` does not guarantee that this loader itself defines the class.** If the parent already sees a class with the same binary name, the parent-first algorithm may return the parent's class.
- `clazz.getClassLoader()` reports the **defining loader** of the `Class<?>` object, not necessarily the loader that was originally passed in.
- `clazz.getName()` only returns the binary name; two classes from two loaders can have equal `getName()` values while `clazzA != clazzB`.
- If child-first delegation is needed, you must design a custom loading policy and manage API/loader identity boundaries. You cannot reverse the delegation order by changing the `initialize` parameter.

### Source and Runtime Classpath Are Not the Same

When compiling the host, if the host only uses reflection with string names, it **does not need a compile-time import** of the plugin implementation. At runtime, you should not put the plugin on the host's `-cp` if the goal is to demonstrate that the plugin is only visible through the child loader. If the plugin is also placed on the application classpath, the parent will be able to see the class and the child loader experiment will no longer demonstrate the difference accurately.

## 4. Class.forName, Loading, Linking, and Initialization

Phases to distinguish:

| Phase | Explanation | Runs `static` block? |
| --- | --- | --- |
| Loading | Creates or finds the `Class<?>` object through the loader mechanism. | Not automatically just from loading. |
| Linking | Verification, preparation, and resolution according to JVM rules. | Not initialization. |
| Initialization | Executes the class's static initializer if not yet initialized. | **Yes**, when an initializer exists. |

In the `Class.forName(name, boolean initialize, loader)` API:

- `initialize=false`: requests loading/linking according to the appropriate contract, but **does not actively initialize**. The JVM may perform some linking at any valid point; do not interpret this as "nothing has been linked yet".
- `initialize=true`: after the required lookup and linking steps, **actively initializes** the class if it has not been initialized yet.
- `Class.forName(name)` is equivalent to `Class.forName(name, true, callerDefiningLoader)` according to the Javadoc. The caller here is the class containing the call, not any logically related object or plugin class.
- `loader.loadClass(name)` only returns the `Class<?>` via the loader without requesting the initializer to run.

Example plugin definition:

~~~java
package plugin;

public final class OnlyChild {
    static {
        System.out.println("OnlyChild initialized");
    }

    public String message() {
        return "plugin says hello";
    }
}
~~~

When executed:

~~~java
Class<?> type = Class.forName("plugin.OnlyChild", false, pluginLoader);
System.out.println(type.getName()); // not actively initialized yet
Class.forName("plugin.OnlyChild", true, pluginLoader); // active initialization
~~~

This is only an **illustrative snippet** within a context that has `pluginLoader`; the standalone program will demonstrate the initialization timing in Section 6. Class literals, metadata queries, and normal loading are not equivalent to invoking `new`, calling a static method, or requesting initialization via `Class.forName(..., true, ...)`.

**Note:** If the class has already been initialized earlier, calling `forName(..., true, ...)` again **does not** re-run `static`. However, two different loaders define two runtime classes with the same name, so each copy has its own initialization process.

## 5. The Thread Context Class Loader (TCCL) Is Not a "Global Loader"

Java supports:

~~~java
ClassLoader context =
        Thread.currentThread().getContextClassLoader();
~~~

The TCCL is **a property of a thread**. It is commonly used by frameworks, service APIs, containers, or libraries to locate providers/resources according to the execution context. For example:

~~~java
ClassLoader old = Thread.currentThread().getContextClassLoader();
try {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    Class<?> plugin = Thread.currentThread()
            .getContextClassLoader().loadClass("plugin.OnlyChild");
} finally {
    Thread.currentThread().setContextClassLoader(old);
}
~~~

The snippet above assumes `pluginLoader` has already been created. You must **restore the old TCCL in finally**, especially with thread pools, so that subsequent tasks do not accidentally use the plugin loader and the loader is not kept alive unintentionally.

**However:** `Class.forName("plugin.OnlyChild")` on its own in the host code **does not automatically use the TCCL** that was just set. It still relies on the defining loader of the class containing the call; only the overload taking an explicit `loader` gives you direct control over the loader in this API.

The TCCL also does not change JVM rules when resolving bytecode symbolic references: according to the JVMS, when class D has a symbolic reference to class C, resolving the class reference uses **the defining loader of D**. The JVM does not consult the TCCL every time a dependent class is needed.

### When Should You Use the TCCL?

- When an API/framework **explicitly documents that it uses the TCCL**, for example the `ServiceLoader.load(ServiceType.class)` overload typically selects the context class loader.
- When the host intentionally wants code/libraries to locate implementations using the plugin loader as permitted by the framework.
- When compatibility must be maintained with an SPI/container that already relies on the TCCL.

If you are performing reflection by class name yourself, a more readable and testable approach is usually to **pass an explicit loader to `Class.forName(name,false,loader)`** rather than mutating thread state and hoping an API picks the right source.

## 6. Standalone Java 17+ Practice: Two Loaders and Reflection

Goal: the host program does not have the plugin on the application classpath; two URLClassLoader instances both see the same plugin files; each loader defines a separate runtime class.

### Source Tree

~~~text
example/
├── src/
│   ├── host/
│   │   └── ReflectionLoaderDemo.java
│   └── child/
│       └── plugin/
│           └── OnlyChild.java
└── out/
    ├── host/               (created after compilation)
    └── plugin/
        └── plugin/
            └── OnlyChild.class
~~~

### File src/child/plugin/OnlyChild.java

~~~java
package plugin;

public final class OnlyChild {
    static { System.out.println("OnlyChild initialized"); }

    public String message() {
        return "plugin says hello";
    }
}
~~~

### File src/host/ReflectionLoaderDemo.java

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class ReflectionLoaderDemo {
    public static void main(String[] args) throws Exception {
        URL source = Path.of(args[0])
                .toAbsolutePath().toUri().toURL();

        try (URLClassLoader first = new URLClassLoader(
                     new URL[]{source},
                     ReflectionLoaderDemo.class.getClassLoader());
             URLClassLoader second = new URLClassLoader(
                     new URL[]{source},
                     ReflectionLoaderDemo.class.getClassLoader())) {

            try {
                Class.forName("plugin.OnlyChild");
                System.out.println("caller unexpectedly found plugin");
            } catch (ClassNotFoundException expected) {
                System.out.println(
                        "caller loader: ClassNotFoundException");
            }

            Class<?> typeA =
                    Class.forName("plugin.OnlyChild", false, first);
            System.out.println("first defines plugin: "
                    + (typeA.getClassLoader() == first));
            System.out.println("loadClass same Class: "
                    + (typeA == first.loadClass("plugin.OnlyChild")));

            Thread current = Thread.currentThread();
            ClassLoader oldContext = current.getContextClassLoader();
            try {
                current.setContextClassLoader(first);
                try {
                    Class.forName("plugin.OnlyChild");
                    System.out.println("TCCL unexpectedly used");
                } catch (ClassNotFoundException expected) {
                    System.out.println("forName ignores TCCL: true");
                }
                System.out.println("explicit TCCL works: "
                        + (current.getContextClassLoader()
                            .loadClass("plugin.OnlyChild") == typeA));
            } finally {
                current.setContextClassLoader(oldContext);
            }

            System.out.println("request initialization");
            Class.forName("plugin.OnlyChild", true, first);

            Object instanceA =
                    typeA.getDeclaredConstructor().newInstance();
            System.out.println("reflection: "
                    + typeA.getMethod("message").invoke(instanceA));

            Class<?> typeB =
                    Class.forName("plugin.OnlyChild", false, second);
            System.out.println("same name: "
                    + typeA.getName().equals(typeB.getName()));
            System.out.println("same runtime Class: "
                    + (typeA == typeB));

            Object instanceB =
                    typeB.getDeclaredConstructor().newInstance();

            try {
                typeA.cast(instanceB);
                System.out.println("unexpected cast success");
            } catch (ClassCastException expected) {
                System.out.println(
                        "cross-loader cast: ClassCastException");
            }

            System.out.println("bootstrap represented as null: "
                    + (String.class.getClassLoader() == null));
        }
    }
}
~~~

**Design explanation:**

- `first` and `second` are **two different loader instances** receiving the same URL of the plugin directory.
- Both have the loader of `ReflectionLoaderDemo` as their parent, but the host does not include the plugin directory on `-cp`, so the parent does not have `plugin.OnlyChild`.
- `Class.forName(name)` inside the host searches using the caller defining loader, so it throws `ClassNotFoundException`.
- The `Class.forName(name,false,first)` overload succeeds in finding the plugin without actively initializing it.
- Changing the TCCL to first **does not** cause the `Class.forName(name)` overload to automatically use first.
- `Class.forName(name,true,first)` actively initializes the class defined by first.
- An instance from `second` cannot be cast to the class from `first` even though the binary name is identical.
- `try-with-resources` closes the URLClassLoader instances after the experiment finishes; closing a loader releases I/O resources and does not guarantee immediate class unloading.

### Compiling and Running on Linux/macOS

Inside the `example` directory containing the two sources:

~~~bash
mkdir -p out/plugin out/host

javac --release 17 -d out/plugin src/child/plugin/OnlyChild.java
javac --release 17 -d out/host src/host/ReflectionLoaderDemo.java

java -cp out/host ReflectionLoaderDemo out/plugin
~~~

### Compiling and Running on Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force out\plugin, out\host | Out-Null
javac --release 17 -d out\plugin src\child\plugin\OnlyChild.java
javac --release 17 -d out\host src\host\ReflectionLoaderDemo.java
java -cp out\host ReflectionLoaderDemo out\plugin
~~~

**Do not** add `out/plugin` to `java -cp`; doing so would allow the parent loader to find the plugin as well, changing the verification results.

### Verified Stdout

~~~text
caller loader: ClassNotFoundException
first defines plugin: true
loadClass same Class: true
forName ignores TCCL: true
explicit TCCL works: true
request initialization
OnlyChild initialized
reflection: plugin says hello
same name: true
same runtime Class: false
OnlyChild initialized
cross-loader cast: ClassCastException
bootstrap represented as null: true
~~~

The code was **compiled with `javac --release 17` and run on OpenJDK 21** with the plugin directory separated from the host classpath; stdout matches verbatim.

### Reading Each Point of the Output

1. **The caller loader fails** because `ReflectionLoaderDemo` is defined in the host loader, which cannot see the plugin directory.
2. **first defines plugin: true** confirms that the plugin is actually defined by first, rather than first merely acting as an initiating loader.
3. **loadClass same Class: true** shows that repeated lookups on the same loader do not re-define the class.
4. **forName ignores TCCL: true** proves that the single-argument overload does not automatically select the context loader.
5. **explicit TCCL works: true** proves that only when you **explicitly call** `contextLoader.loadClass` does the lookup use the selected context loader.
6. **request initialization**, followed by **OnlyChild initialized**: the class in first only runs its initializer when initialize=true is requested.
7. **reflection: plugin says hello**: reflection instantiated the object and then called the public instance method on the right `Class<?>`.
8. **same name: true / same runtime Class: false**: the binary name is the same, but the defining loaders differ.
9. The second **OnlyChild initialized** line appears when instantiating the class from second; it is **a different runtime class**, not the JVM re-initializing the class from first.
10. **cross-loader cast: ClassCastException** is a consequence of different type identities.
11. **bootstrap represented as null: true** illustrates how `Class.getClassLoader()` represents the bootstrap loader for `java.lang.String` on a standard JVM.

If you run this example with a different build tool or classpath, first verify that you have not accidentally included the plugin in the parent's source lookup, and have not generated class/plugin files inside the host output.

## 7. Reflection After Choosing the Right Class<?>: Access Permissions Must Still Be Checked

Having a `Class<?>` object is not enough for every reflection operation to succeed. Some common APIs:

| API | Meaning | Common errors |
| --- | --- | --- |
| `clazz.getConstructor(parameterTypes...)` | Finds a matching public constructor | `NoSuchMethodException` |
| `clazz.getDeclaredConstructor(parameterTypes...)` | Finds a directly declared constructor, including non-public ones | May require opening access when invoking |
| `clazz.getMethod("run", ...)` | Finds a matching public method, including inherited public methods | `NoSuchMethodException` |
| `clazz.getDeclaredMethod("run", ...)` | Finds a directly declared method, including private ones | Does not automatically grant permission to `invoke` |
| `constructor.newInstance(args...)` | Creates an instance (triggers initialization if needed) | `InvocationTargetException`, `IllegalAccessException`, etc. |
| `method.invoke(instance,args...)` | Invokes a method via reflection; static methods use a `null` target | Wrong receiver/args, access permissions, exception inside the method |
| `clazz.cast(object)` | Dynamic type cast against the `Class<?>` object itself | `ClassCastException` if the object belongs to a different runtime class |
| `clazz.isInstance(object)` | Tests type compatibility at runtime | `false` for a class with the same name from another loader |

In the example, `OnlyChild` has a public no-arg constructor and a public method, so `setAccessible(true)` is not needed. If the class/method is private or the package is not open, you must satisfy Java access and JPMS conditions.

### Modules: A Loaded Class May Still Disallow Deep Reflection

In Java 9+, a class in a **named module** is subject to its own readability, exports/opens, and access rules. `Class.forName` or `ClassLoader.loadClass` can return a `Class<?>`, yet code in another module may still be disallowed from calling its members if the package is not exported. For reflecting on private members, `opens p to caller.module;` may be required; if missing, `setAccessible(true)` may throw `InaccessibleObjectException`.

You should not fix this by opening every package or using `--add-opens` unconditionally. Prefer a **common SPI/interface in a shared loader/module**, expose a proper public API, and only open packages when deep reflection is genuinely needed.

### Why Not Use Class.newInstance?

`Class.newInstance()` has been deprecated since Java 9; that API handles and represents exceptions less clearly. You should use:

~~~java
Object instance = clazz.getDeclaredConstructor().newInstance();
~~~

This is an illustrative snippet, assuming the class has an accessible no-arg constructor and the variable `clazz` was resolved with the right loader. The constructor may throw an exception wrapped in `InvocationTargetException`; handle the root cause appropriately instead of swallowing the error.

## 8. Class.forName(Module, String): Selecting a Module, Not Just a Loader

Since Java 9, there is an overload:

~~~java
Class<?> type = Class.forName(module, "com.acme.plugin.Impl");
~~~

Here `module` is a specific `java.lang.Module` object. The differences according to the Java SE documentation:

- Looks up the class with the **binary name in the exact specified module**.
- **Does not link or run the initializer** per this overload's contract.
- If the class does not belong to that module or is not found, returns **`null`** instead of `ClassNotFoundException`.
- If the same loader defines multiple modules and the class name belongs to a different module, the overload can still return `null` because it requires **the exact module**.
- Finding the `Class<?>` does not automatically check whether the class is accessible to the caller. Accessing members must still obey module/access checks.
- Does not support looking up array classes by array descriptor name like the `forName(String,boolean,ClassLoader)` overload.

The snippet above is illustrative only, assuming a `module` variable exists. When using `ModuleLayer`, you can obtain a module from a resolved layer and use `Class.forName(module, binaryName)` to check a class belonging to a **specific module**; however, if the goal is service provider discovery, use `ServiceLoader.load(layer, service)` instead of manually scanning classes by string name.

**Distinguish clearly:** `Class.forName(Module,String)` is not a shorthand for `Class.forName(name, false, module.getClassLoader())`, because it also binds the class name to **the exact named module** and has its own contract regarding linking/errors/null.

## 9. Class Literals, Arrays, Nested Classes, and Binary Names

String names passed to `loadClass` and `Class.forName` must follow the appropriate syntax:

| Java type | Typical binary name | Notes |
| --- | --- | --- |
| `com.example.Widget` | `com.example.Widget` | Dots between packages |
| Member class `com.example.Outer.Inner` | `com.example.Outer$Inner` | `$` sign in the binary name of a member class |
| Array of a reference type | `[Lcom.example.Widget;` | JVM array descriptor form for the loader-based `Class.forName` overload |
| Array of `int` | `[I` | Descriptor form; the class loader of a primitive array is bootstrap/null |
| Primitive `int` | Do not use `Class.forName("int")` to get a primitive `Class` | Use `int.class` |
| Type in a module | Must have the matching module when calling the module overload | The module overload does not support array types |

The syntaxes above are neither the file path `com/example/Widget.class` nor a JAR URL name. Reflection accepts a **binary name**, and the loader applies its own policy to locate the byte source.

In addition, generic type parameters undergo **type erasure** at runtime; `List<String>` and `List<Integer>` do not automatically become two separate runtime classes merely because their generic type strings differ. If you need to inspect signatures/generic types, use the appropriate `java.lang.reflect.Type` APIs instead of treating a simple name string as complete type information.

## 10. The Loader Used to Resolve Dependencies May Differ From the Loader Chosen in Host Code

A dangerous misconception: the host uses `child.loadClass("plugin.Entry")` to obtain the entry, so all dependencies of the entry will be selected by the **host loader** or the **current TCCL**. That is incorrect according to JVM rules.

Example:

~~~text
HostClass (defined by AppLoader)
    |
    | reflection: child.loadClass("plugin.Entry")
    v
Entry (defined by ChildLoader)
    |
    | bytecode references plugin.Helper
    v
Helper is requested via Entry's defining loader
(per symbolic reference resolution rules)
~~~

When the JVM resolves a symbolic reference in the runtime constant pool of class D, **the defining loader of D** is used to load the target class. This helps explain why:

- A plugin can access dependencies visible to its child loader or its parent.
- A host class defined by the parent **does not automatically find** a dependency that exists only in the child when the host's bytecode contains that symbolic reference.
- Switching the TCCL does not automatically fix every `NoClassDefFoundError` in already-defined bytecode.
- Selecting the right `Class<?>` via reflection does not guarantee that all dependencies of that class are valid in the runtime environment.

For real-world plugins, you should place the **shared API in the parent**, put plugin-specific implementations/dependencies in the child, and create an API bridge. If the host needs a contract such as `api.Plugin`, both sides must use the exact same `Class<api.Plugin>` object rather than using reflection to exchange objects that do not share the same loader identity.

## 11. Loader Selection Process by Scenario

| Scenario | Appropriate choice |
| --- | --- |
| Class on the application classpath, used directly by the host | `SomeClass.class`, or `Class.forName(name)` when a dynamic name is truly needed |
| Class in a separate plugin URL | `Class.forName(name, false, pluginLoader)`, followed by reflection on the returned `Class<?>` |
| Need to actively run the plugin's static initializer | `Class.forName(name, true, pluginLoader)` if the name and loader are clearly determined |
| Need only metadata without initializing yet | `Class.forName(name, false, loader)` or `loader.loadClass(name)` |
| Framework explicitly documents using the TCCL | Temporarily set the TCCL and **restore it in finally** |
| Need an SPI provider | `ServiceLoader` with the right ClassLoader or ModuleLayer |
| Need a class from a specific named module | `Class.forName(module, binaryName)`, checking that the result may be null |
| Need to load from a JAR/directory | `URLClassLoader`, passing the exact package root/JAR URL and an appropriate parent |
| Need a shared interface between host/plugin | Place the interface in a shared parent loader/module and let the child delegate |
| Need a separate plugin version even when the parent has the same class name | Selective child-first class loading policy, with identity and dependency tests |
| Want to run untrusted code | Do not treat a class loader as a security sandbox; a separate isolation/security model is needed |

### Step-by-Step Debugging Checklist

1. Is the binary name exact? For nested member classes, did you use `$` where required?
2. Is the call `Class.forName(name)`, the loader overload, or `loader.loadClass(name)`?
3. Which loader defines the **caller** of the single-argument overload?
4. Is the class located in the correctly resolved URL/plugin root or module path?
5. Is parent-first returning the parent's version? Print `clazz.getClassLoader()` to identify the defining loader.
6. What is the current TCCL? Does the API being used **actually read the TCCL**?
7. Are you expecting `loadClass` to run the initializer, or confusing `resolve=true` with `initialize=true`?
8. Do two `Class<?>` objects share the same name but have different loaders? Use `a == b`, `isInstance`, or `cast` to determine this.
9. Which category does the exception belong to: `ClassNotFoundException`, `NoClassDefFoundError`, `ClassCastException`, `IllegalAccessException`, `InaccessibleObjectException`, or `ExceptionInInitializerError`?
10. If using JPMS, does the package have appropriate `exports`/`opens` for the caller module?
11. Did you modify the TCCL and forget to restore it, or close the loader too early?
12. Do the host and plugin share **the same defining loader for the SPI interface**?

### Common Pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `Class.forName(name)` reports not found, whereas `pluginLoader.loadClass(name)` finds it | The caller loader cannot see the plugin source | Select the plugin loader explicitly |
| Changing the TCCL still does not fix `Class.forName(name)` | The single-argument overload does not read the TCCL | Call the overload that accepts a loader |
| Both loaders load a class of the same name, yet casting fails | Different defining loaders create distinct type identities | Share the API contract through the parent |
| `static` block runs earlier than expected | Used `Class.forName(name)` or `initialize=true` | Choose `initialize=false` to retrieve metadata only |
| Class is loaded, yet calling a method raises `NoClassDefFoundError` | A dependency is not visible through the defining loader, or the class previously failed initialization | Inspect the cause/stack trace and the loader of the class containing the reference |
| `getDeclaredMethod` finds a private method, yet `invoke` fails | Java access/module opens does not allow it | Use a public API or open the package selectively |
| `Class.forName(module,name)` returns null | The name does not belong to that exact module, even if the loader defines another module | Verify the module identity and binary name |
| Plugin stops finding new classes after closing URLClassLoader | `close()` releases the source for new lookups | Manage loader lifecycle and streams appropriately |
| Log shows `clazz.getClassLoader() == null` | The class is defined by the bootstrap loader | This does not mean a "not yet loaded" state |

## 12. Self-Check Questions

**Question 1.** The plugin `plugin.OnlyChild` resides only in `out/plugin`. Why does `Class.forName("plugin.OnlyChild")` from the host fail while the overload passing `pluginLoader` succeeds?

**Answer:** The single-argument overload uses the defining loader of the caller class (host); the three-argument overload uses the specified loader. The host parent does not know about the plugin source, whereas the child has the corresponding URL.

**Question 2.** After setting the TCCL to pluginLoader, does calling `Class.forName(name)` automatically select the TCCL?

**Answer:** No. If you want to use the TCCL, you must **call an API that uses it** or pass `Thread.currentThread().getContextClassLoader()` to the three-argument overload.

**Question 3.** Two different URLClassLoader instances both read the same `plugin.OnlyChild` bytecode; why is `clazzA == clazzB` false?

**Answer:** The JVM distinguishes runtime classes by binary name **and defining loader**. Having the same name and the same bytes is not enough to produce the same Class object.

**Question 4.** `loadClass(name)` succeeded, yet `static { ... }` printed nothing; is that a loader bug?

**Answer:** No. A lookup does not automatically request initialization. Only `Class.forName(name,true,loader)` or an appropriate active use initializes the class if needed.

**Question 5.** How does `Class.forName(module,name)` differ from the three-argument overload?

**Answer:** It requires the class to be in a **specific module**, does not link/initialize per its contract, and returns null when the matching class is not found in the module instead of a checked `ClassNotFoundException`.

**Question 6.** Why is changing only the host thread's TCCL unlikely to fix a dependency error inside a plugin class?

**Answer:** The JVM resolves symbolic references using the defining loader of the class containing the reference; the TCCL only takes effect when an API/framework actively uses it.

## Official References

- [Class.forName and Class.getClassLoader, Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): overloads by name, loader, module; initialization; checking the defining loader.
- [ClassLoader, Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): parent-first delegation, loadClass, findClass, and loader identity.
- [Thread.getContextClassLoader, Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html#getContextClassLoader()): managing a thread's context class loader.
- [java.lang.reflect.Method, Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html): invoking methods via reflection and access permissions.
- [JVMS Java SE 21 §5.3 and §5.4.3.1](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html): defining loader, class identity, and symbolic reference resolution.
