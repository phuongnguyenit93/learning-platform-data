# --add-reads: Adding Temporary Readability

## 1. Readability in the Java Module System

In the Java Platform Module System (JPMS), each named module has a set of modules that it **reads**. The readability relationship determines whether code in the current module can reference public types exported by another module.

Normally, this relationship is declared in **module-info.java** using **requires**:

~~~java
module com.example.app {
    requires com.example.logging;
}
~~~

The declaration above creates an explicit dependency between **com.example.app** and **com.example.logging**. At build time and runtime, the module system must resolve the logging module along with its required dependencies.

However, there are situations where temporary readability needs to be added without modifying the module descriptor, such as:

- Migrating an application from the classpath to a named module.
- Needing to connect a named module with a legacy library on the classpath.
- Testing or diagnosing a module graph.
- A plugin or module is selected by runtime configuration, so the dependency cannot be written directly in the main module's descriptor.

The **--add-reads** option allows adding a readability edge to the module graph for a compilation or launch. This is a command-line adjustment that does not rewrite **module-info.java** and does not turn a temporary dependency into a long-term module contract.

## 2. Syntax of --add-reads

General syntax:

~~~text
--add-reads <module>=<target-module>(,<target-module>)*
~~~

Where:

- **module** is the named module to which read access is being added.
- **target-module** is the module that the source module will be able to read.
- Multiple target modules can be specified, separated by commas.
- **ALL-UNNAMED** is a special name representing all unnamed modules, typically classes and JARs on the classpath.

Example:

~~~bash
java --add-reads com.example.app=com.example.logging \
     --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

This command adds a relationship so that **com.example.app** can read **com.example.logging** during the current run.

Multiple target modules can be added:

~~~bash
java --add-reads com.example.app=com.example.logging,com.example.metrics \
     --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

You must ensure that the target modules can be found and resolved in the module graph. If a module has not yet been included in the set of root modules to resolve, you may also need to specify **--add-modules**:

~~~bash
java --module-path mods \
     --add-modules com.example.logging \
     --add-reads com.example.app=com.example.logging \
     -m com.example.app/com.example.app.Main
~~~

**--add-modules** adds the module to the set of modules to resolve; **--add-reads** adds the readability relationship from the source module to the target module. The two options solve two different problems.

## 3. Using --add-reads with ALL-UNNAMED

Legacy libraries are often placed on the classpath and belong to the unnamed module. A named module does not automatically read the unnamed module. When a named module needs to use the public API of a classpath library during a transition period, you can add readability to **ALL-UNNAMED**.

Suppose the legacy library has a class:

~~~java
package com.legacy.codec;

public class LegacyEncoder {
    public String encode(String value) {
        return "encoded:" + value;
    }
}
~~~

The JAR containing this class is in the **legacy-libs** directory. The modular application has the code:

~~~java
package com.example.app;

import com.legacy.codec.LegacyEncoder;

public class Main {
    public static void main(String[] args) {
        LegacyEncoder encoder = new LegacyEncoder();
        System.out.println(encoder.encode("hello"));
    }
}
~~~

The application's module descriptor:

~~~java
module com.example.app {
}
~~~

To compile the module and allow it to read the classpath library, you can use:

~~~bash
javac \
  --class-path "legacy-libs/*" \
  --add-reads com.example.app=ALL-UNNAMED \
  --module-source-path src \
  -d out \
  -m com.example.app
~~~

When running, the corresponding readability must be added for the runtime:

~~~bash
java \
  --module-path out \
  --class-path "legacy-libs/*" \
  --add-reads com.example.app=ALL-UNNAMED \
  -m com.example.app/com.example.app.Main
~~~

This example illustrates a temporary bridge between a named module and a library on the classpath. **ALL-UNNAMED** includes all classpath JARs belonging to unnamed modules in that runtime environment; it is not limited to a single specific JAR.

Because of its broad scope, consider converting the legacy library into a named module or placing the dependency in the module descriptor once the architecture has stabilized. If the application uses the library's API over the long term, an explicit **requires** declaration on the module path is usually easier to manage and control.

## 4. Using --add-reads at Compile Time

javac supports **--add-reads** to adjust readability during compilation. This can be useful when testing a module change or when temporarily integrating with a library that does not yet have an appropriate module descriptor.

For example, module **com.example.app** needs to read module **com.example.legacy** in the **mods** directory:

~~~bash
javac \
  --module-path mods \
  --add-modules com.example.legacy \
  --add-reads com.example.app=com.example.legacy \
  --module-source-path src \
  -d out \
  -m com.example.app
~~~

In the example:

- **--module-path mods** provides the legacy module.
- **--add-modules com.example.legacy** requests adding the legacy module to the set of root modules to resolve.
- **--add-reads com.example.app=com.example.legacy** allows the app module to read the legacy module during the compilation pass.
- **-m com.example.app** selects the app module to compile.

If the source code belongs to a named module and directly uses the legacy API, succeeding at the build step with this command-line option alone is not enough for the application to run properly. At runtime, the corresponding readability relationship must also exist in the runtime module graph.

Example run command:

~~~bash
java \
  --module-path "out:mods" \
  --add-modules com.example.legacy \
  --add-reads com.example.app=com.example.legacy \
  -m com.example.app/com.example.app.Main
~~~

On Windows, replace the module path separator with a semicolon:

~~~powershell
java --module-path "out;mods" --add-modules com.example.legacy --add-reads com.example.app=com.example.legacy -m com.example.app/com.example.app.Main
~~~

Both the compile phase and runtime must be configured. The javac option is not automatically saved into the compiled module descriptor for the JVM to apply on subsequent runs.

## 5. --add-reads Does Not Replace requires

Suppose the app module needs to use the logging module's API. There are two ways to describe the relationship:

**Long-term approach in the module descriptor:**

~~~java
module com.example.app {
    requires com.example.logging;
}
~~~

**Temporary addition on the command line:**

~~~bash
java --add-reads com.example.app=com.example.logging \
     --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

Both can establish readability in their respective contexts, but their management implications differ:

- **requires** is part of the module design, compiled into the module descriptor, and distributed along with the module.
- **--add-reads** is an external configuration that takes effect only for the compilation or launch to which the option is passed.

If a dependency is a stable part of the API or implementation, declare **requires**. Use **--add-reads** when you need temporary intervention, testing, backward compatibility, or special runtime configuration handling.

Do not use **--add-reads** to hide a module descriptor missing dependencies in a modularized product. Others may run the same module without that option and encounter readability errors.

## 6. Readability Differs from exports and opens

A common mistake is confusing whether a module can read another module with whether a package of that module is accessible.

Suppose module **com.example.internal** contains:

~~~java
module com.example.internal {
    // Does not export package com.example.internal.api
}
~~~

The app module is granted additional readability:

~~~bash
java --add-reads com.example.app=com.example.internal \
     --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

Even though app can read the internal module, it still cannot access types in packages that the internal module has not exported.

Related mechanisms:

| Mechanism | What does it control? |
|---|---|
| **requires** | Readability declared in the descriptor |
| **--add-reads** | Additional readability via the command line |
| **exports** | Exposes a package so reading modules can use public types |
| **--add-exports** | Grants additional access to public package types via the command line |
| **opens** | Allows deep reflection into a package |
| **--add-opens** | Grants additional deep reflection access via the command line |
| **--add-modules** | Adds modules to the set of root modules to resolve |

For example, for the app module to read the library module and access a public package that the library exports conditionally, both the readability relationship and the export rules must be properly satisfied. If the goal is deep reflection on private members, consider **opens** or **--add-opens**.

Not every access error can be solved with **--add-reads**. Read the error message to distinguish between a module not reading another, an unexported package, and closed reflection.

## 7. Scope and Limitations of --add-reads

**--add-reads** adds a readability relationship, but it does not perform the following:

- Does not add modules or JARs to the module path.
- Does not automatically resolve the target module if that module has not been included in the graph.
- Does not export packages from the target module.
- Does not open packages for deep reflection.
- Does not modify or rewrite **module-info.java**.
- Does not automatically propagate configuration from javac to the JVM.
- Does not download dependencies from the network or replace dependency management tools.

This option also does not alter the source code or packaging structure of a library. If the target module does not exist or the module name is incorrect, fix the module path or module name first.

With **ALL-UNNAMED**, remember that this is a pseudo-module representing unnamed modules, not a module JAR that can be found on the module path. It is useful for legacy classpath integration, but has a broader scope than a specific named module.

## 8. Using --add-reads in Testing Environments

An application may need additional readability only during an integration test. In that case, you can pass the option to the test run command instead of modifying the main module's descriptor.

Example running a test module or application with a support module:

~~~bash
java \
  --module-path "out:mods:test-mods" \
  --add-modules com.example.test.support \
  --add-reads com.example.app=com.example.test.support \
  -m com.example.test/com.example.test.Runner
~~~

This example instructs module **com.example.app** to read the support module in the test run's module graph. The module names and root module should be replaced with the project's actual structure.

If a test framework uses deep reflection into packages of the application module, **--add-reads** is not sufficient. You must configure **--add-opens** for the appropriate package and framework module, or declare appropriate package opening in the test configuration's descriptor.

Keep these expanded options in a separate test configuration. Do not include them in production launch commands if the application does not need them.

## 9. Diagnosing Readability Errors

When encountering a message such as:

~~~text
module com.example.app does not read module com.example.legacy
~~~

You can take the following steps:

1. Identify the source module mentioned in the error.
2. Identify the target module that owns the class or package the code is using.
3. Check whether the target module is present on the module path.
4. If the dependency is permanent, declare **requires** in the module descriptor.
5. If only a temporary adjustment is needed, try **--add-reads source=target** in the corresponding javac or java command.
6. If the target module is not yet resolved, consider **--add-modules target**.
7. If the error subsequently turns into a package-not-visible error, check **exports**.
8. If an error occurs when reflection accesses a private member, check **opens** or **--add-opens**.

You can inspect a module descriptor using:

~~~bash
java --module-path mods --describe-module com.example.legacy
~~~

And view the modules currently recognized:

~~~bash
java --module-path mods --list-modules
~~~

These commands help confirm module names and resolution locations before changing configuration.

## 10. Safe Usage Workflow

When you need to add temporary readability, follow this workflow:

1. Clearly identify which module needs to read which module.
2. Verify that the target module can be found on the module path or in the runtime.
3. Determine whether the error is actually readability, exports, or deep reflection.
4. Pass **--add-reads** to the exact phase that needs adjustment: javac or java.
5. If the target module is not yet resolved, consider **--add-modules**.
6. Test both compile time and runtime because the configurations of the two phases are independent.
7. Document the reason for using the option and the scope of modules expanded.
8. When the dependency becomes stable, switch to an appropriate **requires** declaration in the module descriptor.

## 11. Key Takeaways

- **--add-reads source=target** adds a readability relationship from the source module to the target module.
- **ALL-UNNAMED** represents classes and JARs belonging to unnamed modules on the classpath.
- The option can be used with javac for compilation and with java for execution; the two configurations do not synchronize automatically.
- The target module must be found and resolved; **--add-modules** may be needed to add the module to the graph.
- Readability does not mean package visibility or deep reflection.
- **--add-reads** is a command-line adjustment and does not replace a formal dependency declaration via **requires**.

Use **--add-reads** as an intentional module graph adjustment tool for migration, testing, or legacy integration. For stable dependencies of a named module, explicitly declaring **requires** in the module descriptor keeps builds and runtime more consistent.
