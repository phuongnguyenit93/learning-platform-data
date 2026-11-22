# Listing Observable Modules with `java --list-modules`

## 1. Objectives

The Java Platform Module System (JPMS) divides the runtime and application into modules with explicit names, descriptors, and dependency relationships. When working with a modular application, you sometimes need to know which modules the current JDK provides or which modules a module path directory contains.

The launcher command:

~~~bash
java --list-modules
~~~

prints the list of modules observable by the runtime under the current search configuration, and then exits. This is a module environment inspection command; it does not launch the application's main class.

This lesson explains how to read the output, add a module path, filter the list, and distinguish observable modules from the actual graph resolved for an application.

After this lesson, you can:

- List the modules available in the runtime currently in use.
- Additionally list modular JARs or exploded modules on the module path.
- Understand the meaning of module names and displayed versions.
- Distinguish observable modules, resolved modules, and instantiated service providers.
- Use related diagnostic options when investigating a modular application.

## 2. Listing Modules of the Current JDK

Open a terminal and run:

~~~bash
java --list-modules
~~~

Output on a JDK may look like:

~~~text
java.base@21
java.compiler@21
java.datatransfer@21
java.desktop@21
java.instrument@21
java.logging@21
java.management@21
java.naming@21
java.net.http@21
java.prefs@21
java.rmi@21
java.scripting@21
java.security.jgss@21
java.sql@21
java.transaction.xa@21
java.xml@21
jdk.compiler@21
jdk.javadoc@21
jdk.jlink@21
jdk.unsupported@21
~~~

The actual list depends on the JDK build, JDK vendor, how the runtime was packaged, and launcher options. The example above illustrates the format; it is not a fixed list for every machine.

Each line typically has the format:

~~~text
module.name@version
~~~

Where:

- The part before `@` is the module name.
- The part after `@` is the version provided by the module, if present.
- Modules that do not declare a version may be displayed without a version part.

A few familiar modules:

| Module | General Role |
| --- | --- |
| java.base | Foundational module containing core APIs such as java.lang and java.util. |
| java.logging | Java logging API and infrastructure. |
| java.sql | JDBC API and SQL data types. |
| java.xml | XML processing APIs. |
| java.desktop | AWT, Swing, and related desktop APIs. |
| jdk.compiler | Compiler tools, including javac. |
| jdk.jlink | Tool for creating custom runtime images. |

The `java.base` module is the foundational module that other named modules read by default; other modules can be requested directly or indirectly by the application.

## 3. Listing Modules on the Module Path

Without additional arguments, the launcher lists observable modules from the current runtime. To inspect custom-packaged application modules, pass the module path:

~~~bash
java --module-path mods --list-modules
~~~

Suppose the `mods` directory contains:

~~~text
project/
├── mods/
│   ├── com.example.greeting.api.jar
│   ├── com.example.greeting.provider.jar
│   └── com.example.tools/
│       ├── module-info.class
│       └── com/example/tools/Main.class
└── src/
~~~

Here, the two JAR files are modular JARs with module descriptors, and the `com.example.tools` directory is an exploded module. When artifacts have a valid structure and reside in the proper location pointed to by the module path, they can appear in the observable module list.

Sample output:

~~~text
java.base@21
java.compiler@21
java.logging@21
...
com.example.greeting.api
com.example.greeting.provider
com.example.tools
~~~

Notes:

- The `mods` directory in the example is a module path entry containing modules.
- A modular JAR has the `module-info.class` module descriptor.
- An exploded module is a module directory containing `module-info.class` and compiled classes arranged by package.
- The module name is determined by the module descriptor, and is not necessarily the same as the JAR filename.
- A JAR without a module descriptor can be treated as an automatic module when placed on the module path; the automatic module name is derived according to naming rules or the manifest. A JAR on the classpath does not become an observable named module in this way.

If using multiple module path entries, pass the list using the operating system's separator. On Windows, a path-list typically uses a semicolon; on Linux and macOS, a path-list typically uses a colon.

Windows example:

~~~powershell
java --module-path "mods;plugins" --list-modules
~~~

Linux/macOS example:

~~~bash
java --module-path "mods:plugins" --list-modules
~~~

## 4. Limiting the List with `--limit-modules`

A runtime may observe more modules than an application actually needs. The `--limit-modules` option restricts the set of observable modules to the specified modules and their required dependency closure.

Example:

~~~bash
java --limit-modules java.base,java.logging --list-modules
~~~

This command instructs the launcher to limit the module set to `java.base` and `java.logging` along with the dependencies required by module resolution rules. The output helps inspect a smaller runtime/module universe.

It can be combined with a module path:

~~~bash
java --module-path mods --limit-modules java.base,com.example.greeting.app --list-modules
~~~

Limiting modules may make certain modules unobservable or prevent the application from resolving if they lie outside the allowed set. Only use this option when you want to actively control the set of usable modules.

## 5. Filtering Output to Find Needed Modules

The output can be long, especially on a full JDK. You can pipe the output through an operating system filtering tool.

On Linux/macOS:

~~~bash
java --list-modules | grep java.sql
~~~

On Windows PowerShell:

~~~powershell
java --list-modules | Select-String "java.sql"
~~~

Or use `findstr` in Command Prompt:

~~~cmd
java --list-modules | findstr java.sql
~~~

For example, finding the HTTP client module:

~~~bash
java --list-modules | grep java.net.http
~~~

Filtering tools only process the printed text. They do not alter the module graph or runtime configuration.

## 6. Distinguishing Observable Modules and Resolved Modules

This is a very easy point to confuse when reading output.

**Observable modules** are the modules that the module system can find within the current search configuration, such as the runtime image and module path. The `--list-modules` command serves to list this set.

**Resolved modules** are the modules actually placed into a `Configuration` when the resolver resolves a set of root modules and their dependencies. A module can be observable without being resolved for the running application.

For example, the module path might contain all three modules:

~~~text
com.example.app
com.example.api
com.example.optional-plugin
~~~

If the app only requires `com.example.api` and neither uses nor requires the optional plugin, the plugin may still appear in the observable list while not being part of the resolved configuration for the app.

Therefore, you cannot conclude that a module has been loaded into the application's graph just because its name appears in `--list-modules` output.

## 7. Related Diagnostic Commands

### Viewing a Module's Descriptor

Use `--describe-module` to view descriptor details for a specific module:

~~~bash
java --describe-module java.sql
~~~

You can describe an application module on the module path:

~~~bash
java --module-path mods --describe-module com.example.greeting.app
~~~

Information can include the module name, version, exported packages, required modules, `uses` services, and `provides` services. This is a way to inspect a module's metadata without running the main class.

### Viewing Resolution When Launching the Application

Use `--show-module-resolution` alongside the module run command:

~~~bash
java --show-module-resolution --module-path mods --module com.example.greeting.app/com.example.greeting.app.Main
~~~

This option prints information about the module resolution process when the launcher starts the application. It is useful when you need to know which modules are resolved and which dependencies led to them.

If you need to observe service providers added through service binding, ensure the launch method performs appropriate service binding. Looking at the `--list-modules` list alone cannot substitute for inspecting the resolution of a specific application.

### Comparing the Three Commands

| Command | Question Answered |
| --- | --- |
| java --list-modules | Which modules can the runtime observe? |
| java --describe-module module.name | What does this module's descriptor declare? |
| java --show-module-resolution ... | Which modules does the launcher resolve when starting the application? |

## 8. Relationship with ServiceLoader

A provider module may appear in `--list-modules` output if that module is observable on the module path or in the runtime image. However, that does not mean the provider was selected or a service instance was created.

Separate the steps:

1. The provider module is placed within the scope of an observable module finder.
2. The module resolver includes the provider in the configuration if service binding or dependency resolution requires it.
3. The application calls `ServiceLoader` to discover providers.
4. The application requests an instance via `Provider.get()` or iterates through instances via an iterator.

For example, the provider's module descriptor might declare:

~~~java
module com.example.greeting.provider {
    requires com.example.greeting.api;

    provides com.example.greeting.api.GreetingService
        with com.example.greeting.provider.FormalGreetingService;
}
~~~

The consumer module declares:

~~~java
module com.example.greeting.app {
    requires com.example.greeting.api;

    uses com.example.greeting.api.GreetingService;
}
~~~

The `--list-modules` command can help confirm that the provider module can be found via the module path. When you need to confirm the provider is brought into the graph for the application, check resolution by launching with `--show-module-resolution` or inspecting `Configuration` in code. When you need to confirm an implementation is instantiated, observe where the application calls `ServiceLoader` and `Provider.get()`.

## 9. Some Practical Scenarios

**Checking whether the machine has the `java.sql` module**

~~~bash
java --list-modules
~~~

Find the `java.sql` line in the output. If you need quick filtering, use `grep` or `Select-String` depending on your operating system.

**Checking whether a modular JAR is found**

~~~bash
java --module-path mods --list-modules
~~~

Compare the displayed module name with the module name in `module-info.java`. If it does not appear, check whether the JAR file has a module descriptor, whether the file sits directly in an appropriate module path entry, and whether the module name is correct.

**Inspecting a provider module's descriptor**

~~~bash
java --module-path mods --describe-module com.example.greeting.provider
~~~

Look for the `provides` directive and the corresponding service type.

**Investigating why an application cannot find a dependency**

~~~bash
java --show-module-resolution --module-path mods --module com.example.greeting.app/com.example.greeting.app.Main
~~~

Check the root module, resolved dependencies, and actual module path. Also check whether the consumer's module descriptor has the appropriate `requires` or `uses`.

## 10. Takeaways

- `java --list-modules` lists observable modules in the current search configuration and then exits.
- Use `--module-path` to add modular JARs or exploded modules to inspect.
- Output lines typically have the form `module.name@version`; the version may not appear if the module does not declare one.
- Observable does not mean resolved; resolved also does not mean a service instance has been instantiated.
- Use `--describe-module` to view a module's descriptor.
- Use `--show-module-resolution` when you need to diagnose the graph resolved for a specific run.
- With `ServiceLoader`, distinguish between a provider present on the module path, a provider bound into the graph, and an implementation instantiated.

When starting to investigate a modular application, use `--list-modules` to verify observable module sources, `--describe-module` to read module contracts, and `--show-module-resolution` to understand the graph the launcher actually builds.
