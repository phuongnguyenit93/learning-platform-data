# JPMS and Strong Encapsulation in Java Reflection

## 1. The Big Picture: Why Is Reflection Still Restricted?

**JPMS (Java Platform Module System)**, introduced in Java 9, allows an application to organize code into **named modules**. Each module declares the other modules it needs to read, the packages exposed to external code, and the packages that allow deep access via reflection. This adds a module-level encapsulation boundary alongside Java's `public`, `protected`, package-private, and `private` language modifiers.

**Strong encapsulation** means external code cannot by default cross a named module's package boundary just because it holds a `Class`, `Method`, `Field`, or `Constructor`. In particular, `setAccessible(true)` is no longer a "master key" to unlock every private member. Whether a package is **opened** to the caller's module determines deep-access capability.

This lesson focuses on the impact of JPMS on **Java Reflection**. The learning goals are:

- Distinguish `requires`, `exports`, and `opens` accurately by their function.
- Understand why you can **find** a private method using `getDeclaredMethod()` yet **cannot invoke** it.
- Predict `canAccess()`, `trySetAccessible()`, and `setAccessible(true)` across two different modules.
- Run a reproducible example on Java 17+ and open the right package only when truly needed.
- Read module-related errors, fix them in the right place, and avoid opening all library internals.

### Three Independent Questions to Ask

1. **Can the caller read the module containing the API?** Module readability is typically declared with `requires` when compiling code that directly references types from another module.
2. **Does the package export its public API externally?** `exports` allows using public types and accessible public members according to normal Java rules.
3. **Is the package opened for deep reflection access?** `opens` allows reflection to bypass Java access checks within the scope granted by JPMS; this permission is typically used by frameworks that need to read private constructors/fields.

A module can answer "yes" to questions 1 and 2, yet "no" to question 3. That is why a public call succeeds while a private call via reflection is rejected.

## 2. Modules and Packages: Two Layers of Encapsulation

Before JPMS, a library typically encapsulated using `public`, `protected`, package-private, and `private`. With JPMS, a package inside a named module also has a policy controlling whether it is exported or opened to other modules.

Example structure:

~~~text
com.example.library  (named module)
  ├── module-info.java
  └── com.example.library.api
        └── SecretBox.java

com.example.client   (named module)
  ├── module-info.java
  └── com.example.client
        └── Main.java
~~~

The library's `module-info.java` defines the module boundary. A client module that wants to call `SecretBox` from regular Java code needs to be able to read the library module **and** needs the package containing that type to be appropriately exported. When using reflection on `private` members, exporting the package is not enough.

| Mechanism | Primary Purpose | Allows private member access via reflection from another module? |
| --- | --- | --- |
| `requires com.example.library;` in client | Client reads the library module as a dependency | **Does not** grant permission by itself |
| `exports com.example.library.api;` in library | Exports the package's public API to modules that read it | **Does not** grant deep-access permission by itself |
| `exports com.example.library.api to com.example.client;` | Exports the public API only to the named module | **Does not** grant deep-access permission by itself |
| `opens com.example.library.api;` | Opens the package for reflection from other modules | **Possible**, when other reflection conditions are also met |
| `opens com.example.library.api to com.example.client;` | Opens for reflection from the specific named module | **Possible**, for the named client |
| `open module com.example.library { ... }` | Opens every package in the module for reflection | Possible, but very broad in scope; do not use individual `opens` inside an `open module` |
| Neither `exports` nor `opens` | Keeps the package internal at the module level | Other clients have no right to use the normal API or deep access via reflection alone |

**`opens` does not replace `exports` when Java code needs to `import` public types at compile time.** Conversely, **`exports` does not replace `opens` when a framework needs to read private fields**. A package can declare both when both normal API usage and deep access are genuinely needed.

In addition, when declaring `exports ... to ...` or `opens ... to ...`, the name after `to` is a **module name**, not a package name and not a class name. Permission is granted per package, not per individual method.

## 3. "Finding" and "Accessing" Are Two Different Steps

Metadata discovery APIs do not have the same meaning as member usage APIs:

| Operation | What are you asking? | Result to understand |
| --- | --- | --- |
| `getDeclaredMethod("secret")` | Does this class itself declare a method named `secret`? | Can find a private method; does not mean it can be invoked |
| `getMethod("greet")` | Is there a matching public method according to the API's lookup rules? | Can find a public method; usage permission still depends on type/package/module accessibility |
| `method.getModifiers()` | Which modifier flags does the method declaration contain? | Returns metadata; does not open access boundaries by itself |
| `method.canAccess(receiver)` | For the current caller and this receiver, is access currently allowed? | Returns `boolean`; pass the proper receiver for instance members |
| `method.trySetAccessible()` | Can Java access checks be suppressed on this reflection object? | `true` if the request succeeds, `false` if impossible due to access restrictions such as modules |
| `method.setAccessible(true)` | Request to suppress Java access checks, or throw an error | May throw `InaccessibleObjectException` if JPMS does not permit it |
| `method.invoke(receiver)` | Actually invoke the method | May throw `IllegalAccessException` if lacking permission; exceptions thrown by the method itself are wrapped in `InvocationTargetException` |

At the Java language access level, a public class in an exported package and a public member of it can be accessed by a client without `opens`. However, private members of that same class remain restricted when the client uses reflection.

A successful call to `trySetAccessible()` **does not modify bytecode** or turn a `private` modifier into `public`. `getModifiers()` still reflects the declaration. The change only concerns suppressing access checks when using that **specific reflection object** within the scope permitted by the runtime.

### Cases Where Suppressing Access Is Permitted

Under the `AccessibleObject` contract, suppressing access checks can be permitted in several cases, such as:

- The caller and the member's declaring type belong to the **same module**.
- A public member of a public class located in a package appropriately exported to the caller's module.
- Certain `protected static` cases of a public class in an exported package when the caller is a subclass.
- The declaring type's package is **opened** to the caller's module; this is the most important case when a framework in another module needs to read/invoke private members.

These are API permission rules, not bypass tricks; rely on the application's module policy.

## 4. Complete Java 17+ Example: Two Modules, One Package Only Exported

The example has a library module containing public and private methods, and a client module calling both via reflection. **By default, the library only `exports` the package; it has not `opens`-ed it yet.**

Create the exact following files in an empty working directory.

**File `src/com.example.library/module-info.java`:**

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

**File `src/com.example.library/com/example/library/api/SecretBox.java`:**

~~~java
package com.example.library.api;

public class SecretBox {
    public String greet() { return "hello"; }
    private String secret() { return "hidden"; }
}
~~~

**File `src/com.example.client/module-info.java`:**

~~~java
module com.example.client {
    requires com.example.library;
}
~~~

**File `src/com.example.client/com/example/client/Main.java`:**

~~~java
package com.example.client;

import com.example.library.api.SecretBox;
import java.lang.reflect.Method;

public class Main {
    public static void main(String[] args) throws Exception {
        SecretBox box = new SecretBox();
        Class<?> type = box.getClass();

        System.out.println("public call: " + box.greet());
        Method greet = type.getMethod("greet");
        System.out.println("public reflection: " + greet.invoke(box));

        Method secret = type.getDeclaredMethod("secret");
        System.out.println("declared: " + secret.getName());
        System.out.println("trySetAccessible: " + secret.trySetAccessible());
        try {
            System.out.println("invoke secret: " + secret.invoke(box));
        } catch (IllegalAccessException ex) {
            System.out.println("invoke blocked: " + ex.getClass().getSimpleName());
        }
    }
}
~~~

**Compile** from the directory containing `src/` (requires JDK 17 or later):

~~~bash
javac --release 17 --module-source-path src -d out -m com.example.library,com.example.client
~~~

The `--module-source-path src` option specifies the source tree organized by module name; `-m` specifies the modules to compile, and `-d out` creates the `out/com.example.library` and `out/com.example.client` directories. This command works in Command Prompt/PowerShell if you are in the working directory containing `src`.

**Run** the client module:

~~~bash
java --module-path out -m com.example.client/com.example.client.Main
~~~

**Verified stdout compiled with `--release 17` and run on JDK 21:**

~~~text
public call: hello
public reflection: hello
declared: secret
trySetAccessible: false
invoke blocked: IllegalAccessException
~~~

**Why does each line happen?**

1. `requires com.example.library` and `exports com.example.library.api` allow the client to compile and work normally with `SecretBox`, calling public `greet()`.
2. `getMethod("greet")` returns the public method; `invoke` is allowed through the exported API.
3. `getDeclaredMethod("secret")` still finds the private method and prints its name. Finding metadata does not require opening the package in the same way as deep access.
4. `trySetAccessible()` returns `false` because `com.example.library.api` is not opened to `com.example.client`.
5. When calling `invoke`, the access check remains in effect; `IllegalAccessException` is caught and printed as the exception's class name.

The output above is the behavior of this specific example with two **named modules** on the module path. When running code on the classpath/unnamed module or changing the `opens` policy, results may differ; do not generalize that all private reflection calls fail.

## 5. Opening the Right Package for Reflection

There are two ways to open the package for the example: editing the module declaration in library source code, or configuring at runtime when you operate the application.

### Option A — Declare `opens ... to ...` in the Library

Replace the contents of `src/com.example.library/module-info.java` with:

~~~java
module com.example.library {
    exports com.example.library.api;
    opens com.example.library.api to com.example.client;
}
~~~

Recompile and run using the **same two commands** from section 4. Now stdout is:

~~~text
public call: hello
public reflection: hello
declared: secret
trySetAccessible: true
invoke secret: hidden
~~~

`exports` serves public calls and `import`; `opens ... to com.example.client` allows the client module deep reflection access to this package. Opening permission applies to the entire named package, so consider carefully before granting it.

### Option B — Add `--add-opens` at Runtime

Keep the original `module-info.java` (`exports` only) and run with the command:

~~~bash
java --module-path out --add-opens com.example.library/com.example.library.api=com.example.client -m com.example.client/com.example.client.Main
~~~

**After compiling with the `exports`-only version from section 4**, stdout matches the opened case in Option A:

~~~text
public call: hello
public reflection: hello
declared: secret
trySetAccessible: true
invoke secret: hidden
~~~

The syntax is `--add-opens <source-module>/<package>=<target-module>`. When a library needs to be opened for a classpath program (unnamed modules), the target is usually `ALL-UNNAMED`; for example, `--add-opens com.example.library/com.example.library.api=ALL-UNNAMED`.

Distinguish clearly:

- `--add-opens`: opens a package for deep reflection access at runtime.
- `--add-exports`: adds visibility to a package's public API; does not by itself grant permission to read private fields/methods via reflection.
- `--add-reads`: adds a readability edge between modules; does not by itself grant `exports` or `opens`.

These flags alter runtime boundaries via deployment configuration; they do not change modifiers in class files and do not modify compiled `module-info.java`. If you want a long-term policy controllable in source, prefer deliberate module declarations.

## 6. Strong Encapsulation for JDK Internals and Legacy Libraries

JPMS does not apply only to application-written modules. Internal packages of the **JDK** are also encapsulated in named modules such as `java.base`.

Key historical milestones to distinguish:

- **Java 9:** introduced JPMS into Java; to ease migration for older applications, the JDK initially had a mechanism relaxing access to some internal packages.
- **Java 16:** JEP 396 made strong encapsulation of JDK internals the default, while still keeping a temporary transition option.
- **Java 17:** JEP 403 strongly encapsulated JDK internal packages by default and rendered the legacy `--illegal-access` option ineffective for broadening access. A few special APIs such as `sun.misc.Unsafe` in `jdk.unsupported` have separate exceptions/policies; do not infer from that that all internal APIs are open.

An application that worked on JDK 8 can fail after upgrading to JDK 17 if a framework or library uses `setAccessible(true)` to access private fields/methods in an unopened JDK package. The sustainable fix is to upgrade the framework, use a supported Java API, or change the access strategy. If a compatibility need cannot be removed immediately, targeted `--add-opens` can serve as a bridge.

Example flag opening `java.base`'s `java.lang` to all unnamed modules:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp app.jar example.Main
~~~

This is a **configuration syntax example**, not a standalone runnable program: `app.jar` and `example.Main` represent a real application. Do not add this flag without evidence that the application needs deep access to `java.lang`. Opening internal packages can reduce encapsulation control and increase coupling to JDK implementation details.

### Why Do Classpath and Module Path Give Different Results?

| How Application/Library Is Loaded | Relevant JPMS Status |
| --- | --- |
| Classes from the classpath | Belong to the **unnamed module** of the associated class loader; packages of an unnamed module are broadly exported and opened per the module contract |
| Regular JAR placed on the module path, without `module-info.class` | Can become an **automatic module** with a module name derived from the JAR; packages of an automatic module are broadly exported/opened for compatibility |
| Named module with explicit `module-info.java` | `requires`, `exports`, `opens` policies are defined by the author; packages do not open automatically just because reflection is used |
| JDK modules | Have their own `exports`/`opens` rules; placing application code on the classpath does not automatically open strongly encapsulated JDK packages |

Therefore, a private library running fine on the classpath **does not prove** that deep access will succeed once the library is converted into an explicit named module. The converse also holds: you must identify which module declares the member and which module invokes reflection before diagnosing.

## 7. Inspecting Modules and Open Policies at Runtime

To diagnose errors, you can query `Module` objects:

~~~java
Module library = com.example.library.api.SecretBox.class.getModule();
Module client = com.example.client.Main.class.getModule();

String pkg = "com.example.library.api";
System.out.println(library.getName());
System.out.println(client.canRead(library));
System.out.println(library.isExported(pkg, client));
System.out.println(library.isOpen(pkg, client));
~~~

This is an **illustrative diagnostic snippet** placed in a context that can reference both classes, not a standalone Java file. With the module descriptors from section 4, you obtain respectively:

~~~text
com.example.library
true
true
false
~~~

When `opens com.example.library.api to com.example.client;` is declared, the last line becomes `true`. If this code is placed in another class, the values of `canRead`, `isExported`, and `isOpen` must be interpreted according to the two specific modules being checked.

- `Class#getModule()`: identifies the actual module containing the loaded class.
- `Module#isNamed()`: helps distinguish a named module from an unnamed module.
- `Module#canRead(other)`: checks the actual readability relationship; this alone does not prove permission to call private members.
- `Module#isExported(packageName, target)`: checks whether the package is exported to the target module.
- `Module#isOpen(packageName, target)`: checks whether the package is open to the target module.

For reflection-based frameworks, **access permission is evaluated against the module of the code that actually invokes the reflection API**, usually the framework module, not necessarily the final application module. Therefore, `opens ... to` must name the exact module receiving permission, such as the framework module that needs to access a model's private fields.

## 8. Distinguishing Common Exceptions

| Error / Result | When Does It Usually Appear? | How to Check |
| --- | --- | --- |
| `NoSuchMethodException` | `getMethod`/`getDeclaredMethod` cannot find the requested signature | Check the name, parameter types, public-vs-declared lookup, and which class actually declares it |
| `IllegalAccessException` | `invoke`, `Field.get/set`, or `Constructor.newInstance` is denied access | Check modifiers, calling class, package, `exports`/`opens`, and accessible state |
| `InaccessibleObjectException` | `setAccessible(true)` requests suppressing checks, but JPMS denies it | Read the error message identifying the source module/package and target module; adjust targeted open permissions |
| `trySetAccessible() == false` | Cannot enable deep access in the current context | Check the actual target module and `opens`; prefer a public API |
| `InvocationTargetException` | The invoked method itself threw an exception | Inspect `getCause()`; this is a failure in the invoked code, not inherently a JPMS error |
| Compile error "package ... is not visible" | Code imports a type from a package not exported to the caller's module or lacks proper readability | Check `requires` and `exports`; opening a package with `opens` alone is not enough for regular `import` |

For example, an `InaccessibleObjectException` message might say module A "does not opens package X to module B". In that case, update module **A** to open package **X** to module **B** (or configure `--add-opens A/X=B` if appropriate). Do not assume that merely adding `requires A` in B fixes it.

Note that `trySetAccessible()` is not guaranteed never to throw in every environment: security checks or invalid API usage can have their own outcomes. In the section 4 example, it returns `false` due to JPMS restrictions.

## 9. Designing Systems That Use Reflection While Preserving Encapsulation

**Follow this priority order when designing a library or framework:**

1. **Expose the right API to use.** When a caller only needs a behavior, choose an appropriate public method/interface instead of grabbing private fields via reflection.
2. **Separate the public API from internal implementation.** Only `exports` packages containing the official contract. Do not export an entire implementation package just to satisfy one convenience snippet.
3. **Open only the right package to the exact framework that needs deep access.** For a library where you can edit `module-info.java`, you can use `opens com.example.model to framework.module;`. This name is purely illustrative; replace it with the actual module name.
4. **Track granted permissions.** When using `--add-opens` for migration, record the reason, library version, deployment configuration section, and replacement plan. Avoid `ALL-UNNAMED` or `open module` when the specific module name of the party needing permission is already known.
5. **Test on the exact target deployment mode.** Test on the module path if the product deploys as named modules; test both open and closed package cases to uncover hidden classpath assumptions.

In framework ecosystems, a library can support its public API in an `api` package via `exports`, while model data used for deserialization/injection in a `model` package uses targeted `opens`. This boundary lets the framework do its job while limiting how much implementation detail external code depends on.

### Repeated Mistakes to Avoid

- **"`setAccessible(true)` always forces private access."** False when a named module does not permit suppressing access.
- **"`exports` and `opens` are the same."** `exports` is for normal API access; `opens` is for deep reflection access.
- **"Finding it with `getDeclaredField` means you can `get` or `set` it."** Metadata discovery differs from operating on the member.
- **"A library that works on the classpath will definitely work identically on the module path."** Unnamed/automatic module permissions differ from explicitly declared named modules.
- **"Open every package to make errors go away fast."** That discards encapsulation boundaries and often hides versioning or API design problems.
- **"Having `requires` automatically allows private reflection."** `requires` is a module readability relationship, not package-opening permission.
- **"`--illegal-access=permit` fixes JDK 17 errors."** That legacy option no longer relaxes access to JDK internals on Java 17.

## 10. Practice and Check Questions

**Exercise 1 — Export public without opening private.** Keep `exports com.example.library.api;` and remove all `opens`. Predict the outcomes of `greet.invoke(box)` and `secret.trySetAccessible()`.

**Answer:** The public call succeeds, while `trySetAccessible()` returns `false` in the two-named-module example. Discovering a private member is not enough to cross the package-opening boundary.

**Exercise 2 — `opens` without `exports`.** Edit the library module to have only `opens com.example.library.api to com.example.client;`. Keep the client code with `import com.example.library.api.SecretBox;`. Predict the compilation result.

**Answer:** Client code is not allowed to directly reference a public type from a non-exported package, so compilation fails; `opens` does not replace `exports`. If the client needs to call `SecretBox` via normal Java APIs and also use private reflection, both appropriate permissions must be granted.

**Exercise 3 — Targeted opening.** `opens com.example.library.api to com.example.client;` is declared. A third module `com.example.other` also wants to call the private member. Does the third module get the same permission?

**Answer:** Not automatically; opening permission is granted specifically to `com.example.client`, unless another open policy or additional runtime configuration is present.

**Exercise 4 — Moving from classpath to module path.** A library relies on private field reflection and works fine before being converted into an explicit named module; afterward `trySetAccessible()` returns `false`. What should you check?

**Answer:** Identify the module of the class declaring the field, the module of the code actually invoking reflection, and the package containing the field; check `isOpen(package, callerModule)`. Prefer a supported API or declare `opens ... to ...` accurately.

**Exercise 5 — Categorizing errors.** `getDeclaredMethod("secret")` succeeds; `setAccessible(true)` throws `InaccessibleObjectException`. Should you fix the method name or the module boundary?

**Answer:** Metadata lookup already succeeded, so check the package-opening boundary and JPMS policy; changing the method name will not solve the root cause.

## 11. Takeaways

JPMS adds module-level boundaries to control which packages are **read**, **exported as public API**, and **opened for reflection**. With Java Reflection, separate three actions: *finding a member*, *reading modifiers*, and *actually accessing it*. `getDeclared...` can see private declarations, yet `trySetAccessible()` only succeeds when module permissions allow it. In long-term design, reserve `exports` for official APIs and `opens` only for packages that truly need deep access, preferring opening to a specific named module.
