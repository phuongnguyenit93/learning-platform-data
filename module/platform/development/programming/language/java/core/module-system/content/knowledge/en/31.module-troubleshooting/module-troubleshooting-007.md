# ClassNotFoundException Due to Wrong Loader or Layer

In a Java application using the **Java Platform Module System (JPMS)**, having a JAR file on disk does not guarantee that all code in the JVM can find the classes inside that JAR. A class may reside in a resolved named module yet be defined by a **different class loader** from the loader that the framework or application is using. It may also reside in a **child ModuleLayer** or sibling layer, outside the search scope of the current loader.

When calling **Class.forName(...)**, **ClassLoader.loadClass(...)**, or automatic discovery mechanisms, the application may encounter **ClassNotFoundException** even when the class name and JAR look right. Handling this accurately requires distinguishing **module discovery**, **module resolution**, **layer definition**, **class loading**, and **module access**. A common mistake is using **--add-exports** or **--add-opens** to treat a class-not-found error, when the actual cause is using the wrong loader or looking in the wrong layer.

This lesson presents a workflow for investigating ClassNotFoundException across the module graph and class loaders, along with a custom ModuleLayer reproduction example and appropriate fixes.

## 1. Concepts to distinguish

A Java class is identified at runtime by its **binary name** together with its **defining class loader**. With JPMS, a class also belongs to a **Module** object, and a named module is defined in a ModuleLayer.

Related concepts:

| Component | Role | Diagnostic question |
|---|---|---|
| JAR or exploded module | Contains classes and module metadata | Is the class file actually inside the artifact? |
| ModuleFinder | Discovers observable modules | Which path is the finder searching? |
| Configuration | Result of resolving root modules and dependencies | Has the module containing the class been resolved yet? |
| ModuleLayer | Defines modules at runtime | Is the module in the boot layer or a custom child layer? |
| ClassLoader | Locates and defines classes | Which loader is the code asking to find the class? |
| Module exports/opens | Controls access permissions | Was the class found, yet the caller lacks permission to use or reflect on it? |
| ServiceLoader | Finds implementations by service contract | Which layer is the framework searching for services? |

Typical sequence of operations:

~~~text
Artifact (JAR or exploded module)
    |
    v
ModuleFinder -> Configuration.resolve(...) or resolveAndBind(...)
    |
    v
ModuleLayer.defineModules...(...)
    |
    v
Module object + defining ClassLoader
    |
    v
Class.forName / loadClass / ServiceLoader
    |
    v
Check readability, exports/opens when using the class
~~~

When errors arise at different steps, the exception names and remedies differ. Do not lump every error into "JPMS denies access".

## 2. What does ClassNotFoundException actually mean?

**ClassNotFoundException** is a checked exception that typically occurs when a call requests loading a class by name, yet the class loader used cannot locate that class:

~~~java
Class<?> type = Class.forName("com.acme.plugin.internal.Parser");
~~~

Or:

~~~java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Class<?> type = loader.loadClass("com.acme.plugin.internal.Parser");
~~~

These calls can fail because:

- The binary class name is wrong, including the package or nested class name.
- The JAR does not exist on the paths the loader can search.
- The class resides in an unresolved module.
- The module was resolved yet defined in a class loader of another child layer.
- Code uses the system class loader to look up a class defined by a plugin loader.
- The thread context class loader (TCCL) points to a loader that cannot see the plugin.
- The plugin sits in a sibling layer outside the caller's delegation relationship.
- A library or framework creates its own loader without being passed the right loader.

Note: Java can load a class and still deny access to that class afterward. **ClassNotFoundException** is about finding the class, whereas **IllegalAccessError**, **IllegalAccessException**, or **InaccessibleObjectException** can be about using the class/member after it has been found.

## 3. How class loaders relate to JPMS

In traditional Java, many applications place libraries on the classpath and rely on the system/application class loader. With JPMS, the module system can define multiple named modules in different class loaders. With custom layers, the loaders created to define the layer are not necessarily the system class loader.

Two common ways to define a layer:

~~~java
ModuleLayer layer = parentLayer.defineModulesWithOneLoader(
    configuration,
    ClassLoader.getSystemClassLoader()
);
~~~

and:

~~~java
ModuleLayer layer = parentLayer.defineModulesWithManyLoaders(
    configuration,
    ClassLoader.getSystemClassLoader()
);
~~~

In the first case, the layer's modules are mapped to one new loader. In the second case, each module in the layer gets its own loader. The **ClassLoader.getSystemClassLoader()** argument here is the parent loader for constructing the layer's loaders; it **does not mean the new modules are defined directly by the system class loader**.

Therefore, the following code can fail to find a class belonging to a new plugin layer:

~~~java
ClassLoader systemLoader = ClassLoader.getSystemClassLoader();
Class<?> pluginType =
    systemLoader.loadClass("com.acme.plugin.impl.PluginImpl");
~~~

The class may already exist in the plugin layer yet be defined by that layer's loader. Look up the right loader for the plugin module rather than assuming the system loader sees every class.

## 4. Which loader does Class.forName use?

There are multiple overloads of **Class.forName** and they are not equivalent.

### 4.1. Class.forName(String)

~~~java
Class<?> type = Class.forName("com.acme.plugin.impl.PluginImpl");
~~~

This overload uses the defining class loader of the calling class to locate the class by name, according to API semantics. If the caller resides on the host classpath or boot layer, it does not automatically switch to the loader of a new child layer.

If the class is defined only in a child layer, this overload can throw ClassNotFoundException even when the plugin module was resolved and defined successfully.

### 4.2. Class.forName(String, boolean, ClassLoader)

~~~java
ClassLoader pluginLoader = pluginLayer.findLoader("com.acme.plugin");
Class<?> type = Class.forName(
    "com.acme.plugin.impl.PluginImpl",
    false,
    pluginLoader
);
~~~

The last parameter lets you specify the loader to use. The value **false** requests not initializing the class merely because of the Class.forName call; this is useful when inspecting a class before running static initializers.

When class initialization is needed, **true** can be used, bearing in mind static initialization can trigger code and cause other exceptions. Use true only when initialization behavior is required.

### 4.3. Class.forName(Module, String)

JPMS also provides:

~~~java
Module module = pluginLayer
    .findModule("com.acme.plugin")
    .orElseThrow();

Class<?> type = Class.forName(
    module,
    "com.acme.plugin.impl.PluginImpl"
);
~~~

This overload looks up the class in the specified module and **returns null if the class is not found in that module**; it does not share the same ClassNotFoundException-throwing contract as the standard String overload. It also does not initialize the class.

Check for a null result and handle access permissions when using the class. Finding a class in a module does not guarantee another caller can invoke every constructor or method of that class.

## 5. ModuleLayer.findLoader(String) is the right starting point

Once you have the plugin's ModuleLayer, use **findLoader(moduleName)** to retrieve the loader defining the corresponding module in the layer:

~~~java
String moduleName = "com.acme.plugin";

ClassLoader loader = pluginLayer.findLoader(moduleName);

Class<?> type = loader.loadClass(
    "com.acme.plugin.impl.PluginImpl"
);
~~~

The **findLoader** method takes a **module name**, not a package name or class name. It is most useful when code already knows which layer defines the plugin module.

If the module name does not belong to the layer under the API contract, the call can throw **IllegalArgumentException**; distinguish that error from a ClassNotFoundException in the subsequent step.

A clear way to check:

~~~java
String moduleName = "com.acme.plugin";

Module module = pluginLayer
    .findModule(moduleName)
    .orElseThrow(() -> new IllegalStateException(
        "Expected plugin module is absent: " + moduleName
    ));

ClassLoader loader = module.getClassLoader();

Class<?> type = Class.forName(
    "com.acme.plugin.impl.PluginImpl",
    false,
    loader
);
~~~

**Module.getClassLoader()** returns the loader that defines the module. For some platform modules, the loader may be represented as null to denote the bootstrap loader; diagnostic code must handle null without treating it as an error.

When there are multiple layers, retrieve the Module object from the right layer and keep it alongside the layer context, rather than storing only a global module name string.

## 6. Reproduction example: class exists yet host uses the wrong loader

The example has two parts: a plugin as a named module, and a host program running on the classpath that creates a ModuleLayer for the plugin.

Project structure:

~~~text
project/
├── plugin-src/
│   └── com.acme.greeter.plugin/
│       ├── module-info.java
│       └── com/acme/greeter/impl/Greeter.java
├── host-src/
│   └── Host.java
├── plugin-out/
└── host-out/
~~~

Plugin descriptor:

~~~java
module com.acme.greeter.plugin {
    exports com.acme.greeter.impl;
}
~~~

Plugin class:

~~~java
package com.acme.greeter.impl;

public final class Greeter {
    public Greeter() {
    }

    public String hello() {
        return "Hello from plugin layer";
    }
}
~~~

Host code:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class Host {
    public static void main(String[] args) throws Exception {
        ModuleLayer parent = ModuleLayer.boot();

        ModuleFinder pluginFinder =
            ModuleFinder.of(Path.of("plugin-out"));

        Configuration config =
            parent.configuration().resolve(
                pluginFinder,
                ModuleFinder.of(),
                Set.of("com.acme.greeter.plugin")
            );

        ModuleLayer pluginLayer =
            parent.defineModulesWithOneLoader(
                config,
                ClassLoader.getSystemClassLoader()
            );

        String className =
            "com.acme.greeter.impl.Greeter";

        try {
            Class.forName(className);
            System.out.println("Unexpected: host found class");
        } catch (ClassNotFoundException expected) {
            System.out.println(
                "Host loader cannot find plugin class"
            );
        }

        ClassLoader pluginLoader =
            pluginLayer.findLoader("com.acme.greeter.plugin");

        Class<?> greeterType =
            Class.forName(className, true, pluginLoader);

        Object instance =
            greeterType.getConstructor().newInstance();

        Object result =
            greeterType.getMethod("hello").invoke(instance);

        System.out.println(result);
    }
}
~~~

Compile the plugin as an exploded named module:

~~~bash
javac --module-source-path plugin-src \
      -d plugin-out \
      -m com.acme.greeter.plugin
~~~

Compile the classpath host:

~~~bash
javac -d host-out host-src/Host.java
~~~

Run the host:

~~~bash
java --class-path host-out Host
~~~

If the directory layout is right, the host creates a child ModuleLayer from the module in **plugin-out**. The **Class.forName(className)** call from the host classpath does not see the plugin class in the child layer's loader. Then the host retrieves the right **pluginLayer.findLoader(...)** and locates the class successfully.

Illustrative output:

~~~text
Host loader cannot find plugin class
Hello from plugin layer
~~~

Here the plugin package is exported so the host can invoke the public constructor and method via reflection. Without exporting the package, the class loader might still find the class, yet reflective invocation from the host could hit an access error; that is a separate issue from ClassNotFoundException.

## 7. What happens when the plugin has not been resolved?

If a module was not included in the Configuration, the layer's **findLoader** cannot provide a loader for that module. Even if the JAR is in the directory, the module system only resolves the chosen root set and required dependencies in that context.

Suppose the directory has JARs:

~~~text
plugins/
├── com.acme.greeter.plugin.jar
└── com.acme.codec.plugin.jar
~~~

If the configuration resolves only the root **com.acme.greeter.plugin** and that module does not require codec, the **com.acme.codec.plugin** module may remain unresolved.

You can inspect the configuration right after resolve:

~~~java
config.modules().stream()
    .map(resolved -> resolved.name())
    .sorted()
    .forEach(System.out::println);
~~~

And after creating the layer:

~~~java
boolean inLayer = pluginLayer
    .findModule("com.acme.codec.plugin")
    .isPresent();

System.out.println(inLayer);
~~~

If the module is absent from the graph, do not try to solve it by swapping loaders arbitrarily. Review the root set, requires, or service binding according to the architecture.

Errors arising at the module resolution step are usually **FindException** or **ResolutionException**, not ClassNotFoundException from a later loadClass call. Read the exact point where the exception originates to avoid fixing the wrong thing.

## 8. Boot layer, child layer, and sibling layer

When launched via the Java launcher on the module path, the root application and its dependencies are normally defined in the **boot layer**. When the application creates a **custom ModuleLayer**, new modules can be defined in child layers.

Diagram:

~~~text
Boot layer
├── com.acme.host
└── com.acme.plugin.api
       |
       +-- CSV plugin layer
       |   └── com.acme.csv.plugin
       |
       +-- JSON plugin layer
           └── com.acme.json.plugin
~~~

CSV and JSON can live in **two sibling layers**. Those layers do not automatically look up each other's classes through a shared loader. A class residing only in the CSV plugin layer does not appear when the JSON plugin loader is asked to find that class.

When sharing an API module, place the API in the boot layer or an appropriate parent layer and have plugin modules require that API. Host and plugins communicate through interfaces/DTOs with shared class identity.

A common mistake is assuming:

~~~java
Class.forName("com.acme.csv.internal.CsvParser");
~~~

will automatically search all existing ModuleLayers. The JVM does not provide such a global class repository. Each class-loading call uses a specific loader.

If the application manages dynamic plugin layers, maintain an explicit mapping from **plugin ID -> ModuleLayer -> module name -> loader**. This makes it clear where classes load from and lets you retire plugins cleanly by lifecycle instead of blindly scanning all class loaders.

## 9. What does parent delegation mean?

Class loaders typically delegate to a parent loader. However, loaders created by the module system must also respect the mapping between named modules and defining loaders; do not reason solely via traditional classpath parent-first delegation.

If a child layer's loader has the system loader as its parent, that does **not** make the system loader know how to look up new classes in the child. Delegation typically flows from a child loader's request up to the parent when needed, not in reverse for the parent to search all child loaders.

Thus:

~~~java
ClassLoader parentLoader =
    ClassLoader.getSystemClassLoader();

ClassLoader pluginLoader =
    pluginLayer.findLoader("com.acme.greeter.plugin");
~~~

These two loaders can be different. A class defined by pluginLoader is not automatically loadable by parentLoader.

If a framework is installed in a parent layer and calls Class.forName from framework code, it may search with a loader that cannot see the plugin. The best fix is usually supplying the right loader/plugin layer to the framework if the framework's API supports it, or using an extension mechanism via a service contract.

## 10. Thread Context ClassLoader (TCCL)

Many Java frameworks and legacy libraries look up classes using **Thread.currentThread().getContextClassLoader()**. The TCCL is bound to a thread and does not automatically synchronize with a ModuleLayer holding plugins.

Example:

~~~java
ClassLoader contextLoader =
    Thread.currentThread().getContextClassLoader();

System.out.println(contextLoader);
~~~

If a framework needs a plugin class yet the TCCL is still the system loader, TCCL-based discovery can hit ClassNotFoundException or fail to detect extensions.

You can set the right TCCL for a controlled execution scope:

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

ClassLoader pluginLoader =
    pluginLayer.findLoader("com.acme.greeter.plugin");

try {
    thread.setContextClassLoader(pluginLoader);
    runFrameworkIntegration();
} finally {
    thread.setContextClassLoader(previous);
}
~~~

In this example, **runFrameworkIntegration()** stands for the framework work, not a built-in JDK API. In real code, replace it with the actual method of the library being used.

Important points:

- Do not permanently alter a thread pool's TCCL just to fix a test.
- Always restore the previous loader in a finally block.
- Do not assume every framework uses TCCL; some use the loader that defined the framework classes or an explicitly passed loader.
- Do not use TCCL to try to "force" a named module to read modules disallowed by the module graph.
- Watch out for threads, executors, or callbacks retaining references to a plugin loader and preventing plugin unloading.

If the framework lets you pass a class loader directly, that is usually clearer and easier to control than mutating the thread's TCCL.

## 11. ServiceLoader and ModuleLayer

For plugin architectures, loading implementation classes by string name from the host can cause coupling to internal packages. JPMS provides **ServiceLoader** so consumers work with a service interface.

Service API:

~~~java
module com.acme.plugin.api {
    exports com.acme.plugin.api;
}
~~~

Plugin provider:

~~~java
module com.acme.greeter.plugin {
    requires com.acme.plugin.api;

    provides com.acme.plugin.api.GreeterService
        with com.acme.greeter.impl.DefaultGreeter;
}
~~~

Consumer module:

~~~java
module com.acme.host {
    requires com.acme.plugin.api;
    uses com.acme.plugin.api.GreeterService;
}
~~~

Once the provider module is resolved and defined in the appropriate plugin layer, the host can discover services:

~~~java
ServiceLoader<GreeterService> services =
    ServiceLoader.load(pluginLayer, GreeterService.class);

for (GreeterService service : services) {
    System.out.println(service.hello());
}
~~~

This reduces the need to call:

~~~java
Class.forName("com.acme.greeter.impl.DefaultGreeter");
~~~

Still, ServiceLoader requires the provider module to be present in the appropriate layer, and the service API type must share the same class identity between host and provider.

When using a custom layer, the **ServiceLoader.load(layer, serviceType)** overload clearly expresses where to look for providers. When using an overload based on the context class loader, results can vary depending on the thread's loader and framework setup.

**ServiceConfigurationError** caused by invalid provider configuration or instantiation should not be automatically treated as ClassNotFoundException. Read the root cause and the provider's uses/provides metadata.

## 12. Class identity: finding the same name can still fail to cast

Another issue is two loaders defining two classes with the same binary name. This can happen when each plugin bundles its own copy of the same API JAR.

Suppose the host uses:

~~~java
com.acme.plugin.api.GreeterService
~~~

and the plugin accidentally loads another copy of the API class from its own loader. Two Class objects have the same name yet different defining loaders, so casting can be incompatible:

~~~java
GreeterService service = (GreeterService) pluginInstance;
~~~

The result can be **ClassCastException**, even though the class names in the message look identical.

Inspect:

~~~java
Class<?> hostApi = GreeterService.class;
Class<?> pluginApi = pluginInstance.getClass()
    .getInterfaces()[0];

System.out.println(hostApi == pluginApi);
System.out.println(hostApi.getClassLoader());
System.out.println(pluginApi.getClassLoader());
~~~

This is an illustrative snippet: in a real application, a provider may implement multiple interfaces, so do not rely on the first element of **getInterfaces()** to draw conclusions. Look up the exact interface type to inspect in the inheritance hierarchy.

The durable design is placing the API module in a common parent layer that both host and plugins read, avoiding duplicate packaging of the API module in child layers. Differing class identity is not solved by **--add-opens** or **--add-exports**.

## 13. Distinguishing exception types

| Exception or symptom | Stage where it typically occurs | Primary investigation direction |
|---|---|---|
| **ClassNotFoundException** | Requested loader cannot find class by name | Binary name, class loader, layer, artifact location |
| **FindException** | Resolution cannot find required module or descriptor | ModuleFinder, module path, module name, dependencies |
| **ResolutionException** | Invalid module graph | requires, package conflicts, readability graph |
| **LayerInstantiationException** | Cannot define configuration into loaders/layer | Loader mapping, split packages, parent layers |
| **NoClassDefFoundError** | JVM cannot define/initialize class when needed | Dependency class, linkage, class initialization, root cause |
| **ClassCastException** | Class types incompatible at runtime | Defining loaders, API duplication, type identity |
| **IllegalAccessError** | Class/member access violates access control on link or run | exports/readability, modifiers, binary compatibility |
| **InaccessibleObjectException** | Deep reflection blocked by strong encapsulation | opens, qualified opens, framework module |
| **ServiceConfigurationError** | Service/provider invalid or failed to load | uses, provides, provider instance, ServiceLoader scope |

**NoClassDefFoundError** is not synonymous with ClassNotFoundException. It can occur when the JVM is linking a class and a dependency class cannot be found, or when class initialization previously failed. Read both **Caused by** and the point where it occurred.

Similarly, a **FindException** thrown before a ModuleLayer exists should not be addressed by changing the TCCL in code that runs later. The code may not even have started executing yet.

## 14. Step-by-step diagnostic workflow

When you get a stack trace with ClassNotFoundException:

### Step 1. Verify the binary class name

Record the exact class name from the exception. For nested classes, the binary name has a **$** instead of a dot between outer and inner classes.

Example:

~~~java
Class.forName("com.acme.order.Outer$Inner");
~~~

This name differs from the canonical name **com.acme.order.Outer.Inner**. Check whether the code uses **Class.getName()** or **Class.getCanonicalName()** if names are built dynamically.

### Step 2. Verify the artifact actually contains the class

Run:

~~~bash
jar --list --file plugins/com.acme.greeter.plugin.jar
~~~

Look for the corresponding entry:

~~~text
com/acme/greeter/impl/Greeter.class
~~~

If the class is absent from the artifact, the problem lies in build/publish or artifact version, not module access.

### Step 3. Confirm module name and kind

~~~bash
jar --describe-module --file plugins/com.acme.greeter.plugin.jar
~~~

Determine the actual module name. Do not infer the module name from the JAR filename. If it is an automatic module, the derived descriptor may have a different name than expected.

### Step 4. Confirm the module is resolved

If using the boot layer:

~~~java
System.out.println(
    ModuleLayer.boot().findModule("com.acme.greeter.plugin")
);
~~~

If using a plugin layer:

~~~java
System.out.println(
    pluginLayer.findModule("com.acme.greeter.plugin")
);
~~~

For custom layers, also compare **configuration.modules()** immediately after resolution. Do not use the boot layer to conclude whether child/sibling layers contain a module.

### Step 5. Identify the loader being queried

Log:

~~~java
ClassLoader systemLoader =
    ClassLoader.getSystemClassLoader();

ClassLoader contextLoader =
    Thread.currentThread().getContextClassLoader();

ClassLoader moduleLoader =
    pluginLayer.findLoader("com.acme.greeter.plugin");

System.out.println("System: " + systemLoader);
System.out.println("Context: " + contextLoader);
System.out.println("Module: " + moduleLoader);
~~~

If a framework has an API for supplying a loader, log the loader passed to the framework as well.

### Step 6. Try finding the class with the right loader

~~~java
ClassLoader moduleLoader =
    pluginLayer.findLoader("com.acme.greeter.plugin");

Class<?> type = Class.forName(
    "com.acme.greeter.impl.Greeter",
    false,
    moduleLoader
);

System.out.println(type.getModule().getName());
~~~

If this succeeds where the earlier loader failed to find the class, the evidence points directly to a loader/layer mismatch.

### Step 7. Check exports or opens after loading the class

Once the class is found, if reflective constructor or method invocation fails due to access, inspect the module boundary:

~~~java
Module source = type.getModule();
Module caller = Host.class.getModule();

String pkg = type.getPackageName();

System.out.println(source.isExported(pkg, caller));
System.out.println(source.isOpen(pkg, caller));
~~~

**Host.class** is an example of the actual caller class in use; replace it with the real class in your code. These permissions do not govern whether a loader can find a class, only what kinds of access are accepted.

### Step 8. Document findings and fix at the right layer

The conclusion should look like:

~~~text
Class name: com.acme.greeter.impl.Greeter
Owning module: com.acme.greeter.plugin
Module layer: plugin child layer
Defining loader: plugin layer's loader
Failing lookup: Class.forName(String) from host
Successful lookup: Class.forName(name, false, pluginLoader)
Fix: pass pluginLoader or use ServiceLoader.load(pluginLayer, API.class)
~~~

Record enough context for others to reproduce it, rather than merely noting "added --add-opens and it worked".

## 15. Tools for observing class loading

### 15.1. JVM class loading logs

On modern JDKs, you can enable unified logging:

~~~bash
java -Xlog:class+load=info \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

The log shows which classes are loaded and from what source. Output can be very large, so enable it only while investigating, store logs cleanly, and filter by relevant package names.

In other environments, **-verbose:class** is also a commonly used option for observing class loading.

### 15.2. Printing Module/ClassLoader info

~~~java
static void inspect(Class<?> type) {
    Module module = type.getModule();
    ClassLoader loader = type.getClassLoader();

    System.out.println("Class: " + type.getName());
    System.out.println("Module: " + module.getName());
    System.out.println("Layer: " + module.getLayer());
    System.out.println("Loader: " + loader);
    System.out.println("Package: " + type.getPackageName());
}
~~~

This method runs only after the class has been found. If the problem is ClassNotFoundException, log the loader and layer used in the failing lookup operation as well.

### 15.3. Observing module resolution

~~~bash
java --show-module-resolution \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

This command describes launcher resolution. It helps when a module was not selected into the boot layer, though it does not replace inspecting custom ModuleLayers created after the application starts.

## 16. When the error occurs in tests or the IDE

A project may pass under Maven/Gradle yet fail in the IDE or vice versa. The cause usually lies in differences in runtime graphs and loader setup.

Configurations to compare:

- Are test classes running on the classpath, in a named test module, or patched into a production module?
- Which module path and root modules do JavaExec/Test tasks pass?
- Does the IDE construct the runtime classpath and module path identically to CI?
- Does the test framework use the system loader, TCCL, or the test module's loader?
- Does a test plugin create its own custom layer to load test engines?
- Are plugin JARs copied into the exact directory configured in ModuleFinder?
- Do JVM flags **--add-modules**, **--add-reads**, or **--patch-module** differ between environments?

If the error occurs only in JUnit/serialization/plugin discovery, check which loader the framework uses. A test passing from the classpath does not prove modules in a custom layer load properly in production.

To avoid environmental fragility, write an integration test that creates the ModuleLayer from the exact artifacts scheduled for release and performs class/service discovery using the same API production uses.

## 17. Durable fixes

### 17.1. Pass the loader explicitly

If the existing API accepts a **ClassLoader**, pass the loader of the module/layer owning the class:

~~~java
ClassLoader loader =
    pluginLayer.findLoader("com.acme.greeter.plugin");

Class<?> type = Class.forName(
    "com.acme.greeter.impl.Greeter",
    false,
    loader
);
~~~

This fits plugin loader utilities or frameworks that load classes by string name.

### 17.2. Use ServiceLoader instead of implementation names

If the host only needs a capability, design a service API in a parent layer and register providers via **provides**. The host calls **ServiceLoader.load(layer, serviceType)** to avoid depending on implementation class names.

### 17.3. Fix the root set and resolution

If the module is not resolved, adjust root modules or service binding by design. Swapping loaders will not find classes from an undefined module.

### 17.4. Unify service API identity

If host and plugin use two copies of the API under different loaders, move the API to a shared parent layer, eliminate duplicate packaging, and verify type identity.

### 17.5. Scope TCCL carefully

If a framework requires TCCL, set the right loader only for the duration of the framework call and restore it in finally. Avoid letting background threads or pools hold onto the loader after a plugin stops.

### 17.6. Do not misuse escape hatches

The options **--add-exports**, **--add-opens**, and **--add-reads** alter module permissions; they do not create child layers, reload classes, or turn the system loader into a plugin's loader.

Use them only when the stack trace confirms the real issue is readability, package export, or reflection. If a class is not found by the loader, fix class lookup/loading first.

## 18. Hands-on exercises

1. Create the named module **com.acme.greeter.plugin** and the Greeter class as in the example.
2. Compile the plugin into an exploded module inside **plugin-out**.
3. Write the classpath host that creates a child layer using **Configuration.resolve** and **defineModulesWithOneLoader**.
4. Call **Class.forName(String)** from the host and observe ClassNotFoundException.
5. Retrieve the loader with **pluginLayer.findLoader(moduleName)** and call **Class.forName(name, false, loader)**.
6. Print **Class.getModule()**, **Module.getLayer()**, and **Class.getClassLoader()** after locating the class.
7. Try changing the root module or removing the artifact from pluginFinder to distinguish FindException from ClassNotFoundException.
8. Place two plugins in sibling layers and try loading a class from plugin A with plugin B's loader.
9. Write an integration test using ServiceLoader instead of a hard-coded implementation class name.
10. Set TCCL to the plugin loader inside a try/finally scope and verify it is restored.
11. Include a duplicate copy of the service API in the plugin layer, observe the class identity issue, and fix it with a parent API module.
12. Try removing exports from the plugin package: confirm class loading and reflective access are two separate steps.
13. Use **-Xlog:class+load=info** to observe class sources during loading.
14. Write a diagnostic table covering four errors: FindException, ClassNotFoundException, ClassCastException, and InaccessibleObjectException.
15. Compare the actual command lines of the IDE, CI, and production when plugin discovery behaves inconsistently.

## 19. Key takeaways

- **ClassNotFoundException** usually indicates the queried loader could not locate the class by binary name.
- Having a JAR on disk or a module on the module path does not guarantee the class is resolved and reachable from the current loader.
- A custom ModuleLayer has its own loaders; the system loader does not automatically see child-layer classes.
- **Class.forName(String)** and **Class.forName(String, boolean, ClassLoader)** can use different loaders.
- **Class.forName(Module, String)** returns null if the class is not found in the named module.
- **ModuleLayer.findLoader(moduleName)** is an explicit way to obtain the loader for a named module in a defined layer.
- A module missing from the configuration cannot be fixed merely by swapping TCCL.
- Sibling layers do not automatically share implementation classes; shared APIs should reside in a parent layer.
- **TCCL** matters for some legacy frameworks, yet must be scoped and restored after use.
- Two classes with the same name but different defining loaders can be incompatible when cast.
- **ServiceLoader** reduces coupling to implementation class names and enables selecting providers by layer.
- **--add-opens** and **--add-exports** are not direct fixes when a class loader cannot find a class.
- When debugging, log **binary name, module name, layer, defining loader, caller loader, classpath/module path, and root set**.

**The way to handle ClassNotFoundException caused by a wrong loader or layer is to identify which module/layer the class belongs to, confirm the module is resolved, and look it up using the exact defining loader.** Distinguishing class discovery, module resolution, and access permissions lets you fix the error at the right layer and avoid unnecessary escape hatches.