# Distinguishing Temporary Workarounds from Long-Term Descriptor Fixes

## 1. Objectives

When migrating an application to the Java Platform Module System (JPMS), you may encounter errors because a module cannot read another module, a package is not exported, or a library uses reflection to access internal module members. Java provides launcher options such as `--add-reads`, `--add-exports`, and `--add-opens` to adjust module graph behavior at runtime.

These options are useful for testing, supporting legacy libraries, or serving as a bridge during migration. However, if dependency relationships and access permissions are a stable part of the application's design, the long-term solution is usually to modify `module-info.java` of the module you own, then recompile and release the module.

This lesson distinguishes the two approaches, shows which type of problem each option solves, and explains how to choose the smallest scope of change.

After this lesson, you will be able to:

- Identify readability, export, and reflective access errors.
- Choose the right corresponding runtime option.
- Convert a workaround into an appropriate module descriptor declaration.
- Understand the limitations of `--add-modules` and `--patch-module`.
- Avoid keeping unnecessarily broad access permissions in production configurations.

## 2. Three Different Relationships in JPMS

Before choosing a runtime flag, distinguish three concepts:

**Readability — ability to read a module**

A module can reference types and APIs of another module only when an appropriate read relationship exists. This relationship typically comes from a `requires` directive in `module-info.java`.

**Export — package access permission at compile and link time**

A module can read another module yet still be unable to access types in a package that the target module has not exported. The `exports` directive determines which packages are exposed to other modules.

**Open — deep reflection access permission**

An exported package allows accessing public APIs under language and module rules. That does not automatically permit reflection to access private members. The `opens` directive grants permission to open a package for deep reflection at runtime.

These three error types are not interchangeable. For example, adding readability does not automatically export packages; exporting a package does not automatically open private members for reflection.

## 3. Common Runtime Options

### --add-reads: adding a readability relationship

Syntax:

~~~bash
java --add-reads <source-module>=<target-module> ...
~~~

Example:

~~~bash
java --add-reads com.example.app=com.example.legacy \
     --module-path mods \
     --module com.example.app/com.example.app.Main
~~~

This option adds a relationship so that module `com.example.app` can read module `com.example.legacy` for that run. It does not automatically export packages of the legacy module. If the needed package is still unexported, the application also needs appropriate export permission.

You can use `ALL-UNNAMED` as the target when adding readability to unnamed modules on the classpath:

~~~bash
java --add-reads com.example.app=ALL-UNNAMED ...
~~~

Do not add a broad relationship if the application only needs to read a specific named module.

### --add-exports: exporting a package to a target module

Syntax:

~~~bash
java --add-exports <source-module>/<package>=<target-module> ...
~~~

Example:

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED ...
~~~

This example exports the internal `sun.nio.ch` package of `java.base` to unnamed modules for the current run. This is commonly a workaround when a legacy library on the classpath depends on an internal JDK API.

You can restrict the target to a named module:

~~~bash
java --add-exports java.base/sun.nio.ch=com.example.app ...
~~~

`--add-exports` adjusts access to public types in the specified package. It does not open private members for deep reflection. If the error occurs when a framework uses reflection to access a private field or method, consider `--add-opens`.

The `--add-exports` option also has a compile-time form for `javac`, allowing the compiler to accept references to the additionally exported package. Launcher flags only address runtime; if source code needs to compile with that export permission, configure the compiler accordingly.

### --add-opens: opening a package for deep reflection

Syntax:

~~~bash
java --add-opens <source-module>/<package>=<target-module> ...
~~~

Example:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED ...
~~~

This option opens package `java.lang` of `java.base` for deep reflection from unnamed modules. Frameworks can use this permission to access private members via reflection at runtime.

Restrict the target module if you know which library needs the permission:

~~~bash
java --add-opens java.base/java.lang=com.example.framework ...
~~~

`--add-opens` is not a general replacement for `--add-exports`. It serves reflective access at runtime and does not turn a package into a public API for source code to import arbitrarily.

### --add-modules: adding root modules to resolve

Syntax:

~~~bash
java --add-modules <module-name>[,<module-name>...] ...
~~~

Example:

~~~bash
java --add-modules java.sql --module-path mods --module com.example.app/com.example.app.Main
~~~

This option instructs the resolver to include the named modules in the root module set for resolution. It is useful when an application needs an observable module that has not been pulled into the graph from normal roots.

`--add-modules` does not create arbitrary readability relationships and does not export packages. If the app module needs to read an added module, an appropriate readability relationship must still exist, usually `requires` in the descriptor or an intentional `--add-reads` adjustment.

## 4. Quick Selection Table by Error Type

| Issue | Common Runtime Option | Corresponding Descriptor Declaration |
| --- | --- | --- |
| Module A needs to read module B | `--add-reads A=B` | `requires B;` in A |
| Module B needs to expose package p to A | `--add-exports B/p=A` | `exports p to A;` in B |
| Framework needs deep reflection into package p of B | `--add-opens B/p=A` | `opens p to A;` in B |
| Need to add module M to root set for resolution | `--add-modules M` | No direct replacement directive; inspect application root/configuration |

The corresponding descriptor can only be edited when you own or can re-release the module containing the declaration. A consumer cannot directly edit `exports` or `opens` inside the descriptor of a third-party library module.

## 5. Editing module-info.java to Express Long-Term Relationships

Suppose the app module needs to use the library module's API.

App descriptor:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

Library descriptor:

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

Here:

- `requires` declares that app reads library.
- `exports` exposes the API package to modules that read library.
- Internal packages that do not need exporting remain encapsulated.

If you want to export a package only to a specific module, use a qualified export:

~~~java
module com.example.library {
    exports com.example.library.api to com.example.app;
}
~~~

This limits which modules are allowed to access the package, rather than opening the API to every module that reads library.

### When Deep Reflection Is Needed

If a legitimate framework needs deep reflection into a package you own, you can declare:

~~~java
module com.example.domain {
    opens com.example.domain.model to com.example.framework;
}
~~~

The `opens` directive is not synonymous with `exports`:

- `exports` serves public API access according to module rules.
- `opens` serves deep reflection at runtime.
- `opens` does not make a package an API for another module's source code to import and use private members.

If you need to open all packages in a module for reflection, you can use an open module:

~~~java
open module com.example.domain {
    requires com.example.api;
}
~~~

An open module opens the module's packages for deep reflection. When only a few packages need opening, use specifically scoped `opens` directives to preserve better encapsulation.

## 6. Example: Converting a Workaround into a Descriptor

Suppose an application currently runs thanks to the command:

~~~bash
java --add-reads com.example.app=com.example.legacy \
     --add-exports com.example.legacy/com.example.legacy.api=com.example.app \
     --module-path mods \
     --module com.example.app/com.example.app.Main
~~~

The command above supplies two conditions:

1. App can read the legacy module.
2. Package `com.example.legacy.api` is exported to app.

If you own both modules, express these relationships in the descriptors.

App module:

~~~java
module com.example.app {
    requires com.example.legacy;
}
~~~

Legacy module:

~~~java
module com.example.legacy {
    exports com.example.legacy.api to com.example.app;
}
~~~

After recompiling and releasing both modules, the run command no longer needs the two workaround flags:

~~~bash
java --module-path mods \
     --module com.example.app/com.example.app.Main
~~~

For deep reflection, do the same: identify the exact package and module that need opening, then add `opens package.name to target.module;` to the descriptor of the module owning that package if it is a stable design requirement.

## 7. --patch-module Is Not a Descriptor Fix

Syntax:

~~~bash
java --patch-module <module>=<path> ...
~~~

Example:

~~~bash
java --patch-module com.example.app=build/patches/app ...
~~~

`--patch-module` injects additional classes or resources into the contents of an existing module at runtime. It typically serves testing, instrumentation, or controlled compatibility workarounds.

It does not modify `module-info.class` in the sense of updating a released descriptor. Do not use module patching as a long-term replacement for redesigning dependencies, exports, or opens.

If a module needs a new API package, edit the module's source and descriptor and rebuild. If you are testing a class change before packaging, patching a module can be a suitable temporary tool.

## 8. Placing Options in the Run Command

Launcher module options are placed before the option identifying the application, such as `-m` or `-jar`.

Running a modular application:

~~~bash
java --add-opens java.base/java.lang=com.example.framework \
     --module-path mods \
     --module com.example.app/com.example.app.Main
~~~

Running an executable JAR on the classpath:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED \
     -jar app.jar
~~~

If multiple permissions are needed, multiple options can be declared:

~~~bash
java --add-reads com.example.app=com.example.legacy \
     --add-exports com.example.legacy/com.example.legacy.api=com.example.app \
     --add-opens java.base/java.lang=com.example.framework \
     --module-path mods \
     --module com.example.app/com.example.app.Main
~~~

Store launch configurations in a controlled script or deployment configuration if a workaround must be applied consistently. This ensures environments run with the same set of arguments and avoids each developer's machine adding different flags manually.

## 9. Limitations and Risks of Workarounds

Runtime flags have a clear scope of impact, yet keeping them long-term without governance creates maintenance costs:

- **Hiding module design flaws:** incorrect dependencies or package boundaries can be masked by additionally granted permissions.
- **Widening access scope:** `ALL-UNNAMED` grants permissions to all unnamed modules, broader than a specific target module.
- **Launch configuration dependency:** running via an IDE, service wrapper, container, or another script can omit required flags.
- **Internal implementation dependency:** packages like `sun.nio.ch` are not stability-guaranteed APIs. Newer JDK releases can alter or remove the implementation.
- **Harder encapsulation and control:** access permissions sit in deployment parameters rather than module contracts reviewed alongside source code.

Since JDK 17, strong encapsulation for internal JDK packages has been strictly enforced; the legacy `--illegal-access` option has been removed. When a legacy library accesses JDK internals, prefer upgrading the library or migrating to supported APIs. Flags like `--add-opens` or `--add-exports` should only be scoped, time-bound bridges.

## 10. Recommended Resolution Workflow

When encountering a module access error, proceed in order:

1. Read the exact error message to identify whether it is readability, export, or deep reflection.
2. Identify the source module, package, and target module mentioned in the error.
3. Inspect descriptors using `jar --describe-module` or `java --describe-module`.
4. If you need to verify a hypothesis quickly, add exactly one runtime flag with a narrow target and re-run.
5. If the workaround confirms the cause, identify which module is owned by your project.
6. For project-owned modules, fix `requires`, `exports`, or `opens` to match the intended contract, then rebuild and retest.
7. For third-party libraries, prefer upgrading or replacing the library. If forced to keep a workaround, manage the flag in deployment configuration and document which dependency requires that permission.
8. Once the descriptor or library is fixed, remove the temporary flag and verify the application still runs.

Do not add all flags at once from the start. Changing one small permission at a time helps pinpoint the exact cause and avoids granting excessive permissions.

## 11. Key Takeaways

- `--add-reads` adds readability; the corresponding descriptor directive is usually `requires`.
- `--add-exports` exposes a package to a target module; the corresponding descriptor directive is `exports`.
- `--add-opens` opens a package for deep reflection; the corresponding descriptor directive is `opens`.
- `--add-modules` adds root modules to resolve, not replacing `requires`, `exports`, or `opens`.
- `--patch-module` adds content to a module at runtime, not a long-term descriptor fix.
- Launcher flags are suitable for diagnostics, experimentation, or migration bridges.
- Stable relationships owned by the project should be expressed in `module-info.java`, tested, and released with the module.

Treat runtime workarounds as evidence that identifies which permission is missing. Once you know the cause and control the relevant modules, move that relationship into the appropriate descriptor so the runtime configuration becomes simple, consistent, and maintainable.
