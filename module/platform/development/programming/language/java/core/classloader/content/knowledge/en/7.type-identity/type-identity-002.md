# Two Classes with the Same Name but Different ClassLoaders Are Two Different Types in Java

## 1. Type Identity Rules in the JVM

In Java, the fully qualified name of a class such as `com.example.Plugin` is important, but **knowing only the class name is not enough to identify a type at runtime**. For an ordinary class or interface, the JVM determines identity by **the pair consisting of its binary name and the class loader that defined it (defining class loader)**:

~~~text
Runtime type identity = (binary name, defining ClassLoader)
~~~

For example, suppose two independent loaders actually define bytecode for `com.example.Plugin`:

~~~text
Loader A -- defineClass("com.example.Plugin", bytes) --> Class A
Loader B -- defineClass("com.example.Plugin", bytes) --> Class B

Class A.getName() == "com.example.Plugin"
Class B.getName() == "com.example.Plugin"

Class A != Class B
~~~

Even if the two bytecode arrays are identical, the JVM can still create **two different runtime types** if they are defined by **two different defining loaders**. An object created from the first type is not automatically an instance of the second type; casting between them can cause a `ClassCastException`.

**Important condition:** two different `ClassLoader` objects do *not necessarily* produce two different classes. If both **delegate to the same parent** and the parent defines the class, they can receive **the exact same `Class<?>` object**. Only when there are **two distinct runtime definitions** by two different defining loaders does the "two different types" conclusion apply.

This article explains the mechanism, a runnable example on Java 17+, the difference between an initiating loader and a defining loader, the results of `instanceof` / `isInstance` / casting, `static` state, as well as how to diagnose errors in plugins and application servers.

## 2. Why Comparing Only Class Names Is Wrong

In Java source code, importing `com.example.Plugin` appears to refer to a single type. However, a runtime environment can consist of multiple class-loading domains:

- The main application loads APIs and dependencies using the application/system loader.
- A container creates a separate loader for each deployed application.
- Each plugin has its own loader, which may carry different library versions.
- Development tools, test runners, or hot-reload frameworks create new loaders when code changes.
- A runtime running multiple module layers may associate modules with different loaders.

Therefore, two pieces of code that both see the string `"com.example.Plugin"` may still be operating on two different `Class` objects.

Basic observations:

~~~java
Class<?> left = objectA.getClass();
Class<?> right = objectB.getClass();

boolean sameName = left.getName().equals(right.getName());
boolean sameType = left == right;

ClassLoader loaderA = left.getClassLoader();
ClassLoader loaderB = right.getClassLoader();
~~~

This is **illustrative code inside a method that already has two objects**, not a standalone program.

- `sameName` answers: **are the binary names the same?**
- `sameType` answers: **are they truly the same runtime type?**
- `getClassLoader()` indicates the loader that defined the type. For many core Java classes defined by the bootstrap loader, the result is `null`.
- Do not use `left.toString().equals(right.toString())` to determine whether two types are the same: some printed strings do not carry sufficient information about the defining loader.

This rule is tied to the JVM and the type verifier, rather than merely being a compiler class-naming convention.

## 3. Distinguishing Defining Loader and Initiating Loader

A **defining class loader** is the loader that actually **defines** a class from class file data or the corresponding valid definition mechanism. The runtime identity of the class is bound to that defining loader.

An **initiating class loader** is a loader that initiates class loading at the JVM's request, even when the work is ultimately delegated to another loader.

Consider the following scenario:

~~~text
ChildLoader.loadClass("example.Service")
        |
        v
ChildLoader delegates -> ParentLoader.loadClass("example.Service")
                                  |
                                  v
                            ParentLoader defines
                                  |
                                  v
               returns the same Class<?> to ChildLoader
~~~

`ChildLoader` may be the initiating loader of the request, but **ParentLoader is the defining loader** of `example.Service`. In that case, `Service.class.getClassLoader()` (or `loadedClass.getClassLoader()`) shows that the defining loader is the parent.

Loaders can maintain delegation relationships and cache results so that subsequent loads return the same `Class<?>`. Therefore, the statement "loaded the class through two different loaders" is **not enough** to conclude that there are two different types.

### Child-first is not the default

`ClassLoader.loadClass(String, boolean)` by default checks for an already-loaded class, tries the parent or bootstrap loader, and only then calls `findClass` on the current loader. This is the common **parent-first delegation** strategy. A custom loader can change the search strategy within its permitted scope, such as **child-first** when plugin libraries need to be isolated.

Do not assume that simply creating `new ClassLoader(parent)` isolates all classes. If it does not define the class name in question itself and the parent finds that class, it will normally return the class defined by the parent.

## 4. Complete Java 17+ Example: Two Classes with the Same Name, Different Runtime Types

The following example intentionally creates **two loaders that do not use the application loader as their parent** for the target class. Both read **the same compiled `Payload.class` file**; each loader calls `defineClass` to create a separate Class. The application still has the `Payload` copy loaded by the normal loader.

Create **two files in the same directory**.

### File Payload.java

~~~java
public class Payload {
    private static int counter;

    public static int next() {
        return ++counter;
    }

    public String text() {
        return "hello";
    }
}
~~~

The `Payload` class has a public default constructor, an instance method `text()`, and a static field `counter`. Naming the file `Payload.java` to match the public class name is required.

### File LoaderIdentityDemo.java

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public class LoaderIdentityDemo {
    static final class IsolatedLoader extends ClassLoader {
        private final byte[] payloadBytes;

        IsolatedLoader(byte[] payloadBytes) {
            super(null); // Parent is bootstrap, avoiding delegation to app loader
            this.payloadBytes = payloadBytes.clone();
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!name.equals("Payload")) {
                throw new ClassNotFoundException(name);
            }

            return defineClass(
                    name, payloadBytes, 0, payloadBytes.length
            );
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(Path.of("Payload.class"));

        Class<?> app = Payload.class;
        Class<?> first = new IsolatedLoader(bytes).loadClass("Payload");
        Class<?> second = new IsolatedLoader(bytes).loadClass("Payload");

        ClassLoader delegating = new ClassLoader(
                LoaderIdentityDemo.class.getClassLoader()) { };
        Class<?> delegated = delegating.loadClass("Payload");

        System.out.println("same name: "
                + app.getName().equals(first.getName()));
        System.out.println("app == first: " + (app == first));
        System.out.println("first == second: " + (first == second));
        System.out.println("delegated == app: " + (delegated == app));

        Object value = first.getDeclaredConstructor().newInstance();

        System.out.println("first.isInstance: "
                + first.isInstance(value));
        System.out.println("app.isInstance: "
                + app.isInstance(value));
        System.out.println("second.isInstance: "
                + second.isInstance(value));

        System.out.println("invoke method: "
                + first.getMethod("text").invoke(value));

        try {
            Payload cast = (Payload) value;
            System.out.println(cast.text());
        } catch (ClassCastException exception) {
            System.out.println("cast: ClassCastException");
        }

        System.out.println("app.next: " + Payload.next());
        System.out.println("first.next: "
                + first.getMethod("next").invoke(null));
        System.out.println("app.next again: " + Payload.next());
        System.out.println("first.next again: "
                + first.getMethod("next").invoke(null));
        System.out.println("second.next: "
                + second.getMethod("next").invoke(null));

        System.out.println("unnamed modules equal: "
                + (first.getModule() == second.getModule()));
    }
}
~~~

### Compile and Run

Using JDK 17 or later, open a terminal **in the directory containing the two files**:

~~~bash
javac --release 17 Payload.java LoaderIdentityDemo.java
java LoaderIdentityDemo
~~~

The program reads `Payload.class` using a relative path, so it must be run from the exact directory containing that file. No framework, dependencies, or Java agent are required.

**Exact stdout when run as above on a standard Java 17+ JVM:**

~~~text
same name: true
app == first: false
first == second: false
delegated == app: true
first.isInstance: true
app.isInstance: false
second.isInstance: false
invoke method: hello
cast: ClassCastException
app.next: 1
first.next: 1
app.next again: 2
first.next again: 2
second.next: 1
unnamed modules equal: false
~~~

### Analyzing the Results by Group

**1. Same name, but not the same Class.** `app.getName().equals(first.getName())` is `true` because both have the binary name `Payload`. However, `app == first` and `first == second` are both `false` because the three classes are defined by three different defining loaders.

**2. Parent delegation can lead to the same type.** `delegating` is a new loader whose parent is the loader of `LoaderIdentityDemo`. It does not define `Payload` itself, so it delegates to its parent; `delegated == app` is `true`.

**3. An object is only an instance of its exact type.** `value` is created using `first`'s constructor. Therefore `first.isInstance(value)` is true, while `app.isInstance(value)` and `second.isInstance(value)` are both false.

**4. Reflection does not erase type identity.** Calling `first.getMethod("text").invoke(value)` succeeds because the method belongs to `first` and the receiver also belongs to `first`. It returns `String`, a shared core type. However, casting `(Payload) value` requires the `Payload` referenced by the application code, namely the `app` version; the JVM detects the type mismatch and throws `ClassCastException`.

**5. Each class has its own static state.** `counter` exists separately in `app`, `first`, and `second`. Calls to `next()` produce independent sequences: `1, 2` on `app`; `1, 2` on `first`; `1` on `second`. This reflects the fact that static state is bound to each defined and initialized runtime class.

**6. Unnamed modules are also separate per loader.** In Java 9+, each class loader has its own corresponding unnamed module. Therefore `first.getModule() == second.getModule()` is `false` even though the two classes have the same binary name and bytecode.

This example does not attempt to redefine classes with names under `java.*`. The custom loader still delegates the loading of `java.lang.Object` and foundational Java classes to the bootstrap loader. The JVM enforces protective restrictions on which names/packages may be defined.

## 5. Why Must defineClass Actually Be Called?

The `findClass` method in the example contains:

~~~java
return defineClass(name, payloadBytes, 0, payloadBytes.length);
~~~

This is where the loader **defines the runtime Class from bytecode data**. The `name` argument must match the actual binary name inside the class file; trying to take the bytes of `Payload` and change the name to `Other` will not arbitrarily create a valid `Other` class. The JVM checks consistency and can throw `NoClassDefFoundError` or an appropriate class-definition error.

In contrast, the following code usually does **not** create a new type:

~~~java
ClassLoader app = Payload.class.getClassLoader();
ClassLoader childA = new ClassLoader(app) { };
ClassLoader childB = new ClassLoader(app) { };

Class<?> a = childA.loadClass("Payload");
Class<?> b = childB.loadClass("Payload");

System.out.println(a == b); // true if both delegate to the app's Payload
~~~

This is an **illustrative snippet**, assuming `Payload` is already on the application class path and the anonymous loaders do not override `loadClass` / `findClass`. `childA` and `childB` are two different loader objects, but **both receive the same Class from their parent**.

Nor can a single loader arbitrarily define the same binary name multiple times within the same namespace where it has already succeeded. Repeating an invalid definition can cause a `LinkageError` because the JVM enforces consistency in class definition.

## 6. Class.isInstance, instanceof, Casting, and Reflection

Suppose an object is created using the `Plugin` class defined by loader A:

| Operation | Meaning with two independent `Plugin` definitions |
| --- | --- |
| `pluginA.getName().equals(pluginB.getName())` | Can be `true` |
| `pluginA == pluginB` | `false` |
| `pluginA.equals(pluginB)` | `false`, because `Class` reflects type identity |
| `pluginA.isInstance(objectA)` | `true` for the matching object |
| `pluginB.isInstance(objectA)` | `false` if the two types have no appropriate compatibility relationship |
| Cast `(PluginB) objectA` | Typically `ClassCastException` |
| `pluginA.isAssignableFrom(pluginB)` | `false` for two completely independent classes |
| `pluginA.getDeclaredConstructor().newInstance()` | Creates an instance of the exact class defined by A, if the constructor is accessible |

**Do not infer cast compatibility merely by comparing names.** Test `Class.isInstance(Object)` or `Class.isAssignableFrom(Class<?>)` directly on the specific `Class` objects.

A class A can be a subtype of a shared interface `api.Service` defined by the parent loader, and another class B can also implement **that exact same shared interface**. Both objects can then be cast to the **shared `api.Service`**, even though the two implementations cannot be cast to each other. This is an important design for plugin systems.

### Member Types and Arrays

The binary name of a nested class may contain the `$` character, for example `example.Outer$Inner`. The type identity rule still uses **the full binary name + defining loader**. The `$` character itself does not represent a different loader namespace.

For array types, the JVM creates array classes via a special mechanism: `getClassLoader()` on a reference array corresponds to the loader of its element type. For example, if two versions of `Plugin` belong to two different loaders, the two corresponding `Plugin[]` array types are not the same runtime type either. Arrays with primitive elements such as `int[]` are represented by the bootstrap loader as `null` according to the API.

## 7. Two Sets of Static State, Two Class Initializations

Each runtime class has its own static field state and initialization lifecycle. In the example, the single name `Payload` is defined three times, so three separate `counter` variables exist.

Consider an illustrative class:

~~~java
public class SessionCounter {
    private static int count = initialize();

    private static int initialize() {
        System.out.println("Initializing SessionCounter");
        return 0;
    }

    public static int next() {
        return ++count;
    }
}
~~~

If loaders A and B each actually define a copy of `SessionCounter` from the same bytecode, each copy can run its own class initializer `<clinit>` upon first active use. Thus, the log `Initializing SessionCounter` can appear **once for A and once for B**. The two `count` sequences are independent.

Distinguish the two points properly:

- **Loading/linking** a class does not necessarily execute its static initializer.
- **Initializing** executes the prescribed class initialization procedure, at most one successful initialization per runtime Class.
- Creating multiple instances of the same Class does not re-run `<clinit>`.
- Defining a new class through another loader can have its own static state and initialization process.

This affects static singletons, static caches, logger registries, JDBC driver registries, thread-local registries, or libraries with an `initialized` flag. A "singleton" backed by a static field is in practice usually unique only **within the scope of a single class definition**, not an absolute JVM-wide singleton when multiple loaders exist.

## 8. Runtime Packages Also Depend on the Loader

Beyond type identity, the defining loader also participates in determining the **runtime package**: two classes with the same package name in source code but defined by different loaders do not automatically have package-private access to each other. Package-private access examples are examined in the dedicated article on runtime packages; the key takeaway here is that **the same source package does not guarantee the same runtime package**.

## 9. Distinguishing ClassNotFoundException, ClassCastException, and LinkageError

These errors occur at different stages:

| Symptom | Common cause |
| --- | --- |
| `ClassNotFoundException` | A name-based lookup API cannot find the class. |
| `ClassCastException` | The object is incompatible with the target runtime type, even if the class names match. |
| `NoClassDefFoundError` | The JVM cannot define a required class during linking/execution, or a prior class initialization failed. |
| `LinkageError` | A linking rule violation, such as a loading constraint requiring the same type. |

Two definitions with the same name do **not automatically** cause a `LinkageError`; identify the operation that triggers the error before addressing it.

## 10. Designing Plugins Properly with a Shared API

A plugin system needs to distinguish the **shared API contract** from each plugin's **private implementation**. The host and the plugin loaders all reference a single `api.Plugin` interface defined by a shared/parent loader, while each plugin can define its own `impl.*`. If each plugin loads its own copy of `api.Plugin`, casting to the host's interface can still fail.

When models that cannot be shared directly need to be isolated, convert them to DTOs belonging to the shared API or to an independent data protocol. The article on multi-loader boundary design covers parent-first/child-first configurations, runnable examples, versioning, and lifecycles.

## 11. Cases Where You May See the Same Loader Yet Different Class Lookup Results

### A loader can know many Classes, without defining all of them itself

In Java, calling `ChildLoader.loadClass(name)` can return a Class defined by the parent. In that case, the child loader participates in the loading process, yet `Class.getClassLoader()` does not point to it.

### A loader does not define two versions of the same name side by side

To load a new version of the same binary name in a plugin with its own loader, a **new loader** is typically created and lifecycle handoff is coordinated. Attempting to call `defineClass` a second time with the same name in the old loader is not how hot reload works.

### The same class file does not guarantee the "same Class"

Two loaders reading the exact same `Payload.class` can still define two independent runtime Classes. Conversely, two different class paths referencing a Class can still yield the same Class object through delegation.

### Both class names and bytecode contents have constraints

The JVM requires valid class files and consistent name constraints. Two loaders can define **different** bytecodes for the same binary name, leading to differences in API, data, or behavior; besides `ClassCastException`, you can also encounter `NoSuchMethodError`, `NoSuchFieldError`, or linkage errors if components expect incompatible versions.

## 12. Class.forName with a Specific Loader

When you need to choose a loader, use the three-parameter overload:

~~~java
Class<?> type = Class.forName(
        "com.example.Plugin",
        false,
        pluginLoader
);
~~~

This is an **illustrative snippet**, assuming `pluginLoader` is a real ClassLoader variable and the `com.example.Plugin` class exists within its search scope.

- The first parameter is the **binary name** of an ordinary class.
- The `false` parameter does not request class initialization immediately at the call.
- The last parameter is the loader **used to request loading**; the result may belong to a parent if delegation occurs.

When passing `true` instead of `false`, the API requests class initialization if needed. **Initialization does not turn two definitions with the same name into a single type**.

Be careful with the call that does not pass a loader:

~~~java
Class<?> type = Class.forName("com.example.Plugin");
~~~

This overload uses the caller's class loader according to the API rules and triggers type initialization; in complex plugins/containers, it may fail to find a class that a dedicated plugin loader can find. Do not equate the "caller's loader" with the "system class loader" or the TCCL in all environments.

## 13. Arrays, Reflection, Serialization, and Modules

### Arrays

If `Class<?> a` and `Class<?> b` are two reference classes with the same binary name but different defining loaders, their one-dimensional array types are also distinct. The JVM creates an array class based on its defined element type; there is no way to cast an `A[]` array to `B[]` merely because the two element types share the same name.

### Reflection

Reflection operates on **specific Class objects**. To invoke a method from type A on an object created by A, use `a.getMethod(...)` and the corresponding receiver. If you obtain `b.getMethod(...)` from type B and apply it to an incompatible object A, the call does not automatically "merge" the two definitions; the reflection API reports an appropriate error.

### Serialization

Traditional Java serialization stores class name and data structure information, but upon deserialization it must **resolve the name to a runtime Class** through a class resolution mechanism. Choosing the wrong loader can lead to a missing class or a type mismatch; having the same `serialVersionUID` does not erase type identity boundaries. For plugin applications, a neutral data protocol or a decoding process that selects the appropriate loader is typically needed.

### JPMS

Since Java 9, every Class belongs to a runtime module; call `type.getModule()` to inspect it. Two runtime Classes from two different loaders can belong to two different unnamed modules; named modules also have their own module readability (`reads`), package export (`exports`), package opening (`opens`), and class loading rules. Do not infer that identical module names automatically make two Classes from two loaders the same type.

### Garbage Collection and Class Unloading

A class can be unloaded when JVM conditions are met, particularly regarding the reachability of the loader that defined it and any remaining references. Holding long-lived references to a Class, ClassLoader, thread, TCCL, static cache, or plugin object can keep the old loader alive and prevent classes from being unloaded after a reload. You cannot "replace bytecode" inside an existing Class by deleting the .class file while its loader is still alive.

## 14. Investigation Checklist for "Same Name, Cannot Cast" Errors

When a `ClassCastException` or suspicious linkage error occurs, do not look only at the class name string in the stack trace. Gather evidence from the **two actual Class objects**:

~~~java
static void describe(Class<?> type) {
    System.out.println("name=" + type.getName());
    System.out.println("loader=" + type.getClassLoader());
    System.out.println("module=" + type.getModule());
}
~~~

This is an **illustrative snippet inside a Java class**, not a standalone program.

Steps to follow:

1. **Obtain the two actual Classes:** the side that created the object and the side performing the cast/call. When possible, compare `left == right`.
2. **Print the binary names:** `left.getName()` and `right.getName()`. The two names may be identical.
3. **Print the defining loaders:** `left.getClassLoader()` and `right.getClassLoader()`. Note that the loader of core classes may be `null`.
4. **Print the modules:** `getModule()`; also inspect the JAR/module source or class loading logs if needed.
5. **Inspect the loader graph:** parent-first vs. child-first, plugin isolation, app server deployment, TCCL.
6. **Look for duplicate APIs/JARs:** Is the host API bundled separately inside the plugin? Is a class with the same package/name being defined from two locations?
7. **Identify which stage the error occurs at:** class lookup, definition, linking, static initialization, reflection, or casting.
8. **Fix the type-sharing scope:** unify the loader for the shared API, replace the loader during hot reload, or use DTOs/protocols across the isolation boundary.

In OpenJDK/HotSpot, you can enable JVM unified logging to observe which classes are loaded and which source supplies the data:

~~~bash
java -Xlog:class+load=info LoaderIdentityDemo
~~~

This command applies to the example after compilation, and JVM logs depend on the version/environment, with **no fixed stdout**. Some logs do not show the full initiating/defining loader relationship; combine logs with `Class.getClassLoader()`.

## 15. Common Misconceptions

| Misconception | What to remember instead |
| --- | --- |
| "Same fully qualified name means same Java type" | Runtime type identity uses both the binary name **and the defining loader** |
| "Two different ClassLoader variables always produce two different Classes" | They can delegate and receive the same Class from a parent |
| "The .class files have the same hash, so casting works" | Identical bytecode does not cross defining loader boundaries |
| "Matching `obj.getClass().getName()` means casting is safe" | Use `isInstance` / `isAssignableFrom` and check actual Class identity |
| "Changing TCCL also changes the loader that defined the object" | TCCL only changes the context loader for APIs that use it; it does not alter the defining loader of an existing Class |
| "A static singleton is always unique across the entire JVM" | Static state is separated per runtime Class; each loader that defines its own copy gets separate state |
| "Packaging the API JAR inside every plugin is good practice" | It easily creates multiple API copies and causes host-side casts to fail |
| "Same-name errors only happen during casts" | The JVM also enforces loader constraints, which can fail during linking |
| "Reloading the class file with the old loader is a safe reload" | You typically need a new loader and to drop references to the old loader |
| "The `ClassLoader.toString()` string identifies the entire type" | Use the `Class<?>` object itself and its defining loader when debugging |

## 16. Self-Check Questions

1. **Two loader objects A and B call `loadClass("X")`, and both receive the same `Class<?>` from their parent. Are there two types X?** No; only one Class is defined by the parent in this scenario.
2. **Two loaders A/B validly call `defineClass` using the same bytes of X. Can `AClass.getName().equals(BClass.getName())` be true?** Yes; the names are equal, yet `AClass == BClass` is still false.
3. **Can an object that is an instance of X defined by loader A be directly cast to X defined by B?** No. The two types are independent; casting can cause a `ClassCastException`.
4. **Does a static int counter in two runtime X Classes share the same variable?** No. Each class definition has its own static state.
5. **Are two classes from different loaders with the same package in source code in the same runtime package?** No, because the runtime package also depends on the defining loader.
6. **Why should the host and plugins share a single API interface defined by a parent loader?** So that both resolve the same runtime type and casts/calls through that interface are checked consistently.
7. **If we print `obj.getClass().getClassLoader()`, are we looking at the initiating or defining loader?** The defining loader.
8. **If the host's class literal `X.class` and `loader.loadClass("X")` return two different Classes, what should you check?** Check the binary names, defining loaders, parent chain, path/JAR/module, isolation settings, and whether there is a duplicate copy of the API.

## Authoritative References

- **JVM Specification Java 17, `5.3` – Creation and Loading** (runtime identity, defining/initiating loader): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- **JVM Specification Java 17, `5.3.4` – Loading Constraints**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.4
- **Java Language Specification Java 17, `12.2` – Loading of Classes and Interfaces**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2
- **Java SE 17 API, java.lang.ClassLoader**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Java SE 17 API, java.lang.Class**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **Java SE 17 API, java.lang.reflect.Method**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html
