# --patch-module: Replacing Module Contents

> Scope: Java Platform Module System (JPMS, since Java 9). The **--patch-module** option allows adding to or overriding classes and resources of a named module with content located in a directory or JAR outside the original module.

## Objectives

After this lesson, you will be able to:

- Explain what **--patch-module** is used for and when to use it.
- Write the exact syntax when running with **java** and compiling with **javac**.
- Prepare a patch directory/JAR with the appropriate package structure.
- Understand how patch contents are attached to the target module and prioritized during class loading.
- Distinguish patching contents from modifying a module descriptor.
- Distinguish **--patch-module** from **--add-exports**, **--add-opens**, **--add-reads**, and **--upgrade-module-path**.
- Diagnose cases where a patch is not applied or causes runtime errors.

## 1. What Is --patch-module?

**--patch-module** is an option for the Java launcher and Java compiler to add or override contents of a named module. Patch contents typically reside in one or more directories of compiled classes or JARs.

For example, module **com.acme.lib** has been packaged in a modular JAR. You want to test a new version of a class without modifying the original JAR. You can place the replacement class in a patch directory and run:

~~~bash
java --patch-module com.acme.lib=build/patch \
     --module-path mods \
     --module com.acme.app/com.acme.app.Main
~~~

In the example:

- **com.acme.lib** is the name of the module to patch.
- **build/patch** is the directory containing the additional or replacement classes/resources.
- **mods** contains the application module and library module.
- **com.acme.app/com.acme.app.Main** is the main module and main class to launch.

Patch contents are treated as part of the target module at runtime. Therefore, a patched class belongs to that module, rather than becoming a class of the unnamed module as happens when placing a JAR on the class path.

This option is useful for testing, debugging, trying out a hotfix, swapping an implementation in a controlled environment, or adding classes to a module without repackaging the original module. It is not a general-purpose plugin mechanism and must be used intentionally.

## 2. Syntax of --patch-module

General syntax:

~~~text
--patch-module <module>=<file>(<path-separator><file>)*
~~~

Where:

- **module** is the name of the named module to patch.
- **file** is the path to a directory or JAR containing the patch classes/resources.
- **path-separator** is the operating system's path separator.

You can specify multiple paths in a single value:

Linux/macOS:

~~~bash
--patch-module com.acme.lib=build/patch:build/extra-patch
~~~

Windows:

~~~powershell
--patch-module com.acme.lib=build/patch;build/extra-patch
~~~

The separator is a colon (**:**) on Linux/macOS and a semicolon (**;**) on Windows. When a path contains spaces, wrap the entire module-equals-path value in quotes appropriate for the shell:

~~~bash
java "--patch-module=com.acme.lib=build/patch files" ...
~~~

You can use the option multiple times to patch different modules:

~~~bash
java \
  --patch-module com.acme.lib=build/patch-lib \
  --patch-module com.acme.util=build/patch-util \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

Each invocation targets one module. Do not use a package name instead of a module name, and do not omit the module name before the equals sign.

## 3. Preparing a Patch Directory

Suppose a library module has the structure:

~~~text
mods/
└── com.acme.lib.jar
~~~

The JAR contains the class:

~~~text
com/acme/lib/Message.class
~~~

Module descriptor inside the JAR:

~~~java
module com.acme.lib {
    exports com.acme.lib;
}
~~~

You want to replace the **com.acme.lib.Message** class with a new version. Prepare a patch directory with the corresponding package structure:

~~~text
build/
└── patch/
    └── com/
        └── acme/
            └── lib/
                └── Message.class
~~~

The package path must start from the root directory of the patch path. Thus, if the package is **com.acme.lib**, the patch root must be the directory immediately above the **com** directory.

Do not set the patch root deep inside the package, such as **build/patch/com/acme/lib**, if that directory does not contain another **com/acme/lib** package tree. The launcher searches for classes by package path relative to the patch root.

The patch path can be a class directory or a JAR. Example:

~~~text
build/
├── patch-classes/
│   └── com/acme/lib/Message.class
└── patch.jar
~~~

If using a JAR, the JAR contents must have a similar package path:

~~~text
com/acme/lib/Message.class
~~~

## 4. Compiling Classes for a Patched Module

When compiling source files belonging to a package of the target module, use **javac --patch-module** so the compiler treats those sources as part of the module being patched.

Example replacement source:

~~~text
src-patch/
└── com/acme/lib/Message.java
~~~

Content:

~~~java
package com.acme.lib;

public class Message {
    public static String greet(String name) {
        return "[patched] Hello, " + name + "!";
    }
}
~~~

Compile:

~~~bash
javac \
  --module-path mods \
  --patch-module com.acme.lib=src-patch \
  -d build/patch \
  src-patch/com/acme/lib/Message.java
~~~

Meaning:

- **--module-path mods** helps the compiler locate the target module.
- **--patch-module com.acme.lib=src-patch** places the sources in the patch root into the context of module **com.acme.lib**.
- **-d build/patch** writes the compiled classes into the patch root.
- The source path at the end of the command is the Java file to compile.

Result:

~~~text
build/patch/com/acme/lib/Message.class
~~~

You can use multiple source directories or pre-built JARs, but ensure the package paths are correct and the classes are compiled compatibly with the Java version of the target runtime.

If the patch source references types inside the target module, the compiler must be able to see that module on the module path. Do not compile a patch as regular source on the class path if the goal is to add to or replace content of a named module.

## 5. Running the Application with the Patched Module

Suppose:

- **mods/com.acme.lib.jar** is the original module.
- **mods/com.acme.app.jar** is the application module.
- **build/patch** contains the new class for **com.acme.lib**.

Run:

~~~bash
java \
  --patch-module com.acme.lib=build/patch \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

When the launcher creates the module configuration, content from the patch path is attached to the target module. Classes or resources with matching names in the patch can replace corresponding content in the original module; new classes/resources can be added to the module.

If the program calls:

~~~java
System.out.println(Message.greet("Lan"));
~~~

and the patched class is loaded, the example output will be:

~~~text
[patched] Hello, Lan!
~~~

The order of patch paths also matters if multiple patch paths contain the same class/resource. Avoid having multiple duplicate-named versions appear together in the patch list; keep the patch set small and reproducible.

**--patch-module** must be passed to the exact Java run that needs to apply the patch. Adding the option only during compilation does not cause the runtime to automatically use the new class. Likewise, the patch path is not written back into the original JAR; it is a separate input for that run.

## 6. Patching JDK Modules

You can use **--patch-module** to patch a system module, for example **java.base**, in a test environment:

~~~bash
java \
  --patch-module java.base=build/patch-java-base \
  -version
~~~

The module name must be the exact system module name. The patch directory tree must mirror the packages inside that module.

Patching core modules carries high risk: JDK classes can be used very early by the JVM and core libraries, many classes have internal invariants, and incompatible changes can cause JVM startup to fail. Use only in controlled experiments, test on the exact JDK build, and keep a way to restore the original runtime.

Do not use the **java.base** patch example as a recipe to fix the JDK in production. If you need to change the behavior of an application library you maintain, prefer updating the module/JAR and releasing a new artifact.

## 7. Does --patch-module Modify module-info.class?

**No.** This option adds or overrides classes/resources within module contents. It does not change the target module's module descriptor.

Therefore, patching does not automatically add:

- **requires** directives to create new dependencies.
- **exports** directives to expose packages to other modules.
- **opens** directives to allow deep reflection.
- **uses** or **provides** directives to change service declarations.
- A new module name or a new module descriptor version.

If a patch adds a new package to a module, that package belongs to the target module but does not automatically become an exported package. If code in another module needs to access an unexported package, access must be adjusted via an appropriate descriptor or a dedicated launcher option during testing.

If you need to modify the descriptor permanently, update the **module-info.java** source and rebuild the modular JAR. Do not use a patch path assuming you have changed the module's dependencies or API boundaries.

## 8. Distinguishing from Other Module Options

| Option | Effect | Does it replace classes/resources in the module? |
|---|---|---|
| **--patch-module** | Adds or overrides classes/resources of a module | Yes |
| **--add-exports** | Allows the target module to export a package to another module for the run | No |
| **--add-opens** | Opens a package for deep reflection at runtime | No |
| **--add-reads** | Adds a readability relationship between modules | No |
| **--upgrade-module-path** | Provides a replacement module for a system module during resolution | Replaces the module via the upgrade mechanism, not merely patching classes |

Example opening a package for reflection:

~~~bash
java --add-opens com.acme.lib/com.acme.lib.internal=ALL-UNNAMED ...
~~~

Example exporting a package to a specific module:

~~~bash
java --add-exports com.acme.lib/com.acme.lib.internal=com.acme.app ...
~~~

These two options only adjust access permissions in the module system; they do not replace class implementations. If the goal is to replace class contents, use **--patch-module**.

If the goal is to replace an entire system module with another module version, learn about **--upgrade-module-path**. Patching a module and upgrading a module solve two different problems: patching replaces contents inside the selected module, whereas upgrading supplies a replacement module through the upgrade mechanism.

## 9. Patching at Compile Time and Patching at Runtime

There are two separate phases:

**At compile time**, use the javac option:

~~~bash
javac \
  --module-path mods \
  --patch-module com.acme.lib=src-patch \
  -d build/patch \
  src-patch/com/acme/lib/Message.java
~~~

The compiler processes patch sources in the context of the target module. This is the right approach when patch sources reside in a package of a named module.

**At runtime**, use the java option:

~~~bash
java \
  --patch-module com.acme.lib=build/patch \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

The launcher attaches the patch contents to the target module at runtime. The two steps do not replace each other: javac produces class files; java needs the patch path containing those class files to use them at runtime.

In a controlled build workflow, keep patch sources, patch classes, and launch commands in separate configurations. This helps avoid confusion between newly compiled class files and stale class files left over in the build directory.

## 10. Verifying That a Patch Was Applied

You can verify at multiple layers:

1. Confirm the class file was generated at the exact package location inside the patch root.
2. Use **jar tf patch.jar** if the patch is packaged as a JAR to inspect entries.
3. Run the application with the exact command containing **--patch-module**.
4. Use an easily recognizable output in the patched class, such as a version string or distinct test behavior.
5. When you need to identify the source of a loaded class, enable class-loading logs.

Example:

~~~bash
java -Xlog:class+load=info \
  --patch-module com.acme.lib=build/patch \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

Class-loading logs can help identify which classes are loaded and the load source reported by the JVM. You should not rely solely on **java --describe-module** to confirm a patch replaced a class: that command describes the module descriptor, whereas patching does not modify the descriptor.

You can inspect the module descriptor after running or using:

~~~bash
java --describe-module com.acme.lib --module-path mods
~~~

The output describes the original module, not the list of patched classes. To prove the new class is being used, inspect actual behavior or class-loading logs.

## 11. Common Errors and Troubleshooting

| Symptom | Common Cause | Resolution |
|---|---|---|
| Runtime still uses the old class | Wrong patch root, wrong package path, or launcher did not receive the option | Check that the class sits under the right package relative to the patch root; pass **--patch-module** to the actual java command |
| Compiler reports package belongs to another module | Patch source was compiled as regular source without patch context | Compile using **javac --patch-module module=source-root** |
| Module not found | Wrong module name or target module not on module path/configuration | Check name with **jar --describe-module** and check the module path |
| New class causes linkage errors | Patched class is incompatible with the API, fields, methods, or binary contract expected by other modules | Compile against the right API/runtime; check signatures and dependencies |
| New package is inaccessible from other modules | Patch added a package but the module descriptor does not export that package | Update descriptor if the API needs to be exposed; use **--add-exports** only for testing |
| Reflection is still blocked | Patching does not automatically open packages | Use appropriate **--add-opens** or redesign access permissions |
| Patch has no effect when run via another service/launcher | Option was placed on the build command or another process, not in the actual JVM | Pass the patch option to the exact java/launcher command starting the application |
| JVM startup fails when patching a system module | Incompatible core class or patch breaks internal JDK assumptions | Remove patch, restore clean environment, and test only on the exact JDK version |

A practical debugging sequence:

1. Identify the exact target module name.
2. Confirm the target module can be resolved from the module path or is a system module.
3. Check that the patch path is a valid, existing directory/JAR.
4. Check the package path relative to the patch root.
5. Recompile the patch using **javac --patch-module** if sources just changed.
6. Check that the actual java command has **--patch-module** with the right module and path.
7. Enable class-loading logs or run a test with output that clearly distinguishes original and patched versions.

## 12. Key Takeaways

- **--patch-module module=path** adds to or overrides classes/resources of a named module.
- The patch path can be a directory or a JAR; package structure starts from the root of the patch path.
- Use **javac --patch-module** when compiling patch sources and **java --patch-module** when running.
- Patch content is attached to the target module; patched classes belong to that module.
- Patching does not modify **module-info.class**, and does not automatically add **requires**, **exports**, **opens**, **uses**, or **provides**.
- **--add-exports**, **--add-opens**, and **--add-reads** change access/readability permissions, not classes.
- **--upgrade-module-path** replaces a module via the upgrade mechanism; **--patch-module** only patches contents.
- Prefer using it for controlled testing and debugging; official releases should update fully built and tested modules/JARs.

## References

- [The java Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [The javac Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [JEP 261 — Module System](https://openjdk.org/jeps/261)
- [Module System — Java Platform Module System](https://openjdk.org/projects/jigsaw/spec/)
