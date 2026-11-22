# ModuleLayer.defineModulesWithManyLoaders — Creating a Module Layer with a Separate ClassLoader per Module

## 1. Learning Objectives

After this lesson, you can:

- Explain the differences among **Module**, **Configuration**, **ModuleLayer**, and **ClassLoader** in the Java Platform Module System (JPMS).
- Use **ModuleLayer.defineModulesWithManyLoaders** to create a layer where **each module is defined into its own ClassLoader**.
- Retrieve the right ClassLoader of a module via **layer.findLoader(moduleName)** and observe which module a class belongs to.
- Distinguish the two API overloads, and understand how parent layers, module readability, and class-loading delegation work.
- Recognize limitations regarding isolation, type compatibility, and errors when creating a layer.

Scope: JPMS from Java 9 onward; examples use Java 17/21 syntax.

## 2. What Problem Does ModuleLayer Solve?

A **module** is a named unit containing packages, classes, resources, and declarations in **module-info.java** (for example: requires, exports, opens, uses, provides). A **Configuration** is the graph of modules resolved from available modules. A **ModuleLayer** turns a resolved configuration into **Module** instances existing at runtime, while binding each module to a ClassLoader.

The JVM starts with **ModuleLayer.boot()**, containing foundational modules and those resolved at startup. An application can create new layers, for example to load plugins or sets of modules at runtime without putting everything into the boot layer.

A simple mental model:

~~~text
ModuleFinder (reads loadable modules)
    |
    v
Configuration (resolves requires, module graph)
    |
    v
ModuleLayer (defines modules in the JVM)
    |-- module com.demo.api  --> ClassLoader A
    |-- module com.demo.job  --> ClassLoader B
    +-- relationship with parent layer --> ModuleLayer.boot()
~~~

With **defineModulesWithManyLoaders**, the two modules in the new layer have **ClassLoader A != ClassLoader B**. This is an important difference from **defineModulesWithOneLoader**, which creates one shared loader for all modules in the new layer.

## 3. Two Overloads and Parameter Meanings

~~~java
// Instance method on a specific parent layer:
public ModuleLayer defineModulesWithManyLoaders(
        Configuration cf,
        ClassLoader parentLoader);

// Static method, allowing multiple parent layers and returning a Controller:
public static ModuleLayer.Controller defineModulesWithManyLoaders(
        Configuration cf,
        List<ModuleLayer> parentLayers,
        ClassLoader parentLoader);
~~~

- **cf**: the configuration containing the modules to define in the new layer. This configuration must be resolved before calling the API.
- **parentLayers**: the list of parent layers in the exact order corresponding to the parent configurations of **cf**. Appears only on the static overload.
- **parentLoader**: the parent ClassLoader of **each newly created ClassLoader**; you can pass **null** if you want to use the bootstrap class loader as parent. This is a loader relationship, different from the parent layer relationship.
- **Return value**: the instance overload returns **ModuleLayer** directly; the static overload returns **ModuleLayer.Controller**, from which you call **controller.layer()** to obtain the layer, and can adjust certain reads/exports/opens relationships at runtime if truly necessary.

When **parent** is a single ModuleLayer, the following two ways are equivalent in terms of the layer created:

~~~java
ModuleLayer child1 = parent.defineModulesWithManyLoaders(cf, parentLoader);

ModuleLayer.Controller controller =
        ModuleLayer.defineModulesWithManyLoaders(
                cf, List.of(parent), parentLoader);
ModuleLayer child2 = controller.layer();
~~~

These two snippets only illustrate **two ways to call the API**: each call creates a new layer, so **child1 and child2 are not the same object**. In a real application, choose one style.

## 4. ClassLoader Mechanism and Module Readability

### 4.1. One ClassLoader per Module

Suppose the new layer configuration has two modules **com.demo.api** and **com.demo.job**. The method creates two separate ClassLoaders:

~~~text
Layer L
  com.demo.api   --(defined to)--> Loader A --parent--> parentLoader
  com.demo.job   --(defined to)--> Loader B --parent--> parentLoader
         |
         +-- requires com.demo.api
~~~

When Loader B needs a class in a package exported by **com.demo.api** and read by **com.demo.job**, the loader can **delegate directly to Loader A**. This is a package/module-based routing mechanism. It does not mean that Loader A is **getParent()** of Loader B.

When a class name does not map to a module in that routing relationship, the loader forwards to **parentLoader**. For resources, each loader searches resources belonging to the module it manages first before searching through the parent loader, according to the API rules and module encapsulation boundaries.

### 4.2. Readability and Exports Still Apply

- **requires** determines which module needs to read which module during resolution; at runtime there is a corresponding **reads** relationship.
- **exports** allows access to public types of the exported package; **opens** is for deep reflective access where applicable.
- A class being found by a loader **does not automatically grant access** to non-exported packages or unlock private access.
- **parent layer** and **parentLoader** are two different concepts: one describes runtime module relationships, and the other is the parent relationship of class loaders.

Thus, multiple ClassLoaders help organize class-loading namespaces, but **do not turn JPMS into a security sandbox**, nor do they remove Java access rules.

## 5. Complete Example: Loading Two Modules into a New Layer

We have two modules: **com.demo.api** provides a greeting; **com.demo.job** depends on it. The **Launcher** program runs on the classpath, resolves the two modules from the **mods** directory, and creates a layer using the API under study.

### 5.1. Source Structure

~~~text
src/
  com.demo.api/
    module-info.java
    com/demo/api/Message.java
  com.demo.job/
    module-info.java
    com/demo/job/Job.java
Launcher.java
~~~

File **src/com.demo.api/module-info.java**:

~~~java
module com.demo.api {
    exports com.demo.api;
}
~~~

File **src/com.demo.api/com/demo/api/Message.java**:

~~~java
package com.demo.api;

public final class Message {
    private Message() {}

    public static String text() {
        return "Hello from module";
    }
}
~~~

File **src/com.demo.job/module-info.java**:

~~~java
module com.demo.job {
    requires com.demo.api;
    exports com.demo.job;
}
~~~

File **src/com.demo.job/com/demo/job/Job.java**:

~~~java
package com.demo.job;

import com.demo.api.Message;

public final class Job {
    private Job() {}

    public static String run() {
        return Message.text();
    }
}
~~~

### 5.2. Writing the Layer-Initializing Program

File **Launcher.java**:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;

public final class Launcher {
    public static void main(String[] args) throws Exception {
        // 1. Read the compiled modules in the mods/ directory.
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

        // 2. Resolve the root module and its dependency modules.
        ModuleLayer parent = ModuleLayer.boot();
        Configuration cf = parent.configuration().resolve(
                finder,
                ModuleFinder.of(),
                Set.of("com.demo.job"));

        // 3. Each module in the configuration receives a new ClassLoader.
        ModuleLayer.Controller controller =
                ModuleLayer.defineModulesWithManyLoaders(
                        cf,
                        List.of(parent),
                        ClassLoader.getSystemClassLoader());

        ModuleLayer layer = controller.layer();

        // 4. Retrieve ClassLoaders by module name.
        ClassLoader apiLoader = layer.findLoader("com.demo.api");
        ClassLoader jobLoader = layer.findLoader("com.demo.job");

        System.out.println("Different loaders: "
                + (apiLoader != jobLoader));

        // 5. Load the class from the loader of the module containing the class.
        Class<?> jobClass = jobLoader.loadClass("com.demo.job.Job");

        System.out.println("Module: "
                + jobClass.getModule().getName());
        System.out.println("Result: "
                + jobClass.getMethod("run").invoke(null));
    }
}
~~~

Explanation:

1. **ModuleFinder.of(Path.of("mods"))** locates the compiled modules. This is the input for resolving modules; it does not create a layer yet.
2. **resolve(...)** takes **com.demo.job** as the root; the **requires com.demo.api** declaration causes **com.demo.api** to be resolved as well.
3. **defineModulesWithManyLoaders(...)** uses the boot layer as the parent layer. Because the configuration contains two modules, the method creates a separate ClassLoader for each module.
4. **layer.findLoader(...)** returns the loader of the specified module. There is no need to manually create a **URLClassLoader** for each JAR.
5. Reflection invokes the public method **Job.run()** in the exported **com.demo.job** package; **Job** uses **Message** in the module it reads.

### 5.3. Compiling and Running

From the directory containing **src/** and **Launcher.java**, using JDK 17+:

~~~bash
javac --module-source-path src -d mods -m com.demo.api,com.demo.job
javac -d out Launcher.java
java -cp out Launcher
~~~

Expected output:

~~~text
Different loaders: true
Module: com.demo.job
Result: Hello from module
~~~

If you switch to the **parent.defineModulesWithOneLoader(cf, parentLoader)** API, the two modules in the new layer share **the same ClassLoader** and the loader comparison condition in the example will be **false**. The module declarations and **requires** graph do not change merely because of the loader choice.

## 6. Comparing Layer Creation Methods

| API | ClassLoader allocation | Return type (instance/static) | When to use |
| --- | --- | --- | --- |
| **defineModulesWithOneLoader** | One loader for all modules in the new layer | ModuleLayer / Controller | Trusted modules with compatible package structure, and when wanting fewer loaders |
| **defineModulesWithManyLoaders** | Each module in the new layer gets its own loader | ModuleLayer / Controller | Wanting to separate class-definition scopes per module and clearly track which module loads which class |
| **defineModules** | Uses an application-supplied function to map module names to loaders | ModuleLayer / Controller | Needing a custom ClassLoader strategy; must ensure delegation/readability rules yourself |

Creating many loaders typically costs additional objects and class/resource management overhead. Choose the method based on architectural needs and actual measurements, rather than assuming one loader per module is always better.

## 7. Rules and Common Pitfalls

### Configuration Must Match Parent Layers

**cf** must have the exact parent configurations of the layers passed in **parentLayers**, including **order**. Any mismatch throws **IllegalArgumentException**. The instance overload is only appropriate for a configuration with **a single parent configuration**, namely the configuration of the layer on which the method is called.

### Do Not Redefine java.base

A new layer must not contain a module named **java.base**, nor a package named **java** or starting with **java.**. Such cases cause layer creation to fail with **LayerInstantiationException**.

### Module Resolution Is a Separate Step

If **ModuleFinder** cannot find the root module or a dependency, or if there is a constraint conflict during resolution, the error occurs at the **Configuration.resolve(...)** step (for example **FindException**, **ResolutionException**) before calling **defineModulesWithManyLoaders**. Distinguish resolution errors from layer-definition errors.

### Do Not Accidentally Load Classes via the System Class Loader

The new layer holds classes in the new loaders. Calling **Class.forName("com.demo.job.Job")** without specifying a loader, or looking up the class via the system loader, may fail to find the class or pick up another class of the same name in complex environments. Use **layer.findLoader("com.demo.job")** and the appropriate class-loading API.

### Watch Class Identity When Exchanging Data

In the JVM, a class's identity depends on both its **binary name** and its **defining ClassLoader**. Two classes with the same name defined by two different loaders **cannot be cast to one another**. In a plugin architecture, place the shared API in a parent module or layer with a stable loader; communicate through those shared interfaces and objects instead of casting directly between plugin-internal types.

### Do Not Misunderstand Module Unloading

Java has no direct **unload ModuleLayer** API. Classes and loaders can only be collected when no live references keep them alive (including instances, threads, callbacks, caches, ServiceLoader, or TCCL). Creating a new layer does not guarantee old layers automatically disappear.

### Does Not Automatically Guarantee Safety or Prevent All Conflicts

Giving each module its own loader does not mean complete isolation of dependencies, static state, native libraries, the filesystem, or machine resources. JPMS still enforces exports/opens/reads constraints; the loader and module graph design must remain consistent.

## 8. When to Apply in Practice?

- **Plugin systems**: each plugin is a module in its own layer or a set of modules in a new layer, allowing the host to dynamically load resolved modules and identify each module's loader.
- **Tools processing multiple feature groups**: separating modules with different lifecycles and resources.
- **Testing or reloading versions**: creating a new layer for another module version; must ensure reference lifecycles and API contracts when replacing.

For plugins, a common approach is to define a **shared SPI/interface in a parent layer**, have implementation modules use **requires/provides**, and use **ServiceLoader.load(layer, serviceType)** to find providers in the layer. When doing so, the service type received by the host must have the same class identity; avoid bundling multiple copies of the SPI across different loaders.

## 9. Practice Questions

1. What is the difference between **parentLayers** and **parentLoader**? Why can Loader B load classes from Loader A even though **Loader A is not Loader B's getParent()**?
2. When **com.demo.job requires com.demo.api**, does that make all packages of **com.demo.api** publicly accessible?
3. If you want to obtain a **Controller**, which overload do you choose and what condition on parent configurations must be met?
4. If a class with the same name is loaded by two different ClassLoaders, why can casting fail?
5. Modify the example to use the instance overload, then verify that the two ClassLoaders are still different.

## 10. Takeaways

**ModuleLayer.defineModulesWithManyLoaders** defines each module in a Configuration into a **separate new ClassLoader**, while preserving JPMS dependency and access control rules. The workflow to remember is **find modules → resolve Configuration → define ModuleLayer → findLoader → use classes/services**. Specifying the right parent layers and parent loader is required for the model to work as intended.

API documentation: [java.lang.ModuleLayer — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html).