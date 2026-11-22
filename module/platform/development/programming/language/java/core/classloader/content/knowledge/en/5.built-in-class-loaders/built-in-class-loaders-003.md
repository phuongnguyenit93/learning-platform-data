# System Class Loader and Application Class Loader in Java

## 1. Goal and Core Answer

When learning about Java's **built-in class loaders**, two terms that easily cause confusion are **system class loader** and **application class loader (app class loader)**. In the common way of running applications on OpenJDK/HotSpot from Java 9 onward, they **usually refer to the same loader**: the built-in application loader, responsible for loading many application classes, especially classes on the **application class path**.

However, these two terms are not always synonymous in every configuration:

- **System class loader** emphasizes the **role exposed by the JVM/JDK API**: the object returned by `ClassLoader.getSystemClassLoader()`. Many static APIs such as `ClassLoader.getSystemResource(...)` use this system loader.
- **Application class loader** emphasizes the **built-in loader of the standard runtime environment** that typically loads application classes. In modern OpenJDK implementations, the implementation class name usually has the suffix `AppClassLoader`, but this is an **implementation detail**, not a public type name guaranteed by Java SE.
- If the application specifies the startup property `java.system.class.loader`, the JVM can use **a custom class loader** as the system class loader. In that case, you should not conclude that “system loader = the default AppClassLoader object”.
- An application can additionally use multiple **custom class loaders** for plugins, web applications, test suites, dynamic modules, or hot-reload mechanisms. Classes defined by child loaders are not necessarily defined by the system loader.

This lesson focuses on the roles, APIs, delegation relationships, class path/module path, empirical observations, and how to debug these two concepts in Java 17+.

## 2. Position of the Application/System Loader Among Built-in Loaders

In a typical JDK 17 environment, the parent delegation chain can be visualized as follows:

~~~text
Bootstrap Class Loader                (represented as null in many APIs)
         ↑  delegated to search for classes first
Platform Class Loader                 ClassLoader.getPlatformClassLoader()
         ↑
Application Class Loader              usually = ClassLoader.getSystemClassLoader()
         ↑
Custom Child Class Loader             if the program creates one and sets an appropriate parent
~~~

The arrows represent the **parent relationship and default delegation path**, not “subclasses” in the Java inheritance hierarchy. Class loaders are Java objects (except the bootstrap loader, which is implemented by the JVM via its own mechanism). The parent relationship of class loaders is also **not synonymous with** the `extends` relationship of the classes they define.

### Bootstrap loader

The bootstrap loader is responsible for many core classes of the Java runtime, for example `java.lang.String` in a standard JDK. When calling `String.class.getClassLoader()`, the result is typically **null** to represent the bootstrap loader; null does not mean that the class has not been loaded.

### Platform loader

Starting from Java 9, the **platform class loader** replaces the role formerly named the extension class loader (`ExtClassLoader`). It is obtained via `ClassLoader.getPlatformClassLoader()`; in a standard JDK 17 configuration, its parent is the bootstrap loader. It is associated with Java platform modules and class-loading delegation under the modern module mechanism. Do not use the Java 8 diagram with `lib/ext` to explain a Java 17 runtime.

### Application loader

The built-in application loader typically sits below the platform loader and loads application classes. In a program run with `java -cp out Main`, the `Main` class is typically defined by the application loader, and that is also the loader returned by `ClassLoader.getSystemClassLoader()`, unless customized at the system level.

Classes on the **class path** typically belong to the **unnamed module** corresponding to the loader that defines them. In Java 9+, a loader can also be associated with **named modules**. Therefore, “the application loader only knows about the class path” is an incomplete description in the modern module system.

> Safety rule: call the API to inspect the **specific loader object** running at runtime; do not infer solely from names like `AppClassLoader`, `Launcher`, or the internal file layout of the JDK.

## 3. The System Class Loader Is the Name of an API Role

Primary API:

~~~java
ClassLoader system = ClassLoader.getSystemClassLoader();
~~~

This is a **static method** of `java.lang.ClassLoader`. According to the API contract, it returns the system class loader used for the Java runtime's class-loading mechanism. In a typical Java environment, this call returns a non-null object.

Some related APIs:

| API | Purpose |
| --- | --- |
| `ClassLoader.getSystemClassLoader()` | Retrieve the system class loader currently used by the JVM |
| `ClassLoader.getPlatformClassLoader()` | Retrieve the platform class loader (Java 9+) |
| `ClassLoader.getSystemResource(String)` | Find a resource through the system class loader |
| `ClassLoader.getSystemResources(String)` | List resource URLs with the same name via the system loader |
| `ClassLoader.getSystemResourceAsStream(String)` | Open a resource using the system loader |
| `ClassLoader.loadClass(String)` | Request a specific loader to find/define a class by binary name |
| `Class.getClassLoader()` | Determine the **defining loader** of a specific runtime type |
| `Thread.currentThread().getContextClassLoader()` | Retrieve the **thread context class loader (TCCL)**; may differ from the system loader |

The following three operations answer three **different** questions:

~~~java
ClassLoader a = ClassLoader.getSystemClassLoader();        // System loader
ClassLoader b = MyApp.class.getClassLoader();               // Loader defining MyApp
ClassLoader c = Thread.currentThread().getContextClassLoader(); // TCCL
~~~

This is an **illustrative snippet**, assuming `MyApp` is an existing class. In common execution modes, a, b, and c may be the same object. In complex runtimes or with a custom system loader, these objects **can differ**. You should not substitute them for one another arbitrarily in libraries.

## 4. Application Loader: Common Name of the Built-in Loader

A JVM/JDK must support the class-loading system according to the specification, but the **internal Java class name** of the default loader is not a compatibility API for applications. On modern OpenJDK/HotSpot, a line observed via `getClass().getName()` may look like:

~~~text
jdk.internal.loader.ClassLoaders$AppClassLoader
~~~

This line is a **JDK-dependent output example**, not a contract that every JVM or release will always print the exact same string. The `jdk.internal.*` prefix indicates an internal implementation class; do not import it, do not cast to it, and do not write logic depending on this string name.

In a typical running application:

1. The JDK launcher prepares the runtime environment, including the class path or module path according to the passed arguments.
2. The application loader finds/defines the appropriate classes according to that configuration.
3. `ClassLoader.getSystemClassLoader()` typically returns that default application loader.
4. Library classes on the class path are also typically loaded by this loader if they have not already been handled by a parent or another loader.
5. Classes belonging to the Java runtime may be defined by the bootstrap or platform loader even when referenced from application code.

Therefore, **“a class used by the app” does not mean “a class defined by the application loader”**. For example, an application uses `java.lang.String`, but the `String` class belongs to the core loader; it does not shift to the app loader just because it is called from `main`.

## 5. Java 17+ Experiment: Printing Loaders and Parent Relationships

Create the file **SystemLoaderDemo.java** exactly as follows:

~~~java
public class SystemLoaderDemo {
    static class Marker {
    }

    private static String name(ClassLoader loader) {
        return loader == null ? "<bootstrap>" : loader.getClass().getName();
    }

    public static void main(String[] args) {
        ClassLoader system = ClassLoader.getSystemClassLoader();
        ClassLoader platform = ClassLoader.getPlatformClassLoader();
        ClassLoader mainLoader = SystemLoaderDemo.class.getClassLoader();
        ClassLoader markerLoader = Marker.class.getClassLoader();
        ClassLoader stringLoader = String.class.getClassLoader();
        ClassLoader context = Thread.currentThread().getContextClassLoader();

        System.out.println("system type: " + name(system));
        System.out.println("platform type: " + name(platform));
        System.out.println("main type: " + name(mainLoader));
        System.out.println("String: " + name(stringLoader));

        System.out.println("main == system: " + (mainLoader == system));
        System.out.println("Marker == main: " + (markerLoader == mainLoader));
        System.out.println("system parent == platform: "
                + (system.getParent() == platform));
        System.out.println("context == system: " + (context == system));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 SystemLoaderDemo.java
java SystemLoaderDemo
~~~

**Illustrative output on OpenJDK/HotSpot 17 in the default launcher configuration** (the `type` entries may vary across JDKs):

~~~text
system type: jdk.internal.loader.ClassLoaders$AppClassLoader
platform type: jdk.internal.loader.ClassLoaders$PlatformClassLoader
main type: jdk.internal.loader.ClassLoaders$AppClassLoader
String: <bootstrap>
main == system: true
Marker == main: true
system parent == platform: true
context == system: true
~~~

Explanation:

- `main == system` compares **ClassLoader object identity**, which is suitable for confirming that two variables point to the same loader.
- `Marker == main`: the member class `Marker` is generated by javac as a separate class and is typically defined by the same loader as the main class in this execution mode.
- `String: <bootstrap>`: an indication that the core class is loaded by the bootstrap loader.
- `system parent == platform`: true in the default configuration described above. If a custom system loader is present, its direct parent may be the original application loader; the expression may evaluate to false.
- `context == system` is a common result for the main thread from the standard launcher. A framework may change the TCCL per thread or per operation.

**Do not write business correctness tests requiring the class name to strictly equal `jdk.internal.loader.ClassLoaders$AppClassLoader`.** This is only a tool for observing the environment.

## 6. How Does Parent Delegation Work?

With the default `ClassLoader.loadClass(String, boolean)` implementation, the general processing flow is:

~~~text
loadClass("com.example.Widget")
        |
        v
Has this loader already loaded the class? -- Yes --> return Class<?>
        |
        No
        v
Call parent.loadClass(...) if parent != null;
if there is no parent, search using the bootstrap loader
        |
     found? ---- Yes --> return Class<?>
        |
        No
        v
Call findClass(...) on the current loader
        |
        +-- found --> may resolve --> return Class<?>
        |
        +-- not found --> ClassNotFoundException
~~~

Key distinctions:

- **Parent delegation** is the default class-lookup strategy provided by `ClassLoader`. A custom loader can override `loadClass` to apply a different policy (for example, child-first) within valid boundaries.
- **Loading** does not automatically imply **initialization**. `ClassLoader.loadClass("pkg.Type")` typically returns `Class<?>` without running the static initializer of Type solely because of this call.
- **Parent** is a relationship between loaders, not an `extends` relationship between two data types.
- The loader that invokes `loadClass` is the **initiating loader** of the request. The loader that actually defines a specific class is called the **defining loader**. Class.getClassLoader() reveals the defining loader; it may be a parent if delegation succeeds.
- If a parent has already defined `java.lang.String`, the app loader typically just receives the `Class` back from the parent. It does not need to define a second copy of `String` itself.

The diagram above is the basic mental model for the **class path and ClassLoader.loadClass**. When loading classes belonging to **named modules**, the JVM applies additional module mappings and rules; you should not assert that every class from a module goes through a strictly linear parent-first chain exactly as shown in the diagram.

## 7. System Loader, Class Path, and Module Path

### Class path

Traditional programs commonly use:

~~~bash
javac -d out src/com/example/Main.java
java -cp out com.example.Main
~~~

This is a **command template** that only works when the source file actually exists and the package/class match the path. `-cp` (or `--class-path`) specifies the directories/JARs where the application is allowed to search for classes. Classes found on the application class path are typically defined by the default app/system loader and belong to the **unnamed module** of the corresponding loader.

In Java 17, if there is a library JAR on the class path, determining the loader of that class still depends on whether the class may already have been loaded by a parent, whether a custom loader is present, or specific rules of the runtime environment. There is no guarantee that “everything on the execution path must be defined by the system loader”.

### Module path

JPMS-based applications can be run with a module path configuration:

~~~bash
java --module-path mods --module com.example.app/com.example.Main
~~~

This is also a **command template**, requiring the appropriate module to have been compiled and placed in the `mods` directory. With named modules, the JDK can associate modules with built-in loaders and apply rules for resolution, readability, exports, and package/module mapping. Therefore:

- **class path** and **module path** are not the same list;
- **system loader** is not synonymous with “any JAR on the class path”;
- **module visibility** and **class loading** are related but distinct mechanisms: being able to load a class by name does not mean code in every module is permitted to access its public API;
- `ClassLoader.getUnnamedModule()` returns the unnamed module associated with a loader, not all named modules in the system.

In projects using Gradle/Maven, the actual class path is configured by the build tool or launcher. The error “runs in the IDE, but `java -cp` cannot find the class” usually stems from missing entries on the class path/module path, not from missing a class named `AppClassLoader`.

## 8. The System Loader Can Be Replaced with a Custom Loader

Java supports configuring a system property at **JVM startup time**:

~~~bash
java -Djava.system.class.loader=com.example.CustomSystemLoader -cp out com.example.Main
~~~

This is a **syntax illustration** and cannot be run unless a compatible `com.example.CustomSystemLoader` class exists on the appropriate loading path. A valid custom system loader must satisfy the API requirements, including a **constructor accepting a ClassLoader parent**, so that the JVM can instantiate it. The API initializes the system loader through its own mechanism; a configuration missing the constructor, where the class cannot be found, or that throws an exception during initialization will cause setup to fail.

An example **sketching a custom component**, not a standalone runnable program unless compiled/placed on the proper class path:

~~~java
package com.example;

public class CustomSystemLoader extends ClassLoader {
    public CustomSystemLoader(ClassLoader parent) {
        super(parent);
    }
}
~~~

This snippet only inherits the default delegation behavior; it does not yet add its own bytecode lookup mechanism. Its purpose is to show the **constructor signature** required by system-loader customization, not a mandatory instruction that every application must use a custom loader.

In a standard JDK, when this configuration is enabled, the loader returned by `getSystemClassLoader()` is the custom instance, while the built-in application loader used to load the custom class typically serves as its parent during initialization. Therefore, the comparison:

~~~java
ClassLoader system = ClassLoader.getSystemClassLoader();
ClassLoader defining = Main.class.getClassLoader();
boolean same = (system == defining);
~~~

is an **illustrative snippet**; `same` should not be assumed to be true in every environment. The relationship and class-loading order depend on the JDK launcher, the custom loader, and how the Main class is defined.

Do not attempt to “replace the system class loader” after the JVM has already started by assigning a regular Java variable: the API provides no dynamic setter for that role. To select a different system loader, a valid configuration must be ready at the time the JVM sets up the system class loader.

## 9. Java 17+ Example: Checking Class Loading Without Initialization

Create the file **SystemLoadVsInitialize.java**:

~~~java
public class SystemLoadVsInitialize {
    static class Service {
        static {
            System.out.println("Service initialized");
        }

        static void hello() {
            System.out.println("Hello from Service");
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader system = ClassLoader.getSystemClassLoader();

        Class<?> type = Class.forName(
                "SystemLoadVsInitialize$Service",
                false,
                system
        );

        System.out.println("Found: " + type.getSimpleName());
        System.out.println("Defined by system: "
                + (type.getClassLoader() == system));

        Service.hello();
    }
}
~~~

Compile and run normally, without passing `-Djava.system.class.loader`:

~~~bash
javac --release 17 SystemLoadVsInitialize.java
java SystemLoadVsInitialize
~~~

**Exact expected stdout when running on a standard JDK 17+ with the default class path:**

~~~text
Found: Service
Defined by system: true
Service initialized
Hello from Service
~~~

Mechanism:

1. **Class.forName(binaryName, false, system)** requests looking up the type via the system loader with `initialize=false`. That is not a constructor invocation and does not require running `static { ... }` code.
2. `type.getSimpleName()` only reads class metadata; it does not trigger the static initializer to run in this example.
3. When `Service.hello()` is called (corresponding to `invokestatic`), the JVM ensures `Service` is initialized, so it prints **Service initialized** before the method body.
4. Accessing a class literal, obtaining Class<?>, or loading a class and executing its static initializer are **distinct** phases.
5. If a custom system loader actively defines the class according to its own policy, `type.getClassLoader() == system` may yield a different result; therefore, the `true` result is explicitly stated for the standard execution of this example.

The name `SystemLoadVsInitialize$Service` is the **binary name** of the nested class; the dot in the source syntax `SystemLoadVsInitialize.Service` cannot replace the `$` sign in a `Class.forName(String,boolean,ClassLoader)` call.

## 10. The Thread Context Class Loader Is Not by Default the System Loader

Some frameworks, SPI mechanisms, JNDI, service discovery, or plugin runtimes need to locate classes/resources that the library's own loader does not know about. The JVM provides the **thread context class loader** (TCCL) as a context reference for a thread:

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
ClassLoader system = ClassLoader.getSystemClassLoader();
~~~

This snippet is illustrative code. Many launchers set the main thread's initial TCCL to the system loader, but:

~~~java
thread.setContextClassLoader(customLoader);
~~~

can change it for the current thread (if environment security rules allow), without **changing the object returned by `ClassLoader.getSystemClassLoader()`**. Other threads may inherit the TCCL of the thread that created them or be reconfigured by a framework.

When a library supports SPI or plugins, trying to load every class with the system loader can miss classes that only exist in the application's or plugin's own loader. If an API recommends using the context loader, you should follow the API contract and preserve/restore the TCCL when temporarily changing it:

~~~java
ClassLoader old = Thread.currentThread().getContextClassLoader();
try {
    Thread.currentThread().setContextClassLoader(customLoader);
    // Call the API that requires the plugin's context loader.
} finally {
    Thread.currentThread().setContextClassLoader(old);
}
~~~

This is an **illustrative snippet**, assuming `customLoader` has already been created and the thread holds permission to modify the context. Restoring the TCCL is important in thread pools: subsequent tasks may reuse the same thread.

## 11. System Resources and Resource Naming Rules

With class loaders, resource names typically use **/** as a directory separator relative to the root of the class path/module resources, rather than dot-separated binary names:

~~~java
ClassLoader system = ClassLoader.getSystemClassLoader();

java.net.URL first = system.getResource("config/app.properties");
java.net.URL viaStatic = ClassLoader.getSystemResource("config/app.properties");
~~~

This is an **illustrative snippet**, depending on `config/app.properties` actually residing on the system loader's resource search path. When the system loader is the loader used by the API, both lookup calls describe the system resource lookup path, though details of module/resource visibility still depend on the Java runtime.

Comparison:

| API | Resource Naming Rules to Note |
| --- | --- |
| `ClassLoader.getResource("pkg/file.txt")` | Path name from the root; typically **without a leading /** |
| `SomeClass.class.getResource("file.txt")` | If it does not start with /, searches relative to the package of SomeClass |
| `SomeClass.class.getResource("/pkg/file.txt")` | If it starts with /, searches using an absolute path from the root of the Class resource lookup |
| `ClassLoader.getSystemResource("pkg/file.txt")` | Requests resource lookup through the system loader |

Do not confuse a **.class file** with a **binary name**: the class `demo.Widget` has a typical resource path of `demo/Widget.class`, whereas `Class.forName` uses the binary name `demo.Widget`.

When multiple JARs contain resources with the same name, the result of `getResource` may depend on the search path and the loader's policy. `getResources` helps enumerate multiple candidates; do not rely on a single fixed ordering as a business contract when the specification does not guarantee it.

## 12. Class Identity Depends on Both Binary Name and Defining Loader

In Java, two files containing bytecode representing the same class `com.example.Plugin` do not necessarily produce **the same runtime type**:

~~~text
Loader A --defines--> com.example.Plugin  --> Class object A
Loader B --defines--> com.example.Plugin  --> Class object B
~~~

When A and B actually **define** the same binary name themselves, the JVM treats them as **two distinct runtime types**. An object of type A cannot be automatically cast to type B merely because the package name and class name match; incompatibility can lead to a `ClassCastException` or a corresponding linkage error.

From this it follows that:

- Identical `Class.getName()` values are **not sufficient** to confirm the same type.
- `Class.getClassLoader()` returns the defining loader, helping distinguish them.
- Parent-first delegation typically causes two child loaders to receive the same `Class` defined by their parent, limiting the creation of multiple versions of a core API.
- Plugin loaders sometimes intentionally define their own classes to isolate dependencies, but they must agree on the shared interfaces/APIs between the plugin and the host.
- Static initialization state is also tied to **each runtime class definition**, not just the name string. Two different defining loaders can have two independent sets of static state for the same binary name.

The system/application loader is typically **one part of the class-identity system**, not the sole origin of every class executed on the JVM.

## 13. Handling ClassNotFoundException, NoClassDefFoundError, and Loader Issues

### ClassNotFoundException

When calling:

~~~java
ClassLoader system = ClassLoader.getSystemClassLoader();
Class<?> plugin = system.loadClass("com.example.Plugin");
~~~

this is an **illustrative snippet**: if the plugin only exists in another plugin loader, the system loader may throw `ClassNotFoundException`. The way to handle this is to use **the loader capable of finding the class**, configure an appropriate search path, or use a framework API that supports TCCL; do not default to fixing it by copying JARs indiscriminately to multiple places.

### NoClassDefFoundError

The JVM may throw `NoClassDefFoundError` when a class was available at compile time but its corresponding definition cannot be obtained at runtime, or when a previous initialization attempt failed (“Could not initialize class ...”). You should inspect the **cause and exact message** to distinguish between a missing runtime dependency, a transitively missing dependency, and a static initializer failure.

### ClassCastException Across Loaders

Two classes with the same binary name defined by two different loaders may not be castable to each other. When debugging, you should print:

~~~java
static void describe(Class<?> type) {
    System.out.println(type.getName());
    System.out.println(type.getClassLoader());
    System.out.println(type.getModule());
}
~~~

This is an **illustrative snippet within a Java class**, not a standalone runnable file. To avoid confusion, compare using `type1 == type2` once both are `Class<?>`, check the defining loaders, and review the parent delegation configuration. In a JPMS environment, you should also inspect the module and the package's exports/opens scope.

## 14. When to Use Which Loader?

| Need | Appropriate Loader/API and Reason |
| --- | --- |
| Inspect the JVM's system loader | `ClassLoader.getSystemClassLoader()` |
| Inspect the platform loader | `ClassLoader.getPlatformClassLoader()` |
| Determine the loader that actually defines a type | `SomeType.class.getClassLoader()` |
| Locate a resource in the same package as a library class | `SomeType.class.getResource(...)` (see path rules) |
| Load a class in the same loading scope as a library/object | That class's loader when appropriate for the API |
| Framework SPI/plugin requiring TCCL | `Thread.currentThread().getContextClassLoader()` per the framework contract |
| Load custom classes unknown to the system | A custom loader with an appropriate parent configuration and `findClass` mechanism |
| Load a class by binary name and control initialization | `Class.forName(binaryName, initialize, loader)` |
| Read a resource belonging to the system loader | `ClassLoader.getSystemResource(...)` / `getSystemResourceAsStream(...)` |

The choice of loader depends on **which scope the class/resource belongs to**, not merely on whether the code is executed from `main`, from a server, or from a JAR.

## 15. Common Mistakes and How to Avoid Them

1. **Asserting that the system loader is always `AppClassLoader`.** In standard configurations the two roles usually coincide; the system allows a custom system loader. Check via the API.
2. **Casting to `jdk.internal.loader.ClassLoaders$AppClassLoader`.** This is an internal implementation. Work only with the public `java.lang.ClassLoader` API.
3. **Assuming the system loader loads every class in the JVM.** Core classes are typically defined by the bootstrap loader, certain platform classes by the platform loader, and plugins possibly by custom loaders.
4. **Assuming `getSystemClassLoader() == Thread.currentThread().getContextClassLoader()` is always true.** Frameworks/thread pools can change the TCCL.
5. **Thinking a loader's parent is the superclass of the classes it defines.** Parent delegation is a mechanism between loaders, independent of Java type inheritance.
6. **Using a loader's `getName()` as a business contract.** Implementation class names can vary across JVMs/JDKs.
7. **Treating `loadClass` as synonymous with static initialization.** Loading/linking and initialization are distinct phases.
8. **Passing a nested class's canonical name to `loadClass`.** For nested member classes, a binary name such as `pkg.Outer$Inner` is typically required.
9. **Ignoring JPMS.** Named modules have their own class-lookup and accessibility rules; the class path and module path are not the same source.
10. **Changing the TCCL without restoring it.** Thread pools can reuse threads, causing subsequent tasks to resolve classes/resources with the wrong context.
11. **Seeing `NoClassDefFoundError` and immediately concluding a class file is missing.** A prior initialization failure can also leave a class in an erroneous state.
12. **Assuming two classes with the same fully-qualified name are guaranteed to be castable to each other.** Defining loaders and class identity must be taken into account.

## 16. Short Debugging Workflow for a Class-Loading Error

When a class/resource is found in the IDE but fails during actual execution:

1. Print `ClassLoader.getSystemClassLoader()`, `ClassLoader.getPlatformClassLoader()`, `Thread.currentThread().getContextClassLoader()`, and `ProblemType.class.getClassLoader()` if the type was already loaded.
2. Record how the process was launched: `-cp` / `--class-path`, `--module-path`, `--module`, VM arguments, and whether `-Djava.system.class.loader` is set.
3. Verify that the **binary name** has the correct package and `$` separator for nested classes, and that resources use the proper `/` path.
4. Identify where the JAR/class is supplied from: class path, module path, plugin directory, or a custom loader.
5. Check parent delegation and the TCCL that the library actually uses.
6. If the class is loaded but inaccessible, check exports/opens/module access, linkage errors, or initialization failures. Do not lump every issue under “class loader not found”.
7. When suspecting multiple versions of a class, print **name + defining loader + module** and compare the actual `Class<?>` objects.

In modern JDKs, depending on the Java version, you can enable JVM logging with `-Xlog:class+load=info` to observe class names and loading sources. The displayed information depends on the JVM and logging options; combine it with reflection to understand the **specific loader object** rather than inferring solely from file paths.

## 17. Self-Check

**Question 1.** In a Java 17 application running normally on the class path, which loader is `ClassLoader.getSystemClassLoader()` usually?  
**Answer:** The built-in application class loader, typically with the implementation name `AppClassLoader`. This is common JDK behavior, not a guarantee about the internal class name.

**Question 2.** What does `String.class.getClassLoader() == null` mean in a standard JDK?  
**Answer:** `String` is defined by the bootstrap loader; null is how the API represents the bootstrap loader, not the absence of a loader.

**Question 3.** If a thread has its TCCL pointing to a plugin loader, does `getSystemClassLoader()` change along with it?  
**Answer:** No. Changing a thread's TCCL does not change the JVM-wide system loader role.

**Question 4.** Does setting a custom loader as the system loader mean every application class will always be defined by it?  
**Answer:** No. Which loader defines a class depends on how the launcher locates classes, parent delegation, and loader policies; many classes may be defined by a parent.

**Question 5.** When `loadClass("com.example.Plugin")` succeeds, is it guaranteed that Plugin's static block has already executed?  
**Answer:** No. Loading is not automatically initialization; the initialization trigger point must be considered.

**Question 6.** Do two independent plugin loaders defining `com.example.Api` with identical bytecode create the same runtime class?  
**Answer:** No. Type identity consists of both the binary name and the defining loader; a single shared definition must be used if a shared runtime API is required.

**Question 7.** You need to read `config/service.properties` using the system loader. Should you use dots like a package or / like a path?  
**Answer:** Use `config/service.properties`, not `config.service.properties`, and typically do not put a leading / before the name for ClassLoader.getResource.

## Official Documentation for Reference

- Java SE 17 API — **ClassLoader**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 API — **Class**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 API — **Thread** (context class loader): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
- Java SE 17 API — **Module**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- Java Virtual Machine Specification, §5.3 **Creation of Classes and Interfaces**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- Java Virtual Machine Specification, §5.5 **Initialization**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- Java Language Specification, §12.2 **Loading of Classes and Interfaces**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2
