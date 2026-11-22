# 5.9 Designing Public APIs and Intentional Access Opening When Building Dynamic Libraries

**Module:** Java Advance - dynamic-runtime  
**Parent Topic:** 5. Access Control

A dynamic library typically allows an application to **discover, load, connect, and invoke** separately deployed components: plugins, service providers, adapters, processors, or extension modules. Proper design requires distinguishing **which contracts are allowed to be used externally** from **which implementation details only the library is permitted to manage**.

A useful principle: **expose the minimal contract; grant additional access only to those who need it, with the right type of access and the right scope**. This protects the ability to swap implementations, reduces accidental coupling between modules, and enables upgrading the API without forcing consumers to know internal structures.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Choose what should belong to the **public API/SPI** and what should remain in the **internal implementation** when designing a dynamic library.
2. Distinguish between access control layers: Java modifiers (`public`, `protected`, package-private, `private`), packages and class loaders, as well as **JPMS module readability / `exports` / `opens`**.
3. Understand when **normal access** (standard Java access) differs from **deep reflection** (reflective access to non-public members).
4. Use `uses` / `provides` with `ServiceLoader` so the host consumes an SPI without having to export the package containing the provider.
5. Try a Java 17+ example with three independent modules; observe that the provider runs via SPI while direct reflection to the internal package is blocked.
6. Determine when to use qualified `exports ... to`, qualified `opens ... to`, or an explicit API instead of overly broad access; recognize compatibility and security pitfalls.

## 2. Two Boundaries to Design Before Writing Code

### 2.1. Contract Boundary: What may external code **depend on**?

A **public API (Application Programming Interface)** is the set of types and behaviors that callers are permitted to use: interfaces, classes, factory methods, DTOs, error contracts, thread-safety, lifecycle rules, and version compatibility. An **SPI (Service Provider Interface)** is the contract for the *implementation-providing* side, such as the `TextPlugin` interface that plugins must implement.

A practical design typically divides things as follows:

| Component | Should it be public? | Reason |
| --- | --- | --- |
| Stable `TextPlugin` interface | **Yes**, if independent host/plugins need to compile against it | It is the interaction contract |
| Input/output data types of `TextPlugin` | **Yes**, if they appear in public signatures | Callers must be able to read and use them |
| Well-designed factory or registry | **Maybe** | Serves as a supported entry point, avoiding callers having to guess class names |
| Concrete `UpperTextPlugin` implementation | **Usually no** | Allows changing algorithms, class names, and package structure |
| Parser configuration, cache, private fields, helpers | **No**, unless there is a genuine integration need | Avoids depending on details that may change |
| Reflection gate (`opens`) for data-processing frameworks | **Only when needed**, restricted to target packages and modules | Supports runtime mechanisms that cannot be achieved through normal contracts alone |

**`public` on a class does not mean "this is an API committed to long-term support."** In Java, the `public` modifier permits access according to language semantics, but with a **named module**, a public class in a **non-exported** package still cannot be directly imported or invoked by code outside the module as a normal API.

### 2.2. Technical Boundary: **Through which mechanisms** can external code access it?

View the access system as multiple necessary conditions that must combine:

- **Type/member modifiers:** `public`, `protected`, package-private, and `private` define the baseline access level.
- **Package:** types in the same package have package-level privileges, but in the module system, package names cannot be treated as an arbitrary sharing mechanism across modules.
- **Module readability:** the caller module must be able to read the module containing the API when compiling/invoking in the normal way (`requires` and the module graph).
- **Export:** the package must be exported to the caller for the caller to have public access under Java semantics across modules.
- **Open:** the package is opened for deep reflection into non-public members via the corresponding Reflection/Method Handles APIs.
- **Class loader/layer:** whether the class is found, whether the module is resolved, and whether type identities match.
- **Application contract/authorization:** Java-level invocation rights do not automatically guarantee that the caller is permitted to perform a business operation or manipulate sensitive data.

Permissions of the **compiler**, **JVM runtime**, **Reflection**, and **business policy** are related, but they are not the same thing.

## 3. How Do `exports`, `opens`, `uses`, and `provides` Differ?

| Declaration in `module-info.java` | What does it allow? | What should not be inferred |
| --- | --- | --- |
| `requires com.example.spi;` | The current module reads the required dependency | Does not automatically export the API of the required module |
| `exports com.example.api;` | Allows any module that reads this module to access types/members matching Java visibility in the package | Does not open private fields/methods for deep reflection from external modules |
| `exports com.example.api to com.example.friend;` | Exports the package only to the named module | Does not grant access to other modules |
| `opens com.example.model;` | Allows deep reflection at runtime into that package from other modules | **Does not** allow code in other modules to import this package at compile time if the package is not exported |
| `opens com.example.model to com.example.mapper;` | Opens a package for a **specific module** to perform deep reflection | Does not grant the same access to all modules |
| `uses com.example.spi.TextPlugin;` | Declares that the module **consumes a service** using `ServiceLoader` | Does not select or provide an implementation itself |
| `provides com.example.spi.TextPlugin with com.example.impl.UpperTextPlugin;` | Publishes a service provider in the current module | **Does not require** exporting the package containing the implementation for `ServiceLoader` to use it |

**`exports`** and **`opens`** serve different purposes:

- `exports` is for **Java language-level APIs**, allowing callers to import public types, compile, and invoke directly.
- `opens` is for **runtime deep reflective discovery/access**. APIs such as `Field.trySetAccessible()` or `MethodHandles.privateLookupIn(...)` must satisfy the corresponding conditions and do not bypass module boundaries on their own.
- A package that is **only `opens`** is not exported for direct import/access at compile time. An `exports` package also does not implicitly allow Reflection to access every private member from external modules.
- `open module ...` opens **all packages** of the module for deep reflection; this is usually broader than necessary for a dynamic library.

**Note on runtime checks:** `Module.isExported(pkg, otherModule)` treats an **open** package as having export access at runtime in certain cases. Do not use the result of this runtime check API in place of reading `module-info.java` to decide whether a package is a **public compile-time API**.

A **qualified directive** (the form with `to`) uses **target module names**, not package names or class names. For libraries on the classpath (the unnamed module), the JPMS conditions for **named modules** above do not apply in the same way; if strict boundary control is needed, you must actually deploy proper named modules, not merely add documentation describing intent.

## 4. Java 17+ Hands-On Lab: Public SPI, Internal Provider

We will build three named modules:

- **`com.example.dynamic.spi`**: contains the `TextPlugin` contract that all consumers need to know, exporting only the API package.
- **`com.example.dynamic.plugin`**: provides an implementation named `UpperTextPlugin`, **neither exporting nor opening** the implementation package.
- **`com.example.dynamic.host`**: uses `ServiceLoader`, only `requires` the SPI module and declares `uses` for the service; does not compile against the concrete implementation.

### 4.1. Directory Structure

Create the files at the following paths, starting from an empty project directory:

~~~text
src/
├── com.example.dynamic.spi/
│   ├── module-info.java
│   └── com/example/dynamic/spi/TextPlugin.java
├── com.example.dynamic.plugin/
│   ├── module-info.java
│   └── com/example/dynamic/plugin/internal/UpperTextPlugin.java
└── com.example.dynamic.host/
    ├── module-info.java
    └── com/example/dynamic/host/Main.java
~~~

The first directory name under `src/` is the **module name**, matching `--module-source-path src` mode. The classes inside follow the Java package path.

### 4.2. SPI Module: Export Only the Contract

**`src/com.example.dynamic.spi/module-info.java`**

~~~java
module com.example.dynamic.spi {
    exports com.example.dynamic.spi;
}
~~~

**`src/com.example.dynamic.spi/com/example/dynamic/spi/TextPlugin.java`**

~~~java
package com.example.dynamic.spi;

public interface TextPlugin {
    String id();
    String transform(String input);
}
~~~

Callers need both `id()` and `transform(String)`. The input/output type here is only `String`, without exposing implementation classes. More complex APIs should define error rules, nullability, state/thread-safety, and versioning in the same place where the SPI is published.

### 4.3. Provider Module: Publish the **service**, Keep the Implementation Package Hidden

**`src/com.example.dynamic.plugin/module-info.java`**

~~~java
module com.example.dynamic.plugin {
    requires com.example.dynamic.spi;
    provides com.example.dynamic.spi.TextPlugin
            with com.example.dynamic.plugin.internal.UpperTextPlugin;
}
~~~

**`src/com.example.dynamic.plugin/com/example/dynamic/plugin/internal/UpperTextPlugin.java`**

~~~java
package com.example.dynamic.plugin.internal;

import com.example.dynamic.spi.TextPlugin;
import java.util.Locale;

public final class UpperTextPlugin implements TextPlugin {
    public UpperTextPlugin() { }

    @Override
    public String id() {
        return "upper";
    }

    @Override
    public String transform(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
~~~

The provider class is `public` with a public no-arg constructor, satisfying the provider form supported by `ServiceLoader`. However, **the package `com.example.dynamic.plugin.internal` is not exported**. Clients do not need to import `UpperTextPlugin`; the module system and `ServiceLoader` use the `provides` declaration to obtain the provider.

### 4.4. Host Module: Consume the Service Without Depending on the Provider

**`src/com.example.dynamic.host/module-info.java`**

~~~java
module com.example.dynamic.host {
    requires com.example.dynamic.spi;
    uses com.example.dynamic.spi.TextPlugin;
}
~~~

**`src/com.example.dynamic.host/com/example/dynamic/host/Main.java`**

~~~java
package com.example.dynamic.host;

import com.example.dynamic.spi.TextPlugin;
import java.lang.reflect.Constructor;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) throws Exception {
        int count = 0;

        // 1. Call via SPI contract; host does not import the provider.
        for (TextPlugin plugin : ServiceLoader.load(TextPlugin.class)) {
            count++;
            System.out.println(plugin.id() + ":" + plugin.transform("java"));
        }
        System.out.println("providers=" + count);

        // 2. Attempt direct reflection access to the implementation.
        Class<?> impl = Class.forName(
                "com.example.dynamic.plugin.internal.UpperTextPlugin");
        Constructor<?> constructor = impl.getDeclaredConstructor();

        System.out.println("exported=" + impl.getModule().isExported(
                impl.getPackageName(), Main.class.getModule()));
        System.out.println("opened=" + impl.getModule().isOpen(
                impl.getPackageName(), Main.class.getModule()));
        System.out.println("tryAccessible=" + constructor.trySetAccessible());

        try {
            constructor.newInstance();
            System.out.println("directReflection=allowed");
        } catch (IllegalAccessException expected) {
            System.out.println("directReflection=blocked");
        }
    }
}
~~~

This is **an independent multi-module program that can be compiled and run** once all six files are saved. Using `Class.forName` in the second part is only to observe the access boundary. This API can obtain a `Class<?>` for a class present at runtime, but having a `Class` object **does not mean** having permission to invoke that class's constructor.

### 4.5. Compile and Run

From the directory containing `src/`, use **JDK 17 or later**:

**PowerShell (Windows):**

~~~powershell
$files = Get-ChildItem src -Recurse -Filter '*.java' |
    Select-Object -ExpandProperty FullName
javac --release 17 --module-source-path src -d out $files
java --module-path out --module com.example.dynamic.host/com.example.dynamic.host.Main
~~~

**Bash (Linux/macOS):**

~~~bash
javac --release 17 --module-source-path src -d out $(find src -name '*.java')
java --module-path out --module com.example.dynamic.host/com.example.dynamic.host.Main
~~~

Output with these exact three modules:

~~~text
upper:JAVA
providers=1
exported=false
opened=false
tryAccessible=false
directReflection=blocked
~~~

**Explanation of each observation:**

1. `ServiceLoader` locates the provider in the resolved module path environment, then calls `transform("java")` through `TextPlugin`. The result `upper:JAVA` confirms that the SPI contract is sufficient to use the dynamic implementation.
2. `providers=1` in the example project because there is only one provider. In a real application, the set of providers depends on the module graph/layer and deployed artifacts; do not assume a general provider ordering is stable across all environments.
3. `exported=false` and `opened=false` for the host module because the provider declared neither `exports` nor `opens` for the implementation package.
4. `tryAccessible=false` shows that the host cannot enable access to the constructor from another module when the package is not appropriately exported/opened.
5. `directReflection=blocked` is the expected behavior. The system still runs successfully via SPI, so **there is no need to open the implementation package just to use `ServiceLoader`**.

This output has been verified using `javac --release 17` and `java --module-path` with the exact sources shown.

### 4.6. Experimenting with Intentional Access Changes

Suppose there is an **approved integration requirement**: the host module genuinely needs to instantiate via Reflection to serve a mechanism outside `ServiceLoader`. In that case, **strictly within the scope of this experiment**, modify **`src/com.example.dynamic.plugin/module-info.java`** to:

~~~java
module com.example.dynamic.plugin {
    requires com.example.dynamic.spi;
    provides com.example.dynamic.spi.TextPlugin
            with com.example.dynamic.plugin.internal.UpperTextPlugin;

    opens com.example.dynamic.plugin.internal to com.example.dynamic.host;
}
~~~

Recompile everything and run. `opens ... to com.example.dynamic.host` grants the host deep reflective access to that package. `constructor.trySetAccessible()` can return `true` and the `newInstance()` call can succeed if no other condition blocks it. **You should not choose this design for a typical plugin example**, because `ServiceLoader` already handles instantiation via the SPI without granting extra access.

Note: `opens` counts as a form of public access at runtime when checking `Module.isExported(package, module)`; therefore, do not simply interpret the demo's `exported` variable as a pure `exports` configuration after adding `opens`.

## 5. Granting the Right Access for the Right Kind of Integration

### 5.1. Prefer API/SPI and Factories When Only Functionality Needs to Be Invoked

If external applications only need to invoke behavior, provide a public interface, public factory, or registry with a stable contract. With multiple independent providers, `ServiceLoader` or an explicit registry allows discovery without exporting each implementation package.

For modular projects, configure `uses` on the consumer and `provides` on the provider. A service provider in a named module can reside in a non-exported package; this is an important encapsulation capability. The provider must satisfy `ServiceLoader`'s rules regarding type, constructor, or an appropriate provider method.

**Do not design an API that requires callers to use `Class.forName("...internal...")` and cast down to an implementation class.** That turns internal package and class names into part of an informal contract, making refactoring and upgrades unpredictable.

### 5.2. Use `exports` When Consumers Need to Compile Against Public Types

For example, a module `com.example.library` exposing the package `com.example.library.api`:

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

This snippet is an **illustrative module descriptor**, not an additional file needed to run the example in Section 4. Only export packages whose surface consumers are permitted to depend on; avoid exporting `internal`, `impl`, or `generated` just to fix compile errors. To restrict access to a module you control:

~~~java
module com.example.library {
    exports com.example.library.internalbridge to com.example.friend;
}
~~~

`exports ... to` is a **qualified export**. It helps narrow down the consumers permitted public access, though it still creates coupling to the friend module's name; track it when renaming or splitting modules.

### 5.3. Use `opens` When Frameworks Genuinely Need Deep Reflection

A serializer, mapper, ORM, or dependency injection tool may need to invoke non-public constructors, read/write fields, or inspect members via Reflection. If a suitable public API path cannot be designed and the requirement is justified, open the **specific data/config package** to the **specific framework module**:

~~~java
module com.example.library {
    requires com.example.mapper;
    opens com.example.library.dto to com.example.mapper;
}
~~~

This is a module policy example, **not a standalone compilable program**: it assumes the modules and packages are named appropriately in a real project. Do not open a package containing secrets or the entire implementation just because a framework reports an access error; first verify the exact member, package, caller module, and type of Reflection actually needed.

If the framework runs in the **unnamed module** (classpath), the qualified `opens ... to` issue cannot be solved by writing a package name instead of a module name; proper packaging/launch design is required. The runtime flag `--add-opens` is sometimes useful for **migration/diagnostics**, but it makes access depend on the launch command:

~~~text
--add-opens com.example.library/com.example.library.dto=ALL-UNNAMED
~~~

This is an illustrative **JVM option fragment**, not a complete shell command. Use it only in a controlled manner; do not treat opening up to all unnamed modules as a long-term API model.

### 5.4. `setAccessible(true)` and `MethodHandles` Are Not Master Keys

When a member is outside the permitted scope, `Field.setAccessible(true)` or `Constructor.setAccessible(true)` can throw `InaccessibleObjectException`; `trySetAccessible()` can return `false`. `MethodHandles.privateLookupIn` is also subject to module access rules and does not bypass the limits of a non-open package on its own.

**`public` member + `public` class + `exports`** supports normal public access, but does not mean private fields can be accessed. **`opens`** grants deeper runtime Reflection within the opened package, but it is not "granting full administrative privileges" to a plugin, nor does it guarantee that external dependencies are sufficient to run.

## 6. Public API Compatibility in Dynamic Libraries

When a host and a plugin are compiled at different times, **API changes** may only surface as errors when loading/linking/invoking:

| Change | Risk | Design Approach |
| --- | --- | --- |
| Renaming package, module, or public type | Consumer cannot find the type; compile or runtime linkage error | Maintain contract names; plan migration/versioning for major changes |
| Changing SPI method name, parameters, or return type | Old provider/host is incompatible; may encounter `NoSuchMethodError`/`AbstractMethodError` | Design an evolution strategy, test with previous plugin versions |
| Adding an abstract method to an interface that old providers must implement | New consumer calling the method on an old provider may encounter `AbstractMethodError` | Consider a default method with clear semantics or a new SPI version |
| Adding a default method | Usually reduces provider modification needs, but can still cause conflicts or unintended behavior | Test across multiple versions; do not assume every default method is safe |
| Putting a private implementation type into a public API signature | Consumer becomes dependent on an inaccessible type or an ABI that is hard to change | Use public DTOs/interfaces belonging to an exported package |
| Exporting more packages or opening more deep reflection | Expands the dependency and access surface; hard to narrow later | Add only after a clear use case and consumer entity are identified |
| Changing provider implementation while keeping the SPI unchanged | Normally consumers via SPI do not need code changes | Preserve semantics, ID/provider selection, lifecycle, and errors as contracted |

Distinguish between **source compatibility**, **binary compatibility**, and **behavioral compatibility**. A change might compile yet cause the plugin to behave incorrectly in business terms; conversely, renaming a parameter usually does not change the JVM method descriptor, yet it can break name-based binding that frameworks build on top of Reflection.

If a public API returns a type from another module, consider declaring `requires transitive` **when consumers need to read that type in public signatures**. Do not add `transitive` for every internal dependency, as that accidentally widens the public dependency graph.

Establish contract versioning, test the host against old and new providers, measure execution errors per module, and have a fallback when no provider is found. This is part of dynamic library design, not merely choosing the `public` keyword.

## 7. Security and Reliability: Access Control Does Not Replace Isolation

- **Do not trust arbitrary plugins:** `ClassLoader` and module `exports`/`opens` are Java type-loading and access-control mechanisms; they **do not create a security sandbox** or prevent a plugin from using any capability the process has permission to use. Plugin code can execute in constructors, initializers, and methods.
- **Authorize by capability:** instead of giving a plugin full context/credentials, provide it with an interface that has clear permissions, exposing only the exact capabilities needed. If untrusted code must be executed, consider process-level isolation and OS permission limits.
- **Keep internal data narrowly scoped:** do not export/open packages containing implementations or sensitive data just to fix a Reflection error. With immutable DTOs and public factories, many integrations do not need deep reflection.
- **Do not grant access for debugging convenience:** `--add-opens` or `open module` may make an application run immediately, but it increases coupling to internal details; state the reason, scope, subject, and expiration when applying them.
- **Respect loaders/layers:** classes with the same binary name loaded by different defining class loaders can be distinct types. Do not use a class name string as proof that a class is compatible with the host's SPI.
- **Package artifacts properly:** in the example, the provider module must actually be present on the module path and resolved by the module system. A `provides` written in source code does not automatically bring a missing JAR into the runtime environment.

**Decision rule:** need to *invoke functionality* → public contract/SPI; need to *compile against types* → export the API package; need to *read private state via Reflection* → open the minimal package to the specific module, when truly necessary; need to *run untrusted code* → consider process isolation and OS permissions.

## 8. Diagnosing Access Errors in Real-World Applications

| Symptom | What to Check First |
| --- | --- |
| Compile error `package ... is not visible` or `does not export` | `requires`, `exports`, the exact public package/API, module path |
| `IllegalAccessError` at runtime | Do versions/class files/module graph differ from build time? Is the public type still exported? |
| `IllegalAccessException` when invoking constructor/method via Reflection | Java modifiers, package export/open, calling module, actual constructor/method |
| `InaccessibleObjectException` on `setAccessible(true)` | Is the target package `opens` to the caller? Is deep reflection being overused? |
| `trySetAccessible() == false` | Insufficient open/export access for the member kind; try a supported API/SPI path |
| `ServiceConfigurationError` / provider not found | `uses`/`provides`, provider class/constructor, module resolution, classpath service descriptor, packaging |
| `ClassCastException` despite identical interface names | Are host and plugin loading two copies of the SPI from different class loaders? |
| `NoClassDefFoundError` / `NoSuchMethodError` | Classpath/module path, dependency versions, mismatched public ABI between host and provider |
| `IllegalCallerException` on `ServiceLoader.load` in a named module | Has the calling module declared the appropriate `uses`? |

**Suggested debugging order:** identify the actual class/module name (`clazz.getModule()`), package, caller module, whether the module is resolved/readable, to whom the package is `exports` or `opens`, the kind of member being invoked, and the running artifact version—only then decide to modify `module-info.java`. Use `Module.isOpen(pkg, callerModule)` to check the Reflection opening scope; remember that `isExported` at runtime has broader semantics than the `exports` keyword in the descriptor when a package is open.

## 9. Misconceptions to Avoid

1. **"If there is a `public class`, any module can import it."** False in JPMS: the package containing the class must also be appropriately exported, and the caller module must read the module providing the API.
2. **"To make `ServiceLoader` work, you must export the provider class."** False: a provider module can `provides` a public implementation in a non-exported package; the hands-on example proved this.
3. **"`exports` allows reading private fields via Reflection."** False: public API access is different from deep reflection.
4. **"`opens` allows calling any internal class from source code."** False: `opens` serves runtime reflective access; compile-time imports require `exports`.
5. **"`setAccessible(true)` always bypasses module restrictions."** False: since Java 9+, strong encapsulation has rules that block access if the package is not appropriately opened.
6. **"Not finding a plugin is due to Reflection permissions."** Likely false: verify the service descriptor, module resolution, loader/layer, and valid provider first.
7. **"Class loaders or modules can block malicious code once it runs."** False: they are not an OS sandbox; code in the same process still shares many capabilities.
8. **"Once an API is public, all changes are compatible."** False: signatures, semantics, visibility, lifecycle, and binary compatibility must all be tested.

## 10. Practice Exercises

**Exercise 1 — Identify the API Surface:** Given a library consisting of `TextPlugin`, `UpperTextPlugin`, `CacheManager`, `PluginRegistry`, and `InternalParser`, propose a module descriptor that exports only the packages consumers need to compile against. Explain why implementations should not appear in public signatures.

**Exercise 2 — Reflection Permissions:** Keep the example in Section 4, and update the provider module with a qualified `opens ... to com.example.dynamic.host`. Predict `tryAccessible()` and `newInstance()`, then run to verify. Explain why doing so does not automatically turn the package into a public compile-time API.

**Exercise 3 — Remove Unnecessary Reflection:** Remove the entire `Class.forName`/constructor section in `Main`, keeping only `ServiceLoader` and invoking `TextPlugin`. Recompile/run and compare. Explain why the client is less coupled to the implementation.

**Exercise 4 — Contract Changes:** Add a new abstract method to `TextPlugin` while keeping the old binary provider. Analyze potential source and runtime errors. Propose a default method with valid semantics or a new SPI version; do not assume adding a method is always compatible.

**Exercise 5 — Choose the Mechanism:** Given three requirements—"the plugin may only run transform", "the mapper needs to read private fields of the DTO", and "external partners need to import the DTO type"—indicate when to use a public SPI, qualified `opens`, or `exports`; explain the limitations of each choice.

## Core Knowledge Summary

High-quality dynamic library design begins with a **small and stable contract**, giving the host access via a **public API/SPI**, keeping implementations hidden, and granting Reflection only the minimal permissions truly required. `exports` serves public type usage between named modules; `opens` enables deep reflection at runtime; `uses`/`provides` supports discovery via `ServiceLoader` without exporting implementations. These permissions are technical boundaries that can be inspected and tested, yet they must still be accompanied by proper version management, dependency management, and trust models.

## References

- [Java Language Specification 17 — `7.7` Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7)
- [Java SE 17 API — `java.util.ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [Java SE 17 API — `java.lang.reflect.AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Java SE 17 API — `java.lang.Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html)
- [Java SE 17 API — `java.lang.invoke.MethodHandles`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [JDK 17 `javac` Documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)