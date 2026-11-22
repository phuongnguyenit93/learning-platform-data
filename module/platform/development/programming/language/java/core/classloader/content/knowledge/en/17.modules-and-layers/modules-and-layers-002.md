# Named module, unnamed module, and automatic module in Java

Since Java 9, the Java Platform Module System (JPMS) adds the concept of a **module** to the process of finding, loading, linking, and controlling access to classes. The same JAR containing `com.example.Tool` can be seen as a **classpath component belonging to an unnamed module** or a **named automatic module** when placed on the module path; a JAR with a proper `module-info.class` is typically an **explicit named module**. Location, descriptor, and module resolution determine what a class can read/access — not just the JAR filename.

Three concepts to distinguish:

- **Named module:** a module with a defined name. It can be an *explicit named module* (declaring `module-info.java`) or an *automatic module* (a legacy JAR named by the module system when on the module path).
- **Unnamed module:** a **nameless** module that groups classes not belonging to any named module of **a defining class loader**; the classpath typically resides in the unnamed module of the application loader.
- **Automatic module:** **a kind of named module** for a JAR without a module descriptor when it appears on the **module path**, allowing the migration from the classpath to JPMS to take place incrementally.

This article belongs to the **Modules and layers** group of Java core – classloader. Goals: accurately explain each kind, a comparison table, **reads / exports / opens** rules, module path and classpath, module resolution, module-to-loader mapping, a compilable/runnable Java 17+ example, common migration errors, and how to design the modularization process.

## 1. How does a module differ from a package, a JAR, and a ClassLoader?

A **package** groups Java types by namespace (for example `demo.api`). A **JAR** is an archive format containing `.class` files, resources, and a manifest. A **ClassLoader** defines runtime types and has a class-finding policy. A **module** is a JPMS unit with a **name, a set of packages, dependency requirements (`requires`), exports, opens, and service declarations**.

They should not be conflated:

| Concept | Answers the question | Example |
| --- | --- | --- |
| Package | Which namespace does this class reside in? | `demo.api` |
| JAR | How are bytecode/resources physically packaged? | `legacy-tools.jar` |
| ClassLoader | Who defines the class and how does it find classes? | Application loader, plugin loader |
| Module | Which module does the class belong to; which modules does this module read; how are packages exported/opened? | `m.library`, `legacy.tools`, unnamed module |
| ModuleLayer | A set of resolved named modules along with parent layer relationships | `ModuleLayer.boot()` or an application layer |
| ModuleFinder/module path | Where does the runtime discover module artifacts? | `--module-path mods` |

**A JAR does not necessarily correspond to a named module.** On the classpath, multiple JARs typically contribute classes together to the unnamed module of the application loader. On the module path, each valid JAR is recognized as a separate module (explicit or automatic). A directory module artifact can contain an entire compiled named module.

**One module is not synonymous with one ClassLoader.** Multiple named modules of the boot layer can be defined by the same bootstrap, platform, or application loader; `ModuleLayer.defineModulesWithManyLoaders` is an API that explicitly creates one loader per module in a new layer.

## 2. Named module — a module with a name

A **named module** has a name obtained from a descriptor or the module naming mechanism. For an explicit named module, the developer writes `module-info.java`:

```java
module m.library {
    exports demo.api;
}
```

This is a **complete `module-info.java` file**, not a regular Java class. It declares:

- The module name is `m.library`.
- The package `demo.api` is **exported**, so modules that read `m.library` can access the valid public types/members of this package.
- Other packages in the module are **not automatically exported** externally.
- JPMS implicitly adds a dependency on `java.base` for normal modules.

Another module that uses the API can declare:

```java
module m.app {
    requires m.library;
}
```

`requires` establishes dependency/readability from `m.app` to `m.library` when modules are resolved. To use a public class in `demo.api`, `m.library` must also have **exported the corresponding package**.

### A named module can be explicit or automatic

The term *named* only states that it **has a name**; it does **not** by itself assert that the descriptor was written by the developer. An automatic module is also a named module, but it is created from an unmodularized JAR.

When precision is needed, use:

- **Explicit named module:** has a `module-info.class` module descriptor compiled from a module declaration (or an equivalent modular artifact).
- **Automatic named module:** its name/descriptor is derived by the module system for a **non-modular JAR placed on the module path**.

An explicit module can have `requires`, `requires transitive`, `requires static`, `exports`, `opens`, `uses`, and `provides` with explicit constraints. Do not assume that every named module exports all of its packages.

## 3. Unnamed module — the classpath without a module name

Each `ClassLoader` has **its own unnamed module**, queried via:

```java
Module unnamed =
        ClassLoader.getSystemClassLoader().getUnnamedModule();
System.out.println(unnamed.isNamed()); // false
System.out.println(unnamed.getName());  // null
```

This is an **illustrative snippet inside a Java method**. For the application class loader, a class placed on the classpath without participating in a named module typically has:

```java
Module m = MyClass.class.getModule();
System.out.println(m.isNamed());             // false
System.out.println(m.getDescriptor() == null); // true
```

This is also an **illustrative snippet**, assuming `MyClass` is on the classpath. An unnamed module **has no `module-info.java`/ModuleDescriptor**, and `Module.getLayer()` for an unnamed module is `null`.

### Readability and accessibility rules

According to Java SE 17, an unnamed module:

1. **Reads every module.** `Module.canRead(other)` from an unnamed module returns `true` for other modules, both named and unnamed.
2. **Exports all of its packages.** Those packages are treated as exported externally when evaluated by runtime APIs.
3. **Opens all of its packages.** It has no strong encapsulation at the module level; standard Java access rules and reflection rules still apply.
4. **Cannot be an explicit `requires` dependency** in `module-info.java` because it **has no name to write in `requires`**.
5. **Each loader manages only its own unnamed module.** The unnamed module of the system loader is different from the unnamed module of a plugin loader; there is no "single unnamed module for the entire JVM".

An easily misunderstood consequence: even though **an unnamed module reads named modules**, a module must still **be resolved** into the configuration/layer for the relevant classes to be present at runtime, and classpath code can only access packages that are **appropriately exported**. `canRead=true` does not automatically create JAR files on the classpath, does not automatically resolve arbitrary modules, and does not bypass exports or Java access checks.

### Why is it so easy for classpath code to depend on everything?

In a traditional Java application:

```bash
java -cp "out:lib/*" com.example.Main
```

classes from `out` and the JARs defined by the application class loader typically belong to the **same unnamed module of that loader**. Because an unnamed module reads every module and exports/opens all of its packages, it provides behavior close to the pre-Java 9 classpath model: minimal dependency declarations at the JPMS level, at the cost of making architectural boundaries hard to control.

The command above uses the `:` character for Linux/macOS; on Windows use `;`. Do not mistakenly think that the `lib/*` wildcard turns JARs into automatic modules: **their placement on the classpath** determines that they belong to the unnamed module, even though they are regular JARs.

## 4. Automatic module — a bridge for unmodularized JARs

A **non-modular JAR** without `module-info.class`, when placed on the **module path**, can be treated by the module system as an **automatic module**:

```text
lib/
└── legacy-tools.jar
      └── legacy/LegacyMessage.class
            |
            +-- placed via --class-path ---> unnamed module
            |
            +-- placed via --module-path --> automatic named module
                                           "legacy.tools"
```

Characteristics of an automatic module in Java 17:

- **Has a module name** derived from `Automatic-Module-Name` in the manifest if that attribute exists, otherwise from the JAR filename according to the ModuleFinder algorithm.
- **Does not require `module-info.class`**. If the JAR has a valid explicit module descriptor, it is an **explicit named module**, not an automatic one.
- **Treated as exporting and opening all packages** at runtime.
- **Reads all named modules resolved in the configuration**, and when created in the JVM also **reads all unnamed modules**.
- **Can be required (`requires`) by another explicit module by name**, for example `requires legacy.tools;`.
- Supports discovery of service providers from `META-INF/services` metadata according to the mechanism for automatic modules.
- **Still obeys module resolution constraints**, such as duplicate module names or split-package conflicts; it is not "the legacy classpath with unlimited access across every layer".

A specification detail: the `ModuleDescriptor` of an automatic module does not have explicit `exports`/`opens` directives like a developer-written descriptor. Exporting/opening every package is **how the module is treated by the runtime**, so do not infer from `descriptor.exports().isEmpty()` that its packages are closed. Use `module.isExported(...)` / `module.isOpen(...)` or properly understand the automatic modifier.

### Does an automatic module read the classpath?

**Yes, according to module readability rules:** an automatic module reads unnamed modules when instantiated. This is readability at the **module graph level**. However, sources/libraries still need to be placed on the appropriate path and loader, bytecode must be resolvable, and class-loading/module-access constraints still apply. One should not write that "an automatic module always sees every file on disk" or treat it as a replacement for configuring `--class-path`.

## 5. Direct comparison of the three kinds

| Criterion | Explicit named module | Automatic module | Unnamed module |
| --- | --- | --- | --- |
| Has a module name? | Yes | **Yes** | **No** (`getName()==null`) |
| Who provides the descriptor? | Author writes `module-info.java` or equivalent | JVM/module finder creates descriptor from non-modular JAR | No descriptor |
| Typical distribution | Modular JAR/directory on the module path; runtime image | Non-modular **JAR on the module path** | Class files/JARs on a loader's classpath |
| `isNamed()` | `true` | `true` | `false` |
| `getDescriptor().isAutomatic()` | `false` | **`true`** | Descriptor is `null` |
| Reads whom? | Declared modules / modules added by the module system | All resolved named modules and unnamed modules | All modules |
| Exports packages? | Only packages declared with `exports` or permitted by runtime configuration | All packages | All packages |
| Opens for deep reflection? | Only according to `opens`/`open module`/corresponding configuration | All packages | All packages |
| Can be used in `requires`? | Yes, by name | **Yes**, by name | **No**, because it has no name |
| Class identity scope | Binary name + defining loader; plus JPMS constraints | Similar | Similar |
| When to use? | True modularization, dependency/API control | Transitioning legacy JAR libraries to JPMS | Classpath applications/legacy frameworks |

**The name "automatic" does not mean the JVM automatically converts bytecode or rewrites code into a modular JAR.** It supplies a bridge descriptor/module name, while the class files remain the legacy class files.

**The name "unnamed" does not mean the package/class has no name.** The class `org.example.Service` still has a full binary name; **only the module containing that class has no module name**.

## 6. Key module readability edges

Suppose there are three modules:

```text
m.app (explicit named)
   |
   +-- requires m.library  ------> m.library (explicit named)
   |
   +-- requires legacy.tools ----> legacy.tools (automatic named)

Unnamed module of the application loader
   |
   +-- reads resolved named modules (and other modules)
   |
   +-- has no name for a named module to write "requires <unnamed>"
```

In the default model:

- `m.app` reads `m.library` and `legacy.tools` because of the `requires` declarations.
- `m.app` does **not automatically read** the unnamed module merely because there is a classpath on the command line.
- `legacy.tools`, being an automatic module, reads the unnamed module as well.
- The unnamed module reads `m.app`, `m.library`, and `legacy.tools` when they exist at runtime, but **does not have permission to bypass non-exported packages from an explicit module**.

To check at runtime:

```java
Module app = /* module m.app */;
Module api = /* module m.library */;
Module legacy = /* automatic module legacy.tools */;
Module unnamed = ClassLoader.getSystemClassLoader()
        .getUnnamedModule();

System.out.println(app.canRead(api));
System.out.println(app.canRead(legacy));
System.out.println(app.canRead(unnamed));
System.out.println(legacy.canRead(unnamed));
System.out.println(unnamed.canRead(app));
```

This is an **illustrative snippet**, not a standalone compilable file because the module variables must be obtained from an actual `ModuleLayer`. The complete executable example below verifies the special edges `app → unnamed` and `automatic → unnamed`.

### Do not confuse `reads` with `exports`

In JPMS:

- **`requires`/reads:** module A can reference public types in modules that it reads **if the package is appropriately exported**.
- **`exports`:** a package of module B allows modules reading B to use its valid public API.
- **`opens`:** allows deep reflection according to the opened scope; it does not turn every private member into a public source-level API.
- **`module-info.java`:** defines explicit relationships for explicit modules; that syntax does not apply to the unnamed module.

For example, `m.app requires m.library` is not sufficient to access `demo.internal.Hidden` if `m.library` does not export `demo.internal`. Conversely, B exporting a package does not give A a default read edge to B.

## 7. Complete Java 17+ example: three module kinds in the same application

This is an example **that has been compiled with `javac --release 17` and run**. It demonstrates that an automatic module is named, an explicit module `requires` it, an unnamed client can read **resolved** named modules, and the difference in read edges to the unnamed module.

### 7.1 Project structure

Create the `module-kinds-demo` directory:

```text
module-kinds-demo/
├── src/
│   ├── m.library/
│   │   ├── module-info.java
│   │   └── demo/api/Answer.java
│   └── m.app/
│       ├── module-info.java
│       └── demo/app/Main.java
├── legacy-src/
│   └── legacy/LegacyMessage.java
├── classpath/
│   └── UnnamedClient.java
├── mods/
│   ├── m.library/             (output)
│   └── m.app/                 (output)
├── legacy-classes/           (output)
├── lib/
│   └── legacy-tools.jar      (artifact generated by jar)
└── out/                       (output)
```

Create `mods/m.library`, `mods/m.app`, `legacy-classes`, `lib`, and `out` before compiling. Run the commands from **the `module-kinds-demo` directory**. Do not add `legacy-tools.jar` to the classpath when you want it to be recognized as an automatic module.

### 7.2 Explicit module `m.library`

File `src/m.library/module-info.java`:

```java
module m.library {
    exports demo.api;
}
```

File `src/m.library/demo/api/Answer.java`:

```java
package demo.api;

public final class Answer {
    public static String value() {
        return "Named";
    }
}
```

The descriptor exports `demo.api` to other modules that read `m.library`. The class `Answer` is public with a static method that is easy to call and has no side effects.

### 7.3 Legacy JAR without a module descriptor

File `legacy-src/legacy/LegacyMessage.java`:

```java
package legacy;

public final class LegacyMessage {
    public static String value() {
        return "Automatic";
    }
}
```

We will compile this class **without `module-info.java`** and then package a JAR named `legacy-tools.jar`. The module system derives the module name **`legacy.tools`** when the JAR file is on the module path.

### 7.4 Explicit module `m.app` depending on both

File `src/m.app/module-info.java`:

```java
module m.app {
    requires m.library;
    requires legacy.tools;
}
```

File `src/m.app/demo/app/Main.java`:

```java
package demo.app;

import demo.api.Answer;
import legacy.LegacyMessage;

public class Main {
    public static void main(String[] args) {
        System.out.println("main named: "
                + Main.class.getModule().isNamed());

        System.out.println("library module: "
                + Answer.class.getModule().getName());

        System.out.println("legacy automatic: "
                + LegacyMessage.class.getModule()
                        .getDescriptor().isAutomatic());

        System.out.println("values: "
                + Answer.value() + " + " + LegacyMessage.value());

        Module unnamed = ClassLoader.getSystemClassLoader()
                .getUnnamedModule();

        System.out.println("named reads unnamed: "
                + Main.class.getModule().canRead(unnamed));

        System.out.println("automatic reads unnamed: "
                + LegacyMessage.class.getModule().canRead(unnamed));
    }
}
```

`m.app` **requires the automatic module `legacy.tools` by name**, proving that an automatic module is a genuine named module rather than an unnamed one.

### 7.5 A client in the classpath/unnamed module

File `classpath/UnnamedClient.java`:

```java
import demo.api.Answer;
import legacy.LegacyMessage;

public class UnnamedClient {
    public static void main(String[] args) {
        System.out.println("client named: "
                + UnnamedClient.class.getModule().isNamed());

        System.out.println("named value: " + Answer.value());
        System.out.println("auto value: " + LegacyMessage.value());
    }
}
```

`UnnamedClient` has no `module-info.java` and is compiled/run with `-cp`. It cannot `requires` any module because it has no descriptor, but the unnamed module reads the resolved named modules.

### 7.6 Compiling the two foundational artifacts

**Step 1: compile the explicit `m.library`.**

```bash
javac --release 17 -d mods/m.library src/m.library/module-info.java src/m.library/demo/api/Answer.java
```

**Step 2: compile the legacy JAR and inspect the derived module name.**

```bash
javac --release 17 -d legacy-classes legacy-src/legacy/LegacyMessage.java
jar --create --file lib/legacy-tools.jar -C legacy-classes .
jar --describe-module --file lib/legacy-tools.jar
```

The important part of the `jar --describe-module` output:

```text
No module descriptor found. Derived automatic module.

legacy.tools automatic
requires java.base mandated
contains legacy
```

The ordering/extra lines in the output may depend on the `jar` version; what needs to be verified is **`legacy.tools automatic`** and the absence of a manually written module descriptor.

### 7.7 Compiling and running the named application

**Windows** (`;` separates module-path entries):

```bash
javac --release 17 --module-path "mods;lib/legacy-tools.jar" -d mods/m.app src/m.app/module-info.java src/m.app/demo/app/Main.java
java --module-path "mods;lib/legacy-tools.jar" --module m.app/demo.app.Main
```

**Linux/macOS** (`:` separates module-path entries):

```bash
javac --release 17 --module-path "mods:lib/legacy-tools.jar" -d mods/m.app src/m.app/module-info.java src/m.app/demo/app/Main.java
java --module-path "mods:lib/legacy-tools.jar" --module m.app/demo.app.Main
```

Verified stdout:

```text
main named: true
library module: m.library
legacy automatic: true
values: Named + Automatic
named reads unnamed: false
automatic reads unnamed: true
```

Explanation:

1. `Main` belongs to the explicit named module `m.app`.
2. `Answer` belongs to the named module `m.library`.
3. `LegacyMessage` belongs to the automatic named module `legacy.tools`; its descriptor has `isAutomatic()==true`.
4. `m.app` can use both APIs because it has `requires` and the appropriate packages are exported.
5. `m.app` does **not** have a read edge to the unnamed module merely because the Java launcher exists.
6. An automatic module **can read the unnamed module** according to the Java 17 specification.

This is direct evidence that **a regular named module and an automatic module do not have the same default readability**, even though both have a module name.

### 7.8 Compiling and running the unnamed client

When a classpath application uses classes in named modules, the target modules must be **resolved**. In this example, pass `--add-modules m.library,legacy.tools` to ensure the module graph includes them.

**Windows:**

```bash
javac --release 17 --module-path "mods;lib/legacy-tools.jar" --add-modules m.library,legacy.tools -d out classpath/UnnamedClient.java
java --module-path "mods;lib/legacy-tools.jar" --add-modules m.library,legacy.tools -cp out UnnamedClient
```

**Linux/macOS:**

```bash
javac --release 17 --module-path "mods:lib/legacy-tools.jar" --add-modules m.library,legacy.tools -d out classpath/UnnamedClient.java
java --module-path "mods:lib/legacy-tools.jar" --add-modules m.library,legacy.tools -cp out UnnamedClient
```

Verified stdout:

```text
client named: false
named value: Named
auto value: Automatic
```

Even though an unnamed module has no `requires`, it can use the exported public APIs of named modules **once those modules are resolved**.

**Note:** `--module-path` only makes artifacts **observable**; it does not mean every module is **resolved** by default in every launch mode. `--add-modules` is a way to explicitly add root modules. With `java --module m.app/...`, `m.app` is the root, and module resolution pulls in `m.library`/`legacy.tools` from the `requires` declarations.

## 8. Choosing the classpath or module path changes the nature of a JAR

A traditional JAR can reside:

**A. On the classpath:**

```bash
java -cp "out:lib/legacy-tools.jar" UnnamedClient
```

This command only **illustrates placement** on Linux/macOS; if `UnnamedClient` also needs `m.library`, that dependency must be provided separately (on the classpath or as an appropriately resolved named module). The key point: `legacy-tools.jar` on the **classpath** ⇒ the JAR's classes belong to the **unnamed module** of the corresponding defining loader, and it does not become an automatic module.

**B. On the module path:**

```bash
java --module-path "mods:lib/legacy-tools.jar" --add-modules m.library,legacy.tools -cp out UnnamedClient
```

Here, `legacy-tools.jar` is present on the module path and is resolved; `LegacyMessage.class.getModule().getName()` can return `"legacy.tools"`, and `getDescriptor().isAutomatic()` returns `true`.

**C. After the JAR is modularized:** if the author adds a valid `module-info.class` and packages the JAR as a modular artifact, it becomes an **explicit named module** when the module system reads that descriptor on the module path.

**Placement does not by itself turn Java 8 bytecode into Java 17 source:** an automatic module is a way for **JPMS to wrap module identity**, without modifying the contents of `LegacyMessage.class`.

## 9. How is an automatic module's name derived?

JPMS needs a **module name** so that an explicit module can declare `requires`. There are two prioritized sources:

1. The JAR's manifest has the **`Automatic-Module-Name`** attribute → use the declared value if valid.
2. If absent, the module system **derives the name from the JAR filename** according to standard rules: stripping the extension/version part algorithmically, converting appropriate separator characters, and producing a valid module name.

For example, with the artifact `legacy-tools.jar`, the derived name is `legacy.tools`. Different JAR names can produce different names, and renaming the artifact can **break every `requires old.name`**. Therefore, library publishers planning to move gradually toward JPMS should typically set a stable manifest attribute:

```text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.legacy
```

This is an **illustrative manifest excerpt**, not a file that needs to be written for the `legacy.tools` example that was run. If the attribute above is used, the module name will be `com.acme.legacy` instead of the name derived from the filename.

You can inspect the artifact before writing `requires`:

```bash
jar --describe-module --file lib/legacy-tools.jar
```

Do not infer a module name by guessing at all the hyphens/version numbers of a JAR, especially for artifacts that are repackaged, shaded, or renamed through a repository. Use the actual module descriptor/manifest.

### Automatic-Module-Name is not synonymous with an explicit module

The manifest attribute only provides the **name**; it does not explicitly declare `requires`, `exports`, or `opens`. While that JAR is an automatic module, the runtime still treats it as exporting/opening all packages and reading broadly according to automatic module rules. To turn it into a true explicit module, the author must supply a module descriptor, control packages/APIs, and verify dependency/service metadata.

## 10. When is an automatic module resolved?

A common source of confusion: placing a JAR on `--module-path` **does not guarantee** that every class in the JAR is present in the program's module graph.

Typically, a module is resolved when:

- It is a root module specified via `--module` or `--add-modules`.
- An already-resolved module declares `requires` on that module, causing resolution to follow the dependency.
- The launcher/build tool/module layer configuration explicitly adds root modules or uses an appropriate discovery mechanism.

In the example, `m.app requires legacy.tools;` causes the module to be automatically pulled into the graph when launching `m.app`.

For the classpath program `UnnamedClient`, which has no `module-info` to declare dependencies, we use:

```bash
--add-modules m.library,legacy.tools
```

This is a **command-line argument fragment**, not a standalone command. In addition, the Java launcher has special tokens such as `ALL-MODULE-PATH`, but **do not use `--add-modules ALL-MODULE-PATH` unconditionally in production** because it can resolve unnecessary modules, expose name/package conflicts, or create a complex dependency graph.

**Do not confuse the three states:** an artifact is on the module path → **observable**; an artifact is selected/pulled into the graph → **resolved**; a specific class is requested → the JVM/class loader **loads/defines** that class. The three steps do not occur at the same time and are not synonymous.

## 11. One unnamed module per ClassLoader

If custom plugin class loaders are used:

```text
Application loader
   └── unnamed module of the application loader

PluginLoader A
   └── unnamed module of A

PluginLoader B
   └── unnamed module of B
```

Each loader can define classes **not belonging to any named module**, and those classes are placed into **that loader's own unnamed module**.

Illustrative code snippet:

```java
ClassLoader a = new ClassLoader(
        ClassLoader.getSystemClassLoader()) { };
ClassLoader b = new ClassLoader(
        ClassLoader.getSystemClassLoader()) { };

System.out.println(a.getUnnamedModule().isNamed());
System.out.println(a.getUnnamedModule() == b.getUnnamedModule());
System.out.println(a.getUnnamedModule().canRead(b.getUnnamedModule()));
```

The snippet above can be placed inside `main` of a Java 17 class. Expected stdout:

```text
false
false
true
```

Explanation:

- Both A and B have unnamed modules, so `isNamed()` returns `false`.
- Two different loaders have **two distinct unnamed modules**.
- An unnamed module reads every module, so `canRead` between them returns `true`.

**Readability is not a mechanism for automatically finding classes from another loader**. If A defines `plugin.Type` itself, `B.getUnnamedModule().canRead(A.getUnnamedModule())` returning true **does not make B.loadClass("plugin.Type") automatically search down into A**. The class loader delegation/defining loader graph and module readability are two distinct relationships.

### Class identity still depends on the defining loader

Java runtime type identity consists of **binary name + defining class loader**, regardless of whether a module is named or unnamed. Two plugin loaders defining `plugin.Config` in two separate unnamed modules produce two different types, even though the package/class name matches.

Conversely, two named modules can share the same loader while still having **separate module names and exports/readability**. JPMS adds an access-control layer; it does not replace the JVM rules for type identity.

## 12. A named module cannot normally `requires` an unnamed module

This is an important architectural constraint during migration:

```java
module m.app {
    requires com.example.legacy;
}
```

This is valid **only when a module named `com.example.legacy` can be found and resolved by the module system**. A JAR solely on the classpath belongs to the unnamed module and has no module name to declare in `requires`.

Consequences:

- A **classpath application** can use the exported API of a resolved named module.
- An **explicit named module** cannot write `requires unnamed;` to formally depend on legacy code that remains only on the classpath.
- One transition path is to move the legacy JAR onto the **module path** as an automatic module with a stable name, and then `requires` it.
- The long-term path is to modularize the dependency into an explicit named module with deliberate descriptors/exports/opens.

The launcher option `--add-reads m.app=ALL-UNNAMED` can be used for special migration/debugging cases; however, this is an **externally added read edge**—it does not turn the unnamed module into a named module, does not automatically fix class loading, and does not turn legacy code into a fully declared JPMS dependency. Both compiler and runtime must be configured appropriately if both compilation and execution need this edge. Prefer a clearer module dependency structure for long-lived systems.

## 13. Exports, opens, and runtime reflection

A class can **be loaded** yet still **not be accessible** from another module. Three easily confused forms of access:

| Mechanism | Meaning |
| --- | --- |
| `requires x;` | Module can read module `x` |
| `exports p;` | Exports the public API in package `p` so reading modules can use it |
| `exports p to y;` | Exports package `p` only to module `y` |
| `opens p;` | Opens the package for deep reflection at runtime under the corresponding conditions |
| `opens p to y;` | Opens the package for reflection by module `y` |
| `open module x { ... }` | An explicit named module that opens its packages according to open-module rules |
| Automatic module | Treated by the runtime as **exporting and opening all packages** |
| Unnamed module | Treated by the runtime as **exporting and opening all packages** |

An example with a named module:

```java
module m.library {
    exports demo.api;
    opens demo.internal to m.framework;
}
```

This is an **illustrative descriptor**, assuming the packages and target modules exist. `m.framework` may need `opens` for deep reflection into `demo.internal`, whereas source-level access to public types still relies on `exports`.

**Do not call an automatic module a security sandbox mechanism:** because it exports/opens all packages, module encapsulation is very loose. An unnamed module has similarly broad behavior. And even with explicit modules, exports/opens do not provide comprehensive protection against malicious code in the same JVM.

### When encountering `InaccessibleObjectException`

If reflection code from the classpath tries `setAccessible(true)` on a private member in a package belonging to an **explicit module that is not open**, you may encounter `InaccessibleObjectException`. The fact that the unnamed module reads that module does not bypass `opens`. Use the public API, configure `opens` for the right module, or temporarily use `--add-opens module/package=ALL-UNNAMED` when genuinely necessary and you understand the risks.

## 14. Automatic modules during migration: useful, but not the end goal

**Benefits of an automatic module:**

1. Allows an explicit module to write `requires` for a library that does not yet have a descriptor.
2. Does not force immediate modification of the legacy library's source in a single migration pass.
3. Provides a module identity observable via `Class.getModule()` and module resolution.
4. Maintains compatibility at the class-files/JAR-packaging level when a library moves from the classpath to the module path.
5. Buys time to standardize API exports/opens and service declarations before fully switching to an explicit descriptor.

**Risks:**

- **Unstable automatic module names** if derived solely from artifact filename/version/renaming.
- **All packages are exported/opened**, weakening encapsulation, including implementation packages not intended as public API.
- **Split packages** or identical module names across multiple JARs can cause module resolution to fail.
- **Overly broad readability**: an automatic module can depend on named/unnamed modules without explicitly declared dependencies.
- **Service discovery** may rely on `META-INF/services` metadata; when converting to an explicit module, appropriate `uses`/`provides` declarations must be designed.
- **Classpath fallback is not unlimited**: package/module mappings and loader policies can prevent classes from being found in the legacy classpath manner.
- **Unmodularized transitive dependencies** may need to be handled layer by layer or grouped into automatic modules that the module graph can resolve.

**Suggested migration workflow:**

1. Inventory JARs, packages, and native libraries/services/reflection.
2. Run `jar --describe-module` to identify explicit vs. automatic status and module names.
3. Stabilize the module name via the `Automatic-Module-Name` manifest attribute if the library cannot be modularized yet.
4. Move a suitable subset of dependencies onto the module path rather than throwing all JARs in at once.
5. Explicitly declare `requires` in explicit modules and run integration tests.
6. Check for split-package errors, duplicate module names, deep reflection issues, and service loader issues.
7. Create an actual `module-info.java` for the library once dependencies and the API surface are established.
8. Keep `--add-reads`/`--add-opens`/`--add-exports` to the necessary minimum and plan to remove them when possible.

### What is a split package?

Two named modules containing the same package—for example, both `m.alpha` and `m.beta` containing `com.acme.util`—can make resolution or layer creation invalid depending on configuration/readability. Automatic modules are also subject to these checks; a JAR is not exempt merely for being "legacy".

The traditional classpath used to allow multiple JARs to contain classes in the same package of one unnamed module, whereas the module system wants clearer package ownership. When encountering a split package, you typically need to split packages, merge artifacts, perform controlled shading, or restructure dependencies — you cannot fix it merely by adding `requires`.

## 15. Module name, loader, and layer must be observed together

A runtime helper:

```java
static void inspect(Class<?> type) {
    Module module = type.getModule();
    System.out.println("class=" + type.getName());
    System.out.println("loader=" + type.getClassLoader());
    System.out.println("module=" + module.getName());
    System.out.println("named=" + module.isNamed());
    System.out.println("layer=" + module.getLayer());

    if (module.isNamed()) {
        System.out.println("automatic="
                + module.getDescriptor().isAutomatic());
    }
}
```

This is an **illustrative method**, which must be placed inside a class to compile. Do not call `module.getDescriptor().isAutomatic()` **when the module is unnamed**, because `getDescriptor()` can return `null` and cause a `NullPointerException`.

**Interpretation:**

- `module.getName()==null` → unnamed module.
- `module.isNamed()==true` and `getDescriptor().isAutomatic()==true` → automatic named module.
- `module.isNamed()==true`, descriptor is not automatic → another kind of named module (typically explicit).
- `module.getLayer()` is only relevant for a named module's layer; for unnamed it is `null`.
- `type.getClassLoader()` indicates the class's defining loader, **not the module name**.

Whenever debugging, separate at least three questions: **Which loader defined the class? Which module does it belong to? Which read/export/open edges exist in the module graph?**

### Useful diagnostic commands

```bash
jar --describe-module --file lib/legacy-tools.jar
java --module-path "mods:lib/legacy-tools.jar" --describe-module legacy.tools
java --module-path "mods:lib/legacy-tools.jar" --show-module-resolution --module m.app/demo.app.Main
```

The commands above are written with the Linux/macOS separator; on Windows change `:` to `;`. The `--show-module-resolution` option prints additional resolution lines to stderr/stdout before the application output depending on the launcher; use it to determine **which modules have been resolved**, not to prove that every class in a module has been loaded.

You can use `jdeps` to inspect JAR/module dependencies when preparing a migration. However, `jdeps` output must be cross-checked against reflective/service/native dependencies because static analysis cannot see every dynamic loading path.

## 16. Distinguishing common errors

| Error/symptom | Common cause | How to inspect/fix |
| --- | --- | --- |
| `module not found: legacy.tools` during `javac` | The JAR is not yet on the module path or the module name differs from what was expected | `jar --describe-module`, check the manifest/JAR filename and `--module-path` |
| `package ... is not visible` | Missing `requires`, package not exported, or module not resolved | Module descriptor/readability/exports and compiler options |
| `ClassNotFoundException` in a classpath program using a named module | The module artifact is only observable but not yet resolved, or the loader/path is wrong | `--add-modules`, module graph, defining loader |
| `IllegalAccessError` / `InaccessibleObjectException` | Module access restriction applies, often deep reflection into an explicit module | `exports`/`opens` or adjust the API |
| `FindException` / `ResolutionException` | Duplicate module name, split package, invalid module, or graph conflict | Audit module path/JAR packages |
| `NoClassDefFoundError` | Missing runtime dependency / linking / initialization failure | Compare compile vs. runtime module/class paths and check the cause |
| `ServiceConfigurationError` | Incorrect module `uses`/`provides` or `META-INF/services` | ServiceLoader API and corresponding metadata |
| Module name changes after renaming the JAR file | Automatic module name is derived from the filename | Add a stable `Automatic-Module-Name` or convert to an explicit module |
| Explicit module cannot use a classpath library | There is no `requires` for an unnamed module | Convert the dependency to automatic/explicit, or add an intentional read edge |
| Classes have the same name but casting fails | Different defining loaders create distinct runtime types | Print `Class.getClassLoader()`/`getModule()`, unify the API loader |

**Do not fix module errors by blindly adding `--add-opens ALL-UNNAMED`.** That option does not fix module-not-found errors, does not turn a classpath JAR into an automatic module, and does not resolve class identity conflicts.

## 17. Common misconceptions

| Misconception | Correction |
| --- | --- |
| "An automatic module is an unnamed module." | **False.** An automatic module is a **named module**; `isNamed()==true`. |
| "A JAR with a module name is always automatic." | If it has a `module-info.class` descriptor, it is typically an **explicit named module**. |
| "A JAR on the classpath still uses Automatic-Module-Name as a named module." | No; on the classpath it belongs to the unnamed module of the corresponding loader. |
| "Unnamed module means classes have no package." | No; a class in `com.acme` can still reside in an unnamed module. |
| "There is only one unnamed module in the JVM." | Each defining class loader has its own unnamed module. |
| "All named modules have the same `requires` behavior." | Automatic modules have uniquely broad readability; explicit modules rely on their descriptor and the module graph. |
| "An automatic module has all packages listed in `descriptor.exports()`." | It is **treated by the runtime** as exporting/opening all packages, without necessarily storing individual directives in the descriptor. |
| "If the module path contains a JAR, every class/JAR is immediately loaded." | You must distinguish **observable → resolved → class loading**. |
| "Since an unnamed module reads everything, it can read private fields of an explicit module." | No; `opens` and Java reflection access rules still apply. |
| "`requires m.library` makes `m.library`'s loader the parent." | No; module readability is distinct from parent classloader delegation. |
| "Automatic modules represent a complete modularization architecture." | They are a **migration bridge**, not yet enforcing tight package/dependency boundaries. |
| "You can write `requires unnamed;`." | No; an unnamed module has no module name. |

## 18. Self-check questions with answers

**1.** `legacy-tools.jar` does not contain `module-info.class`. If launched with `-cp lib/legacy-tools.jar`, which module do classes in the JAR belong to?

**Answer:** The unnamed module of the loader that defines the corresponding class. It does **not** automatically become an automatic module just because the JAR filename is valid.

**2.** If the JAR is placed on the module path and resolved, what kind of module is it?

**Answer:** An automatic named module if the JAR truly has no module descriptor. `getModule().isNamed()==true` and `getDescriptor().isAutomatic()==true`.

**3.** Does `Module.getName()==null` mean the class has no binary name?

**Answer:** No. Only the module is unnamed; the class can have a normal binary name such as `com.demo.Tool`.

**4.** Why is `m.app requires legacy.tools` valid even though `legacy-tools.jar` has no `module-info.java`?

**Answer:** When the JAR is an automatic module on the module path, the runtime creates a named module `legacy.tools`. An explicit module can write `requires` against that name.

**5.** Can `m.app` directly reference `com.legacy.Helper` that resides only on the classpath via `requires com.legacy;`?

**Answer:** There is no named module named `com.legacy` to resolve. You can move the JAR to the module path as an automatic module or design another migration approach; `--add-reads ...=ALL-UNNAMED` is a temporary workaround with limitations.

**6.** Which kind of module reads the unnamed module by default: automatic or explicit named?

**Answer:** An automatic module reads all unnamed modules according to the specification. An explicit named module does **not automatically** read the unnamed module, unless a read edge is added via appropriate configuration/API.

**7.** Does an unnamed module export and open all of its packages?

**Answer:** Yes, according to JPMS semantics. That does **not remove** Java visibility rules for private/protected members or unconditionally grant access across another explicit named module.

**8.** Why does `--module-path lib` not automatically guarantee that `legacy.tools` is in the module graph?

**Answer:** The module is only *observable* from the path; module resolution must select it as a root, pull it in via `requires`, or include it via another root rule. You can use `--add-modules legacy.tools` if a classpath application genuinely needs it.

**9.** How can you reliably inspect the automatic module name instead of guessing from the JAR filename?

**Answer:** Use `jar --describe-module --file artifact.jar` and check the `Automatic-Module-Name` manifest attribute. If the JAR has no descriptor yet, the name can be derived from the filename according to ModuleFinder rules.

**10.** `PluginLoader A` and `PluginLoader B` create two unnamed modules. Why can two classes with the same name still be two different types?

**Answer:** JVM type identity consists of binary name + defining loader. Unnamed module readability does not merge class definitions across loaders.

**11.** In the example output, why are both `main named: true` and `legacy automatic: true` true at the same time?

**Answer:** `m.app` is an explicit named module; `legacy.tools` is an automatic named module. Both are named, but their descriptors and readability differ.

**12.** If an internal package in an automatic module is currently accessed via deep reflection, what might change when the library is converted into an explicit module?

**Answer:** An automatic module has all packages opened. An explicit module by default opens only packages that are appropriately declared/opened; reflection code may encounter access errors if `opens`/corresponding configuration is missing. Migration testing is required.

## 19. Checklist for real-world projects

1. **Identify the artifact:** is the class in source output, a plain JAR, or a modular JAR?
2. **Identify placement:** `--class-path` or `--module-path`? Do not take filesystem location as proof of module type.
3. **Inspect the descriptor:** does `module-info.class` exist? Is there an `Automatic-Module-Name`? What does `jar --describe-module` report?
4. **Identify the runtime module:** do `clazz.getModule().getName()` and `isNamed()` match expectations?
5. **Check automatic status:** only call `getDescriptor().isAutomatic()` when the module is named.
6. **Check resolution:** is the module only observable or actually resolved? Is `--add-modules` or `requires` present?
7. **Check the graph:** which module reads which module? Is the required package exported?
8. **Check reflection:** does code needing deep reflection have appropriate opens?
9. **Check the loader:** which loader defined the class? Which loader's unnamed module is it?
10. **Check migration readiness:** are module names stable? Are there split packages, duplicate modules, or JNI/SPI dependencies?
11. **Check tests:** run both compile and runtime commands for JDK 17+; do not just compile and assume the module graph is right.
12. **Maintain architecture:** use automatic modules for transition, while moving toward explicit descriptors and clear dependency boundaries when the project is ready.

## Conclusion

**Named** means a module with a name; **unnamed** means a module without a name (each ClassLoader has its own unnamed module); **automatic** is a **special named module** derived from a non-modular JAR on the module path. **Placing an artifact on the classpath vs. module path**, choosing module roots, resolving the graph, and applying `reads/exports/opens` determine how classes interact in Java 17+.

When diagnosing issues, always distinguish three independent yet interrelated layers: **(1) where the JAR/class resides on the classpath/module path, (2) module type and the module graph/readability, and (3) the defining class loader and JVM type identity.** This is the foundation for modularizing legacy classpath projects without accidentally breaking dependencies or reflection.

**Official documentation:**

- [Java SE 17 — `java.lang.Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html) (named/unnamed, `getName`, `canRead`, `isExported`, `isOpen`).
- [Java SE 17 — `java.lang.module.ModuleDescriptor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleDescriptor.html) (automatic module modifier and how the runtime handles it).
- [Java SE 17 — `java.lang.module` package specification](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/package-summary.html) (module resolution, readability graph).
- [Java SE 17 — `java` launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html) (`--module-path`, `--module`, `--add-modules`, `--add-reads`).
- [Java SE 17 — JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html) (`Automatic-Module-Name`).
- [dev.java — Incremental Modularization with Automatic Modules](https://dev.java/learn/organizing/modules/automatic-module/) (guide to migrating legacy libraries).
