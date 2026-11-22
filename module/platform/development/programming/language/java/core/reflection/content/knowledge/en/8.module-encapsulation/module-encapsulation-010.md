# Designing Public APIs Instead of Depending on JDK Internals

Java Reflection allows reading metadata and invoking members when access rules are satisfied; it does not turn every class visible in the JDK into a **long-term supported API**. In the Java Platform Module System (JPMS), a class marked `public` can still reside in a package that is not `exports`-ed and must not be used as a public contract. Sustainable design chooses documented public APIs, sets clear module boundaries, hides implementations, and uses Reflection within permitted access boundaries.

This lesson belongs to the **Modules and Encapsulation** topic: we will identify internal JDK APIs, understand why forcing access breaks easily on JDK upgrades, design stable APIs for our own modules, verify with Reflection, and plan migration away from JDK internals.

## 1. Syntactic "Public" Differs from Contract "Public API"

A class may be `public class Example`, yet there are at least three distinct questions:

1. **Does the class/member have the `public` modifier?** `Modifier.isPublic(type.getModifiers())` or `Modifier.isPublic(method.getModifiers())` checks one piece of metadata.
2. **Is the package `exports`-ed by its owning module to the calling module?** With named modules, JPMS checks accessibility at module boundaries. An unexported package does not become a directly usable API just because a class is `public`.
3. **Is that API committed to be supported, documented, and maintained by the JDK or library?** This is a question of stability, compatibility, and release policy. JPMS assists encapsulation, yet `exports` by itself is not an eternal compatibility guarantee.

Warning-sign namespaces when encountered in an application are `jdk.internal.*`, many `sun.*` packages, `sun.reflect.*`, or `sun.security.*`. They can change, become more strongly encapsulated, or be removed from the runtime. A notable exception is certain documented APIs in `com.sun.*`-prefixed packages, such as `com.sun.net.httpserver.HttpServer` in module `jdk.httpserver`: **you cannot judge whether an API is supported from the package prefix alone**. Consult the official API and module documentation for the JDK version your project supports.

A familiar example: Base64 encoding/decoding should use `java.util.Base64` (the official API), rather than relying on legacy internal JDK encoders.

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

byte[] input = "hello".getBytes(StandardCharsets.UTF_8);
String encoded = Base64.getEncoder().encodeToString(input);
byte[] decoded = Base64.getDecoder().decode(encoded);
String result = new String(decoded, StandardCharsets.UTF_8);
```

This is an illustrative snippet meant to sit inside a method. The `Base64` API has a public contract and lives in `java.base`; the application needs neither internal package opening nor Reflection to encode Base64.

**Principle:** the `public` keyword is only part of the story. To depend on something long term, verify **that the package is exported to consumers, actual accessibility, and supported-API status**.

## 2. JPMS Boundaries: requires, exports, and opens

JPMS (Java Platform Module System, Java 9+) describes module dependencies and access in `module-info.java`.

| Declaration or Mechanism | Purpose | Impact to Remember |
| --- | --- | --- |
| `requires com.example.lib;` | Current module reads module `com.example.lib` | Reading the module alone is not enough to access unexported packages |
| `exports com.example.lib.api;` | Exposes API package to code from modules reading this module | Allows accessing public types/members per Java rules; regular Reflection on public APIs also works |
| `exports com.example.lib.spi to com.example.plugin;` | Qualified export to the named module | Other modules cannot directly import this package |
| `opens com.example.lib.model;` | Allows deep Reflection access at runtime | Does not grant permission to import an unexported package at compile time |
| `opens com.example.lib.model to com.example.serializer;` | Opens package to one specific Reflection module | Narrows open scope compared to unqualified `opens` |
| Neither `exports` nor `opens` | Hides implementation details | External code has neither direct access nor normal deep Reflection access |

`exports` and `opens` **do not replace each other**:

- `exports` serves public APIs. Reading metadata and calling public methods on public classes in an exported package can be done via Reflection without opening the package to override access checks.
- `opens` lets tools such as serializers or dependency injection perform deep access to non-public members when that access is genuinely required and passes other checks. It **does not** make a package normally importable at compile time.
- `open module com.example.lib { ... }` opens every package of the module for deep Reflection. This is broad; usually prefer exact `opens package to framework.module` when working with frameworks.
- A package can be both `exports`-ed and `opens`-ed when there is a clear reason for both; regular public APIs only need `exports`.

For a class in a named module, consider whether the calling module **reads** the owning module (readability), whether the package is **exported** to the caller, and whether the member has suitable access rights. Being able to load a `Class` by name or retrieve metadata does not mean invoking a member will be permitted.

### Checking Export/Open Status via Module's Public API

```java
Module owner = String.class.getModule();
Module caller = MyClass.class.getModule(); // MyClass belongs to your application

boolean publicApiVisible = owner.isExported("java.lang", caller);
boolean deepReflectionAllowed = owner.isOpen("java.lang", caller);
```

This is an illustrative snippet, where `MyClass` is an application class you define. `Module.isExported(String, Module)` and `Module.isOpen(String, Module)` distinguish export and open permissions **for a specific calling module**. With standard JDK 17, `java.base` exports `java.lang` yet does not unconditionally open that package to every application; therefore do not assume you can read every private field of `String`.

Checking `Module.isExported` alone is still not enough to conclude an API is safe for long-term use: it only describes the JPMS access policy of the runtime version being inspected.

## 3. Architectural Example: Export Only the API, Keep Implementation Inside the Module

Design a library `com.example.greeter` with two packages:

```text
src/
├── com.example.greeter/
│   ├── module-info.java
│   └── com/example/greeter/
│       ├── api/
│       │   ├── Greeter.java
│       │   └── Greeters.java
│       └── internal/
│           └── DefaultGreeter.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
```

Goal: the application module can instantiate the service via a factory and use the public interface. The library remains free to change `DefaultGreeter` without forcing users to depend on the implementation class.

### File 1 — src/com.example.greeter/module-info.java

```java
module com.example.greeter {
    exports com.example.greeter.api;
}
```

Intentionally **do not export** package `com.example.greeter.internal`. Code within `com.example.greeter` itself can still use classes in that package under normal Java access rules.

### File 2 — src/com.example.greeter/com/example/greeter/api/Greeter.java

```java
package com.example.greeter.api;

public interface Greeter {
    String greet(String name);
}
```

### File 3 — src/com.example.greeter/com/example/greeter/api/Greeters.java

```java
package com.example.greeter.api;

import com.example.greeter.internal.DefaultGreeter;

public final class Greeters {
    private Greeters() {
    }

    public static Greeter create() {
        return new DefaultGreeter();
    }
}
```

The factory returns the **interface** rather than `DefaultGreeter`, keeping the caller's contract small and clear.

### File 4 — src/com.example.greeter/com/example/greeter/internal/DefaultGreeter.java

```java
package com.example.greeter.internal;

import com.example.greeter.api.Greeter;

public final class DefaultGreeter implements Greeter {
    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

The `public` keyword on `DefaultGreeter` is needed so the factory in another package of the same module can call the public constructor. However, this class is still not part of the public API **for the application module** because its package is not exported.

### File 5 — src/com.example.app/module-info.java

```java
module com.example.app {
    requires com.example.greeter;
}
```

The application simply declares its dependency on the library module, then uses types from exported packages.

### File 6 — src/com.example.app/com/example/app/Main.java

```java
package com.example.app;

import com.example.greeter.api.Greeter;
import com.example.greeter.api.Greeters;
import java.lang.reflect.Method;

public final class Main {
    public static void main(String[] args)
            throws ReflectiveOperationException {

        Greeter service = Greeters.create();
        System.out.println(service.greet("Java"));

        Class<?> apiType = Greeter.class;
        Module owner = apiType.getModule();
        Module caller = Main.class.getModule();

        System.out.println("API type: " + apiType.getName());
        System.out.println("API module: " + owner.getName());
        System.out.println("API exported: "
                + owner.isExported("com.example.greeter.api", caller));
        System.out.println("Internal exported: "
                + owner.isExported("com.example.greeter.internal", caller));

        Method method = apiType.getMethod("greet", String.class);
        Object output = method.invoke(service, "Reflection");
        System.out.println("Reflection: " + output);
    }
}
```

### Compiling and Running

In the parent directory containing `src`, run using JDK 17+:

```bash
javac --module-source-path src -d out -m com.example.greeter,com.example.app
java --module-path out -m com.example.app/com.example.app.Main
```

Output:

```text
Hello, Java
API type: com.example.greeter.api.Greeter
API module: com.example.greeter
API exported: true
Internal exported: false
Reflection: Hello, Reflection
```

**Why does Reflection still work?** `getMethod("greet", String.class)` finds the public method on **interface `Greeter` in the exported package**. Reflection invokes through the public contract; the JVM dispatches to the real implementation, even though the implementation sits in a hidden package. This is an example of proper encapsulation: the caller never needs to import or deep-reflect on `DefaultGreeter`.

If you try adding to `Main.java`:

```java
import com.example.greeter.internal.DefaultGreeter;
```

the compiler rejects importing the unexported package in module `com.example.greeter`. Even though `DefaultGreeter` has the `public` modifier, module `com.example.app` is not permitted to depend directly on that package.

**Note:** the example code provides all files for modular compilation. It requires the exact directory structure and module names. The `--module-source-path`, `-m`, and `--module-path` syntax belongs to JDK tools and does not rely on shell-specific command substitution.

## 4. Reflection Does Not Bypass JPMS Encapsulation

The operations below have different meanings:

```java
Class<?> type = Class.forName("java.lang.String");
java.lang.reflect.Method method =
        type.getMethod("substring", int.class);
```

`String` resides in `java.lang`, a public/exported package of `java.base`, so public methods can be used via normal APIs or Reflection under access checks.

Meanwhile, here is **illustrative code showing an access pattern you must not build features on**:

```java
java.lang.reflect.Field internal =
        String.class.getDeclaredField("value");
internal.setAccessible(true);
```

Across many JDK 17+ builds, `String` has a private field named `value`, yet **do not depend on that name or storage layout**: another JDK or future release can change it. `getDeclaredField` can return metadata, but `setAccessible(true)` can throw `java.lang.reflect.InaccessibleObjectException` because `java.base` does not open `java.lang` to the calling module. If the field no longer exists, `NoSuchFieldException` can occur at the metadata lookup step.

Choose the public API that fits your intent:

```java
String text = "hello";
char first = text.charAt(0);
int length = text.length();
byte[] utf8 = text.getBytes(java.nio.charset.StandardCharsets.UTF_8);
```

These APIs express **intent** (characters, length, encoding) without forcing code to understand `String`'s private storage.

### Errors/Outcomes to Distinguish

| Symptom | Common Cause | Sound Resolution |
| --- | --- | --- |
| Compile error saying package is not visible/exported | Package belongs to a named module and is not exported to calling code | Use the official exported API; update the module descriptor if you own the package and exporting is intentional |
| `InaccessibleObjectException` on `setAccessible(true)` | JPMS denies enabling deep access to an unopened package | Avoid reading private JDK fields; for your own packages, use `opens ... to ...` if justified |
| `IllegalAccessException` on `Method.invoke` or `Field.get` | Member/type access check is not satisfied | Use valid public APIs; ensure proper receiver, access permission, and module |
| `ClassNotFoundException`/`NoSuchMethodException` | Class/method name or implementation version differs from assumption | Do not hard-code internal names; use documented APIs and clear capability detection |
| `Class.forName(name)` succeeds yet invoke fails | Class loading and member access permission are two separate steps | Do not equate loading a class with "being permitted to use the API" |

`AccessibleObject.trySetAccessible()` (Java 9+) returns `false` when access cannot be enabled, instead of always throwing an exception on access-permission failure; other errors can still occur. Use it to write cleanly controlled diagnostic code, **not** to probe and force JDK encapsulation.

## 5. Suitable Replacement APIs for Common Needs

| Practical Need | Dependency Example to Avoid by Default | Public API Direction to Consider |
| --- | --- | --- |
| Base64 encoding/decoding | Legacy internal JDK Base64 decoders | `java.util.Base64` |
| Atomic updates or variable access with specific memory semantics | `sun.misc.Unsafe` just for CAS/field read/write | `java.util.concurrent.atomic` or `java.lang.invoke.VarHandle` where appropriate |
| Invoking methods/constructors, metadata discovery | Access hacks with `sun.reflect.*` | `java.lang.reflect`, `java.lang.invoke.MethodHandles`, public constructors/factories |
| Cryptography, signatures, and secure random | Direct implementations under `sun.security.*` | `java.security`, `javax.crypto`, standard JCA/JCE providers |
| Accessing JVM and environment metrics | Reading private fields of JDK runtime classes | `Runtime`, `ManagementFactory`, `java.lang.management` per needed data |
| Processing `String` contents | Reading private `String.value` | `String.charAt`, `codePoints`, `getBytes(Charset)`, `length` |
| Loading files, resources, and modules | Intervening in internal class loader structures | `ClassLoader.getResource*`, `Class.getResource*`, `Module`, `ServiceLoader` per goal |

The table is **grouped by intent**, without claiming every replacement API covers 100% of every internal API's capabilities. For example, `sun.misc.Unsafe` spans several distinct feature groups; classify your actual usage to choose `VarHandle`, atomic classes, supported foreign function/memory APIs on your target JDK, or a redesign.

Similarly, `MethodHandles.privateLookupIn` is a public API yet **not a bypass around module permissions**: to create a private lookup for a class in another module, module/open-package conditions must still be satisfied. Do not design libraries assuming a lookup can access any private JDK class.

## 6. Two Frequently Misunderstood Launch Flags: add-exports and add-opens

The JDK provides compatibility/diagnostic flags used in some legacy systems:

```bash
# Syntax example, not a recommended long-term configuration:
java --add-exports java.base/jdk.internal.misc=ALL-UNNAMED -cp app.jar com.example.Main

java --add-opens java.base/java.lang=ALL-UNNAMED -cp app.jar com.example.Main
```

- `--add-exports module/package=target` grants access to a package at the **public API** level for the specified target. It is usually used temporarily when code needs to import/link public types in an unexported package.
- `--add-opens module/package=target` opens a package for **deep Reflection** at runtime, e.g., letting a legacy framework attempt accessing private members. This flag does not turn private members into a compile-time public API.
- `ALL-UNNAMED` applies to unnamed modules (typically code running on the classpath). For named modules, the target should be a **specific module name**. Enabling permission may require corresponding configuration at both compile time and runtime, depending on the case.
- Opening flags **do not repair API contracts** and do not guarantee internal classes/methods still exist or preserve semantics after a JDK upgrade.
- Starting in Java 17, the broad `--illegal-access` relaxation mechanism from Java 9–16 became obsolete and no longer relaxes encapsulation. Do not use it as a solution for Java 17+ environments.

A pragmatic design rule: if a system only runs by opening `java.base/java.lang` to read `String`'s private fields, record that as **compatibility debt** and replace the code with public APIs before considering migration complete.

If a framework genuinely needs Reflection into **classes you own**, declare modules intentionally:

```java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.model to com.example.serializer;
}
```

This is an **illustrative** module descriptor; module `com.example.serializer` must be present in the module graph at the corresponding build/run step. It protects the exported API contract while granting deep Reflection access to the model package only to the named serializer. Do not "open everything" merely to avoid identifying which package actually needs access.

## 7. Detecting Internal JDK Dependencies Before Upgrading Versions

An important step is identifying dependencies in **both static and dynamic directions**.

### Static Scanning with jdeps

The JDK ships with `jdeps`; scan the application JAR file:

```bash
jdeps --jdk-internals app.jar
```

Depending on application structure, add classpath/module-path entries for dependent libraries so `jdeps` analyzes more accurately. For multi-release JARs, you can specify the target version, e.g., `--multi-release 17`. `jdeps --jdk-internals` reports notable static dependencies on JDK internal APIs and in many cases suggests replacement public APIs.

**Limitation:** `jdeps` analyzes bytecode and statically observable dependencies, so it can **miss accesses constructing class names from strings and Reflection**, dynamically generated code, later-loaded plugins, or native integrations. Never treat an empty `jdeps` report as proof that no execution path uses internals.

### Reviewing Reflection and Runtime Configuration

Search within your project's own code and configuration for:

- Package name strings `sun.`, `jdk.internal.`, `sun.reflect.`, along with `Class.forName`/`getDeclared*`/`setAccessible` calls targeting JDK classes.
- VM flags `--add-opens` and `--add-exports`; identify where they are needed and their exact targets.
- Legacy JSON, ORM, DI, bytecode agent, proxy, or plugin libraries: they may use deep Reflection in third-party code even if application code does not call it directly.
- Critical run profiles: module-path vs classpath, tests, dev, CI, and production environments may have different flag sets.

When you find a dependency, document the **business purpose**, exact internal API, public replacement, and version-upgrade risk level. That prevents "patching" every place with the same flag and missing design flaws.

## 8. Designing Sustainable APIs for Your Own Java Libraries

Principles that let internal classes evolve without forcing consuming applications to change:

1. **Define the contract first:** export an `api` package containing interfaces, factories, records/DTOs, or stable classes. Return only types accessible to callers. Avoid public methods returning internal types that consumers cannot name or handle cleanly.
2. **Hide actual implementations:** keep `internal`/`impl` packages unexported; instantiate via factories or public dependency injection. Do not instruct consumers to call `Class.forName("...internal...")`.
3. **Open minimal Reflection:** for packages where serializers/DI need to read private fields, consider `opens ... to ...` for the right module. If you can design public constructors, accessors, or adapters instead of deep reflection, the API will be easier to maintain.
4. **Do not randomly export internal packages just to fix compile errors:** adding `exports` turns implementation details into something consumers can depend on. Any future refactoring of that package can cause breakage.
5. **Use `ServiceLoader` when plugins/extensibility are needed:** providers can be configured with `provides ... with ...`, while consumers use `uses ...` and the proper service interface. Do not force callers to identify private implementations by fixed class names.
6. **Maintain API compatibility deliberately:** when changing signatures, return types, module requirements, or documented behavior, evaluate source/binary compatibility and test consumers. The word "public" alone does not guarantee compatibility.
7. **State support policies clearly:** rely only on public APIs of the declared minimum Java version; avoid implicitly requiring newer versions by reflecting on classes absent from the baseline.

In the section 3 example, if `DefaultGreeter` switches from building strings directly to reading a configuration resource, callers still see only `Greeter.greet(String)`. That is the benefit of abstraction combined with JPMS encapsulation.

## 9. Step-by-Step Migration: From Implementation Detail to Contract

Suppose a codebase uses Reflection to directly grab `String`'s backing array and process bytes. When upgrading the JDK, this operation can fail because the private field/layout changed or because `java.base/java.lang` is not open.

Workflow:

1. **Analyze intent:** do you need to iterate characters, Unicode code points, UTF-8 bytes, or just length? Those are different requirements and cannot all be replaced by the same API.
2. **Choose the public API:** `charAt` iterates UTF-16 code units; `codePoints` works in Unicode code points; `getBytes(StandardCharsets.UTF_8)` produces a UTF-8 byte array; `length` gives the number of UTF-16 code units. Do not confuse code point count with `length()`.
3. **Replace the internal dependency and remove unnecessary opens:** delete the reflection hack and `--add-opens` flags if no caller needs them anymore.
4. **Verify exact behavior:** add tests with non-BMP characters, null inputs if applicable, encoding, and real performance if this is a hot path. Do not assume an internal backing array has a fixed encoding or layout.
5. **Verify the deployment environment:** run on the minimum supported JDK, test module-path if modularized, and run full integration flows with plugins/agents.
6. **Monitor compatibility:** use `jdeps --jdk-internals` in build verification where appropriate and review newly added VM flags.

For a third-party dependency that requires internals, prioritize upgrading to a library version supporting the target JDK or replacing the library. Module-opening flags should only be a **scoped temporary measure with a removal plan**, if operations genuinely demand it.

## 10. Common Mistakes

| Mistake | Why It Is Dangerous | Right Approach |
| --- | --- | --- |
| "A `public` class means a public API" | JPMS also checks exports; the class may just be an implementation detail | Check support docs, owning module, package exports, and API purpose |
| "`Class.forName` succeeded, so any method can be called" | Class loading is separate from access/reflection permissions | Call only public methods on exported APIs, or grant intentional open permissions for code you own |
| Calling `setAccessible(true)` on `java.base` and assuming it always works | Strong encapsulation can cause `InaccessibleObjectException` | Use public `String`/collections/JCA/JDK APIs instead of private fields |
| Using `--add-opens` to fix an unexported package import error | Opens serves only runtime reflection, not compile-time imports | Design exported public APIs; distinguish from `--add-exports` |
| Adding `--add-exports` permanently | Still locks the application to internal packages | Migrate to supported APIs and limit workarounds |
| Blindly replacing `Unsafe` with any arbitrary API | Different features require different solutions | Classify operations and choose `VarHandle`, atomic APIs, or fitting alternatives |
| Treating all `com.sun.*` names as internal | Some such APIs are publicly exposed and documented by the JDK | Evaluate by module/documentation, not by prefix alone |
| Running only `jdeps` and declaring zero internal API dependencies | Dynamic reflection and native code may not appear in static dependencies | Combine code review, config checks, integration tests, and jdeps |
| Exporting the whole `impl` package because a consumer wants to import one class | Turns implementation into a client dependency | Use factories/service interfaces/DTOs in the `api` package |
| Using module-wide `opens` for a framework | Relaxes Reflection permissions far more broadly than needed | Prefer opening specific packages, qualified `opens ... to ...` when appropriate |

## 11. Self-Check Questions

**Question 1.** Can `public class DefaultGreeter` in an unexported package be imported from another named module just because the class has the `public` modifier?

**Answer:** No. JPMS checks package export permission for the calling module; the `public` modifier is not enough.

**Question 2.** How does `exports package` differ from `opens package`?

**Answer:** `exports` grants access to public APIs from modules that can read the owning module; `opens` grants deep Reflection at runtime within the open scope. `opens` alone does not grant normal compile-time import permission.

**Question 3.** In the `Greeter` example, why does `method.invoke(service, "Reflection")` work when the implementation is not exported?

**Answer:** `Method` is a public member belonging to interface `Greeter` in the exported API package. The JVM dispatches the instance call to the hidden implementation inside the module, so the implementation package does not need to be opened to the caller.

**Question 4.** Does `--add-opens java.base/java.lang=ALL-UNNAMED` turn reading `String`'s private field into good API design?

**Answer:** No. It only relaxes Reflection permission for the specified target; it does not turn a private representation into a stable public contract.

**Question 5.** Does `jdeps --jdk-internals` reporting nothing mean the application uses no internals?

**Answer:** Not necessarily. Code can construct class names at runtime, invoke Reflection by string, load plugins, or perform native operations outside static dependency analysis.

**Question 6.** Can `Modifier.isPublic(type.getModifiers())` be used as the sole criterion to confirm a "supported API"?

**Answer:** No. You must check the module, export permission, documentation, target Java version, and compatibility policy.

**Takeaway:** Reflection is a tool for metadata discovery and member invocation within Java access limits, whereas a **public API** is the system's contract boundary. Use supported JDK APIs, export only your API packages, keep implementations unexported, and open deep Reflection only when there is a genuine, legitimate need.
