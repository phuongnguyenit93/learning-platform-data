# IllegalAccessError After Module Graph Changes

When a Java application compiles successfully but later encounters an `IllegalAccessError` at runtime, the cause may lie in a change to the module graph or module descriptors between compile time and runtime. A module that previously could read another module, or previously had permission to access a package, may no longer have that permission in the new runtime configuration.

`IllegalAccessError` is a runtime linkage error belonging to the `LinkageError` family. It typically indicates that bytecode is attempting to access a class or member that the JVM does not permit accessing under the actual loaded structure. With JPMS, at least two conditions must be checked: **readability** (whether the calling module reads the target module) and **accessibility** (whether the package is exported by the target module to the calling module).

This lesson focuses on errors arising after module graph changes: library upgrades, changes to `module-info.java`, module path changes, or running older bytecode with a newer descriptor.

## 1. What Is IllegalAccessError?

`IllegalAccessError` is a `LinkageError` thrown by the JVM when a class attempts to access a class or member whose actual access permissions disallow it. The error typically occurs when linking symbolic references in bytecode to classes/members at runtime.

An example message may look like:

~~~text
java.lang.IllegalAccessError:
  class com.acme.app.Main (in module com.acme.app)
  cannot access class com.acme.library.internal.Helper
  (in module com.acme.library)
  because module com.acme.library does not export
  com.acme.library.internal to module com.acme.app
~~~

This message indicates:

- The calling class is `com.acme.app.Main`, belonging to module `com.acme.app`.
- The accessed class is `com.acme.library.internal.Helper`, belonging to module `com.acme.library`.
- Package `com.acme.library.internal` is not exported to the calling module.
- The JVM denied access when linking/executing bytecode.

Another variant may mention that the calling module does not read the target module. In that case, check the readability edge in the module graph.

Not every `IllegalAccessError` is caused by JPMS. The error can also happen when a class, method, or field is no longer public or no longer satisfies standard Java access rules. Read the full class, module, package, and member names in the message before choosing a fix.

## 2. Two Key JPMS Conditions: Readability and Exports

For a class in module A to use a public type belonging to module B, both conditions normally must be satisfied:

1. Module A **reads** module B.
2. Module B **exports** the package containing the public type to module A.

Example:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

~~~java
module com.acme.app {
    requires com.acme.library;
}
~~~

The application can use public types in the `com.acme.library.api` package. The `requires` edge establishes readability from `com.acme.app` to `com.acme.library`; the `exports` directive permits accessing the public API in the package.

If `requires com.acme.library` is removed, the app module may fail to read the library module. If `exports com.acme.library.api` is removed, the app module can read the library module but cannot access types in that package. The two errors have different causes and must be fixed on the corresponding edge.

### Readability does not equal accessibility

- `requires` controls which modules the current module reads.
- `exports` controls which packages other modules can access under standard Java rules.
- `opens` grants deep reflection permission for a package; it does not replace `exports` for normal API calls.

A package can be exported to module A but not exported to module B. This is a qualified export:

~~~java
module com.acme.library {
    exports com.acme.library.api;
    exports com.acme.library.spi to com.acme.app;
}
~~~

Only module `com.acme.app` is permitted to access package `com.acme.library.spi` under the qualified export directive.

## 3. Why Do Module Graph Changes Cause Errors?

Several common scenarios exist.

### Dependency descriptor changes

In an older library version:

~~~java
module com.acme.library {
    exports com.acme.library.internal;
}
~~~

The application inadvertently used classes in the `internal` package. Later, the library changed its descriptor:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

Package `com.acme.library.internal` is no longer exported. Previously compiled application bytecode still contains symbolic references to the old class, but when run against the new version, the JVM no longer permits access. The result can be an `IllegalAccessError`.

This signals that the application depends on a package that is no longer part of the published API.

### A requires edge is removed or changed

If the app module previously read the library module via `requires`, `requires transitive`, or an additional configuration, and the new descriptor/runtime graph no longer has the corresponding readability edge, accessing classes at runtime can fail.

Do not rely on `requires transitive` from an intermediate module if the application actually uses the dependency's API directly. Declare a direct dependency when your module uses types belonging to that module.

### Runtime loads the wrong module version

A build may compile against one JAR version while the launch command uses a different module path. Both versions share the same module name but have different descriptors and exported packages. The launcher resolves modules from the sources found in the runtime configuration, resulting in different access permissions than at compile time.

### Moving from classpath to module path

A library that previously ran on the classpath belonged to the unnamed module and was accessed under classpath rules. When placed on the module path, it becomes a named module (or automatic module), so readability and exports rules are enforced more explicitly. Legacy code may expose dependencies on internal packages.

### JDK upgrades and strong encapsulation

Recent Java releases have tightened encapsulation of JDK internals. Starting in JDK 17, the `--illegal-access` mechanism no longer restores broad access modes as in older releases. Applications accessing JDK internal APIs may need to switch to public APIs or configure targeted export/open permissions during transition.

## 4. Distinguishing IllegalAccessError from Reflection Access Errors

Not every access error is an `IllegalAccessError`.

| Error | Common Occurrence / Trigger | Meaning |
|---|---|---|
| `IllegalAccessError` | Runtime linkage/bytecode access | Bytecode accesses a disallowed class or member |
| `IllegalAccessException` | Reflection APIs such as `Method.invoke` in certain cases | Reflection cannot perform the access operation |
| `InaccessibleObjectException` | `setAccessible(true)` or `trySetAccessible()` cannot open deep access | Package/module is not open to the caller |
| `ClassNotFoundException` | Loading a class by name, typically via class-loading APIs | Class was not found |
| `NoClassDefFoundError` | Linkage/runtime after a required class is unavailable | Required class definition cannot be found/loaded |
| `NoSuchMethodError` | Runtime linkage | Bytecode references a method not present in the loaded class version |

Reflection example:

~~~java
Field field = SomeType.class.getDeclaredField("secret");
field.setAccessible(true);
~~~

If the package containing `SomeType` is not open to the calling module, this operation can throw `InaccessibleObjectException`. This is an `opens` and deep reflection issue.

Conversely, if code directly calls a public class in an unexported package, the issue is `exports` and can lead to `IllegalAccessError`.

Do not use `--add-opens` to fix every `IllegalAccessError`. First determine whether the error is normal bytecode access or reflection.

## 5. Diagnostic Workflow

When an error appears only at runtime or after upgrading modules, gather evidence in order.

### Step 1: Read the full stack trace

Record:

- The calling class and the module owning the calling class.
- The accessed class/member and the module owning it.
- The denied package.
- Whether the message mentions missing readability, missing export, or ordinary class/member access rules.
- Any JARs or paths appearing in the stack trace.

Do not look only at the first line and immediately conclude that `--add-exports` is needed.

### Step 2: Inspect the actual runtime module graph

~~~bash
java --show-module-resolution   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

The output helps confirm root modules, resolved dependencies, and the locations from which modules are selected. If the library module comes from an unexpected path, check the module path and the running artifact.

### Step 3: Describe both modules' descriptors

~~~bash
java --module-path mods --describe-module com.acme.app
java --module-path mods --describe-module com.acme.library
~~~

Check:

- Whether app has `requires com.acme.library`.
- Whether library exports the right package to app.
- Whether the export is unqualified or qualified.
- Whether any relevant `opens` exists if the error stems from reflection.

### Step 4: Inspect compiled descriptors and runtime artifacts

You can read the descriptor directly in the output directory:

~~~bash
javap -v out/com.acme.library/module-info.class
~~~

For a modular JAR:

~~~bash
jar --describe-module --file lib/com.acme.library.jar
~~~

Compare the descriptor of the dependency used at compile time with the descriptor of the dependency actually running. Make sure stale build outputs are not mixed with new artifacts.

### Step 5: Check dependencies with jdeps

~~~bash
jdeps --module-path mods --check com.acme.app
~~~

If you suspect the application depends on a JDK internal API:

~~~bash
jdeps --jdk-internals app.jar
~~~

`jdeps` helps analyze static dependencies. It does not replace observing module resolution at runtime, but it can point out dependencies or internal APIs that need attention.

## 6. Preferred Fix: Fix Module Descriptors and Dependencies

If the application uses a valid public API, update descriptors to express the dependency accurately.

For example, if the app module genuinely uses the library module:

~~~java
module com.acme.app {
    requires com.acme.library;
}
~~~

If the library module intends to support that API, export the corresponding package:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

If the API is intended only for specific modules:

~~~java
module com.acme.library {
    exports com.acme.library.spi to com.acme.app;
}
~~~

If the app module needs to read another module whose dependency is not described in the descriptor (for instance, due to a special deployment configuration), you can use `--add-reads` as a temporary compatibility measure. However, for stable application dependencies, declare `requires` in `module-info.java`.

If the internal package was not designed as a public API, the sustainable approach is to migrate code to a supported public API. Reopening an internal package should only be done when there is a clear compatibility reason.

## 7. Command-Line Options for Transition Handling

JPMS provides several additional options. They are useful when running legacy applications, verifying root causes, or migrating incrementally. Limit target modules specifically and document clearly why they are needed.

### --add-reads

Syntax:

~~~bash
--add-reads <source-module>=<target-module>
~~~

Adds a readability edge from the source module to the target module.

Example:

~~~bash
java --add-reads com.acme.app=com.acme.optional   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

This option does not automatically export packages of the target module. If the package is not exported, adding readability alone is not enough.

### --add-exports

Syntax:

~~~bash
--add-exports <source-module>/<package>=<target-module>
~~~

Allows the target module to access public types in the specified package.

Example:

~~~bash
java --add-exports com.acme.library/com.acme.library.internal=com.acme.app   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

If the caller belongs to an unnamed module (application running on the classpath), you can use target `ALL-UNNAMED`. For a named module, specify the consuming module name explicitly.

If new code accessing an additionally exported package needs to be compiled, pass the corresponding option to javac:

~~~bash
javac --add-exports com.acme.library/com.acme.library.internal=com.acme.app ...
~~~

For the application to run with the compiled bytecode, the runtime configuration must also provide the corresponding export permission. Compile-time options do not automatically alter the module's runtime descriptor.

### --add-opens

Syntax:

~~~bash
--add-opens <source-module>/<package>=<target-module>
~~~

Opens a package for deep reflection at runtime. Example:

~~~bash
java --add-opens com.acme.library/com.acme.library.internal=com.acme.app   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

Use this option when a framework genuinely needs deep reflection into non-public members. It does not replace `--add-exports` for regular API access and is not a general fix for `IllegalAccessError`.

### Do not rely on --illegal-access

The `--illegal-access` option previously supported the strong encapsulation transition phase in older Java releases. Starting in JDK 17, it no longer restores broad access to JDK internals. Do not use it as a solution for modern applications; instead replace internal APIs or grant the exact required access with targeted options during migration.

## 8. Example Reproducing an Error When Exports Change

Suppose the first version of a library has the descriptor:

~~~java
module com.acme.library {
    exports com.acme.library.internal;
}
~~~

And class:

~~~java
package com.acme.library.internal;

public class Helper {
    public static String message() {
        return "from library";
    }
}
~~~

The app declares:

~~~java
module com.acme.app {
    requires com.acme.library;
}
~~~

The app calls directly:

~~~java
package com.acme.app;

import com.acme.library.internal.Helper;

public class Main {
    public static void main(String[] args) {
        System.out.println(Helper.message());
    }
}
~~~

Compile and run with the old library version:

~~~bash
javac --module-path mods --module-source-path src -d out --module com.acme.app
java --module-path "out:mods" --module com.acme.app/com.acme.app.Main
~~~

Then replace the library descriptor with a version that exports only the API:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

Keep the old app bytecode and re-run with the new library version. The app still contains a reference to `com.acme.library.internal.Helper`, but that package is no longer exported. The JVM may throw `IllegalAccessError` when linking the reference.

The proper ways to handle this are:

1. If `Helper` is an API the app is permitted to use, move it into an exported API package and recompile the app against the new descriptor.
2. If `Helper` is an internal implementation detail, update the app to use the public API.
3. If quick confirmation of the cause is needed during migration, try a tightly scoped `--add-exports`; do not keep broad workarounds unnecessarily.

Example using the new API package:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

The app switches to importing the class belonging to that API package, then recompiles with the correct module path. This keeps code, descriptors, and runtime artifacts in sync.

## 9. Common Pitfalls and How to Avoid Them

**Adding only `requires` and still failing.** The app module may already read the library, but the package containing the class is still not exported. Check both readability and exports.

**Adding only `exports` and still failing.** The app may not read the library module. Check the `requires` edge or required readability configuration.

**Using `opens` to fix direct access.** `opens` is for deep reflection. Regular public API access requires `exports`.

**Compile time and runtime use two different dependency versions.** Check paths using `--show-module-resolution`, describe the actual JARs, and clean build outputs before concluding.

**Using internal packages of the JDK or libraries.** Internal packages may become more strongly encapsulated after upgrades. Switch to supported public APIs; use `--add-exports` only with a migration plan and clear scope.

**Confusing with InaccessibleObjectException.** If a framework calls `setAccessible(true)` and is blocked, check `opens` and use `--add-opens` when truly needed. If bytecode directly accesses a disallowed class/member, check `requires` and `exports`.

## 10. Practice

1. Create module `com.acme.library` exporting package `com.acme.library.internal` and module `com.acme.app` requiring the library.
2. Compile and run the app with the first descriptor version.
3. Change the library descriptor to remove the internal package export while keeping the old app bytecode; re-run and observe the error.
4. Use `--show-module-resolution` to confirm the library module version and loaded location.
5. Use `java --describe-module` to inspect the library's exports and the app's requires.
6. Try `--add-exports` for the exact package and calling module to confirm the cause, then remove the workaround.
7. Refactor the app to use the public API package, recompile, and run with the new descriptor.
8. Create a reflection example using `setAccessible(true)`; compare the `InaccessibleObjectException` error and how `opens` resolves it.

When encountering `IllegalAccessError` after module graph changes, identify the calling module, target module, package, and missing permission. Compare the compile-time descriptor with the descriptor actually resolved at runtime. Prioritize fixing dependencies and API contracts; use `--add-reads`, `--add-exports`, or `--add-opens` only for the exact permission type needed and within a narrow scope.
