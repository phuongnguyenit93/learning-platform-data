# --upgrade-module-path: Replacing System Modules

## Objectives

After this lesson, you will be able to explain why Java has the --upgrade-module-path option, distinguish the upgrade module path from the application module path, replace an upgradeable system module with a custom modular JAR, and recognize the limitations of this mechanism compared to --patch-module.

## 1. Context: System Modules in the Runtime Image

Since Java 9, the JDK has been organized into modules. Platform modules such as java.base, java.logging, java.sql, java.xml, and many jdk.* modules are packaged inside the JDK's runtime image.

When starting the JVM, Java uses the system modules available in the runtime image to resolve platform dependencies. An application can supply its own modules via --module-path, yet sometimes needs to replace the implementation of a system module with a different version.

For example, a deployment environment might need to use an updated version of a library module in the JDK before migrating the entire application to a newer JDK. When that module is allowed to be upgraded, Java provides the option:

~~~bash
--upgrade-module-path <module-path>
~~~

This option specifies where Java searches for replacement versions of upgradeable system modules. A module found on the upgrade module path takes precedence over the module of the same name in the runtime image.

This is a module-replacement mechanism at the JPMS level. It does not replace the entire JDK, does not modify the runtime image on disk, and does not automatically replace every module in the system.

## 2. How Does the Upgrade Module Path Work?

You can visualize the resolution process as follows:

1. The runtime image provides the JDK's system modules.
2. The upgrade module path is checked to find upgradeable system modules.
3. If the upgrade path contains a module with the same name as an upgradeable system module, the version on the upgrade module path is used instead.
4. Application modules are still located from the application module path specified via --module-path.
5. The module graph is resolved based on the selected modules and their requires relationships.

For example, the current JDK provides module java.xml. If the upgrade module path contains an explicit module named java.xml, the runtime can use that module instead of the java.xml module built into the runtime image.

The module name is the deciding factor for replacement. A JAR named custom-xml.jar whose descriptor declares module com.acme.xml does not replace java.xml. Conversely, a JAR file with an arbitrary filename whose descriptor declares the exact name of an upgradeable system module is recognized by the module name in its descriptor.

## 3. Distinguishing Three Common Module Paths

| Option | Role |
|---|---|
| --module-path | Locates application or library modules that the application needs to use |
| --upgrade-module-path | Provides replacement versions for upgradeable system modules in the runtime image |
| --system | Specifies the runtime image/JDK used as the source of system modules when compiling with javac |

These three options are not interchangeable.

Example:

- com.acme.app sits on --module-path because it is an application module.
- The replacement for java.xml sits on --upgrade-module-path because it replaces a built-in system module.
- The remaining platform modules continue to come from the runtime image of the running JDK.

If you only place a replacement JAR on --module-path, Java treats it as a regular application or library module. Placing the JAR on --upgrade-module-path expresses the intent to replace the system module of the same name.

## 4. Example Directory Structure

Suppose we have a modular application and a replacement for a system module:

~~~text
deployment/
  app-modules/
    com.acme.report.jar

  upgrade-modules/
    java.xml.jar
~~~

In this example:

- com.acme.report.jar is the application module.
- java.xml.jar is an explicit modular JAR containing a module descriptor declaring the module name java.xml.
- Other system modules are still supplied by the JDK in use.

The filename java.xml.jar merely helps operators identify it easily. What matters is that module-info.class inside the JAR declares the exact name java.xml and the module structure is valid.

You can inspect the replacement's descriptor with:

~~~bash
jar --describe-module --file deployment/upgrade-modules/java.xml.jar
~~~

The output should confirm the module name is java.xml, while also showing the requires, exports, and other module directives declared by the replacement.

Do not package a regular library JAR and merely rename the file to java.xml.jar. A module on the upgrade module path needs an appropriate module descriptor so Java recognizes the exact module to upgrade.

## 5. Running the Application with a Replacement Module

Use the java launcher:

~~~bash
java \
    --upgrade-module-path deployment/upgrade-modules \
    --module-path deployment/app-modules \
    --module com.acme.report/com.acme.report.Main
~~~

Meaning:

- --upgrade-module-path specifies the directory containing the replacement module.
- --module-path specifies the directory containing the application modules.
- --module selects the module and main class to run.

On Windows, the separator for multiple entries in a module path is a semicolon; on Linux and macOS it is a colon. In the example above, each option takes one directory, so joining multiple entries is not needed.

At launch, Java resolves com.acme.report along with its dependencies. If the module graph requires java.xml, the runtime uses the version found on the upgrade module path instead of the java.xml version in the runtime image, provided that module belongs to the upgradeable group and the replacement resolves cleanly.

If the upgrade module path does not contain a corresponding replacement module, Java continues using the module built into the runtime image.

## 6. Which Modules Can Be Upgraded?

Not every part of the runtime can be replaced using this option. Module java.base is a special core module and cannot be upgraded via --upgrade-module-path.

For other system modules, upgradeability depends on the rules of the runtime/JDK in use. Check the documentation for the exact target JDK version before deploying a replacement module.

The replacement must satisfy basic conditions:

- It is a valid module that Java can locate on the upgrade module path.
- It declares the same module name as the system module to replace.
- It has dependencies that can be resolved within the module graph.
- It provides the packages and types expected by dependent modules.
- It is compatible with the runtime and the remaining modules in the running JDK.

JPMS governs module names, module readability, and package access. It does not guarantee that the replacement's binary API is compatible with every application. If the new version removes a class or method that the application uses, the application can still fail during linking or execution.

Do not assume a replacement module compiled on a newer JDK will always run on every older JDK. Build and test the artifact on the supported platform version.

## 7. Inspecting Resolved Modules

You can use JDK commands to inspect system modules and descriptors:

~~~bash
java --list-modules
~~~

This command lists the modules present in the runtime being used. It is useful for identifying module names and module versions provided by the JDK.

View the descriptor of a module in the JDK:

~~~bash
java --describe-module java.xml
~~~

To inspect a replacement JAR file before running, use:

~~~bash
jar --describe-module --file deployment/upgrade-modules/java.xml.jar
~~~

When you need to observe the module graph or diagnose why a module is not resolved, you can enable module logging:

~~~bash
java -Xlog:module+load=info \
     --upgrade-module-path deployment/upgrade-modules \
     --module-path deployment/app-modules \
     --module com.acme.report/com.acme.report.Main
~~~

Log tags can vary across JDK versions. If a tag is not supported by the runtime, view the tag list with -Xlog:help and choose the appropriate tag.

## 8. Distinguishing --upgrade-module-path from --patch-module

Both options affect module contents, but they work differently:

| Criterion | --upgrade-module-path | --patch-module |
|---|---|---|
| Purpose | Replaces an upgradeable system module with a module of the same name | Adds or replaces classes/resources inside an existing module |
| Artifact | Replacement module with its own descriptor | Classes/resources injected into the target module |
| Module descriptor | Uses the descriptor of the replacement module | Does not change the existing module descriptor |
| Scope | Upgradeable system modules | Specified module to patch |
| Common use cases | Testing or deploying a new version of a system module | Testing, instrumentation, or adding classes to an existing module |

Example patching module java.base with a compiled class directory:

~~~bash
java \
    --patch-module java.base=build/patches/java.base \
    --module-path app-modules \
    --module com.acme.app/com.acme.app.Main
~~~

The path after the equals sign is additional content for the target module. Patching does not replace the module's descriptor, does not create a new module, and does not automatically alter requires, exports, or opens directives.

Conversely, --upgrade-module-path provides a complete replacement module with the corresponding name. Choose patching when you need to add or replace a few classes in an existing module; choose the upgrade path when you need to supply a replacement module version via the JPMS mechanism.

## 9. Distinguishing from --add-exports and --add-opens

Some runtime errors related to encapsulated modules cause learners to confuse --upgrade-module-path with access-opening options.

- --add-exports opens a package so the target module can access public types in that package.
- --add-opens opens a package for deep reflective access at runtime.
- --upgrade-module-path selects a different module implementation for an upgradeable system module.

Example:

~~~bash
java \
    --add-exports java.base/sun.nio.ch=ALL-UNNAMED \
    -jar legacy-app.jar
~~~

This command opens package sun.nio.ch of java.base to unnamed modules. It does not replace module java.base and does not update that module's implementation.

If the application needs access to an internal package, handle access permissions using the appropriate exports/opens option. If you need to replace the implementation of an upgradeable system module, consider the upgrade module path.

## 10. Using --upgrade-module-path at Compile Time

Javac also has the --upgrade-module-path option to specify replacement modules when resolving system modules during compilation.

Example:

~~~bash
javac \
    --upgrade-module-path upgrade-modules \
    --module-path app-dependencies \
    -d build/classes \
    --module-source-path src \
    -m com.acme.report
~~~

Here:

- --upgrade-module-path tells javac where to find replacement versions of upgradeable system modules.
- --module-path provides the application's dependency modules.
- --module-source-path specifies the module-based source layout.
- -m selects the module to compile.

If you compile with a replacement java.xml version but run on a JDK without the same artifact on the upgrade module path, the compile and runtime environments can diverge. Synchronize the configuration across both phases to avoid succeeding at compile time yet failing at runtime due to different APIs/modules being selected.

## 11. Common Errors

| Symptom | Common Cause | Resolution |
|---|---|---|
| Replacement module is not selected | Placed JAR on --module-path instead of --upgrade-module-path | Place the artifact on the proper upgrade module path |
| Module does not replace the system module | Name in module descriptor does not match the name of the module to replace | Use jar --describe-module to check the module name |
| Cannot upgrade java.base | java.base is a non-upgradeable core module | Do not use the upgrade path to replace java.base |
| FindException or ResolutionException | Replacement module or its dependencies cannot be resolved | Check descriptor, requires, and module paths |
| NoSuchMethodError or NoClassDefFoundError | Replacement is incompatible with the module/application in use | Check API and binary compatibility |
| Compile succeeds but runtime fails | Javac and java use different replacement modules or JDK versions | Synchronize upgrade module path at both compile time and runtime |
| Internal package access errors persist | Upgrade path does not automatically open packages or grant reflective access | Consider --add-exports or --add-opens if genuinely needed |

When diagnosing, check in order: the artifact's module name, the paths passed to the launcher/compiler, the upgradeability of the target module, dependencies in the descriptor, and API compatibility. Checking only the JAR filename is not enough.

## 12. When Should This Option Be Used?

--upgrade-module-path is useful when you need to test or deploy a replacement for an upgradeable system module without replacing the entire JDK runtime image.

Before using it in production, verify:

- Does the target module belong to the upgradeable group of the running JDK?
- Does the replacement artifact have the exact module name and a valid descriptor?
- Can the module's dependencies be resolved?
- Is the replacement's API compatible with the application and other modules?
- Are compile-time and runtime configurations consistent?
- Does the deployment environment use the exact JDK and upgrade module path that were tested?

If the goal is only to add a new application module, use --module-path. If the goal is only to add or replace a few classes in an existing module, consider --patch-module. If you need to replace an upgradeable system module with a module of the same name, --upgrade-module-path is the corresponding option.

## Key Takeaways

--upgrade-module-path provides replacement modules for upgradeable system modules in the runtime image. Java uses a module of the same name on this path instead of the corresponding module in the JDK; java.base is the non-upgradeable exception. --module-path is for application modules, while --patch-module adds or replaces classes/resources in an existing module without changing its descriptor. When using the upgrade path, verify the module name, dependencies, compatibility, and ensure compile/runtime configurations match.