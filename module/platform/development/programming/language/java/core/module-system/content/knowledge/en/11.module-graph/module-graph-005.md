# The module path finds modules by name

In the Java Platform Module System (JPMS), the **module path** is where Java searches for modules usable at compile time and launch time. The core principle is that JPMS identifies a module by its **module name** in the module descriptor, rather than looking up dependencies by class name or JAR filename like the traditional classpath.

When a module declares requires, Java searches for a module with the corresponding name on the module path or among the platform modules provided by the runtime. The resolver then builds the module graph from the root modules and the dependencies they require.

## 1. What is the module path?

The module path is a list of locations containing modules. A location can be:

- A modular JAR containing module-info.class.
- A compiled module directory in exploded module form containing module-info.class.
- A legacy JAR without a descriptor that is recognized as an automatic module when placed on the module path.
- A directory containing multiple modular JARs or exploded modules.

Example directory:

~~~text
project/
├── mods/
│   ├── com.example.customer.jar
│   ├── com.example.orders.jar
│   └── com.example.reporting/
│       ├── module-info.class
│       └── com/example/reporting/Main.class
└── libs/
    └── commons-text-1.11.0.jar
~~~

In this example, mods contains two modular JARs and one exploded module. The JAR in libs can become an automatic module if placed on the module path without a module descriptor.

When running the application, these locations can be specified:

~~~bash
java --module-path mods:libs -m com.example.orders/com.example.orders.Main
~~~

Colons separate path entries on Unix-like systems. On Windows, use semicolons:

~~~powershell
java --module-path "mods;libs" -m com.example.orders/com.example.orders.Main
~~~

The short option **-p** can be used instead of **--module-path**.

## 2. Java locates modules by module name

Suppose the orders module has the descriptor:

~~~java
module com.example.orders {
    requires com.example.customer;
}
~~~

The customer module has the descriptor:

~~~java
module com.example.customer {
    exports com.example.customer.api;
}
~~~

When compiling or running orders, JPMS needs to find a module named exactly **com.example.customer**. This name is taken from the module-info.class of the modular JAR or exploded module.

For example, a file named:

~~~text
customer-library-2.0.jar
~~~

whose internal descriptor declares:

~~~java
module com.example.customer {
    exports com.example.customer.api;
}
~~~

still has the module name **com.example.customer**. The JAR filename can change without changing the module name, as long as the descriptor remains the same.

This differs from an automatic module: when a JAR lacks module-info.class and does not declare Automatic-Module-Name, the module name is derived from the JAR filename. Therefore, it is necessary to distinguish explicit module names from derived names.

The module name is the identifier used in requires, exports to, opens to, uses, provides directives, and in launch commands using -m.

## 3. requires connects modules in the module graph

The module path tells Java which modules can be found. Module descriptors tell which module needs to read which module.

Example of three modules:

~~~text
com.example.app
    └── requires com.example.orders

com.example.orders
    └── requires com.example.customer

com.example.customer
    └── requires java.sql
~~~

When the application launches from com.example.app, the resolver starts from the root module and follows requires directives to build the module graph.

This can be expressed as:

~~~java
module com.example.app {
    requires com.example.orders;
}
~~~

~~~java
module com.example.orders {
    requires com.example.customer;
}
~~~

~~~java
module com.example.customer {
    requires java.sql;
}
~~~

If a dependency is not found by module name, compilation or startup can fail with an error such as:

~~~text
error: module not found: com.example.customer
~~~

or:

~~~text
java.lang.module.FindException:
Module com.example.customer not found
~~~

The fix is to check the actual module name and ensure the corresponding module resides on the module path or an appropriate module source.

## 4. Observable modules and resolved modules

These two concepts explain why a JAR present on the module path is not necessarily loaded into the module graph.

An **observable module** is a module that the resolver can locate through module finders, such as the module path and JDK system modules.

A **resolved module** is a module that has been placed into the module graph after resolution from the root modules and their dependencies.

For example, the module path contains:

~~~text
mods/
├── com.example.app.jar
├── com.example.customer.jar
├── com.example.reporting.jar
└── com.example.unused.jar
~~~

If the root application is com.example.app and it only requires com.example.customer, the reporting or unused modules may still be observable on the module path yet not belong to the resolved module graph of that run.

This means placing a JAR on the module path only makes the module findable. It does not mean every module in the directory automatically becomes a dependency of the application.

To add a module as a root module at launch time, use **--add-modules**:

~~~bash
java --module-path mods --add-modules com.example.reporting \
    -m com.example.app/com.example.app.Main
~~~

This option instructs the reporting module to be included in the root module set for resolution. Its requires dependencies are also considered when building the module graph.

## 5. How are root modules selected?

When launching a modular application, the **-m** or **--module** option specifies the root module and the main class:

~~~bash
java --module-path mods \
    -m com.example.app/com.example.app.Main
~~~

General syntax:

~~~text
module.name/main.class
~~~

Where:

- module.name is the module name of the application module.
- main.class is the fully qualified name of the class with the main method.
- --module-path specifies where to find modules.

One or more root modules can be added with --add-modules:

~~~bash
java --module-path mods \
    --add-modules com.example.reporting,com.example.metrics \
    -m com.example.app/com.example.app.Main
~~~

Each root module will be resolved along with the dependencies it requires. If a root module name does not exist on the module path or in the corresponding module sources, the JVM will report module not found.

For a traditional command running a class by class name after -cp, the main class belongs to the unnamed module. That is a classpath launch, not launching a named module with -m.

## 6. How does the module path differ from the classpath?

Both the classpath and the module path help the JVM locate compiled code, but they use different identity and access models.

| Characteristic | Classpath | Module path |
| --- | --- | --- |
| Lookup unit | Classes and resources in directories/JARs | Modules by module name |
| Descriptor | Does not use module descriptors to form named modules | Uses module-info.class or automatic module rules |
| Dependencies | Typically managed by build tools and class loaders | Declared with requires in the module descriptor |
| Package encapsulation | No JPMS boundaries between JARs on the classpath | Packages are controlled by exports and opens |
| Identity | Classes belong to the corresponding unnamed module | Named module or automatic module |
| Access | Follows class loader and Java language rules | Follows both Java rules and module readability/access |

A named module cannot write requires on the unnamed module because the unnamed module has no module name. If a library is only on the classpath, a named module cannot reference it with a standard requires directive.

If a legacy library needs to be used from a named module, the JAR can be placed on the module path so Java recognizes it as an automatic module, or a version of the library that already has a module descriptor can be used.

## 7. The JAR filename is not always the module name

For a modular JAR, the module name is declared in module-info.class.

Example:

~~~text
customer-client-2.1.jar
~~~

may contain:

~~~java
module org.example.customer {
    exports org.example.customer.api;
}
~~~

In that case, the module name is **org.example.customer**.

For a JAR without a descriptor:

- If the manifest has Automatic-Module-Name, Java uses that value.
- If that attribute is absent, Java derives the name from the JAR filename.

Check with:

~~~bash
jar --describe-module --file libs/customer-client-2.1.jar
~~~

The output shows the module name recognized by the JDK, the module type, and related packages or directives.

Do not guess requires from an artifactId or filename. Verify the module name on the exact artifact being built or deployed.

## 8. Multiple module path locations and name collision issues

Multiple module path locations can be supplied:

~~~bash
java --module-path mods:libs:plugins \
    -m com.example.app/com.example.app.Main
~~~

Java can search for modules across the configured locations. However, the module graph requires module names to be unambiguously identified. If multiple artifacts provide the same module name in the same module finder or configuration, discovery/resolution can report duplicate modules.

Example:

~~~text
libs/
├── customer-1.0.jar
└── customer-2.0.jar
~~~

If both declare the module name com.example.customer or derive the same automatic module name, both should not be placed into the same module configuration.

Select the appropriate version via Gradle or Maven dependency management, then verify the final module path contains only one module for the needed name.

Different filenames do not turn two modules with the same name into two independent dependencies.

## 9. javac and java module paths must be consistent

When compiling modular source code, provide dependencies on the module path:

~~~bash
javac --module-path libs \
    --module-source-path src \
    -d out \
    -m com.example.app
~~~

The command tells javac:

- libs contains compiled dependencies.
- src contains module sources following the module source path structure.
- out is the output directory.
- com.example.app is the module to compile.

When running, provide the compiled modules and dependencies:

~~~bash
java --module-path out:libs \
    -m com.example.app/com.example.app.Main
~~~

If compilation uses a module path yet runtime is missing a dependency, the application can compile successfully and then fail at launch.

Conversely, adding a JAR to the classpath when launching the application with -m does not turn that JAR into a named module that requires can reference.

## 10. Options related to the module graph

Several JVM options are useful when working with the module path:

| Option | Purpose |
| --- | --- |
| --module-path or -p | Specifies where to locate modules. |
| --module or -m | Specifies the root module and main class. |
| --add-modules | Adds root modules to resolve. |
| --show-module-resolution | Displays module resolution during startup. |
| --list-modules | Lists modules observable by the runtime in the configuration. |
| --limit-modules | Restricts the set of observable system modules. |
| --upgrade-module-path | Provides replacement modules for system modules under the upgrade mechanism. |
| --patch-module | Adds classes/resources to an existing module. |

Do not confuse --upgrade-module-path with the regular module path. It serves the mechanism for replacing certain system modules according to specific JPMS rules.

Similarly, --patch-module is not the normal way to add a new dependency. It supplements the contents of an already identified module.

## 11. Checking which modules are found and resolved

When encountering a module not found error or wanting to see the actual module graph, check in sequence:

### Step 1: Identify the artifact's module name

~~~bash
jar --describe-module --file libs/customer.jar
~~~

Confirm the module name inside the JAR. If it is an automatic module, check the name obtained from the manifest or filename.

### Step 2: Check which modules the runtime sees

~~~bash
java --module-path mods:libs --list-modules
~~~

This command checks the system modules and module path modules observable by the runtime.

### Step 3: Observe the resolution process

~~~bash
java --show-module-resolution \
    --module-path mods:libs \
    -m com.example.app/com.example.app.Main
~~~

The output shows resolved modules and related dependency relationships. This is useful evidence when a module is on the module path yet does not appear in the graph as expected.

### Step 4: Inspect the module's dependencies

~~~bash
jdeps --module-path mods:libs --check com.example.app
~~~

jdeps helps analyze dependencies and check module descriptors. When analyzing a specific JAR, options such as --print-module-deps or --list-deps can also be used.

### Step 5: Compare the build command and deployment command

Compare the compile-time module path with the runtime module path. Check the JDK version, artifact locations, and module name of each dependency. IDEs may automatically add module paths, so running directly in the terminal is an important verification step.

## 12. Common errors

| Message or Symptom | Common Cause | How to Check |
| --- | --- | --- |
| module not found | Missing JAR, wrong module name, or wrong module path | Use jar --describe-module and check --module-path. |
| FindException: Module ... not found | Root module or requires dependency is not observable | Check names after -m/--add-modules and requires directives. |
| Duplicate module | Multiple artifacts provide the same module name | Remove duplicate version or artifact. |
| Source code cannot import package | Missing requires or package is not exported | Check descriptors of the calling module and API-owning module. |
| Runs in IDE but fails in terminal | IDE and terminal use different module paths | Compare the run command and actual dependencies. |
| JAR is in directory but missing from graph | Module is only observable, not resolved from roots | Check requires, root modules, and --add-modules. |
| JAR on classpath yet requires cannot find it | JAR belongs to the unnamed module | Move JAR to the module path or change integration design. |

## 13. Principles for using the module path

- Use verified module names in module-info.java and the -m command.
- Keep compile-time and runtime module paths consistent with the deployment configuration.
- Clearly separate libraries on the module path from libraries on the classpath.
- Only add root modules with --add-modules when there is a specific resolution need.
- Avoid placing multiple versions with the same module name into one module configuration.
- Use jar --describe-module to identify a JAR's module name.
- Use --show-module-resolution to understand the actual module graph.
- Do not treat the presence of a JAR on the module path as proof that it has been resolved.

The module path finds modules by name and module descriptor. The module graph is then formed from the root modules along with their requires relationships. Clearly distinguishing lookup locations, module names, and resolution status makes diagnosing modular application dependencies more accurate.

## 14. Self-check

**Scenario 1:** A JAR named customer-client.jar contains a module-info.class declaring module org.example.customer. Which name should the application module write in requires?

Answer: requires org.example.customer. For a modular JAR, the module name comes from the module descriptor, not directly from the filename.

**Scenario 2:** A JAR is already in the mods directory yet does not appear in the application's module graph. Why might that happen?

Answer: The JAR may be observable on the module path yet not resolved from the root modules. Check requires, root modules, and the --add-modules option.

**Scenario 3:** Module app declares requires orders; orders declares requires customer. Does app need to declare requires customer?

Answer: If app's code directly uses types belonging to customer, app needs an appropriate readability relationship. If only orders uses customer and the dependency is not propagated via requires transitive, app does not automatically read customer.

**Scenario 4:** Can two versions of the same named module be placed in two different directories on the module path?

Answer: No. If both provide the same module name in the same module configuration, lookup and resolution can report duplicate modules. Choose one version.

**Scenario 5:** A library is on the classpath, yet a named module declares requires on that library. Why doesn't it work?

Answer: On the classpath, the library belongs to the unnamed module and has no module name for requires to reference. Move the library to the module path so it is recognized as an automatic module, or use a modularized version of the library.