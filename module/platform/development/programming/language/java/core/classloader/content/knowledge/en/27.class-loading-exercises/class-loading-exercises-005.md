# Hands-On: Creating Plugins Using a Shared API and Discovering Them with ServiceLoader

> **Java Core → ClassLoader → Hands-On.** Build a Java 17 application consisting of a **host**, a **shared SPI interface**, and **two separate plugin JARs**; use `URLClassLoader` and `java.util.ServiceLoader` so the host discovers provider implementations without importing the implementation classes. The lab includes complete source code, directory structure, `META-INF/services` files, `javac`/`jar`/`java` commands, stdout, ClassLoader identity verification, a TCCL example, and troubleshooting. No Maven, Gradle, or libraries outside the JDK are required.

## 1. Learning Outcomes

After this lesson, you will know how to:

1. Write a **shared API contract** so the host and plugins can communicate through the same runtime interface.
2. Create two plugins that implement the contract in **two independent JARs**.
3. Declare each provider according to the Java SPI protocol using `META-INF/services/<service-binary-name>`.
4. Create a `URLClassLoader` pointing to a JAR and use `ServiceLoader.load(Service.class, chosenLoader)` to find providers.
5. Prove that the plugin implementation is defined by the plugin loader, while the service interface is shared from the parent loader.
6. Explain the difference between an explicit ClassLoader and the thread context class loader (TCCL).
7. Understand lazy discovery, `ServiceConfigurationError`, `reload()`, and the lifecycle of plugins/loaders.
8. Extend the system without modifying the host API each time a plugin is added.

**The main lab was compiled with `javac --release 17` and run successfully on OpenJDK 21.** You only need JDK 17 or later with the `java`, `javac`, and `jar` commands.

## 2. Architecture: The Host Knows Only the API, Not the Implementation

~~~text
                       Application/Host Loader
                       defines demo.spi.Processor
                                  |
                    +-------------+---------------+
                    |                             |
                    v                             v
            URLClassLoader upper            URLClassLoader reverse
            build/upper.jar                 build/reverse.jar
                    |                             |
            demo.upper.UpperProcessor      demo.reverse.ReverseProcessor
            META-INF/services/...          META-INF/services/...
                    |                             |
                    +-------------+---------------+
                                  |
                       ServiceLoader<Processor>
~~~

**Important invariant:** The JVM identifies a runtime type by **binary name + defining ClassLoader**. A plugin can be loaded by its own loader, but it must implement **the exact runtime `Processor.class` that the host knows**. If each plugin defines its own copy of `demo.spi.Processor` with a child-first loader, the host may receive `ServiceConfigurationError: not a subtype` or `ClassCastException` even though the class/interface names match.

The simplest approach:

- Compile the API into a separate directory `build/api`.
- The host has the API on the application classpath.
- Compile the providers with the API on the **compile classpath**.
- Package the provider JARs **without** `demo/spi/Processor.class`.
- Set the parent of each `URLClassLoader` to `Processor.class.getClassLoader()`.
- When running the host, do **not** put the implementation JARs on the application classpath; they are added only via `URLClassLoader`.

Parent-first delegation ensures that the child can use the `Processor` already defined by the parent, while plugin-private implementations remain defined by the child. Do not use identical interface names as a compatibility check; compare `Class<?>` identity or `isAssignableFrom`.

## 3. Complete Directory Tree

Create the source/config files as follows; the `build` directory is created by the build commands:

~~~text
service-plugin-lab/
├── src/
│   ├── api/demo/spi/Processor.java
│   ├── upper/demo/upper/UpperProcessor.java
│   ├── reverse/demo/reverse/ReverseProcessor.java
│   └── host/demo/host/PluginHost.java
├── config/
│   ├── upper/META-INF/services/demo.spi.Processor
│   └── reverse/META-INF/services/demo.spi.Processor
└── build/
    ├── api/
    ├── upper/
    ├── reverse/
    ├── host/
    ├── upper.jar
    └── reverse.jar
~~~

All commands below run from **`service-plugin-lab` as the working directory**. If you run the host from a different folder, `Path.of("build/upper.jar")` may point to the wrong file because it is a relative path.

### 3.1. Shared API Source

**File `src/api/demo/spi/Processor.java`:**

~~~java
package demo.spi;

public interface Processor {
    String id();
    String process(String text);
}
~~~

The interface intentionally uses only JDK `String` in its signatures. `id()` helps the host distinguish between providers. `process()` demonstrates a plugin capability. In real applications, the API may have shared DTOs, error types, or lifecycle methods; all types crossing the boundary must have clear ownership/ABI.

You **should not** have a method signature return `demo.upper.InternalData` or a private library class that the host cannot access. Separating the shared API from private classes reduces version conflicts and protects type identity.

## 4. Plugin A — UpperProcessor

**File `src/upper/demo/upper/UpperProcessor.java`:**

~~~java
package demo.upper;

import demo.spi.Processor;
import java.util.Locale;

public final class UpperProcessor implements Processor {
    public UpperProcessor() {}

    @Override
    public String id() {
        return "upper";
    }

    @Override
    public String process(String text) {
        return text.toUpperCase(Locale.ROOT);
    }
}
~~~

The provider is a **public concrete class** with a **public no-argument constructor**. This is the appropriate contract for a provider deployed in an **unnamed module/classpath**. `Locale.ROOT` avoids output depending on the default locale; inputting `java 17` produces `JAVA 17`.

## 5. Plugin B — ReverseProcessor

**File `src/reverse/demo/reverse/ReverseProcessor.java`:**

~~~java
package demo.reverse;

import demo.spi.Processor;

public final class ReverseProcessor implements Processor {
    public ReverseProcessor() {}

    @Override
    public String id() {
        return "reverse";
    }

    @Override
    public String process(String text) {
        return new StringBuilder(text).reverse().toString();
    }
}
~~~

Inputting `java 17` produces `71 avaj`. `StringBuilder.reverse()` is sufficient for this ASCII example; it should not be treated as an algorithm for reversing complex Unicode grapheme clusters across all languages.

The two plugins do not import each other. The host does not import `UpperProcessor` or `ReverseProcessor` either. This is the core point for adding new implementations without modifying the host source.

## 6. Declaring the SPI via `META-INF/services`

For a classpath provider, the file must be named with the **full binary name of the service type**:

~~~text
META-INF/services/demo.spi.Processor
~~~

**File `config/upper/META-INF/services/demo.spi.Processor` has one line:**

~~~text
demo.upper.UpperProcessor
~~~

**File `config/reverse/META-INF/services/demo.spi.Processor` has one line:**

~~~text
demo.reverse.ReverseProcessor
~~~

Rules:

- Use plain UTF-8 text; do not write `.class`, `.java`, slashes, or `new` expressions.
- Each line contains one fully qualified **provider binary name**; there can be multiple providers on separate lines.
- The exact path is `META-INF/services` (plural services), which is case-sensitive across many environments.
- The descriptor must be **copied into the output JAR itself**; simply placing the file in the source tree is not enough.
- The provider must be visible to the loader, implement the exact shared `Processor`, have a valid constructor, and not fail during instantiation.

ServiceLoader **does not automatically scan every `.class`** in a plugin JAR to find classes implementing an interface. Without a descriptor (and without a named module provider declaration), discovery results can be **empty** even though the implementation class is still in the JAR.

**Note:** When using named JPMS modules, you can declare `provides ... with ...` in `module-info.java` instead of the classpath descriptor mechanism. This lab intentionally uses **unnamed modules and SPI descriptors** to clearly observe the ClassLoader.

## 7. Host Java Code — Knowing Only the `Processor` Interface

**File `src/host/demo/host/PluginHost.java`:**

~~~java
package demo.host;

import demo.spi.Processor;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ServiceLoader;

public final class PluginHost {
    static void run(String label, ClassLoader loader) {
        ServiceLoader<Processor> discovered =
                ServiceLoader.load(Processor.class, loader);

        int count = 0;
        for (Processor provider : discovered) {
            count++;
            System.out.println(label + ":" + provider.id()
                    + "=" + provider.process("java 17"));
            System.out.println(label + ":owned="
                    + (provider.getClass().getClassLoader() == loader));
        }
        System.out.println(label + ":count=" + count);
    }

    public static void main(String[] args) throws Exception {
        ClassLoader shared = Processor.class.getClassLoader();

        URL upper = Path.of("build/upper.jar")
                .toAbsolutePath().toUri().toURL();
        URL reverse = Path.of("build/reverse.jar")
                .toAbsolutePath().toUri().toURL();

        try (URLClassLoader upperLoader =
                     new URLClassLoader(new URL[] {upper}, shared);
             URLClassLoader reverseLoader =
                     new URLClassLoader(new URL[] {reverse}, shared)) {

            run("host", shared);
            run("upper", upperLoader);
            run("reverse", reverseLoader);

            System.out.println("same api="
                    + (upperLoader.loadClass(Processor.class.getName())
                        == Processor.class
                    && reverseLoader.loadClass(Processor.class.getName())
                        == Processor.class));

            Thread t = Thread.currentThread();
            ClassLoader before = t.getContextClassLoader();
            ServiceLoader<Processor> tcclServices;

            try {
                t.setContextClassLoader(upperLoader);
                tcclServices = ServiceLoader.load(Processor.class);
            } finally {
                t.setContextClassLoader(before);
            }

            System.out.println("tccl first="
                    + tcclServices.findFirst().orElseThrow().id());
        }
    }
}
~~~

Analysis:

- `ClassLoader shared = Processor.class.getClassLoader()` selects the loader that actually defines the shared API. Do not guess based on a loader named “system” when running inside a container or custom runtime.
- `new URLClassLoader(new URL[]{upper}, shared)` creates a loader pointing to the provider JAR, with the shared API loader as its parent.
- `ServiceLoader.load(Processor.class, loader)` uses the passed-in loader to find provider-configuration resources and provider classes (in this classpath lab).
- `for (Processor provider : discovered)` is the step that **lazily finds and creates instances**. `ServiceLoader.load` itself does not necessarily instantiate providers.
- `provider.getClass().getClassLoader() == loader` confirms the **defining loader** of the implementation in the lab configuration.
- `loadClass(Processor.class.getName()) == Processor.class` confirms the **shared runtime contract identity**.
- `try-with-resources` closes both `URLClassLoader` instances when the entire example finishes using them; `close()` is not called on the provider objects (the demo API does not declare this lifecycle).

**Do not blindly apply `owned==true` to every ServiceLoader outside this lab**: with parent-first delegation or named module providers, the implementation may be defined by a different loader. That does not mean ServiceLoader is wrong; you need to understand the actual defining loader.

### 7.1. Distinguishing an Explicit Loader from TCCL

The overload:

~~~java
ServiceLoader.load(Processor.class, upperLoader)
~~~

takes the **upperLoader** provided by the host, without depending on the thread's incidental TCCL.

The overload:

~~~java
ServiceLoader.load(Processor.class)
~~~

is equivalent to:

~~~java
ServiceLoader.load(
    Processor.class,
    Thread.currentThread().getContextClassLoader())
~~~

In `main`, the TCCL is temporarily set to the upper loader right when creating `tcclServices`, then restored **before** `findFirst()`. ServiceLoader still uses the loader selected initially, yielding `upper`.

When using a worker pool, **do not assume** that the submitter thread's TCCL is propagated to an existing worker. If a framework only uses the convenience overload, set/restore the TCCL on **the exact thread executing discovery**, inside a `try/finally`. Whenever possible, a plugin host should prefer the two-argument overload because the owner is clearer.

## 8. Building the Two Plugin JARs and Running the Host

Use a POSIX shell (Linux/macOS/Git Bash). From the `service-plugin-lab` root:

~~~bash
# 1. Output folders + correct paths for SPI descriptors.
mkdir -p build/api build/upper/META-INF/services \
         build/reverse/META-INF/services build/host

# 2. Shared API is compiled separately.
javac --release 17 -d build/api \
    src/api/demo/spi/Processor.java

# 3. Providers use the shared API on the compile classpath.
javac --release 17 -cp build/api -d build/upper \
    src/upper/demo/upper/UpperProcessor.java

javac --release 17 -cp build/api -d build/reverse \
    src/reverse/demo/reverse/ReverseProcessor.java

# 4. Copy the SPI descriptor into each provider's output root.
cp config/upper/META-INF/services/demo.spi.Processor \
   build/upper/META-INF/services/demo.spi.Processor

cp config/reverse/META-INF/services/demo.spi.Processor \
   build/reverse/META-INF/services/demo.spi.Processor

# 5. Package exactly two JARs, without the shared Processor.class.
jar --create --file build/upper.jar -C build/upper .
jar --create --file build/reverse.jar -C build/reverse .

# 6. Host compiles with only the API.
javac --release 17 -cp build/api -d build/host \
    src/host/demo/host/PluginHost.java

# 7. Host runtime does NOT have upper.jar/reverse.jar on the classpath.
java -cp "build/api:build/host" demo.host.PluginHost
~~~

On Windows, `javac`/`jar` are similar, but create/copy directories using PowerShell/CMD and **the classpath separator is `;`**:

~~~powershell
java -cp "build/api;build/host" demo.host.PluginHost
~~~

Do not run `java -jar build/upper.jar`: it is a provider JAR without a `Main-Class`. The class with `main` is in the host.

### 8.1. Checking the Correct Artifacts in the JARs

~~~bash
jar --list --file build/upper.jar
jar --list --file build/reverse.jar
~~~

`upper.jar` must contain at least:

~~~text
demo/upper/UpperProcessor.class
META-INF/services/demo.spi.Processor
~~~

`reverse.jar` must contain at least:

~~~text
demo/reverse/ReverseProcessor.class
META-INF/services/demo.spi.Processor
~~~

`jar --list` may also print `META-INF/`, `MANIFEST.MF`, and directory entries; do not assert that the list has only two lines or a specific print order. There is **no** `demo/spi/Processor.class` in the plugin JARs.

## 9. Lab Stdout Verified on OpenJDK 21

~~~text
host:count=0
upper:upper=JAVA 17
upper:owned=true
upper:count=1
reverse:reverse=71 avaj
reverse:owned=true
reverse:count=1
same api=true
tccl first=upper
~~~

Explanation of each group:

- `host:count=0`: the application/host loader knows the interface, and there are **no** plugin descriptor JARs on the host classpath.
- `upper:upper=JAVA 17`: `upperLoader` reads the descriptor from `upper.jar` and instantiates `UpperProcessor`.
- `upper:owned=true`: the implementation class is defined by `upperLoader`.
- `upper:count=1`: only one provider is visible through this scope.
- `reverse:reverse=71 avaj`: `reverseLoader` sees the separate provider from `reverse.jar`.
- `reverse:owned=true` and `reverse:count=1`: one implementation defined by the reverse loader itself.
- `same api=true`: both loaders delegate `demo.spi.Processor` to the shared parent, avoiding duplicate type identity.
- `tccl first=upper`: `ServiceLoader.load(Processor.class)` used the TCCL upper loader at the time of the factory call.

This output is reliable under **this exact lab configuration**; if you place plugin JARs on the host classpath, the host has additional providers, or you use a different parent or a custom child-first loader, you should not expect every line to be identical.

## 10. ServiceLoader Discovery Under the Hood

For classpath providers:

1. The caller specifies `Processor.class` (a specific runtime class/interface) and a ClassLoader.
2. When iteration begins, ServiceLoader searches for `META-INF/services/demo.spi.Processor` through the loader's `getResources` mechanism.
3. It reads the lines of binary names; comments starting with `#` and blank lines are allowed per the specification.
4. It loads the provider class according to loader/module visibility rules and checks that it properly provides the service.
5. For classpath deployment, it invokes the **public no-argument constructor** and returns a `Processor` instance.
6. Instantiated providers are kept in the **ServiceLoader instance's provider cache**; subsequent iterations may see cached objects first.

**Do not** use `Class.forName("demo.upper.UpperProcessor")` from the default system loader as a replacement for ServiceLoader. The host would hard-code the class name and might look in the wrong loader. SPI allows providers to be added or removed via metadata rather than modifying the host.

### 10.1. Multiple Providers in One Descriptor

A single `META-INF/services/demo.spi.Processor` can contain:

~~~text
demo.upper.UpperProcessor
demo.reverse.ReverseProcessor
~~~

The condition is that the loader can locate **both classes**. If you create a single `URLClassLoader` with the URLs of both `upper.jar` and `reverse.jar`, ServiceLoader can find both provider descriptors. This is a way to deploy a group of plugins within the **same loader namespace**, differing from the lab's two-separate-loaders model.

**Exercise snippet** inside `main` using `upper`, `reverse`, and `shared`:

~~~java
try (URLClassLoader combined = new URLClassLoader(
        new URL[] {upper, reverse}, shared)) {

    ServiceLoader<Processor> services =
            ServiceLoader.load(Processor.class, combined);

    java.util.List<String> names = new java.util.ArrayList<>();
    for (Processor provider : services) {
        names.add(provider.id());
    }
    names.sort(String::compareTo);
    System.out.println(names);
}
~~~

If both JARs are correct, the expected final line is:

~~~text
[reverse, upper]
~~~

Sorting before printing ensures the output does not depend on provider discovery order. This code is an **extension snippet** and is not part of the `PluginHost.java` stdout in Section 9.

### 10.2. Lazy Loading, `findFirst`, `stream`, and `reload`

~~~java
ServiceLoader<Processor> services =
        ServiceLoader.load(Processor.class, upperLoader);

// Java 9+: first provider instance if present.
Processor first = services.findFirst().orElseThrow();

// Stream descriptors before instantiating objects:
services.stream().forEach(p -> {
    System.out.println(p.type().getName());
    // p.get() creates/retrieves the provider instance per the contract.
});

// Clear the provider cache of this ServiceLoader instance:
services.reload();
~~~

This is a **snippet** within a scope that has `upperLoader`. `stream()` returns `ServiceLoader.Provider<S>`; `type()` and `get()` let you inspect the type and instantiate intentionally. `reload()` only refreshes the discovery/provider cache **on the current ServiceLoader instance**; it does **not** change the chosen loader, close objects, or redefine JAR classfiles within the same defining loader.

ServiceLoader is **not thread-safe**; do not share a single instance across multiple threads performing concurrent iteration and reloading without synchronization/lifecycle control.

## 11. Variations and Intentional Errors for Self-Verification

### 11.1. Removing the SPI Descriptor from the JAR

If `upper.jar` does not have `META-INF/services/demo.spi.Processor`, calling `run("upper", upperLoader)` finds no provider in this plugin scope and may print `upper:count=0`. **However**, the final `tcclServices.findFirst().orElseThrow()` in the host main will throw `NoSuchElementException` if there is no provider; do not say the entire application runs through to completion as before.

### 11.2. Misspelling the Class Name in the Descriptor

If you write `demo.upper.MissingProcessor`, Java will not find the provider class and may throw `ServiceConfigurationError` **when iterator/findFirst looks up the provider**, not necessarily when `ServiceLoader.load` is called. Fix the binary name to match the JAR entry path; check the package in the source and `jar --list`.

### 11.3. Provider Is Not a Subtype of the Shared API

If a plugin implements a **copy of `Processor` redefined by a child-first loader**, the host is using `Processor.class` from the parent; the two types are incompatible even though `Class.getName()` is identical. ServiceLoader may throw `ServiceConfigurationError: ... not a subtype`. If the plugin JAR contains a copy of the API while the loader **is still parent-first**, that copy alone may not cause an error because the parent class can win. You must observe the actual defining loaders.

### 11.4. Non-Public Constructor or Constructor Throwing an Error

A classpath provider requires a public concrete class and a public no-arg constructor. Violating the contract or throwing from the constructor results in a `ServiceConfigurationError`/related cause upon instantiation. Do not catch all `Throwable` and pretend the provider is absent.

### 11.5. Putting a Plugin JAR on the Host Classpath

If the `java -cp` command includes `build/upper.jar`, the application loader can see the provider descriptor and UpperProcessor; `host:count=0` no longer holds. Because of parent-first delegation, `upperLoader` can also delegate the implementation back to the host, causing `upper:owned=false`. This is a very common ClassLoader configuration mistake.

### 11.6. Resource Found but Instance Creation Fails

You can check the exact loader:

~~~java
String path = "META-INF/services/" + Processor.class.getName();
var urls = upperLoader.getResources(path);
while (urls.hasMoreElements()) {
    System.out.println(urls.nextElement());
}
~~~

The snippet needs to be placed inside `main`; the method may throw `IOException`. Having the resource **does not prove** that the implementation class exists, the subtype is right, the constructor is public, or all dependencies are satisfied. If an error occurs, inspect the full `ServiceConfigurationError` stack/cause.

## 12. Comparing an Explicit Loader vs. TCCL

| API | Loader Used as Starting Point | When Appropriate |
| --- | --- | --- |
| `ServiceLoader.load(S.class, pluginLoader)` | Explicit plugin loader | Host knows the owner, avoids thread dependency |
| `ServiceLoader.load(S.class)` | TCCL at the time of the factory call | Framework using ambient application context |
| `ServiceLoader.load(S.class, null)` | System classloader (or bootstrap if there is no system) | Does not mean “do not load” |
| `ServiceLoader.loadInstalled(S.class)` | Platform classloader (Java 9+) | Not the general way to find app plugin JARs |
| `ServiceLoader.load(layer, S.class)` | Named modules in the layer and parent layers | JPMS plugin ModuleLayer |

`ServiceLoader.load(S.class)` captures the TCCL **when creating** the ServiceLoader, even though provider instantiation may happen lazily **later**. If a worker pool reuses a thread that still carries an old plugin's TCCL, a new request may see the wrong providers and keep the old loader alive. Use an explicit loader or **set/restore the TCCL inside `try/finally`** when a framework API does not allow passing a loader.

Do not treat the TCCL as the defining loader of the service type. `Processor.class.getClassLoader()` remains the loader that defined the API according to JVM type identity.

## 13. JPMS (Java 9+) Is Another Variant, Not Required for This Lab

When using named modules, a provider can be declared in `module-info.java`:

**API module:**

~~~java
module demo.api {
    exports demo.spi;
}
~~~

**Provider module:**

~~~java
module demo.upper {
    requires demo.api;
    provides demo.spi.Processor
        with demo.upper.UpperProcessor;
}
~~~

**Consumer module:**

~~~java
module demo.host {
    requires demo.api;
    uses demo.spi.Processor;
}
~~~

These are **three descriptors belonging to three different named modules**, not combined into a single file. `uses` declares that the consumer uses the service; `provides ... with` declares the provider; `requires` grants readability of the API module; `exports` makes the API package accessible.

With named modules:

- Classpath `META-INF/services` is not required for a provider declared with `provides`.
- The provider implementation package does not need to be exported publicly just for ServiceLoader to instantiate the provider under the module contract.
- Provider modules must be present in the **resolved module graph/layer**, not merely sitting arbitrarily in a folder.
- `ServiceLoader.load(layer, S.class)` finds providers in named modules within that layer and parent layers; it does **not** automatically find providers in unnamed modules via SPI files.
- Named-module providers have their own constructor/provider-method rules; do not use a static `provider()` method as a workaround for a missing public constructor in the **classpath demo**.

If switching to ModuleLayer, you must rewrite the build/launch module-path and module-resolution logic accordingly; do **not** simply add `module-info.java` to the demo JARs and keep all classpath expectations.

## 14. Lifecycle, Hot Reload, and Safety

In this lab, `try-with-resources` closes the `URLClassLoader` and the file/JAR handles it owns. However, `URLClassLoader.close()`:

- Does not destroy already loaded classes and does not reset static fields.
- Does not automatically close HTTP/DB connections, streams, or threads created by the provider itself.
- Does not automatically unregister listeners, `ServiceLoader` provider caches, or DI/reflection maps in the host.
- Does not guarantee immediate class unloading or an immediate reduction in Metaspace.
- Does not have a safe protocol for being called concurrently with another thread loading a class; the Javadoc states that the result of loading during a concurrent `close()` is undefined.

To update `upper.jar` from V1 to V2:

1. Verify the artifact/version and create a **new-generation loader**.
2. Discover/instantiate/health-check the V2 provider before publishing.
3. Cut over routing with proper synchronization/leases so new requests use V2.
4. Drain in-flight V1 work and stop callbacks.
5. Close provider-owned resources, clear caches, restore the TCCL, and remove ThreadLocal values.
6. Close the old `URLClassLoader` and drop strong references; the JVM can unload old classes once conditions are met.

`ServiceLoader.reload()` is not bytecode hot-reloading. If plugin code is **untrusted**, a classloader does not create a security sandbox; you need a process/container/OS boundary, source/signature verification, and real permission management.

## 15. Acceptance Checklist

- [ ] A single copy of `Processor.java` exists in `build/api`.
- [ ] The host does not import concrete provider classes.
- [ ] Each provider has a public no-arg constructor and implements `demo.spi.Processor`.
- [ ] Both JARs contain the implementation and `META-INF/services/demo.spi.Processor` at the correct path.
- [ ] No duplicate copy of `demo/spi/Processor.class` is contained in the plugin JARs.
- [ ] `javac --release 17` compiles all four files.
- [ ] The host runtime classpath contains only `build/api` and `build/host`.
- [ ] `host:count=0` and each plugin has `count=1`.
- [ ] Output matches `JAVA 17` and `71 avaj`.
- [ ] `upper:owned=true`, `reverse:owned=true`, and `same api=true`.
- [ ] The TCCL is restored in `finally`, and the `tccl first=upper` line is correct.
- [ ] ServiceLoader is not cached VM-wide across multiple tenants/generations.
- [ ] When a plugin retires, requests are drained, caches are cleared, and resources are closed by the proper owner.
- [ ] Upon `ServiceConfigurationError`, the original cause and SPI descriptor/JAR contents have been inspected.

## 16. Self-Check Questions

1. Which loader loads the shared API? **Host/parent**, identified by `Processor.class.getClassLoader()`.
2. Does the host need to compile against `UpperProcessor`? **No**, it only needs `Processor`.
3. Which file is used to declare a provider on the classpath? **`META-INF/services/demo.spi.Processor`**.
4. Does the descriptor contain a Java source path or a provider binary name? **The binary name `demo.upper.UpperProcessor`**.
5. Is a plugin JAR that contains only the implementation class without a descriptor automatically discovered? **No**, except through the separate named-module provider mechanism.
6. Why does the plugin's loader take the shared loader as its parent? **To use the same runtime `Processor.class`**.
7. How do `ServiceLoader.load(S.class, loader)` and the one-argument overload differ? **Explicit loader versus current thread context loader**.
8. When the host changes the TCCL after `ServiceLoader.load(S.class)`, does the existing ServiceLoader automatically switch its provider scope? **No**.
9. Can a provider class be defined by the parent when the explicit loader is a child? **Yes**, depending on delegation/JPMS.
10. Does `ServiceLoader` find providers immediately upon object creation? **Discovery/instantiation is mostly lazy during iteration/streaming**.
11. If the descriptor has the wrong class name, what error commonly occurs? **ServiceConfigurationError**.
12. If the API is duplicated in a child-first loader, what happens? **Runtime type identity mismatch, provider not subtype/cast failure**.
13. Does `URLClassLoader.close()` unload classes immediately? **No**.
14. Does `reload()` load a V2 implementation class within the same defining loader? **No**.
15. Does `ServiceLoader.load(layer, S.class)` search classpath `META-INF/services` in unnamed modules? **No**, it uses named-module declarations.
16. Can two JARs be used in a single loader? **Yes**, when their binary namespace/dependencies are compatible.
17. When should you create a separate loader for each plugin? **When you need dependency isolation or independent lifecycle/version ownership**.
18. Should a ClassLoader be used as a sandbox for untrusted plugins? **No**, OS/process isolation is required when a trust boundary exists.

## 17. Official References

1. [ServiceLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html): provider contract, classpath `META-INF/services`, named modules, explicit loader/TCCL, lazy instantiation, `reload`, errors.
2. [URLClassLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/URLClassLoader.html): looking up classes/resources from URLs, parent delegation, `close`.
3. [ClassLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): defining/initiating loaders and resource lookup.
4. [ServiceConfigurationError — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceConfigurationError.html): error when SPI provider loading/creation is invalid.
5. [Thread — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html): thread context ClassLoader.
6. [JVMS §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3): runtime class identity.
7. [ModuleLayer — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ModuleLayer.html): provider modules by layer.
8. [JEP 261 — Module System](https://openjdk.org/jeps/261): `uses` and `provides ... with ...` in module descriptors.

**Conclusion:** A classpath plugin under Java SPI consists of an **implementation class + the exact `META-INF/services` file**. The host holds the shared `Processor` interface, creates a ClassLoader pointing to the provider JAR, and calls `ServiceLoader.load(Processor.class, pluginLoader)`. Do not trade shared API type identity for arbitrary child-first loading; in production deployments, manage provider discovery, TCCL, errors, caches, and loader lifecycles per plugin generation.
