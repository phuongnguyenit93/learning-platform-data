# Named modules do not automatically read unnamed modules

In the Java Platform Module System (JPMS), code on the classpath belongs to an **unnamed module**. A named module has an explicit name in `module-info.java`, whereas an unnamed module has no module name to declare in `requires`.

This difference leads to an important rule: **an unnamed module can read named modules in the boot layer according to JPMS rules, but a named module does not automatically read unnamed modules**. Therefore, a legacy library on the classpath can be used normally by classpath code, but when the application is migrated to a named module, that module may not be able to access the library.

Understanding this rule properly helps explain errors when moving from the classpath to the module path and choose the right approach for integrating legacy libraries.

## 1. Where does an unnamed module come from?

A Java program run via the classpath can be launched as follows:

~~~bash
java --class-path app.jar:legacy-library.jar com.acme.app.Main
~~~

Classes loaded from the classpath by a class loader belong to the unnamed module associated with that class loader. An unnamed module:

- Has no module name such as `com.acme.app`.
- Has no `module-info.class` file describing dependencies.
- Exports all of its packages according to unnamed module rules.
- Has broad readability according to JPMS rules: an unnamed module reads named modules in the boot layer and unnamed modules.

In a typical application, libraries placed on the classpath are loaded by the application class loader and belong to that class loader's unnamed module. At the API level, this can be checked with `Class.getModule()`.

For example:

~~~java
Module module = Main.class.getModule();

System.out.println(module.isNamed()); // false
System.out.println(module.getName()); // null
~~~

The result `isNamed() == false` indicates that the class belongs to an unnamed module.

Note: an unnamed module is tied to a class loader. If an application has multiple class loaders, each class loader has its own unnamed module. You should not assume that the entire classpath across all class loaders in the JVM always belongs to a single unnamed module.

## 2. Named modules and unnamed modules do not have automatic bidirectional readability

Suppose an application has two parts:

- `com.acme.app`: a named module, declared with `module-info.java`.
- `legacy-library.jar`: a legacy library placed on the classpath, belonging to an unnamed module.

The graph can be visualized as:

~~~text
Unnamed module  ──reads──>  named modules in the boot layer

Named module    - - -X- - -> unnamed module
                 does not automatically read
~~~

A named module cannot write:

~~~java
module com.acme.app {
    requires unnamed;
}
~~~

because an unnamed module has no name to put into a `requires` directive.

Even when `legacy-library.jar` is present in `--class-path`, that does not automatically create readability from `com.acme.app` to the unnamed module. The classpath specifies where to find classes; it does not replace module relationships declared in the module graph.

### Why does old classpath code still run?

In an application running entirely on the classpath, classes belong to the unnamed module. The unnamed module can read named modules in the boot layer and other unnamed modules according to platform rules. Thus, legacy code can use libraries on the classpath without needing a descriptor.

When only part of an application is converted into a named module, the dependency direction changes. A named module must have an explicit readability relationship to its dependency. If the dependency remains on the classpath, it belongs to an unnamed module, and the named module cannot automatically read it.

This is a common difference encountered when modularizing legacy applications.

## 3. Example error when a named module uses a library on the classpath

Suppose the legacy library has the class:

~~~java
package com.legacy.format;

public final class LegacyFormatter {
    private LegacyFormatter() {
    }

    public static String format(String value) {
        return "[legacy] " + value;
    }
}
~~~

The library is packaged into `legacy-library.jar` and placed on the classpath.

The new application has a named module:

~~~java
module com.acme.app {
}
~~~

Application code:

~~~java
package com.acme.app;

import com.legacy.format.LegacyFormatter;

public class Main {
    public static void main(String[] args) {
        System.out.println(LegacyFormatter.format("JPMS"));
    }
}
~~~

If you only add the JAR to the classpath during compilation and execution, the named module `com.acme.app` still does not automatically read the unnamed module containing `LegacyFormatter`. The compiler may report that the package is not visible or not read by the module; at runtime, the required readability relationship is also absent.

This is not an error caused by `LegacyFormatter` lacking `public`. The class can be public and the package can exist on the classpath, yet the named module still needs permission to read the module containing that class.

## 4. Using --add-reads to create temporary readability

When you need to integrate a legacy library that cannot yet be converted into a named module, you can add a readability relationship using the `--add-reads` option.

Syntax:

~~~text
--add-reads source-module=target-module
~~~

When the target is unnamed modules, use the special name `ALL-UNNAMED`:

~~~text
--add-reads com.acme.app=ALL-UNNAMED
~~~

This allows the named module `com.acme.app` to read the appropriate unnamed modules in the runtime configuration. `ALL-UNNAMED` is a special token for launcher/compiler options, not a module name that can be declared in `module-info.java`.

### Compilation

Suppose the directory structure is:

~~~text
project/
├── legacy-library.jar
├── src/
│   └── com.acme.app/
│       ├── module-info.java
│       └── com/acme/app/Main.java
└── mods/
    └── other dependency modules
~~~

You can compile the app module with the legacy classpath and add readability:

~~~bash
javac \
  --module-path mods \
  --class-path legacy-library.jar \
  --add-reads com.acme.app=ALL-UNNAMED \
  --module-source-path src \
  -d out \
  -m com.acme.app
~~~

`--class-path` places the legacy library where the compiler searches for classes. `--add-reads` allows the module being compiled to read the corresponding unnamed module.

### Running the application

At runtime, you must provide the classpath and readability configuration again to the JVM:

~~~bash
java \
  --module-path out:mods \
  --class-path legacy-library.jar \
  --add-reads com.acme.app=ALL-UNNAMED \
  --module com.acme.app/com.acme.app.Main
~~~

Output:

~~~text
[legacy] JPMS
~~~

On Windows, the separator for multiple paths in classpath/module path is a semicolon (`;`); on Linux and macOS, it is a colon (`:`).

Permissions must be granted at both compile-time and run-time when both phases require the named module to reference classes on the classpath. Adding `--add-reads` only at runtime cannot fix a compile error that occurred earlier; adding it only at compile-time also does not automatically configure the JVM at launch.

## 5. --add-reads is not the same as requires or exports

The following mechanisms solve different problems:

| Mechanism | Purpose | Scope |
| --- | --- | --- |
| `requires other.module` | Declares a dependency on a named module | In `module-info.java`, effective as part of the descriptor |
| `requires transitive other.module` | Passes readability on to consumers of the current module | In `module-info.java` |
| `--add-reads app=ALL-UNNAMED` | Adds a readability relationship from a named module to unnamed modules | Corresponding compile/run configuration |
| `exports package.name` | Exposes a package for normal Java code | In the descriptor of the module owning the package |
| `--add-exports` | Adds access to an unexported public package | Corresponding compile/run configuration |
| `opens package.name` | Allows deep reflection into a package | In the descriptor of the module owning the package |
| `--add-opens` | Adds deep reflection access at runtime | JVM launch configuration |

For a library on the classpath, the unnamed module exports its packages according to its own rules. The main issue when a named module wants to use that library is readability; `--add-reads` resolves this relationship.

Conversely, if the dependency is a named module but the needed package is not exported, adding `--add-reads` is not enough. In that case, consider `exports` or `--add-exports` depending on descriptor control and the execution phase.

## 6. Distinguishing between an unnamed module and an automatic module

These two concepts are often confused when migrating legacy libraries to JPMS.

| Characteristic | Unnamed module | Automatic module |
| --- | --- | --- |
| Common source | Classpath | JAR without a descriptor placed on the module path |
| Has a module name | No | Yes |
| Can be used in `requires` | No | Yes |
| Descriptor | No `module-info.class` | Descriptor is automatically derived |
| Packages | Exported according to unnamed module rules | Packages exported according to automatic module rules |
| Read by a named module via `requires` | Not possible because it has no name | Can declare `requires automatic.name` |

A JAR whose manifest contains:

~~~text
Automatic-Module-Name: com.legacy.format
~~~

still belongs to an unnamed module if it is placed on the classpath. The `Automatic-Module-Name` attribute is only used to determine the automatic module name when the JAR is placed on the module path and treated as an automatic module.

If you move `legacy-library.jar` to the module path, you can declare:

~~~java
module com.acme.app {
    requires com.legacy.format;
}
~~~

The module name must match the automatic module name advertised by the JAR or the derived name. For important libraries, verify the actual name with:

~~~bash
jar --describe-module --file legacy-library.jar
~~~

Placing a JAR on the module path does not turn it into an explicit named module. If the JAR has no `module-info.class`, it remains an automatic module.

## 7. How to check which module contains a class

You can use the Java Reflection API to inspect a class's module:

~~~java
Module appModule = Main.class.getModule();
Module legacyModule = LegacyFormatter.class.getModule();

System.out.println("App named: " + appModule.isNamed());
System.out.println("App name: " + appModule.getName());

System.out.println("Legacy named: " + legacyModule.isNamed());
System.out.println("Legacy name: " + legacyModule.getName());

System.out.println("App reads legacy: "
    + appModule.canRead(legacyModule));
~~~

If `Main` belongs to a named module and `LegacyFormatter` belongs to an unnamed module:

- `appModule.isNamed()` returns `true`.
- `legacyModule.isNamed()` returns `false`.
- `legacyModule.getName()` returns `null`.
- `appModule.canRead(legacyModule)` is normally `false` without `--add-reads`, and can be `true` once the readability relationship has been properly added.

You can enable module resolution logging at launch:

~~~bash
java --show-module-resolution \
  --module-path out \
  --class-path legacy-library.jar \
  --add-reads com.acme.app=ALL-UNNAMED \
  --module com.acme.app/com.acme.app.Main
~~~

The log helps show which modules are resolved. To determine which module a specific class belongs to, `Class.getModule()` and `Module.isNamed()` are usually more direct.

## 8. Long-term approaches when migrating an application to JPMS

`--add-reads` is a useful compatibility bridge, but it should not become the primary way to declare dependencies for every library. You can choose one of the following approaches:

**Keep the library on the classpath during transition.** Use `--add-reads module=ALL-UNNAMED` for modules that need integration, while limiting the scope of legacy classpath usage.

**Use an automatic module.** Place the JAR on the module path and declare `requires` using the automatic module name. This establishes a clearer named-module relationship, though automatic modules have fairly broad boundaries, so this should be viewed as a transitional step.

**Modularize the library.** Add `module-info.java`, export the necessary APIs, and keep implementation packages unexported. Consumers then declare `requires` with a stable module name.

**Separate API and implementation.** If the library is a large integration, create a small API module so business modules depend on the contract, while an adapter/provider implements that contract. This reduces the need for business modules to know about legacy library details.

When choosing an approach, consider whether you can modify the dependency, the stability of the API, and how many modules need to use the library. Do not open `ALL-UNNAMED` to all modules if only one module needs compatibility with the legacy library.

## 9. Common errors

| Symptom | Cause | Solution |
| --- | --- | --- |
| Named module cannot import a package on the classpath | Named modules do not automatically read unnamed modules | Add `--add-reads module=ALL-UNNAMED` at compile-time and runtime or modularize the dependency |
| `requires com.legacy.format` reports module not found | The JAR is still on the classpath, not a named/automatic module on the module path | Move the JAR to the module path and check the module name, or continue using the unnamed module with `--add-reads` |
| Added `--add-reads` but still cannot access a named module's package | The target module's package is not exported | Check `exports` or `--add-exports` |
| Compiles successfully but fails at runtime | Runtime is missing the classpath or missing the readability relationship | Check both `--class-path` and `--add-reads` in the launch command |
| Class is loaded by a different class loader | The class belongs to a different unnamed module than expected by the configuration | Check `Class.getClassLoader()` and `Class.getModule()` |

## Conclusion

A named module does not automatically read an unnamed module because an unnamed module has no name to declare with `requires`. This is why code on the classpath can run fine in an old application yet fail when part of the application is converted into a named module.

During the compatibility phase, `--add-reads named.module=ALL-UNNAMED` can add readability at compile-time and runtime. In the long run, dependencies should be converted into automatic or explicit named modules, or a small API should be extracted so business modules depend on a stable contract. When diagnosing issues, check which module a class actually belongs to and distinguish readability from exports/opens.