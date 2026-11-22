# Module.getClassLoader() and the limits of ClassLoader

## 1. The role of Module.getClassLoader()

Since Java 9, the Java Platform Module System (JPMS) adds the **java.lang.Module** class to represent a module loaded by the JVM. Each module is defined by a class loader. The **Module.getClassLoader()** method returns the class loader that defined that module.

    Module module = Main.class.getModule();
    ClassLoader loader = module.getClassLoader();

This approach is useful when you need to find out which module a class belongs to and which loader loaded that module. Typically, start from a class the application already knows, call **Class.getModule()**, and then obtain the loader from the corresponding Module object.

Two concepts must be distinguished:

- **Module** describes module boundaries: the module name, the modules it can read, exported or opened packages, and related relationships.
- **ClassLoader** is responsible for finding and defining classes. The loader participates in determining which Class object in the JVM a class name maps to.

One class loader can define multiple named modules as well as its own unnamed module. Therefore, the relationship between modules and class loaders is not necessarily one-to-one. You cannot deduce that every module always has its own loader, or that every module defined by the same loader is the same module.

In the JVM, a class's identity is tied to **the binary name of the class and the class loader that defined that class**. Two classes with the same fully qualified name defined by two different loaders are still two distinct types. This explains many type-casting or class-linkage errors in plugin applications, containers, and multi-loader environments.

## 2. Why can getClassLoader() return null?

If a module is defined by the **bootstrap class loader**, the method returns **null**. This is a valid value; it does not mean the module is missing or that obtaining the loader failed.

A typical example is the **java.base** module, where the String class resides:

    Module baseModule = String.class.getModule();

    System.out.println(baseModule.getName());        // java.base
    System.out.println(baseModule.getClassLoader()); // null

The bootstrap loader is the foundational loader managed by the JVM; applications do not receive a regular ClassLoader object representing it. Therefore, never directly call **loader.loadClass(...)** without handling the case where loader is null.

A safe check:

    Module module = Main.class.getModule();
    ClassLoader loader = module.getClassLoader();

    if (loader == null) {
        System.out.println("Module is loaded by the bootstrap loader: "
                + module.getName());
    } else {
        System.out.println("Class loader: " + loader);
    }

You should not mechanically replace a null result with **ClassLoader.getSystemClassLoader()**. The system class loader is a specific loader of the runtime environment; it is not a universal stand-in for every module and is not necessarily the loader that defined the module in question.

## 3. Obtaining a loader does not equal module access permission

This is the most important limitation when working with JPMS: **Module.getClassLoader() only tells you the loader bound to the module; it does not grant additional module read permissions, package access, or deep reflection.**

Access permissions between modules still obey the module configuration:

- **requires** declares read relationships between modules. A module normally must read the module containing types it uses.
- **exports** exposes a package to other modules according to Java's access rules. Export does not turn every private or package-private member into public API.
- **opens** permits deep reflective access to a package under JPMS-specified conditions. This is the mechanism typically needed when a framework uses reflection to access non-public members.

For example, if module A obtains module B's loader, that does not automatically allow A to use every class in B. You must simultaneously check read relationships, exported/opened packages, and standard Java access rules.

APIs such as **Module.canRead(...)**, **Module.isExported(...)**, and **Module.isOpen(...)** help check these aspects. They answer different questions from **getClassLoader()**:

    Module source = Main.class.getModule();
    Module target = Service.class.getModule();

    boolean canRead = source.canRead(target);
    boolean exported = target.isExported("com.example.service",
                                         source);
    boolean opened = target.isOpen("com.example.service",
                                   source);

The results must be interpreted according to the exact permission type being checked. An exported package does not mean that package is opened for deep reflection.

## 4. Using a loader to load classes: understand the search scope

When loader is non-null, you can call **ClassLoader.loadClass(String)**:

    ClassLoader loader = Main.class.getModule().getClassLoader();
    Class<?> serviceType =
            loader.loadClass("com.example.service.Service");

This asks the loader to locate the class by binary name. It can throw **ClassNotFoundException** if the class is not found. The result depends on how the loader implements class lookup, parent-child relationships, and the modules the loader defines.

However, **loadClass(String) is not an API that guarantees the returned class belongs to the exact module you are inspecting**. A loader can define multiple modules. Therefore, if the requirement is to find a class in a specific module, consider the **Class.forName(Module, String)** overload:

    Module module = Main.class.getModule();
    Class<?> serviceType =
            Class.forName(module, "com.example.service.Service");

    if (serviceType == null) {
        System.out.println("Class not found in the specified module");
    }

This API has existed since Java 9. It searches for the class in the specified module and returns **null** if the class is not found in that module. This method does not initialize the class. It is usually a clearer choice when you need to constrain lookup to a specific module.

Do not confuse the API above with **Class.forName(String)**. The overload taking only a class name uses its default class-loading mechanism, so it may search through a different loader than the loader of the module you care about.

## 5. Common limitations and differences of ClassLoader

### Delegation mechanism

Many class loaders use a parent delegation model: first checking whether the class is already loaded, then asking the parent loader, and only then searching for the class themselves if needed. This is a common implementation, not a guarantee that every custom loader must behave the same way. A loader can override class lookup logic to serve plugins, application servers, or specialized runtime environments.

Therefore, knowing the loader object does not mean knowing the full lookup order. When investigating class-loading errors, inspect both the specific loader and its parent structure.

### Same class name but different loaders

Suppose two plugins both carry a class named **com.example.api.Message**, but each plugin is loaded by its own loader. The JVM can treat them as two different types. When passing objects between the two sides, the application can encounter **ClassCastException**, even though the message displays the same class name.

Other linkage errors can also appear if components within a data type are loaded from incompatible loaders. The usual fix is to unify where shared APIs are defined, establish loader boundaries, and avoid packaging multiple copies of the same API into independent class-loading zones.

### Module layers can use different loader strategies

JPMS allows creating module layers with different loader strategies. For example, **ModuleLayer.defineModulesWithOneLoader(...)** can define modules in a layer using a shared loader; **ModuleLayer.defineModulesWithManyLoaders(...)** can use a separate loader per module. Applications can also use custom loaders when building a layer.

Therefore, do not rely on the assumption that each module has its own loader. Check how the layer was created and how loaders are configured in the actual application.

### Context class loader is a different concept

**Thread.currentThread().getContextClassLoader()** returns the thread's context class loader. Frameworks or libraries may use this loader to locate classes or providers on behalf of running code.

The context class loader can differ from the loader returned by **Module.getClassLoader()**. They serve different purposes: one is tied to the module containing the class, while the other is the class-loading context carried by the thread. Do not substitute one for the other without understanding which mechanism the library uses.

## 6. Combined example

The following example inspects the module and loader of an application class:

    public class LoaderInfo {
        public static void printInfo(Class<?> anchor) {
            Module module = anchor.getModule();
            ClassLoader loader = module.getClassLoader();

            System.out.println("Module name: " + module.getName());

            if (loader == null) {
                System.out.println("Loader: bootstrap");
            } else {
                System.out.println("Loader: " + loader);
                System.out.println("Parent: " + loader.getParent());
            }
        }
    }

You can call the method with an application class:

    LoaderInfo.printInfo(Main.class);

If running on the classpath, application classes typically belong to an unnamed module. If running on the module path, classes can belong to a named module declared in **module-info.java**. In both cases, the specific loader depends on the runtime configuration.

To look up a class belonging to the exact module, you can use:

    Module module = Main.class.getModule();
    Class<?> result =
            Class.forName(module, "com.example.app.internal.Helper");

    if (result != null) {
        System.out.println("Found in module: " + result.getModule().getName());
    }

The example uses the full binary name of the class, including the package. If the class does not belong to the specified module, the result is null; obtaining the module's loader does not change this condition.

## 7. How to choose the right API

| Need | API to consider | Note |
|---|---|---|
| Identify the module of a class | **Class.getModule()** | Returns the Module containing that class |
| Get the loader bound to a module | **Module.getClassLoader()** | May return null for the bootstrap loader |
| Load a class via a known loader | **ClassLoader.loadClass(String)** | Searches according to loader logic; not uniquely bound to one module |
| Look up a class in a specific module | **Class.forName(Module, String)** | Returns null if the class is not in that module; does not initialize the class |
| Check whether a module reads another module | **Module.canRead(Module)** | Does not replace package access checks |
| Check whether a package is exposed | **Module.isExported(...)** | Serves access permissions via exports |
| Check whether a package is open for reflection | **Module.isOpen(...)** | Relates to deep reflection |
| Get the thread context loader | **Thread.getContextClassLoader()** | May differ from the loader bound to the module |

## 8. Key takeaways

- Obtain the module from a class with **Class.getModule()**, and only then call **Module.getClassLoader()**.
- Always handle the case where the loader result is null; this is a valid case for the bootstrap loader.
- A loader can define multiple modules, so a loader does not uniquely represent a module.
- **ClassLoader.loadClass(...)** looks up classes according to the loader's logic; it does not grant module access permissions and does not guarantee the class belongs to the module in question.
- Use **Class.forName(Module, String)** when you need to look up a class in the exact specified module.
- When encountering access errors, check **requires**, **exports**, **opens**, and Java access rules; switching or obtaining a loader does not resolve these boundaries on its own.
- When encountering cast or linkage errors, check whether the classes were loaded from different loaders.
- Distinguish a module's loader from a thread's context class loader.

**Module.getClassLoader() is the API for identifying the loader bound to a module.** To load classes within the right scope and access them, you must still consider how the loader locates classes along with the rules of the Java Module System.