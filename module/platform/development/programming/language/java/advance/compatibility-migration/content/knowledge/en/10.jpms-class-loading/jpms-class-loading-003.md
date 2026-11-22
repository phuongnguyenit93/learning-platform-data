# `requires`, `exports`, and `opens` in the Access Contract

When a Java application moves from the traditional classpath to the **Java Platform Module System (JPMS)**, having a `public` modifier on a class is no longer a sufficient condition for code in another component to use it. Across module boundaries, the JVM and compiler also need to know which module **can read** which module, which packages are **exported as API**, and which packages are **opened for reflection**. The three core directives in `module-info.java` are `requires`, `exports`, and `opens`.

This is not merely syntax for organizing source code. The three directives form part of the **access contract** between modules: which APIs a library exposes, which modules an application is allowed to depend on, and which classes frameworks are permitted to inspect or manipulate deeply. When upgrading the JDK or adjusting `module-info.java`, changing a single `exports` or `opens` line can cause code that previously compiled and ran normally to raise access errors, even when class and method names have not changed.

This lesson focuses on how these directives operate, how to combine them in real-world applications, and how to assess compatibility impacts when migrating to JPMS.

## 1. From the Classpath to a Module-Level Access Contract

In the traditional classpath model, classes are typically placed in JARs or directories. If a class is `public` and present on the classpath, code in another package can generally reference it under standard Java access rules.

In JPMS, a **named module** declares its identity and dependencies using `module-info.java`. For example:

```java
module com.example.orders {
    requires java.sql;
    exports com.example.orders.api;
    opens com.example.orders.persistence;
}
```

The `com.example.orders` module in this example makes three commitments:

- It needs to read the `java.sql` module to use the types provided under that module's access contract.
- It exposes public types in the `com.example.orders.api` package as part of its API accessible from modules that read it.
- It permits deep reflection on the `com.example.orders.persistence` package, including non-public members subject to the rules of the reflection API.

None of those three lines means that every class in the module is public. `requires` relates only to module readability, `exports` opens regular access to public types in a package, and `opens` enables reflective access at runtime.

### 1.1. Three Layers of Control When Code in Another Module Calls an API

Suppose `com.example.app` wants to call a public method in `com.example.orders.api.OrderService`. For a regular call to be valid, all of the following conditions must be satisfied simultaneously:

1. **Readability:** the application module can read the library module, usually via `requires` or a readability relationship established by JPMS rules.
2. **Package export:** the package containing the public type is exported to the application module, either by an unqualified `exports` or by `exports ... to ...` that includes it.
3. **Java access control:** the class, constructor, and method must have appropriate accessibility, such as `public` for calls from another package.

You can visualize the access gates as follows:

```text
com.example.app
      |
      | (1) can read the module?
      v
com.example.orders
      |
      | (2) package exported to app?
      v
com.example.orders.api
      |
      | (3) class/member has appropriate Java access?
      v
OrderService.submit()
```

If any condition is not met, the code may be rejected by the compiler or the compiled binary may encounter access errors when the JVM links it. Having a *fully qualified name* and existing inside a JAR does not bypass these gates.

### 1.2. Reflection Is a Different Contract

An ORM framework, dependency injection container, or serializer may need to read private fields, invoke non-public constructors, or change accessibility via `setAccessible(true)`. This is a form of **deep reflection**, distinct from a client calling a regular public method.

In JPMS, `opens` governs this kind of deep access. A package that is only `exports`-ed does not automatically allow frameworks to manipulate every private field. Conversely, a package that is only `opens`-ed does not automatically become publicly importable in the source code of another module.

## 2. `requires`: Declaring Module Dependencies and Readability

`requires` is placed in `module-info.java` to declare that the current module depends on another named module. For example:

```java
module com.example.app {
    requires com.example.orders;
    requires java.sql;
}
```

The `com.example.app` module reads `com.example.orders` and `java.sql`, provided the module configuration resolves successfully. However, readability does not mean every package inside those two modules is accessible. The target module must still export the packages to be used.

### 2.1. Standard `requires`

This is a mandatory dependency in the module configuration:

```java
module com.example.billing {
    requires com.example.contracts;
}
```

At runtime, if `com.example.contracts` is a mandatory dependency that the module system cannot find or resolve, creating the module configuration may fail, typically with an error related to `java.lang.module.FindException` or `ResolutionException`. That is a **module resolution** problem, distinct from `ClassNotFoundException` during a call to load a class by name.

When declaring `requires`, make sure the target module is provided via the runtime image, module path, or corresponding distribution mechanism. Simply listing a dependency in a build configuration file does not guarantee that the runtime artifact packages it properly.

### 2.2. `requires transitive`: Exposing a Dependency for Indirect Reading by Consumers

Suppose module `com.example.facade` provides a public API based on types located in module `com.example.contracts`:

```java
module com.example.facade {
    requires transitive com.example.contracts;
    exports com.example.facade.api;
}
```

The client module only declares:

```java
module com.example.client {
    requires com.example.facade;
}
```

Because of `requires transitive`, the client reads `com.example.contracts` indirectly through `com.example.facade`. This is useful when the facade's API has parameter or return types belonging to the contracts module.

```text
com.example.client
        |
        | requires
        v
com.example.facade
        |
        | requires transitive
        v
com.example.contracts

=> client has an indirect readability relationship with contracts
```

However, **readability does not replace exports**. For the client to actually use a public type in `com.example.contracts`, the package containing that type must still be exported by the contracts module according to JPMS rules.

Use `requires transitive` deliberately: it expands the dependency contract visible to consumers. If the facade uses a module only in its internal implementation, a regular `requires` usually expresses the intent more accurately.

### 2.3. `requires static`: Compile-Time Required, Runtime Optional Dependency

Some dependencies serve annotations or optional integration features. JPMS supports:

```java
module com.example.model {
    requires static com.example.annotations;
    exports com.example.model.api;
}
```

`requires static` indicates that the target module must exist at compile time, but is not required to be present during runtime configuration resolution. It is not a directive guaranteeing that all code using that dependency will run safely when the dependency is absent.

If the code actually calls or needs to load a class from the optional module at runtime, its absence can still cause errors. Ensure that execution paths depending on this module are properly guarded and tested both with and without the dependency present.

### 2.4. Comparison Table of the Three `requires` Forms

| Directive | Primary Meaning | Things to Keep in Mind |
|---|---|---|
| `requires m;` | Depends on and directly reads module `m` | The module must resolve properly; required packages must still be exported. |
| `requires transitive m;` | Depends on `m` and propagates readability to modules that read the current module | Does not automatically export packages of `m`; use when the public API exposes the dependency. |
| `requires static m;` | Requires the module at compile time, optional at runtime | Code invoking classes of `m` at runtime still requires the actual dependency. |

Every module reads `java.base` implicitly, so writing `requires java.base;` is unnecessary. This does not mean that all modules in the JDK are automatically read in the same way.

## 3. `exports`: Exposing a Package as Part of the API

`exports` declares a package whose public types can be accessed by code in other modules through normal Java mechanisms, when readability and Java access permissions also hold.

For example:

```java
module com.example.orders {
    exports com.example.orders.api;
}
```

Suppose that package contains:

```java
package com.example.orders.api;

public class OrderService {
    public String status() {
        return "READY";
    }

    private void refreshInternalCache() {
        // Implementation details
    }
}
```

A consumer that reads `com.example.orders` can call the `status()` method if normal access rules are satisfied. However, `exports` **does not make private methods public**. Nor does it turn package-private classes in the same package into public types.

### 3.1. Unqualified Exports

```java
exports com.example.orders.api;
```

This directive allows other modules with valid readability to access the public types in the exported package. This is typically the choice for library APIs intended for use by many external consumers.

A module can still keep its implementation in another unexported package:

```text
com.example.orders
  +-- com.example.orders.api          (exports)
  |       +-- OrderService.java
  +-- com.example.orders.internal     (not exported)
          +-- OrderRepositoryImpl.java
```

This allows developers to modify the implementation without promising public access compatibility for internal classes.

### 3.2. Qualified Exports: Exporting Only to Specified Modules

JPMS lets you restrict which modules can access a package:

```java
module com.example.orders {
    exports com.example.orders.api;
    exports com.example.orders.integration to com.example.billing;
}
```

Under this declaration, the `com.example.orders.integration` package is exported only to the `com.example.billing` module. Another module, even if it declares `requires com.example.orders;`, still cannot import public types from that package via regular Java access.

This is a way to design an API for a specific consumer, such as internal integration between modules in the same system. However, the target module name becomes part of the access configuration. If the consumer module is renamed, split, or repackaged, the qualified exports must also be updated.

### 3.3. `exports` Does Not Mean External Code Can Access Every Member

Let's distinguish three situations:

| Element in an `exports`-ed Package | Can Another Module Read the Source Module | Can It Be Used Normally? |
|---|---:|---|
| `public class` with `public` method | Yes | Yes, when no other access constraints apply. |
| `public class` with `private` field | Yes | Cannot read the private field directly. |
| Package-private class | Yes | Cannot be accessed directly from another package. |
| `protected` member | Yes | Only within Java's `protected` rules. |

A change to an access modifier at the class/member level can break clients even when `exports` stays unchanged. Conversely, revoking an `exports` line can also break clients even when every class and method remains `public`.

## 4. `opens`: Allowing Deep Access via Reflection

Reflection allows a program to inspect classes, constructors, methods, and fields at runtime. Many frameworks must operate on non-public members—for instance, an ORM needs to assign values to private fields, or a serializer needs to invoke non-public constructors.

If a package belongs to a named module and is not opened to the framework's module, calling `setAccessible(true)` to bypass access checks can be blocked. `opens` is the directive used to grant the appropriate reflective access.

### 4.1. Opening a Package to All Modules Needing Reflection

```java
module com.example.orders {
    exports com.example.orders.api;
    opens com.example.orders.persistence;
}
```

The `com.example.orders.persistence` package is opened for deep reflection from other modules. However, this package **is not exported** merely because it has `opens`. A normal application still cannot import types from that package without a corresponding export.

### 4.2. Qualified Opens: Opening Only to Specific Frameworks or Modules

```java
module com.example.orders {
    exports com.example.orders.api;
    opens com.example.orders.persistence to com.example.orm;
}
```

Only the `com.example.orm` module has deep reflection permission under this package-opening configuration. This reduces implementation exposure compared to opening the package to all modules.

The name in the `to` clause must correspond to the actual module name of the framework or consumer. Some older dependencies running on the classpath belong to the *unnamed module*, or JARs on the module path have *automatic module* names; determine the exact deployment model before writing qualified opens.

### 4.3. `open module`: Opening Every Package for Reflection

JPMS also supports:

```java
open module com.example.legacy {
    requires java.sql;
    exports com.example.legacy.api;
}
```

`open module` causes every package in the module to be opened for deep reflection. This can serve as a transitional step for applications heavily reliant on reflection, though the scope is broader than necessary and can weaken desired encapsulation.

An `open module` cannot also declare individual `opens` directives. Opening all packages also **does not automatically export** them for regular source-code access; `exports` still carries independent meaning.

### 4.4. When Do You Need `opens` Instead of `exports`?

| Need | Usually Appropriate Directive | Explanation |
|---|---|---|
| Application imports a public class and calls a public method | `exports` + readability | Grants standard Java access. |
| ORM sets an entity's private field via reflection | `opens` to the ORM module | Supports deep reflection at runtime. |
| Serializer invokes a private constructor via reflection | `opens` to the serializer module | Access needs to bypass normal Java access checks. |
| Integration module needs to call a public helper in an internal package | `exports ... to ...` | Provides a public API to the specified consumer. |
| Both public API and deep reflection are needed | `exports` and `opens` on the same package if needed | Two distinct access purposes that can coexist. |

Note: public members of an exported package can already be used by many standard public reflection operations without `opens`. `opens` is especially important when you want to *suppress* access checks to reach non-public members or perform deep reflection.

## 5. Complete Example: A Library with Both a Public API and a Model for Reflection

Consider two modules:

```text
src/
  com.example.library/
    module-info.java
    com/example/library/api/GreetingService.java
    com/example/library/internal/SecretRecord.java
  com.example.client/
    module-info.java
    com/example/client/Main.java
```

### 5.1. Library Module

File `src/com.example.library/module-info.java`:

```java
module com.example.library {
    exports com.example.library.api;
    opens com.example.library.internal to com.example.client;
}
```

File `src/com.example.library/com/example/library/api/GreetingService.java`:

```java
package com.example.library.api;

public class GreetingService {
    public String greet(String name) {
        return "Xin chào, " + name;
    }
}
```

File `src/com.example.library/com/example/library/internal/SecretRecord.java`:

```java
package com.example.library.internal;

public class SecretRecord {
    private final String code = "CODE-42";

    public SecretRecord() {
    }
}
```

`SecretRecord` is a public class in the Java language, yet its package is not exported. Therefore, client code cannot import this class via normal access paths. Qualified opens grants only deep reflection capability to `com.example.client`.

### 5.2. Client Module

File `src/com.example.client/module-info.java`:

```java
module com.example.client {
    requires com.example.library;
}
```

File `src/com.example.client/com/example/client/Main.java`:

```java
package com.example.client;

import com.example.library.api.GreetingService;

import java.lang.reflect.Field;

public class Main {
    public static void main(String[] args) throws Exception {
        GreetingService service = new GreetingService();
        System.out.println(service.greet("Java"));

        Class<?> type = Class.forName(
            "com.example.library.internal.SecretRecord"
        );

        var constructor = type.getDeclaredConstructor();
        constructor.setAccessible(true);
        Object record = constructor.newInstance();

        Field code = type.getDeclaredField("code");
        code.setAccessible(true);
        System.out.println(code.get(record));
    }
}
```

Here there are two different kinds of access. `GreetingService` is imported and called thanks to `requires` combined with `exports`. `SecretRecord` is not imported directly; the client looks up the class by name and then reads the private field via reflection because the package is `opens`-ed to the client module.

### 5.3. Compiling and Running the Example

In the root directory containing `src/`, using a JDK that supports JPMS:

```bash
javac --module-source-path src -d out \
  --module com.example.library,com.example.client

java --module-path out \
  --module com.example.client/com.example.client.Main
```

The commands shown use the Unix-style shell line-continuation character `\`. On Windows PowerShell, you can enter each command on a single line or use the shell's corresponding line-continuation syntax. The essential point is that both modules are on the module path at runtime.

If you remove `requires com.example.library;` from the client, the compiler will lack the readability relationship needed to import the library's public API. If you remove `exports com.example.library.api;` from the library, the client still declares requires but loses source access to the API package. If you remove `opens com.example.library.internal to com.example.client;`, deep reflection calls such as `setAccessible(true)` may fail with a module access error at runtime.

The example shows clearly: the three directives handle three distinct conditions. Fixing one directive does not automatically satisfy the other two.

## 6. Typical Errors When Access Contracts Do Not Match

### 6.1. Module Does Not Read a Dependency

If a client module uses a class from another module without an appropriate readability relationship, the compiler may report that the package is declared in a module that the current module does not read.

```text
package com.example.library.api is not visible
  (package ... is declared in module com.example.library,
   but module com.example.client does not read it)
```

The way to resolve this is to determine whether the consumer truly needs to depend on this module, then declare `requires` or adjust the module architecture. Do not use `exports` to fix missing readability: a library module cannot substitute its own export for the client's dependency declaration.

### 6.2. Package Is Not Exported

If the client has `requires` but the library's package is not exported to it, the compiler may report:

```text
package com.example.library.internal is not visible
  (package ... is declared in module com.example.library,
   which does not export it)
```

Determine whether that package should be part of the public API. If it is a supported API, intentionally add `exports` or `exports ... to ...`. If it is purely internal implementation, update the client to use the public API instead of exporting internals just to make the build succeed.

### 6.3. Deep Reflection Is Blocked

If a framework calls `setAccessible(true)` on a private field in a package not opened to the calling module, the runtime may throw `java.lang.reflect.InaccessibleObjectException`, with a message indicating that the source module does not `opens` the corresponding package to the target module.

Conceptual example:

```text
java.lang.reflect.InaccessibleObjectException:
  Unable to make field private ... accessible:
  module com.example.library does not "opens"
  com.example.library.internal to module com.example.client
```

This is not `NoSuchFieldError`: the field may still exist, yet the deep access operation is disallowed. Identify the framework module actually performing reflection and open the exact required package, or upgrade the framework so it uses public APIs where appropriate.

### 6.4. Older Binaries Encounter `IllegalAccessError`

If a consumer was compiled against a library module version where a package was exported, and a newer library version revokes that export, recompiling the consumer's source will be rejected by the compiler. Pre-existing consumer binaries are not automatically recompiled and still retain references to the previously accessible public classes/methods; during linking, the JVM may detect that access is no longer permitted and throw `IllegalAccessError`.

Preserving class names, package names, and method descriptors does not guarantee binary compatibility if the module contract is narrowed. Distinguish this access-check error from `NoSuchMethodError`, which usually indicates that a method with the matching name and descriptor can no longer be found.

### 6.5. Missing Module at Startup

If a module demands a dependency via `requires` and the runtime does not supply that module, module resolution may fail before the application enters `main()`:

```text
java.lang.module.FindException:
  Module com.example.library not found,
  required by com.example.client
```

Inspect the module path, module names, and packaging. Do not try to fix `exports` or `opens` when the real error is that a required module is absent from the runtime configuration.

| Symptom | Question to Check First | Usually Related Change |
|---|---|---|
| Client cannot read another module | Does a module readability relationship exist yet? | `requires`, `requires transitive`, or special configuration |
| Importing a public class is still rejected | Is the package exported to the client? | `exports` or qualified exports |
| Reflection on a private field fails | Is the package opened to the calling module? | `opens` or qualified opens |
| Old binary fails access after replacing JAR | Were exports or access modifiers narrowed? | Binary/module compatibility contract |
| Runtime reports a missing module | Is the module present on the module path/resolution? | Packaging, module name, and `requires` |

## 7. Compatibility When Upgrading the JDK and Changing Module Descriptors

A module descriptor is part of the API contract. When changing it, do not look solely at which Java methods remain or are removed.

### 7.1. Removing `exports` Is a Potentially Consumer-Breaking Change

Suppose version 1 has:

```java
module com.example.library {
    exports com.example.library.api;
    exports com.example.library.legacy;
}
```

In version 2, the author removes the export of the legacy package:

```java
module com.example.library {
    exports com.example.library.api;
}
```

Even if the classes in `com.example.library.legacy` remain public and keep the same descriptors, consumers in other modules may lose access. Treat this as a contract change and verify both source compatibility and binary compatibility.

If the goal is to remove a legacy API, announce a deprecation roadmap, maintain a replacement API for a transition period, and revoke access only in a planned breaking-change release.

### 7.2. Narrowing `exports` to Qualified Exports

Changing:

```java
exports com.example.library.api;
```

to:

```java
exports com.example.library.api to com.example.partner;
```

means that only the `com.example.partner` module retains access via that export. Other consumers that previously used this package may be blocked. This is a compatibility change even though the package and the code inside remain unchanged.

Qualified exports are useful when the consumer group is well-defined, but should not be used to restrict a broadly published API without evaluating existing applications.

### 7.3. Removing `opens` Can Break Frameworks at Runtime

If an entity package was previously opened to an ORM framework and is later closed, the application may compile successfully while the ORM fails when constructing entities, reading fields, or creating proxies via reflection.

The failure might only surface in a specific database execution path, not necessarily at startup. Therefore, beyond compiling, run integration tests for frameworks that use reflection and verify behavior on the actual production module path.

### 7.4. Changing `requires transitive` to `requires`

When a module stops propagating readability to a dependency, consumers that previously relied on indirect readability may no longer compile or be able to access types in the dependency module. Even if the implementation code of the first module still works, consumers of its public API may need to add a direct `requires`.

This is why `requires transitive` should be treated as an API contract design decision, not merely syntax to silence compiler warnings.

### 7.5. Renaming a Module Also Affects the Contract

Consumers declare `requires` by **module name**, not necessarily by JAR file name. If a module changes its name, consumers may encounter module resolution failures. Qualified exports and qualified opens must also be updated to match the new module name.

When converting a traditional JAR into an explicit named module, define a stable module name and a migration plan. An automatic module name derived from the JAR or read from `Automatic-Module-Name` may differ from the explicit module name a library later chooses; verify it rather than assuming.

## 8. Classpath, the Unnamed Module, and Automatic Modules

During migration, an application may not have moved all libraries to JPMS yet. Understanding transitional regions helps prevent errors caused by inconsistent configurations.

### 8.1. The Unnamed Module of the Classpath

Code placed on the classpath belongs to the unnamed module rather than having its own `module-info.java` descriptor. This mechanism enables legacy applications to keep running in a JPMS-enabled JDK environment.

However, a named module does not automatically treat every class on the classpath as a valid dependency. When incrementally migrating to named modules, examine dependency directions and packaging, because a named module cannot simply declare `requires` on the unnamed module as it would on an ordinary named module.

### 8.2. Automatic Modules

A JAR without `module-info.class` placed on the module path can be treated as an automatic module. This is a transitional mechanism allowing legacy JARs to participate in the module system; it receives a module name and broader readability/exports than an explicit module.

An automatic module does not replace designing a stable module descriptor. When a library transitions to an explicit module, internal packages may no longer be broadly exported. Consumers relying on the earlier default openness will need to adapt to use official APIs.

### 8.3. Split Packages and the Module Path

JPMS enforces constraints when multiple named modules contain the same package (*split package*). A layout that previously worked on the classpath may no longer resolve cleanly when those JARs are moved onto the module path.

When encountering module resolution errors related to duplicate packages, inspect how packages are split across JARs, transitive dependencies, and the modularization strategy. Adding `requires` or `exports` cannot fix an invalid split-package design.

## 9. Transitional Options: `--add-reads`, `--add-exports`, `--add-opens`

During migration, it is sometimes impossible to immediately edit a library's module descriptor or upgrade a framework in the same wave. The JVM and compiler provide several options to adjust access relationships via configuration.

### 9.1. `--add-reads`

```bash
--add-reads com.example.app=com.example.library
```

This option adds a readability relationship from a source module to a target module in the applicable configuration. It addresses **module readability**, without automatically exporting an unexported package.

### 9.2. `--add-exports`

```bash
--add-exports com.example.library/com.example.library.internal=com.example.app
```

This option exports a package from a source module to a specified target module for regular Java access to public types. It does not automatically permit deep reflection on private fields.

In some migrations, it may be necessary to export to code on the classpath using the special target `ALL-UNNAMED`, for example:

```bash
--add-exports com.example.library/com.example.library.internal=ALL-UNNAMED
```

This is a transitional option, not a justification for turning an internal API into a permanent dependency.

### 9.3. `--add-opens`

```bash
--add-opens com.example.library/com.example.library.internal=com.example.framework
```

This option opens a package for deep reflection from the target module. When a framework runs on the classpath, you may see the form:

```bash
--add-opens com.example.library/com.example.library.internal=ALL-UNNAMED
```

Open only the exact package and exact consuming module. Do not add bulk `--add-opens` flags copied from the Internet without identifying the actual access path.

### 9.4. The Three Options Are Not Interchangeable

| Option | Adjusts | Does Not Automatically Solve |
|---|---|---|
| `--add-reads` | Which module can be read | Packages that are not yet exported or opened. |
| `--add-exports` | Packages whose public API can be accessed normally | Deep reflection into non-public members. |
| `--add-opens` | Packages opened for deep reflection | Compile/import relationships and regular API exports. |

These options may appear at compile time or runtime depending on the goal, yet configuration for one phase does not automatically carry over to the other. If a flag is used at compile time, you must still ensure the runtime has appropriate access relationships. If the runtime needs a flag, place it in the production startup command or wherever the JVM process is launched, not only in test tasks.

In modern JDKs with strong encapsulation, do not rely on legacy relaxation mechanisms like `--illegal-access` as a substitute for a framework/API upgrade plan. Transitional configurations should have an owner, a justification, a scope limit, and a removal timeline.

## 10. Inspecting and Diagnosing Access Contracts

To determine whether an issue lies in `requires`, `exports`, or `opens`, combine descriptor inspection, runtime checks, and stack-trace analysis.

### 10.1. Viewing the Module Descriptor

For a JAR with a module descriptor or an inferable module name, you can run:

```bash
jar --describe-module --file library.jar
```

For modules built into the runtime, you can list them with:

```bash
java --list-modules
```

Or view the description of a module recognized by the runtime:

```bash
java --describe-module java.sql
```

When inspecting a module on the module path, configure `--module-path` appropriately. Rely on the output to verify the actual module name, requires, exports, qualified exports, and opens. Do not merely infer them from the JAR filename or from the source code of another version.

### 10.2. Analyzing Dependencies with `jdeps`

`jdeps` can help inspect static dependencies across JARs, packages, or modules. For example:

```bash
jdeps --module-path mods --summary app.jar
```

The output helps identify modules or packages referenced by code via static analysis. However, `jdeps` cannot see every dependency loaded via string names, service loaders, plugins, or reflection. Therefore, a clean `jdeps` result cannot be used to conclude that all existing `opens` directives are unnecessary.

### 10.3. Reading Error Messages Carefully

The error messages usually reveal a great deal about which access gate is missing:

- **“module A does not read module B”**: check readability relationships, `requires`, and module configurations.
- **“module B does not export package p to module A”**: check `exports` or qualified exports.
- **“module B does not open package p to module A”**: check `opens`/qualified opens for deep reflection.
- **“Module X not found, required by Y”**: check the module path, module names, and required dependencies.

If the error appears during bean initialization, object serialization, or proxy creation, read deep into the `Caused by` chain. Framework exceptions may wrap a module-related `InaccessibleObjectException` or `IllegalAccessException`.

### 10.4. Identifying the Caller's Actual Module

A JAR on the classpath and the same JAR on the module path can belong to different modules. If a framework runs as an automatic module, its module name may also differ from the artifact name an operator expects.

When needed, you can print a class's module information:

```java
Module module = SomeFrameworkClass.class.getModule();
System.out.println(module.getName());
```

For an unnamed module, `getName()` returns `null`. This is one way to confirm the target needed for a qualified `opens` or a corresponding runtime flag.

## 11. Designing Sustainable Access Contracts During Migration

A good module is not necessarily the one that exports and opens the fewest packages in every situation. The goal is to expose the exact APIs intended to be supported, allow frameworks to operate as needed, and prevent consumers from depending on internal details.

### 11.1. Expose a Small, Clear, and Stable API

Place supported APIs in clearly named packages, such as `api`, `spi`, or `contracts`. Export only packages genuinely intended for consumers. Implementation classes should reside in unexported packages if clients do not need direct access.

If a package has long been broadly exported, revoking its export requires a migration plan appropriate for a breaking API change. Do not arbitrarily remove an export simply because a package is named `internal`.

### 11.2. Use `requires transitive` According to the API Contract

If module A's public API accepts or returns types from module B, `requires transitive B` usually reflects the dependency consumers need to see. If B is used only in A's implementation, `requires B` avoids propagating unnecessary readability.

Switching between these two forms must be evaluated from the perspective of deployed clients, not merely whether module A itself compiles.

### 11.3. Open Packages to Frameworks with Minimal Scope

An ORM, serializer, or dependency injection framework may require deep reflection. Instead of a module-wide `open module` or unqualified `opens p;`, prefer `opens p to module.framework;` when the target module and deployment layout can be determined.

If the framework runs on the classpath or spans multiple target modules, choose a configuration that actually works in practice and document the reason. Opening too narrowly can break the framework at runtime; opening too broadly makes module encapsulation ineffective.

### 11.4. Do Not Use Flags to Mask Flawed Designs

JVM flags are useful tools to keep operations running during a transition period, but they should be tracked as migration debt:

| Information | Example Entry |
|---|---|
| Flag | `--add-opens module/package=consumer` |
| Reason | Legacy framework accesses private fields via reflection. |
| Scope | Entity package only, only JVMs running service A. |
| Owner | Team owning the framework and migration effort. |
| Plan | Upgrade framework, update descriptor, or change mapping approach. |
| Removal condition | Integration tests pass with the flag removed on the target JDK. |

A build that runs thanks to flags does not mean the module contract is cleanly designed. Before releasing, test both the production configuration and the documented transitional mechanisms.

## 12. Compatibility Testing Process for the Three Directives

When upgrading the JDK or modifying `module-info.java`, verify each access layer individually.

### Step 1: Inventory Consumers and Modules

Identify official module names, JARs on the module path, libraries still running on the classpath, and frameworks using reflection. Record JDK/build versions and dependency versions.

### Step 2: Verify Readability with `requires`

Compile API-consuming modules against the target module descriptor. Verify direct dependency paths, paths requiring transitive readability, and optional compile-time-only dependencies.

### Step 3: Verify Package APIs with `exports`

For each exposed public API, create a test client outside the module and compile it on the module path. When using qualified exports, test both authorized consumers and consumers excluded from the list.

### Step 4: Verify Reflection with `opens`

Run integration tests for ORMs, mappers, serializers, and dependency injection. Do not only check that classes can be found; actually invoke constructors, read/write fields, and execute the deep reflection operations used by the frameworks.

### Step 5: Run Pre-Compiled Consumer Binaries

When evaluating binary compatibility, keep the consumer artifact compiled against the old library and swap in the new library/module descriptor. Exercise critical API access paths to detect `IllegalAccessError` and linkage errors that can be hidden by merely recompiling source.

### Step 6: Verify Packaging and the Actual Runtime

Run on the exact module path, container image, and production startup command. Ensure runtime flags are applied to the right Java process. A test passing on the classpath does not guarantee that a modular application running on the module path will behave identically.

### Step 7: Record Evidence and Decisions

For each change, record the old/new module descriptors, list of consumer modules, errors/stack traces if any, verification tests, and remediation plan. Consider a change safe only within the scope of verified consumers and execution paths.

## 13. Common Misconceptions

**“Having `requires` lets you use every class of the dependency.”** No. The source module must also export the appropriate package, and the class/member must have suitable Java access permissions.

**“A public class means other modules can always import it.”** No. Public visibility does not bypass JPMS package export and readability boundaries.

**“`exports` allows frameworks to access private fields.”** No. Deep reflective access generally requires the package to be opened to the calling module.

**“`opens` means that package is part of the public API.”** No. Opens is for reflection and does not automatically expose the package for regular imports or calls.

**“`requires transitive` also exports all packages of the dependency.”** No. It propagates readability; the dependency module still controls exports of its own packages.

**“`requires static` guarantees the dependency is unnecessary at runtime.”** No. It makes the module optional during runtime resolution; executing code that uses a class from the dependency still requires that class to be present.

**“Just adding `--add-opens` fixes every module error.”** No. Missing readability, missing exports, missing required modules, and reflection errors require different resolutions.

**“If source and method descriptors are unchanged, binary compatibility is guaranteed.”** No. Revoking `exports`, changing qualified exports, or narrowing Java access modifiers can cause older binaries to hit access errors at link time.

**“Running tests on the classpath is enough.”** No. If production uses the module path, you must test with the actual module configuration, module names, and runtime flags.

## 14. Checklist Before Accepting a JPMS Change

- [ ] Identified source module names, target module names, and actual consumers.
- [ ] Checked `requires` and distinguished direct, transitive, and static dependencies.
- [ ] Cross-checked public packages requiring export against the officially supported API.
- [ ] Verified that qualified exports do not inadvertently exclude legitimate consumers.
- [ ] Identified which frameworks require deep reflection and which packages must be opened.
- [ ] Distinguished `exports`, `opens`, and `open module` in the design.
- [ ] Checked classpath/unnamed modules and automatic modules for legacy components.
- [ ] Verified module names, `module-info.java`, and the module path of actual artifacts.
- [ ] Reviewed transitional JVM flags, their scope, and their removal plan.
- [ ] Compiled consumer sources against the new module descriptor.
- [ ] Ran integration tests for reflection, ORM, serializers, and related plugins.
- [ ] Ran older consumer binaries against the new library module where binary compatibility is required.
- [ ] Recorded test results, remaining issues, and assigned owners.

## 15. Conclusion

`requires`, `exports`, and `opens` are three independent yet closely related parts of JPMS's access contract. **`requires` determines readability between modules; `exports` exposes a package for regular Java API usage; `opens` permits deep reflective access at runtime.** To call an API from another module, readability, package export, and Java access control must all be satisfied simultaneously. To access private members via reflection, also check whether the package is opened to the caller.

During a migration, changing a module descriptor can break source compatibility, binary compatibility, or framework integrations even while the library's classes and methods still exist. Therefore, do not treat `module-info.java` as merely an internal configuration file. Design modules around real consumers, expose APIs intentionally, open reflection permissions with minimal scope, and test both new source code and pre-compiled artifacts before altering access contracts in production.
