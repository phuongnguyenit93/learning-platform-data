# Access to JDK Internal APIs

The Java Development Kit (JDK) contains not only public APIs used by developers, but also many classes, packages, and modules serving **implementation details** of the JVM, compiler, standard library, and JDK tools. These components are commonly referred to as *JDK internal APIs*. In older Java systems, some applications or libraries may have accessed them directly; when adopting the Java Platform Module System (JPMS) or upgrading the JDK, that access may be blocked.

The focus of this lesson is to distinguish **module readability**, **package exports**, and **opens for reflection** when accessing internal JDK components, and to understand why `--add-exports` and `--add-opens` can resolve a specific error without turning an internal API into a stably supported API.

## 1. What Are JDK Internal APIs?

Internal APIs are classes, methods, fields, or packages used by the JDK for internal implementation work rather than serving as a stable API contract for external applications. They may involve:

- Memory management, class loading, and runtime metadata mechanisms.
- Reflection, method handles, bytecode processing, or compiler internals.
- Algorithms and data structures supporting the standard library.
- Security infrastructure, certificate formats, and JVM communication.
- Low-level optimizations that are permitted to change across JDK releases.

Package names such as `jdk.internal.*`, `sun.*`, and some `com.sun.*` packages are often signs worth checking. However, **you should not draw conclusions based on prefix alone**. For example, there are documented JDK-specific APIs, and there are also `com.sun.*` APIs exposed within a specific scope of support. Always check official documentation and the module descriptor of the JDK version in use.

Three levels can be distinguished:

| API Kind | Examples | What to Understand |
|---|---|---|
| Public Java SE API | `java.util.List`, `java.nio.ByteBuffer` | Specified and carries Java platform compatibility commitments |
| Documented JDK-specific API | Certain APIs in `jdk.jfr`, `jdk.httpserver` | Documented with JDK support policies, though not necessarily part of Java SE |
| JDK internal implementation API | `jdk.internal.misc.*`, many types in `sun.security.*` | Implementation detail; should not be treated as a stable contract |

The key point is: **"Being able to see a class in the JDK" does not mean "Applications are recommended to use that class."**

## 2. Why Could Older Applications Access Internal APIs?

Before Java 9, many applications ran on the classpath. Internal JDK packages could sometimes still be imported or accessed via reflection, even though they were not supported as public APIs. Some libraries took advantage of this to:

- Call `sun.misc.Unsafe` for low-level memory operations.
- Read or modify private fields inside JDK classes.
- Use internal certificate-handling, cryptography, or class-loader classes.
- Optimize serialization, object allocation, or proxy generation.
- Use compiler/runtime APIs outside the public contract.

These techniques typically relied on **implementation details present in a particular JDK release**. When JPMS was introduced in Java 9, access boundaries of named modules were explicitly modeled. Newer JDK releases also strengthened encapsulation of internal packages.

As a result, applications may hit errors when:

1. Upgrading from Java 8 to Java 11, 17, or a newer version.
2. Moving a library from the classpath to the module path.
3. Converting code from the unnamed module to an explicit named module.
4. Changing JDK vendors, update builds, or runtime images.
5. Running reflection frameworks under stricter JPMS boundaries.

## 3. Which Mechanisms Comprise Module Access?

JPMS controls cross-module access across multiple layers, not solely through the `public` access modifier.

**Readability:** the consuming module must read the module containing the type to be used. This relationship typically comes from `requires` in `module-info.java`.

**Exports:** the package containing the type must be exported to the consuming module for normal Java access. A `public` class in an unexported package still does not become public API for external modules.

**Opens:** a module can open a package for **deep reflection**, such as accessing private fields or methods via `setAccessible(true)`.

**Java access control:** even when module and package allow access, class/member modifiers (`public`, `protected`, package-private, `private`) remain in effect.

Example descriptor:

```java
module com.example.library {
    exports com.example.library.api;

    opens com.example.library.model
        to com.example.serializer;
}
```

This module exports the API package to modules with appropriate readability, yet opens the model package deeply only to the specific serializer module.

Another module **cannot bypass encapsulation** merely by knowing a class name, holding a reference to a `ClassLoader`, or calling `Class.forName`.

## 4. Why Is Importing a Public Class in the JDK Still Blocked?

Suppose code attempts to use a type located in an internal package:

```java
import jdk.internal.misc.Unsafe;
```

This type belongs to package `jdk.internal.misc` inside module `java.base`. Every named module implicitly reads `java.base`, yet that **does not mean** `java.base` exports every package to applications.

The compiler may report an error similar to:

```text
package jdk.internal.misc is not visible
(package jdk.internal.misc is declared in module java.base,
 which does not export it to the current module)
```

The issue is not a missing `requires java.base;`, but rather that the internal package is not exported to the module being compiled.

This exemplifies the rule:

```text
Readability to the module
          +
Appropriately exported package
          +
Accessible type and member
          =
Valid normal Java access
```

If any condition is missing, access can be blocked. The presence of `.class` files on disk does not grant access permission.

## 5. Strong Encapsulation in Modern JDKs

JPMS introduced encapsulation for packages of named modules starting in Java 9. In the initial phase, the platform included compatibility mechanisms so legacy applications could still access some internal components via reflection.

Notable milestones:

- **Java 9:** JPMS arrives. Many internal packages are not exported to normal application code; certain legacy reflection accesses are relaxed during a migration period.
- **Java 16:** strong encapsulation becomes the broader default, tightening access to internal components.
- **Java 17:** JEP 403 further reinforces encapsulation of JDK internals. Broad relaxation via `--illegal-access` is no longer a way to restore previous access behavior.

Therefore, a framework using reflection on `java.lang.String` or other JDK packages may run on older environments yet fail on JDK 17+.

This is not an accidental JDK bug; it is the result of maintaining clear API boundaries so JDK developers can evolve implementations without breaking applications that rely on supported APIs.

## 6. --add-exports: An Exception for Normal API Access

Sometimes a legacy project cannot immediately eliminate an internal API import. The `--add-exports` option can grant additional access to a package belonging to a source module.

Syntax:

```text
--add-exports=<source-module>/<package>=<target-module>
```

Where:

- `source-module`: the module owning the package, such as `java.base`.
- `package`: the internal package to access, such as `jdk.internal.misc`.
- `target-module`: the module permitted access, such as `com.example.internaldemo`.

For code on the classpath, the special target is `ALL-UNNAMED`, which grants permission to unnamed modules.

**Important:** `--add-exports` opens access to eligible types and members under normal access modifiers, yet **does not automatically grant access to private members via deep reflection**.

### 6.1. Named Module Example

Create the structure:

```text
internal-demo/
└── src/
    ├── module-info.java
    └── com/example/internaldemo/Main.java
```

`module-info.java`:

```java
module com.example.internaldemo {
}
```

`Main.java`:

```java
package com.example.internaldemo;

import jdk.internal.misc.Unsafe;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Unsafe.class.getName());
    }
}
```

This code **only illustrates access rules** and does not invoke unsafe memory primitives. Do not use this example as a production dependency.

Try compiling normally:

```shell
javac -d out src/module-info.java     src/com/example/internaldemo/Main.java
```

On JDKs with strong encapsulation, the compiler blocks the import because the package is not exported.

If the project must have a migration exception, it can compile with:

```shell
javac --add-exports=java.base/jdk.internal.misc=com.example.internaldemo     -d out     src/module-info.java     src/com/example/internaldemo/Main.java
```

Run with the matching exception:

```shell
java --module-path out     --add-exports=java.base/jdk.internal.misc=com.example.internaldemo     -m com.example.internaldemo/com.example.internaldemo.Main
```

Expected output on JDKs containing this type:

```text
jdk.internal.misc.Unsafe
```

If exports are opened only at compile time without granting the corresponding access at runtime, bytecode can still be blocked when trying to access classes or members in that package. Both the build environment and launcher must be explicitly controlled.

Note: internal APIs can change or be removed across JDK releases; this example is not a guarantee that the specific class or member will exist in every future JDK.

### 6.2. Classpath Code Example

An application without `module-info.java` normally runs in the unnamed module. You may see usage such as:

```shell
javac --add-exports=java.base/jdk.internal.misc=ALL-UNNAMED     -d out src/com/example/internaldemo/Main.java
```

And:

```shell
java --add-exports=java.base/jdk.internal.misc=ALL-UNNAMED     --class-path out     com.example.internaldemo.Main
```

`ALL-UNNAMED` opens the package to unnamed modules, which does **not** mean all named modules. If you migrate to a named module, specify the appropriate target module name.

## 7. --add-opens: An Exception for Deep Reflection

Another common access failure is reflecting on non-public members. Example:

```java
import java.lang.reflect.Field;

public final class ReflectionDemo {
    public static void main(String[] args) throws Exception {
        Field field = String.class.getDeclaredField("value");
        field.setAccessible(true);
        System.out.println(field.getType());
    }
}
```

On modern JDKs, `setAccessible(true)` can throw `InaccessibleObjectException` because package `java.lang` in `java.base` is not open for deep reflection from the calling module.

The message may look similar to:

```text
java.lang.reflect.InaccessibleObjectException:
module java.base does not "opens java.lang"
to unnamed module ...
```

If legacy code strictly requires a temporary exception, you can configure:

```shell
java --add-opens=java.base/java.lang=ALL-UNNAMED     --class-path out ReflectionDemo
```

General syntax:

```text
--add-opens=<source-module>/<package>=<target-module>
```

`--add-opens` is for **runtime deep reflection**; it does not automatically make `import jdk.internal.misc.Unsafe;` valid at compile time. Do not use `--add-opens` in place of `--add-exports` when the error involves normal Java access.

For a named module, specify the exact module requiring reflection:

```shell
java --add-opens=java.base/java.lang=com.example.reflector     --module-path mods     -m com.example.reflector/com.example.reflector.Main
```

Do not broadly open JDK packages in production just because an old framework still depends on private fields. The sustainable path is to upgrade the framework or refactor to use public APIs.

## 8. Distinguishing requires, add-reads, add-exports, and add-opens

This is one of the easiest areas to mix up when fixing module access errors.

| Mechanism | What does it change? | What can it not do? |
|---|---|---|
| `requires` | Declares a module dependency/readability | Does not export another module's internal packages |
| `--add-reads` | Adds readability for a single build/run | Does not grant access to unexported packages |
| `exports` | Owning module exposes a package via its descriptor | Does not automatically grant deep reflection on private members |
| `--add-exports` | Adds exports for a target module | Does not automatically open deep reflection |
| `opens` | Owning module opens a package for reflection | Not a public API contract |
| `--add-opens` | Opens a package for deep reflection at runtime | Does not make the package an exported API at compile time |

Examples:

- Error "module X does not read module Y": check `requires` or `--add-reads`.
- Error "module Y does not export package P to X": check `exports` or an `--add-exports` exception.
- Error "module Y does not opens package P to X": check `opens` or `--add-opens`.
- `NoClassDefFoundError` because a class was removed: adding access flags cannot restore a class no longer present in the JDK.

**Access flags do not replace one another.** Adding multiple flags "just to try" without reading the error message can over-grant permissions and hide internal dependencies.

## 9. When Is --add-exports Needed for Both javac and java?

If source code directly imports a non-exported internal class, the compiler needs permission to read the package to compile. If the resulting bytecode continues to reference that class, the runtime also needs the matching permission to link and execute.

A two-step example:

```shell
javac --add-exports=java.base/jdk.internal.misc=com.example.internaldemo     -d out src/module-info.java src/com/example/internaldemo/Main.java
```

```shell
java --add-exports=java.base/jdk.internal.misc=com.example.internaldemo     -p out -m com.example.internaldemo/com.example.internaldemo.Main
```

If a framework only uses reflection at runtime, `--add-opens` is usually needed at runtime without needing `--add-exports` at compile time.

In Maven/Gradle, the compiler, test launcher, and application launcher can use **different sets of JVM arguments**. Putting a flag in the build step does not mean it is automatically forwarded to production runtime. Likewise, configuring a flag in an IDE while forgetting CI can cause tests to pass only on a developer's machine.

Certain combinations of `javac --release` and opening exports on system modules may be restricted by the compiler; do not assume these options work across all cross-compilation modes. Verify against the target JDK and prioritize removing internal dependencies instead of keeping permanent build flags.

## 10. Internal APIs and the jdk.unsupported Module

One special case to understand separately is `jdk.unsupported`. This module is used by the JDK to provide certain APIs outside the standard Java SE API set, mainly for compatibility with legacy applications and libraries.

A well-known example is `sun.misc.Unsafe`. On some JDKs, `jdk.unsupported` exports the `sun.misc` package so legacy code can continue accessing this type under the implementation's policy.

You can inspect it:

```shell
java --describe-module jdk.unsupported
```

If an application genuinely uses an API in this module, a named module may need to declare the corresponding dependency:

```java
module com.example.legacy {
    requires jdk.unsupported;
}
```

However, distinguish carefully:

- `jdk.unsupported` shows that the JDK provider offers a compatibility mechanism for certain legacy APIs.
- Being able to import from an exported package **does not turn the API into a public Java SE API**.
- Do not infer that `jdk.internal.misc.Unsafe` and `sun.misc.Unsafe` have the same access policy.
- Classes/fields/methods in this group still carry compatibility risks and need a replacement plan.

If `jdk.unsupported` is not included in a stripped-down runtime image, code depending on it may fail to run. Therefore, do not treat availability on a full JDK as a guarantee for every runtime environment.

## 11. Qualified Exports of JDK Modules

A JDK module can export a package to **specific other JDK modules**, rather than exporting it to all modules.

Conceptual descriptor example:

```java
module some.jdk.module {
    exports some.internal.package to another.jdk.module;
}
```

Here `another.jdk.module` is allowed to use the package's public types within the defined boundary, whereas arbitrary application modules do not have that right.

You can run:

```shell
java --describe-module java.base
```

to inspect the base module's descriptor, including exports/opens directives printed in the tool's format.

This explains why a package can be used inside JDK source code yet cannot be directly imported by applications. **JDK internals shared among JDK modules are not an invitation for application code to use them.**

## 12. Identifying the Module Owning an Internal API

If you see an import like:

```java
import sun.security.x509.X500Name;
```

start by identifying which module owns the package in the target JDK, for instance via JDK documentation, `jdeps`, or JDK module descriptors.

A general workflow:

1. Record the fully qualified class name.
2. Identify the package, such as `sun.security.x509`.
3. Identify the module owning that package on the running JDK.
4. Check whether the package is exported to the consuming module.
5. Check the access kind: import/static linkage or deep reflection.
6. Check whether that API is documented/supported for your use case.
7. If it is an internal API, prioritize an alternative solution before considering flags.

Do not deduce the owning module solely from a package prefix. Some legacy packages have moved or changed across JDK releases.

## 13. Detecting JDK Internal APIs with jdeps

The JDK provides the `jdeps` tool to analyze bytecode dependencies. When migrating from the classpath to the module path, one of the most useful commands is:

```shell
jdeps --jdk-internals build/libs/application.jar
```

The `--jdk-internals` option focuses on dependencies targeting JDK internal APIs that the tool can detect from bytecode.

If the application needs external dependencies for analysis, supply the classpath:

```shell
jdeps --jdk-internals     --class-path "libs/*"     build/libs/application.jar
```

You can analyze deeper dependencies:

```shell
jdeps --jdk-internals     --recursive     --class-path "libs/*"     build/classes
```

The output typically helps identify:

- Which application or library classes depend on internal APIs.
- Which internal packages/classes are being used.
- Whether the dependency lies in your own code or a third-party library.
- Possible replacement API suggestions, when the tool has matching information.

**Limitation:** `jdeps` analyzes bytecode and cannot fully see accesses constructed dynamically from strings, reflection, JNI, code generation, or plugins loaded in the future. Therefore, receiving no warnings from `jdeps` is not conclusive proof that an application has no remaining internal dependencies.

## 14. Finding Reflection into JDK Components

Reflection can make internal dependencies harder to spot than direct imports.

Example:

```java
Class<?> type = Class.forName("java.lang.String");
var field = type.getDeclaredField("value");
field.setAccessible(true);
```

Indicators to search for in source code:

- `Class.forName(...)`.
- `getDeclaredField(...)`, `getDeclaredMethod(...)`, `getDeclaredConstructor(...)`.
- `setAccessible(true)` or `trySetAccessible()`.
- `MethodHandles.privateLookupIn(...)`.
- `Unsafe` or wrapper libraries around low-level memory access.
- Serialization/ORM/DI frameworks using private-field injection.

Do not search only for internal imports. A library might assemble `sun.*` or `jdk.internal.*` names from strings, use reflection, and leave no static imports visible.

If a framework causes errors, upgrading the framework version is usually less risky than manually adding `--add-opens` for multiple JDK packages.

## 15. Distinguishing Common Errors

### 15.1. Compile Error: package is not visible

Example:

```text
package jdk.internal.misc is not visible
```

Common cause: the package belongs to a named module and is not exported to the module being compiled.

Actions to take:

1. Identify the module owning the package.
2. Check whether a public replacement API exists.
3. Only when migration is unavoidable, consider `--add-exports` for the exact target module.
4. Document clearly where compiler flags and runtime flags are configured.

### 15.2. Runtime IllegalAccessError

The application may have compiled with relaxed access settings yet lacked corresponding permissions at runtime. During bytecode linking or execution, the JVM may throw `IllegalAccessError`.

Verify **both the actual javac command and java command**, especially when commands come from an IDE, CI, Maven Surefire, or Gradle.

### 15.3. Runtime InaccessibleObjectException

Typically occurs when a framework performs deep reflection on an unopened package:

```text
java.lang.reflect.InaccessibleObjectException:
module java.base does not "opens java.lang"
```

Inspect the stack trace to see which module is attempting reflection; do not assume the target is `ALL-UNNAMED` by default. If the framework runs inside a named module, `--add-opens` may need to specify that module's name.

### 15.4. ClassNotFoundException / NoClassDefFoundError

The class may no longer exist in the newer JDK, may have been relocated, or the runtime image may omit the required module. In such cases, **opening access does not restore missing bytecode**.

Verify whether the class actually exists in the target JDK rather than only tweaking module flags.

### 15.5. NoSuchMethodError / NoSuchFieldError

This is usually a binary compatibility symptom: bytecode references a method/field that no longer has the expected signature. With internal APIs, this risk is high because implementations can change.

`--add-exports` or `--add-opens` cannot fix a changed signature.

## 16. Supported APIs to Replace Internal APIs

When an internal dependency is discovered, look for public or documented APIs that solve the **actual underlying need** instead of searching for a class with a similar name.

| Need | APIs to Consider |
|---|---|
| Base64 encoding/decoding | `java.util.Base64` |
| Atomic operations and synchronization | `java.util.concurrent.atomic` |
| Variable access with appropriate memory ordering | `java.lang.invoke.VarHandle` |
| Binary data, buffers | `java.nio.ByteBuffer`, NIO |
| Resource cleanup management | `java.lang.ref.Cleaner` |
| Stack inspection | `java.lang.StackWalker` |
| Process information | `java.lang.ProcessHandle` |
| Native memory and native calls | Foreign Function & Memory API if supported by target JDK |
| Key/security operations | Java Security/JCA/JCE APIs and supported libraries |
| Logging, metrics, JVM monitoring | `java.lang.management`, JFR, or documented APIs |

There is no one-to-one replacement rule for every internal API. A library that previously called `Unsafe` for low-level data manipulation may need redesigning with `VarHandle`, `ByteBuffer`, atomic classes, or an appropriate abstraction.

For APIs standardized in newer JDKs but absent in older JDKs, consider the minimum Java version the project commits to support.

## 17. Migration Example: Removing a Dependency on an Old Encoder

Suppose legacy code used an internal API or custom implementation to perform Base64 encoding. You should not keep depending on an internal class just to encode a byte array.

Use the public API:

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class Encoder {
    public static String encode(String input) {
        byte[] bytes = input.getBytes(StandardCharsets.UTF_8);
        return Base64.getEncoder().encodeToString(bytes);
    }

    public static String decode(String encoded) {
        byte[] bytes = Base64.getDecoder().decode(encoded);
        return new String(bytes, StandardCharsets.UTF_8);
    }
}
```

Test example:

```java
String encoded = Encoder.encode("Java JPMS");
System.out.println(encoded);
System.out.println(Encoder.decode(encoded));
```

Advantages:

- No `--add-exports` required.
- No dependency on internal packages.
- Easy to run inside a named module because `java.base` is implicitly read.
- Documented API and behavior.

This illustrates the migration principle: **replace the actual business need**, rather than "preserving the old call site at all costs".

## 18. When Internal Dependencies Come from Third-Party Libraries

Many errors do not originate in your application's own source code. They come from JSON libraries, ORMs, bytecode manipulation, instrumentation, test frameworks, or networking libraries chosen years ago.

Recommended priority workflow:

1. Use `jdeps --jdk-internals` or stack traces to identify the offending artifact/class.
2. Check the library version and newer releases.
3. Read the library's release notes and Java compatibility documentation.
4. Upgrade to a version that uses supported APIs, if available.
5. Run tests on the target JDK, including integration tests involving reflection.
6. Keep `--add-exports`/`--add-opens` only as a documented workaround with a clear timeline, scope, and owner.

Do not copy internal JDK classes into your application packages to evade the module system. That usually creates additional legal/technical, binary compatibility, and maintenance risks.

## 19. Checking Module Access at Runtime

Several methods on `java.lang.Module` help diagnose cross-module access permissions.

Example:

```java
Module base = Object.class.getModule();
Module app = MyApplication.class.getModule();

System.out.println(base.getName());
System.out.println(app.getName());

System.out.println(app.canRead(base));
System.out.println(base.isExported("java.lang", app));
System.out.println(base.isExported("jdk.internal.misc", app));
System.out.println(base.isOpen("java.lang", app));
```

The outputs reflect the configuration and access adjustments in effect at runtime. For a typical application:

- App can read `java.base`.
- Package `java.lang` is broadly exported.
- Package `jdk.internal.misc` is not broadly exported as application API.
- `java.lang` is normally not open for arbitrary deep reflection under strong encapsulation.

If the launcher passes `--add-exports` or `--add-opens`, the granted access permissions can change the corresponding results.

However, even if `Module.isExported` returns `true`, that only answers the **module access** question; it does not guarantee the API is supported or preserved in the future.

## 20. Access Flags Are Neither Security Boundaries Nor Long-Term Compatibility Guarantees

You must understand two distinct risks:

**Compatibility risk:** internal APIs can be renamed, have signatures altered, change behavior, or disappear. Flags do not prevent any of that.

**Over-broad access risk:** an option such as `--add-opens java.base/java.lang=ALL-UNNAMED` opens the package to every unnamed module in the process. This can be much wider than what a single library actually needs.

Guidelines:

- Use a specific target module name instead of `ALL-UNNAMED` when code resides in a named module.
- Open only the exact package needed, not batches of unrelated JDK packages.
- Separate compiler flags, test flags, and production runtime flags.
- Document the purpose of every flag in deployment documentation.
- Have tests verifying the program runs after removing a workaround.
- Treat flags as technical debt to be retired, not as an API contract.

In particular, **custom class loaders, signed JARs, automatic modules, or reflective class loading do not create a sandbox**. If an application processes untrusted code, you need an appropriate isolation model beyond JPMS access options.

## 21. Workflow for Handling Access Errors to JDK Internal APIs

When upgrading the JDK and hitting errors, you can follow this workflow:

1. **Record the environment:** JDK version, vendor, launch command, module path/classpath, build tool.
2. **Capture the stack trace or compiler message:** extract the full source module, package, and target module.
3. **Identify the failing API:** direct import, bytecode linkage, or reflection.
4. **Verify the owning module:** use `java --describe-module <module>` and target JDK information.
5. **Scan dependencies:** run `jdeps --jdk-internals` on the application artifacts and relevant libraries.
6. **Find replacement APIs:** prefer Java SE APIs or documented JDK APIs.
7. **Upgrade libraries:** if the internal dependency comes from a third-party library.
8. **Use scoped workarounds if needed:** specify the exact `--add-exports` or `--add-opens`, distinguishing compile time and runtime.
9. **Test across layers:** unit tests, integration tests, reflection/serialization/ServiceLoader, startup, and packaging.
10. **Remove workarounds:** once your code or libraries no longer depend on internal APIs.

Example tracking table:

| Component | Internal API | Access Type | Temporary Workaround | Removal Plan |
|---|---|---|---|---|
| Legacy serializer | Internal JDK package | Reflection | Scoped `--add-opens` | Upgrade library |
| Old runtime helper | `jdk.internal.misc` | Import/linkage | Scoped `--add-exports` | Migrate to public API |
| Low-level code | `sun.misc.Unsafe` | Direct API | Depend on `jdk.unsupported` | Refactor with `VarHandle` or another API |

Do not apply a "for the entire JDK" workaround without a dependency inventory and migration plan.

## 22. Pre-Release Checklist

- [ ] Inspected all relevant JARs with `jdeps --jdk-internals`.
- [ ] Searched for reflection calls and string-based class names that `jdeps` may miss.
- [ ] Identified the exact module/package/target experiencing access failures.
- [ ] Distinguished whether `requires`, `exports`, or `opens` is needed.
- [ ] Preferred public APIs over internal APIs.
- [ ] Upgraded third-party libraries where compatible versions exist.
- [ ] Any remaining `--add-exports` and `--add-opens` flags have a clear justification and scope.
- [ ] Compiler, test runtime, CI, and production do not use conflicting configurations.
- [ ] Tested on the exact target JDK and distributed runtime image.
- [ ] Have a plan to remove migration flags in subsequent releases.

## Conclusion

**Access to JDK internal APIs** is a special case of module access: a class can exist in the JDK and even carry the `public` modifier, yet its package is not exported to applications. Similarly, reflection into private fields in JDK packages can be rejected if the package is not open.

`--add-exports` adds normal Java access to a package, whereas `--add-opens` grants runtime deep reflection permission. They are scoped compatibility tools, **not** ways to turn internal APIs into stable APIs. Strong encapsulation changes from Java 9 through Java 17 cause previously working internal dependencies to surface as errors during upgrades.

The sustainable solution is to audit with `jdeps`, read stack traces and module descriptors carefully, upgrade fixed libraries, and migrate to documented Java/JDK APIs. When an access exception cannot yet be removed, keep it minimal, consistent between build and runtime, and plan its removal during migration.