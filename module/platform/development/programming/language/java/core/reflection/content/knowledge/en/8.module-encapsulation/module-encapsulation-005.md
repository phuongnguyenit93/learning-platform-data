# Named Module, Unnamed Module, and Open Module in Java Reflection

## 1. Goal and Context

Since Java 9, the **Java Platform Module System (JPMS)** adds module boundaries alongside packages, classes, and access modifiers. Two classes both being `public` no longer guarantees one can access the other from any module: in addition to Java-level access permissions, the JVM checks the **module graph**, module readability (`readability`), **exported** packages, and packages **opened** for Reflection.

When working with `Class<?>`, `Method`, `Field`, and `Constructor`, three concepts must be distinguished:

- **Named module**: a module with a name, typically declared with `module-info.java`; *automatic module* JARs on the module path are also named modules.
- **Unnamed module**: a module without a name, containing classes loaded from the **class path**; each class loader has its own unnamed module.
- **Open module**: a **type of named module** declared with `open module ...`; every package in that module is opened for deep reflection at runtime.

These three terms are not on the same classification axis: **an open module is a named module**, whereas an unnamed module is a separate kind of module. You should also distinguish the `opens package.name` directive inside a regular named module from making the **entire** module an `open module`.

After this lesson, you will be able to inspect module metadata via Reflection, configure `module-info.java` properly for both public APIs and libraries using Reflection, explain `InaccessibleObjectException`, and decide when to use `exports`, `opens`, `open module`, or the `--add-opens` command-line option.

## 2. Where Does JPMS Sit in the Access Process?

Suppose there are two modules:

```text
com.example.inspector
    |
    | requires com.example.target   (reads module)
    v
com.example.target
    ├── com.example.target.api
    │       exports ...             (public API)
    └── com.example.target.internal
            opens ... to com.example.inspector
                                    (deep reflection permitted)
```

In the diagram, `requires` establishes the read relationship, `exports` grants permission to use the public API under suitable Java/module conditions, and `opens` allows deep reflection within the opened scope. Opening a package for Reflection **does not automatically allow importing** that package's public types at compile time.

The specific focus of this lesson is the **default policy by module kind**: unnamed module on the classpath, explicit named module, automatic module, and explicit open module. Modules can support Reflection differently even when the caller's Java source code does not change.

## 3. Exact Comparison Table

| Feature | Regular explicit named module | Unnamed module | Explicit open module |
| --- | --- | --- | --- |
| Typical creation | `module name { ... }` in `module-info.java` | Classes/JARs on `--class-path` or `-cp` | `open module name { ... }` in `module-info.java` |
| `Module.isNamed()` | `true` | `false` | `true` |
| `Module.getName()` | Module name | `null` | Module name |
| Package export permission | Per `exports` (and appropriate runtime access rules) | All packages exported | All packages open at runtime, yet **not by default compile-time exported APIs** |
| Inter-module deep reflection | Only packages appropriately `opens`-ed, or already permitted access cases | All packages open | All packages open |
| Protection interface via `module-info.java` | Yes, per package | No separate source descriptor | Yes, but opens all packages |
| Use case | Libraries/applications with selective API and Reflection design | Legacy classpath applications | Applications/modules intentionally allowing broad framework Reflection access |

### 3.1. Explicit Named Module

A module named `com.example.target` can declare:

```java
module com.example.target {
    exports com.example.target.api;
    opens com.example.target.internal to com.example.inspector;
}
```

- `exports com.example.target.api;` allows modules that appropriately read it to use this package's public API.
- `opens com.example.target.internal to com.example.inspector;` opens the internal package **only to the named module** for deep reflection.
- Packages that are neither exported nor opened are **strongly encapsulated** against external modules.
- You can write `exports p to m1, m2;` for qualified exports or `opens p;` to open to all modules at runtime.

For a module that wants to use the API:

```java
module com.example.inspector {
    requires com.example.target;
}
```

The `requires` directive creates readability, but **does not automatically open** private fields in the target's packages.

### 3.2. Unnamed Module

All classes on the classpath loaded by a class loader belong to that class loader's unnamed module. Running a program like:

```bash
java -cp classes UnnamedDemo
```

typically yields `UnnamedDemo.class.getModule().isNamed() == false` and `getName() == null`.

An unnamed module **reads every observable named module**, and exports/opens all of its own packages. This is a compatibility mechanism so many legacy classpath applications keep running. However, a class being in an unnamed module **does not** automatically let it cross private boundaries of other named modules; to reflect into a closed package of a named module, the **target named module** must open the package or the runtime must be configured equivalently.

Note: this does not mean every class in the entire JVM resides in a single unnamed module. `ClassLoader.getUnnamedModule()` returns the unnamed module of a specific class loader.

### 3.3. Open Module

If every package in a module is designed for deep reflection, you can declare:

```java
open module com.example.target {
    exports com.example.target.api;
}
```

- `open module` opens **all packages of the module** for runtime Reflection.
- `exports` directives are still necessary to define the compile-time API; the `open` keyword **does not** replace `exports` at compile time.
- **You must not put `opens package.name;` directives inside the body of an `open module`**, because all packages are already open.
- The module still has a **name**, can declare `requires`, `exports`, `uses`, `provides`, and participates in the module graph.

Use `open module` only when opening all packages is intentional. For large libraries, `opens some.package to module.framework` usually maintains steadier boundaries.

### 3.4. Automatic Module Is Another Named Module to Know

A JAR without `module-info.class`, when placed on the module path, can become an **automatic module**, with its name taken from `Automatic-Module-Name` metadata or derived from the JAR filename. An automatic module has `isNamed() == true`, and exports and opens its packages; do not equate it with an unnamed module simply because it lacks `module-info.java`.

Use `Module.getDescriptor().isAutomatic()` when you need to identify an automatic module. On an explicit named module, you can use `Module.getDescriptor().isOpen()` to detect an `open module` declaration. For an unnamed module, `getDescriptor()` returns `null`, so check before calling methods on the descriptor.

**Three typical runtime cases:** classpath → unnamed module; modular JAR with explicit `module-info.class` → explicit named module; JAR without descriptor on module path → automatic named module.

## 4. Related Reflection APIs

| API | Practical Meaning |
| --- | --- |
| `Class.getModule()` | Find the module containing the reflected type. |
| `Module.isNamed()` | Check whether the module has a name. |
| `Module.getName()` | Module name; `null` for an unnamed module. |
| `Module.getDescriptor()` | `ModuleDescriptor` metadata; `null` if unnamed module. |
| `Module.canRead(Module other)` | Whether the current module has a read edge to `other`. |
| `Module.isExported(String pkg)` | Whether the package is exported **unconditionally** under runtime semantics. |
| `Module.isExported(String pkg, Module other)` | Whether the package is accessible/exported at runtime to module `other`; **`opens` can make the result true**. |
| `Module.isOpen(String pkg)` | Whether the package is opened unconditionally at runtime. |
| `Module.isOpen(String pkg, Module other)` | Whether the package is opened to module `other`. |
| `AccessibleObject.setAccessible(true)` | Request suppressing certain language access checks; JPMS can still reject with `InaccessibleObjectException`. |
| `AccessibleObject.trySetAccessible()` | Attempt to enable access; returns `false` if unable to enable due to access checks. |

Diagnostic notes:

- A package with `opens p to m` can make both `isOpen(p, m)` and **`isExported(p, m)`** return `true` at runtime. This **does not prove** the descriptor contains an `exports p to m` directive; read `ModuleDescriptor.exports()` when analyzing **declarations**.
- With `isOpen(pkg, thisSameModule)`, the result can be `true` because a module has access to itself. To check an external framework's permission, pass the **exact module of the framework**, not the source module as the second argument.
- `Module.isOpen(String pkg)` and the overload taking a module differ: an `opens p to m` statement is a **qualified opening**, so `isOpen(p)` can still be `false` while `isOpen(p, m)` is `true`.
- `Class.getModule()` works on regular Java classes; for array types, the module is the element type's module; primitive types and `void` belong to `java.base` according to the API.
- `ModuleLayer.boot()` provides the layer of named modules resolved at startup; unnamed modules are not entries to look up like named modules in a layer.

## 5. Standalone Java 17+ Example: Named Module Opening a Package for Reflection

We create **two named modules**: `com.example.target` holds data and `com.example.inspector` reads that data via Reflection. Directory layout:

```text
src/
├── com.example.target/
│   ├── module-info.java
│   └── com/example/target/
│       ├── api/PublicApi.java
│       └── internal/Secret.java
└── com.example.inspector/
    ├── module-info.java
    └── com/example/inspector/Inspector.java
```

### 5.1. Target Module Source

File **`src/com.example.target/module-info.java`**:

```java
module com.example.target {
    exports com.example.target.api;
    opens com.example.target.internal to com.example.inspector;
}
```

File **`src/com.example.target/com/example/target/api/PublicApi.java`**:

```java
package com.example.target.api;

public class PublicApi {
    public static String greeting() {
        return "hello";
    }
}
```

File **`src/com.example.target/com/example/target/internal/Secret.java`**:

```java
package com.example.target.internal;

public class Secret {
    private final String value = "jpms";
}
```

Class `Secret` is declared `public` so the example focuses on the module boundary; **the `value` field is private** and package `internal` has no `exports` directive. To read the field, the inspector module must use deep reflection, enabled by `opens ... to ...`.

### 5.2. Inspector Module Source

File **`src/com.example.inspector/module-info.java`**:

```java
module com.example.inspector {
    requires com.example.target;
}
```

File **`src/com.example.inspector/com/example/inspector/Inspector.java`**:

```java
package com.example.inspector;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

public class Inspector {
    public static void main(String[] args) throws Exception {
        Class<?> type = Class.forName("com.example.target.internal.Secret");

        Module target = type.getModule();
        Module inspector = Inspector.class.getModule();

        System.out.println("inspector named=" + inspector.isNamed());
        System.out.println("target named=" + target.isNamed());
        System.out.println("target name=" + target.getName());

        String internal = "com.example.target.internal";
        System.out.println("internal open to inspector="
                + target.isOpen(internal, inspector));
        System.out.println("internal unqualified export="
                + target.isExported(internal));
        System.out.println("internal runtime export to inspector="
                + target.isExported(internal, inspector));

        Constructor<?> ctor = type.getDeclaredConstructor();
        ctor.setAccessible(true);
        Object instance = ctor.newInstance();

        Field field = type.getDeclaredField("value");
        field.setAccessible(true);
        System.out.println("secret=" + field.get(instance));
    }
}
```

### 5.3. Compile, Run, and Observe Stdout

From the directory containing `src/`, run using JDK 17 or higher:

```bash
javac --release 17 -d mods --module-source-path src -m com.example.target,com.example.inspector
java --module-path mods -m com.example.inspector/com.example.inspector.Inspector
```

Output:

```text
inspector named=true
target named=true
target name=com.example.target
internal open to inspector=true
internal unqualified export=false
internal runtime export to inspector=true
secret=jpms
```

The example files were compiled with `javac --release 17` and run successfully on JDK 21, with stdout matching the output above.

**Explanation:**

1. Both `Inspector` and `Secret` belong to named modules.
2. `Class.forName` looks up the class by name in the resolved module environment; this **does not mean** Java code in the inspector module is allowed to `import Secret` because package `internal` is not exported as a compile-time API.
3. `isOpen(internal, inspector) == true` because target declares **qualified opens** for `com.example.inspector`.
4. `isExported(internal) == false` because the package is not exported/opened **unconditionally** in this case.
5. `isExported(internal, inspector) == true` is an unexpected detail: when a package is opened to inspector, the API reflects runtime accessibility even though source lacks `exports internal`. This **is not** evidence that `import Secret` is accepted by the Java compiler.
6. `setAccessible(true)` on the constructor and private field succeeds because the package is opened to the **exact caller module**, printing `secret=jpms`.

### 5.4. Try Changing Permissions to Understand Errors

If you remove `opens com.example.target.internal to com.example.inspector;` and recompile, `setAccessible(true)` operations on non-public members of `Secret` from the inspector module **are no longer allowed**. The program will fail with `java.lang.reflect.InaccessibleObjectException` when attempting to enable access, unless you grant open permission through another mechanism.

If you replace it with:

```java
module com.example.target {
    exports com.example.target.api;
    opens com.example.target.internal;
}
```

package `internal` is opened **to all modules**, rather than just inspector.

If you replace the module declaration with:

```java
open module com.example.target {
    exports com.example.target.api;
}
```

all packages in target will be opened for deep reflection, including `internal`. The `exports` directives remain the compile-time public API policy. When running the `open module` variant, some runtime `isExported(...)` queries can differ from the qualified-open variant because runtime permissions were broadened.

**Important:** each `module-info.java` variant above is **an alternative configuration**, not to be combined into the same file.

## 6. Unnamed Module Example on the Classpath

A short Java 17+ program can confirm the module of classpath code.

File **`UnnamedDemo.java`**:

```java
public class UnnamedDemo {
    public static void main(String[] args) {
        Module module = UnnamedDemo.class.getModule();

        System.out.println("named=" + module.isNamed());
        System.out.println("name=" + module.getName());
    }
}
```

Run:

```bash
javac --release 17 UnnamedDemo.java
java -cp . UnnamedDemo
```

Output:

```text
named=false
name=null
```

With the exact same source code, when the application is packaged into an explicit module on the module path and run with `-m`, `Class.getModule()` will reflect the corresponding **named module containing the class**.

In particular, do not treat `getName() == null` as the string `"null"`: the API actually returns Java's `null` value for an unnamed module; only string concatenation in `println` turns it into the text `null` in stdout.

## 7. Migrating Legacy Applications and Handling Deep Reflection Errors

### 7.1. How Does `InaccessibleObjectException` Differ from `IllegalAccessException`?

When a Reflection tool calls `field.setAccessible(true)` from module A on a private field in module B while the target package is not open to A, **enabling access** can throw `InaccessibleObjectException` (unchecked).

If access is not enabled and `Field.get(...)` or `Method.invoke(...)` is still called when disallowed, the access operation can encounter `IllegalAccessException` (checked) per the respective API.

Distinguish **an error when requesting to bypass checks** from **an error when performing access**. Merely switching to `trySetAccessible()` does not broaden module permissions: this API lets you probe with a `boolean` instead of always demanding access with `setAccessible(true)`.

Intentional illustrative example (not a standalone program):

```java
Field field = targetClass.getDeclaredField("value");
if (field.trySetAccessible()) {
    Object value = field.get(targetObject);
    // process value
} else {
    // request opening the package to the right module from the owner
}
```

Do not assume `setAccessible(true)` will bypass JPMS simply because the application runs with elevated OS privileges.

### 7.2. Configuring Package Opening Without Changing Module Source

When the target module belongs to a library or JDK that cannot be modified immediately, the runtime has a temporary option:

```bash
java --add-opens com.example.target/com.example.target.internal=com.example.inspector --module-path mods -m com.example.inspector/com.example.inspector.Inspector
```

Syntax:

```text
--add-opens <source-module>/<package>=<target-module>
```

If the application invoking Reflection belongs to the unnamed module on the classpath, the target is usually `ALL-UNNAMED`:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp classes UnnamedDemo
```

This command illustrates the **syntax** for opening `java.base`'s `java.lang` package to unnamed modules; the `UnnamedDemo` program above does not actually need that permission. Do not add flags just because you saw an example: identify the **exact blocking module/package** and **caller module**.

Other options serve **different functions**:

- `--add-exports source/package=target` grants access to public types/members at runtime; it is **not** a general substitute for deep reflection into private members.
- `--add-reads source=target` adds a readability edge, without **automatically exporting/opening** packages.
- `--add-opens source/package=target` opens a package so Reflection can request deep access from the specified module.

Since Java 17, `--illegal-access` is no longer a mechanism to bypass JDK strong encapsulation. For modern applications, prefer public APIs or narrowly scoped `opens` instead of relying on global flags or JDK internals.

### 7.3. Is Opening a Package Truly Safe and Necessary?

Many DI, serialization, ORM, or testing frameworks must inspect constructors, annotations, fields, or setters via Reflection. However, **not every framework needs private reflective access**. Some frameworks only use public APIs, code generation, or module-specific integrations.

When deciding, ask:

1. Which packages does the framework actually use, and does it run in a **named or unnamed module**?
2. Does it only need public types/members, or does it need to set `accessible` on private members?
3. Can `opens p to framework.module` be used to restrict the receiving module?
4. Is `exports p` needed for regular Java code compiling direct references to the API?
5. In actual deployment, has the framework's module name been confirmed from `Class.getModule().getName()`?

That is why `open module` is sometimes convenient for an application wholly managed by a framework, yet is not the default choice for a library wanting to keep internal packages hidden.

## 8. Diagnosing Errors by Scenario

| Symptom | Possible Module Cause | How to Check |
| --- | --- | --- |
| Cannot `import` a public class from another module | Missing `requires` or package not `exports`-ed to the right target | Check both `module-info.java` files and the module path at compile time |
| `setAccessible(true)` throws `InaccessibleObjectException` | Package not `opens`-ed to the calling module | Print `targetClass.getModule()` and `callerClass.getModule()`, check `isOpen(package, callerModule)` |
| `Class.getModule().getName()` returns `null` | Class is in an unnamed module | Check `isNamed()`, classpath, and class loader |
| A JAR without `module-info.java` has `isNamed()==true` | JAR is used as an automatic module on the module path | Check `getDescriptor().isAutomatic()` |
| `open module` still gives package-not-visible on compile | Package is not `exports`-ed for compilation | Declare `exports` for APIs meant to be public, separate from `opens` |
| Reflective access works on classpath but fails when moved to module path | Change in strong encapsulation boundary | Check which target package needs `opens`, the target of `opens ... to ...`, and launch config |

Non-JPMS issues can also cause `ClassNotFoundException`, `NoClassDefFoundError`, or `IllegalAccessException`. Do not edit `module-info.java` by guessing: check type names, class loaders, module resolution, stack traces, and the exact API throwing the error.

## 9. Common Mistakes and How to Avoid Them

**Mistake 1: Assuming unnamed module and open module are the same.** An unnamed module has no name and is tied to a class loader/classpath. An open module is a named module declared to open all its packages. Both are permissive for runtime Reflection, yet their configuration and module relationships differ.

**Mistake 2: Assuming named modules only exist when `module-info.java` is present.** Automatic modules on the module path are also named modules. Read `getDescriptor().isAutomatic()` before concluding a module's origin.

**Mistake 3: Assuming `exports` permits accessing every private field.** `exports` is for public APIs and normal access; appropriate `opens` is needed if you want `setAccessible(true)` on private members from an external module.

**Mistake 4: Assuming `opens` makes `import` compile successfully.** `opens` does not publish a package as a compile-time public API. If another module must reference it directly, consider `exports`.

**Mistake 5: Seeing `isExported(pkg, other) == true` and inferring `module-info` has `exports`.** At runtime, a package opened to `other` can make that result `true` as well. Distinguish **runtime state** from **directives in `ModuleDescriptor`**.

**Mistake 6: Using `isOpen(pkg, targetModule)` to check framework permissions.** A module has access to its own packages; you must pass the actual framework **caller** module.

**Mistake 7: Thinking classpath code can arbitrarily deep-reflect into JDK internals.** Modern Java strongly encapsulates many packages of named modules; the target must open the needed package, or use an appropriate launch option.

**Mistake 8: Using `open module` to fix all import errors.** That is a runtime Reflection decision and does not replace export/readability policies for compilation.

## 10. Exercises and Self-Check Checklist

1. Run the `com.example.target`/`com.example.inspector` example and verify all six lines of stdout. Try removing `opens ... to ...` and observe where `InaccessibleObjectException` occurs.
2. Try adding `opens` back in **unqualified** form and observe the difference between `isOpen(package)` and `isOpen(package, inspector)`.
3. Replace `module com.example.target` with `open module com.example.target`, remove the separate `opens` line, and recompile. Explain why reflection into `Secret` still works.
4. Use `Module.getDescriptor()` to inspect `isOpen()` and the module's `exports()` list. Distinguish declared metadata from `Module.isExported(pkg, module)` runtime permissions.
5. Run `UnnamedDemo` on the classpath. Then package it into a named module, run with `-m`, and compare `getName()`.
6. For a library intended for the module path, review which packages truly need a public API and which truly need deep reflection before deciding between `exports` and `opens`.

**Takeaway:** `Class.getModule()` tells you which module a type belongs to; `Module.isNamed()` distinguishes named/unnamed; `module-info.java` controls **readability**, **exports**, and **opens**; and the `open module` keyword opens every package of a **named module** for deep reflection. When Reflection fails, pinpoint the **module owning the package**, the **calling module**, and the **missing permission type**.
