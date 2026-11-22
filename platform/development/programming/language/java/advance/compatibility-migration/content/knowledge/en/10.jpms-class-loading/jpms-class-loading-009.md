# Resource Loading by Class Loader and Cross-Module Visibility

In Java, finding a class and finding a resource accompanying that class are two related but distinct things. Before Java 9, many applications placed configuration files, templates, images, schemas, or resource bundles inside JARs and used `ClassLoader.getResourceAsStream()` to read them. When moving to the Java Platform Module System (JPMS), the resources still reside inside the JAR, yet accessibility can change depending on the **module owning the resource**, the **package containing the resource**, the **API used to look it up**, and the **class loader performing the lookup**.

A project upgrading the JDK or moving libraries from the classpath to the module path may encounter a situation where classes still load normally and the application still starts up, yet reading a `.properties` or `.xml` file suddenly returns `null`. This lesson explains how Java locates resources, how JPMS restricts visibility, common errors, and testing approaches during migration.

## 1. Distinguishing Classes, Classpath Resources, and Module Resources

A **Class** is a Java type identified by its binary name and defining class loader. A **Resource** is data placed on the classpath, in a module, or in a source that a class loader can provide; a resource is usually identified by a `/`-separated path string.

For example, a JAR with the structure:

~~~text
com/acme/order/OrderService.class
com/acme/order/defaults.properties
com/acme/order/templates/receipt.txt
config/application.properties
META-INF/services/com.acme.spi.Codec
~~~

Some resources can be looked up by name:

~~~text
com/acme/order/defaults.properties
com/acme/order/templates/receipt.txt
config/application.properties
~~~

Resource names in resource-loading APIs normally use `/` even when running on Windows. It is not an operating system file path and does not need to exist as a separate physical file. A resource can be inside a JAR, a runtime image, or a store provided by a custom class loader.

Important differences:

- **Finding a class:** usually relies on the binary name, class resolution mechanism, and class loader.
- **Finding a resource:** relies on the resource name, the rules of the lookup method, loader ordering, modules, and encapsulation rules.
- **Reading a resource:** obtains a `URL` or `InputStream`; whether it can be read also depends on stream handling, encoding, and I/O errors.
- **Finding a class does not guarantee finding a resource in the same package.** JPMS has policies protecting resources inside packages of named modules.

When investigating a migration issue, ask first: where is the resource packaged, which module does it belong to, and which API is used to access it?

## 2. Resource Naming When Using Class and ClassLoader

Two common APIs have different naming rules:

~~~java
Class<?> owner = com.acme.order.OrderService.class;

// Relative to package com.acme.order:
URL samePackage = owner.getResource("defaults.properties");

// Absolute from the root of the Class search area:
URL absolute = owner.getResource("/config/application.properties");

// Search from the root of the class loader; do not add a leading /:
ClassLoader loader = owner.getClassLoader();
URL byLoader = loader.getResource("com/acme/order/defaults.properties");
~~~

### 2.1. Class.getResource / Class.getResourceAsStream

With `SomeClass.class.getResource("name.txt")`, a string not starting with `/` is resolved relative to the package of `SomeClass`.

With `SomeClass.class.getResource("/config/name.txt")`, the leading `/` indicates that the resource name is interpreted as absolute; this `/` is stripped when constructing the name for lookup. This is **not** an absolute path on the filesystem.

Example:

~~~java
package com.acme.order;

public final class OrderService {
    public static InputStream openDefaults() {
        return OrderService.class
                .getResourceAsStream("defaults.properties");
    }
}
~~~

The call above looks up the logical name `com/acme/order/defaults.properties`, not `defaults.properties` at the JAR root.

The advantage of `Class.getResourceAsStream` is that the resource is anchored to the reference class. When the class moves to another package or another module, the resource location must be reviewed accordingly.

### 2.2. ClassLoader.getResource / getResourceAsStream

With `ClassLoader`, the name is specified **relative to the root** of the resource space searched by the loader. Do not use a leading `/`:

~~~java
ClassLoader loader = OrderService.class.getClassLoader();

try (InputStream in = loader.getResourceAsStream(
        "com/acme/order/defaults.properties")) {
    if (in == null) {
        throw new IllegalStateException("Không tìm thấy defaults.properties");
    }
    // Read content from in.
}
~~~

A common mistake is writing `loader.getResourceAsStream("/com/acme/order/defaults.properties")` by inferring from the rules of `Class.getResourceAsStream`. That form does not follow the standard contract of `ClassLoader.getResource` and may return `null`.

### 2.3. The Bootstrap Class Loader May Be Represented by null

`SomeClass.class.getClassLoader()` may return `null` for classes defined by the bootstrap loader. You should not immediately call `getResource` on the result without accounting for this case.

If you want to read a resource associated with a specific class, `SomeClass.class.getResourceAsStream(...)` is usually simpler. If an application-determined loader is needed, explicitly document which loader is selected and why.

## 3. Three Environments to Distinguish: Classpath, Module Path, and Module Layer

Java can run code in several ways:

1. **Classpath / unnamed module:** classes from the classpath belong to the unnamed module of their defining loader. This is the traditional model, commonly seen in unmodularized applications.
2. **Named module on the module path:** a module with a name and possibly `module-info.class`, with package boundaries, exports, opens, and module readability relationships.
3. **Custom module layer / class loader:** plugin applications or containers can create separate layers and class loaders, making resource visibility and lookup order differ from a simple classpath environment.

A module does not by itself imply a separate class loader. Multiple modules can be defined by the same loader, and multiple module layers can use different loaders. Therefore, looking only at the module name is not enough to know the path by which a resource will be searched.

Conceptual diagram pattern:

~~~text
Application
   |
   +-- Classpath -> unnamed module of the loader
   |
   +-- Module path -> named modules
   |                     |
   |                     +-- exports: type API
   |                     +-- opens: reflective access and some resources
   |
   +-- Plugin layer -> separate modules and loaders
                         |
                         +-- different visibility boundaries
~~~

During migration, a JAR moved from the classpath to the module path may still contain the exact same old resources, yet encapsulation mechanics will change because it now belongs to a named module.

## 4. Exports, Opens, and Resource Access Permissions

JPMS introduces two declaration groups that are easily confused:

- `exports com.acme.lib.api;`: allows modules with appropriate readability to access public types in the exported package.
- `opens com.acme.lib.internal;`: opens the package for deep reflection at runtime, and also affects access to resources located inside the named module's package.
- `opens com.acme.lib.internal to com.acme.app;`: opens conditionally to the specified target module.
- `open module com.acme.lib { ... }`: packages in the module are opened under the open module mechanism.

**Exports does not mean opens.** An exported package does not necessarily allow public loader APIs to list or retrieve every resource inside that package.

Example:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
    opens com.acme.catalog.internal to com.acme.app;
}
~~~

Here, `com.acme.catalog.api` is exported so other modules can use public types. The package `com.acme.catalog.internal` is opened only to `com.acme.app`, not automatically opened publicly to every module or every `ClassLoader.getResource` call.

### 4.1. Accessing Resources with Module.getResourceAsStream

Since Java 9, you can access a specific module's resources via `Module.getResourceAsStream(String)`:

~~~java
Module catalogModule = CatalogApi.class.getModule();

try (InputStream in = catalogModule.getResourceAsStream(
        "com/acme/catalog/internal/defaults.properties")) {
    if (in == null) {
        throw new IllegalStateException("Không truy cập được resource");
    }
    // Read the resource.
}
~~~

`CatalogApi` is a public type permitted to be referenced from the calling code in the example. The name passed to `Module.getResourceAsStream` is a `/`-separated resource name with no leading `/`.

For a resource located inside a package of a **named module**, the access rule depends on whether the package is opened to the **caller's module**; code inside the same module is allowed to access that module's own resources. If the package is conditionally opened with `opens ... to ...`, the calling module must be in the permitted set.

A resource that does not belong to a module package may be treated differently from a resource in an encapsulated package. Do not guess solely by the `.properties` extension: the location within packages and the access API are what matter.

`Module.getResourceAsStream` can throw `IOException` on a read error, and returns `null` if not found or inaccessible under the API contract. These two situations must be distinguished during diagnosis.

### 4.2. Specific Restrictions of ClassLoader.getResource in Named Modules

When using `ClassLoader.getResource` or `getResources` to find **non-class-file resources** located inside a package of a named module, JPMS encapsulation rules apply. For this group of APIs, a resource in a named module's package is typically found only when that package is **unconditionally opened**. Conditional `opens p to some.module` does not automatically make the resource public via `ClassLoader.getResource`.

This is why some applications observe:

~~~java
Module target = SomeApi.class.getModule();

// Intentional lookup by module and caller permissions:
InputStream a = target.getResourceAsStream(
        "com/acme/secret/config.xml");

// Lookup by loader may not see the same resource:
InputStream b = SomeApi.class.getClassLoader()
        .getResourceAsStream("com/acme/secret/config.xml");
~~~

Results `a` and `b` are not guaranteed to be the same. The first API knows the exact target module and checks accessibility according to module relationships. The second API looks up via the loader, where encapsulated resources may be hidden.

**Exception to remember:** resources whose names end with `.class` are treated specially in certain class loader resource lookup rules. Do not use the exception for class files as proof that configuration resources in the same package are also public.

### 4.3. Summary Table by Lookup Method

| Access Method | Name Resolution | Points to Note |
|---|---|---|
| `SomeClass.class.getResource("x.txt")` | Relative to `SomeClass`'s package | Anchored to the class; behavior in a named module depends on module/package |
| `SomeClass.class.getResource("/p/x.txt")` | Absolute name after stripping leading `/` | Not a filesystem path |
| `loader.getResource("p/x.txt")` | From the root of the loader's resource space | Has special restrictions for resources in packages of named modules |
| `loader.getResources("p/x.txt")` | Looks up multiple URLs with the same name | Does not guarantee finding encapsulated resources; avoid assuming order |
| `module.getResourceAsStream("p/x.txt")` | Against the specified module | Applies `opens` rules relative to the calling module |
| `Thread.currentThread().getContextClassLoader()` then `getResource` | Via the context loader | Not necessarily the current class's loader |

The table is for choosing the appropriate lookup API; it does not replace determining the module path, class loaders, and `opens` permissions of a specific system.

## 5. Why Can Class.getResource and ClassLoader.getResource Produce Different Results?

In a simple classpath environment, both approaches can find the resource once relative/absolute names are adjusted properly. With JPMS, `Class.getResource` uses the class as an anchor in that class's module context, whereas `ClassLoader.getResource` performs a loader-based lookup and applies loader-specific encapsulation rules.

Therefore, you should not arbitrarily replace:

~~~java
InputStream in = MyComponent.class.getResourceAsStream("rules.json");
~~~

with:

~~~java
InputStream in = MyComponent.class.getClassLoader()
        .getResourceAsStream("com/acme/component/rules.json");
~~~

and assume it is a guaranteed-equivalent refactor. Beyond differences in the path anchor, module boundaries and how resources are read can cause different outcomes.

When code resides inside the module owning the resource, using `Class.getResourceAsStream` anchored to the class or `Module.getResourceAsStream` makes intent clear. When code needs to find plugin resources provided by another loader, `ClassLoader` or the context class loader may be more appropriate, but must have a corresponding visibility design.

## 6. Thread Context Class Loader and Libraries/Plugins

A library sometimes cannot know in advance which class loader holds the classes or resources used by the application. For example, a framework needs to load drivers, plugins, providers, or configuration files deployed by the application. In that case, the library can use the **thread context class loader (TCCL)**:

~~~java
ClassLoader contextLoader =
        Thread.currentThread().getContextClassLoader();

URL config = contextLoader == null
        ? null
        : contextLoader.getResource("plugin/plugin.properties");
~~~

The TCCL differs from the library's defining loader. It can be set by a container or caller so that a framework library finds resources provided by the application/plugin.

Points to remember:

- Do not assume the TCCL always equals `SomeLibrary.class.getClassLoader()`.
- The TCCL can vary across request-handling threads, executor threads, and background threads.
- When running asynchronously, a task may or may not inherit the expected context loader depending on the thread creation mechanism.
- With custom loaders, parent delegation order and how `getResource` is implemented affect the result.
- When crossing module boundaries, the TCCL does not bypass JPMS encapsulation rules.

If the TCCL must be changed temporarily, it must be restored in `finally`:

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    // Call the library designed to use TCCL.
} finally {
    thread.setContextClassLoader(previous);
}
~~~

This is an intentional integration technique, not a default fix for every resource lookup failure. In a multi-plugin environment, setting the wrong context loader can cause code to pick the wrong resource with the same name from another plugin.

## 7. Duplicate Resource Names and Precedence Order

A name such as `config/defaults.properties` may appear in multiple JARs or multiple modules. `ClassLoader.getResource` typically returns one result if found; `ClassLoader.getResources` retrieves an enumeration of matching URLs.

~~~java
ClassLoader loader = Thread.currentThread().getContextClassLoader();

Enumeration<URL> resources =
        loader.getResources("config/defaults.properties");

while (resources.hasMoreElements()) {
    URL url = resources.nextElement();
    System.out.println(url);
}
~~~

The snippet illustrates finding multiple resources; in a real environment you must check that the loader is non-`null` and handle `IOException` appropriately for the context.

You should not design a system relying on the ordering of identically named resources unless that order is guaranteed by the loader contract. With named modules, the order or set of modules searched via a loader may not be the module graph order a developer expects. With custom loaders, behavior also depends on the implementation.

If you want to select the exact configuration of a specific module, **look it up by target module** or use a sufficiently distinct resource namespace, for example:

~~~text
com/acme/catalog/config/defaults.properties
com/acme/payments/config/defaults.properties
~~~

Do not place a generic name such as `config.properties` at the root of multiple JARs and rely on "whichever JAR comes first wins," unless this is a defined and tested contract.

## 8. Resources Not Located in a Java Package

Not every resource in a JAR belongs to a Java package. For example:

~~~text
config/application.properties
templates/receipt.mustache
META-INF/services/com.acme.spi.Codec
META-INF/native-image/...
~~~

A path residing inside a JAR does not automatically mean it is a package declared in JPMS. Encapsulation rules for resources inside packages of named modules must be distinguished from resources outside such packages.

A group of files is often placed outside packages to serve discovery mechanisms or configuration systems. However, placing resources at the JAR root does not by itself solve name collisions or wrong loader selection. Resource names should still be properly namespaced.

In particular, `META-INF/services` is commonly used in the traditional service provider mechanism. In named modules, providing and consuming services have dedicated module declarations; you should not simply replace `ServiceLoader` by reading resource files and loading classes manually.

## 9. ServiceLoader, uses/provides, and Module Layers

`ServiceLoader` is the standard mechanism for discovering providers implementing a service interface. It involves class loaders and resource discovery, but is not merely an ordinary `getResources("META-INF/services/...")` call.

On the classpath, providers are typically listed in:

~~~text
META-INF/services/com.acme.spi.Codec
~~~

A named module can declare:

~~~java
module com.acme.codec.provider {
    requires com.acme.codec.api;
    provides com.acme.spi.Codec
        with com.acme.impl.JsonCodec;
}
~~~

The module using the service can declare:

~~~java
module com.acme.app {
    requires com.acme.codec.api;
    uses com.acme.spi.Codec;
}
~~~

Then the application loads the providers:

~~~java
ServiceLoader<Codec> codecs = ServiceLoader.load(Codec.class);

for (Codec codec : codecs) {
    System.out.println(codec.getClass().getName());
}
~~~

With named modules, check the module descriptor, layer, loader, and provider search path according to the `ServiceLoader` contract. `ServiceLoader.load(service)` uses a mechanism tied to the context class loader; `ServiceLoader.load(layer, service)` can be used when searching for providers within a specific module layer.

In a plugin system, if a custom `ModuleLayer` is created while `ServiceLoader` is called with an inappropriate loader/layer, providers may fail to appear even though the provider module has been resolved. This is a discovery error, not necessarily a missing class or missing resource file.

## 10. ResourceBundle and Multilingual Data

`ResourceBundle` typically uses files:

~~~text
com/acme/app/messages.properties
com/acme/app/messages_vi.properties
com/acme/app/messages_en.properties
~~~

On the classpath, code can read:

~~~java
ResourceBundle bundle = ResourceBundle.getBundle(
        "com.acme.app.messages",
        Locale.forLanguageTag("vi"));

String title = bundle.getString("screen.title");
~~~

In a named-module environment, bundle and provider lookup are also affected by modules, caller context, package visibility, and `ResourceBundle`'s overloads/module-aware APIs. Do not assume every bundle behaves identically to how it did on the classpath.

When migrating:

1. Record the bundle's base name.
2. Check the file location by resource path and package.
3. Check encoding, locale fallback, and keys used.
4. Check the module containing the bundle and related opens/provider rules.
5. Use the appropriate module-aware API if you want to explicitly select the module containing the bundle.
6. Test the locales that the system actually supports.

If a resource bundle is not found, you may receive a `MissingResourceException` instead of `null` as with `getResourceAsStream` calls. Distinguish between an error loading the bundle and a missing key inside the bundle.

## 11. Resources in Modular Libraries and Automatic Modules

A JAR without `module-info.class` placed on the module path can become an **automatic module**. The interoperability and export/open policies of an automatic module differ from a named module explicitly described by `module-info.java`.

During migration, record:

- Whether the JAR has an explicit module descriptor.
- Whether the JAR is placed on the classpath or the module path.
- If it is an automatic module, how the module name is determined.
- If it is an explicit named module, which packages are declared with `exports` and `opens`.
- Which package of the module the resource resides in.
- Which module and loader the code requesting the resource belongs to.
- Whether there is a custom module layer or plugin loader.

Merely seeing a JAR named `some-library.jar` is not enough to conclude whether it runs as an unnamed, automatic, or explicit named module. The same JAR launched differently can lead to different resource lookup behavior.

## 12. Illustrative Model: Configuration-Owning Module and Consuming Module

Suppose there are two modules:

~~~text
com.acme.catalog
  module-info.java
  com/acme/catalog/api/CatalogApi.java
  com/acme/catalog/internal/DefaultsMarker.java
  com/acme/catalog/internal/defaults.properties

com.acme.app
  module-info.java
  com/acme/app/Main.java
~~~

The catalog module declares:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
    opens com.acme.catalog.internal to com.acme.app;
}
~~~

The app module declares:

~~~java
module com.acme.app {
    requires com.acme.catalog;
}
~~~

In `Main`, the application obtains the module from a public API type of catalog:

~~~java
package com.acme.app;

import com.acme.catalog.api.CatalogApi;
import java.io.IOException;
import java.io.InputStream;

public class Main {
    public static void main(String[] args) throws IOException {
        Module catalog = CatalogApi.class.getModule();

        try (InputStream in = catalog.getResourceAsStream(
                "com/acme/catalog/internal/defaults.properties")) {
            if (in == null) {
                throw new IllegalStateException("Resource bị thiếu hoặc không truy cập được");
            }
            System.out.println(in.read());
        }
    }
}
~~~

In the example, the resource resides in package `com.acme.catalog.internal` of a named module. `opens ... to com.acme.app` allows the app module to access the resource under the rules of `Module.getResourceAsStream`. However, you should not expect a call to `CatalogApi.class.getClassLoader().getResource(...)` to automatically find that resource, because the package is not unconditionally opened.

The example uses `in.read()` to prove the stream exists; real application code should parse the file with the proper encoding and format, using `Properties.load`, `InputStreamReader`, or a corresponding parser.

### 12.1. Adding a Resource to an Unopened Package

If the provider moves `defaults.properties` into package `com.acme.catalog.secrets` and the module does not `opens` that package to app, calls from the app module may return `null` even though the file is still packaged in the JAR. Fixing the path alone while overlooking the module policy is not sufficient.

### 12.2. Should You Open Every Package to Avoid Errors?

You should not rush to change it to `open module com.acme.catalog` just so one configuration file can be read. That opens all packages to deep reflection and weakens module encapsulation boundaries. Prefer opening the right package to the right module when the contract requires it, or having the provider expose a public API returning the configuration data instead of forcing consumers to read internal files.

If the resource is an implementation detail, a better design solution may be:

~~~java
public final class CatalogDefaults {
    public static Properties loadDefaults() throws IOException {
        Properties properties = new Properties();
        try (InputStream in = CatalogDefaults.class
                .getResourceAsStream("defaults.properties")) {
            if (in == null) {
                throw new FileNotFoundException("defaults.properties");
            }
            properties.load(in);
        }
        return properties;
    }
}
~~~

When the reading API lives inside the module owning the resource, consumers only call the public API and do not need to know internal paths. For the example to compile, the class needs to import `java.util.Properties`, `java.io.InputStream`, `java.io.IOException`, and `java.io.FileNotFoundException`; the purpose of the snippet is to illustrate how to encapsulate resource reading.

## 13. Do Not Mechanically Convert a Resource URL to a File

An error-prone way to write it:

~~~java
URL url = MyComponent.class.getResource("template.txt");
File file = new File(url.getFile());
~~~

It may work when running from an IDE where the resource is a file in the output directory, yet fail when packaged into a JAR, fat JAR, or custom runtime image. The URL may use the `jar:` scheme, contain percent-encoded characters in its path, or be provided by a custom loader.

If the goal is to read content, prefer streams:

~~~java
try (InputStream in = MyComponent.class
        .getResourceAsStream("template.txt")) {
    if (in == null) {
        throw new IllegalStateException("Thiếu template.txt");
    }

    String content = new String(in.readAllBytes(),
            StandardCharsets.UTF_8);
    System.out.println(content);
}
~~~

The example uses `InputStream.readAllBytes()`, available since Java 9, and requires the corresponding imports. For large files, read in a streaming manner to avoid holding all data in memory. Do not assume an encoding; choose the charset according to the resource's contract.

If an external library requires a `Path` or `File`, you may need to copy the resource to a safely managed temporary directory and delete it after use. That is different from assuming the resource is inherently a real file.

## 14. Packaging Resources in Gradle and Maven

A missing-resource error can also simply be caused by the build not including the file in the artifact. JPMS cannot make a file appear if the file has not been packaged.

In a typical Gradle/Maven structure:

~~~text
src/main/java/...
src/main/resources/com/acme/order/defaults.properties
src/test/resources/...
~~~

Build tools normally place resources from `src/main/resources` into the main output, while test resources have their own scope. Confirm the project's actual source set, filtering, and packaging configuration, because plugins can override defaults.

Check the packaged file:

~~~bash
jar tf build/libs/example.jar
~~~

Or for a Maven artifact:

~~~bash
jar tf target/example.jar
~~~

Look for the exact resource name, including uppercase/lowercase letters. The Windows filesystem is often case-insensitive in many configurations, whereas resource entries inside a JAR have exact names and Linux environments are typically case-sensitive. Case-sensitivity bugs may only surface after deployment.

With multi-module builds, a file may reside in module A's JAR while code in module B uses B's own `getClassLoader` to look it up. Identify the actual artifact containing the resource before modifying module configuration.

### 14.1. Multi-Release JARs

A JAR can contain versioned entries under `META-INF/versions/N/`. When running on different JDKs, the selected class/resource can change according to the multi-release JAR mechanism and the API/JAR loader used. If resources are not uniform across versioned entries, check both manifest metadata and behavior across the target JDKs.

Do not assume that two runtimes load the same resource just because they use the same JAR name. Observe the actual resource read and inspect the input artifact.

## 15. Investigation Workflow When getResource Returns null

When migrating and resource lookup fails, investigate systematically:

**Step 1 — Record the absolute resource name.** If code uses `Class.getResource("x")`, derive the actual package-prefixed name. If using `ClassLoader`, determine whether the code added an incorrect `/`.

**Step 2 — Verify the file in the artifact.** Use `jar tf` or inspect the build output. Check the exact entry name, path, and casing.

**Step 3 — Identify the module containing the resource.** Is it an unnamed, automatic, or explicit named module? Is the JAR running on the classpath or the module path?

**Step 4 — Identify the lookup API.** Is it using `Class.getResource`, `ClassLoader.getResource`, `Module.getResourceAsStream`, `ResourceBundle`, or a custom framework? Each API has a different contract.

**Step 5 — Identify the caller, module, and loader.** Which module does the anchor class belong to? Which module does the caller of `Module.getResourceAsStream` belong to? Is the loader an application, platform, context, or plugin loader?

**Step 6 — Check package and opens.** Is the resource inside a package of a named module? Is the package opened unconditionally or only to a target module? Does the way it is opened satisfy the lookup API being used?

**Step 7 — Check for duplicate names.** Does a resource with the same name exist in multiple JARs/modules? Is the loader returning a different resource than expected?

**Step 8 — Check packaging and environment.** Do the IDE, test runtime, fat JAR, JDK image, and production use the same classpath/module path and the same resources?

**Step 9 — Run a minimal test.** Create a test that reads that exact resource with the same launch configuration, and record the JDK version, class loader, module name, and lookup result.

**Step 10 — Fix at the right layer.** Fix the path if the name is wrong; fix packaging if the file is missing; fix `opens` if valid permission is missing; fix the loader/layer if looking in the wrong place; fix the API design if consumers are having to read internal implementation resources.

### 15.1. Logging Module and Loader Information

In diagnostic code, you can print:

~~~java
Class<?> owner = MyComponent.class;

System.out.println("Class: " + owner.getName());
System.out.println("Module: " + owner.getModule().getName());
System.out.println("Named module: " + owner.getModule().isNamed());
System.out.println("Defining loader: " + owner.getClassLoader());
System.out.println("Context loader: "
        + Thread.currentThread().getContextClassLoader());
~~~

`Module.getName()` may return `null` for an unnamed module. Do not assume two classes share the same loader just because they belong to the same source package; always check the actual classes at runtime.

### 15.2. Do Not Rely on null to Distinguish Too Many Causes

`getResourceAsStream` returning `null` can have many causes: wrong name, unpackaged resource, invisible to the loader, module encapsulation, or wrong module selection. You should not react by switching the entire classpath, opening all modules, or disabling security before pinpointing the exact cause.

## 16. Compatibility Testing During JPMS Migration

Test at least the deployment combinations that are actually supported:

| Combination | How It Runs | What to Verify |
|---|---|---|
| Legacy | Everything on classpath | Old resource lookups still work |
| Mixed | Classpath application, libraries may be modules | Whether loader/module lookup is accurate |
| Modular | Named modules on module path | `exports`, `opens`, and resource visibility |
| Plugin | Custom loader or layer | Whether modules/resources are found via the right loader/layer |
| Packaged | JAR/fat JAR/runtime image | Resources actually exist inside the final artifact |
| CI/prod | Target JDK and OS | Consistent paths, encoding, and behavior |

The test suite should include:

- Resource in the same package as its owning class.
- Resource in a different package within the same module.
- Resource in a package opened (`opens`) to only one module.
- Resource in an unopened package.
- Resource at the JAR root or outside packages.
- Resource with duplicate names in two dependencies.
- Resource read via context loader and custom loader if the application uses plugins.
- Resource read after packaging the real artifact, not only inside the IDE.
- Locale bundles and service providers if the application uses them.

For sensitive resources, tests should confirm that the package is **not permitted** to be accessed from unintended modules. The correctness of modularization is not only "being able to read the files that need to be read" but also "not exposing additional resources outside the contract."

## 17. Pre-Release Checklist

- [ ] Distinguished `Class.getResource`, `ClassLoader.getResource`, and `Module.getResourceAsStream`.
- [ ] Confirmed relative/absolute resource names and the `/` rule.
- [ ] Verified resources are present in the final JAR/runtime image.
- [ ] Identified the class loader and module of the class/caller at runtime.
- [ ] Determined whether the package containing the resource belongs to a named module.
- [ ] Distinguished `exports` and `opens`, including conditional opening.
- [ ] Checked the rule requiring unconditional opening for certain lookups via `ClassLoader`.
- [ ] Checked TCCL, custom loaders, and module layers if plugins/frameworks are used.
- [ ] Considered duplicate resource names and unguaranteed lookup order.
- [ ] Tested ResourceBundle/ServiceLoader with appropriate APIs if used.
- [ ] Checked stream reading, stream closing, and encoding.
- [ ] Tested after packaging and on the target JDK/OS.
- [ ] Avoided opening the entire module just to work around a resource path issue.

## 18. Conclusion

Resource loading in Java depends on the **resource name**, the **anchor class or loader**, the **module owning the resource**, and **encapsulation rules**. When moving from the classpath to JPMS, a resource may still exist inside the JAR yet fail to be returned by `ClassLoader.getResource` if it lies in a named module's package that is not appropriately opened. `Module.getResourceAsStream` provides explicit access by module and caller permissions; `Class.getResourceAsStream` is convenient when the resource belongs to a class's implementation; `ClassLoader` and TCCL are better suited for certain plugin designs or resource discovery.

When errors occur, do not assume it is a path mistake or missing file. Verify in turn the artifact, path, lookup API, module, loader, `opens`, and launch configuration. Combining tests on the classpath, module path, custom layers, and the final artifact will help ensure the migration preserves both resource readability and the encapsulation boundaries established by JPMS.
