# Readability, exports, and opens in the Java Module System

## 1. Three concepts, yet three different questions

The **Java Platform Module System (JPMS)**, introduced in Java 9, organizes packages into **named modules** with explicit dependency relationships and encapsulation levels. When module A needs to use code in module B, you must distinguish:

1. **Readability**: Does A **read** (`reads`) B? This relationship usually originates from `requires B;` in A's `module-info.java`.
2. **Exports**: Does B **export the package** containing the needed API to A? The `exports` keyword allows normal access to public/protected types and members according to Java access rules, where compile-time readability must still be valid.
3. **Opens**: Does B **open the package** to A for **deep reflection** at runtime? The `opens` keyword is a mechanism for frameworks/reflection to access constructors, methods, or fields that are not public using APIs such as `setAccessible(true)`.

Remember:

> `requires` answers **which module to read**; `exports` answers **which package is the API for normal code**; `opens` answers **which package allows deep reflection**.

The three mechanisms **do not replace one another**. Having permission to read a module does not mean having permission to import every internal package. Having `exports` does not mean having permission to access private fields via deep reflection. Having `opens` does not mean having `exports` at compile time.

Example:

~~~java
// module-info.java of the library
module com.example.lib {
    exports com.example.lib.api;
    opens com.example.lib.internal to com.example.app;
}
~~~

~~~java
// module-info.java of the application
module com.example.app {
    requires com.example.lib;
}
~~~

The application reads lib; package `com.example.lib.api` is used via normal imports; package `com.example.lib.internal` is not exported, yet allows `com.example.app` to perform deep reflection. Another package that is neither exported nor opened remains closed to the app.

## 2. Readability: the relationship between modules

In JPMS, the module graph is built by the resolver from observable named modules and module directives. A **readability** edge is directed:

~~~text
+---------------------+      requires       +-----------------------+
|   com.example.app   | ------------------> |   com.example.lib     |
|     consumer        |        reads        |      provider         |
+---------------------+                     +-----------------------+
~~~

`requires com.example.lib;` resides in the **consumer**'s descriptor, not in lib's. It creates the relationship where app reads lib when the modules are properly resolved. The reverse direction does not appear automatically.

Every named module always reads itself and has appropriate readability to `java.base` without needing to declare `requires java.base;`. However, a module being able to read B does **not** automatically make every class/package in B visible: exports/opens and Java accessibility must also be considered.

### Forms of requires

| Directive | Meaning | Scenario |
| --- | --- | --- |
| `requires lib;` | The current module reads lib. | The app uses the lib API directly. |
| `requires transitive lib;` | The current module reads lib; modules reading the current module gain additional readability to lib according to JPMS rules. | A facade API exposes types originating from lib. |
| `requires static lib;` | Dependency during the compile phase; the module is not required to be present at runtime solely because of this directive. | Optional integration, annotation/compile-only API. |

Example:

~~~text
module app    { requires facade; }
module facade { requires transitive model; }
module model  { exports model.api; }
~~~

In a properly resolved graph, app reads both facade and model through `requires transitive`. However, **reading** model does not automatically turn non-exported packages of model into public API.

Do not confuse "a JAR placed on the module path" with "a module already in the graph with a read edge". Whether a module is resolved also depends on the launcher/root modules and the module resolver. Libraries placed on the regular **classpath** belong to the unnamed module, unlike named modules on the module path.

### Inspecting readability via API

~~~java
Module app = Main.class.getModule();
Module lib = Greeting.class.getModule();
boolean reads = app.canRead(lib);
~~~

These are just illustrative Java expressions inside code that has the corresponding classes. `canRead` returns the runtime read relationship and does **not** indicate which packages are exported/opened. The `addReads` API can dynamically add a read edge under appropriate caller conditions; it should not be treated as a replacement for a proper descriptor in production.

## 3. Exports: the API surface for normal use

In the provider:

~~~java
module com.example.lib {
    exports com.example.lib.api;
}
~~~

In the consumer:

~~~java
module com.example.app {
    requires com.example.lib;
}
~~~

If `Greeting` in `com.example.lib.api` is a `public class` and the `hello()` method is public, app can do:

~~~java
import com.example.lib.api.Greeting;

// Inside a valid Java method:
String text = Greeting.hello();
~~~

**Note:** the snippets above are illustrative; each `module-info.java` resides in its own module, not in a single Java file.

`exports` operates at the **package level**. If a package is exported, its public types become part of the API surface according to Java access rules. `protected` still has to obey inheritance/access conditions; not just any code can access every protected member.

### Qualified exports

You can export selectively:

~~~java
module com.example.lib {
    exports com.example.lib.spi to com.example.app, com.example.tools;
}
~~~

Only the specified modules receive the export permission when the remaining conditions are met. The form `exports p;` is **unqualified**, whereas `exports p to A, B;` is **qualified**.

### Why is a public class in a hidden package still blocked?

~~~java
package com.example.lib.hidden;

public class Hidden {}
~~~

If module lib **does not export** `com.example.lib.hidden`, `Hidden` still cannot be imported normally from another named module just because it is declared public. The module boundary adds an extra layer of encapsulation beyond traditional Java modifiers.

The compiler may report that the package is not visible / not exported when the consumer tries to import it. Check **two separate conditions**: whether the consumer has an appropriate `requires` and whether the provider `exports` that package to the consumer.

## 4. Opens: granting deep reflection at runtime

The `opens` keyword grants deep reflection access to permitted modules:

~~~java
module com.example.lib {
    opens com.example.lib.internal;
}
~~~

The form above opens the package to any qualifying module. If only one framework/app needs access:

~~~java
module com.example.lib {
    opens com.example.lib.internal to com.example.app;
}
~~~

This is **qualified opens**: the package is opened to `com.example.app`, not to all modules.

### Opens is not compile-time exports

If lib only `opens com.example.lib.internal to com.example.app;` without **exporting** it, code in app cannot normally use direct import syntax for classes from `internal` at compile time:

~~~java
// COUNTEREXAMPLE: invalid import if the package is only opened and not exported
import com.example.lib.internal.Secret;
~~~

However, app code can look up the class by name and perform deep reflection on private members if the package is opened to the caller:

~~~java
Class<?> type = Class.forName("com.example.lib.internal.Secret");
var ctor = type.getDeclaredConstructor();
ctor.setAccessible(true);
Object value = ctor.newInstance();

var field = type.getDeclaredField("value");
field.setAccessible(true);
Object text = field.get(value);
~~~

This is an illustrative snippet inside a method that can throw reflection exceptions. Why include `ctor.setAccessible(true)`? Because the package is not exported at compile time; a public constructor of a class in a non-exported package does not automatically become a valid normal access call from another module. Deep reflection granted by opens handles that situation.

If the package is not open to the module of the code calling `setAccessible(true)`, Java may throw `java.lang.reflect.InaccessibleObjectException`. Calling `getDeclaredField(...)` may retrieve metadata, but the step of **bypassing access checks** is not automatically valid.

### Is exports enough for private reflection?

**No.** A package with `exports p;` allows using the public API according to Java access rules; it does not unconditionally grant permission to access private fields/constructors via `setAccessible(true)` from another module. Serialization, ORM, DI frameworks, or JSON libraries may require `opens p to framework.module;`, or may need to be redesigned to use public factories/getters.

### A subtlety in Module.isExported

The runtime API `Module.isExported(packageName, otherModule)` treats a package **open to otherModule** as **exported at runtime** to that module. Therefore:

- The descriptor only declares `opens p to A;`.
- `lib.isOpen("p", A)` is `true`.
- `lib.isExported("p", A)` **can also be `true` at runtime**.
- However, there is **no** `exports p;` directive in the module descriptor, so the compiler does not consider that package exported for direct code.

To confirm **exports that are genuinely declared**, use `lib.getDescriptor().exports()` on a named module that has a descriptor. Avoid looking only at `isExported` and inferring backward that `module-info.java` must contain an exports statement.

## 5. Comparison table of readability, exports, and opens

| Property | Readability | Exports | Opens |
| --- | --- | --- | --- |
| Unit | **module → module** edge | Package in provider | Package in provider |
| Typical declaration | `requires B;` in consumer | `exports p;` in provider | `opens p;` in provider |
| Selective variant | `requires transitive` or dynamic graph; no `requires ... to ...` | `exports p to A;` | `opens p to A;` |
| Allows importing public types at compile time? | **Necessary but not sufficient** | **Yes**, with a read edge and Java access rules | **No**, if only opens |
| Runtime public access | Read edge is one factor | Yes, according to the rules | An opened package is treated as runtime-exported to the receiving module |
| Allows deep reflection on private members | No | No | Yes, when opened to the right module and other reflection conditions are met |
| Status query API | `caller.canRead(provider)` | `provider.isExported(p,caller)` | `provider.isOpen(p,caller)` |
| Typical error | Module/package not visible | Package not exported | `InaccessibleObjectException` on `setAccessible(true)` |

In a program, **readability + package access + Java member access** work together. Do not use any one of the three columns to draw conclusions in place of all the remaining columns.

## 6. Standalone Java 17+ example with two named modules

This lesson builds two real modules instead of simulating with the classpath:

- `com.example.lib` has an exported public API package, an internal package opened **only to app**, and a hidden package that is neither exported nor opened.
- `com.example.app` declares `requires com.example.lib;`, calls the public API, attempts to read a private field in internal, and then proves that hidden is blocked.
- The module layer and module descriptor are observed directly.

### Structure

~~~text
example/
└── src/
    ├── com.example.lib/
    │   ├── module-info.java
    │   └── com/example/lib/
    │       ├── api/Greeting.java
    │       ├── internal/Secret.java
    │       └── hidden/Hidden.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
~~~

### File `src/com.example.lib/module-info.java`

~~~java
module com.example.lib {
    exports com.example.lib.api;
    opens com.example.lib.internal to com.example.app;
}
~~~

### File `src/com.example.lib/com/example/lib/api/Greeting.java`

~~~java
package com.example.lib.api;

public class Greeting {
    public static String hello() {
        return "Hello from exported API";
    }
}
~~~

### File `src/com.example.lib/com/example/lib/internal/Secret.java`

~~~java
package com.example.lib.internal;

public class Secret {
    private String value = "opened-secret";
}
~~~

### File `src/com.example.lib/com/example/lib/hidden/Hidden.java`

~~~java
package com.example.lib.hidden;

public class Hidden {
    private String value = "hidden-secret";
}
~~~

Both classes `Secret` and `Hidden` are public, yet their packages are not exported; only `internal` is selectively opened.

### File `src/com.example.app/module-info.java`

~~~java
module com.example.app {
    requires com.example.lib;
}
~~~

### File `src/com.example.app/com/example/app/Main.java`

~~~java
package com.example.app;

import com.example.lib.api.Greeting;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

public class Main {
    private static String readPrivate(String name) throws Exception {
        Class<?> type = Class.forName(name);

        Constructor<?> constructor = type.getDeclaredConstructor();
        constructor.setAccessible(true);
        Object instance = constructor.newInstance();

        Field field = type.getDeclaredField("value");
        field.setAccessible(true);
        return (String) field.get(instance);
    }

    public static void main(String[] args) throws Exception {
        Module app = Main.class.getModule();
        Module lib = Greeting.class.getModule();

        System.out.println("app reads lib: " + app.canRead(lib));
        System.out.println("api exported to app: "
                + lib.isExported("com.example.lib.api", app));

        System.out.println("internal explicitly exported: "
                + lib.getDescriptor().exports().stream()
                    .anyMatch(e ->
                            e.source().equals("com.example.lib.internal")));

        System.out.println("internal opened to app: "
                + lib.isOpen("com.example.lib.internal", app));
        System.out.println("internal unqualified open: "
                + lib.isOpen("com.example.lib.internal"));
        System.out.println("hidden opened to app: "
                + lib.isOpen("com.example.lib.hidden", app));

        System.out.println("api: " + Greeting.hello());
        System.out.println("internal private: "
                + readPrivate("com.example.lib.internal.Secret"));

        try {
            readPrivate("com.example.lib.hidden.Hidden");
            System.out.println("hidden unexpected success");
        } catch (java.lang.reflect.InaccessibleObjectException expected) {
            System.out.println("hidden private: blocked");
        }

        System.out.println("app layer is boot: "
                + (app.getLayer() == ModuleLayer.boot()));
        System.out.println("lib in same layer: "
                + (lib.getLayer() == app.getLayer()));
    }
}
~~~

### Compile and run on Linux/macOS

From inside the `example` directory:

~~~bash
mkdir -p out
javac --release 17 --module-source-path src -d out \
  $(find src -name '*.java')

java --module-path out \
  --module com.example.app/com.example.app.Main
~~~

### Compile and run on Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
$sources = @(Get-ChildItem -Path src -Filter *.java -Recurse |
    ForEach-Object { $_.FullName })

javac --release 17 --module-source-path src -d out $sources
java --module-path out --module com.example.app/com.example.app.Main
~~~

`--module-source-path src` takes modules from the `src/<module-name>/` directories; `-d out` places them into the corresponding modular output. Use `--module-path out` and `--module com.example.app/com.example.app.Main` at runtime so that JPMS actually resolves named modules, rather than mistakenly loading them like classpath/unnamed modules.

### Verified stdout (OpenJDK 21, Java 17-compatible source)

~~~text
app reads lib: true
api exported to app: true
internal explicitly exported: false
internal opened to app: true
internal unqualified open: false
hidden opened to app: false
api: Hello from exported API
internal private: opened-secret
hidden private: blocked
app layer is boot: true
lib in same layer: true
~~~

Meaning of the lines:

1. `app reads lib: true`: the `requires` directive is in effect.
2. `api exported to app: true`: the provider exports the API.
3. `internal explicitly exported: false`: the descriptor has no `exports` for internal; it is **only opened**.
4. `internal opened to app: true`: qualified opens targets the exact consumer.
5. `internal unqualified open: false`: internal is **not** open to all modules.
6. `hidden opened to app: false`: hidden is not permitted for deep reflection.
7. `api: Hello from exported API`: the public API can be used normally.
8. `internal private: opened-secret`: deep reflection into the private field succeeds thanks to opens.
9. `hidden private: blocked`: `setAccessible(true)` encounters `InaccessibleObjectException` because the package is closed.
10. Both layer lines are `true`: in the launcher example, both app and lib are in the **boot module layer**.

**Note:** the example requires both `constructor.setAccessible(true)` and `field.setAccessible(true)`. The code does not assume that a public class in an opened-only package automatically has a public constructor that can be called directly via normal access.

## 7. Readability does not automatically export; exports does not automatically grant readability

Normal access conditions between named modules are viewed in layers:

~~~text
A reads B
   +
B exports package p to A
   +
Java type/member accessibility
   =
A can reference APIs in p according to normal rules
~~~

A declares `requires B;` while B does not export `p.internal`? A cannot publicly import types in p.internal merely through a read edge.

Conversely, B has `exports p.api;` while A does not read B? An exports directive in B does not automatically add `requires B;` to A. This difference becomes even more important when migrating legacy code from the classpath to the module path.

Reflection has its own runtime rules and class-lookup APIs; `Class.forName` can find a `Class<?>` object even when a compile-time import is invalid, but that **does not prove** you are allowed to call every constructor/method or read private fields. Test access according to the specific API/runtime policy.

## 8. Qualified opens, open module, automatic modules, and unnamed modules

### Qualified and unqualified

~~~java
module lib {
    exports lib.api to consumer;
    opens lib.internal to framework.core;
}
~~~

Only consumer receives the export of `lib.api`, and only framework.core receives deep reflection for `lib.internal`. For multiple authorized modules, separate names with commas.

### Open module

~~~java
open module lib {
    exports lib.api;
}
~~~

`open module` enables deep reflection on all packages of the module according to runtime rules, but **does not automatically export all packages for compile-time imports**. Packages that serve as normal APIs still need exports if there are consumers. Inside an open module, do not declare `opens p;` individually because everything is already opened.

### Automatic module

A qualifying JAR placed on the module path without a descriptor can be treated by the resolver as an **automatic module**. This type of module has broad compatibility rules for readability and exporting/opening packages. It is useful during migration, but should not be a reason to forego designing clear boundaries for named modules in the long term.

### Unnamed module

Classes on the regular classpath belong to the **unnamed module** corresponding to their loader. An unnamed module reads other modules and treats its own packages as exported/opened; however, a named module cannot simply write `requires unnamed;` to read back into an unnamed module. This is why new designs should prioritize explicit module boundaries.

## 9. ModuleLayer and ClassLoader are two different layers

In multi-plugin systems, learners easily equate **modules** with **class loaders**:

- **ClassLoader** finds or defines classes by binary name and delegation policy.
- **Module resolution/readability** determines which named modules are present in the graph and who reads whom.
- **Exports/opens** determine package usage permissions by access type.
- **ModuleLayer** groups resolved modules into a layer, with relationships to parent layers and mappings to class loaders.

**One loader can be associated with multiple modules.** Sharing the same class loader does not mean modules A and B automatically read each other, nor does it mean B's internal packages are automatically open to A. Conversely, two different class loaders do not automatically create a new ModuleLayer.

Example runtime observation API:

~~~java
Module current = Main.class.getModule();
Module library = Greeting.class.getModule();

System.out.println(current.canRead(library));
System.out.println(library.isExported("com.example.lib.api", current));
System.out.println(library.isOpen("com.example.lib.internal", current));
System.out.println(current.getLayer());
System.out.println(Greeting.class.getClassLoader());
~~~

This is an illustrative snippet, not a complete program. `getDescriptor()` can be `null` for an unnamed module; `getLayer()` can be `null` in contexts not belonging to a layer. In the boot-layer example, the two modules share the same layer, yet each package still follows its own access rules.

If you want plugins in a new layer, you must use the module resolution APIs and create an appropriate layer. Simply creating `new URLClassLoader(urls, parent)` does not automatically resolve module-info into a graph of named modules as you intend.

## 10. Launcher flags: --add-reads, --add-exports, --add-opens

When integrating legacy libraries or diagnosing issues, the Java launcher provides options to extend the graph/access at runtime:

~~~text
--add-reads consumer=provider
--add-exports provider/package.name=consumer
--add-opens provider/package.name=consumer
~~~

These are **syntax templates**; replace the module and package names according to the actual case.

| Option | Primary purpose | Does not automatically do |
| --- | --- | --- |
| `--add-reads A=B` | Adds a readability edge from A to B at runtime | Does not export or open B's packages. |
| `--add-exports B/p=A` | Grants export of package p from B to A at runtime | Does not allow reflection on private members like opens does. |
| `--add-opens B/p=A` | Allows deep reflection from A into package p of B at runtime | Does not add a compile-time exports directive to the descriptor. |

For the runnable example in section 6, you can intentionally open the hidden package to app with:

~~~bash
java --module-path out \
  --add-opens com.example.lib/com.example.lib.hidden=com.example.app \
  --module com.example.app/com.example.app.Main
~~~

This command **changes the test condition**: reflection on Hidden can succeed, and the code will print the line `hidden unexpected success` because it does not enter the catch branch. This is an illustration of the effect of a runtime override, not a baseline result.

Some syntaxes accept the special target `ALL-UNNAMED` to grant permission to classpath code. The scope can be very broad, so evaluate the impact before using it. For long-term applications, prefer proper descriptors or an appropriate API architecture rather than relying indefinitely on flags that open internal packages.

Runtime APIs such as `Module.addReads`, `addExports`, and `addOpens` have rules checking the calling module and existing permissions; it must not be assumed that an arbitrary module can modify any other module at will.

## 11. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Compiler cannot see a module | The module is unresolved or the consumer is missing requires. | Inspect module-info.java and the module path. |
| Compiler reports package is not visible | The provider does not export the package to the consumer. | Add selective exports if that package is genuinely an API. |
| Runtime IllegalAccessError | Access/linkage conditions no longer hold for the runtime graph and version. | Compare module descriptors, runtime module path, and override flags. |
| `InaccessibleObjectException` on `setAccessible(true)` | The package is not opened to the caller module. | Use a public API or appropriate qualified opens. |
| Public class found, but constructor is rejected | The package is not properly exported/opened, or the member is not accessible. | Check package access and setAccessible according to the contract. |
| Runs only when `--add-opens` is present | Runtime configuration is temporarily opening the package. | Design module-info properly or eliminate the need for deep reflection. |
| `isExported(p,A)` is true even though the descriptor has no exports | The package is opened to A, so it is treated as runtime-exported. | Check `isOpen` and `getDescriptor().exports()`. |
| `requires transitive` is present, yet import still fails | The package on the transitive module side is not exported. | Inspect both readability and exports. |
| Adding a JAR to the module path still fails to find the class | The module is unresolved, or classpath/module path are confused. | Check launcher flags and resolution roots. |
| Two modules use the same ClassLoader, yet private reflection fails | A shared loader does not automatically grant opens permission. | Check module identity, layer, and package opens. |

### Diagnostic checklist

1. Which module does the class belong to? Use `clazz.getModule()` and `isNamed()`.
2. Does the consumer read the provider? `consumer.canRead(provider)`.
3. Does the provider export the package to the consumer? `provider.isExported(p,consumer)` and **descriptor exports** if asking about compile-time.
4. Does the code require private deep reflection? `provider.isOpen(p,consumer)`.
5. Does `opens`/`exports` have `to moduleName`? What is the actual module name of the caller?
6. Does the run command have the appropriate `--module-path` and `--module`? Are any `--add-*` flags used?
7. Which layer and class loader is the class in? Do not infer modules solely from classpath filenames.
8. Are you mixing normal API access with reflective access in the same assertion?

## 12. Review questions

**Question 1.** A declares `requires B;` but B does not export package `b.internal`. Can A import a public class in `b.internal`?

**Answer:** No. Readability is not equivalent to package exports.

**Question 2.** B `exports b.api;` to A. Can you automatically call `setAccessible(true)` on a private field inside b.api from A?

**Answer:** Not simply because of exports. Deep reflection requires opens/appropriate reflection conditions.

**Question 3.** B `opens b.internal to A;` without exporting it. Can A import the class directly?

**Answer:** Not at compile time. However, deep reflection from A can succeed at runtime.

**Question 4.** Why can `isExported("b.internal", A)` be true even though the descriptor has no exports?

**Answer:** The Module API treats a package opened to A as runtime-exported to A. Use descriptor exports to determine compile-time declarations.

**Question 5.** Does sharing the same ClassLoader cause two named modules to access each other's private fields?

**Answer:** No. Class loader identity is distinct from module access; opens must still satisfy JPMS rules.

## Authoritative references

- [JLS Java SE 21 §7.7 – Module Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7): requires/readability, exports, opens, and transitive.
- [JLS Java SE 21 §7.7.2 – Exported and Opened Packages](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7.2): compile-time vs runtime access and deep reflection.
- [Java SE 21 java.lang.Module](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): canRead, isExported, isOpen, descriptor, layer.
- [Java SE 21 ModuleLayer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html): layers and class loader mappings.
- [Java SE 21 java launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): module path and add-reads/add-exports/add-opens flags.
