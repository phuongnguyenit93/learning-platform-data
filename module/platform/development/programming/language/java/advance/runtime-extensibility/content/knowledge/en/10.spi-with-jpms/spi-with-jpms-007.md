# Distinguishing Module Readability, `exports`, and `opens` for Reflective Access

In the **Java Platform Module System (JPMS)**, the fact that a class exists in another module does not mean an application has permission to call that class, and even less does it mean reflection can read every private field or invoke private constructors. To design SPIs, plugin-integrating frameworks, and module-loading systems properly, three questions must be distinguished:

1. **Readability:** Does the calling module *read* the module containing the target type?
2. **Exports:** Does the package containing the type *publish its API* to the calling module?
3. **Opens:** Does the package *permit deep reflective access* from the module performing reflection?

These three factors are related, yet they solve different problems. A `requires` clause does not automatically export packages. An `exports` clause does not automatically open private fields to reflection. An `opens` clause does not turn a package into an API that can be imported at compile time.

## 1. Readability Is a Relationship Between Two Modules

Suppose there are two named modules:

~~~text
demo.consumer  --requires-->  demo.library
~~~

In **src/demo.consumer/module-info.java**:

~~~java
module demo.consumer {
    requires demo.library;
}
~~~

When the module graph is resolved, module `demo.consumer` **reads** `demo.library`. This readability relationship allows the compiler and runtime to evaluate permission to use types from `demo.library`, though package accessibility and Java language access rules such as `public`/`private` must still be satisfied.

For instance, if `demo.library` **does not export** the `demo.library.internal` package, adding `requires demo.library` in the consumer is still not enough to write:

~~~java
// Compile-error illustration: internal package is not exported.
import demo.library.internal.Secret;
~~~

This is an **illustrative line forbidden by the module boundary**, not source code used in the runnable program in Section 5.

Key points to remember:

- `requires X` expresses the current module's dependency on `X` and creates a module read edge in JPMS; a named module reads `java.base` by default without declaring it.
- `requires transitive X` propagates readability of `X` to other modules that read the module declaring `requires transitive`; it **does not automatically export** packages in `X`.
- `requires static X` is a compile-time dependency that is optional at runtime; it likewise does not replace `exports`/`opens`.
- `Module.canRead(other)` lets you inspect actual readability at runtime. Relationships can be added dynamically or by the launcher, so distinguish `module-info.java` from the runtime graph.
- The fact that one module can read another does not prove that classes in a package on the other side are accessible from source code.

## 2. `exports` Publishes a Package as a Normal API

Example in **src/demo.library/module-info.java**:

~~~java
module demo.library {
    exports demo.library.api;
}
~~~

The `exports demo.library.api` directive makes **accessible public types** in that package—along with their `public`/`protected` members under Java access rules—part of the API for eligible modules.

For code in `demo.consumer` to use a public class in `demo.library.api` directly, all three conditions are needed simultaneously:

- `demo.consumer` reads `demo.library` (here via `requires demo.library`);
- `demo.library` exports `demo.library.api` to `demo.consumer`;
- the class and member have appropriate Java access modifiers.

A public class in an **unexported package** does not automatically become public API outside the module. And `exports` does not turn private fields into public fields: `private` members remain subject to normal access checks.

You can restrict `exports` to a list of target modules:

~~~java
module demo.library {
    exports demo.library.api to demo.consumer;
}
~~~

This is a **qualified export**: it exposes the package to `demo.consumer` without exposing it to all modules. It does not mean `demo.consumer` automatically reads `demo.library`; the consumer still needs valid readability when using the API in source code.

### Public Reflection Through an Exported Package

If a package is already exported to the reflecting module, Java reflection can typically invoke **public constructors/methods on public classes** under normal access rules. For example:

~~~java
Class<?> type = Class.forName("demo.library.api.PublicApi");
Object object = type.getConstructor().newInstance();
Object result = type.getMethod("greet").invoke(object);
~~~

This is an **illustrative snippet placed inside a method that handles checked exceptions**, not a standalone program. It assumes `PublicApi` has a public no-arg constructor and a public `greet()` method. It uses only public members; calling `setAccessible(true)` is unnecessary.

Conversely, `exports` is **not sufficient** to access private constructors, private fields, or private methods of classes in that package from another module. Switching to reflection does not make private access checks disappear.

## 3. `opens` Enables Deep Reflection Without Exposing a Compile-Time API

The `opens` directive differs from `exports` in its goal:

~~~java
module demo.library {
    exports demo.library.api;
    opens demo.library.internal to demo.consumer;
}
~~~

In this example:

- The `demo.library.api` package is the public API for normal Java code.
- The `demo.library.internal` package still cannot be directly imported by `demo.consumer` at compile time, because this package is **not exported in the descriptor**.
- However, code **performing reflection inside `demo.consumer`** can perform deep reflective access on members of classes in `demo.library.internal`, including private members, through the appropriate reflection APIs.

An `opens` directive can be written without `to` to open the package to all modules, or written as `opens package to module1,module2` to restrict access strictly to the modules that need reflection. Where a package genuinely must serve as a compile-time API **and** allow private reflection, **both `exports` and `opens`** can be declared for it.

There is also syntax to open an entire module:

~~~java
open module demo.library {
    exports demo.library.api;
}
~~~

Declaring an `open module` allows **every package** in the module to undergo deep reflection at runtime. This is a broad choice that should be weighed carefully because it exposes many implementation details. Individual `opens` directives are not allowed inside an `open module` because the entire module is already open.

### `exports` Is Not Synonymous with `opens`

| Provider Module Configuration | Direct Import of Public API from a Readable Module | Reflecting Public Members Under Normal Access | Deep Reflection into Private Members from Another Module |
| --- | --- | --- | --- |
| Neither `exports` nor `opens` on package | No | Access to members is not granted | No |
| `exports package` | Yes | Yes, for eligible public types/members | Not via `exports` alone |
| `opens package` | Not via `opens` alone | Yes at runtime under reflection rules | Yes, for modules it is opened to |
| Both `exports` and `opens` on package | Yes | Yes | Yes, for modules it is opened to |
| `open module` | Only exported packages are compile-time APIs | Opened packages support runtime reflection | Yes, for packages in the module |

In the *direct import* column, the consumer must also read the providing module and the class/member must have appropriate Java visibility. In the reflection columns, distinguish **knowing a class name**, **reading class metadata**, **invoking public members**, and **suppressing access checks to invoke private members**: these are not the same permission.

One important note: `exports` concerns exposing **public/protected** elements under Java visibility conditions; it does not turn `protected` or package-private elements into `public` for arbitrary external code.

## 4. Reflection Has Its Own Rules: Finding a Class Does Not Mean Permission to Access It

Java reflection can look up a class by name and return a `Class` object, or retrieve member lists via `getDeclaredFields`/`getDeclaredMethods`, even when those members are **not accessible**. Discovering a field's name does not prove permission to read the field's value.

Two commonly misunderstood APIs:

- `AccessibleObject.setAccessible(true)` **attempts** to bypass default access checks. On JDK 17, if the module has not opened the relevant package and no other condition permits it, the call can throw `InaccessibleObjectException`.
- `AccessibleObject.trySetAccessible()` makes the same attempt, but when denied due to module rules it can return `false` instead of throwing `InaccessibleObjectException`. It can still throw other errors under certain conditions, so do not treat it as a "never throws" method.

A call such as:

~~~java
Field field = PublicApi.class.getDeclaredField("token");
boolean allowed = field.trySetAccessible();
~~~

only reports whether access checks can be suppressed **for that specific field** at the time of the call, not whether every member in the module has been opened.

### Readability and Reflection: An Exception to Distinguish

In Java core reflection, reflective access checks have rules that **assume readability** in certain cases; therefore, you cannot take a successful `Class.forName` or `Method.invoke` call as proof that the calling module has a static `requires` read edge.

Conversely, when compiling named type references from another module, the compiler checks both readability and `exports`. When evaluating the actual module graph, use `Module.canRead()` for readability; when evaluating private reflection permission, use `Module.isOpen(packageName, targetModule)` and an actual access attempt. These are distinct observations.

With `MethodHandles.privateLookupIn`, opening the package is also critical, and there are separate lookup/readability conditions; do not infer that `privateLookupIn` and core reflection always share the exact same set of preconditions.

## 5. Runnable Example: One Modular Library and One Modular Consumer

This example uses **JDK 17+**, compiled with `--release 17`, with no dependencies outside the JDK. It illustrates one exported public API package, one unexported internal package, and two private fields that the host attempts to read via reflection.

Initially `demo.library` **opens no packages**. We run it three times: default, opening `internal` alone, and then opening both `internal` and `api`. In this way, only **launcher flags** change without modifying source code or bytecode.

### 5.1. Directory Structure

~~~text
src/
  demo.library/
    module-info.java
    demo/library/api/PublicApi.java
    demo/library/internal/Secret.java
  demo.consumer/
    module-info.java
    demo/consumer/Main.java

mods/
  demo.library/          # javac output
  demo.consumer/         # javac output
~~~

### 5.2. Library `module-info.java`

**src/demo.library/module-info.java**

~~~java
module demo.library {
    exports demo.library.api;
}
~~~

Only the `api` package is exported. The `internal` package remains closed to code in other modules; there is no `opens` in the initial version.

### 5.3. Two Classes in Two Packages

**src/demo.library/demo/library/api/PublicApi.java**

~~~java
package demo.library.api;

public final class PublicApi {
    private final String token = "api-private";

    public String greet() {
        return "HELLO";
    }
}
~~~

**src/demo.library/demo/library/internal/Secret.java**

~~~java
package demo.library.internal;

public final class Secret {
    private final String token = "internal-private";

    private Secret() {}
}
~~~

`PublicApi` is a public class in an exported package, with an implicit public constructor and a private field. `Secret` resides in an unexported package, with a private constructor and a private field. Outside the module, direct source access to `Secret` is disallowed by JPMS.

### 5.4. Consumer Declaring Readability

**src/demo.consumer/module-info.java**

~~~java
module demo.consumer {
    requires demo.library;
}
~~~

Through `requires`, the consumer reads the library; through `exports`, the consumer can import `PublicApi`. Without `requires`, consumer code using `PublicApi` directly will not compile in a normal named-module setup.

### 5.5. Consumer Attempting Direct Calls and Reflection

**src/demo.consumer/demo/consumer/Main.java**

~~~java
package demo.consumer;

import demo.library.api.PublicApi;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

public final class Main {
    public static void main(String[] args) throws Exception {
        Module caller = Main.class.getModule();
        Module lib = PublicApi.class.getModule();

        System.out.println("reads library: " + caller.canRead(lib));
        System.out.println("api exported: " +
                lib.isExported("demo.library.api", caller));
        System.out.println("internal exported: " +
                lib.isExported("demo.library.internal", caller));
        System.out.println("internal open: " +
                lib.isOpen("demo.library.internal", caller));
        System.out.println("direct public call: " +
                new PublicApi().greet());

        Field apiField = PublicApi.class.getDeclaredField("token");
        boolean apiAccess = apiField.trySetAccessible();
        System.out.println("api private accessible: " + apiAccess);
        if (apiAccess) {
            System.out.println("api token: " +
                    apiField.get(new PublicApi()));
        }

        Class<?> hiddenType =
                Class.forName("demo.library.internal.Secret");
        Constructor<?> ctor = hiddenType.getDeclaredConstructor();
        boolean ctorAccess = ctor.trySetAccessible();
        System.out.println("internal ctor accessible: " + ctorAccess);
        if (ctorAccess) {
            Object instance = ctor.newInstance();
            Field field = hiddenType.getDeclaredField("token");
            boolean fieldAccess = field.trySetAccessible();
            System.out.println("internal field accessible: " + fieldAccess);
            if (fieldAccess) {
                System.out.println("internal token: " +
                        field.get(instance));
            }
        }
    }
}
~~~

The code intentionally uses `Class.forName` with `Secret`'s name as a string. Because the module is resolved in the example and the class loader can locate `Secret`, `Class.forName` returns the `Class` object. Yet to invoke the private constructor, `Main` still needs reflection permission. `trySetAccessible` returns `false` when permission is denied, so the application avoids calling `newInstance` when unauthorized.

### 5.6. Compiling with PowerShell

Run from the directory containing `src` (Windows PowerShell, JDK 17 or newer):

~~~powershell
New-Item -ItemType Directory -Force -Path 'mods/demo.library','mods/demo.consumer' | Out-Null

javac --release 17 -encoding UTF-8 -d mods/demo.library src/demo.library/module-info.java src/demo.library/demo/library/api/PublicApi.java src/demo.library/demo/library/internal/Secret.java

javac --release 17 -encoding UTF-8 --module-path mods -d mods/demo.consumer src/demo.consumer/module-info.java src/demo.consumer/demo/consumer/Main.java
~~~

Each module is compiled into its own directory under `mods`. For a modular application, `--module-path` is where `javac`/`java` locate compiled modules. The second line needs `demo.library` on the module path to resolve `requires demo.library` and the `PublicApi` import.

### 5.7. Default Run: Deep Reflection Not Yet Opened

~~~powershell
java --module-path mods -m demo.consumer/demo.consumer.Main
~~~

**Exact stdout:**

~~~text
reads library: true
api exported: true
internal exported: false
internal open: false
direct public call: HELLO
api private accessible: false
internal ctor accessible: false
~~~

Point-by-point explanation:

- Consumer reads library because of `requires demo.library`.
- `api exported: true` because the library exports `demo.library.api`.
- `internal exported: false` and `internal open: false` because the package is neither exported nor opened.
- Java code calls `PublicApi.greet()` directly and succeeds.
- `PublicApi`'s private `token` is **not** deeply accessible solely because the `api` package is exported.
- `Class.forName` can find `Secret`, but the consumer cannot invoke its private constructor while the `internal` package remains closed.

### 5.8. Opening Only the `internal` Package to the Consumer at Runtime

~~~powershell
java --module-path mods --add-opens demo.library/demo.library.internal=demo.consumer -m demo.consumer/demo.consumer.Main
~~~

**Exact stdout:**

~~~text
reads library: true
api exported: true
internal exported: true
internal open: true
direct public call: HELLO
api private accessible: false
internal ctor accessible: true
internal field accessible: true
internal token: internal-private
~~~

Now `Main` is permitted to invoke the private constructor and read the private field of `Secret`. **Only the `internal` package is opened**, so the private `token` in `api` remains inaccessible.

One detail that often surprises developers: after `--add-opens`, **`internal exported: true`** even though `module-info.java` still lacks `exports demo.library.internal`. This is not a bug in the example. Per the `java.lang.Module` documentation, **a package that is open to a target module is also considered exported to that module at runtime**, so `Module.isExported(package, target)` returns `true`. That does **not** mean an `opens` directive has turned into a compile-time `exports` in `module-info.java` source.

Therefore, if you need to check **original static declarations**, read `ModuleDescriptor.exports()`/`opens()`; if you need to check **current runtime permissions**, inspect `Module.isExported()`/`isOpen()`. The two sources can differ due to launcher flags or dynamic module graph updates.

### 5.9. Opening Both `api` and `internal` to Verify Private Reflection

~~~powershell
java --module-path mods --add-opens demo.library/demo.library.api=demo.consumer --add-opens demo.library/demo.library.internal=demo.consumer -m demo.consumer/demo.consumer.Main
~~~

**Exact stdout:**

~~~text
reads library: true
api exported: true
internal exported: true
internal open: true
direct public call: HELLO
api private accessible: true
api token: api-private
internal ctor accessible: true
internal field accessible: true
internal token: internal-private
~~~

Compared to the default run, this time `PublicApi`'s private field is also accessible. The change comes from `--add-opens demo.library/demo.library.api=demo.consumer`; having `api` exported from the beginning was **not enough** for deep reflection.

All three commands and stdout outputs above were verified using `javac --release 17` and executed on a newer JDK. The example compiles and runs on its own without third-party libraries.

## 6. Using `exports` and `opens` in SPI/Plugin Design

For plugins using JPMS, clearly separate **the stable contract** from **internal implementations**:

~~~text
Host module                   Plugin implementation module
    |                                      |
    | requires demo.plugin.api             | requires demo.plugin.api
    v                                      v
            demo.plugin.api
            exports demo.plugin.spi

The host can locate providers via ServiceLoader and the shared interface.
Plugin implementation does not need to export all internal packages.
~~~

A typical set of declarations for named modules using a service is:

**Contract module:**

~~~java
module demo.plugin.api {
    exports demo.plugin.spi;
}
~~~

**Plugin provider module:**

~~~java
module demo.plugin.provider {
    requires demo.plugin.api;
    provides demo.plugin.spi.Plugin with
            demo.plugin.internal.PluginImpl;
}
~~~

**Host module:**

~~~java
module demo.plugin.host {
    requires demo.plugin.api;
    uses demo.plugin.spi.Plugin;
}
~~~

This is an **illustration of `module-info.java` across three separate modules**; an actual `Plugin` interface and `PluginImpl` class are needed to compile. Key point: when a provider is declared via `provides ... with ...` on the module path, **`ServiceLoader` has a JPMS mechanism to locate and instantiate the provider**, without requiring the implementation package to be exported or opened to the host just for service discovery.

If the host also wants to reflect directly into private fields/constructors of a plugin, that is a **separate** requirement from `ServiceLoader` discovery. In that case, consider an API with public configuration methods, or open the package strictly to the module actually performing reflection.

Do not open an entire module containing plugins just because of a reflection error. Opening too broadly gives the host/framework permission to reflect deeply into structures not designed as contracts, increasing coupling and refactoring risk.

### Which Module Actually Needs to Be Opened?

Identify **the module containing the code directly performing the access check**. If the host calls a framework library that uses reflection, the module that needs to be opened to is usually **the framework's module**—such as a serializer or persistence framework—rather than solely the host module. Qualified `opens` declarations should target the exact module performing reflection.

Example:

~~~java
module demo.library {
    exports demo.library.api;
    opens demo.library.model to demo.serializer;
}
~~~

When compiling `module-info.java` with a qualified target, build tools may warn if the target module is not visible; ensure the module path and build environment are configured consistently. The library/framework module name must be the **actual runtime module name**, not guessed from package names or JAR filenames.

## 7. Runtime Options: Checking the Exact Door to Open

The Java launcher provides options to observe or work around a module constraint, often useful when diagnosing packaged applications:

| Option | Primary Effect | What It Does Not Solve on Its Own |
| --- | --- | --- |
| `--add-reads A=B` | Adds a readability edge from `A` to `B` | Package export/open permissions |
| `--add-exports B/p=A` | Exports package `p` of `B` to `A` at runtime | Private reflection inside `p` |
| `--add-opens B/p=A` | Opens package `p` for deep reflection from `A` at runtime | Compile-time source imports into package `p` via `opens` alone |

Example when private reflection from `demo.consumer` into `internal` is denied:

~~~text
--add-opens demo.library/demo.library.internal=demo.consumer
~~~

If the reflecting code resides on the **classpath / unnamed module**, the target usually needs to be `ALL-UNNAMED` instead of a module name:

~~~text
--add-opens demo.library/demo.library.internal=ALL-UNNAMED
~~~

These options can make a program run at runtime, but they should be treated as **explicit deployment configurations or diagnostic measures**, not opened unconditionally by default to bypass API design. Avoid `ALL-UNNAMED` when you can narrow the target to an exact named module.

Another important point: `--add-exports` only grants runtime public API access; if the package containing private fields is still not open, `setAccessible(true)` can still be rejected. Similarly, `--add-opens` does not make the compiler accept an import that is not exported in `module-info`.

## 8. Common Errors and How to Read Messages

| Symptom | Common Explanation | How to Fix |
| --- | --- | --- |
| Compiler reports module does not read dependency | Missing `requires` or appropriate readability edge | Check `module-info`, `requires transitive`, and module path |
| Compiler reports package not visible / not exported | Readability exists, but package is not exported to consumer | Export only the API packages meant to be public |
| `IllegalAccessException` when invoking/constructing via reflection | Class/member is not accessible under Java visibility or module boundaries | Check `public`/`exports` and whether `opens` is needed |
| `InaccessibleObjectException` on `setAccessible(true)` | Not permitted to suppress access checks for that member | Verify `opens` for the exact package and reflecting module |
| `trySetAccessible()` returns `false` | Deep reflection permission has not been granted | Inspect `Module.isOpen` and the accessing module |
| `ClassNotFoundException` | Module/JAR not resolved/loaded or class loader cannot find name | Check module path, layer, binary name, and class loader |
| `isExported()` returns `true` yet compile-time import fails | Package is opened at runtime or dynamic rights differ from compile-time descriptor | Distinguish runtime `isExported` from `exports` in `module-info` |
| `ServiceLoader` finds no plugins | Missing `uses`/`provides` or module/layer/provider not discovered | Check JPMS service declarations and resolution sources |

**Do not treat a successful `getDeclaredFields()` call as proof of permission to read private data.** Test an actual operation such as `trySetAccessible()`, `Field.get()`, or `Method.invoke()` from inside the module performing reflection.

**Do not fix errors by exporting every package.** `exports` opens public APIs, not private fields. If a framework needs private reflection, a narrow qualified `opens` is usually the right target.

**Do not use `open module` as a default answer.** Opening every package expands the reflection surface. On JDK 17, strong encapsulation of named modules is an architectural property that should be actively managed.

## 9. Step-by-Step Workflow to Diagnose a Real Module Error

When encountering a module error while integrating a plugin/framework:

1. Record the **calling source module**, **module containing the class**, **package**, **member**, and specific action (compile-time import, invoking a public method, or reading a private field).
2. Check the readability graph: `requires`, `requires transitive`, `Module.canRead()`, and whether the module is actually resolved in the layer.
3. Check `exports` for the **exact target module**. `Module.isExported(package, target)` reflects runtime state, while `ModuleDescriptor.exports()` shows the static declaration.
4. If the action is deep reflection, check `opens` for the target module actually invoking reflection; use `Module.isOpen(package, target)`.
5. Confirm Java visibility: `public` type/member versus `private`/package-private/`protected`; JPMS permissions do not alter all Java language access rules.
6. Verify in practice with `trySetAccessible()` or the corresponding reflection call, along with the original stack trace.
7. When temporary `--add-opens` or `--add-exports` flags are needed, codify a minimal, tested policy in `module-info.java` or deployment docs; avoid reflexively widening permissions.

A stable SPI system typically exports only contract packages, uses `requires`/`uses`/`provides` for module and service relationships, and opens only packages where a framework requires deep reflection. That way, plugins are discovered cleanly while implementation encapsulation remains intact.

## 10. Self-Check Questions

**A consumer already `requires` a module yet still cannot import a public class—why?** Because `requires` establishes readability; the providing module must also `exports` the package containing that class to the consumer.

**If a package is `exports`ed, can private fields be read via `setAccessible(true)`?** Not by default. Private members from another module still require an appropriate `opens` (or another qualifying access condition per the specification).

**If a package is `opens`ed without `exports`, can the consumer directly import public classes from that package?** Not via `opens` alone. `opens` grants runtime reflection access, not compile-time source import permission.

**Why does `Module.isExported()` return `true` after `--add-opens`?** Java treats a package open to a target module as exported to that target at runtime. This is a dynamic runtime state, not an `exports` directive in the original module descriptor.

**Does discovering providers with `ServiceLoader` require `opens` on the implementation package?** Normally not for service discovery alone, because named modules use `provides ... with ...` and `uses`; deep reflection into private members of a provider is a separate requirement.

**When a framework performs reflection on behalf of the host, who should `opens ... to` target?** The module containing the framework code executing the access check, using its actual module name.

### Standard References

- Java Language Specification 17, §7.7.2 *Exported and Opened Packages*: https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html
- Java SE 17, `java.lang.Module` (`canRead`, `isExported`, `isOpen`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- Java SE 17, `java.lang.reflect.AccessibleObject`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html
- Java SE 17, `java.util.ServiceLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Dev.java, *Reflective Access with Open Modules and Open Packages*: https://dev.java/learn/organizing/modules/opening-for-reflection/

**Distinction to keep clear:** readability answers "does module A read module B"; `exports` answers "which packages are public API for consumers"; `opens` answers "which modules are permitted deep reflection into a package." To resolve errors accurately, identify the exact *access type* and *accessing module*, then verify each permission separately.
