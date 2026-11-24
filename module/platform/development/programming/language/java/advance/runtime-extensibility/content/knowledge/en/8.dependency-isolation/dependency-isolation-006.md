# Loading Constraints, Runtime Packages, and Non-Public Member Access

## 1. Why Can the Same Package Name Still Be Inaccessible?

When designing Java plugins, a confusing situation arises when two classes both declare:

```java
package com.example.shared;
```

yet one class resides in the host application and the other is loaded by a plugin's dedicated `ClassLoader`. Even though the package name is identical, the JVM may treat them as belonging to **two distinct runtime packages**. As a result, default-access (*package-private*) members or certain `protected` accesses can fail even when the source code appears to live in the same package.

The central rule in the JVM mechanism is: **a runtime package is identified by the package name and the class loader that defines the class**. In a modular environment, access is further constrained by the Java Platform Module System (JPMS), such as `exports`, `opens`, and module relationships. You cannot simply change a `package` string or JAR path to cross that boundary.

This article focuses on the interaction between class loading, runtime package identity, and non-`public` member access checks; it is especially useful when host and plugins intentionally isolate dependencies using multiple class loaders.

## 2. Class Identity and Runtime Packages

### 2.1. Class Identity

In the JVM, each class is identified by:

1. **Binary name**, for example `com.example.api.Contract`.
2. **Defining class loader**: the loader that actually invokes the mechanism to define that class.

Consequently, two different class loaders can define two classes with the same binary name while the JVM still considers them two distinct types. The outcome can be `ClassCastException`, `LinkageError`, or access-check errors depending on usage and loading constraints.

Distinguish the roles:

- **Initiating loader**: the loader requested to find/load the class; it may delegate to a parent loader.
- **Defining loader**: the loader that actually defines the `Class` from bytecode.
- **Parent delegation**: the mechanism commonly used to prioritize classes provided by a parent loader. Two plugin loaders both delegating the API to the parent can see the exact same **single** `Contract.class`.

In this article, runtime package boundaries rely on the **defining loader**, not merely the loader passed to `Class.forName` or the class path appearing in configuration.

### 2.2. Runtime Package

Consider two classes:

```text
HostClass    package com.example.shared;  defining loader = L1
PluginClass  package com.example.shared;  defining loader = L2
```

If `L1 != L2`, the two classes reside in **two different runtime packages**, despite having the same package name. This affects accessibility:

| Member/type | Key condition on the traditional class path |
|---|---|
| `public` class, `public` member | Accessible if the declaring class is visible and not blocked by module policy |
| `private` | Accessible only under same-class/nest rules; does not become freely accessible due to same package |
| No modifier (package-private) | Accessible only within the **same runtime package** |
| `protected` | Allowed within the same runtime package; or under subclass rules with the additional restrictions of `protected` access |
| Package-private top-level class | Cannot be used automatically from a plugin loader merely by sharing the package name |

A Java class may compile validly because the compiler sees sources in the same package, yet when running under different loaders, the JVM checks permissions against the actual runtime package and can throw `IllegalAccessError`.

## 3. Package-Private: A Practical Failure Example

Consider two sources in the same package:

**`host-src/demo/shared/HostSecret.java`**

```java
package demo.shared;

public class HostSecret {
    static String token() {
        return "HOST_TOKEN";
    }
}
```

`token()` has no modifier, so it is **package-private**.

**`plugin-src/demo/shared/PluginCall.java`**

```java
package demo.shared;

public class PluginCall {
    public static String call() {
        return HostSecret.token();
    }
}
```

At compile time, if both classes are visible on the same compile classpath and in the same package, `javac` accepts the call. Suppose at runtime `HostSecret` is defined by the parent loader while `PluginCall` is defined by a child loader; then even though the binary package name is still `demo.shared`, the two classes do not belong to the same runtime package.

### 3.1. Runnable Example on Java 17+

Create the structure:

```text
demo/
├── host-src/demo/shared/HostSecret.java
├── plugin-src/demo/shared/PluginCall.java
└── Runner.java
```

File **`Runner.java`**:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class Runner {
    public static void main(String[] args) throws Exception {
        URL pluginUrl = Path.of("build/plugin.jar").toUri().toURL();

        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[] {pluginUrl},
                Runner.class.getClassLoader())) {
            Class<?> plugin = Class.forName(
                    "demo.shared.PluginCall", true, pluginLoader);

            System.out.println("host loader: "
                    + demo.shared.HostSecret.class.getClassLoader().getClass().getSimpleName());
            System.out.println("plugin loader: "
                    + plugin.getClassLoader().getClass().getSimpleName());

            try {
                System.out.println(plugin.getMethod("call").invoke(null));
            } catch (java.lang.reflect.InvocationTargetException ex) {
                Throwable cause = ex.getCause();
                System.out.println("cause: " + cause.getClass().getSimpleName());
            }
        }
    }
}
```

Run these POSIX shell commands from the `demo/` directory:

```bash
mkdir -p build/host build/plugin build/runner
javac -d build/host host-src/demo/shared/HostSecret.java
javac -cp build/host -d build/plugin plugin-src/demo/shared/PluginCall.java
jar --create --file build/host.jar -C build/host .
jar --create --file build/plugin.jar -C build/plugin .
javac -cp build/host.jar -d build/runner Runner.java
java -cp "build/runner:build/host.jar" Runner
```

Typical output on OpenJDK 17 on a standard class path:

```text
host loader: AppClassLoader
plugin loader: URLClassLoader
cause: IllegalAccessError
```

Explanation:

1. The JVM application loader defines `HostSecret` from `host.jar`.
2. `PluginCall` exists only in `plugin.jar`, which the parent loader does not see, so `URLClassLoader` defines the plugin class.
3. When plugin code executes `invokestatic HostSecret.token()`, the JVM detects that `token()` is not public and the two classes are not in the same runtime package.
4. `IllegalAccessError` is thrown at runtime. Reflection in `Runner` is used only to call `PluginCall.call()` and wraps the exception in `InvocationTargetException`; the root cause is the direct access error in the plugin bytecode.

The loader class names may differ on another JVM/launcher; the points to verify are that **the class loaders of the two classes differ** and `IllegalAccessError` occurs.

If `HostSecret.token()` is changed to `public static` and the host JAR is recompiled, the cross-loader call is permitted under `public` access in this class path example. However, with JPMS named modules, you must also ensure the package is exported to the accessing module.

**What to avoid:** Do not bundle `host.jar` into `plugin.jar` to keep a private copy of `HostSecret`. That approach may mask the access-error symptom, but it splits state/type identity, breaks contracts, and makes the system hard to debug.

## 4. How Does `protected` Access Differ from Package-Private?

A `protected` member has two important access paths:

- Classes in the same runtime package can access it under package rules.
- A subclass in a different runtime package can access permitted inherited members, though for instance members there are usually additional conditions on the type of the target expression; not every instance of the superclass is a valid receiver.

Example of a subclass permitted at the source level:

```java
package demo.plugin;

public class PluginChild extends demo.api.Base {
    public String readOwnState() {
        return this.state();
    }
}
```

Suppose `demo.api.Base` is public and has:

```java
protected String state() {
    return "ready";
}
```

This is an **illustrative snippet**; `Base` must be placed in `demo/api/Base.java` inside the API JAR and `PluginChild` in `demo/plugin/PluginChild.java` to compile. Access through `this` is valid because `PluginChild` inherits from `Base`; it does not mean arbitrary code in package `demo.plugin` can call `state()`.

If a plugin merely uses the same package name as `Base` but a different loader, the "same package" access path does not take effect; subclass rules must be satisfied. For plugin APIs, it is generally better to use `public` methods in contracts/interfaces rather than relying on package-private friendliness or intricate `protected` rules.

## 5. What Constraints Do JPMS Modules Add?

Since Java 9, **named modules** also enforce module-level access boundaries:

- `requires` declares module dependencies.
- `exports` permits code in other modules to access **public types** in the exported package.
- `opens` permits deep reflection on the opened package, according to the scope of the module directive.
- `exports ... to ...` / `opens ... to ...` apply only to the specified target modules.

Example API module descriptor:

```java
module demo.api {
    exports demo.api;
}
```

Plugin module:

```java
module demo.plugin {
    requires demo.api;
}
```

The module declarations above are **illustrative code** requiring an appropriate source/class structure and module-path build; they are not a single-file program.

**Core warning:** `exports` does not turn package-private into public. Nor does a `public` class in a non-exported package have normal access from another module. `opens` enables deep reflection under the specified conditions, but does not grant normal Java bytecode access to package-private members.

JPMS does not permit arbitrary duplicate package names across named modules resolved in the same module layer/ClassLoader; "split packages" can cause module resolution or layer definition errors. In a plugin architecture, design distinct package namespaces per module and avoid treating matching package names as an API-sharing mechanism.

## 6. Can Reflection Bypass This Boundary?

Reflection behaves differently from normal bytecode linkage.

Java reflection example:

```java
var method = someClass.getDeclaredMethod("hidden");
method.setAccessible(true);
Object value = method.invoke(instance);
```

The snippet above only illustrates the API and depends on an existing `someClass` and `instance`. It is not guaranteed to work across all modules/class loaders. `setAccessible(true)` can fail with `InaccessibleObjectException` when the package resides in a named module that is not opened under the required access relationship. Java module encapsulation is not disabled merely because a plugin uses reflection.

On the class path / unnamed module, many deep reflection cases may be allowed, yet doing so creates tight coupling to implementation details, complicates maintenance, and introduces compatibility risks. `MethodHandles.Lookup` and `privateLookupIn` are also governed by their own access rules and module openness; they should not be treated as a free bypass mechanism.

In a plugin system, the durable solution is to publish a clear API, move required capabilities into the contract, and pass dependencies through interfaces or factories.

## 7. Isolating Dependencies and Sharing the API

A typical loader layout:

```text
Bootstrap / Platform
       |
Application loader (parent)
       |-- demo.api.PluginService
       |-- demo.api.PluginContext
       |-- demo.host.Host
       |
       +-- PluginLoader A (child)
       |       |-- demo.vendorA.PluginA
       |       +-- library A dependencies
       |
       +-- PluginLoader B (child)
               |-- demo.vendorB.PluginB
               +-- library B dependencies
```

Host and plugins share the **same definition** of interfaces/APIs in the parent. Plugin implementation classes should sit in separate namespaces owned by child loaders. This layout avoids trying to use package-private access to communicate across loaders.

If a plugin loads its own copy of `demo.api.PluginService` (for example, child-first loading favors a plugin JAR containing the API), the host can hit `ClassCastException` when trying to cast the plugin instance to the host's `PluginService`. Both interfaces have the same name, yet differing defining loaders make them distinct types.

**Loading constraints:** the JVM enforces type consistency constraints when linking methods/fields whose types cross loader boundaries. A system with misconfigured class loaders can hit `LinkageError: loader constraint violation` even before an explicit cast occurs. The operational rule is to keep cross-boundary types (shared interfaces, DTOs, exceptions) in the shared API and never duplicate them inside plugin loaders.

## 8. Sealing and Package Namespaces

**Package sealing** in a JAR manifest is a separate mechanism: setting `Sealed: true` requires classes of a sealed package to be defined from a matching code source, typically the same JAR, within a class loader. It prevents split packages across multiple JARs in the same loader when the package is sealed.

However, sealing does **not** merge two runtime packages in two different loaders into one package and does **not** grant package-private access across loaders. Changing `Sealed` also cannot fix `IllegalAccessError` in the `HostSecret` and `PluginCall` example because the cause lies in differing defining loaders.

A helpful rule when packaging plugins:

- Use dedicated packages for internal implementations and dependencies.
- Keep shared APIs in a separate JAR/module supplied by a shared loader.
- Do not create split packages across host, contract, and plugins.
- Enable sealing only when you want to enforce the class definition source within a package, after verifying JAR and loader structure.

## 9. Common Deployment Errors

| Symptom | Possible cause | What to check |
|---|---|---|
| `IllegalAccessError` when calling a package-private method | Caller and declaring class share a package name but have different defining loaders | Print `Class.getClassLoader()` and check runtime packages |
| `ClassCastException` between two same-named interfaces | The contract was loaded twice in different loaders | Check `api.jar` in parent and child, and parent delegation |
| `NoClassDefFoundError` | Missing class dependency or error during class initialization | Inspect full stack trace and runtime classpath |
| `LinkageError: loader constraint violation` | Cross-boundary types were defined inconsistently | Check binary names, signatures, and loader topology |
| `InaccessibleObjectException` in reflection | Named module has not `opens` the appropriate package | Check `module-info.java`; use `--add-opens` only temporarily when risks are understood |
| `SecurityException: sealing violation` | Classes of the same package were loaded from invalid multiple code sources | Inspect manifest, JARs, and defining loaders |
| `IllegalAccessError` with a public class in a named module | Package is not exported or module access is invalid | Check module readability and `exports` |

Not every error is caused by class loaders: verify the exact exception and stack trace before changing packaging structure. For example, `NoSuchMethodError` is usually related to binary incompatibility rather than package-private access.

## 10. Diagnostics and Testing

### Observing Sources and Loaders

You can add diagnostics in the host:

```java
static void describe(Class<?> type) {
    System.out.println(type.getName());
    System.out.println("loader=" + type.getClassLoader());
    System.out.println("module=" + type.getModule().getName());
    System.out.println("source=" + (type.getProtectionDomain().getCodeSource() == null
            ? "unknown"
            : type.getProtectionDomain().getCodeSource().getLocation()));
}
```

This is an **illustrative utility snippet** that must be placed inside a Java class and may be subject to security policies in some environments. `getModule().getName()` can return `null` for an unnamed module. Do not rely on a loader's display string as an absolute ID; compare the loader objects themselves in a debugging environment.

On modern HotSpot JVMs, you can use:

```bash
java -Xlog:class+load=info -cp "build/runner:build/host.jar" Runner
```

Class-loading output helps identify which JAR a class came from. When debugging with multiple plugin loaders, combine logs, `Class.getClassLoader()`, code sources, modules, and the dependency graph.

### Plugin Testing Checklist

1. **Compile** plugins against the public contract API only; do not use package-private members of the host.
2. **Runtime** verification that the API is defined once by the parent loader and implementations are defined by child loaders as intended.
3. **Dependency isolation** by running two plugins concurrently that use different versions of internal libraries to check for conflicts.
4. **Access control** tests confirming public API calls succeed and invalid accesses are blocked.
5. **Module mode** if using JPMS: test `requires`, `exports`, `opens`, package names, and module layers.
6. **Packaging** checks ensuring JARs do not inadvertently embed duplicate contracts, split packages, or conflicting sealing configurations.

## 11. Conclusion

A package name is part of Java's namespace, yet the runtime package also depends on the **defining class loader**. Placing a plugin and the host in the same package name does not establish package-private access when they are defined by different loaders. For both sides to communicate reliably, design a `public` contract shared by a common loader, control module exports when using JPMS, and keep each plugin's implementation classes and dependencies in separate namespaces. This makes dependency isolation viable without relying on access privileges that break easily at runtime.