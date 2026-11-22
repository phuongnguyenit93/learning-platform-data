# Conditions Under Which an Unnamed Module Reads a Named Module

In JPMS, an **unnamed module** is a special module associated with a class loader when classes are loaded from the classpath. Even though it has no name and no `module-info.java` file, an unnamed module can still use named modules in the runtime configuration.

The key rule is: **an unnamed module reads all named modules in the boot layer, but can only access appropriately exported packages**. Therefore, the presence of a modular JAR on the module path is not enough to conclude that classpath code can use every class inside that JAR. The module must be resolved into the running configuration, the target package must be exported to the unnamed module, and the type/member must still satisfy Java access modifiers.

## 1. How is an unnamed module created?

When running an application via the classpath, classes not belonging to a named module are loaded into the unnamed module associated with the corresponding class loader. For example:

~~~bash
java -cp "out:lib/*" com.acme.app.Main
~~~

If running on Windows, the separator for classpath entries is a semicolon:

~~~powershell
java -cp "out;lib/*" com.acme.app.Main
~~~

The `com.acme.app.Main` class and library classes loaded from the classpath belong to the unnamed module of the class loader that loaded them. An unnamed module has several characteristics:

- Has no module name to declare via `requires` in a module descriptor.
- Has no separate `module-info.class` file.
- Its packages are exported and opened according to the special rules of the unnamed module.
- It reads all named modules in the boot layer.
- It does not automatically become a named module simply because the classpath contains a JAR with `module-info.class`.

There is a separate unnamed module for each class loader. Therefore, if an application or container creates multiple class loaders, each class loader can have its own unnamed module. When using the `ALL-UNNAMED` launcher option, the JVM applies the corresponding change to unnamed modules, including those associated with class loaders created during the process.

## 2. First condition: the named module must belong to the runtime configuration

An unnamed module reads named modules in the **boot layer**. The boot layer is the initial module layer created by the JVM at startup. Required JDK modules are typically resolved into this layer; application or library modules on the module path can also be included if they are roots or pulled in via dependencies/service binding.

Suppose there is a modular JAR:

~~~text
mods/
└── com.acme.api.jar
~~~

Descriptor inside the JAR:

~~~java
module com.acme.api {
    exports com.acme.api;
}
~~~

A classpath application can run with this module by adding the module as a root:

~~~bash
java --module-path mods \
     --add-modules com.acme.api \
     -cp out \
     com.acme.app.Main
~~~

The `--add-modules com.acme.api` option instructs the JVM to include that module in the resolution process as a root module. If the module is already pulled in as a dependency of another root, there is no need to add it again.

Key point to remember: **the module path is where modules are located; the boot layer is the configuration of resolved modules**. A JAR located in the module path directory that is not selected as a root, not pulled in by a dependency, and not included by service binding may not appear in the boot layer. In that case, an unnamed module cannot use that module merely because the JAR file exists on disk.

You can use `--add-modules ALL-MODULE-PATH` to request resolution of all observable modules on the module path, though in normal applications it is better to select the needed roots for a clearer configuration.

## 3. Second condition: the package must be exported to the unnamed module

An unnamed module has readability to named modules in the boot layer, but readability is not synonymous with access to every package. The source module must export the package containing the type to be used.

Example library module:

~~~java
module com.acme.api {
    exports com.acme.api;
}
~~~

Public class:

~~~java
package com.acme.api;

public class Greeting {
    public String message() {
        return "Hello from named module";
    }
}
~~~

Application without `module-info.java`:

~~~java
package com.acme.app;

import com.acme.api.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(new Greeting().message());
    }
}
~~~

Compile the classpath application while the library module is on the module path:

~~~bash
javac --module-path mods \
      --add-modules com.acme.api \
      -d out \
      src/com/acme/app/Main.java
~~~

Run the application:

~~~bash
java --module-path mods \
     --add-modules com.acme.api \
     -cp out \
     com.acme.app.Main
~~~

The classpath application does not need to write `requires com.acme.api` because the unnamed module has special readability rules. However, the `com.acme.api` package must be exported unqualified or granted export access via appropriate runtime configuration.

If the module descriptor does not export the package:

~~~java
module com.acme.api {
    // com.acme.api is not exported
}
~~~

then classpath code cannot import `com.acme.api.Greeting` across the module boundary. Adding `public` to the class will not solve this issue.

## 4. Qualified exports do not automatically grant access to unnamed modules

A module can export a package to specific named modules:

~~~java
module com.acme.api {
    exports com.acme.api.spi to com.acme.plugin;
}
~~~

In this case, the `com.acme.api.spi` package is exported only to the `com.acme.plugin` module. An unnamed module has no name to appear in the list of target modules, so it does not receive access to the package from this qualified export alone.

If a classpath application genuinely needs to access public types in that package, you can supplement the export at runtime:

~~~bash
java --module-path mods \
     --add-modules com.acme.api \
     --add-exports com.acme.api/com.acme.api.spi=ALL-UNNAMED \
     -cp out \
     com.acme.app.Main
~~~

Option structure:

~~~text
--add-exports source.module/package=target.module
~~~

Here:

- `com.acme.api` is the source module.
- `com.acme.api.spi` is the package to export.
- `ALL-UNNAMED` is the special target representing unnamed modules.

`ALL-UNNAMED` is a special symbol for launcher/compiler options such as `--add-exports`; it is not a module name to write in `module-info.java`. You cannot write `exports com.acme.api.spi to ALL-UNNAMED;` in a descriptor.

If you can modify the source module, consider designing an appropriate public API instead of relying long-term on runtime expansion flags.

## 5. Third condition: types and members still obey Java access modifiers

Once the module is resolved and the package is exported, Java language access rules still apply.

Example:

~~~java
package com.acme.api;

public class Customer {
    public String name() {
        return "An";
    }

    String internalLabel() {
        return "internal";
    }

    private String secret() {
        return "hidden";
    }
}
~~~

Code in the unnamed module can use the `Customer` class and call the public method `name()`. It cannot directly call `internalLabel()` because it is package-private, nor can it call `secret()` because it is private.

`exports` does not turn all members in a package into public ones. It only allows other modules to access public types in the package according to JPMS rules. After that, access modifiers continue to determine which members are accessible.

If a framework needs to access private fields or non-public constructors via reflection, the export condition is not enough. The package must be opened for deep reflection.

## 6. Deep reflection requires opens

`exports` and `opens` serve two different purposes:

- `exports` allows code in other modules to access public APIs in a package.
- `opens` allows reflection to deeply access non-public members of a package at runtime.

Example module:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model;
}
~~~

The `com.acme.domain.model` package is opened to all modules at runtime. If only a classpath framework needs reflection, you can limit it with a launcher option:

~~~bash
java --module-path mods \
     --add-modules com.acme.domain \
     --add-opens com.acme.domain/com.acme.domain.model=ALL-UNNAMED \
     -cp out \
     com.acme.app.Main
~~~

If the framework is a named module, replace `ALL-UNNAMED` with the framework's module name. If you can edit the descriptor, qualified opens usually express scope better:

~~~java
module com.acme.domain {
    opens com.acme.domain.model to com.acme.json;
}
~~~

A package opened for reflection does not automatically become an API for external source code to import. If the application needs to call public types in the package, check `exports` as well.

## 7. Can a named module read an unnamed module?

The reverse direction has a different rule. An unnamed module reads named modules in the boot layer by default; a named module **does not automatically read an unnamed module**.

For example, a modularized application declares:

~~~java
module com.acme.app {
    // No requires for the classpath library
}
~~~

If the application's classes need to import a library that only exists on the classpath, the named module cannot automatically read the unnamed module containing that library. During migration, you can add a read relationship at runtime:

~~~bash
java --module-path mods \
     --add-reads com.acme.app=ALL-UNNAMED \
     --class-path lib/legacy.jar \
     -m com.acme.app/com.acme.app.Main
~~~

`--add-reads com.acme.app=ALL-UNNAMED` allows the named module `com.acme.app` to read unnamed modules. This alters the opposite direction of the rule examined in this lesson. An unnamed module reading a named module is already permitted by JPMS when the module is in the boot layer; a named module needs additional configuration if it wants to read classpath libraries.

A module cannot write `requires unnamed.module` because an unnamed module has no stable name to reference in a descriptor.

## 8. Checking readability and exports with the Java API

You can inspect module relationships programmatically:

~~~java
public class ModuleAccessCheck {
    public static void main(String[] args) {
        Module unnamed = ModuleAccessCheck.class.getModule();

        Module named = ModuleLayer.boot()
            .findModule("com.acme.api")
            .orElseThrow();

        System.out.println("Caller is named: " + unnamed.isNamed());
        System.out.println("Can read named module: " + unnamed.canRead(named));
        System.out.println(
            "API package exported to caller: "
                + named.isExported("com.acme.api", unnamed)
        );
        System.out.println(
            "API package open to caller: "
                + named.isOpen("com.acme.api", unnamed)
        );
    }
}
~~~

When the `ModuleAccessCheck` class is loaded from the classpath:

- `unnamed.isNamed()` returns `false`.
- `unnamed.canRead(named)` indicates whether the caller has readability to the module found in the boot layer.
- `named.isExported(packageName, unnamed)` checks whether the package is exported to that exact caller.
- `named.isOpen(packageName, unnamed)` checks whether the package is open for deep reflection to the caller.

If `findModule` does not find the module, check whether that module has been included in the boot layer. If `canRead` is true but `isExported` is false, the issue lies in package export permissions, not readability.

## 9. Observing module resolution at runtime

Add `--show-module-resolution` to see which modules are resolved by the JVM:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --add-modules com.acme.api \
     -cp out \
     com.acme.app.Main
~~~

The output helps confirm whether the `com.acme.api` module joined the runtime configuration. To inspect the static metadata of a JAR:

~~~bash
jar --describe-module --file mods/com.acme.api.jar
~~~

This command displays the module name, `requires` directives, and `exports` packages. Combining both checks helps distinguish:

- The JAR was not found or the module was not resolved.
- The module was resolved, but the package is not exported to the unnamed module.
- The package is exported, but the type/member does not satisfy Java access modifiers.
- The package needs reflection, but has not been opened.

## 10. Common errors and how to handle them

| Symptom | Cause | Resolution |
|---|---|---|
| `package ... is not visible` when compiling a classpath app | The named module's package is not exported or the module was not included in the compile configuration | Check `exports`, module path, and `--add-modules` |
| `FindException: Module ... not found` | A required module is missing from observable module sources | Check the module name and module path |
| `IllegalAccessError` | Module readability or export is not satisfied during linking/execution | Check `canRead`, `isExported`, descriptor, and runtime options |
| `InaccessibleObjectException` | Reflection attempts to access a non-public member in an unopened package | Use qualified `opens` or `--add-opens` for the right caller |
| Classpath app can call API but named module cannot | Named module does not read unnamed module, or the package is not exported to it | Declare `requires`/`exports` properly; only use `--add-reads` for intentional classpath integration |
| Module is in the `mods` directory but does not appear in the boot layer | Module is not a root and was not pulled in by dependency/service binding | Check `--add-modules` and `--show-module-resolution` |

## 11. Practical diagnostic workflow

When a classpath application needs to use a named module, check in order:

1. **Identify the caller module:** which unnamed module does the API-calling class belong to, and which class loader loaded it?
2. **Verify the source module:** does the JAR have a valid descriptor and the right module name?
3. **Verify the module is resolved:** does the module belong to the boot layer? Use `--add-modules` if you need to add a root.
4. **Check readability:** call `canRead` or observe the graph to confirm the unnamed module reads the source module.
5. **Check exports:** is the package containing the type exported? A qualified export may not grant access to an unnamed module.
6. **Check access modifiers:** are the class and member public to the required extent?
7. **Check reflection:** if a framework needs deep reflection, verify the package is open to the caller via `opens` or `--add-opens`.
8. **Test configuration on the right process:** place the options on the JVM actually running the application/tests, then re-run and inspect the resolution output.

Do not add `--add-exports` or `--add-opens` in bulk before identifying which boundary is blocking access. Each option should address a specific package and a specific caller module.

## 12. Key takeaways

An unnamed module reads named modules in the boot layer, but reading a module is not synonymous with accessing every package. The source module must export the package to the unnamed module; types and members must still obey Java access modifiers. If deep reflection is needed, the package must be opened separately.

When integrating modularized libraries with a classpath application, confirm that the module is resolved, the API package is exported unqualified or supplemented with `--add-exports ...=ALL-UNNAMED`, and reflection frameworks are granted appropriate `opens`. `ALL-UNNAMED` is a special target for runtime options, not a module name to declare in `module-info.java`.