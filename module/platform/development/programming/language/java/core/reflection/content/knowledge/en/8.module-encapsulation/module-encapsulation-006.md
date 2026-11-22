# `Module.isExported`, `Module.isOpen`, and Checking Access Context

## 1. The Problem: `public` May Still Not Be Enough

`Module.isExported` and `Module.isOpen` read the **runtime package permission state** from the perspective of a specific module. When diagnosing Reflection, accurately identify the module containing the target package (`source`) and the module **actually calling** `setAccessible` (`client`): that may be a framework, not the application module that initiated the request.

When you need to reference a public API with regular Java code, examine readability and `exports`; when you want to bypass Java access checks from another module, examine `opens`. The sections below focus on accurately interpreting the four overloads and the case where `opens` also causes `isExported` to return `true` at runtime.

Four APIs of `java.lang.Module` are the centerpiece of this lesson:

```java
boolean x1 = source.isExported("example.api");
boolean x2 = source.isExported("example.api", client);
boolean x3 = source.isOpen("example.internal");
boolean x4 = source.isOpen("example.internal", client);
```

The snippet above is illustrative with two already-resolved `Module` variables. Each API asks about permissions for **a package in the source module**, not directly whether a specific field/method can be read or invoked.

**Key point:** `opens` differs from `exports` in purpose, yet **a package opened to a target module is treated as exported to that module at runtime**. Therefore, `isExported(pn, client)` can return `true` even if `module-info.java` only declares `opens pn to client;`. Do not confuse the runtime result with compile-time permission to import that package.

## 2. Correctly Identifying Source, Client, and Package

Define:

- **`source`**: the module containing the package/class being accessed.
- **`client`** (or `callerModule`): the module containing the code actually performing Reflection.
- **`pn`**: the full package name such as `"example.internal"`; not a class name `example.internal.Secret` or path `example/internal`.

Obtaining the information from classes:

```java
Module source = TargetType.class.getModule();
Module client = MyInspector.class.getModule();
String pn = TargetType.class.getPackageName();
```

This is an illustrative snippet requiring the classes to be declared in an appropriate program. If the package is not exported so client code cannot import `TargetType` directly, you can obtain `source` from an exported public API class in the same module, from `Class.forName(...)` when appropriate, or look up a resolved module via `ModuleLayer.boot().findModule("module.name")` if it belongs to the boot layer.

| Check | Meaning |
| --- | --- |
| `source.isNamed()` | Distinguish a named module from an unnamed module |
| `source.getName()` | Module name; `null` for an unnamed module |
| `source.getPackages().contains(pn)` | Is the package currently reported by the module as its own? |
| `client.canRead(source)` | Can client read source? |
| `source.isExported(pn)` | Unconditionally exported at runtime? |
| `source.isExported(pn, client)` | Exported at least to client at runtime? |
| `source.isOpen(pn)` | Unconditionally open at runtime? |
| `source.isOpen(pn, client)` | Open at least to client at runtime? |

**Do not reverse the direction:** When asking about access to `source`'s package, call `source.isOpen(pn, client)`, not `client.isOpen(pn, source)`.

In real applications, `client` may be the module of the framework running the Reflection code, **not necessarily the application module that called into the framework**. This is a very common source of `opens ... to ...` misconfiguration.

## 3. `isExported`: What Purpose Is the Package Visible For?

### 3.1. `isExported(String pn)`

Returns `true` if the package is exported **unconditionally** at runtime:

```java
module m.library {
    exports demo.api;
}
```

`source.isExported("demo.api")` will be `true` for this module if `demo.api` is a present package. Code in another module wishing to directly reference `public` types from `demo.api` still needs other Java/module access conditions, notably readability.

Do not use `isExported(pn)` as a substitute for checking `client.canRead(source)`: the Java documentation specifies that `isExported` methods **do not check** whether the module under inspection is read by the client module.

Important note: an **unconditionally opened** package is also treated as unconditionally exported at runtime, so `source.isExported(pn)` can be `true` when the descriptor has `opens pn;` without `exports pn;`.

### 3.2. `isExported(String pn, Module other)`

Checks whether the package is exported at least to module `other`. For example:

```java
module m.library {
    exports demo.spi to m.client;
}
```

With the exact module `m.client`:

- `source.isExported("demo.spi")` is `false` because the export is **qualified**.
- `source.isExported("demo.spi", client)` is `true` because client is in the target list.

The case of **qualified opens** is even subtler:

```java
module m.library {
    opens demo.internal to m.client;
}
```

At **runtime**, `source.isExported("demo.internal", client)` is **`true`** because a package opened to client is treated as exported to client. However, `source.isExported("demo.internal")` is `false` when there is no unconditional export/open.

Do not deduce that `m.client` source code can write `import demo.internal.Secret;` simply because the two-parameter overload returns `true`. `opens` serves Reflection and runtime access; `exports` is the regular public API declaration checked by the compiler between named modules.

### 3.3. A Module Accessing Itself

If the package belongs to `source`, `source.isExported(pn, source)` returns `true`: Java considers a module to have access to its own packages. This is **not** evidence that the package is exported externally. To learn an external framework's permission, pass that framework's exact `Module`.

## 4. `isOpen`: Permitting Deep Reflection Access

### 4.1. `isOpen(String pn)`

Checks whether the package is opened **unconditionally**:

```java
module m.library {
    opens demo.model;
}
```

In that configuration, `source.isOpen("demo.model")` is `true`. An open package allows suitable Reflection APIs to request bypassing Java language access checks for members in that package, such as `private` constructors or fields.

Conversely, if the module only has:

```java
module m.library {
    exports demo.api;
}
```

then `source.isExported("demo.api")` is `true` while `source.isOpen("demo.api")` remains `false`. Exporting does not automatically grant deep reflection permission.

### 4.2. `isOpen(String pn, Module other)`

Checks whether the package is opened to **a specific module**:

```java
module m.library {
    opens demo.model to m.client;
}
```

Assuming no additional runtime permission changes:

| Check | Result |
| --- | --- |
| `source.isOpen("demo.model")` | `false` |
| `source.isOpen("demo.model", client)` | `true` |
| `source.isExported("demo.model")` | `false` |
| `source.isExported("demo.model", client)` | **`true`** because open is also treated as export at runtime |
| `client.canRead(source)` | Must be checked **separately** |

The `Module` documentation also specifies that `source.isOpen(pn, source)` returns `true` if the package belongs to source itself. Thus, when checking an external framework, passing `source` as `other` will give misleading results.

### 4.3. Comparing the Directives

The table assumes an **explicit named module** whose package actually belongs to it, with no added `--add-exports`/`--add-opens`:

| `module-info.java` | `isExported(pn)` | `isOpen(pn)` | `isExported(pn, client)` | `isOpen(pn, client)` |
| --- | --- | --- | --- | --- |
| Neither `exports`/`opens` | false | false | false | false |
| `exports p;` | true | false | true | false |
| `exports p to m.client;` | false | false | true | false |
| `opens p;` | **true** | true | **true** | true |
| `opens p to m.client;` | false | false | **true** | true |

In the two qualified rows, `client` is the exact module `m.client`. If you pass another module not in the list, the corresponding qualified results will be `false`. These methods return the **current** access state, not merely reading the source declaration lines.

## 5. Checking Full Context: Module Read, Package, and Member

For Java code in the client module to **directly reference** a public API in source, you must check simultaneously:

1. **Readability:** `client.canRead(source)`. A `requires m.library;` directive in `module-info.java` creates the read edge when the module graph is resolved under JPMS rules.
2. **Export:** the package containing the public API is exported to client; distinguish unconditional from qualified exports.
3. **Java access control:** the type and member actually have suitable visibility, e.g., `public` class, `public` method.

For **deep reflection** from a framework, the additional question is whether the package is **open to the module containing the framework**. When operating on `Field`, `Method`, and `Constructor`, methods on `java.lang.reflect.AccessibleObject` also reflect specific accessibility:

| API | Effect |
| --- | --- |
| `getDeclaredField("value")` | Finds metadata about a **directly declared** field; does not grant permission to read the value |
| `canAccess(instance)` | Checks the **caller**'s current access permission for the reflected object |
| `trySetAccessible()` | Attempts to enable suppressing access checks; returns `true` if enabled, `false` when impossible |
| `setAccessible(true)` | Requests enabling that mode; may throw `InaccessibleObjectException` when JPMS forbids it |
| `Field.get(instance)` / `Method.invoke(...)` | Performs the access/invocation and enforces the appropriate rules |

**Caller context is critical:** If code in module `m.framework` calls `trySetAccessible()`, source must open the package to `m.framework`. Opening the package to `m.app` may not help, even if `m.app` is what launched the framework.

**A technical distinction:** Per `AccessibleObject` documentation, using reflected objects to access members has a variation in permission checking: Reflection **assumes readability** during access checks. Therefore, do not mechanically apply every compile-time reference rule to runtime Reflection operations. Even so, `canRead` remains useful when analyzing the module graph and normal Java access; by itself it is nowhere near enough to bypass package encapsulation.

Do not equate **finding a `Class`**, **obtaining `Field`/`Method` metadata**, and **being permitted to read/invoke that member**. For example, `Class.forName` can find a class while `trySetAccessible` still fails if the package is not opened to the caller.

## 6. Hands-On Java 17+ Example: Two Named Modules

The example below demonstrates **qualified opens**: an internal package is not publicly exported yet is opened for Reflection to a specific client. Create the files:

```text
src/
├── m.library/
│   ├── module-info.java
│   └── demo/
│       ├── api/Api.java
│       └── model/Secret.java
└── m.client/
    ├── module-info.java
    └── demo/client/Main.java
```

**`src/m.library/module-info.java`**

```java
module m.library {
    exports demo.api;
    opens demo.model to m.client;
}
```

**`src/m.library/demo/api/Api.java`**

```java
package demo.api;

public final class Api {
    private Api() {
    }
}
```

**`src/m.library/demo/model/Secret.java`**

```java
package demo.model;

public final class Secret {
    private final String message = "hello";

    private Secret() {
    }
}
```

**`src/m.client/module-info.java`**

```java
module m.client {
    requires m.library;
}
```

**`src/m.client/demo/client/Main.java`**

```java
package demo.client;

import demo.api.Api;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

public class Main {
    public static void main(String[] args) throws Exception {
        Module source = Api.class.getModule();
        Module client = Main.class.getModule();

        System.out.println("client reads library: "
                + client.canRead(source));
        System.out.println("api exported to all: "
                + source.isExported("demo.api"));
        System.out.println("api open to all: "
                + source.isOpen("demo.api"));
        System.out.println("model exported to all: "
                + source.isExported("demo.model"));
        System.out.println("model exported to client at runtime: "
                + source.isExported("demo.model", client));
        System.out.println("model open to all: "
                + source.isOpen("demo.model"));
        System.out.println("model open to client: "
                + source.isOpen("demo.model", client));

        // Do not import package demo.model directly.
        Class<?> type = Class.forName("demo.model.Secret");
        Constructor<?> constructor = type.getDeclaredConstructor();
        System.out.println("constructor trySetAccessible: "
                + constructor.trySetAccessible());
        Object instance = constructor.newInstance();

        Field field = type.getDeclaredField("message");
        System.out.println("field trySetAccessible: "
                + field.trySetAccessible());
        System.out.println("secret: " + field.get(instance));
    }
}
```

In the directory containing `src`, compile and run:

```bash
javac -d out --module-source-path src src/m.library/module-info.java src/m.library/demo/api/Api.java src/m.library/demo/model/Secret.java src/m.client/module-info.java src/m.client/demo/client/Main.java
java --module-path out -m m.client/demo.client.Main
```

**Expected stdout:**

```text
client reads library: true
api exported to all: true
api open to all: false
model exported to all: false
model exported to client at runtime: true
model open to all: false
model open to client: true
constructor trySetAccessible: true
field trySetAccessible: true
secret: hello
```

Analysis:

- `requires m.library;` lets client read the library module; `canRead` is `true`.
- `demo.api` is only publicly `exports`-ed: `isExported` is `true`, `isOpen` is `false`.
- `demo.model` is `opens ... to m.client`: not unconditionally exported/opened. Yet **`isExported("demo.model", client) == true` at runtime**, because qualified open to client also counts as exported.
- Client does not write `import demo.model.Secret;`. Instead, `Class.forName` fetches the class by name. That is a metadata lookup path and does not pre-grant access to constructors/fields.
- Both `trySetAccessible()` calls succeed because the package is genuinely opened to module `m.client` containing the calling code, so the code can instantiate the object via its private constructor and read the private field.

**Controlled failure test:** Remove `opens demo.model to m.client;` in the source module and recompile. Then `isOpen("demo.model", client)` and `isExported("demo.model", client)` become `false`. `constructor.trySetAccessible()` also returns `false`; if the code still calls `constructor.newInstance()` as if permission were granted, `IllegalAccessException` can occur. Always check the return value and stop the deep-access branch on failure.

## 7. Quick Check from Classpath and `java.base`

This is a separate example without a multi-module layout. Save `ModuleProbe.java`:

```java
public class ModuleProbe {
    public static void main(String[] args) {
        Module mine = ModuleProbe.class.getModule();
        Module base = String.class.getModule();

        System.out.println("mine named: " + mine.isNamed());
        System.out.println("mine reads java.base: " + mine.canRead(base));
        System.out.println("java.lang exported: "
                + base.isExported("java.lang"));
        System.out.println("java.lang open: "
                + base.isOpen("java.lang"));
        System.out.println("java.lang exported to mine: "
                + base.isExported("java.lang", mine));
        System.out.println("java.lang open to mine: "
                + base.isOpen("java.lang", mine));
    }
}
```

```bash
javac ModuleProbe.java
java -cp . ModuleProbe
```

**Stdout on standard JDK 17+ configuration, without adding `--add-opens java.base/java.lang=ALL-UNNAMED`:**

```text
mine named: false
mine reads java.base: true
java.lang exported: true
java.lang open: false
java.lang exported to mine: true
java.lang open to mine: false
```

`ModuleProbe` runs in the class loader's **unnamed module**; `String` belongs to the named module `java.base`. Package `java.lang` is exported so code can use public APIs like `String.length()`, but that does not permit Reflection from the classpath to arbitrarily read `String`'s private fields.

## 8. Special Module Types and Consequences

### Explicit Named Module

A module with an explicit `module-info.java` allows per-package control using `exports` and `opens` (including qualified `to m.client` forms). This is the case to which the comparison table in section 4 directly applies.

### `open module`

Declaring `open module m.library { ... }` opens **every package belonging to the module** for Reflection. This is a module-level property, unlike `opens p;` which opens a single package. For packages in an open module, `isOpen(pn)` returns `true`; an unconditionally open package is also treated as unconditionally exported at runtime. Inside the body of an `open module`, do not declare separate `opens` directives.

### Unnamed Module

Code loaded from the classpath typically belongs to an unnamed module. Per the Java `Module` contract, `isExported` and `isOpen` **when called on an unnamed module** always return `true`; an unnamed module also reads every module. However, an unnamed module does not cause other named modules to automatically open their packages to classpath code.

### Automatic Module

A JAR without an explicit module descriptor can become an **automatic module** if placed on the module path. An automatic module has a name (`isNamed() == true`), and exports and opens its packages for compatibility. Distinguish it from an unnamed module. You can inspect `module.getDescriptor().isAutomatic()` when a descriptor is present.

### A Module Accessing Its Own Package

`source.isOpen(pn, source)` or `source.isExported(pn, source)` returns `true` for packages belonging to `source`. If you accidentally pass `source` instead of the accessing framework's module, the result is easily misinterpreted as external open permission.

## 9. Runtime Permissions Can Differ from Source Declarations

`Module.isExported` and `Module.isOpen` reflect the **runtime module state**. When running Java, additional permissions can be supplied:

| Mechanism | Effect |
| --- | --- |
| `requires m.library;` | Establishes module readability in the module graph |
| `exports p;` or `exports p to m.client;` | Unqualified / qualified public API |
| `opens p;` or `opens p to m.client;` | Unqualified / qualified Reflection access |
| `--add-reads m.client=m.library` | Adds a read edge at runtime |
| `--add-exports m.library/demo.internal=m.client` | Adds an export to client at runtime |
| `--add-opens m.library/demo.model=m.client` | Adds an open to client at runtime |

Suppose you remove `opens demo.model to m.client;` from the library; after recompiling, you can enable open permission right at launch (if you control the launch command):

```bash
java --module-path out --add-opens m.library/demo.model=m.client -m m.client/demo.client.Main
```

`--add-opens` is the choice for deep reflection needs. `--add-exports` has a different meaning, supporting public access at runtime; do not automatically add both without determining the requirement.

The methods `Module.addReads`, `Module.addExports`, and `Module.addOpens` also exist, but they are **guarded by caller and module-state checks**. An arbitrary module's framework cannot assume it is free to open all packages of another module.

Therefore, `source.getDescriptor().exports()` or `opens()` represents the module's descriptor and can **differ from runtime state** due to configuration flags or dynamic updates. When analyzing an error, look simultaneously at the descriptor, the actual `Module` object, launch arguments, and the relevant module layer.

## 10. Workflow for Debugging `InaccessibleObjectException`

A short yet complete workflow:

1. **Target class:** identify `targetClass.getName()` and `targetClass.getPackageName()`.
2. **Source module:** `targetClass.getModule()`, along with its name and `isNamed()` status.
3. **Actual caller:** find the class executing `setAccessible`/`trySetAccessible`; get `Accessor.class.getModule()`. If that is a framework, the framework module is `other`.
4. **Query package permissions:** compare `source.isOpen(pn)` with `source.isOpen(pn, callerModule)`; do the same for `isExported`.
5. **Readability:** query `callerModule.canRead(source)` separately, especially when there are compile/module resolution errors or normal Java access errors.
6. **Check the specific member:** test `canAccess`/`trySetAccessible` or examine the actual exception, noting that constructors, instance/static fields, and methods require the proper `obj` argument.
7. **Check runtime:** `module-info.java`, `--module-path` vs `-cp`, launch flags, agents, and permission-updating APIs.

When an exception says module `m.library` does not `opens demo.model` to module `m.framework`, check open permission **to `m.framework`**. Adding `opens demo.model to m.app;` just because the main application belongs to `m.app` may fail to cover the actual caller.

### Inferences to Avoid

- `isOpen(pn) == false` **does not** mean `isOpen(pn, client)` is always false (there are qualified opens).
- `isExported(pn, client) == true` **does not** guarantee the package has an `exports` line; the result can come from `opens` at runtime.
- `isOpen(pn, client) == true` **does not** guarantee every Reflection action will succeed unconditionally.
- `canRead(source) == true` **does not** allow reading private fields if other Reflection conditions are missing.
- `getDeclaredField` finding a field **does not** mean the caller is allowed to call `Field.get`.
- `isOpen(pn, source) == true` for a package belonging to `source` **does not** prove the package is opened to an external framework.

## 11. Self-Check Exercise

Given the source module:

```java
module m.provider {
    exports demo.api;
    opens demo.internal to m.consumer;
}
```

Assume `demo.api` and `demo.internal` are real packages, module `m.consumer` is resolved and reads the source module, and there are no runtime overrides. Predict:

```java
provider.isExported("demo.api");                   // A
provider.isOpen("demo.api");                       // B
provider.isExported("demo.internal");              // C
provider.isOpen("demo.internal");                  // D
provider.isExported("demo.internal", consumer);    // E
provider.isOpen("demo.internal", consumer);        // F
provider.isOpen("demo.internal", provider);        // G
```

**Answer:** A = `true`; B = `false`; C = `false`; D = `false`; E = **`true`** (qualified opens also takes export effect at runtime); F = `true`; G = `true` (a module can access its own packages).

These are code snippets for reasoning, not a standalone compilable Java file. To run, use the full program in section 6.

## 12. Takeaways and Official Documentation

**Ask questions from both source and caller perspectives:** `source.isExported(package, callerModule)` and `source.isOpen(package, callerModule)`. The one-argument overload queries unconditional permission; the two-argument overload queries permission at least for a specific module. A package opened to a target module **is treated as exported to that module at runtime**, yet `opens` retains its distinct purpose of deep reflection; `exports` is for normal public APIs. Module readability, package permissions, and member permissions must be evaluated separately.

Reference documentation:

- [Java SE 21 — `Module`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html)
- [Java SE 21 — `AccessibleObject`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Java Language Specification `7.7 — Module Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html)
