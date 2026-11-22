# Resources in a Named Module: Encapsulation Rules and `opens`

When migrating a Java application from the classpath to a **named module (JPMS, Java 9+)**, developers may encounter a situation where a `.properties` or `.txt` file **is already inside the JAR** and a class in the module can read it, yet `ClassLoader.getResourceAsStream()` returns `null`. This is not necessarily a path or packaging error: **resources in a package of a named module can be encapsulated**. Readability also depends on **the API being used**, **the caller's module**, and **whether the package is `opens` or not**.

This lesson explains resource naming, module/JAR structure, lookup via `Class`, `Module`, and `ClassLoader`, and the meaning of `exports` / `opens` / `open module` / `--add-opens`, followed by hands-on practice with a compilable and runnable Java 17+ project.

## 1. What are resources and named modules?

A **resource** is data loaded by an application at runtime: text, configuration, templates, images, schemas, translations, metadata, and so on. They usually sit alongside `.class` files in the output directory, in a JAR, or in a module image. A regular resource **is not a Java class**, and `javac` does not automatically copy all data files along with the source code.

A **named module** is a Java module with an explicit name, typically declared via `module-info.java` and placed on the module path or in an appropriate module layer. A module may contain:

```text
demo.resources (named module)
├── module-info.class
├── demo/
│   ├── app/
│   │   └── Main.class
│   └── assets/
│       ├── Anchor.class
│       └── note.txt
└── META-INF/
    └── build-info.txt
```

In the example above, there is a class `demo.assets.Anchor`, so **`demo.assets` is an actual package belonging to the module**. The file `demo/assets/note.txt` has a resource name associated with that package. Conversely, `META-INF/build-info.txt` lies outside a valid Java package (`META-INF` is not a Java package name), so it is not subject to encapsulation in the same way.

Do not conflate these three concepts:

- **Resource path**: a path separated by `/`, for example `demo/assets/note.txt`.
- **Package name**: a dot-separated name, for example `demo.assets`.
- **Module name**: for example `demo.resources`, which identifies the module namespace and part of the encapsulation policy.

A class loader can define classes belonging to multiple modules, but that **does not mean all resources in those modules are public as they were on the legacy classpath**.

## 2. Two kinds of encapsulation to separate: physical and access

A file can fall into four states:

| Is the file in the module output/JAR? | Is the resource name correct? | Is the package opened appropriately? | Can it be read by the API in use? |
|---|---|---|---|
| No | Any | Any | No |
| Yes | No | Yes | No, because the lookup name is wrong |
| Yes | Yes | No | **May return `null`** due to encapsulation |
| Yes | Yes | Yes | Readable, if the loader can locate the resource and there are no other I/O errors |

Therefore, **`null` does not prove that the file does not exist**. You must verify all of the following together: the artifact contents, the resource name, the package/module, and exactly which API/caller is making the request.

### The resource package rule according to `Module.getResourceAsStream`

For a resource such as `a/b/c/config.properties`, the package name is derived from the portion before the last `/`, namely `a.b.c`.

- If `a.b.c` **is a package belonging to the named module**, the resource `config.properties` is encapsulated. A caller in another module can only read it via `Module.getResourceAsStream` if the package is open to the caller's module.
- If the resource name **ends with `.class`**, the specification does not apply this resource encapsulation rule to that resource.
- If the resource name does not map to a package belonging to the module, the resource **is not encapsulated** by that rule. For example, `META-INF/MANIFEST.MF` has the component `META-INF`, which is not a Java package.
- Accessibility still requires the file to actually be present and found; opening a package does not make a missing resource appear.

**Specifically:** a `config/` directory containing a few files does not automatically become a package just because it exists in the JAR. In contrast, if `demo.assets` has a class belonging to the module, then `demo/assets/note.txt` is clearly a resource in the `demo.assets` package.

## 3. Three resource-reading APIs have different rules

### 3.1. `Class.getResourceAsStream` and `Class.getResource`

```java
InputStream relative =
        Anchor.class.getResourceAsStream("note.txt");

InputStream absolute =
        Anchor.class.getResourceAsStream("/demo/assets/note.txt");
```

This is an **illustrative snippet**, with `Anchor` in package `demo.assets` and a `note.txt` file present.

When using `Class`:

1. If the name **does not start with `/`**, Java prepends the package of the representing class: `"note.txt"` becomes `demo/assets/note.txt`.
2. If the name starts with `/`, the name is interpreted as an absolute path from the root of the resource space: `"/demo/assets/note.txt"` is normalized to `demo/assets/note.txt`.
3. If the class belongs to a **named module**, the lookup is directed to that module itself and follows the encapsulation rules of `Module.getResourceAsStream`. A caller in the **same module** can access resources in packages of its own module (a module opens its packages to itself); a caller in another module needs the package to be appropriately opened.

`Class.getResource` returns a `URL` or `null`; `Class.getResourceAsStream` returns an `InputStream` or `null`. Even if a resource exists, an I/O error can still occur when opening or reading the stream.

### 3.2. `Module.getResourceAsStream(String)`

```java
Module module = Anchor.class.getModule();
try (InputStream in =
        module.getResourceAsStream("demo/assets/note.txt")) {
    // Process in; may be null.
}
```

This API targets a **specific module** via a `Module` object and takes a `/`-separated resource name, with an optional leading `/`. Most importantly: **it checks whether the package is open to the caller's module**.

Within the same named module, module code can read its own module's resources without making the package public everywhere. If code in another module calls this API, the package containing the resource must be open to the **caller module** (either unconditionally open or via a matching qualified `opens`).

`Module.getResourceAsStream` declares `throws IOException`. Therefore, you should use `try-with-resources` and handle both `null` and actual I/O errors.

### 3.3. `ClassLoader.getResourceAsStream` / `getResource`

```java
ClassLoader loader = Anchor.class.getClassLoader();
InputStream in =
        loader.getResourceAsStream("demo/assets/note.txt");
```

This is an illustrative snippet; you must close the stream yourself if it is non-`null`.

**A critical point for named modules:** as of JDK 17, for a resource **not ending with `.class`** located in a package of a named module, `ClassLoader.getResource` / `getResources` / `getResourceAsStream` can only find the resource when the package is **opened unconditionally** — meaning open unconditionally to all modules.

This holds **even when the caller of `ClassLoader.getResourceAsStream` is in the same module**. The `ClassLoader` API does not use caller module context the way `Module.getResourceAsStream` does.

For the resource `demo/assets/note.txt` in module `demo.resources`:

- Without `opens demo.assets;` declared in the module: `Anchor.class.getResourceAsStream("note.txt")` called from the same module can read it, but `loader.getResourceAsStream("demo/assets/note.txt")` returns `null`.
- When `opens demo.assets;` is added to `module-info.java`, both lookup paths can find the resource.
- If you only use `opens demo.assets to some.consumer;`, that **does not make the package opened unconditionally**, so `ClassLoader.getResourceAsStream` is still not a reliable choice for this resource.

### Comparison table

| API | Resource name style | Lookup scope | `opens` rule for regular resources in a named module's package |
|---|---|---|---|
| `Anchor.class.getResourceAsStream("note.txt")` | Relative to Anchor's package | Module containing Anchor | Package must be open to caller module; calls from the same module succeed |
| `Anchor.class.getResourceAsStream("/demo/assets/note.txt")` | Absolute from resource root | Module containing Anchor | Same as above |
| `Anchor.class.getModule().getResourceAsStream("demo/assets/note.txt")` | Path within the module | The specified module | Package must be open to caller module; same module succeeds |
| `Anchor.class.getClassLoader().getResourceAsStream("demo/assets/note.txt")` | Path with `/`, no automatic package prefix | Via the class loader | Package must be **open unconditionally**, except for exceptions like `.class` |
| `ClassLoader.getSystemResourceAsStream("demo/assets/note.txt")` | Path with `/` | Via the system loader | Also subject to `ClassLoader`'s named-module resource rules |

No API "bypasses all module boundaries." Each API has its own *scope* and access rules.

## 4. How `exports`, `opens`, and `open module` differ

Consider the module descriptor:

```java
module demo.resources {
    exports demo.app;
    opens demo.assets;
}
```

This is an **example declaration**, not a separate file outside `module-info.java`.

| Declaration | Primary purpose | Sufficient for `ClassLoader.getResourceAsStream` to read `demo/assets/note.txt`? |
|---|---|---|
| No declaration for `demo.assets` | Encapsulates the package from other modules | No |
| `exports demo.assets;` | Allows reading modules to access public types/members | **No** — `exports` is not equivalent to `opens` |
| `exports demo.assets to consumer;` | Selectively exports the public API | No |
| `opens demo.assets;` | Opens the package unconditionally for deep reflection and resource access | **Yes**, if the resource exists |
| `opens demo.assets to consumer;` | Opens the package to the specified consumer | **No**, because it is not unconditional |
| `open module demo.resources { ... }` | Opens every package in the module | Yes for existing resource packages, but with broad permission scope |

**`exports` and `opens` are not interchangeable**:

- `exports` primarily governs access to **public Java types and members** for modules that read this module.
- `opens` opens a package for deep reflective access under JPMS rules and **directly affects resource lookup**.
- `opens ... to m1, m2;` opens only to a specific list of modules.
- `open module ...` opens all packages in the module; you should not choose it just to fix one `null` resource when opening a smaller package suffices.

Within the same module, Java code routinely uses non-`exports` packages directly and accesses its own resources via `Class`/`Module`. **There is no need to export a public API just to read an internal configuration file**.

### Is `--add-opens` equivalent to `opens p;`?

Not quite. For example:

```bash
java --add-opens demo.resources/demo.assets=ALL-UNNAMED \
     --module-path mods -m demo.resources/demo.app.Main
```

This option opens `demo.assets` **targetedly** to unnamed modules. It is not the same as an unconditional `opens demo.assets;` declaration. Therefore, do not assume `ClassLoader.getResourceAsStream` will find every resource in that package after `--add-opens`. For access within the module itself, using `Class`/`Module` is usually more accurate; if broad classloader-based lookup is needed, consider unconditional `opens` and evaluate the encapsulation implications.

**Do not use `--add-exports` instead of `--add-opens`** to work around encapsulation of non-`.class` resources.

## 5. Java 17+ experiment: the file exists, yet `ClassLoader` returns `null`

The following example runs in **named module** mode on Java 17+. It is structured clearly enough to distinguish **a missing resource error** from **an encapsulated resource**.

### 5.1. Project structure

```text
project/
├── src/
│   ├── module-info.java
│   └── demo/
│       ├── app/
│       │   └── Main.java
│       └── assets/
│           └── Anchor.java
├── resources/
│   ├── demo/
│   │   └── assets/
│   │       └── note.txt
│   └── META-INF/
│       └── build-info.txt
├── mods/                    (generated during compilation)
└── dist/                    (generated when creating the modular JAR)
```

There are two packages defined by code: `demo.app` and `demo.assets`. The resource `demo/assets/note.txt` resides in package `demo.assets`, whereas `META-INF/build-info.txt` does not belong to a valid Java package.

### 5.2. File `src/module-info.java`

```java
module demo.resources {
}
```

Initially, there are **no `exports` and no `opens`** so we can verify the default behavior. `Main` and `Anchor` belong to the same module, so code in the module can reference `Anchor` directly.

### 5.3. File `src/demo/assets/Anchor.java`

```java
package demo.assets;

public final class Anchor {
    private Anchor() {
    }
}
```

This class serves as a **package anchor** when calling `Anchor.class.getResourceAsStream("note.txt")`. We do not need to instantiate `Anchor`.

### 5.4. File `src/demo/app/Main.java`

```java
package demo.app;

import demo.assets.Anchor;
import java.io.InputStream;

public final class Main {
    private static boolean exists(InputStream in) throws Exception {
        if (in == null) {
            return false;
        }
        try (in) {
            return in.read() != -1;
        }
    }

    public static void main(String[] args) throws Exception {
        Module module = Anchor.class.getModule();
        ClassLoader loader = Anchor.class.getClassLoader();
        String name = "demo/assets/note.txt";

        System.out.println("named module: " + module.isNamed());
        System.out.println("Module API: "
                + exists(module.getResourceAsStream(name)));
        System.out.println("Class relative: "
                + exists(Anchor.class.getResourceAsStream("note.txt")));
        System.out.println("Class absolute: "
                + exists(Anchor.class.getResourceAsStream("/" + name)));
        System.out.println("ClassLoader API: "
                + exists(loader.getResourceAsStream(name)));
        System.out.println("META-INF resource: "
                + exists(loader.getResourceAsStream(
                        "META-INF/build-info.txt")));
    }
}
```

The `exists` method uses `try-with-resources` to close the stream and checks that the resource has at least one byte. The data files in this example will be created non-empty, so a `true` result cannot be confused with an empty resource. In real applications, name the method `read...` if you need to read/parse the entire file, rather than just running this check.

### 5.5. Data files

`resources/demo/assets/note.txt`:

```text
hello
```

`resources/META-INF/build-info.txt`:

```text
build=test
```

These two files are plain data files, **not** Java source files.

### 5.6. Compile and copy resources

The following commands use Bash on Linux/macOS, run from the `project` directory:

```bash
mkdir -p mods/demo.resources/demo/assets
mkdir -p mods/demo.resources/META-INF
mkdir -p dist

javac -d mods/demo.resources \
    src/module-info.java \
    src/demo/app/Main.java \
    src/demo/assets/Anchor.java

cp resources/demo/assets/note.txt \
   mods/demo.resources/demo/assets/note.txt

cp resources/META-INF/build-info.txt \
   mods/demo.resources/META-INF/build-info.txt
```

**Why is `cp` needed?** `javac` only compiles the specified `.java` files; it does not automatically pick up all `.txt` files from `resources/`. For the module to actually contain the config files, you must copy them into the output at the exact resource path or configure your build tool to do so.

Run command:

```bash
java --module-path mods -m demo.resources/demo.app.Main
```

**Exact stdout when the module does not declare `opens`:**

```text
named module: true
Module API: true
Class relative: true
Class absolute: true
ClassLoader API: false
META-INF resource: true
```

### 5.7. Why does the output look counterintuitive?

- `module.isNamed()` returns `true`: the code is running in a named module.
- `Module API: true`: the caller `demo.app.Main` belongs to **the very module containing the resource**, so `Module.getResourceAsStream` finds `demo/assets/note.txt`.
- `Class relative/absolute: true`: `Anchor.class` locates the resource within the same module; both relative and absolute syntax point to the right file.
- `ClassLoader API: false`: the file still exists; the difference is that package `demo.assets` is **not opened unconditionally**, so classloader-based resource lookup cannot see non-`.class` resources in that package.
- `META-INF resource: true`: the path does not belong to a Java package in the module, so package encapsulation rules do not block it.

**This is not a broken class loader bug.** Same project, same runtime, same absolute resource name, yet the APIs have different encapsulation rules.

### 5.8. Update `module-info.java` with `opens demo.assets;`

Edit **only `src/module-info.java`** in the example project to:

```java
module demo.resources {
    opens demo.assets;
}
```

Recompile the module descriptor and classes:

```bash
javac -d mods/demo.resources \
    src/module-info.java \
    src/demo/app/Main.java \
    src/demo/assets/Anchor.java

java --module-path mods -m demo.resources/demo.app.Main
```

The `.txt` files were already copied into the output directory and are not deleted by `javac` in the commands above.

**Stdout now:**

```text
named module: true
Module API: true
Class relative: true
Class absolute: true
ClassLoader API: true
META-INF resource: true
```

Simply adding **`opens demo.assets;`** flips `ClassLoader API` from `false` to `true`. This is a direct demonstration of the **unconditional opens** rule.

### 5.9. Package as a modular JAR and run again

After compiling the version with `opens`, package **the same output that already includes the resources**:

```bash
jar --create --file dist/demo.resources.jar \
    -C mods/demo.resources .

jar --list --file dist/demo.resources.jar

java --module-path dist -m demo.resources/demo.app.Main
```

The output of `jar --list` includes the key entries such as:

```text
module-info.class
demo/app/Main.class
demo/assets/Anchor.class
demo/assets/note.txt
META-INF/build-info.txt
```

The actual listing may also include `META-INF/MANIFEST.MF` or other metadata depending on the JAR tool. What you need to verify is that **both resources are actually present**, at the right paths, and that `module-info.class` has been packaged.

With the `opens` build, running from `dist/demo.resources.jar` produces **the exact same six lines of stdout** as in section 5.8. This is a packaging sanity check: if running from the `mods` directory succeeds but running from the JAR fails, look for the issue in the copy/resource packaging step rather than blaming `opens` by default.

## 6. Reading resources from another module

Suppose a named module `demo.consumer` needs to read `demo/assets/note.txt` located in module `demo.resources`. Using the API:

```java
Module provider = Anchor.class.getModule();
try (InputStream in =
        provider.getResourceAsStream("demo/assets/note.txt")) {
    // Caller is running in demo.consumer.
}
```

This is an **illustrative snippet** that compiles only when the consumer has access to reference `Anchor` or obtains the provider `Module` object through an appropriate mechanism.

If `demo.resources` has not opened `demo.assets` to the consumer, `getResourceAsStream` may return `null` even though the resource exists. Ways to open it include:

```java
module demo.resources {
    opens demo.assets to demo.consumer;
}
```

This declaration opens the package **selectively** to `demo.consumer`; you only need to name the target module. If the consumer directly imports the public class `Anchor`, you also need to consider **`exports demo.assets to demo.consumer;`** and module readability separately, because **`opens` does not implicitly declare a public compile-time API for the consumer**.

One way to reduce coupling between the consumer and internal packages is for the provider module to expose a **public resource-reading API** in an `exports`ed package. The provider code uses `Class`/`Module` internally to read its own resource and returns the data according to the API contract. That approach is usually safer than opening an internal package just so a consumer can look up files.

**Important note:** `opens demo.assets to demo.consumer;` is sufficient for `Module.getResourceAsStream` called by the consumer if all other conditions are met; however, it is **not sufficient** for classloader-based lookup rules that require **unconditional** opens.

## 7. Cases where resources are not in a package

Not every resource in a named module is encapsulated. For example:

```text
META-INF/services/com.example.Service
META-INF/build-info.txt
config/application.properties
demo/assets/note.txt
```

Look at where the actual Java packages live:

- `META-INF` is not a valid Java package; resources there are not subject to package encapsulation under `Module.getResourceAsStream`.
- `config/application.properties` is only treated as a resource in package `config` if `config` is actually a package of the named module. If there is no corresponding package in the module, the resource is not encapsulated by the package rule.
- `demo/assets/note.txt` is in package `demo.assets` when the module contains class `demo.assets.Anchor`; in that case, the `opens` rule applies.
- If a resource path ends with `.class`, the specification makes an exception for resource encapsulation. **This does not mean every `.class` is public for execution as a Java API**, because class visibility, module exports, and linking are separate mechanisms.

Do not treat moving files into `META-INF` as an arbitrary trick to bypass permissions. Choose locations based on the purpose of the data and the build/module contract; public and private resources should be designed intentionally.

### `META-INF/services` and `ServiceLoader`

In traditional classpath applications, service provider configuration usually lives under `META-INF/services/...`. In **named modules**, `ServiceLoader` also uses declarations in the module descriptor:

```java
module demo.provider {
    provides com.example.spi.Handler
        with com.example.provider.HandlerImpl;
}
```

This is an **illustrative syntax example**; it requires the appropriate types and modules to compile. Do not replace the named module `provides`/`uses` mechanism with the assumption that manually reading `META-INF/services` is equivalent to service loading via JPMS.

## 8. `open module` and CLI flags: at what level should you apply them?

A module can be declared as:

```java
open module demo.resources {
}
```

All packages of the module are opened unconditionally. Resource lookup via `ClassLoader` can see regular resources in the corresponding packages if they are present.

However, opening the entire module is usually **broader than necessary**: other code can also gain deep reflection access to all those packages. If only one package containing resources needs to be exposed, prefer:

```java
module demo.resources {
    opens demo.assets;
}
```

If the goal is solely **reading internal data**, there is an even better option that preserves encapsulation: **do not open it**; use `Anchor.class.getResourceAsStream(...)` or `Anchor.class.getModule().getResourceAsStream(...)` from code in the **same module**.

### Considerations with libraries/frameworks

Frameworks may use `ClassLoader.getResource(...)` or the thread context class loader to locate resources by path. When migrating a framework from the classpath to named modules, the fact that application code can read a resource via `Class` does not guarantee the framework can read it too.

Your approach must be based on the framework's actual API:

1. If the framework supports passing an `InputStream`, `URL`, or pre-read configuration, the provider can read it using `Class`/`Module` and pass it to the framework.
2. If the framework requires `ClassLoader.getResource` and the package containing the resource must be exposed, consider `opens p;` while being aware of the unconditional open scope.
3. If the framework loads service providers, annotations/metadata, or module layers, check the framework's dedicated JPMS support; do not tweak `exports`/`opens` by trial and error without understanding the caller.
4. If shared resources need to be independent of module packages, design the resource location/path in a valid public scope from the start.

## 9. Distinguishing packaging errors, path names, and module encapsulation

A practical diagnostic sequence:

**Step 1: Print the module and loader**

```java
Class<?> anchor = Anchor.class;

System.out.println(anchor.getModule().getName());
System.out.println(anchor.getModule().isNamed());
System.out.println(anchor.getClassLoader());
```

This snippet applies when `Anchor` is in scope. On the regular classpath, `getModule().isNamed()` may be `false` (unnamed module), so you should not blindly apply named-module rules.

**Step 2: Verify physical contents**

```bash
jar --list --file dist/demo.resources.jar
```

Look for the exact `demo/assets/note.txt`, `module-info.class`, and other resources. `javac` does not copy data files automatically; a build tool might be configured to ignore `resources/`.

**Step 3: Verify the resource name**

```java
Anchor.class.getResourceAsStream("note.txt");
Anchor.class.getResourceAsStream("/demo/assets/note.txt");
Anchor.class.getClassLoader()
    .getResourceAsStream("demo/assets/note.txt");
```

The first two (via `Class`) are equivalent in the example because `Anchor` is in `demo.assets`. `ClassLoader` requires a path from the root; it does not prepend the package and does not use a leading `/` like `Class`'s relative/absolute convention.

**Step 4: Verify the package and open state**

```java
Module module = Anchor.class.getModule();
String pkg = "demo.assets";

System.out.println(module.getPackages().contains(pkg));
System.out.println(module.isOpen(pkg));
System.out.println(module.isOpen(pkg, module));
```

For the module without `opens` in the experiment, the outputs are:

```text
true
false
true
```

Explanation: the package exists; it is **not opened unconditionally**; however, a module's package is considered open to **that module itself**. This is precisely the difference exhibited by the `ClassLoader` and `Module` resource APIs.

**Step 5: Pick the right API and open only the minimum required scope**

If the file is for internal module use, prefer the `Module`/`Class` APIs. If external code needs the resource, clearly decide which modules are allowed to read it and which API the framework uses. Only consider unconditional opens when classloader-based lookup is genuinely required for all callers.

## 10. Common misconceptions

1. **"If the file is already in the JAR, `ClassLoader.getResourceAsStream` must be able to read it."** False for resources in a package of a named module that is not opened unconditionally.
2. **"`exports p;` is enough for all resources in `p`."** False: `exports` primarily controls access to the public Java API and does not replace `opens` for resource encapsulation.
3. **"I'm calling `ClassLoader` from the same module, so it will always succeed."** False: classloader-based lookup requires unconditional package `opens` for non-`.class` resources in a named module.
4. **"`opens p to m;` is equivalent to `opens p;`."** False: one opens selectively, while the other opens unconditionally.
5. **"`Class.getResourceAsStream("note.txt")` searches from the root of the JAR."** False: without a leading `/`, it prepends the class's package.
6. **"`Module.getResourceAsStream` always searches the entire module graph."** False: the API reads resources **within the selected `Module` object**.
7. **"Resources under `META-INF` are implicitly a package in the module."** False: `META-INF` is not a Java package, so it is not encapsulated by the same rule.
8. **"`javac` automatically packages all `resources` files."** False: you must copy them or configure your build tool.
9. **"Being able to read a resource means the classes in that package are public/exported."** False: resource access and Java type access are two separate mechanisms.
10. **"`--add-opens ...=ALL-UNNAMED` opens the package unconditionally for all APIs."** False: it opens targetedly to unnamed modules.
11. **"A named module always lives in a JAR file."** False: a module can exist as an exploded module directory, a modular JAR, or a runtime image.
12. **"A `.class` resource is not encapsulated, so I can use any private/internal class."** False: the resource lookup exception does not bypass linkage, Java access control, or JPMS exports.
13. **"Returning `null` is always a Java module system bug."** False: wrong names, missing files, packaging mistakes, a different class loader, or resource path mismatches can also return `null`.

## 11. Build & packaging checklist for named module resources

- [ ] Have `module-info.java` and run with `--module-path ... -m module/class` when testing a named module.
- [ ] `javac` generated `module-info.class` and all classes under the correct package paths.
- [ ] Resource data files are copied into the **module output** with the exact names and paths.
- [ ] The modular JAR / exploded module actually contains the files after the build.
- [ ] Names passed to `Class.getResourceAsStream` follow the `/` rule for relative vs. absolute paths.
- [ ] Names passed to `Module.getResourceAsStream` use the path within the module.
- [ ] Names passed to `ClassLoader.getResourceAsStream` are `/`-separated paths without relying on relative package resolution.
- [ ] Know the package name derived from the resource and whether that package belongs to the module.
- [ ] Determine whether the caller is in the same module or a different module.
- [ ] Use `exports` only for public Java API needs; use `opens` when the package needs to be opened.
- [ ] Use **unconditional opens** only if a `ClassLoader`-based API genuinely needs resources in that package.
- [ ] Verify against the final artifact (JAR/module image), not just the IDE output directory.
- [ ] Close `InputStream` using `try-with-resources` to avoid resource leaks.

## 12. Self-check

**Question 1.** `demo.assets` is a package belonging to the named module `demo.resources`. The file `demo/assets/note.txt` exists. The module does not declare `opens`. Why can code inside the same module read it via `Anchor.class.getResourceAsStream("note.txt")`, while `Anchor.class.getClassLoader().getResourceAsStream("demo/assets/note.txt")` returns `null`?

**Answer:** `Class` performs a module-aware lookup and checks open permissions for the caller module (a module has permission to read its own data). `ClassLoader` only exposes regular resources in a named module's package if the package is opened **unconditionally**.

**Question 2.** Does adding `exports demo.assets;` fix the `ClassLoader` result in Question 1?

**Answer:** No. `exports` is not equivalent to `opens`; you need `opens demo.assets;` when using classloader-based lookup, or you should use another API with the appropriate scope.

**Question 3.** Does `opens demo.assets to demo.consumer;` allow the consumer to use `Module.getResourceAsStream`? Does it guarantee `ClassLoader.getResourceAsStream` will work?

**Answer:** It allows code in module `demo.consumer` to read the resource using the `Module` API (assuming the resource is found and other conditions hold). However, it does not open **unconditionally**, so it does not satisfy the requirement of classloader-based lookup for non-`.class` resources in this package.

**Question 4.** Why can `META-INF/build-info.txt` be read by `ClassLoader` in the example while `demo/assets/note.txt` cannot?

**Answer:** `META-INF` is not a valid Java package name; resources there are not subject to package encapsulation. `demo.assets` is a real package of the module and has not been opened unconditionally.

**Question 5.** If running from `mods/demo.resources` works, but after packaging the JAR the resource cannot be found, what should you check first?

**Answer:** Use `jar --list --file ...` to confirm the resource was copied into the modular JAR at the right path; check build resource copying before changing `opens`.

## 13. Mental model

```text
Want to read a resource in a named module:
                 |
                 v
Is the file in the module output/JAR at the right path?
          /                 \
        No                   Yes
         |                    |
  Fix packaging        Is the resource in an
                       actual package of the module?
                           /        \
                         No          Yes
                          |           |
                 Not encapsulated   Which caller/API?
                 by package rule      |
                                     +-- Class/Module:
                                     |     same module or
                                     |     package open to caller
                                     |
                                     +-- ClassLoader:
                                           package must be
                                           opened unconditionally
                                           (for non-.class resources)
```

**Summary of three principles:**

1. **Get the artifact and resource name right first:** if the file wasn't copied or the path is wrong, no `opens` will help.
2. **Named modules have resource encapsulation:** `Class`/`Module` take the caller module into account; `ClassLoader` requires unconditional `opens` for regular resources in a named module's package.
3. **Choose the smallest open scope that satisfies the API:** for internal module reads, use `Class`/`Module`; for public APIs, use `exports`; open a package for reflection/resources only when genuinely needed with the appropriate `opens`.

### Official references

- [Java SE 17 — Module.getResourceAsStream: module resource encapsulation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html#getResourceAsStream(java.lang.String))
- [Java SE 17 — Class.getResourceAsStream: relative paths and named modules](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getResourceAsStream(java.lang.String))
- [Java SE 17 — ClassLoader.getResource / getResourceAsStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#getResourceAsStream(java.lang.String))
- [Java Language Specification, `7.7.2: Module Declarations, exports and opens](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.2)
