# --add-modules: Adding Observable Modules to the Root Set

In the Java Platform Module System (JPMS), a module can reside on the module path without yet being included in the application's module graph. In that case, the JVM can locate the module, but the module has not been resolved and does not appear in the running ModuleLayer.

The command-line option `--add-modules` lets you specify additional modules as **root modules** when the JVM resolves the module graph. This is how you instruct the runtime to resolve an observable module even if the main module does not declare a direct `requires` to it.

Key point to remember: **observable**, **root**, and **resolved** are three related states, not synonyms. `--add-modules` affects the root set used to resolve the module graph. It does not automatically grant readability, does not export packages, and does not open packages for deep reflection.

## 1. What Is an Observable Module?

A module is considered observable when the runtime can locate that module's descriptor through the configured module sources. Common sources include:

- System modules bundled with the JDK.
- Modules on the application module path passed via `--module-path`.
- Modules on the upgrade module path if the application configures that source.

For example, the `mods` directory might contain two modules:

~~~text
mods/
├── com.example.app/
│   ├── module-info.class
│   └── com/example/app/Main.class
└── com.example.plugin/
    ├── module-info.class
    └── com/example/plugin/PluginMarker.class
~~~

When running with:

~~~shell
java --module-path mods --module com.example.app/com.example.app.Main
~~~

The runtime can locate both `com.example.app` and `com.example.plugin`. However, if `com.example.app` does not declare `requires com.example.plugin`, the plugin module is not necessarily included in the graph just because it is sitting on the module path.

In other words:

- **Observable**: the runtime can find the module.
- **Root**: a module chosen as a starting point of the resolution process.
- **Resolved**: a module that has been included in the graph after the JVM resolves the roots and their required dependencies.

The module path determines where to look for modules. `--add-modules` determines which additional modules need to be added to the root set.

## 2. Syntax and Meaning of --add-modules

Syntax:

~~~shell
java --add-modules <module>(,<module>)* ...
~~~

You can specify a single module or multiple modules, separated by commas:

~~~shell
java --module-path mods --add-modules com.example.plugin,com.example.metrics --module com.example.app/com.example.app.Main
~~~

The JVM adds the specified modules to the root set, then resolves them along with dependencies declared via `requires`.

In addition to specific module names, this option supports three special selectors:

| Value | Meaning |
| --- | --- |
| `ALL-DEFAULT` | Adds all modules belonging to the default root modules set |
| `ALL-SYSTEM` | Adds all system modules |
| `ALL-MODULE-PATH` | Adds all observable modules found on the module path |

Examples:

~~~shell
# Add a specific module
java --module-path mods --add-modules com.example.plugin --module com.example.app/com.example.app.Main

# Add all modules on the module path
java --module-path mods --add-modules ALL-MODULE-PATH --module com.example.app/com.example.app.Main

# Add all system modules
java --add-modules ALL-SYSTEM --module com.example.app/com.example.app.Main
~~~

When only a specific plugin or support module is needed, name that module explicitly. `ALL-MODULE-PATH` can pull unnecessary modules into resolution and surface configuration conflicts that would not otherwise occur.

## 3. How Do Root Modules Affect the Resolution Process?

The resolution process starts from the set of root modules. For each root, the JVM continues examining dependencies declared via `requires`, then brings the required modules into the graph.

Suppose there are these relationships:

~~~text
com.example.app
    └── requires com.example.api

com.example.plugin
    └── requires com.example.api

com.example.api
    └── requires java.base
~~~

If `com.example.app` is the root, the JVM resolves app along with its required dependencies. The plugin module may remain only an observable module if no relationship causes it to be resolved.

When adding:

~~~shell
--add-modules com.example.plugin
~~~

`com.example.plugin` becomes an additional root. The JVM resolves the plugin and the plugin's dependencies. As a result, the module graph can contain app, plugin, api, and java.base.

This is useful when an application needs the runtime to recognize a support module, plugin, or module providing a capability selected by configuration. The application can locate resolved modules via the ModuleLayer API.

## 4. Example: Resolving a Plugin Not Directly Required

We create two independent modules. The app module does not declare a dependency on the plugin; the plugin module is still present on the module path.

Directory structure:

~~~text
src/
├── com.example.app/
│   ├── module-info.java
│   └── com/example/app/Main.java
└── com.example.plugin/
    ├── module-info.java
    └── com/example/plugin/PluginMarker.java
~~~

### The Plugin Module

File `src/com.example.plugin/module-info.java`:

~~~java
module com.example.plugin {
    exports com.example.plugin;
}
~~~

File `src/com.example.plugin/com/example/plugin/PluginMarker.java`:

~~~java
package com.example.plugin;

public final class PluginMarker {
    private PluginMarker() {
    }
}
~~~

The plugin module exports its package so its public API can be used by modules that read it. This export is independent of the decision whether to resolve the plugin.

### The App Module

File `src/com.example.app/module-info.java`:

~~~java
module com.example.app {
}
~~~

File `src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

import java.util.Optional;

public class Main {

    public static void main(String[] args) {
        Module appModule = Main.class.getModule();

        Optional<Module> pluginModule =
            ModuleLayer.boot().findModule("com.example.plugin");

        System.out.println(
            "Plugin resolved: " + pluginModule.isPresent()
        );

        pluginModule.ifPresent(plugin ->
            System.out.println(
                "App reads plugin: " + appModule.canRead(plugin)
            )
        );
    }
}
~~~

The program uses `ModuleLayer.boot().findModule(...)` to check whether the plugin belongs to the current boot layer. It uses `Module.canRead(...)` to check the readability relationship from app to plugin.

### Compilation

From the root directory of the example, run:

~~~shell
javac -d mods/com.example.plugin src/com.example.plugin/module-info.java src/com.example.plugin/com/example/plugin/PluginMarker.java

javac --module-path mods -d mods/com.example.app src/com.example.app/module-info.java src/com.example.app/com/example/app/Main.java
~~~

### Running Without Adding the Root

~~~shell
java --module-path mods --module com.example.app/com.example.app.Main
~~~

Expected output:

~~~text
Plugin resolved: false
~~~

The plugin module can be found on the module path, but it has not been resolved into the boot layer.

### Running With --add-modules

~~~shell
java --module-path mods --add-modules com.example.plugin --module com.example.app/com.example.app.Main
~~~

Expected output:

~~~text
Plugin resolved: true
App reads plugin: false
~~~

The plugin has been resolved and appears in the boot layer. However, app still cannot read the plugin because the app module does not declare `requires com.example.plugin` and does not have equivalent readability permission.

This example shows that `--add-modules` solves bringing the module into the graph; it does not automatically create readability relationships between modules.

## 5. Distinguishing --add-modules from Other Module Options

JPMS options frequently appear together but solve different problems:

| Option | Role |
| --- | --- |
| `--module-path` | Specifies where the runtime searches for application modules |
| `--add-modules` | Adds observable modules to the root set for resolution |
| `--limit-modules` | Limits the set of observable modules that the runtime can use |
| `--add-reads` | Adds a readability relationship between a source module and a target module |
| `--add-exports` | Exports a package of a target module to specified modules |
| `--add-opens` | Opens a package for deep reflection from specified modules |

You can use `--add-modules` and `--add-reads` together when both conditions are needed:

~~~shell
java \
  --module-path mods \
  --add-modules com.example.plugin \
  --add-reads com.example.app=com.example.plugin \
  --module com.example.app/com.example.app.Main
~~~

After running with the two options above, the plugin is resolved and app has readability to the plugin. If accessing public types from the plugin's package is needed, that package must still be exported according to JPMS rules. If deep reflection into non-public members is needed, the opens rules must also be satisfied.

For an application compiled into a named module, `--add-reads` at runtime does not replace the configuration needed at compile time. If source code directly references types of another module, configure the module dependency properly in `module-info.java` or provide the appropriate compile options to javac.

## 6. Combining with --limit-modules

`--limit-modules` restricts the set of modules that the runtime considers observable. Therefore, it can prevent a module from remaining in the set available for resolution.

Example:

~~~shell
java \
  --module-path mods \
  --limit-modules java.base,com.example.app \
  --add-modules com.example.plugin \
  --module com.example.app/com.example.app.Main
~~~

If `com.example.plugin` is excluded from the observable set by this limit, the JVM cannot resolve that module merely via `--add-modules`. Any module name added as a root must be findable within the set of modules the runtime is permitted to observe.

When encountering a module-not-found error, check in order:

1. Has the module been compiled or packaged properly?
2. Is the module located in the path passed via `--module-path`?
3. Does the module name match the name declared in `module-info.java`?
4. Is `--limit-modules` excluding that module from the observable set?
5. Can the module's required dependencies be found and resolved?

If the module is not observable or a dependency cannot be resolved, startup can fail with a resolution error, such as `FindException` or a module-not-found error.

## 7. When Should --add-modules Be Used?

Some common cases:

- **Configuration-selected plugins:** the plugin resides on the module path but is not a mandatory dependency of the main module. The selected plugin can be added as a root at startup.
- **Modules providing optional APIs or services:** the application wants to ensure a support module is resolved before looking it up in a ModuleLayer.
- **Testing or diagnostic tools:** a specific module needs to be brought into the graph for observation or to run a test scenario.
- **Applications needing many modules on the module path:** `ALL-MODULE-PATH` can be used when the intention is to resolve all observable modules on that path.

Do not use `ALL-MODULE-PATH` out of habit. Resolving every module can enlarge the graph scope and cause package, dependency, or module configuration conflicts to surface earlier.

If a module is always a mandatory part of the application, declaring `requires` in `module-info.java` usually expresses the dependency more clearly. `--add-modules` is suitable when you need to control the root set from the launch configuration.

## 8. Common Misconceptions

1. **A module on the module path is definitely already resolved:** the module path only provides a search source; a module can be observable without yet being in the graph.
2. **--add-modules automatically grants access permissions:** this option adds roots for resolution. Readability, exports, and opens still have their own rules.
3. **A root module only resolves itself:** the JVM also resolves required dependencies declared via `requires`.
4. **ALL-MODULE-PATH is just a named module:** it is a special selector representing observable modules on the module path.
5. **You can add a non-existent module:** the module must be observable in the runtime configuration; otherwise, resolution will fail.
6. **Using --add-modules instead of requires in every case:** mandatory dependencies should be expressed in the module descriptor so the architecture is easy to understand and verify.
7. **A resolved plugin means the app can directly call the plugin's classes:** the app still needs readability and appropriate package exports.

## 9. Diagnostic Workflow

When a module exists on the module path but does not appear in the runtime graph, check in order:

1. Confirm the module name via `module-info.java` or JAR metadata.
2. Confirm the module path points to the exact directory or JAR containing the module.
3. Check whether the module is restricted by `--limit-modules`.
4. Add the needed module using `--add-modules <module>`.
5. Verify the module is resolved using `ModuleLayer.boot().findModule(name)`.
6. If another module needs to use its API, check readability using `Module.canRead`.
7. Check exports or opens if the operation requires access to the corresponding package.

This workflow separates module-discovery errors, resolution errors, and access errors. As a result, you can identify the exact runtime option to adjust.

## Conclusion

`--add-modules` adds observable modules to the root set so the JVM resolves them into the module graph. It is useful when you need to bring plugins, support modules, or optional modules into the runtime without declaring mandatory dependencies in the main module. Remember that resolving a module only ensures the module is present in the graph; readability, exports, and opens still must be configured according to actual access needs.
