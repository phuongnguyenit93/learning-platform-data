# Namespaces, Visibility, and Dependency Isolation in Java ClassLoader

## 1. Why the Same Class Name Does Not Guarantee the Same Type

In Java, a `ClassLoader` both loads class definitions into the JVM and establishes **type identity** boundaries. This is especially important when running applications with plugins, containers, module systems, or multiple library versions.

At runtime, a class is fundamentally identified by the **pair (binary name of the class, defining class loader)**. For example, `(com.example.dto.Order, LoaderA)` and `(com.example.dto.Order, LoaderB)` are **two distinct types**, even if their bytecode or source code is identical. Therefore, an object of the first type cannot be automatically cast to the second type.

Three terms should be distinguished:

- **Binary name**: the name the JVM uses for references, such as `com.example.dto.Order`.
- **Defining loader**: the loader that actually defines the class from bytecode, typically via `defineClass`. This is the component that determines type identity.
- **Initiating loader**: the loader that requested the class load and may receive the result from a parent loader. A class can have multiple initiating loaders, but only one defining loader for a given definition.

Consequently, calling `child.loadClass("java.lang.String")` does not mean `child` defines `String`; under the standard delegation mechanism, this class is returned by the bootstrap loader.

### Practical Consequences

| Scenario | Meaning |
| --- | --- |
| Two different loaders each define `pkg.Foo` | There are two separate `pkg.Foo` types |
| Two child loaders both receive `pkg.Api` from a parent loader | They share **one** `pkg.Api` type |
| Same package name, but classes are defined by two loaders | Not automatically in the same **runtime package** |
| Two plugins use two separately loaded library versions | Can coexist if internal types do not leak across a shared API |

**Note:** "Can find the `.class` file" and "can use the class as the same type" are two different questions.

## 2. Namespaces When the JVM Resolves Inter-Class References

Being able to **find** a class, having **access** to that class, and being able to **share type identity** are three distinct checks. A loader can request a class from its parent without defining that class itself; `clazz.getClassLoader()` indicates the **defining loader**, whereas `Thread.currentThread().getContextClassLoader()` is a contextual loader choice used by certain service discovery APIs.

During linking, the JVM also enforces **loading constraints** at type boundaries such as method signatures between classes defined by different loaders. Thus, two plugins may load their own libraries successfully yet encounter a `LinkageError` when they must agree on the identity of a shared type. This error should be investigated through loader relationships and the types in the method descriptor; renaming variables or casting will not resolve the root cause.

Loading classes separately also does not bypass verification, initialization rules, or JPMS access controls. The next section focuses on **who can see whose classes** and the conditions under which exchanging types across loader boundaries is valid.

## 3. Parent-Child Delegation Model and Visibility

In the default **parent delegation** model of `ClassLoader.loadClass`, a loader checks whether the class is already loaded, then typically delegates to its parent first; only if the parent cannot find it does the child loader call `findClass` to define it itself.

```text
Bootstrap loader              (java.base, e.g., java.lang.String)
       ↑
Platform loader               (selected JDK platform modules)
       ↑
Application/System loader     (application classpath/module path)
       ↑
PluginLoader-A           PluginLoader-B
   (plugin A)              (plugin B)
```

The arrows indicate the direction of **delegating requests up to the parent**; they do not mean the parent loader automatically has access to all classes private to its children.

- **A child generally sees its parent's classes** because requests are delegated upward.
- **A parent does not automatically see classes defined only by a child**, because the default mechanism does not search downward.
- **Sibling loaders do not automatically see each other's private classes**. They only share classes returned to both by a common parent, or through an explicitly designed bridging mechanism.
- **Not every loader is parent-first**. Containers and plugin frameworks may implement child-first or package-based rules. You must verify the actual loader behavior rather than assuming every class follows the diagram above.

### Distinguishing Three Kinds of "Visibility"

1. **Class-loading visibility**: can the loader in use locate the definition?
2. **Language/JVM accessibility**: once found, do `public`, `protected`, package-private, inheritance relationships, and module rules permit access?
3. **Type compatibility**: which loader defined the type? Are two `Class<?>` references actually the exact same `Class` object?

For example, a child loader may be able to load a `public` class from its parent yet still be blocked by JPMS because the module does not `exports` the package, or be restricted from deep reflective access by `opens`.

## 4. Runtime Packages, Access Rights, and Modules

In the JVM, two classes are considered to belong to the same **runtime package** only if their package names match **and their corresponding defining loaders are the same**. Therefore, package-private is not a "shortcut" for two plugins to access each other's internals simply because they use the same `package org.example;` declaration.

For instance, `pluginA.internal.Helper` and `pluginA.internal.Entry` have the same textual package name but are defined by two different loaders: the JVM does not treat them as the same runtime package for package-private access. Errors may manifest as `IllegalAccessError` when bytecode links to an invalid member.

The Java Platform Module System (JPMS, Java 9+) adds **readability, exports, and opens** rules:

- **Reads**: which module has a readability relationship to which module.
- **Exports**: which packages are exposed for compile-time and runtime access.
- **Opens**: which packages allow deep reflective access within the configured scope.
- **Class loader**: still handles loading classes and participates in determining type identity; `ModuleLayer` is not synonymous with class loader, because the mapping from modules to loaders can vary.

Access rights are determined by **all** relevant loader boundaries, modifiers, and module rules. Do not try to "fix" module errors merely by adding a JAR path to the classpath, or fix a `ClassCastException` between two loaders with `--add-opens`.

## 5. Java 17+ Experiment: Two Loaders, One Class Name, Two Types

The program below generates the source code for `example.Payload`, compiles it using the **JDK** compiler, and then creates two independent `URLClassLoader` instances pointing to the same class directory. It demonstrates the exact difference between "same binary name" and "same type identity".

Save the code to `LoaderNamespaceDemo.java`:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class LoaderNamespaceDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("loader-namespace-");
        Path source = dir.resolve("example/Payload.java");
        Path bytecode = dir.resolve("example/Payload.class");

        try {
            Files.createDirectories(source.getParent());
            Files.writeString(source,
                    "package example; public class Payload { }");

            JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
            if (compiler == null) {
                throw new IllegalStateException("Run with a JDK, not a JRE");
            }
            int exit = compiler.run(
                    null, null, null,
                    "-d", dir.toString(), source.toString());
            if (exit != 0) {
                throw new IllegalStateException("Compilation failed: " + exit);
            }

            URL location = dir.toUri().toURL();
            ClassLoader platform = ClassLoader.getPlatformClassLoader();

            try (URLClassLoader left =
                         new URLClassLoader(new URL[]{location}, platform);
                 URLClassLoader right =
                         new URLClassLoader(new URL[]{location}, platform)) {

                Class<?> leftType = Class.forName(
                        "example.Payload", true, left);
                Class<?> rightType = Class.forName(
                        "example.Payload", true, right);
                Object leftObject =
                        leftType.getDeclaredConstructor().newInstance();

                System.out.println(leftType.getName()
                        .equals(rightType.getName()));
                System.out.println(leftType == rightType);
                System.out.println(rightType.isInstance(leftObject));
                System.out.println(leftType.getClassLoader() == left);
                System.out.println(String.class.getClassLoader() == null);
            }
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(bytecode);
            Files.deleteIfExists(dir.resolve("example"));
            Files.deleteIfExists(dir);
        }
    }
}
```

Run in the directory containing the file using JDK 17 or later:

```bash
javac LoaderNamespaceDemo.java
java LoaderNamespaceDemo
```

Stdout upon successful compilation and execution:

```text
true
false
false
true
true
```

Explanation in order:

1. `true`: both classes have the same **binary name**.
2. `false`: the two `Class<?>` variables do not reference the same class definition.
3. `false`: the object created by `leftType` is **not** an instance of `rightType`, so `rightType.cast(leftObject)` will throw `ClassCastException`.
4. `true`: `left` is the defining loader of the left `Payload` copy.
5. `true`: `String` is a core JDK class defined by the bootstrap loader, so the API returns `null`.

The program uses `platform` as the parent so that `example.Payload` is not "picked up first" by the application loader. If two `URLClassLoader` instances share a parent **and the parent has already defined `Payload`**, the default parent-first mechanism will cause both to receive the same `Class` from the parent, and the comparison results may differ. That is why designing where JARs are placed matters.

## 6. Dependency Isolation in Plugin Architectures

Suppose a host application needs to run Plugin A, which depends on `json-lib 1.x`, and Plugin B, which depends on `json-lib 2.x`. If both JARs are placed on a single flat classpath where they share the same binary names, classpath ordering and loading behavior may cause only one version to be selected, leading to `NoSuchMethodError` or incorrect behavior.

An intentional architecture:

```text
Host / parent loader
  ├─ com.acme.spi.Plugin          (shared interface)
  ├─ com.acme.spi.Request         (shared communication data type)
  └─ shared stable libraries
         ↑                       ↑
  Plugin A loader            Plugin B loader
    ├─ impl.APlugin            ├─ impl.BPlugin
    └─ json-lib 1.x            └─ json-lib 2.x
```

**Boundary design principles:**

- **Place shared APIs/SPIs in the parent loader**: the host and plugins must reference **the exact same** `com.acme.spi.Plugin`. If a plugin packages and redefines that interface itself, casting to the host's interface can fail even though the names match.
- **Place libraries needing isolation in separate loaders**: only dependencies that are truly meant to be separate should be defined in individual loaders. If the same library name already exists in the parent and the plugin loader remains parent-first, the plugin may inadvertently use the parent's copy.
- **Use child-first strategies selectively**: some frameworks prioritize a plugin's JARs for its own packages while still delegating JDK classes and shared APIs/SPIs to the parent. Writing an arbitrary child-first loader can cause `LinkageError`, break type identity, or undermine security assumptions.
- **Exchange data through stable contracts**: shared interfaces, shared DTO types, primitives, `String`, or intermediate JSON data. Do not pass Plugin A's `json-lib.internal.Node` directly to Plugin B if both sides define that class independently.
- **Manage the lifecycle**: closing a `URLClassLoader` releases resources such as JAR handles, but does not guarantee immediate class unloading. For GC to reclaim a loader, you must eliminate all remaining references to classes, instances, threads, `ThreadLocal`, TCCL, caches, and callbacks belonging to the plugin.

### Parent-First vs. Child-First for Overlapping Dependencies

| Loading Strategy | Benefits | Limitations |
| --- | --- | --- |
| Parent-first | Keeps JDK and shared APIs consistent; predictable | Cannot isolate a private library if a version with the same name is already loaded by the parent |
| Selective child-first | Lets plugins prefer internal library versions | Must exclude shared API packages and protect JDK classes; hard to diagnose when types leak |
| Separate loader per plugin, communicating only via parent SPI | Separates implementation libraries while preserving a shared contract | Must manage resources, TCCL, serialization, and plugin lifecycle |

**Cross-boundary example:** the host invokes `Plugin.execute(Request)` through an interface defined by the parent. Inside the plugin, it may use a private JSON parser, but before returning the result to the host, the data must be converted into a shared result type defined by the parent. When designing APIs, avoid letting plugin-private types appear in public method signatures of the shared contract.

## 7. Context ClassLoader and ServiceLoader

A library residing in a parent loader sometimes needs to discover providers defined by a child loader. Because a parent does not automatically search downward into children, Java provides the **Thread Context ClassLoader (TCCL)**:

```java
ClassLoader previous =
        Thread.currentThread().getContextClassLoader();
try {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    // Call the library that needs to discover providers in the plugin context.
} finally {
    Thread.currentThread().setContextClassLoader(previous);
}
```

This is an **illustrative snippet** assuming `pluginLoader` has already been created by the framework; it is not a standalone program. You must restore the TCCL in `finally`, especially with thread pools, otherwise the old plugin may be retained or affect subsequent tasks.

`ServiceLoader` can discover providers via a specified loader, e.g., `ServiceLoader.load(Plugin.class, pluginLoader)`. To succeed, the provider must implement **the exact** `Plugin` interface used by the host; provider metadata (such as `META-INF/services/...` on the traditional classpath or `provides ... with ...` in a module) must also be correct. Even if a loader finds the provider, there is still no guarantee the provider can be cast to the host's SPI if the SPI was redefined.

Do not confuse `Thread.currentThread().getContextClassLoader()` with the loader that defined the currently executing class: they can be different. TCCL is a thread-contextual loader selection mechanism; it does not change the identity of an already-defined class.

## 8. Common Errors and Tracing Boundaries

| Symptom | Cause to Check | How to Investigate |
| --- | --- | --- |
| `ClassNotFoundException` | The requested loader could not find the class name | Print the class name, entry loader, URLs/JARs, and parent hierarchy |
| `NoClassDefFoundError` | Missing dependency at resolution time or failed initialization state after an earlier failure | Read the full `Caused by` chain, verify dependencies and earlier initialization errors |
| `ClassCastException` with the same class name on both sides | Two loaders defined the same binary name | Compare `a.getClass() == expectedType` and print the defining loader on each side |
| `NoSuchMethodError` / `NoSuchFieldError` | The actual loaded version/API does not match the caller's bytecode | Identify the JAR source and the version **actually loaded** |
| `LinkageError: loader constraint violation` | The JVM sees incompatible definitions at a type-linking boundary | Inspect types in the method descriptor and the loader of each component |
| `IllegalAccessError` | Invalid bytecode/runtime package/module access rights | Check modifiers, defining loaders, `exports`, and module configuration |
| `ServiceConfigurationError` | Provider not found, cannot be instantiated, or is not a subtype of the shared service | Check provider metadata, classpath/module path, and SPI identity |
| `InaccessibleObjectException` | Deep reflective access blocked by module encapsulation | Check `opens`, access direction, and valid alternative APIs |

**Key distinction:** `ClassNotFoundException` is a checked exception commonly thrown when calling class-loading APIs by name; `NoClassDefFoundError` is a linkage/initialization error when the JVM cannot use an expected definition—do not automatically treat them as the same issue.

### Concise Diagnostic Workflow

1. Record the **binary name**, which class is making the call, and the full exception chain.
2. Print `SomeType.class.getClassLoader()`; for dynamic objects, print `obj.getClass().getClassLoader()`. Check both sides of the API boundary.
3. Inspect where the bytecode was loaded from; for classes with an available code source, you can use `clazz.getProtectionDomain().getCodeSource()` (which may return `null`).
4. On JDK 17+, run `java -Xlog:class+load=info ...` to trace class-loading activity. Depending on the logging setup, you may need to combine this with loader info from the application to confirm identity.
5. If the process allows attaching, `jcmd <pid> VM.classloaders` provides a view of the loader hierarchy; available commands can be checked with `jcmd <pid> help`.
6. Cross-check the classpath/module path, parent relationships, delegation rules, and the actual set of JARs attached to each loader.
7. For issues that occur only after a redeploy/plugin reload, audit references retaining the old loader: long-lived threads, schedulers, callbacks, static registries, caches, TCCL, or `ThreadLocal`.

A quick inspection helper in Java:

```java
static void describe(Class<?> type) {
    System.out.println("class=" + type.getName());
    System.out.println("loader=" + type.getClassLoader());
    System.out.println("module=" + type.getModule().getName());
}
```

The snippet above is a **helper method** placed in an application class for invocation; `getModule().getName()` may return `null` for an unnamed module. A loader's `toString()` is useful for observation, but should not be treated as an immutable or unique identifier.

## 9. Misconceptions That Lead to Flawed Designs

- **"Same FQN means it can be cast."** False when the defining loaders differ. The FQN is only half of a type's identity.
- **"A child loader can load any class from a sibling loader."** False under default delegation; a dedicated lookup channel, layer, or bridge is required.
- **"Creating a URLClassLoader isolates all dependencies."** False if the library is already present in the parent and parent-first returns the parent's copy.
- **"Same package name grants package-private access."** A runtime package also depends on the defining loader.
- **"Changing TCCL changes the class of an existing object."** TCCL affects how certain APIs look up classes/providers going forward; it does not redefine existing classes.
- **"Using reflection bypasses all boundaries."** Reflection is still subject to access checks and module encapsulation.
- **"Closing a loader means unloading all classes."** The JVM can only reclaim classes/loaders when reachability and lifecycle conditions are met.
- **"JPMS replaces ClassLoader."** Modules are an organization/encapsulation mechanism, while loaders still handle loading and type identity.

## 10. Application: Designing a Version-Conflict-Free Plugin System

Before implementing, answer these questions in order:

1. **What must be shared?** Identify a single canonical copy of interfaces, DTOs, and exceptions in the host-side API/SPI.
2. **What must be isolated?** List libraries that may vary in version across plugins; prevent those libraries from leaking through public APIs.
3. **What does the loader graph look like?** Clearly map parent-child relationships, directories/JARs for each loader, and which packages are parent-first or child-first.
4. **Who is responsible for provider discovery?** Specify the loader for `ServiceLoader` or set TCCL at the exact call site and restore TCCL afterward.
5. **What gets released when a plugin stops?** Close resources, interrupt threads, unregister hooks, clear caches/`ThreadLocal`, and drop references to objects/classes/loaders.
6. **Which collisions should be tested?** Two plugins using the same class name with different bytecode; two JSON library versions; casting across the SPI; plugin reload; missing classes at resolution time.

### Knowledge Self-Check

**Question 1.** Two different `URLClassLoader` instances both load the same `example.Payload.class` path. Are the two `Class` objects guaranteed to be identical?  
**Answer:** No. If each loader defines the class itself, they are two distinct types; if both delegate to the same defining loader in a parent, they can be the same type.

**Question 2.** Plugin A reports `ClassCastException: com.acme.spi.Plugin cannot be cast to com.acme.spi.Plugin`. What should you check first?  
**Answer:** The identity of `Plugin.class` on the host side and the plugin side, especially whether the plugin packaged/redefined the SPI instead of delegating to the parent.

**Question 3.** Plugin B is supposed to run a different `json-lib` version from the host, yet it still loads the host's copy. Why?  
**Answer:** Loader B is using parent-first, so the parent found the `json-lib` class first. You need to design dependency separation with selective delegation while avoiding breaking shared APIs/SPIs.

**Question 4.** A shared library cannot find a provider placed inside a plugin, even though the plugin can see that library. Why?  
**Answer:** Visibility is one-way: the library's parent loader does not automatically search down into the plugin's child loader. Check the loader passed to `ServiceLoader` or the TCCL during discovery.

## Conclusion

The right mental model is to clearly map **who defines which class**, **which loader can request classes from where**, and **which types must share a single identity at communication boundaries**. When these three aspects are consistent, Java's `ClassLoader` can support plugins and multiple dependency versions safely; when they are mixed up, errors typically surface only at runtime as cast, linkage, access, or service discovery failures.
