# IllegalAccessError Due to Missing Exports or Reads

In the Java Platform Module System (JPMS), Java code may compile successfully yet fail at runtime with **java.lang.IllegalAccessError**. One major cause is that access relationships between named modules are no longer valid at runtime: the calling module **cannot read** the module containing the target type, or the package containing that type **is not exported** to the calling module.

IllegalAccessError belongs to the **LinkageError** family. The JVM may detect the error when resolving references to a class, method, or field in bytecode. Therefore, the error often surfaces when a class is loaded or when an execution path uses the member for the first time, rather than necessarily at application startup.

This lesson focuses on errors caused by **readability** and **exports**, how to reproduce them, how to read JVM messages, how to use requires, exports, --add-reads, and --add-exports, and a workflow to fix them without widening access excessively.

## 1. Reading a module and accessing a package are two distinct conditions

For code in the named module com.example.app to use a public class in com.example.library, at least three layers must be checked:

1. **Readability:** Does com.example.app read com.example.library? Normally this is declared using requires in module-info.java.
2. **Package export:** Does com.example.library export the package containing that class to com.example.app?
3. **Java language access:** Do the class, constructor, method, or field have appropriate access modifiers?

Example library module:

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

Application module:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

With this configuration, com.example.app reads com.example.library and can use the public types of package com.example.library.api.

However, if com.example.library also has a package com.example.library.internal that is not exported, the application cannot use public classes in internal as ordinary API.

**requires allows reading a module; exports allows accessing a package.** One condition does not substitute for the other.

## 2. Why can the error appear only at runtime?

The javac compiler normally catches missing requires or exports up front. Yet situations still exist where compile-time and runtime use different configurations:

- Compiling with --add-exports while running without the corresponding flag.
- Compiling with --add-reads while runtime lacks that read relationship.
- JARs/module descriptors changed between build time and deployment.
- Bytecode was generated or transformed by instrumentation tools, proxies, or a different compiler.
- A library was compiled against a public API, while runtime provides a version whose visibility or exports changed.
- Modules are loaded in a custom ModuleLayer with a configuration differing from the build environment.

When the JVM links a bytecode reference, it checks effective access permissions at runtime. If permissions are not satisfied, IllegalAccessError can occur.

It is important not to conclude "since it compiled, runtime surely has access". JPMS also depends on the actual module graph and runtime configuration.

## 3. Distinguishing easily confused errors

| Error | When it typically occurs | Cause to examine |
| --- | --- | --- |
| error: package ... is not visible | Compilation | Missing requires/readability or package not exported. |
| java.lang.module.FindException: Module ... not found | Module resolution on launch | Module not found in module sources. |
| java.lang.module.ResolutionException | Module graph resolution | Configuration conflict or unresolvable module constraints. |
| IllegalAccessError | Runtime linking | JVM disallows class/member reference; may be due to reads, exports, or visibility. |
| IllegalAccessException | Reflective operation or MethodHandles | Caller lacks sufficient access permission during reflection. |
| InaccessibleObjectException | When attempting to enable deep reflection | Package is not open to caller, typically at setAccessible(true). |
| ClassNotFoundException | Looking up/loading a class by name | Class loader cannot find the class. |
| NoClassDefFoundError | Defining or linking a class at runtime | Missing class or an underlying error in class initialization/loading. |

IllegalAccessError is not exclusively caused by JPMS: private/public changes, class hierarchy changes, or binary incompatibility can also cause it. Read the **entire message** to determine whether the error refers to a package/module or to member visibility.

## 4. Example reproducing a missing exports error

Suppose the library has a public class inside an internal package. It can be used within the same module, yet it is not public API for other modules.

Structure:

~~~text
src/
├── com.example.library/
│   ├── module-info.java
│   └── com/example/library/internal/InternalFormatter.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

Library descriptor:

~~~java
module com.example.library {
    // Does not export com.example.library.internal.
}
~~~

Internal class:

~~~java
package com.example.library.internal;

public final class InternalFormatter {
    private InternalFormatter() {
    }

    public static String format(String text) {
        return "[" + text + "]";
    }
}
~~~

App descriptor:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

App code:

~~~java
package com.example.app;

import com.example.library.internal.InternalFormatter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(InternalFormatter.format("JPMS"));
    }
}
~~~

Under normal compilation, javac rejects the import because the internal package is not exported to com.example.app. That is the intended result of JPMS.

However, we can intentionally grant permission only at compile time to reproduce the divergence from runtime.

## 5. Compiling with --add-exports while running without it

Assuming the src directory matches the example and a JPMS-capable JDK is used, it can be compiled with:

~~~bash
javac --module-source-path src \
    --add-exports com.example.library/com.example.library.internal=com.example.app \
    -d out \
    -m com.example.library,com.example.app
~~~

The --add-exports option tells the compiler that com.example.library.internal may be used from com.example.app during this compilation.

Then run **without** the extra export permission:

~~~bash
java --module-path out \
    -m com.example.app/com.example.app.Main
~~~

The JVM may throw IllegalAccessError, with a message similar to:

~~~text
java.lang.IllegalAccessError:
class com.example.app.Main (in module com.example.app)
cannot access class com.example.library.internal.InternalFormatter
(in module com.example.library)
because module com.example.library does not export
com.example.library.internal to module com.example.app
~~~

The message clearly identifies the source module, target module, and package lacking exports. This is a runtime linking error, not a missing JAR file error.

## 6. Fixing the example with --add-exports at runtime

To grant the same permission in the JVM runtime, pass:

~~~bash
java --module-path out \
    --add-exports com.example.library/com.example.library.internal=com.example.app \
    -m com.example.app/com.example.app.Main
~~~

Expected output:

~~~text
[JPMS]
~~~

Syntax:

~~~text
--add-exports SOURCE_MODULE/PACKAGE=TARGET_MODULE
~~~

Meaning:

- SOURCE_MODULE is the module that owns the package.
- PACKAGE is the package to export.
- TARGET_MODULE is the module that wants to access public API in that package.

This option helps handle compatibility, yet it does not turn an internal package into a stable API contract. If you maintain the library and want consumers to use that class officially, redesign the API package and descriptor rather than requiring every consumer to pass flags.

## 7. Durable fix via module-info.java

If the package genuinely contains public API, the owning module can export it:

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

Suppose the class is redefined as:

~~~java
package com.example.library.api;

public final class Formatter {
    private Formatter() {
    }

    public static String format(String text) {
        return "[" + text + "]";
    }
}
~~~

The consumer imports Formatter from the api package, declares requires, and needs no --add-exports.

If only one integration module should be allowed to use a specialized package, qualified exports can be used:

~~~java
module com.example.library {
    exports com.example.library.api;
    exports com.example.library.integration
        to com.example.app;
}
~~~

This grants the export only to com.example.app. Still, it remains part of the library module's contract, so compatibility must be considered before renaming or removing it later.

Do not export an entire internal package just to silence one error without determining the intended meaning of the API.

## 8. Missing readability: a module does not read another module

The module graph uses a directed **reads** relationship. If com.example.app reads com.example.library, that does not mean com.example.library also reads com.example.app.

Normal descriptor:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

Declaring requires establishes readability from app to library. When a class in app references a public class in an exported package of library, the JVM still needs to see the appropriate read relationship at runtime.

This can be observed via the API:

~~~java
Module appModule = Main.class.getModule();
Module libraryModule = SomePublicApi.class.getModule();

System.out.println(
        appModule.canRead(libraryModule));
~~~

In the example, SomePublicApi is a public class in an exported package of library that the program can validly reference.

If canRead returns false, the read relationship from the app module to the library module does not exist in the current configuration.

Note: Java automatically provides readability to java.base for every named module. For other modules, the relationship must be established via requires, requires transitive, or corresponding valid mechanisms.

## 9. --add-reads syntax and directionality

When you need to add readability without being able to edit the descriptor, you can use:

~~~text
--add-reads SOURCE_MODULE=TARGET_MODULE
~~~

Example:

~~~bash
java --module-path out \
    --add-reads com.example.app=com.example.library \
    -m com.example.app/com.example.app.Main
~~~

The flag means com.example.app reads com.example.library. It does not mean library reads app.

However, this is only the readability relationship. If library does not export the package to app, adding --add-reads alone is still insufficient.

Therefore, when diagnosing:

- If the message says module A does not read module B: check requires and, when there is a transitional reason, --add-reads.
- If the message says module B does not export package p to module A: check exports or --add-exports.
- If neither condition holds, address both separately.

Setting --add-reads does not automatically load a module that is absent from the module graph. The target module must be found and properly resolved before the added read relationship is meaningful.

## 10. Reproducer for readability: separating compile-time and runtime

A scenario to examine:

- Library module com.example.library exports package com.example.library.api.
- Module com.example.app uses a public class in this package.
- App's module descriptor does not declare requires com.example.library.
- During compilation, the tool is granted extra readability to library.
- At runtime, that extra read relationship is gone.

Library descriptor:

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

App descriptor:

~~~java
module com.example.app {
    // Intentionally missing requires com.example.library.
}
~~~

To give javac enough information in an illustrative environment, one can use:

~~~bash
javac --module-source-path src \
    --add-reads com.example.app=com.example.library \
    -d out \
    -m com.example.library,com.example.app
~~~

At runtime, library may need to be resolved as an extra root because app does not require library:

~~~bash
java --module-path out \
    --add-modules com.example.library \
    -m com.example.app/com.example.app.Main
~~~

If app's bytecode was compiled to reference a public class from library, yet runtime lacks readability, the JVM can reject linking with IllegalAccessError.

The durable fix is declaring:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

If environmental specifics require keeping the dependency outside the descriptor, document why and supply --add-reads at the necessary stages. Do not turn compile/run inconsistency into the default design.

## 11. --add-reads to ALL-UNNAMED

A common situation is a named module needing to reference a legacy library on the classpath.

A library on the classpath belongs to the unnamed module; you cannot write requires with a specific module name for it. For certain test or migration configurations, you can use:

~~~text
--add-reads com.example.app=ALL-UNNAMED
~~~

This option allows com.example.app to read unnamed modules in an appropriate runtime.

However, it does not turn the legacy JAR into a named module and does not add that JAR to the classpath. The library must still be present at the right path and findable by the class loader.

If the library supports automatic modules or has a descriptor, another design direction is placing the JAR on the module path and using the module name verified by jar --describe-module.

When choosing ALL-UNNAMED, document why this broad relationship is needed and whether its scope is test, migration, or production.

## 12. exports can be qualified

A library module can export a package only to specific modules:

~~~java
module com.example.library {
    exports com.example.library.api
        to com.example.app;
}
~~~

In this case:

- com.example.app can access public types of api if it has proper readability.
- com.example.another does not automatically gain access to api just because the library module is resolved.
- Other modules need an appropriate contract design or qualified export.

At runtime, a class residing in a module with a different name than expected can hit IllegalAccessError despite identical imports, because qualified exports target specific module names.

Diagnostics should verify the caller's actual module name. JAR filename, Maven artifactId, and module name do not necessarily match.

To inspect module details:

~~~bash
jar --describe-module --file libs/library.jar
~~~

And:

~~~bash
java --describe-module com.example.library
~~~

The second command requires the corresponding module to be found in the launch command configuration; for modules on an additional path, supply --module-path as needed.

## 13. Using the Module API to check reads and exports

A diagnostic utility can query runtime state directly:

~~~java
public final class AccessReport {
    public static void show(Class<?> callerClass,
                            Class<?> targetClass) {
        Module caller = callerClass.getModule();
        Module owner = targetClass.getModule();

        String pkg = targetClass.getPackageName();

        System.out.println("Caller: " + caller.getName());
        System.out.println("Owner: " + owner.getName());

        System.out.println("Reads: "
                + caller.canRead(owner));
        System.out.println("Exported: "
                + owner.isExported(pkg, caller));
        System.out.println("Open: "
                + owner.isOpen(pkg, caller));
    }
}
~~~

This is an observation API; it does not mutate the module graph.

The right call direction is:

~~~java
caller.canRead(owner)
~~~

to ask whether caller reads owner.

And:

~~~java
owner.isExported(packageName, caller)
~~~

to ask whether owner's package is exported to caller.

If the target class cannot be referenced directly, you need a valid way to obtain Class<?> before checking, or use descriptor/module tooling to observe the configuration without trying to link a disallowed type.

## 14. Distinguishing ModuleDescriptor and runtime state

ModuleDescriptor stores the module directives published in the artifact:

~~~java
ModuleDescriptor descriptor =
        SomePublicApi.class.getModule().getDescriptor();
~~~

You can read:

~~~java
descriptor.requires();
descriptor.exports();
descriptor.opens();
~~~

However, the runtime module graph can be affected by --add-reads/--add-exports options and APIs permitted to add relationships.

Therefore:

- The descriptor shows the statically declared contract and configuration.
- Module.canRead and Module.isExported reflect the effective relationship between two Modules at runtime.

A technical report can use both. If the descriptor lacks requires yet canRead returns true, there may be added read permissions or an appropriate implicit relationship. Do not assume this is a contradiction before checking how the JVM was launched.

## 15. Inspecting the module graph at launch

Several useful JDK commands:

~~~bash
java --list-modules
~~~

Lists the modules observable in the launcher configuration.

~~~bash
java --module-path mods --list-modules
~~~

Shows the modules recognized in the current module path and applicable system modules.

~~~bash
java --show-module-resolution \
    --module-path mods \
    -m com.example.app/com.example.app.Main
~~~

Displays module resolution before the application runs. This is how to observe the root modules and dependencies of the module graph.

To read a JAR's module descriptor:

~~~bash
jar --describe-module --file libs/example.jar
~~~

For a named module present in a runtime configuration, you can use:

~~~bash
java --module-path mods \
    --describe-module com.example.library
~~~

These commands help identify actual modules and declared relationships. They do not themselves grant access to an unexported package.

## 16. When build and runtime use different module paths

A project may compile against JARs in a libs directory yet deploy a different set of artifacts. Then module names, descriptors, or versions may diverge.

Example scenario:

~~~text
Compile:
  com.example.library-1.0.jar
  - exports com.example.library.api

Runtime:
  com.example.library-2.0.jar
  - exports only a different package
~~~

The consumer may have been compiled against the old version's API, while the runtime JVM checks the new version's module descriptor.

How to handle:

1. Determine the exact JAR version at compile time.
2. Record the JAR found by the JVM on the runtime module path.
3. Read the descriptors of both artifacts with jar --describe-module.
4. Check whether the API changed packages, changed visibility, or removed an export.
5. Synchronize dependency management and deployment artifacts.
6. Re-run modular tests with the exact production configuration.

Do not patch over it with a string of --add-exports if the true cause is an incompatible JAR version. Synchronize dependencies first.

## 17. Errors from Java member access changes can also be IllegalAccessError

IllegalAccessError is not unique to JPMS. For example:

- A public method in an older version was changed to private in a newer version.
- A public class had its visibility reduced.
- A superclass/interface or field changed so older bytecode references are no longer valid.

Suppose the consumer compiled against:

~~~java
public class Feature {
    public void run() {
    }
}
~~~

Yet runtime supplies another version:

~~~java
public class Feature {
    private void run() {
    }
}
~~~

The consumer bytecode still calls run() assuming the method is public. The JVM may raise IllegalAccessError or a related linkage error when verifying/linking the call.

In this case, adding --add-reads or --add-exports will not fix it, because the issue is Java member access level rather than the module graph.

Therefore, always read the class/member name and error description in the stack trace before choosing a solution.

## 18. Do not confuse with deep reflection

With reflection code:

~~~java
Field field = SomeType.class.getDeclaredField("secret");
field.setAccessible(true);
~~~

If SomeType resides in another named module and the package is not open to the caller, the error is typically InaccessibleObjectException.

This case calls for reviewing opens or --add-opens, not simply --add-exports.

| Need | Mechanism typically involved |
| --- | --- |
| Call public method of class in exported package | requires/readability and exports. |
| Import public class from unexported package | exports or --add-exports; along with readability. |
| Call private method via deep reflection | opens or --add-opens to caller. |
| Module does not read another module | requires or --add-reads. |
| Class absent at runtime | Check module path/classpath and class loader. |

Do not add --add-opens to fix an IllegalAccessError that explicitly states a module does not export a package during normal linking. Read the actual access type before picking a flag.

## 19. Dynamically created modules in a ModuleLayer

A plugin application may create a new ModuleLayer from Configuration and ModuleFinder. Here, the module graph does not necessarily resemble the application's boot layer.

A plugin might:

- Be resolved in a child layer yet lack readability to a module it references.
- Read the appropriate module, yet that module's package is not exported to it.
- Use bytecode built against a different configuration.
- Be loaded by a different class loader, leading to class identity errors or linkage errors.

When encountering IllegalAccessError in a plugin:

1. Determine Class.getModule() of caller and target if obtainable validly.
2. Check Module.getLayer() and Module.getClassLoader().
3. Use caller.canRead(owner) to inspect actual readability.
4. Use owner.isExported(packageName, caller) to inspect actual exports.
5. Inspect the ModuleDescriptor of both modules.
6. Compare the module graph of the child layer and parent layers.

A class loader finding bytecode does not mean JPMS permits linking all types in an unexported package.

## 20. Role of --add-modules

A module on the module path can be **observable** yet not **resolved** into the module graph. If the target module has not been brought into the configuration, an --add-reads pointing to it may not solve the problem.

When you need to add a module as an extra root:

~~~bash
java --module-path mods \
    --add-modules com.example.library \
    -m com.example.app/com.example.app.Main
~~~

In a normal modular application, if the app module has requires com.example.library, this dependency is already part of resolution via the requires directive.

--add-modules should be used as needed, such as for plugins/service providers or dynamically selected dependencies. It does not replace requires in all situations and does not automatically export packages.

If the root error is java.lang.module.FindException, prioritize fixing the module path or module name before checking IllegalAccessError.

## 21. --add-exports for ALL-UNNAMED

When an application runs on the classpath, code belongs to the unnamed module. If it needs to access a package from a named module that is not normally exported, a special target can be used:

~~~bash
java --add-exports \
    com.example.library/com.example.library.internal=ALL-UNNAMED \
    -cp app.jar \
    com.example.Main
~~~

This example assumes the library module is resolved into the runtime configuration and app.jar holds the main class on the classpath. When necessary, add --module-path and --add-modules to ensure library is present in the graph.

ALL-UNNAMED means exporting the package to eligible unnamed modules, a broader scope than a specific named module.

If the consumer has a stable module name, prefer:

~~~text
--add-exports com.example.library/com.example.library.internal=com.example.app
~~~

so as not to open access to unrelated unnamed modules.

## 22. Maven and Gradle: separating compiler arguments and JVM arguments

An easy mistake is adding --add-exports to compiler arguments and assuming the JVM runtime inherits it automatically.

In reality:

- javac receives options during compilation.
- the java launcher receives options at runtime.
- the test runner may launch a different JVM from the application JVM.
- the IDE may add its own module flags that the CLI does not have.

With Gradle Groovy DSL, an illustrative configuration:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += [
        '--add-exports',
        'com.example.library/com.example.library.internal=com.example.app'
    ]
}

tasks.withType(Test).configureEach {
    jvmArgs(
        '--add-exports',
        'com.example.library/com.example.library.internal=com.example.app'
    )
}
~~~

This only illustrates where arguments go. If the test runner runs in the unnamed module, the actual flag target may differ; identify the caller module of the test process before applying.

With Maven, the compiler plugin and Surefire/Failsafe/runtime launcher use separate configurations. Avoid placing test-only flags into production if production does not need them.

If source and descriptors can be edited, prefer clean requires/exports over temporary flags.

## 23. How to read an IllegalAccessError stack trace

Example:

~~~text
Exception in thread "main" java.lang.IllegalAccessError:
class com.example.app.Main (in module com.example.app)
cannot access class com.example.library.internal.InternalFormatter
(in module com.example.library)
because module com.example.library does not export
com.example.library.internal to module com.example.app
    at com.example.app/com.example.app.Main.main(Main.java:8)
~~~

Extract the parts:

| Data | Meaning |
| --- | --- |
| com.example.app.Main | Class in bytecode attempting the access. |
| com.example.app | Caller module. |
| InternalFormatter | Target class. |
| com.example.library | Owner module. |
| com.example.library.internal | Package needing export but currently closed. |
| Main.java:8 | Call site in source code to investigate. |

When the message contains the phrase does not export, check exports instead of trying opens.

If the message contains the phrase does not read, check readability and the module graph. If it mentions a private member or protected member, check Java visibility rather than automatically assuming a module error.

## 24. Short, ordered diagnostic workflow

When the application reports IllegalAccessError:

1. **Preserve the original message.** Capture the full stack trace, especially the caller and owner class/module lines.
2. **Classify.** Is the error due to does not export, does not read, or unrelated to modules?
3. **Verify module names.** Use jar --describe-module or java --describe-module.
4. **Verify the runtime graph.** Check the java command, --module-path, -m, --add-modules, and --show-module-resolution.
5. **Inspect descriptors.** Check the caller's requires, owner's exports, qualified exports, and artifact versions.
6. **Check effective permissions.** When a valid Class<?> is available, call caller.canRead(owner) and owner.isExported(packageName, caller).
7. **Compare compile and runtime.** Compare --add-reads, --add-exports flags, and artifact paths between both stages.
8. **Fix at the right layer.** Use requires, exports, or supplementary flags matching the cause.
9. **Limit scope.** Do not open an internal package to all modules just because one consumer needs it.
10. **Re-run in the real deployment environment.** Confirm the linkage error disappears without introducing a new dependency mismatch.

Do not change a bunch of flags and retry at random. Targeted changes with clear readback/logging reveal the true cause.

## 25. Design solutions instead of relying on flags

If a consumer has to use an internal class of a library, ask yourself:

- Is that class meant to be an official API for consumers?
- Can a public interface/factory be exposed in an api package instead?
- Can a public DTO or record be returned instead of an internal type?
- Can requires transitive be added when a public API needs types from another dependency module?
- Can an integration API be separated into its own package with qualified exports?

Example of a stable architecture:

~~~text
com.example.library.api
    Formatter interface
    Formatters factory
    FormatResult DTO

com.example.library.internal
    DefaultFormatter
    Cache
    ParserHelper
~~~

Descriptor:

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

The consumer uses the API package instead of importing DefaultFormatter in internal. This reduces coupling to the implementation and avoids having to keep --add-exports across multiple releases.

If you encounter a missing reads error because a module descriptor lacks requires, add an explicit requires rather than using --add-reads as a permanent mandatory setting, unless the architecture has a specific reason.

## 26. Common mistakes

**Adding only requires when the error is missing exports:** readability does not turn an internal package into public API.

**Adding only exports when the caller module does not read the owner:** an export does not substitute for a read relationship.

**Using --add-opens to fix a public class linking error:** opens serves deep reflection, not normal import/bytecode access.

**Assuming a public class in an internal package is always accessible:** the public modifier does not bypass JPMS exports.

**Swapping classpath/module path without checking module names:** the same artifact can switch between unnamed, automatic, and explicit module depending on placement and descriptor.

**Adding flags at compile time and forgetting runtime:** this is a very common source of runtime-only errors.

**Ignoring binary incompatibility:** IllegalAccessError can stem from class/member visibility changes, not only the module graph.

**Putting every dependency in --add-modules:** it only addresses part of resolution and does not automatically grant all reads and exports relationships.

## 27. Principles for maintaining clear configurations

- Keep module-info.java as the place expressing real dependencies and APIs.
- Only export packages containing public types intended for long-term use.
- Use qualified exports when permission is meant only for specific modules.
- Only use --add-reads or --add-exports when needed for compatibility, migration, or controlled test configurations.
- Document the purpose, caller, owner, package, and JDK version for every flag.
- Ensure compile, test, IDE, and runtime commands use the same appropriate set of dependencies.
- Do not confuse exports with opens.
- Use the Module API and JDK tools to observe rather than guessing from JAR names.
- Always consider the possibility of binary incompatibility when swapping dependencies.
- Test on the exact module path/runtime that will be deployed.

IllegalAccessError due to missing exports or reads signals that **bytecode is requesting an access relationship that the runtime module graph does not allow**. Clearly distinguishing module readability from package export permissions helps fix the true cause, preserve strong encapsulation, and avoid creating hard-to-maintain dependency paths.

## 28. Self-check

**Scenario 1:** App declares requires library yet calls a public class in an unexported internal package. Does it have sufficient access?

No. requires only grants readability; library must also export the package to app if this is normal access.

**Scenario 2:** Javac was passed --add-exports, but the runtime JVM was not passed the flag. What can happen?

The application can compile successfully, yet the JVM throws IllegalAccessError when linking the class reference in the unexported package at runtime.

**Scenario 3:** The JVM reports module app does not read module library. Will using --add-exports automatically fix it?

No. Readability is needed via requires, requires transitive, or an appropriate --add-reads. If the package is also unexported, that condition must be addressed separately.

**Scenario 4:** Qualified exports declare exports p to app, yet another module tool needs to use p. Will tool automatically gain access?

No. A targeted export grants access only to the named modules; tool needs its own export contract or an appropriate public API.

**Scenario 5:** When reflection on a private field hits InaccessibleObjectException, should --add-reads be added instead of --add-opens?

No. This is typically a deep reflection error; inspect opens for the right package/caller if the functional need is legitimate.

**Scenario 6:** If running the application with a library JAR of a different version than compile time, what should be checked before adding flags?

Compare the module descriptors, exports, visibility, API versions, and the artifact actually sitting on the module path. The issue may be binary incompatibility.

**Scenario 7:** A class belongs to the classpath's unnamed module; a named module needs to read it. Which target form of --add-reads can help in some migration setups?

You can use --add-reads named.module=ALL-UNNAMED, while ensuring the classpath contains the library and the class loader can find the class.

**Scenario 8:** Does a class being successfully loaded by a class loader guarantee that every module can use it?

No. The ability to load bytecode and JPMS permission to link/access a class are two different things. The JVM still checks readability, exports, and Java visibility.