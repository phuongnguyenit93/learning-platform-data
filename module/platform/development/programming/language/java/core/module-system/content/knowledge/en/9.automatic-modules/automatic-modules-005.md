# Automatic Modules Read Other Modules

An **automatic module** is a named module created implicitly when a JAR without a module descriptor is placed on the module path. It helps legacy libraries participate in JPMS during the migration phase. An important characteristic of an automatic module is that it **reads all other modules in the resolved configuration, including the unnamed module**.

This rule allows a legacy library to keep referencing the dependencies it was compiled against for the classpath model, while still being usable by a modularized application. However, an automatic module's broad readability scope does not mean every JAR on disk is automatically loaded, nor does it mean other modules inherit the automatic module's full readability rights.

## 1. Where Do Automatic Modules Come From?

An explicit modular JAR has a `module-info.class` file at the root of the JAR. This file declares the module name, dependencies, and exported/opened packages.

A legacy JAR without `module-info.class` when placed on the module path can be treated as an **automatic module**. The module system synthesizes an implicit descriptor for that JAR. The module name is determined in order:

1. The `Automatic-Module-Name` attribute in the manifest, if present.
2. If that attribute is absent, the name is derived from the JAR file name.

For example, a JAR named `legacy-logging-2.4.jar` may be derived as an automatic module named `legacy.logging`. The derived name depends on filename normalization rules and can change if the JAR name changes. Libraries wanting a stable module name should provide `Automatic-Module-Name` in the manifest:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.legacy.logging
~~~

When this JAR is placed on the module path, the module system recognizes it by the name `com.acme.legacy.logging`. The manifest attribute helps other modules declare a stable dependency without depending on the release file name.

A JAR placed on the classpath still belongs to the unnamed module, even if the manifest has `Automatic-Module-Name`. An automatic module is formed only when the JAR is processed via the module path.

## 2. The Broad Readability Rule of an Automatic Module

A regular explicit named module reads only the modules it declares via `requires`, along with transitive relationships per JPMS rules. An automatic module has a special rule: it reads all other modules in the resolved configuration.

This includes:

- Explicit named modules that have been included in the runtime configuration.
- Other automatic modules in the configuration.
- Unnamed modules associated with class loaders within the scope of the automatic module's readability rules.

It can be summarized briefly as:

~~~text
automatic module
    ├── reads explicit named modules in configuration
    ├── reads automatic modules in configuration
    └── reads unnamed modules
~~~

The key phrase is **in configuration**. An automatic module does not automatically turn every JAR sitting in a directory into a resolved module. A module must be found and included in the runtime configuration before readability relationships have meaning.

This read-all characteristic allows legacy libraries to continue referencing many dependencies they previously used on the classpath, even without a descriptor to declare each dependency individually.

## 3. Automatic Modules Also Export Their Packages

In addition to broad readability, an automatic module exports all of its packages. This is a major difference from an explicit named module, where the author must deliberately list packages with `exports`.

Suppose the legacy JAR contains:

~~~text
legacy-logging.jar
└── com/acme/logging/
    ├── Logger.class
    └── internal/
        └── LogConfig.class
~~~

When used as an automatic module on the module path, the JAR's packages are exported according to automatic module rules. A named module depending on it can use public types in the corresponding packages without the JAR declaring `exports`.

This is convenient for migration, but reduces encapsulation. Internal packages of the legacy library can also become accessible across the module boundary if they contain public types. Once the library is explicitly modularized, the author can select API packages and keep implementation packages unexported.

Readability and exports are still two separate concepts. The fact that an automatic module reads all modules does not automatically export packages of the modules it reads. Export rights are decided by the source module.

## 4. How Does a Named Module Use an Automatic Module?

An explicit named module can declare `requires` on an automatic module using the module name recognized by the module system.

For example, the `mods` directory contains the library `legacy-logging-2.4.jar` with a manifest declaring:

~~~text
Automatic-Module-Name: com.acme.legacy.logging
~~~

The application declares:

~~~java
module com.acme.app {
    requires com.acme.legacy.logging;
}
~~~

Application code can import public types from packages provided by the automatic module:

~~~java
package com.acme.app;

import com.acme.logging.Logger;

public class Main {
    public static void main(String[] args) {
        Logger.info("Application started");
    }
}
~~~

Compile and run on JDK 21:

~~~bash
javac --module-path mods \
      --module-source-path src \
      -d out \
      -m com.acme.app
~~~

~~~bash
java --module-path "out:mods" \
     -m com.acme.app/com.acme.app.Main
~~~

On Windows, replace the module path separator `:` with `;`:

~~~powershell
java --module-path "out;mods" -m com.acme.app/com.acme.app.Main
~~~

Here, the application has an explicit dependency on the automatic module. When module `com.acme.app` is resolved, the automatic module is pulled into the configuration. The automatic module can read other modules in the configuration according to its read-all rule.

## 5. An Automatic Module Reads Other Named Modules Without a Separate requires

Suppose the configuration contains the following modules:

~~~text
com.acme.app
    requires com.acme.legacy.logging

com.acme.legacy.logging
    automatic module

com.acme.metrics
    explicit named module
~~~

Module `com.acme.legacy.logging` has no descriptor to declare `requires com.acme.metrics`. Even so, when both modules are in the resolved configuration, the automatic module still reads `com.acme.metrics` under its special rule.

If the legacy library's code references public types in packages exported by `com.acme.metrics`, this readability relationship allows linking and using those types.

However, module `com.acme.app` does not automatically inherit the automatic module's ability to read all modules just because it declares `requires com.acme.legacy.logging`. If the application code itself needs to import types from `com.acme.metrics`, declare a direct dependency:

~~~java
module com.acme.app {
    requires com.acme.legacy.logging;
    requires com.acme.metrics;
}
~~~

Declaring dependencies directly keeps the application's dependency contract clear and avoids relying on an intermediate library happening to be an automatic module.

## 6. An Automatic Module Can Read Libraries on the Classpath

An important transitional feature is that an automatic module can read the unnamed module. This lets a legacy library on the module path continue referencing dependencies that still reside on the classpath, within the scope of the corresponding configuration and class loader.

For example, an application launched with both a module path and a classpath:

~~~bash
java --module-path mods \
     --add-modules com.acme.legacy.logging \
     --class-path "lib/legacy-helper.jar:out" \
     com.acme.app.Main
~~~

In this example, `com.acme.legacy.logging` is an automatic module brought into the configuration as an additional root. Classes from `legacy-helper.jar` and `out` belong to the unnamed module of the classpath class loader. The automatic module can read the unnamed module according to its rules.

If the main application is also a named module, launch with `-m` and declare the needed dependencies in the descriptor. Named modules do not automatically read the unnamed module; if temporary compatibility is needed, `--add-reads` targeting `ALL-UNNAMED` can be used for a specific named module.

## 7. Module Path Does Not Mean Every JAR Is Resolved

A common misconception is: if an automatic module reads all other modules, then simply copying every JAR onto the module path lets the automatic module use all of them. This view overlooks the module resolution step.

The module path is the source from which the module finder observes modules. The runtime configuration contains only the modules resolved from root modules, dependencies, and service bindings. A JAR may be observable yet not included in the configuration for a given run.

For an application launched with a main class on the classpath, you can request specific modules as roots:

~~~bash
java --module-path mods \
     --add-modules com.acme.legacy.logging,com.acme.metrics \
     --class-path out \
     com.acme.app.Main
~~~

Or request all observable modules on the module path as roots:

~~~bash
java --module-path mods \
     --add-modules ALL-MODULE-PATH \
     --class-path out \
     com.acme.app.Main
~~~

The second approach can bring more modules into the configuration than the application needs. In real deployments, choose roots intentionally so dependencies and the runtime module scope remain easy to understand.

Use the following option to observe which modules are resolved:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --add-modules com.acme.legacy.logging \
     --class-path out \
     com.acme.app.Main
~~~

## 8. Automatic Module Names and the Risk of Renaming JARs

If a JAR does not have `Automatic-Module-Name`, the module name is derived from the file name. For instance, `legacy-logging-2.4.jar` might be normalized to `legacy.logging`. When a publisher renames the artifact or changes how versions are named, the derived name can change and break the application's `requires` directive.

For example, a module descriptor declares:

~~~java
module com.acme.app {
    requires legacy.logging;
}
~~~

If the new JAR is named in a way that causes the automatic module to be derived as `legacy.logging.v3`, resolution will fail to find the `legacy.logging` module requested by the application.

You can check the actual name:

~~~bash
jar --describe-module --file mods/legacy-logging-2.4.jar
~~~

When a stable name is needed, prefer libraries that publish `Automatic-Module-Name`. Whenever possible, upgrading the library to a version that provides an explicit module descriptor gives clearer control over dependencies and package exports.

## 9. Limitations of Automatic Modules

Automatic modules are helpful for migration, but should not be treated as a final module design:

- **Overly broad readability:** the module can read every other module in the configuration, making actual dependencies hard to see from a descriptor.
- **Overly broad exports:** every package of the automatic module is exported, including packages meant solely for implementation.
- **No explicit dependency contract:** the JAR does not declare a list of `requires` in `module-info.class`.
- **Derived names can be unstable:** without `Automatic-Module-Name`, renaming the JAR can affect the module name.
- **Hard to control encapsulation:** internal packages can be used unintentionally by other modules.

When the library is ready to support JPMS, add `module-info.java`, declare truly needed dependencies, export only public APIs, and open only packages needed for framework reflection.

## 10. Common Errors and How to Check

| Symptom | Possible Cause | How to Check |
|---|---|---|
| `FindException: Module ... not found` | Automatic module name mismatch or JAR not on the module path | Use `jar --describe-module`, check `Automatic-Module-Name` and file name |
| Automatic module does not see another module | That other module was not included in the runtime configuration | Check root modules, dependencies, and `--show-module-resolution` |
| Named module cannot use types from automatic module | Named module has not declared `requires` on the automatic module | Add explicit dependency in `module-info.java` |
| Package is inaccessible even though automatic module is resolved | The needed package belongs to another source module that did not export it | Check the descriptor of the source module |
| Classpath code cannot use a module on the module path | Module is not in the boot layer or package is not exported | Check `--add-modules` and `exports` |
| After renaming a JAR, the application fails to resolve the module | The derived automatic module name changed | Declare/check `Automatic-Module-Name` |

## 11. Diagnostic Workflow

When an automatic module cannot use types from another module, check in the following order:

1. **Identify the automatic module name:** run `jar --describe-module --file ...` to see the actual name.
2. **Check the JAR location:** ensure the JAR is on the module path, not just on the classpath.
3. **Check the resolved configuration:** use `--show-module-resolution` to confirm both the automatic module and target module are in the configuration.
4. **Check the source package:** the package containing the needed type must be exported by the source module.
5. **Check dependency direction:** a named module using an automatic module must declare `requires`; the automatic module has its own broad reading rule.
6. **Check the classpath if present:** an automatic module can read the unnamed module, but a named module does not automatically read the unnamed module.
7. **Stabilize the module name:** use `Automatic-Module-Name` or an explicit module descriptor to avoid relying on the file name.

## 12. Key Takeaways

Automatic modules serve as a bridge between legacy classpath libraries and JPMS. When included in the resolved configuration, an automatic module reads all other modules in the configuration, including the unnamed module, and exports all of its own packages. As a result, legacy libraries can continue using many dependencies without needing their own descriptor yet.

This broad readability does not mean every JAR on the module path is automatically resolved, nor does it make a named module using it automatically read every other module. Distinguish the module path from the resolved configuration, readability from exports, and automatic modules from the unnamed module. Once migration stabilizes, transition the library to an explicit named module to declare dependencies and APIs with clear boundaries.