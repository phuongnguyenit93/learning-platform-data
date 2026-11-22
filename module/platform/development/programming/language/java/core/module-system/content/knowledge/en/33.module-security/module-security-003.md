# Limits of Reflection and Dynamic Loading

## 1. Objective

Java provides reflection and dynamic class loading so that a program can look up types, read metadata, invoke constructors/methods, or load implementations at runtime. These capabilities are useful for frameworks, dependency injection, ORMs, serialization, plugins, and extensible systems.

When an application runs on the Java Platform Module System (JPMS), reflection and dynamic loading are still subject to module rules. A class may be found and loaded successfully while the package containing it is not exported; a field may be found via reflection yet remain inaccessible; a plugin may be loaded by its own class loader yet still lack permission to read APIs of another module.

This lesson explains the limits of reflection and dynamic loading in a modular environment, how to distinguish `export` from `open`, how to load classes or module layers, common errors, and the security boundaries to understand when designing plugins.

After this lesson, you can:
- Distinguish between normal Java access, reflective access, and deep reflection.
- Understand why finding a class does not mean you are permitted to use that class.
- Use **exports**, **opens**, **--add-exports**, and **--add-opens** for their intended purposes.
- Use **Class.forName**, **ClassLoader**, and **ModuleLayer** to dynamically load implementations.
- Understand the role of class loaders, module readability, and module layers.
- Design controlled plugins and recognize why JPMS is not a security sandbox.

## 2. What Is Reflection?

Reflection is the ability of a program to inspect and manipulate the structure of classes at runtime via the APIs in **java.lang.reflect** and **java.lang.invoke**.

For example, retrieving metadata of a class:

~~~java
Class<?> type = Class.forName("com.example.model.Customer");

System.out.println(type.getName());

for (var method : type.getDeclaredMethods()) {
    System.out.println(method.getName());
}
~~~

Some commonly used operations:

- **Class.forName(...)**: locates and loads a class by name.
- **getDeclaredFields()**, **getDeclaredMethods()**, **getDeclaredConstructors()**: retrieves metadata of members declared in the class, including non-public members.
- **getField()**, **getMethod()**: looks up public members according to inheritance rules.
- **Constructor.newInstance()**, **Method.invoke()**, **Field.get()/set()**: instantiates objects, invokes methods, and reads/writes fields via reflection.
- **MethodHandles.Lookup**: provides a mechanism to look up and invoke methods/fields with controlled access rights.

Reflection enables frameworks to work with classes without knowing all class names or data structures at compile time. However, reflection does not remove Java's access checks. Obtaining a **Field** or **Method** object does not automatically allow invoking or reading/writing that member.

## 3. Three Steps to Distinguish: Finding a Class, Accessing a Type, and Accessing a Member

When working with classes at runtime, distinguish three things:

1. **Finding and loading the class:** the class loader locates bytecode and creates the `Class` object.
2. **Accessing the type/package:** the module system checks whether the target module reads the source module and whether the package is exported.
3. **Accessing the member:** Java checks modifiers, inheritance relationships, packages, modules, and reflection permissions for the specific member.

For example, an application can call **Class.forName("com.example.internal.Secret")** successfully because the class loader finds the class. However, if the **com.example.internal** package belongs to a named module and is not exported to the application module, code cannot use that public type through normal access.

Similarly, **getDeclaredField("token")** may return a `Field` object for a private field. That only indicates the field exists. When calling **field.get(object)** or **field.set(object, value)**, access checks still apply. To bypass certain language access checks for deep reflection, the source module's package must be opened to the calling module according to JPMS rules.

Therefore, do not conclude that reflection has "bypassed the module system" merely because a framework found a class or field name.

## 4. `exports` and `opens` in JPMS

### `exports`: Public API Access

A module exports a package so other modules can access public types and public/protected members according to normal Java rules:

~~~java
module com.example.domain {
    exports com.example.domain.api;
}
~~~

The consumer module needs to read the source module, usually via **requires**:

~~~java
module com.example.application {
    requires com.example.domain;
}
~~~

When the package is exported and the consumer module reads the source module, the consumer can use the public API in that package. `exports` does not open private fields or private methods for deep reflection.

### `opens`: Deep Reflection

If a framework needs reflective access to non-public members, the source module can open the package:

~~~java
module com.example.domain {
    exports com.example.domain.api;

    opens com.example.domain.model
        to com.example.orm;
}
~~~

In this example:
- The **com.example.domain.api** package is exported so consumers can call the public API.
- The **com.example.domain.model** package is opened to module **com.example.orm** so the framework can perform deep reflection.

All packages of a module can be opened for deep reflection with the declaration:

~~~java
open module com.example.domain {
    exports com.example.domain.api;
}
~~~

An `open module` opens its packages for deep reflection at runtime. It does not automatically export all packages for normal code access; if consumers need to import public types in a package, an appropriate `exports` is still required.

### Comparison Table

| Mechanism | Allows | Does Not Automatically Allow |
|---|---|---|
| **exports p** | Access to public API of package `p` | Deep reflection into private members |
| **exports p to m** | Public API of `p` for module `m` | Package access from any other module |
| **opens p** | Deep reflection into package `p` at runtime | Importing public types from `p` when the package is not exported |
| **opens p to m** | Deep reflection from module `m` into `p` | Deep reflection access from other modules |
| **open module** | Deep reflection into all packages of the module | Automatically exporting all packages |

## 5. `setAccessible`, `trySetAccessible`, and Module Restrictions

Before JPMS, frameworks commonly used **setAccessible(true)** to request reflection to bypass certain language access checks. Since Java 9, this operation is also subject to module boundaries.

For example:

~~~java
Field field = Customer.class.getDeclaredField("internalId");

if (field.trySetAccessible()) {
    Object value = field.get(customer);
    System.out.println(value);
} else {
    throw new IllegalStateException(
        "Module does not open the package for deep reflection"
    );
}
~~~

**trySetAccessible()** attempts to enable reflective access and returns **false** if it cannot do so. When blocked by the module system, it does not open the package on its own.

**setAccessible(true)** can throw **InaccessibleObjectException** if access cannot be enabled due to module restrictions. Therefore, legacy code that assumes `setAccessible(true)` can be called on any field may fail when running on a JDK with strong encapsulation.

To allow deep reflection from module **com.example.orm** into package **com.example.domain.model**, the source module can declare:

~~~java
module com.example.domain {
    opens com.example.domain.model to com.example.orm;
}
~~~

Or configure at runtime with the option:

~~~bash
java --add-opens com.example.domain/com.example.domain.model=com.example.orm --module-path mods --module com.example.application/com.example.application.Main
~~~

**--add-opens** is a runtime option. It does not turn the package into a public API for source code to import and call directly. If public type access is needed, use `exports` or `--add-exports`.

If the framework runs in the unnamed module on the classpath, the target can be **ALL-UNNAMED**:

~~~bash
java --add-opens com.example.domain/com.example.domain.model=ALL-UNNAMED -cp app.jar com.example.Main
~~~

`ALL-UNNAMED` opens the package to unnamed modules in the process. This is a broad scope; if possible, use named modules and open only to the specific framework module.

## 6. Reflection with `MethodHandles`

Reflection is not the only mechanism for dynamically accessing members. **MethodHandles** provides typed handles for invoking methods, accessing fields, and calling constructors.

A typical lookup:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodHandle handle = lookup.findVirtual(
    String.class,
    "length",
    MethodType.methodType(int.class)
);

int length = (int) handle.invokeExact("modules");
~~~

A `Lookup` object carries the access rights of the class that created it. Not every lookup has permission to access private members of another class.

To create a private lookup into a class in another module, the **MethodHandles.privateLookupIn(...)** API requires matching module conditions. Essentially, the caller's module must read the target module, and the package containing the target class must be opened to the caller's module. If the package is not open, the operation can throw **IllegalAccessException**.

Skeleton example:

~~~java
MethodHandles.Lookup callerLookup = MethodHandles.lookup();

MethodHandles.Lookup privateLookup =
    MethodHandles.privateLookupIn(
        Customer.class,
        callerLookup
    );
~~~

This snippet succeeds only if the module graph and package openness permit it. **privateLookupIn** is not a workaround to bypass JPMS; it follows module access conditions.

When designing frameworks, prefer public APIs or an explicit SPI. Only use private lookup when the framework genuinely needs deep access and the source module has intentionally opened the package to it.

## 7. What Is Dynamic Class Loading?

Dynamic class loading is the process of loading classes while the program is running instead of directly referencing all implementations at compile time.

The simplest way is **Class.forName**:

~~~java
Class<?> type = Class.forName("com.example.plugin.JsonPlugin");
Object plugin = type.getDeclaredConstructor().newInstance();
~~~

The single-argument call **Class.forName(String)** uses the defining class loader of the calling class and initializes the class. If you only want to load the class without running its static initializer yet, you can use the three-argument overload:

~~~java
Class<?> type = Class.forName(
    "com.example.plugin.JsonPlugin",
    false,
    pluginClassLoader
);
~~~

The **false** parameter requests not to initialize the class at the time of this call. Static initialization can still run when the class is actively used later.

Or use a class loader directly:

~~~java
Class<?> type = pluginClassLoader.loadClass(
    "com.example.plugin.JsonPlugin"
);
~~~

**ClassLoader.loadClass(...)** does not actively initialize the class. Loading, linking, and initialization are separate phases; the JVM may defer part of linking until the class is actually used.

When instantiating via reflection, the constructor may throw an exception. **Constructor.newInstance()** wraps any exception thrown by the constructor in an **InvocationTargetException**. Check its cause to find the underlying error.

## 8. Dynamic Loading Does Not Bypass Module Access

Being able to load a class does not imply permission to use that class.

Suppose **com.example.plugin.impl** is a named module containing package **com.example.plugin.internal**. The application module can find the class via a module layer or class loader, but if the package is not exported, consumer code still cannot access the public type under module rules.

Conditions that usually need to be examined:

- Whether the consumer module reads the module containing the class.
- Whether the package containing the public type is exported to the consumer.
- If a framework needs deep reflection, whether the package is opened to the framework module.
- Whether the class loader can find the right class and its dependencies.
- Whether the module is in the module graph/layer that the application is using.

Do not use **Class.forName**, **loadClass**, or reflection as a fix for missing **requires**, **exports**, or **opens**. These APIs only help locate and interact with classes within the permissions the JVM grants.

## 9. Class Loaders and Class Identity

Every class in the JVM has an identity tied to its binary name and its defining class loader. Two classes with the same fully qualified name defined by two different class loaders are still two distinct runtime types.

For example, suppose the application and a plugin both load a copy of **com.example.api.Plugin** from two separate loaders. An object implementing the plugin's copy of the interface cannot be cast to the copy of the interface held by the application. The result can be a **ClassCastException**, even though the interface names appear identical.

To avoid this error:

1. Place the shared API in a parent class loader or parent module that both the application and the plugin read.
2. Ensure plugins do not bundle another copy of the shared API when the architecture requires sharing the same type.
3. Clearly define parent delegation and which class loader is responsible for loading each package.
4. Use explicit module names and module layers when plugins are modular JARs.
5. Log both the class name and class loader when investigating cast or linkage errors.

You can inspect the defining loader:

~~~java
System.out.println(type.getName());
System.out.println(type.getClassLoader());
System.out.println(type.getModule());
~~~

For classes belonging to the bootstrap loader, **getClassLoader()** may return `null`. That is normal and does not mean the class has not been loaded.

## 10. Loading Plugins with `ModuleLayer`

For plugins packaged as modular JARs, **ModuleLayer** allows creating a new module layer from modules found in a directory or another module source.

Example structure:
- The API module **com.example.plugin.api** resides in the parent layer.
- The implementation module **com.example.plugin.json** resides in the **plugins** directory.
- The plugin module declares **provides** for the service interface.

Plugin module:

~~~java
module com.example.plugin.json {
    requires com.example.plugin.api;

    provides com.example.plugin.api.Plugin
        with com.example.plugin.json.JsonPlugin;
}
~~~

The application module consuming the service must declare:

~~~java
module com.example.application {
    requires com.example.plugin.api;
    uses com.example.plugin.api.Plugin;
}
~~~

Creating the layer and discovering providers:

~~~java
ModuleFinder finder = ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
    ModuleLayer.boot().configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.example.plugin.json")
    );

ModuleLayer.Controller controller =
    ModuleLayer.defineModulesWithOneLoader(
        configuration,
        List.of(ModuleLayer.boot()),
        ClassLoader.getSystemClassLoader()
    );

ModuleLayer pluginLayer = controller.layer();

ServiceLoader<Plugin> plugins =
    ServiceLoader.load(pluginLayer, Plugin.class);

for (Plugin plugin : plugins) {
    plugin.start();
}
~~~

This example assumes the API and application modules are already in the boot layer, the **plugins** directory contains a valid plugin module, and the classes/packages are properly declared. **ModuleLayer.defineModulesWithOneLoader** creates a new layer with a single class loader for the modules defined in that layer.

Using **ServiceLoader.load(pluginLayer, Plugin.class)** finds providers in the specified layer and its parent layers. A module calling `ServiceLoader` in a named module must declare **uses** for the service; the providing module must declare **provides ... with ...**.

If using non-modular JAR plugins, a separate class loader or another plugin mechanism can be used. However, a separate class loader does not by itself create a security boundary and does not replace module readability/exports.

## 11. `ServiceLoader`, Context Class Loader, and Plugins

In plugin applications, providers may be loaded by a different class loader than the application's class loader. The call:

~~~java
ServiceLoader.load(Plugin.class)
~~~

uses the current thread's context class loader to find providers on the classpath.

If the application uses module layers, the overload accepting a layer clearly scopes the search:

~~~java
ServiceLoader.load(pluginLayer, Plugin.class)
~~~

If a framework or application server changes the context class loader, provider discovery can differ across threads. When diagnosing, inspect:

~~~java
System.out.println(
    Thread.currentThread().getContextClassLoader()
);
~~~

In addition, **ServiceLoader** discovers and instantiates providers lazily. Configuration or initialization errors may only surface when iterating over the iterator or stream, not necessarily when calling **load()**. If a provider is invalid, **ServiceConfigurationError** can occur.

For production plugins, SPI is usually easier to manage than assembling class names from configuration strings and calling `Class.forName`. SPI provides a clear service contract and leverages module descriptors or provider configurations.

## 12. Common Errors in Reflection and Dynamic Loading

| Error | Possible Cause | Resolution |
|---|---|---|
| **ClassNotFoundException** | Class loader cannot find the requested class name | Check class name, classpath/module path, module layer, and loader |
| **NoClassDefFoundError** | Compiled class references a dependency missing at runtime or prior class initialization failed | Check dependencies and the original exception in logs |
| **IllegalAccessException** | Reflection lacks permission to access the member under access checks | Check modifiers, package exports, and open permissions |
| **InaccessibleObjectException** | Cannot enable deep reflection because the package is not open | Use narrowly scoped `opens`/`--add-opens` or change design |
| **IllegalAccessError** | Bytecode accesses a type/member blocked by the module system | Check readability and `exports` at runtime |
| **ClassCastException** | Same class name defined by different loaders, or object does not implement the right API | Check class loaders and where the shared API is packaged |
| **NoSuchMethodException** | Class loaded but lacks a constructor/method with the matching signature | Check API version and parameter types |
| **InvocationTargetException** | Target constructor or method threw an exception | Check `getCause()` to find the actual error |
| **ExceptionInInitializerError** | Class static initializer threw an exception during initialization | Inspect static blocks and the root cause |
| **ServiceConfigurationError** | SPI provider misdeclared, failed to load, or failed to instantiate | Check `provides`/`META-INF/services`, dependencies, and provider constructor |

When investigating, do not catch only the outermost exception and ignore its cause. For example, `InvocationTargetException` is often just a wrapper; the real error may be an `IllegalStateException` or a configuration error thrown by the plugin constructor.

## 13. Security Limitations of Reflection and Dynamic Loading

JPMS helps encapsulate modules and control accessibility between modules. However, **the module system is not a sandbox for running untrusted code**.

If an application loads a Java plugin into the same JVM, the plugin code generally runs with the process's permissions and can call APIs the application is also allowed to call. Placing a plugin in its own module or its own class loader does not automatically isolate the file system, network, threads, CPU, memory, or operating system resources.

Some risks:
- **Class initialization:** static initializers can execute code as soon as a class is initialized.
- **Constructor side effects:** instantiating a plugin can open sockets, read files, spawn threads, or alter application state.
- **Reflection abuse:** frameworks or plugins can deeply access objects if modules have opened packages.
- **Untrusted class names:** loading class names directly from configuration/user input can cause the application to execute unintended implementations.
- **Dependency confusion:** plugins can bring along conflicting dependencies or duplicate APIs causing class loader conflicts.
- **Resource exhaustion:** plugins can spawn threads, allocate memory, or run CPU-intensive tasks.

Practical safeguards:

1. Only load plugins from approved sources and control the list of permitted modules/classes.
2. Verify artifact provenance, checksums, or signatures per release policy before loading.
3. Do not treat a valid certificate as proof that code is safe; signatures only identify the signing source and integrity.
4. Keep the plugin API small, clearly versioned, and do not open internal packages unnecessarily.
5. Manage the plugin lifecycle: start, stop, close resources, stop threads, and release references to class loaders/layers.
6. If running untrusted code, use a separate process/container with appropriate OS permissions and resource limits instead of relying on modules or class loaders.
7. Log module name, class name, class loader, artifact source, and initialization errors.

Do not use **SecurityManager** as the foundation for new sandbox designs. The Security Manager has been deprecated for removal since JDK 17; choose process-level and OS-level isolation mechanisms for untrusted code.

## 14. Managing Class Loader and Module Layer Lifecycles

A plugin loader that is no longer needed can still retain classes in memory if the application holds references to classes, objects, threads, `ThreadLocal`, context class loaders, or resources created by the plugin.

Some notes:

- Close **URLClassLoader** when no longer needing to load classes/resources from JARs. Closing the loader does not automatically unload already loaded classes.
- Stop threads created by plugins and clear `ThreadLocal`/context class loaders pointing to the plugin.
- Close files, sockets, executors, watchers, and resources opened by the plugin.
- Clear references to plugin instances, `Class`, `Method`, `MethodHandle`, and callbacks if you want the loader to be reclaimable by the garbage collector.
- `ModuleLayer` has no direct unload API. A layer's classes can only be reclaimed when the associated loaders are no longer kept alive and all other conditions for class unloading are met.

Do not rely on calling **System.gc()** to guarantee immediate plugin unloading. Garbage collection is determined by the JVM; plugin design must manage resources and references explicitly.

## 15. Process for Safer Plugin Design

A practical process can include:

1. **Define the SPI:** place the service interface in a stable API module; export only necessary API packages.
2. **Determine packaging:** choose between classpath plugins or modular JARs on the module path.
3. **Control plugin sources:** verify approved artifacts, versions, checksums/signatures, and dependencies.
4. **Create loading scope:** use a class loader or `ModuleLayer` with clearly defined parent/API modules.
5. **Discover providers:** prefer `ServiceLoader` rather than constructing class names from arbitrary input.
6. **Verify the contract:** confirm the provider satisfies the interface, version, and capabilities required by the application.
7. **Controlled initialization:** handle exceptions, appropriate timeouts, and `ServiceConfigurationError`; do not treat a failing plugin as an absent plugin.
8. **Grant minimal module access:** export API packages; only open packages for deep reflection if frameworks genuinely require it.
9. **Manage lifecycle:** provide start/stop/close, close resources, and prevent plugins from leaving lingering threads or callbacks.
10. **Isolate untrusted code:** run in a separate process/container if a real security boundary is needed.

## 16. Self-Check

**1. Does `getDeclaredField()` returning a `Field` mean the program is allowed to read that field?**

No. It only confirms the field was found. When calling `get`/`set`, access checks still apply; deep reflection may require the package to be opened to the calling module.

**2. Does `Class.forName()` bypass the module system?**

No. It finds and loads the class through a class loader. Using the type and accessing members remain subject to module readability, `exports`, `opens`, and Java access rules.

**3. Why can `setAccessible(true)` throw `InaccessibleObjectException` on newer JDKs?**

Because the module containing the class does not open the package to the module invoking deep reflection. Use a public API, declare narrowly scoped `opens`, or configure `--add-opens` if genuinely needed.

**4. When should `ModuleLayer` be used instead of only creating a `URLClassLoader`?**

When plugins are packaged as named modules and need their own module graph, with explicit `requires`, `exports`, `uses`, and `provides`. `URLClassLoader` suits some classpath plugins but does not provide module configuration on its own.

**5. Can two classes with the same name cause a `ClassCastException`?**

Yes. If they are defined by two different defining class loaders, the JVM treats them as two distinct runtime types.

**6. Is a separate module enough to run an untrusted plugin safely?**

No. JPMS controls access by module, not code sandboxing. For untrusted code, process/container isolation and OS permission restrictions are required.

## 17. Takeaways

Reflection and dynamic loading are powerful tools for frameworks and plugins, yet they do not bypass JPMS boundaries. Finding a class does not mean accessing the type is allowed; finding a `Field` does not mean reading/writing the member is allowed; loading a plugin does not mean the plugin is authorized or trustworthy.

Use **exports** for public APIs, **opens** for deep reflection, **ClassLoader** or **ModuleLayer** for appropriate loading mechanisms, and **ServiceLoader** for SPI. Manage class loaders, module graphs, dependencies, and plugin lifecycles explicitly. When running untrusted code is required, use process-level isolation boundaries instead of treating the module system as a sandbox.

## References

- [AccessibleObject — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Class — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html)
- [ClassLoader — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html)
- [Module — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html)
- [ModuleLayer — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html)
- [MethodHandles — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [ServiceLoader — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html)
- [JEP 261: Module System](https://openjdk.org/jeps/261)
- [JEP 411: Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411)