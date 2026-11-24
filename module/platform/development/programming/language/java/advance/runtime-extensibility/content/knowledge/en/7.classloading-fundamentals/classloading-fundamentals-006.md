# Loading Classes from URLClassLoader and Casting to a Shared Contract Type

## 1. The Problem: Host Does Not Compile Directly Against Plugin Classes

An application may need to load extra behavior from an external JAR at startup or when a user installs a plugin. The host should not have to import and recompile every time a new implementation appears. Instead, **the host and plugin agree on a shared Java contract**, such as a `GreetingPlugin` interface; the host uses `URLClassLoader` to locate classes inside the JAR, instantiate them, and invoke instances through the shared interface.

For example, a plugin provides class **example.impl.VietnameseGreeter**, while the application knows only **example.ext.Greeter**:

~~~text
Host (knows interface Greeter)
          |
          | locate JAR and plugin class name from config
          v
URLClassLoader -> example.impl.VietnameseGreeter
          |
          | verify implements Greeter, create instance
          v
Greeter greeter -> greeter.greet("Java")
~~~

Crucially, **both sides must use the exact same `Class` object of the `Greeter` interface**, provided by a shared class loader (typically the plugin loader's parent). In the JVM, identical class names are not enough to guarantee an object can be cast: **a class's identity is bound to its binary name and the class loader that defined it**.

This lesson walks step-by-step through: creating a shared contract, packaging a separate provider into a JAR, building a `URLClassLoader`, loading a class unknown at compile time, checking the contract, performing a checked type conversion, and using the instance. Then it analyzes common errors and lifecycle management.

## 2. Distinguishing Three Roles in Class Loading

| Component | Role | Who sees it at compile time? |
|---|---|---|
| **API/SPI contract** | `Greeter` interface defining shared methods | Both host and plugin |
| **Plugin implementation** | `VietnameseGreeter` class implementing `Greeter` | Plugin; host does not import it directly |
| **Host/Plugin Loader** | Knows JAR path, class FQN, validates and instantiates implementation | Host; it only needs the interface |

**API (Application Programming Interface)** is what host code calls; when serving as an extension point, the contract providers must implement is commonly called **SPI (Service Provider Interface)**. In this example, the same `Greeter` interface fills both roles. Place the interface in a small, stable API library loaded first by the host and referenced by plugins.

**URLClassLoader** takes URLs pointing to **JARs** or **directories containing `.class` files laid out by package**, and searches for classes/resources inside them. It is a `ClassLoader`, meaning it has parent delegation. Common constructor:

~~~java
// Illustrative fragment: Greeter is the shared interface, jarUrl points to the plugin JAR.
URLClassLoader pluginLoader = new URLClassLoader(
        new URL[] { jarUrl },
        Greeter.class.getClassLoader()
);
~~~

- The first parameter is the array of plugin/dependency URLs to load; for JARs on disk, build them with **Path.toUri().toURL()**.
- The second parameter is the **parent loader**, here the very loader that loaded the `Greeter` contract. This prevents the plugin from using a separate copy of `Greeter` from the one the host uses.
- By default, `URLClassLoader` **asks the parent first** before searching its own URLs; this is *parent-first delegation*. If the implementation class is already present on the parent classpath, the parent may return that copy rather than the one in the new JAR.

Loading a class from a JAR does not automatically create an instance. Calling **loadClass(name)** returns a **Class<?>**, not a **Greeter**.

## 3. Why Can Same-Named Classes Still Fail to Cast?

The JVM distinguishes reference types by **which class loader defined the class/interface**. Imagine two independent loaders:

~~~text
AppLoader                     IsolatedPluginLoader
  |                                  |
  +-- example.ext.Greeter            +-- example.ext.Greeter
       (Class object A)                   (Class object B)
~~~

Two interfaces with the same binary name **example.ext.Greeter** defined by two different defining loaders: **A != B**. A plugin class implementing interface B will **not** be an instance of interface A in the eyes of the host. Having identical package, methods, and signatures does not overcome this difference.

Common symptoms:

- **ClassCastException** when the host casts the instance to its own `Greeter`.
- **Class.asSubclass(Greeter.class)** throws `ClassCastException` because the implementation is not assignable to the interface known by the host.
- Messages of the form *X cannot be cast to X* can appear when two distinct `Class` objects with the same binary name were loaded through different loaders.
- When the host invokes a reflective method with an API-typed parameter from a different loader, it may encounter `IllegalArgumentException` or linkage errors.

An appropriate loader design normally looks like:

~~~text
Application/Shared API ClassLoader
  +-- example.ext.Greeter        <-- single shared definition
  +-- example.host.PluginHost
  |
  +-- child URLClassLoader
        +-- example.impl.VietnameseGreeter
              implements Greeter from parent
~~~

**Key checkpoint:** **Greeter.class.isAssignableFrom(rawClass)** must return `true`, or use **rawClass.asSubclass(Greeter.class)** directly to narrow `Class<?>` to `Class<? extends Greeter>` with a runtime check. If it fails, do not try blind casts or `setAccessible(true)` to "bypass" type constraints.

## 4. Complete Java 17 Example: Loading Provider JAR, Converting to Interface, Calling Business Logic

This standalone example intentionally uses a plugin JAR **not on the host's classpath**. The host knows only the JAR path, the binary class name, and the `Greeter` interface. Building with plain JDK tools lets you inspect `URLClassLoader` behavior directly without Spring or any plugin framework.

### 4.1. Directory Structure

Create the following directory tree from an empty working directory, e.g. **urlclassloader-demo**:

~~~text
urlclassloader-demo/
├── api/
│   └── src/
│       └── example/ext/Greeter.java
├── plugin/
│   └── src/
│       └── example/impl/VietnameseGreeter.java
├── host/
│   └── src/
│       └── example/host/PluginHost.java
└── build/                         # will be created by compile commands
    ├── api/
    ├── plugin/
    ├── host/
    └── vietnamese-greeter.jar
~~~

The three source groups are separated to clarify dependencies. The API contract is compiled first; the plugin implementation uses that API; the host also uses that API, yet the plugin JAR must not be placed on the classpath when running.

### 4.2. Creating the Contract in API

**File api/src/example/ext/Greeter.java**:

~~~java
package example.ext;

public interface Greeter {
    String greet(String name);
}
~~~

The host compiles against this exact interface. The plugin also compiles against this interface, yet in the later step the plugin JAR will **contain only the implementation**, without repackaging `Greeter.class`.

In real projects, the interface should document `null` handling, errors, thread safety, lifecycle, and supported API versions in JavaDoc. The example stays minimal to focus on class loaders and casting.

### 4.3. Creating the Implementation in Plugin

**File plugin/src/example/impl/VietnameseGreeter.java**:

~~~java
package example.impl;

import example.ext.Greeter;

public final class VietnameseGreeter implements Greeter {
    public VietnameseGreeter() {
        // Public no-arg constructor for the host to invoke via reflection.
    }

    @Override
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

The plugin class is **public**, implements `Greeter`, and has a **public no-argument constructor**. These are prerequisites for instantiating via **getConstructor().newInstance()** in this example; they are not mandatory for all plugin models. A plugin requiring dependencies/constructor arguments can use a factory invoked by the host under a different contract.

### 4.4. Host Creates Loader, Checks, and Converts Type

**File host/src/example/host/PluginHost.java**:

~~~java
package example.host;

import example.ext.Greeter;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;

public final class PluginHost {
    private static final String IMPLEMENTATION_CLASS =
            "example.impl.VietnameseGreeter";

    public static void main(String[] args) throws Exception {
        Path jar = Path.of("build", "vietnamese-greeter.jar")
                .toAbsolutePath();

        if (!Files.isRegularFile(jar)) {
            throw new IllegalArgumentException("Plugin JAR not found: " + jar);
        }

        URL[] locations = { jar.toUri().toURL() };
        ClassLoader apiLoader = Greeter.class.getClassLoader();

        try (URLClassLoader pluginLoader =
                new URLClassLoader(locations, apiLoader)) {

            // Step 1: load the class descriptor; plugin instance is not created yet.
            Class<?> rawClass =
                    pluginLoader.loadClass(IMPLEMENTATION_CLASS);

            // Step 2: check who defined the class and whether it honors the contract.
            System.out.println("Loaded by plugin loader: "
                    + (rawClass.getClassLoader() == pluginLoader));
            System.out.println("Implements shared Greeter: "
                    + Greeter.class.isAssignableFrom(rawClass));

            // Step 3: narrow Class<?> to Class<? extends Greeter>.
            Class<? extends Greeter> pluginClass =
                    rawClass.asSubclass(Greeter.class);

            // Step 4: instantiate via the public no-arg constructor.
            Greeter plugin = pluginClass.getConstructor().newInstance();

            // Step 5: from here on, the host only needs the Greeter type.
            System.out.println(plugin.greet("Java"));
        }
    }
}
~~~

Boundary-by-boundary explanation:

1. **Path.toUri().toURL()** creates a valid file URL even when paths contain spaces; avoid hand-concatenating **file:** strings without escaping.
2. **Greeter.class.getClassLoader()** is the loader of the API the host compiled against. It serves as the plugin loader's parent.
3. **pluginLoader.loadClass("example.impl.VietnameseGreeter")** returns `Class<?>`. The name must be a **fully qualified binary name**, not a `.java`/`.class` filename or slash-separated path.
4. **isAssignableFrom** checks subclassing/interface implementation at runtime. For an interface, it returns `true` if the tested class implements that interface directly or indirectly with matching type identity.
5. **asSubclass** checks again and produces a value of type **Class<? extends Greeter>**. If invalid, it throws **ClassCastException** instead of letting the host instantiate an incompatible object.
6. **getConstructor().newInstance()** locates the **public** no-argument constructor and creates the object. That is when required class/instance initialization executes; plugin constructors or static initializers can fail.
7. **greet** is invoked through the interface; the host does not need to import `VietnameseGreeter` or reflectively invoke `greet`.
8. **try-with-resources** closes the `URLClassLoader` once finished in the example. Closing the loader does not mean Java immediately GCs all loaded classes or objects.

### 4.5. Compiling and Packaging Without Putting the Plugin JAR on the Host Classpath

From **urlclassloader-demo**, run on Linux/macOS (bash):

~~~bash
mkdir -p build/api build/plugin build/host

javac --release 17 -encoding UTF-8 -d build/api \
  api/src/example/ext/Greeter.java

javac --release 17 -encoding UTF-8 -cp build/api -d build/plugin \
  plugin/src/example/impl/VietnameseGreeter.java

jar --create --file build/vietnamese-greeter.jar -C build/plugin .

javac --release 17 -encoding UTF-8 -cp build/api -d build/host \
  host/src/example/host/PluginHost.java

java -cp build/api:build/host example.host.PluginHost
~~~

On Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/api, build/plugin, build/host | Out-Null

javac --release 17 -encoding UTF-8 -d build/api api/src/example/ext/Greeter.java

javac --release 17 -encoding UTF-8 -cp build/api -d build/plugin plugin/src/example/impl/VietnameseGreeter.java

jar --create --file build/vietnamese-greeter.jar -C build/plugin .

javac --release 17 -encoding UTF-8 -cp build/api -d build/host host/src/example/host/PluginHost.java

java -cp "build/api;build/host" example.host.PluginHost
~~~

Note the **classpath separator**: **:** on Linux/macOS and **;** on Windows. Java's **-cp** argument contains only **build/api** and **build/host**, without the plugin JAR. The plugin is found via the URL passed to `URLClassLoader`, which is the core point of the lesson.

**Exact expected stdout** with JDK 17+ and the directory tree above:

~~~text
Loaded by plugin loader: true
Implements shared Greeter: true
Xin chào, Java!
~~~

The first `true` appears because **VietnameseGreeter** exists only inside the plugin JAR and was defined by the child `URLClassLoader`. The second `true` appears because the class was compiled to implement **the exact same `Greeter` interface** provided by the parent. The last line confirms the host uses the instance through the shared contract.

**If run on a console configured with an encoding other than UTF-8**, Vietnamese characters may display garbled even though the Java logic is correct; the compile command uses **-encoding UTF-8** so the string literal is stored properly in bytecode.

### 4.6. Checking That the JAR Contains the Right Class

To list entries in the JAR (similar command on both operating systems):

~~~bash
jar --list --file build/vietnamese-greeter.jar
~~~

The contents must include **example/impl/VietnameseGreeter.class**. Because the packaging command reads from **build/plugin**, the example omits **example/ext/Greeter.class** from the JAR. This ensures the host supplies one shared API rather than plugins bundling their own contract definitions.

## 5. Why Use asSubclass Instead of Arbitrary Class Casting?

The value from **loadClass** has type **Class<?>**; the compiler cannot know ahead of time whether it implements `Greeter`. The following snippet is unsafe:

~~~java
// Illustrative snippet of an approach to avoid:
Class<?> raw = pluginLoader.loadClass("example.impl.VietnameseGreeter");

// Directly casting Class lacks strong compile-time type checking;
// easily produces an unchecked warning if cast to Class<Greeter>.
// Class<Greeter> also does not represent all subclasses of Greeter.
@SuppressWarnings("unchecked")
Class<Greeter> unchecked = (Class<Greeter>) raw;
~~~

Use instead:

~~~java
// Illustrative snippet; pluginLoader variable is available inside the try block.
Class<?> raw = pluginLoader.loadClass("example.impl.VietnameseGreeter");
Class<? extends Greeter> typed = raw.asSubclass(Greeter.class);
Greeter result = typed.getConstructor().newInstance();
~~~

Key differences:

- **Greeter.class.isAssignableFrom(raw)** returns a `boolean` so you can check or build a custom error message.
- **raw.asSubclass(Greeter.class)** directly performs the type check and returns `Class<? extends Greeter>`, working cleanly even for classes implementing the interface through superclasses.
- **Greeter.class.cast(object)** is used when you already have an `Object` and want to cast an **instance** with a runtime check; it does not replace narrowing `Class` when you need a typed `Class` before instantiation.
- **(Greeter) object** also checks at runtime, yet does not clarify multi-loader mismatches or inform reflection APIs as early as `asSubclass`.

Equivalent example when creating the instance first and casting afterward:

~~~java
// Illustrative snippet: valid, but type mismatch surfaces later.
Object object = raw.getConstructor().newInstance();
Greeter plugin = Greeter.class.cast(object);
~~~

**Do not use Class.newInstance()**: the old method has been deprecated since Java 9; prefer **getConstructor().newInstance()** if the constructor is public, or a clearly designed factory. Do not call **setAccessible(true)** by default, because a production plugin should expose an entry point with valid access without breaking encapsulation.

## 6. Class Loading, Class Initialization, and Object Creation Are Different Steps

Distinguish:

| Operation | What happens |
|---|---|
| **pluginLoader.loadClass(fqn)** | Requests finding/loading the class by name, normally **without initializing the class** |
| **Class.forName(fqn, false, pluginLoader)** | Requests loading/linking with class initialization set to **false** |
| **Class.forName(fqn, true, pluginLoader)** | Requests **class initialization** as well (may run static initializers) |
| **rawClass.asSubclass(Greeter.class)** | Checks type relationship and narrows the `Class` type, **does not create an instance** |
| **typed.getConstructor().newInstance()** | Calls constructor to create an instance; class is initialized if needed |
| **plugin.greet(...)** | Runs business logic through the shared contract |

`loadClass` can trigger loading of related classes, reading JAR data, and linking errors; "no instance created yet" does not mean "zero side effects or cost." Static initializers run when the JVM initializes the class per Java rules, such as before the first instantiation if the class has not initialized yet.

If a plugin requires configuration, tokens, dependencies, or parameterized constructors, do not force a public no-arg constructor. A **PluginFactory** contract or a static factory entry point with an agreed method/signature fits better. You still need to **convert to the shared API type** before letting the host invoke business operations.

## 7. Parent-First Delegation and Failure Points

### 7.1. Choose the Parent to Share the Contract

In the example, we used:

~~~java
ClassLoader parent = Greeter.class.getClassLoader();
URLClassLoader loader = new URLClassLoader(
        new URL[] { pluginJar.toUri().toURL() },
        parent
);
~~~

The parent **must see and provide the exact `Greeter`** the host uses. If you pick a parent that sees only JDK classes while the plugin URL contains another copy of `Greeter`, you can end up with two same-named types that cannot be cast to one another.

A special case is if **Greeter** is loaded by the bootstrap loader, where **Greeter.class.getClassLoader()** may be `null`; `URLClassLoader` accepts a `null` parent, yet that is unsuitable if other shared APIs are only visible to an application parent. When building a real plugin host, identify the full API boundary and pick the parent accordingly.

### 7.2. Parent-First Can Also Cause the "New Plugin" to Be Ignored

If the host launch command accidentally adds the plugin JAR to the **application classpath**, the parent can load `VietnameseGreeter` itself. Then:

~~~java
rawClass.getClassLoader() == pluginLoader
~~~

may return **false**. The class still implements `Greeter`, yet it was not defined by the new `URLClassLoader` as you expected. Check the host's classpath and **ProtectionDomain/CodeSource** when verifying where a class came from.

### 7.3. Do Not Blindly Switch to Child-First for All Packages

Plugin frameworks sometimes need **child-first** to isolate dependency library versions. However, if you also prioritize child-first for shared API packages, a plugin can redefine `Greeter` and break casting.

An advanced loader policy typically keeps **parent-first for API/JDK packages**, and only considers child-first for designated implementation/dependency packages. Default `URLClassLoader` does not implement this custom policy for you; design, test, and analyze package collisions carefully if building a custom `ClassLoader`.

### 7.4. Why Is Copying the Same Interface Class into the Plugin JAR a Design Smell?

In the parent-first example, an accidentally bundled `Greeter.class` inside the JAR might still be ignored once the parent finds its own copy; thus **having a duplicate file in the JAR does not always cause casting to fail immediately**. Yet shipping duplicate APIs:

- makes contract versions hard to control,
- increases loader confusion when switching to child-first or isolated loaders,
- can trigger `LinkageError`/`NoSuchMethodError` when runtime and compile-time APIs diverge,
- misleads authors into thinking the plugin carries its own private API definition.

Prefer a host-owned API artifact, have plugins declare it as **provided/compileOnly** in build tools, and exclude the API from the plugin JAR.

## 8. Error Handling During Loading and Type Conversion

A real host should report errors clearly by stage: **locate file → load class → check contract → instantiate → invoke business logic**. The table below lists key failures:

| Symptom/exception | Common cause | Investigation direction |
|---|---|---|
| **ClassNotFoundException** | Wrong class name, class missing from JAR, URL not pointing to right JAR/directory | Check binary name, `jar --list`, path/URL |
| **NoClassDefFoundError** | Referenced dependency class missing, or class previously failed initialization | Inspect plugin dependencies and root cause; do not look only at the entry-point class |
| **ClassCastException** at `asSubclass` or cast | Plugin does not implement the right contract, or two API definitions exist across two loaders | Check `isAssignableFrom`, contract loader, and actual interface |
| **NoSuchMethodException** at `getConstructor` | Missing public no-arg constructor | Expose proper constructor or use a factory contract |
| **IllegalAccessException** | Constructor/class not accessible from host | Check visibility/module boundaries |
| **InvocationTargetException** | Plugin constructor itself threw an exception | Inspect **getCause()** for constructor error |
| **ExceptionInInitializerError** | Static initialization failed | Inspect static initializer and cause |
| **UnsupportedClassVersionError** | Plugin compiled for a newer JDK than the running JVM | Adjust Java target or upgrade runtime |
| **NoSuchMethodError/AbstractMethodError** | Host and plugin APIs are binary-incompatible | Check API artifact versions and dependencies |
| **IOException** when closing or reading JAR | File, resource, or loader-closing issue | Log path and cause; ensure cleanup |

**ClassNotFoundException** and **NoClassDefFoundError** are not the same: the first is typically a failure when explicitly looking up a class by name; the second usually appears when the JVM needed a dependent class definition and could not link/load/initialize it in the relevant context.

A clear error-wrapping pattern (illustrative fragment; placed in host code with loader and class name already defined):

~~~java
try {
    Class<?> raw = loader.loadClass(className);
    Class<? extends Greeter> typed = raw.asSubclass(Greeter.class);
    return typed.getConstructor().newInstance();
} catch (ClassNotFoundException e) {
    throw new IllegalStateException("Missing plugin class: " + className, e);
} catch (ClassCastException e) {
    throw new IllegalStateException(
            "Plugin does not implement shared Greeter: " + className, e);
} catch (ReflectiveOperationException e) {
    throw new IllegalStateException(
            "Cannot create plugin: " + className, e);
}
~~~

This is an **illustrative method fragment**, not a standalone program: the example assumes the code sits in a method returning `Greeter`, with `loader`, `className`, imports, and the `Greeter` contract available. Some `LinkageError`s or plugin runtime errors are not caught by the blocks above; at the plugin-loading boundary you may want to record them without swallowing system errors indiscriminately.

When using **getConstructor().newInstance()**, an exception thrown by the constructor is normally wrapped in **InvocationTargetException.getCause()**. The host can classify plugin/configuration errors separately instead of turning everything into a "class not found" message.

## 9. What Do URLs Point To and How Are Plugin Dependencies Resolved?

### 9.1. JARs or `.class` Directories

`URLClassLoader` accepts URLs pointing to JARs or directories containing classes/resources laid out in standard package paths:

~~~java
// Illustrative fragment; paths already exist:
URL jarUrl = Path.of("plugins", "greeter.jar")
        .toAbsolutePath().toUri().toURL();

URL classesUrl = Path.of("plugins", "classes")
        .toAbsolutePath().toUri().toURL();
~~~

**A file URL ending with `/` is treated as a directory**; a URL to a JAR file is handled as a JAR. Calling **Path.toUri()** on an existing directory makes the JDK produce the proper directory URI. For class **a.b.C**, the root directory must contain **a/b/C.class**, not point directly into package `a/b`.

Do not build URLs by concatenating **"file:" + path.toString()**: Windows paths, spaces, Unicode characters, and encoding easily break.

### 9.2. Libraries Needed by the Plugin

If `VietnameseGreeter` uses an extra library JAR absent from the parent, supply that URL in the URL array:

~~~java
// Illustrative fragment:
URL[] locations = {
        Path.of("plugins", "greeter.jar").toUri().toURL(),
        Path.of("plugins", "helper-lib.jar").toUri().toURL()
};
URLClassLoader loader =
        new URLClassLoader(locations, Greeter.class.getClassLoader());
~~~

`URLClassLoader` does not automatically discover every JAR inside a directory simply because you passed that directory's URL. Specify each JAR explicitly, or use controlled build/deployment/`Class-Path` manifest mechanisms. Pay special attention to shared API libraries: the version the plugin compiled against must be compatible with the API provided by the parent.

### 9.3. Resources and ServiceLoader

`URLClassLoader` can also locate resources inside the plugin JAR (configs, schemas, etc.). If the plugin declares services via **META-INF/services**, the host can combine it with:

~~~java
// Illustrative fragment for when the plugin declares a valid SPI:
ServiceLoader<Greeter> services =
        ServiceLoader.load(Greeter.class, pluginLoader);

for (Greeter candidate : services) {
    System.out.println(candidate.greet("Java"));
}
~~~

Here **ServiceLoader** handles provider discovery and instantiation per SPI rules instead of the host tracking a specific class name. **Condition:** the plugin must register a valid service; the section 4 example JAR has no `META-INF/services`, so that example alone would not be automatically discovered by `ServiceLoader`.

Extensibility changes at the discovery/instantiation step, yet the **shared contract class loader** principle remains identical. Do not confuse `ServiceLoader` with `URLClassLoader`: **URLClassLoader provides class/resource lookup**, whereas **ServiceLoader uses service metadata to locate providers**.

## 10. Managing URLClassLoader and Plugin Lifecycles

`URLClassLoader` implements **Closeable/AutoCloseable**, so try-with-resources can be used:

~~~java
try (URLClassLoader loader = new URLClassLoader(urls, parent)) {
    // load classes, instantiate, and use plugin
}
~~~

**close()** closes opened file handles/JARs and prevents the loader from loading additional new classes/resources defined by it. However:

- Already-loaded classes and objects **do not vanish immediately** merely from `close()`.
- GC can reclaim loader/class metadata only when **no strong references remain** to the loader, `Class`, instances, threads, context class loaders, static registries/callbacks, or objects holding them.
- If the plugin creates threads, executors, timers, streams, sockets, file handles, etc., the plugin/host must close them per a separate lifecycle contract.
- Do not close the loader while the plugin still needs to load additional unvisited classes (e.g., first use of a secondary feature) or still has concurrent requests running.
- Do not call **close()** concurrently while another thread is loading a class through that loader; the API docs make no guarantees about the outcome of an in-flight load.

In a small example, having the host finish using the plugin before exiting `try` is reasonable. For long-running plugins, keep the loader alive for the plugin session and close it only after **stop accepting requests → finish in-flight work → close plugin → unregister callbacks → close loader**.

**URLClassLoader is not an automatic hot-reload API.** To swap a plugin version, a design usually needs to create a new loader for the new JAR, route traffic to the new instance, shut down the old instance, and drop all references to the old loader. Replacing a JAR file on disk does not mutate `Class` objects already defined by the JVM.

## 11. Security Boundaries and Limits of the Mechanism

**Loading a JAR with URLClassLoader executes Java code in the same JVM**, not in a sandbox. Constructors, static initializers, and plugin methods can run arbitrary code with the process's privileges. `URLClassLoader` does not inherently provide strong security boundaries, timeouts, CPU/RAM limits, thread isolation, or rollback of plugin actions.

For third-party plugins:

1. Verify artifact origin (checksum/signature per release policy) and control who is allowed to install plugins.
2. Load plugins only from managed directories; validate canonical paths and avoid letting arbitrary inputs open network URLs.
3. Constrain API versions, dependencies, and supported OS/JDK targets.
4. Design timeouts, thread/resource ownership, and contextual business error handling.
5. If plugin code is untrusted or requires genuine isolation, consider a **separate process/container** communicating via IPC/RPC instead of running in the same JVM.

Do not use a class loader as a way to stop malicious code from accessing files, network, or host memory. It is primarily a **class loading and namespace mechanism**.

## 12. Interaction with the Java Platform Module System (JPMS)

The runnable example in section 4 runs on the **classpath**, so classes in the plugin JAR are loaded into the **unnamed module** associated with the `URLClassLoader`. Creating a `URLClassLoader` **does not automatically resolve a named module** merely because the JAR contains **module-info.class**.

When an application deploys on the **module path** with module descriptors, also keep in mind:

- An API in a named module must **export** its package so plugin code is permitted to reference it.
- Module readability and reflective access rules differ from the classpath; being able to load a class does not guarantee every constructor/member is accessible.
- If you want to manage plugins as **named modules** at runtime, design around **ModuleFinder/Configuration/ModuleLayer** and their corresponding loaders; that is a different workflow from simply loading JARs with `URLClassLoader`.
- Plugins providing services with **provides ... with ...**, and a host declaring **uses**, can combine with **ServiceLoader** across module layers.

Therefore, before choosing `URLClassLoader` for a real system, decide whether you are using **classpath plugins** or **module-layer plugins**. Do not mix the two models haphazardly and then patch failures with unchecked casts or forced reflective access.

## 13. How to Debug a Plugin That Fails to Load or Cast

When encountering an error, check in this order:

**(1) Are the JAR and entry class right?**

~~~bash
jar --list --file build/vietnamese-greeter.jar
~~~

Ensure the class exists at the exact path **example/impl/VietnameseGreeter.class**, without an extra nested **build/plugin/** directory inside the JAR.

**(2) Does the URL point to the right artifact?** Print **jar.toAbsolutePath()**, **jar.toUri()**, and the real path. Use `Files.isRegularFile()` to catch missing files. If using a `.class` directory, the URL must point to the **package root**.

**(3) Is the parent the contract's loader?**

~~~java
// Illustrative fragment for debugging in the host:
System.out.println("API loader: " + Greeter.class.getClassLoader());
System.out.println("Implementation loader: " + rawClass.getClassLoader());
System.out.println("Assignable: "
        + Greeter.class.isAssignableFrom(rawClass));
~~~

If assignable is `false`, do not stop at printing class names; check which classloader defined each interface. **rawClass.getInterfaces()** can inspect direct interfaces, yet does not list indirectly inherited ones; **isAssignableFrom** is the direct, accurate check for casting purposes.

**(4) Is the constructor suitable?** If the class is non-public or lacks a public no-arg constructor, **getConstructor()** or **newInstance()** will fail. Define the entry point explicitly; when injection is needed, use a factory API instead of opening reflective access indiscriminately.

**(5) Are dependencies found?** A plugin may load its entry-point class cleanly yet fail with **NoClassDefFoundError** when executing a branch that touches a missing dependency for the first time. Inspect related JARs, API versions, and delegation order. Never assume a plugin works solely because `loadClass` succeeded.

**(6) Was the class accidentally pre-loaded by the host?** If **rawClass.getClassLoader()** equals the parent, the implementation is already on the parent classpath. That alters isolation boundaries and makes swapping the JAR via a new loader ineffective for that class.

**(7) Is the lifecycle still valid?** If the plugin triggers loading additional classes after `URLClassLoader.close()`, new class loads can fail. If the loader is not garbage-collected after disabling the plugin, look for references from instances, static fields, threads, and the Thread Context ClassLoader.

## 14. Common Design Mistakes

### Mistake 1: Host Directly Imports the Plugin Class

~~~java
// Illustrative anti-pattern fragment:
Greeter g = new example.impl.VietnameseGreeter();
~~~

Such a host must have the plugin on its compile/runtime classpath; adding new plugins forces host changes. Use a shared API interface, artifact paths, and class names/configuration/discovery to instantiate implementations at runtime.

### Mistake 2: Using an Isolated Loader That Breaks the Contract

~~~java
// Illustrative anti-pattern fragment: parent cannot see the application's API.
URLClassLoader isolated = new URLClassLoader(
        urls,
        ClassLoader.getPlatformClassLoader()
);
~~~

If the plugin JAR contains its own copy of `Greeter`, this can produce a separate class identity. Using **Greeter.class**'s parent in the example is the right way to preserve the shared contract type; still design carefully for complex hosts with multiple API loaders.

### Mistake 3: Casting First and Checking Afterward

~~~java
// Illustrative anti-pattern fragment:
Object obj = rawClass.getConstructor().newInstance();
Greeter greeter = (Greeter) obj;
~~~

The cast here is not automatically wrong, yet if the class is incompatible the error surfaces only **after creating the object**, potentially having already triggered side effects. Use **asSubclass** before instantiation to validate right at the boundary.

### Mistake 4: Using Reflection for Every Business Call

~~~java
// Illustrative anti-pattern fragment:
Object obj = rawClass.getConstructor().newInstance();
Object value = rawClass.getMethod("greet", String.class).invoke(obj, "Java");
~~~

Once the service has a shared interface, use reflection only at instantiation and invoke **Greeter.greet** directly afterward. That gives compile-time signature checking, reduces stringly-typed logic, and simplifies testing.

### Mistake 5: Forgetting API Versions and Dependencies

Merely loading a plugin class does not prove API version compatibility. A plugin compiled against a new method on `Greeter` yet run against an older API in the parent can hit linkage/`NoSuchMethodError` failures. Manage binary compatibility, publish stable APIs, and test plugins against supported host versions.

### Mistake 6: Treating close() as Immediate Unloading

Closing a loader releases file handles and blocks new loads, yet classes and instances can persist. Threads/callbacks/static caches retained by the plugin prevent reclaiming the loader. Explicit lifecycle cleanup is required.

## 15. When Does This Approach Fit, and When Should SPI/DI Replace It?

**URLClassLoader + class name + shared contract** fits when the host knows specific artifacts, wants a dedicated loader per plugin JAR, avoids compile-time implementation dependencies, and needs explicit API boundaries. It is especially straightforward in launchers, tools, test harnesses *for trusted code*, or systems where operators specify exact plugin classes.

When there are multiple providers and plugin authors need self-registration, build a **registry** or use **ServiceLoader** with `META-INF/services`. With Spring/DI containers, the container can manage factories, dependencies, and lifecycles. None of these mechanisms alter the core rule: **host and implementation must share a compatible contract type at runtime**.

If you need to isolate private library versions across multiple plugins, a policy of **parent-first for API** and **conflict handling for dependencies** becomes a dedicated design concern. If you need to load/unload named modules, use an appropriate `ModuleLayer` approach. If code is genuinely untrusted, isolate at the process level instead of trusting classloaders.

## 16. Self-Check Exercises

**Question 1.** The host has only `Greeter.class` on its classpath plus a JAR path. Why can it still invoke **greeter.greet("Java")**?

**Answer:** The host knows the `Greeter` interface type at compile time. At runtime, `URLClassLoader` loads a class implementing that exact interface, the host verifies it with `asSubclass`, and instantiates it. Calls through the interface are dispatched by the JVM to the corresponding implementation.

**Question 2.** If `Greeter.class.isAssignableFrom(rawClass)` returns `false` even though `rawClass` lists `Greeter` in its `implements` clause, what should you check?

**Answer:** Two `Class` objects named `Greeter` with the same binary name may exist, loaded by two different defining loaders. Inspect the plugin loader's parent and the loader of the host's API, as well as API versions and delegation order.

**Question 3.** Has calling `pluginLoader.loadClass(name)` alone run the constructor?

**Answer:** No. That call returns **Class<?>**; instantiation at **getConstructor().newInstance()** invokes the constructor. However, loading/linking the class can still incur cost or errors.

**Question 4.** Why is the plugin JAR omitted from **java -cp** in the example?

**Answer:** That is required to demonstrate dynamic loading. If the parent classpath already sees the implementation, the child `URLClassLoader` may return the parent's copy and fail to demonstrate loading specifically from the URL.

**Question 5.** Can you replace the JAR on disk and call the same `pluginLoader.loadClass(name)` to get the new implementation class?

**Answer:** That cannot be treated as a valid reload mechanism. Already-defined classes in a loader are cached under that identity; swapping code requires creating a new loader, stopping the old plugin, and managing cleanup/references.

## 17. Pre-Deployment Checklist

1. **Shared API:** place interfaces in a separate API artifact, with host and plugin using compatible versions; plugins should not bundle duplicate APIs.
2. **Loader hierarchy:** parent provides the exact API `Class` object; implementations are located by child `URLClassLoader`s from the right JARs/directories.
3. **Class/JAR names:** verify actual paths, binary names, and JAR contents; keep implementations off the parent classpath when isolated loading is intended.
4. **Type checking:** use **isAssignableFrom** for diagnostics and **asSubclass** to narrow `Class<?>` to `Class<? extends Contract>`.
5. **Explicit instantiation:** use an agreed **public constructor** or factory API; avoid deprecated `Class.newInstance` and arbitrary reflective access.
6. **Error handling:** distinguish file/URL, class loading, dependency linking, casting, constructor, and business exceptions; log causes and relevant versions.
7. **Lifecycle:** stop plugin work, close resources, unregister listeners/threads/static references, and close `URLClassLoader` at the right time.
8. **Limits:** `URLClassLoader` does not discover plugin metadata automatically, does not safely unload/reload by itself, and does not provide a security sandbox.

**Desired lesson outcome:** a host depending only on a **shared contract** can locate new classes from a JAR using **URLClassLoader**, use **asSubclass** to guarantee type compatibility before instantiation, and continue invoking business logic through the interface without coupling host code to plugin implementations.

### Java SE 17 Documentation

- URLClassLoader: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- ClassLoader and parent delegation: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Class.asSubclass, Class.cast, and getConstructor: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Constructor.newInstance: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html
