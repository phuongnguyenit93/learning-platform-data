# Resource Lookup in Modular JARs

## 1. Objectives

A JAR can contain classes, configuration files, templates, schemas, images, localization files, and many other resources. Applications typically read these resources using **Class.getResource()**, **ClassLoader.getResource()**, or **getResourceAsStream()**.

When a JAR is used as a named module on the module path, resource lookup is also subject to the encapsulation rules of the Java Platform Module System (JPMS). A resource may exist inside the JAR yet still be invisible to another module if the package containing the resource has not been opened appropriately. Therefore, packaging the right file and granting permission to access the resource are two separate aspects to check.

This lesson explains how to place resources in a modular JAR, differences between lookup APIs, **opens** rules, how to read resources from a module or module layer, and how to diagnose cases where a resource exists yet lookup returns null.

After this lesson, you will be able to:
- Place resources at the right path inside a JAR and inspect artifact contents.
- Distinguish Class relative/absolute paths from ClassLoader paths.
- Understand resource encapsulation in named modules.
- Use **opens** or **--add-opens** when another module needs to read resources in a package.
- Choose the right API when resources belong to the classpath, a module, or a plugin layer.
- Avoid common pitfalls related to duplicate resources, JAR URLs, and caching.

## 2. Resources in JARs and Modular JARs

Resources are data packaged alongside an application or library for the program to read at runtime. Example:

~~~text
com/example/app/
  Main.class
  config/
    defaults.properties
  templates/
    invoice.html
  schema/
    customer.json
  messages/
    messages_vi.properties
~~~

A modular JAR also contains **module-info.class** at the root of the archive:

~~~text
app.jar
  module-info.class
  com/example/app/Main.class
  com/example/app/config/defaults.properties
  com/example/app/templates/invoice.html
~~~

Resources are normally organized by the package or directory corresponding to the owning component. For example, a Maven/Gradle project structure might be:

~~~text
src/
  main/
    java/
      module-info.java
      com/example/app/Main.java
    resources/
      com/example/app/config/defaults.properties
      com/example/app/templates/invoice.html
~~~

During the build, resources from **src/main/resources** are copied to the output directory and then packaged into the JAR at the same relative path. In Gradle, resource processing is typically performed by the **processResources** task; in Maven, resources are handled in the resources lifecycle phase. Build configuration can alter paths or filter content, so inspect the final artifact.

Command to list JAR contents:

~~~bash
jar --list --file app.jar
~~~

Or the short equivalent form:

~~~bash
jar -tf app.jar
~~~

Inspect the module descriptor:

~~~bash
jar --describe-module --file app.jar
~~~

**Having a file in the source tree does not mean the file was packaged.** A resource may be excluded by build configuration, placed in the wrong directory, renamed during filtering, or omitted from the release artifact. When lookup fails, inspect the actual JAR before changing code.

## 3. Resource Naming Rules

Resource paths use forward slashes **/** as directory separators, even when the application runs on Windows. Do not use backslashes in resource names.

Example:

~~~text
com/example/app/config/defaults.properties
com/example/app/templates/invoice.html
com/example/app/messages/messages_vi.properties
~~~

A resource name is a path inside the archive, not a filesystem path on disk. Therefore, do not pass paths like **C:\project\resources\defaults.properties** to ClassLoader.

Several guidelines:

- Use stable package/path names consistent with the module owning the resource.
- Be case-sensitive; JARs and many runtime environments resolve resource paths by exact entry name.
- Do not use **.** characters in place of **/** in a resource path.
- Do not assume resources sit next to the current working directory.
- Avoid generic resource names like **config.properties** if multiple libraries might package the same name.
- Do not put secrets such as passwords, private keys, or tokens into resources inside a JAR; archive contents can be read.

## 4. Class.getResource(): Class-Based Lookup

**Class.getResource(String name)** searches for a resource relative to a specific class. This API's path rules have two forms.

**Relative name:** if `name` does not start with **/**, the path is resolved relative to the class's package.

~~~java
package com.example.app;

public class Main {
    public void loadDefaults() {
        var url = Main.class.getResource("config/defaults.properties");
        System.out.println(url);
    }
}
~~~

For class **com.example.app.Main**, the path searched is:

~~~text
com/example/app/config/defaults.properties
~~~

**Absolute name:** if `name` starts with **/**, the leading slash is stripped and the remainder is resolved from the resource root of the module/JAR.

~~~java
var url = Main.class.getResource(
    "/com/example/app/config/defaults.properties"
);
~~~

Both approaches point to the same resource in the example.

You can read directly as an InputStream:

~~~java
try (var input = Main.class.getResourceAsStream(
        "config/defaults.properties")) {
    if (input == null) {
        throw new IllegalStateException("defaults.properties not found");
    }

    var properties = new java.util.Properties();
    properties.load(input);
}
~~~

**Class.getResource()** is generally suitable when the resource belongs to the class itself or its package. It keeps code from depending on the thread context class loader and makes resource ownership clear.

Note: **getResource()** returns **null** when the resource is not found or when access is disallowed under module encapsulation rules. Check both the path and module access.

## 5. ClassLoader.getResource(): Root Lookup from a Class Loader

**ClassLoader.getResource(String name)** always takes a resource name relative to the root, without a leading **/**.

~~~java
ClassLoader loader = Main.class.getClassLoader();

var url = loader.getResource(
    "com/example/app/config/defaults.properties"
);
~~~

If you use a name with a leading **/**:

~~~java
loader.getResource(
    "/com/example/app/config/defaults.properties"
);
~~~

lookup will normally not find the entry because ClassLoader does not strip the leading slash the way **Class.getResource()** does.

Reading via stream:

~~~java
try (var input = loader.getResourceAsStream(
        "com/example/app/config/defaults.properties")) {
    if (input == null) {
        throw new IllegalStateException("Resource does not exist or is not accessible");
    }

    var properties = new java.util.Properties();
    properties.load(input);
}
~~~

Common ClassLoader APIs:

- **getResource(name)**: returns the URL of the first resource found.
- **getResources(name)**: returns an Enumeration of all resources with the same name found by the loader.
- **getResourceAsStream(name)**: opens the resource as an InputStream; returns null if not found or inaccessible.

ClassLoader is appropriate when the application needs to look up resources from a specific loader, especially in frameworks, application servers, or plugin systems. However, remember that the thread's context class loader may differ from the defining class loader of the current class.

## 6. Comparing Class and ClassLoader

| Criterion | Class.getResource(name) | ClassLoader.getResource(name) |
|---|---|---|
| Relative path | Resolved from the class's package | No concept of package-relative path |
| Absolute path | Starts with **/** | Does not start with **/** |
| Example | **Main.class.getResource("config/app.properties")** | **loader.getResource("com/example/config/app.properties")** |
| Resource owned by | Class/module containing the class | Selected class loader |
| When suitable | Resource belongs to a specific class or package | Loader-based lookup, frameworks, or plugins |
| Result | URL or null | URL or null |

A common mistake is switching code from Class to ClassLoader while keeping the leading **/** on the path. Adjust the path to match the API in use.

If code runs in an environment with multiple class loaders, do not arbitrarily use **ClassLoader.getSystemClassLoader()**. The system loader may not see resources of plugins or application servers. Choose the loader dictated by the application architecture.

## 7. Resource Encapsulation in Named Modules

On the classpath, resources are usually looked up via a class loader and can be seen by many components according to the loader's search order.

In a named module, resources located inside a module's packages are subject to encapsulation rules. **Non-class resources** in a named module's package can only be accessed by another module if that package is opened to the calling module. A resource can exist inside the modular JAR yet lookup from another module still returns null because the package has not been opened.

Example source module:

~~~java
module com.example.settings {
    exports com.example.settings.api;
}
~~~

Resource:

~~~text
com/example/settings/config/defaults.properties
~~~

A consumer module can read the public API of **com.example.settings.api** but cannot necessarily read resources in package **com.example.settings.config**. The **exports** directive does not open a package for deep reflection or resource access.

If another module needs to read resources in the config package, the source module can declare a qualified open:

~~~java
module com.example.settings {
    exports com.example.settings.api;

    opens com.example.settings.config
        to com.example.settings.reader;
}
~~~

In this example, package **com.example.settings.config** is opened to module **com.example.settings.reader**. The consumer module still needs to read the source module, typically with **requires**:

~~~java
module com.example.settings.reader {
    requires com.example.settings;
}
~~~

If all modules need to read resources in the package, you can use an unqualified open:

~~~java
opens com.example.settings.config;
~~~

Or open all packages of the module:

~~~java
open module com.example.settings {
    exports com.example.settings.api;
}
~~~

**open module** allows deep reflection into packages at runtime; it does not automatically export all packages for ordinary code access.

## 8. Use opens or exports?

Choose the directive according to the type of access:

| Need | Suitable Mechanism |
|---|---|
| Consumer imports and calls public classes in a package | **exports p** or **exports p to m** |
| Framework reads non-class resources in a named module's package | **opens p** or **opens p to m** |
| Framework uses deep reflection on private fields/constructors | **opens p** or **opens p to m** |
| Only need to grant open access at runtime without editing the module descriptor | **--add-opens** |
| Grant temporary export for public API at runtime/compile time | **--add-exports** |

For example, if module **com.example.settings.reader** only needs to read properties files in the config package, there is no need to export that package for importing classes. You can use:

~~~java
opens com.example.settings.config
    to com.example.settings.reader;
~~~

If the consumer both needs to call public types in that package and read resources, you can declare both **exports** and **opens**. However, grant only the exact access the integration actually needs.

If the consumer runs in the unnamed module on the classpath, you can open the package at runtime with:

~~~bash
java --add-opens com.example.settings/com.example.settings.config=ALL-UNNAMED -cp app.jar com.example.Main
~~~

**ALL-UNNAMED** applies to unnamed modules in the process. This is a broader scope than a qualified open to a specific named module.

## 9. Module.getResourceAsStream(): Reading Resources from a Specific Module

Once you have a **Module** object, you can read resources directly from that module:

~~~java
Module module = Main.class.getModule();

try (var input = module.getResourceAsStream(
        "com/example/app/config/defaults.properties")) {
    if (input == null) {
        throw new IllegalStateException("Resource not found in module");
    }

    var properties = new java.util.Properties();
    properties.load(input);
}
~~~

The resource name passed to **Module.getResourceAsStream()** is a **/**-separated path without a leading **/** like the absolute form of Class.getResource().

This API is useful when code wants to specify which module owns the resource rather than letting a class loader search across a broader set of resources. It also respects encapsulation: if the resource lies in a named module's package and the package is not open to the calling module, the method may return null.

If a resource is read by code inside the module that owns it, the module can access its own internal resources per the API's rules. If another module needs to read it, open the package to that module.

## 10. ModuleReader: Low-Level Module Content Reading

**ModuleReader** is a low-level API for reading the contents of a module. It is typically useful for module tooling, custom class loaders, or systems that need to list/inspect resources of a specific module.

You can locate a module with **ModuleFinder** and open a **ModuleReference**:

~~~java
ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

ModuleReference reference = finder.find("com.example.settings")
    .orElseThrow();

try (ModuleReader reader = reference.open()) {
    var resource = reader.open(
        "com/example/settings/config/defaults.properties"
    );

    if (resource.isEmpty()) {
        throw new IllegalStateException("Resource not present in module");
    }

    try (var input = resource.get()) {
        byte[] bytes = input.readAllBytes();
        System.out.println(bytes.length);
    }
}
~~~

Related APIs:

- **ModuleFinder** locates modules from the module path or other module sources.
- **ModuleReference** represents a module whose contents can be read.
- **ModuleReader.open(name)** opens a resource as an InputStream if found.
- **ModuleReader.read(name)** can return a ByteBuffer.
- **ModuleReader.find(name)** finds the URI of a resource.
- **ModuleReader.list()** lists resource names in the module.
- **close()** closes the reader and releases associated resources.

Always close ModuleReader and InputStream with try-with-resources. If using **read(name)** to obtain a ByteBuffer, call **release(buffer)** per ModuleReader's contract when finished using the buffer.

ModuleReader is a tool for low-level module operations. For ordinary application code that just needs to read a config file, **Class.getResourceAsStream()** or **Module.getResourceAsStream()** is usually simpler. ModuleReader is also not a mechanism to bypass application access policies; use it only in components responsible for managing module content and class loading.

## 11. Resource Lookup in Plugins and Module Layers

A plugin may live in a separate modular JAR and be loaded into a **ModuleLayer**. In that case, the plugin's resources belong to the corresponding module/plugin layer.

If code already has a plugin class, the simplest approach is usually to load the resource via that class:

~~~java
try (var input = PluginImplementation.class.getResourceAsStream(
        "config/plugin-defaults.properties")) {
    if (input == null) {
        throw new IllegalStateException("Plugin missing default resource");
    }

    // Read plugin configuration.
}
~~~

This ties the resource to the module owning the implementation and avoids guessing the class loader.

If you need to look up resources by module layer, identify the specific module/plugin and use the appropriate module API or ModuleReader. Do not assume **ClassLoader.getSystemClassLoader()** can see all resources of a custom module layer.

When using ServiceLoader for plugins, providers and resources remain two separate concerns:
- **ServiceLoader** locates service implementations according to module descriptors or provider configurations.
- Resource lookup locates data accompanying the implementation.
- Discovering a provider does not automatically open all resource packages of the plugin module to the application.

If a plugin needs to supply configuration to the host, design a clear API: the plugin can read its internal resource itself and return configuration through an interface, or open the specific resource package to the host module. Having the plugin read its own resources generally reduces the package surface that must be opened.

## 12. Resources on the Classpath vs. Module Path

| Characteristic | Classpath | Module path |
|---|---|---|
| Organization | JARs/directories in the unnamed module | Named module or automatic module |
| Common lookup | ClassLoader/Class | Class/ClassLoader/Module |
| Package-level encapsulation | JPMS not enforced as for named modules | Resources in packages are subject to encapsulation rules |
| Opening packages | No module-info to declare opens for unnamed module | Use opens/open module or --add-opens |
| Identifying owner | Usually based on loader and resource path | Owning module can be identified clearly |
| Duplicate resources | Loader may return the first entry by search order | Specify the target module to avoid ambiguity |

A modular JAR placed on the classpath is treated like an ordinary JAR in the unnamed module; its module descriptor is not used to create a named module. When placed on the module path, the module descriptor is used to resolve the module and encapsulation rules take effect.

Therefore, the exact same JAR can produce different resource lookup results depending on how it is launched. If an application works on the classpath yet returns null when moved to the module path, check whether the package containing the resource is opened to the calling module.

## 13. Duplicate Resources and Search Order

Multiple JARs can contain a resource with the same name, for example:

~~~text
config/defaults.properties
~~~

On the classpath, **ClassLoader.getResource(name)** returns the first resource found according to the loader's search mechanism. If multiple libraries package the same name, the result may depend on classpath ordering or parent delegation.

Use **getResources(name)** when you need to list all resources with the same name:

~~~java
Enumeration<URL> resources =
    Thread.currentThread()
        .getContextClassLoader()
        .getResources("config/defaults.properties");

while (resources.hasMoreElements()) {
    System.out.println(resources.nextElement());
}
~~~

Do not assume the result order is a configuration precedence contract unless your loader/application explicitly defines it. If multiple config files must be merged, define the order and merge rules in the application.

In a modular application, if you need a resource from a specific module, use the class/module owning the resource instead of doing a global lookup via the system loader. This reduces the risk of reading the wrong file with the same name from another dependency.

## 14. Resource URLs Are Not Necessarily Files on Disk

A resource in an output directory when running in an IDE may have a **file:** URL. However, when packaged inside a JAR, the URL typically has a **jar:** scheme or a URL form supplied by the class loader.

Illustrative example:

~~~text
file:/app/classes/com/example/config/defaults.properties
jar:file:/app/lib/app.jar!/com/example/config/defaults.properties
~~~

Do not do the following:

~~~java
File file = new File(
    Main.class.getResource("config/defaults.properties").getFile()
);
~~~

This may work when the resource is in a filesystem directory but fails when the resource is inside a JAR. A JAR URL is not a regular filesystem path.

Read the resource via a stream instead:

~~~java
try (var input = Main.class.getResourceAsStream(
        "config/defaults.properties")) {
    if (input == null) {
        throw new IllegalStateException("Resource not found");
    }

    // Process data from input.
}
~~~

If you genuinely need to work with the URL, use **toURI()** and handle the appropriate scheme. For **jar:** URLs, you may need **JarURLConnection** or the JAR FileSystem API. Do not coerce every URL into a **Path** by assuming the scheme is always `file`.

## 15. Encoding and How to Read Content

Text resources need explicit encoding. **Properties.load(InputStream)** uses ISO-8859-1 rules for traditional properties format, whereas UTF-8 files can be read using a **Reader**.

Example reading UTF-8 properties:

~~~java
Properties properties = new Properties();

try (var input = Main.class.getResourceAsStream(
        "config/defaults.properties")) {
    if (input == null) {
        throw new IllegalStateException("defaults.properties not found");
    }

    try (var reader = new java.io.InputStreamReader(
            input,
            java.nio.charset.StandardCharsets.UTF_8)) {
        properties.load(reader);
    }
}
~~~

For JSON, XML, or templates, also specify UTF-8:

~~~java
try (var input = Main.class.getResourceAsStream(
        "schema/customer.json")) {
    if (input == null) {
        throw new IllegalStateException("Schema not found");
    }

    String json = new String(
        input.readAllBytes(),
        java.nio.charset.StandardCharsets.UTF_8
    );
}
~~~

If a resource is large, avoid reading the entire content into a byte array or String unnecessarily. Use streams and parsers capable of sequential processing to reduce memory usage.

## 16. Performance and Caching

Resource lookup is usually cheaper than reading and parsing content repeatedly, though actual cost depends on the class loader, JAR, filesystem, and how data is processed.

Several guidelines:

1. **Do not look up and parse repeatedly on hot paths:** read configuration once when initializing a component if the content does not change.
2. **Cache parsed data when appropriate:** cache parsed Properties/metadata instead of keeping an InputStream open.
3. **Always close streams:** do not hold file handles or JAR connections longer than necessary.
4. **Choose a stable loader:** avoid looking up via the context class loader if the application does not control thread context.
5. **Watch plugin lifecycles:** caching Class, URL, resource, or plugin objects can keep a class loader/module layer alive longer than expected.
6. **Handle reload explicitly:** if configuration reload is supported, define when caches expire and avoid serving stale data.
7. **Measure before optimizing:** do not build complex caches for small resources if lookup is not on a critical execution path.

If opening a URL connection directly and needing to replace resources at runtime or avoid holding a URLConnection cache, you can configure **setUseCaches(false)** before opening the stream. Caching behavior depends on the URL handler; test on the actual deployment environment.

## 17. Common Errors and How to Diagnose Them

| Symptom | Possible Cause | How to Handle |
|---|---|---|
| **getResource() returns null** | Wrong path, resource not packaged, or encapsulated | Inspect the JAR and package opens |
| Class.getResource finds it but ClassLoader.getResource does not | Using a package-relative path or leading / | Switch to root-relative path and remove leading / |
| Works on classpath but returns null on module path | Package containing resource not opened to calling module | Add narrowly scoped opens |
| **FileNotFoundException** when converting URL to File | Resource is inside a JAR; URL is not a file path | Use getResourceAsStream or handle jar URIs |
| Wrong config read | Multiple JARs contain a resource with the same name | Use the owning class/module or getResources to inspect |
| Resource missing from artifact | Build tool did not copy resource or source path is wrong | Check src/main/resources, output, and jar --list |
| Vietnamese text resource has garbled characters | Read using an unsuitable encoding | Use Reader and StandardCharsets.UTF_8 |
| JAR locked or cannot reload | URLConnection/JAR cache or unclosed stream | Close streams, consider setUseCaches(false), and design reload |
| Plugin cannot find resource | Using system loader instead of plugin's loader/module layer | Look up via plugin class or corresponding module layer |

Investigation workflow:

1. Record the exact resource path and lookup API being used.
2. Determine whether the path is class-relative or class-loader root-relative.
3. Use **jar --list --file app.jar** to confirm the entry exists in the artifact.
4. Identify the class/module owning the resource and the module calling the lookup.
5. If the resource belongs to a named module's package, check **opens** to the calling module.
6. If using plugins, inspect the class loader, module layer, and module graph.
7. Repackage and run on the exact same module path environment as production.

## 18. Security When Reading Resources

Resources inside a JAR are not secret storage. Anyone with the artifact can unpack and read resource contents. Do not put secrets, credentials, private keys, or sensitive user data into packaged config files.

If a resource path comes from external input, do not directly concatenate arbitrary paths onto a filesystem directory or file. Validate resource names against an allowlist and prevent path traversal such as **../** when converting resource names into filesystem paths.

When reading resources from a plugin, treat the content as plugin-supplied data. JAR signatures can help verify the signer and integrity under a trust policy, but do not prove the resource or code is safe.

**opens** controls package accessibility across modules; it does not encrypt resources, authenticate users, or create a sandbox. Open packages only to the modules that need them and avoid broad open modules if the application only needs a small resource.

## 19. Self-Check

**1. Why can Class.getResource("config/app.properties") and ClassLoader.getResource("config/app.properties") search two different paths?**

Because Class resolves paths relative to the class's package when the name does not start with /, whereas ClassLoader always searches from the root of the resource path.

**2. A resource exists in a modular JAR, yet ClassLoader.getResource() from another module returns null. What could be the cause?**

The resource resides in a named module's package that has not been opened to the calling module. Check the opens directive or --add-opens configuration.

**3. Is exporting a package sufficient for another module to read resources in that package?**

Not necessarily. Exports is for public API access; resources and deep reflection require the package to be opened under JPMS rules.

**4. Why should you not convert a resource URL directly into a File?**

Because the resource may reside inside a JAR and the URL has a jar: scheme rather than a normal file path. Use InputStream or handle the URL/URI by scheme.

**5. When should ModuleReader be used?**

When you need to read or list module contents at a low level, such as in a custom class loader or module tooling. For ordinary applications, Class or Module resource APIs are simpler.

**6. Why should plugin resource lookup be tied to the plugin class/module?**

Because the system class loader may not see the plugin layer. Looking up through the owning class/module identifies the right module and avoids picking up same-named resources by mistake.

## 20. Takeaways

Resources in modular JARs are located using familiar Java APIs, while named modules add encapsulation rules. **Class.getResource()** supports package-relative or root-absolute paths; **ClassLoader.getResource()** always takes root-relative paths; **Module.getResourceAsStream()** reads resources from a specific module; **ModuleReader** supports low-level module operations.

If another module needs to read resources located in a named module's package, open the package with **opens** or **--add-opens** for the calling module. Always inspect the actual artifact, close streams, handle URLs by scheme, manage duplicate resources, and never treat JAR resources as secret data.

## References

- [Class — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html)
- [ClassLoader — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html)
- [Module — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html)
- [ModuleReader — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleReader.html)
- [ModuleFinder — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleFinder.html)
- [The jar Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html)
- [The Java Module System — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html)
