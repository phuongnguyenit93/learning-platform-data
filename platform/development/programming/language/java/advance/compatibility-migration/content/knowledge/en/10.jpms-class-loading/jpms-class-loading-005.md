# Split packages, duplicate packages, and module resolution errors

In **Java Advance Compatibility Migration**, moving from the traditional classpath to the **Java Platform Module System (JPMS)** is not simply adding a **module-info.java** file. A dependency structure that once worked on the classpath can become invalid when JARs are placed on the module path. A common cause is a **split package**: the same Java package is distributed across multiple modules instead of belonging to one clear module.

This lesson belongs to the **JPMS and class loading** group, focusing on how to recognize duplicate packages, the conditions that cause errors at compile time or when creating a module layer, the relationship with class loaders, and remediation options so that migration does not break applications or already-released consumers.

Objectives after this lesson:

- Distinguish between **split packages**, **classes with duplicate full names**, duplicate resources, and packages used across different class loaders.
- Understand why the classpath can accept a layout that JPMS cannot resolve safely.
- Read messages such as **reads package ... from both**, **ResolutionException**, **LayerInstantiationException**, along with class-loading errors easily confused with split packages.
- Find the root cause of duplicate packages in JARs, direct dependencies, and transitive dependencies.
- Choose a resolution approach: consolidate the package into one module, rename packages, exclude dependencies, restructure APIs, or use controlled transition mechanisms.
- Build tests for the classpath, module path, automatic modules, and applications with plugins.

## 1. Foundational concepts of packages and modules

### 1.1. A package is a namespace, not an artifact

In Java, the declaration:

~~~java
package com.example.shared;
~~~

defines the package of a type. A package can contain multiple classes and interfaces. On the traditional classpath, classes in the same package are often scattered across multiple directories or JARs.

For example:

~~~text
legacy-a.jar
└── com/example/shared/Alpha.class

legacy-b.jar
└── com/example/shared/Beta.class
~~~

Even though they belong to two JARs, **Alpha** and **Beta** are still in the same package **com.example.shared**.

A JAR is a file packaging unit, not automatically synonymous with a JPMS module. A JAR can be placed on the classpath, become an automatic module when placed on the module path, or contain a descriptor to become an explicit named module.

### 1.2. A JPMS module adds an ownership boundary

JPMS was introduced in Java 9. A **named module** has a name, a set of packages, and relationships such as **requires**, **exports**, **opens**, **uses**, and **provides**.

For example:

~~~java
module com.example.catalog {
    exports com.example.catalog.api;
    requires java.logging;
}
~~~

Here:

- **com.example.catalog** is the module name.
- **com.example.catalog.api** is the exported package.
- **java.logging** is a module that catalog reads through requires.
- Packages that are not exported do not automatically become APIs accessible from other modules.

JPMS uses the module graph to determine **readability** and access permissions to packages. Therefore, having two modules both provide the same package can cause ambiguity: from where will a consuming module obtain that package?

### 1.3. Types of modules to distinguish

| Type | How it appears | Characteristics related to split packages |
|---|---|---|
| **Explicit named module** | Has a module descriptor, typically module-info.class | Package set and module relationships are explicitly described |
| **Automatic module** | JAR without a descriptor, placed on the module path | Assigned a module name automatically; typically exports its packages and has convenient reading mechanisms for migration |
| **Unnamed module** | Classpath, per class loader | Can contain classes from multiple JARs, but is not managed like a regular named module |
| **Patched module** | Named module receiving additional content via --patch-module | Content is added into the patched module; not a way to freely merge conflicting named modules |

A **Gradle module** or **Maven module** is not synonymous with a JPMS module. A Gradle subproject can produce a JAR without module-info, and a Maven project is not a JPMS named module by default either.

## 2. What is a split package?

A **split package** occurs when classes belonging to **the same Java package** are distributed across multiple modules, while the module system needs to treat them as separate package sources.

For example:

~~~text
com.example.alpha (named module)
└── com/example/shared/Alpha.class

com.example.beta (named module)
└── com/example/shared/Beta.class
~~~

Both modules contain **com.example.shared**. If a third module needs to read this package from both modules, the system encounters ambiguity.

Note: a split package does not necessarily require classes with duplicate names. Two classes **Alpha** and **Beta** have different names yet still cause a conflict because the package is the same.

### 2.1. Distinguishing three forms of “duplication”

| Phenomenon | Example | Is it a split package? | Main risk |
|---|---|---|---|
| Same package, different classes | JAR A has **p.A**, JAR B has **p.B** | Can be a split package when in different modules | JPMS cannot determine a single package source |
| Same fully qualified class name | Both A and B have **p.Config** | Also has a duplicate package; additionally a duplicate class | Class is shadowed or loaded with the wrong version |
| Same resource path | Two JARs have **META-INF/config.properties** | Not necessarily | Resource lookup depends on order/loader, merging, or overwriting |
| Same package in two isolated loaders | Two plugin loaders each have **p.Helper** | Not automatically a split package in the same graph | Class identity, casting, service bridges, and cross-loader interaction |

**Duplicate classes** are usually more severe on the application side: the class loader may load an unintended version even if compilation reports no errors. However, two JARs containing different classes in the same package is already enough to cause JPMS risks.

### 2.2. Why does the traditional classpath usually “work”?

On the classpath, multiple JARs can contribute classes to the same namespace of the unnamed module associated with a class loader. The JVM does not enforce full named module boundaries for that layout.

For example:

~~~bash
java -cp "legacy-a.jar:legacy-b.jar:app.jar" com.example.app.Main
~~~

On Windows, the classpath separator character is usually a semicolon (**;**) instead of a colon (**:**).

In this configuration, having **com.example.shared.Alpha** in JAR A and **com.example.shared.Beta** in JAR B can work normally.

That does not prove the two JARs can be moved onto the module path without changes. JPMS adds checks for package ownership, readability, and the module graph.

## 3. Why does JPMS restrict split packages?

The module system aims for clarity: when module **M** reads a specific package, the configuration must identify a valid package source, rather than relying on the accidental order of JARs.

A module also needs to be created in a module layer with an appropriate mapping of packages, class loaders, and modules. If multiple modules defined in the same loader declare the same package, layer creation can fail.

Two common types of conflicts:

1. **Readability/exports conflict:** a module reads the same package exported from two different sources.
2. **Conflict when defining modules into a class loader:** two modules contain the same package but are mapped into the same loader under an invalid configuration.

One should not state that **any** two JARs with the same package cause every JVM startup to fail. The outcome depends on whether they are on the classpath or module path, which modules are resolved, whether the graph reads the package from both sources, and how the modules are defined into class loaders/layers.

### 3.1. Readability and exports differ from classpath lookup

~~~text
com.example.app
   | requires
   +-------------------> com.example.alpha
   |                       exports com.example.shared
   |
   | requires
   +-------------------> com.example.beta
                           exports com.example.shared
~~~

If **com.example.app** reads **com.example.shared** from both alpha and beta, the compiler may report:

~~~text
module com.example.app reads package com.example.shared
from both com.example.alpha and com.example.beta
~~~

The actual message may vary by tool and JDK version. The meaning remains: the configuration is delivering the same package to the consuming module from two module sources.

**exports** defines package accessibility from other modules; **requires** creates a read relationship. They are not mechanisms for transferring package ownership between modules.

### 3.2. JPMS fixes boundaries at the module level

On the classpath, multiple dependencies can share classes within a package without reporting an error immediately. With JPMS, such a structure needs to be reviewed:

- Do the classes belong to a single logical library?
- Does the package need to be consolidated into a single named module?
- Are the two dependencies truly independent in API and lifecycle?
- Can the packages be renamed to express ownership boundaries?
- Should one dependency remain only on the classpath during the transition period?

Changing packaging can affect public APIs and consumers, because the package is part of a class's fully qualified name.

## 4. Example reproducing the reads package ... from both error

Consider three independent named modules.

### 4.1. Module alpha

File **src/com.example.alpha/module-info.java**:

~~~java
module com.example.alpha {
    exports com.example.shared;
}
~~~

File **src/com.example.alpha/com/example/shared/Alpha.java**:

~~~java
package com.example.shared;

public class Alpha {
    public static String name() {
        return "alpha";
    }
}
~~~

### 4.2. Module beta

File **src/com.example.beta/module-info.java**:

~~~java
module com.example.beta {
    exports com.example.shared;
}
~~~

File **src/com.example.beta/com/example/shared/Beta.java**:

~~~java
package com.example.shared;

public class Beta {
    public static String name() {
        return "beta";
    }
}
~~~

Modules alpha and beta have different names but export the same package **com.example.shared**.

### 4.3. Module app

File **src/com.example.app/module-info.java**:

~~~java
module com.example.app {
    requires com.example.alpha;
    requires com.example.beta;
}
~~~

File **src/com.example.app/com/example/app/Main.java**:

~~~java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("start");
    }
}
~~~

Even though Main does not directly call Alpha or Beta yet, the module descriptor still has both **requires** relationships.

### 4.4. Compiling each module

Create the output directories beforehand and then compile each module independently:

~~~bash
# Linux/macOS shell example
mkdir -p mods/com.example.alpha mods/com.example.beta mods/com.example.app

javac -d mods/com.example.alpha \
  src/com.example.alpha/module-info.java \
  src/com.example.alpha/com/example/shared/Alpha.java

javac -d mods/com.example.beta \
  src/com.example.beta/module-info.java \
  src/com.example.beta/com/example/shared/Beta.java
~~~

When compiling app:

~~~bash
javac --module-path mods -d mods/com.example.app \
  src/com.example.app/module-info.java \
  src/com.example.app/com/example/app/Main.java
~~~

The compiler may report an error because app reads package **com.example.shared** from both alpha and beta. The example is a module graph error rather than being caused by duplicate Alpha/Beta class names.

If alpha and beta are turned into JARs and both are placed on the module path, the same conflict pattern can appear when module app resolves dependencies.

### 4.5. Changing packages to fix the root cause

One fix direction is to give each module its own package:

~~~text
com.example.alpha
└── com/example/alpha/api/Alpha.class

com.example.beta
└── com/example/beta/api/Beta.class
~~~

Descriptors after the fix:

~~~java
module com.example.alpha {
    exports com.example.alpha.api;
}
~~~

~~~java
module com.example.beta {
    exports com.example.beta.api;
}
~~~

Then app can read both packages without ambiguity. However, renaming a package changes the binary name of classes, so consumers importing or linking against the old name need to be updated or have a transitional compatibility plan.

## 5. Split packages with automatic modules

An old library JAR without **module-info.class** can become an **automatic module** when placed on the module path. This module is named from metadata such as **Automatic-Module-Name** in the manifest or from the JAR name according to JPMS rules.

For example:

~~~text
legacy-utils-1.0.jar
├── META-INF/MANIFEST.MF
└── com/example/common/Helper.class
~~~

When it is on the module path:

~~~bash
java --module-path lib:mods -m com.example.app/com.example.app.Main
~~~

it can be resolved as an automatic module, rather than just a set of classes in the unnamed module.

### 5.1. Automatic modules do not eliminate split package risk

An automatic module helps bring legacy libraries into the module graph during migration. However, it is still a **named module** when resolved and has its own package set.

If two automatic modules contain the same package, or an automatic module overlaps packages with an explicit named module, the module graph can conflict. The fact that they do not have an author-written descriptor does not make duplicate packages disappear.

An automatic module typically exports its packages to make interacting with other modules easier. This can cause duplicate packages to surface as soon as dependencies are brought into the same graph.

### 5.2. Inspecting the actual module name

Use:

~~~bash
jar --describe-module --file legacy-utils-1.0.jar
~~~

If the JAR does not have an explicit descriptor, the output can indicate that this is an automatic module and show the module name derived from the filename/manifest.

A name derived from the JAR filename can change when the artifact name changes. Therefore, when deciding to use an automatic module long-term, it is necessary to stabilize the module name and check all dependencies declaring **requires** on that name.

### 5.3. Do not treat Automatic-Module-Name as a split package solution

Adding to the manifest:

~~~text
Automatic-Module-Name: com.example.legacy
~~~

helps stabilize the **module name**, without renaming the packages inside the JAR. Two JARs, even with different module names, still split a package if they both contain **com.example.common**.

Some systems only encounter errors after upgrading a dependency because the new version adds **Automatic-Module-Name** or starts including **module-info.class**. It is necessary to analyze the actual JAR at runtime, not just the POM or build file.

## 6. Named modules and the classpath during the transition period

A common migration strategy is to gradually move libraries to JPMS while the rest remains on the classpath.

~~~text
               Application
                  |
             Named modules
                  |
             Automatic modules
                  |
               Classpath
              (unnamed)
~~~

The diagram only illustrates the regions that may exist; it does not mean named modules automatically read the classpath.

### 6.1. Unnamed modules have their own rules

Code on the classpath belongs to the unnamed module associated with a class loader. The unnamed module can read resolved named modules, but a named module **does not by default** read the unnamed module like a dependency declared with **requires**.

If code in a named module needs to call a library that is only on the classpath, it may encounter readability errors or fail to find types as expected. In some migration configurations, the flag:

~~~bash
--add-reads com.example.app=ALL-UNNAMED
~~~

can be used to add a read edge from the named module to unnamed modules.

This is a mechanism for adjusting readability, **not a way to fix a split package between two named modules**. If a package still appears from two read sources, adding a read edge does not turn it into a single package.

### 6.2. The classpath can hide conflicts

For example:

~~~text
classpath:
  vendor-a.jar -> com.example.util.Parser
  vendor-b.jar -> com.example.util.Validator
~~~

This configuration may run. However, after both JARs become automatic modules on the module path, both modules carry the package **com.example.util**, causing a conflict.

Therefore, the test “the old application runs on the classpath” only proves the old baseline; it does not prove the module path design will work.

### 6.3. Avoid overusing moving back to the classpath

Moving a dependency back to the classpath can be a transitional solution if the architecture allows it. However, you need to consider:

- Does the named module need to directly reference types from that dependency?
- Are **--add-reads** flags and other access mechanisms needed?
- Is there a transitive dependency on a duplicate package?
- Are there changes to ServiceLoader and reflective access?
- How long can this configuration be kept?
- Is there a plan to move package ownership to a clear model?

One should not present “put everything on the classpath” as a complete JPMS migration solution. It removes some JPMS checks and can retain classpath ambiguities.

## 7. Distinguishing module resolution errors from class-loading errors

Not every error occurring after switching to the module path is caused by a split package. It is necessary to read the exact error type and the stage where it occurs.

| Error or message | Common stage | Typical cause | Relation to split packages |
|---|---|---|---|
| **module X reads package p from both A and B** | javac or graph verification | X reads package p from two named modules | Direct indicator |
| **ResolutionException** | Module graph resolution | The graph fails to satisfy readability or package constraints | Can be due to a split package, but there are other causes |
| **LayerInstantiationException** | Creating module layer/class loader mapping | The module layer cannot be defined according to the package/module mapping | Can be due to duplicate packages in the same loader |
| **FindException** | Finding/reading modules on the module path | Module cannot be found, corrupt descriptor/JAR, invalid module configuration | Can be related, though not by default |
| **ClassNotFoundException** | Loading a class by name | Class is missing or the loader cannot see the class | Not enough to conclude a split package |
| **NoClassDefFoundError** | Linking or loading a class | Dependent class is missing or a prior loading error occurred | Can be another consequence of migration |
| **IllegalAccessError** | Linking/accessing a type or member | Invalid runtime access | Usually exports/access, not a pure split package |
| **InaccessibleObjectException** | Reflection | Package is not properly opened to the caller | Not a split package |
| **NoSuchMethodError** | Linking a method call | Artifact version differs in descriptor or API | Usually due to a dependency conflict/duplicate class |

Do not just look at the exception name and automatically tweak **--add-exports** or **--add-opens**. You must determine which module is reading which package and which actual artifact is loaded.

### 7.1. ResolutionException and the module graph

Module resolution is the process of selecting a set of modules and establishing valid read relationships from root modules and dependencies. A package conflict can make the graph invalid before the application enters the **main** method.

If you see an error from **java.lang.module.Resolver** or a message stating a module reads the same package from two sources, trace the path:

~~~text
Root module
   |
   +---- requires A
   |
   +---- requires B
               |
               +---- exports package p
A also exports package p
~~~

Check **requires transitive** as well, not just the requires written directly in root.

### 7.2. LayerInstantiationException and module-to-loader mapping

A **ModuleLayer** is a set of modules configured and defined together. Depending on how the layer is created, multiple modules can share the same class loader or have different loaders.

If two modules own the same package and defining them in the same loader is not permitted, layer creation can throw **LayerInstantiationException**.

For example, in a plugin architecture, a customization using **defineModulesWithOneLoader** may encounter different constraints than a loader-per-module design. This is not a reason to disable the constraints: you need to analyze the module graph, package sets, and how loaders are created.

### 7.3. FindException is not automatically a split package

**FindException** can occur when the module path has a corrupt JAR file, an invalid module descriptor, a module name that cannot be found, or other errors while reading metadata.

When seeing FindException, prioritize reading the message and cause first. If the message does not clearly indicate duplicate packages, inspect the artifacts and module descriptors before concluding.

### 7.4. “Class not found” errors differ from duplicate package errors

**ClassNotFoundException** usually occurs in dynamic class loading such as **Class.forName**, or when the class loader cannot see the class to load. **NoClassDefFoundError** can occur if a dependent class is missing at runtime.

Meanwhile, a split package is an issue with package sources in the module graph or loader mapping. The two groups of errors can appear together in a migration, yet their fixes are not the same.

## 8. Role of class loaders

### 8.1. Class identity consists of class name and defining loader

Two classes with the same fully qualified name created by two different defining class loaders are not necessarily the same type to the JVM.

For example:

~~~text
PluginLoader A:
  com.example.spi.PluginImpl

PluginLoader B:
  com.example.spi.PluginImpl
~~~

Even with the same name, the two classes may not be castable to each other if the loaders differ and the API is improperly duplicated. A **ClassCastException**-style error can appear, though that is not always a split package in JPMS.

### 8.2. Package ownership and loader mapping are two control layers

JPMS checks packages, readability, and access at the module level. JVM class loading checks class identity and mapping to the defining loader.

You need to examine simultaneously:

1. Which module has the package.
2. Which modules are resolved in the layer.
3. Which modules read or export that package.
4. The defining class loader of the module.
5. Which class or resource is actually loaded.
6. Whether another class with the same name exists on the classpath or in a plugin loader.

A simple diagram:

~~~text
ModuleLayer
   |
   +---- Module A ---> Loader L1 ---> package p
   |
   +---- Module B ---> Loader L2 ---> package p
   |
   +---- Module C ---> Loader L3 ---> package q
~~~

Some isolated class loader configurations can avoid conflicts when defining packages in the same loader. However, that does not automatically satisfy all rules for module resolution, readability, service type identity, and communication between plugins. Isolated loaders should not be used as a “trick” to bypass package ownership design.

### 8.3. Plugin systems need additional checks

When loading plugins into another layer or a separate loader:

- Does the plugin need to import the host's public API?
- Are API types duplicated inside each plugin JAR?
- Do the host and plugin see the exact same **com.example.spi.Plugin** type from one module/loader?
- Is there an internal split package among plugins?
- Is **opens** required for reflection?
- Is there any loader mapping that defines multiple modules with the same package into one loader?

A sustainable solution is usually keeping shared contract APIs in one clear module, while placing separate implementations in different packages/modules.

## 9. Common causes in real-world projects

### 9.1. Splitting a logical package across multiple artifacts

In legacy systems:

~~~text
client-api.jar
  com.example.client.Request

client-impl.jar
  com.example.client.DefaultRequest
~~~

Two artifacts share the same package to separate API and implementation. On the classpath, this structure can work.

When turning the two artifacts into two separate named modules, the **com.example.client** package is split. The solution may be to consolidate them into one module or move the implementation to **com.example.client.internal** if the API allows.

### 9.2. Old and new JARs appearing together

The dependency graph can simultaneously contain:

~~~text
legacy-core.jar  -> com.example.common.*
new-core.jar     -> com.example.common.*
~~~

This can be the result of direct dependencies, transitive dependencies, or improper shading.

In that case, it is necessary to exclude the old artifact or align version constraints, not merely rename the module.

### 9.3. “All-in-one” libraries and component libraries

A library suite may provide both an aggregate artifact and sub-artifacts:

~~~text
vendor-all.jar
  com.vendor.api.*
  com.vendor.impl.*

vendor-api.jar
  com.vendor.api.*
~~~

If both go onto the module path, the **com.vendor.api** package is duplicated. Depending on the specific structure, there may also be duplicate classes.

The usual approach is to pick a single dependency strategy, rather than using both “all” and “api” unless vendor documentation requires it.

### 9.4. Shaded JARs without package relocation

A library may embed a dependency into its JAR without changing the package:

~~~text
my-sdk.jar
  com.example.sdk.*
  org.thirdparty.codec.*

thirdparty-codec.jar
  org.thirdparty.codec.*
~~~

Then the same package **org.thirdparty.codec** appears from two modules. Simply “shading” into another JAR does not automatically avoid split packages. You need to review the relocation policy and its impact on the API.

### 9.5. Generated code or annotation processors

A code generator can produce classes in a package already owned by another module. For example:

- ORM-generated metamodels.
- Protocol buffer or gRPC-generated classes.
- SOAP/JAXB-generated classes.
- Annotation processors that auto-generate helpers into the library's package.
- Auto-generated adapters packaged into a separate JAR.

If a generator outputs code into the same package as the original library yet into a different artifact/module, JPMS migration can encounter a split package. It is necessary to identify which module owns the generated source and put it in the right place.

### 9.6. Test fixtures and test dependencies

Test sources or fixture JARs may use the same package as production code to access package-private helpers. When switching to named modules, the test configuration may begin to conflict.

A controlled approach is to **patch** test classes into the module under test during the test phase, if the build tool supports it, instead of packaging test fixtures into another named module that owns the same package. This is a test-specific configuration choice, not a general solution for two production library modules.

## 10. Inspecting duplicate packages from actual JARs

To fix the error, you need to know **which artifact** contains the duplicate package. Reading dependency declarations is not enough because of transitive dependencies and repackaged JARs.

### 10.1. Listing classes in a JAR

Use the command:

~~~bash
jar --list --file path/to/library.jar
~~~

Look for entries:

~~~text
com/example/shared/Alpha.class
com/example/shared/Beta.class
~~~

Convert the class file path into a package name by removing the class name part after the last slash.

Be careful to avoid mistakenly assigning resource files to packages or treating **META-INF/** as a Java package. For **multi-release JARs**, classes under **META-INF/versions/** also need to be analyzed according to the runtime release; do not simply treat every entry as a different module.

### 10.2. Viewing the module descriptor

~~~bash
jar --describe-module --file path/to/library.jar
~~~

For an explicit named module, the output helps verify:

- Module name.
- Exports.
- Requires.
- Provides/uses when present.
- Package metadata according to the descriptor/JAR format.

For an automatic module, check the module name derived or declared in the manifest.

The module descriptor output helps identify exported packages, yet a split package can also involve unexported packages in a loader mapping scenario. Therefore, it is necessary to inspect the actual class set, not only the exports.

### 10.3. Checking the module path

The Java launcher has the option:

~~~bash
java --validate-modules --module-path path/to/libs
~~~

This option is useful for detecting some module path issues before running the application. However, it does not replace testing **the exact root module** and module graph that the application actually resolves.

In some projects, it is necessary to run the check command with the same module path, module name, and launcher arguments used in production to reproduce the error.

### 10.4. Checking dependency relationships

With Maven:

~~~bash
mvn dependency:tree
~~~

With Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

These commands help trace transitive dependencies or aggregate artifacts. In projects with different source sets/tasks, you need to inspect the exact configuration of the corresponding application or test.

Do not only look at direct dependencies. Two modules with duplicate packages can come from two different transitive paths.

### 10.5. Checking the module graph and static dependencies

**jdeps** can assist in viewing dependencies at the package or module level, depending on parameters:

~~~bash
jdeps --module-path path/to/libs --check com.example.app
~~~

For a JAR artifact:

~~~bash
jdeps --summary path/to/app.jar
~~~

**jdeps** primarily observes static dependencies. Reflection, ServiceLoader, code generation, and classes only loaded via configuration may not appear completely. Therefore, it needs to be combined with runtime inspection.

### 10.6. Building an evidence table

| Package | Artifact 1 | Artifact 2 | Module type | Detection point |
|---|---|---|---|---|
| com.example.shared | alpha.jar | beta.jar | Two named modules | Compile module app |
| org.thirdparty.codec | sdk-shaded.jar | codec.jar | Automatic + explicit/automatic | Validate module path |
| com.example.generated | app.jar | fixtures.jar | Named + test fixture | Test task |
| com.vendor.api | vendor-all.jar | vendor-api.jar | Two vendor JARs | Dependency graph |

The table should additionally record versions, checksums, dependency sources, and owners in actual practice. It is insufficient information if only filenames are recorded: two environments may contain JARs with the same name but different contents.

## 11. Step-by-step diagnostic process

### Step 1: Record the exact error

Save verbatim:

- Launch command line.
- JDK version and vendor.
- Module path and classpath.
- Root module or main class.
- Stack trace and message.
- List of runtime artifacts/versions.

If the error occurs in Gradle/Maven/IDE, identify which process reported the error: compiler, test worker, JavaExec, or application JVM.

### Step 2: Identify the package and the two sources

If the message is **reads package p from both A and B**, note p, A, and B clearly. Check the JARs and module descriptors to confirm the package exists in each source.

If the error only states **LayerInstantiationException**, inspect the cause and module-to-classloader mapping. If the error is **NoClassDefFoundError**, there is not enough evidence yet to conclude a split package.

### Step 3: Draw a minimal dependency/module graph

For example:

~~~text
app
 | \
 |  \-- requires lib-b
 |
 +----- requires lib-a

lib-a -> exports p
lib-b -> exports p
~~~

Mark direct and transitive dependencies, automatic modules, unnamed code, and modules added via launcher arguments.

### Step 4: Determine the duplication level

It may be:

1. Only duplicate package, different classes.
2. Both duplicate package and duplicate fully qualified class.
3. Duplicate package only in test/generated code.
4. Duplication inside a shaded JAR.
5. Duplication between a named module and a library on the classpath.
6. Duplication across module layers/loaders yet not in the same read graph.

Each type has a different remediation approach. Renaming the module alone cannot resolve duplicate classes/packages.

### Step 5: Choose a fix based on ownership

Determine which module **should own the package**. If it is the same logical library, classes can be consolidated into one module. If they are two independent libraries, namespaces should be separated. If a dependency is unnecessarily duplicated, exclude it.

### Step 6: Re-verify both binary and behavior

After fixing, you need to:

- Rebuild the necessary named modules.
- Verify the module graph.
- Run the application on the exact target module path.
- Run API/consumer tests.
- Verify reflection, ServiceLoader, and plugins.
- Ensure public FQCNs are not changed without a migration plan.
- Save artifacts and test logs.

Do not stop once the compiler stops reporting **reads package**. A package workaround can break class casts, serialization, or ServiceLoader at runtime.

## 12. Strategies for handling split packages

### 12.1. Consolidating classes of the same package into one named module

If A and B are actually two parts of one logical library, a single named module can own the entire package:

~~~text
Before:
  module A -> com.example.shared.Alpha
  module B -> com.example.shared.Beta

After:
  module com.example.sharedlib
    -> com.example.shared.Alpha
    -> com.example.shared.Beta
~~~

Advantages:

- Clear package ownership.
- Can keep the existing package name and class FQCNs.
- Reduces split packages on the module path.

Considerations:

- The build/dependency graph changes.
- The same class should not be packaged twice in old and new artifacts.
- Consumers must know the new module name if using module-info.
- It may be necessary to keep a transitional artifact on the classpath for older consumers.
- Public API contracts and OSGi/JPMS integration may be affected.

### 12.2. Renaming the package on one side

For example:

~~~text
Before:
  alpha -> com.example.common.Alpha
  beta  -> com.example.common.Beta

After:
  alpha -> com.example.alpha.Alpha
  beta  -> com.example.beta.Beta
~~~

Advantage: each module has its own namespace, reducing unnecessary dependencies.

Disadvantage: class FQCNs change, leading to breaking changes for source imports, bytecode consumers, reflection, serialized data, and configuration. An adapter/migration guide or an appropriate major version is needed.

### 12.3. Excluding duplicate dependencies

If the conflict is caused by an old artifact pulled in transitively that is no longer needed, exclude it at the dependency declaration or select the right vendor artifact set.

Gradle Groovy DSL example, illustrative:

~~~groovy
dependencies {
    implementation('com.example:feature:2.0') {
        exclude group: 'com.vendor', module: 'legacy-api'
    }
    implementation 'com.vendor:modern-api:3.0'
}
~~~

The condition is that **feature** is actually compatible with **modern-api**. Manual exclusion does not prove the runtime still has all required classes. After excluding, verify the dependency graph, compilation, and integration tests.

Maven example:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>feature</artifactId>
    <version>2.0</version>
    <exclusions>
        <exclusion>
            <groupId>com.vendor</groupId>
            <artifactId>legacy-api</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

An appropriate replacement artifact must also be declared if the code still uses the vendor's API.

### 12.4. Relocation when shading dependencies

If an internal library embeds a dependency into its JAR, the dependency's private package can be relocated:

~~~text
Before:
  sdk.jar        -> org.thirdparty.codec.*
  codec.jar      -> org.thirdparty.codec.*

After:
  sdk.jar        -> com.example.sdk.internal.codec.*
  codec.jar      -> org.thirdparty.codec.*
~~~

Relocation can prevent a split package between two modules. However, note:

- Do not arbitrarily relocate types appearing in the public API.
- Reflection using string class names may need adjustment.
- Service provider configuration under **META-INF/services** must be handled.
- Serialization may depend on old class names.
- Native/JNI bindings or resource paths may need to change.
- Dependency licenses and distribution policies must be respected.

Relocation is most suitable for privately packaged implementation details, not APIs shared by multiple consumers.

### 12.5. Moving generated sources to the owning module

If generated classes need to reside in the same package as the API to access package-private members, the build can be configured so that those sources are compiled as part of the module that owns the package.

A temporary option in tests/tooling is **--patch-module**. However, merging generated sources into a module must follow clear ownership and build processes; one should not create a separate named module containing the same package just to move an artifact from the classpath to the module path.

### 12.6. Keeping part of the legacy code on the classpath in a controlled manner

Old libraries can be kept in the unnamed module if the application still has classpath code and cannot modularize everything yet.

This is a transitional choice, not to be treated as the target architecture if the goal is full JPMS. Record:

- Which modules remain on the classpath.
- Which named modules need to access them.
- Temporary runtime flags.
- Testing with the exact class loader.
- When the workaround will be removed.

### 12.7. Separating shared API from separate implementations

If two modules share a package because they both use an interface/DTO, consider creating a shared API module and moving implementations into separate packages:

~~~text
com.example.contract
└── com.example.contract.api.Request

com.example.client
└── com.example.client.impl.ClientRequest

com.example.server
└── com.example.server.impl.ServerRequest
~~~

Client/server modules can **requires com.example.contract**, instead of copying API classes or creating half of a shared package in each JAR.

This gives the API a single source of definition and reduces class identity errors when services or plugins communicate.

## 13. Command-line options: what can and cannot be fixed?

### 13.1. --patch-module

Illustrative syntax:

~~~bash
java --patch-module com.example.app=path/to/extra-classes \
     --module-path path/to/mods \
     -m com.example.app/com.example.app.Main
~~~

**--patch-module** injects additional classes/resources into an existing module. This mechanism is useful for tests, certain migration scenarios, or controlled modifications. It is not a command that “allows two different named modules to both own package p”.

Do not use patch-module to mask a duplicate dependency structure long-term. Special caution is needed when the new class and the original class have the same FQCN.

### 13.2. --add-reads

~~~bash
--add-reads com.example.app=ALL-UNNAMED
~~~

Adds readability, often used as a bridge between named/unnamed code. It does not move a package from one module to another; it does not automatically resolve a package appearing in two read named modules.

### 13.3. --add-exports

~~~bash
--add-exports com.example.core/com.example.core.internal=com.example.app
~~~

Opens **compile/runtime** access to a package from another module via an additional export mechanism. It does not change package ownership and does not help distinguish two modules that both export package p to the same consumer.

### 13.4. --add-opens

~~~bash
--add-opens com.example.core/com.example.core.internal=com.example.app
~~~

Permits deep reflection on the specified package, within the option's scope. It solves reflective access issues, not split packages.

### 13.5. --module-path and --class-path

- **--module-path** declares where to look for named modules.
- **--class-path** declares classes/resources belonging to the unnamed module.

Moving a JAR from the classpath to the module path can completely change how packages are interpreted. Conversely, moving a JAR back to the classpath can temporarily avoid a conflict between named modules, yet changes readability, access, and service loading constraints.

### 13.6. Quick selection table

| Symptom | Appropriate tool/approach | Should not be used as the solution |
|---|---|---|
| Two modules export the same package to app | Fix package ownership or dependency graph | Only adding --add-exports |
| Named module needs to read classpath code | Design a bridge or controlled --add-reads | Automatically renaming the module |
| Reflection cannot access internal package | Design API/opens, possibly --add-opens | Relocating packages before understanding the risks |
| Test classes need to be in the module's package | Appropriate test patch-module configuration | Creating a named test module that splits the package |
| Shaded JAR duplicates package with original dependency | Remove duplicate copy or relocate implementation | Only changing Automatic-Module-Name |
| New class is not found | Check classpath/module path, module resolution, and loader | Concluding split package by default |

## 14. Impact on binary compatibility and old consumers

When renaming a package, the class's fully qualified name changes:

~~~text
com.example.shared.Helper
             |
             v
com.example.alpha.Helper
~~~

Old consumer bytecode still references **com.example.shared.Helper**. If the new version no longer has a class with that name, the JVM may fail to link. Therefore, renaming a package can solve JPMS yet create a breaking change for old consumers.

### 14.1. Distinguishing internal migration from public libraries

**Internal applications:** if all source and binaries are under one team's control, packages can be refactored and rebuilt synchronously, provided testing is thorough.

**Shared libraries:** attention must be paid to already-released consumer binaries, partner plugins, service loaders, reflection, serialization, and API signatures.

A roadmap for a public library may include:

1. Announcing the target module structure.
2. Identifying which packages change.
3. Marking old APIs deprecated when feasible.
4. Providing new APIs/adapters.
5. Keeping a transitional compatibility version if design allows.
6. Running old consumer binaries against the new artifact.
7. Releasing breaking changes according to the published versioning policy.

Not every old type can keep the same FQCN if it continues to cause a split package. A bridge class placed in the old package must also have a valid owning module.

### 14.2. Binary compatibility is not synonymous with JPMS compatibility

A new JAR can preserve all public methods and class names, yet if package packaging changes cause the module graph not to resolve, applications on the module path still fail.

Conversely, fixing a split package by changing FQCNs can produce a valid module graph yet break previously compiled consumers.

Therefore, acceptance criteria should include all of:

- Binary API compatibility.
- Module graph resolution.
- Class loading.
- Service discovery.
- Runtime behavior and data compatibility.

## 15. Multi-phase migration model

A practical roadmap can be executed as follows:

~~~text
M0 — Classpath baseline
     Finalize JARs, dependency graph, plugins, and tests
                  |
                  v
M1 — Package ownership analysis
     List packages, module names, source artifacts
                  |
                  v
M2 — Module graph design
     Split namespaces or consolidate packages, define APIs
                  |
                  v
M3 — Migrate dependencies and module descriptors
     Explicit/automatic modules, requires/exports/opens
                  |
                  v
M4 — Reproduce and resolve errors
     Compile, validate modules, startup, plugin loading
                  |
                  v
M5 — Consumer testing and rollout
     Binary compatibility, runtime, rollback
~~~

Each milestone needs entry conditions, evidence, and a Go/No-Go decision.

### 15.1. Sample acceptance criteria

| ID | Acceptance criteria | Evidence |
|---|---|---|
| AC-01 | No duplicate packages causing conflicts remain among named modules in the target graph | Package ownership and module graph report |
| AC-02 | Module app compiles successfully with the exact module path | CI compiler log |
| AC-03 | Module graph resolves and application starts | Java launcher/smoke test |
| AC-04 | No unplanned duplicate dependencies or old JARs remain | Dependency report and checksum |
| AC-05 | Main ServiceLoader, reflection, proxies, and plugins work | Integration tests |
| AC-06 | Old consumers needing support still link and run | Tests using old consumer binaries |
| AC-07 | No regressions in critical behavior | Regression tests |
| AC-08 | Rollback exists for packaging or dependency migration | Rollback drill and release documentation |

If a workaround such as **--patch-module** or **--add-reads** remains, record the owner, reason, tests, and removal conditions before considering migration complete.

### 15.2. Required test matrix

| Environment | Classpath/module path | Purpose |
|---|---|---|
| Old baseline | Classpath before migration | Capture existing behavior |
| Target compile | Module path as designed | Detect reads-package conflicts |
| Target runtime | Same graph as production | Detect resolution/layer errors |
| Integration test | Module path + runtime integrations | Reflection, ServiceLoader, plugins |
| Old consumers | Old binaries + new JAR | Binary compatibility |
| Test fixtures | Actual test module configuration | Detect duplicate packages caused by fixtures |
| Container/runtime image | Exact deployment JDK and artifacts | Eliminate environment mismatch |

Do not run tests only on the classpath and then conclude the module path is valid.

## 16. Real-world analysis scenario

Suppose an application has two dependencies:

~~~text
reporting-api.jar
  module com.example.reporting.api
  package com.example.reports
  class Report

reporting-extras.jar
  automatic module com.example.reporting.extras
  package com.example.reports
  class PdfReport
~~~

On the old classpath, the application uses both **Report** and **PdfReport** normally. When moving to the module path, module app declares requires for both modules. This configuration can produce the error **reads package com.example.reports from both ...**.

### 16.1. Root cause analysis

- Two modules have different names.
- Both contain the package **com.example.reports**.
- The automatic module extras has no hand-written descriptor, yet still has a package set.
- App reads the same package from two modules.
- There is no duplicate class name issue; the conflict is at the package level.

### 16.2. Option A: consolidate into one module

If the two artifacts are released by the same team and can be published together, consolidate Report and PdfReport into one named module **com.example.reporting**.

Advantage: the old package name can be preserved. Risk: the module name and consumer dependency declarations need updating.

### 16.3. Option B: change the package of extras

Move PdfReport to:

~~~java
package com.example.reports.pdf;
~~~

and have extras export the new package. Advantage: artifacts remain independently separated. Risk: old code using **com.example.reports.PdfReport** must migrate.

### 16.4. Option C: remove extras if no longer needed

If PdfReport has been integrated into the new version of reporting-api, remove the extras dependency. However, it must be verified that no runtime consumer is using classes that exist only in extras.

### 16.5. Selection

An option cannot be chosen solely from the error message. It is necessary to consider package ownership, public API contracts, consumer release schedules, and how to guarantee binary compatibility. The accepted roadmap must have real tests and a rollback strategy.

## 17. Common misconceptions

### “Two JARs without classes of the same name do not have a split package.”

False. It only requires them both to have classes belonging to the same package, even if the class names differ.

### “Setting different Automatic-Module-Names is enough.”

False. Different module names do not change the packages inside the JAR.

### “Adding --add-exports or --add-opens will bypass duplicate package errors.”

False. Those two options handle access/reflective access permissions, not package ownership or module graph conflicts.

### “Enabling the classpath for a JAR finishes the JPMS fix.”

Not necessarily. That may be a workaround, but named modules, unnamed modules, and class loaders have their own constraints; readability, access, and migration goals need to be re-examined.

### “NoClassDefFoundError is always caused by a split package.”

False. It can be due to a missing class, dependency mismatch, initialization failure, or class loading error. You must inspect the message and cause.

### “If javac has no errors, all plugins will run.”

False. Reflection, ServiceLoader, generated proxies, serialization, and plugin loaders can fail at runtime. Integration tests on real artifacts are required.

### “Renaming a package is only a source refactoring.”

Incorrect for already-compiled consumers. FQCNs reside in bytecode, service configurations, and possibly in serialized data. Renaming a package can cause breaking changes.

### “A package can reside in multiple modules as long as each module exports different classes.”

Export operates by **package**, not by a selective set of classes. A module graph cannot be safely designed on the assumption that app will pick class Alpha from module A and class Beta in the same package from module B in an ambiguous read relationship.

## 18. Checklist before releasing a JPMS migration

### Packages and artifacts

- [ ] Listed packages in every JAR on the target module path.
- [ ] Detected duplicate packages, duplicate classes, and shaded dependencies.
- [ ] Identified reasonable package owners.
- [ ] Recorded module names of explicit and automatic modules.
- [ ] Checked direct and transitive dependencies.
- [ ] Checked generated sources, tests, and fixtures.

### Module graph and class loaders

- [ ] Recorded requires/exports/opens and root modules.
- [ ] Verified that packages are read from a single valid source.
- [ ] Verified modules sharing loaders/layers according to runtime configuration.
- [ ] Distinguished named, automatic, and unnamed modules.
- [ ] Determined the exact module path/classpath of CI and production.
- [ ] Verified plugin APIs are not duplicated across loaders.

### Remediation approach

- [ ] Chose package consolidation, namespace change, dependency exclusion, or a transitional option with justification.
- [ ] Did not use --add-exports/--add-opens as a fake fix for split packages.
- [ ] If --patch-module is used, has clear ownership and scope.
- [ ] Assessed breaking changes when changing FQCNs.
- [ ] Updated module descriptors and dependency versions.
- [ ] Updated migration guides for consumers.

### Testing and evidence

- [ ] Module app compiles and resolves successfully.
- [ ] Application starts on the exact JDK and module path.
- [ ] Reflection, ServiceLoader, proxy, and plugin paths have been exercised.
- [ ] Old consumers needing support have been tested with original binaries.
- [ ] Verified which artifact classes/resources are actually loaded from when needed.
- [ ] Integration/regression tests and rollback plan are in place.
- [ ] Saved logs, checksums, and target module/package lists.

## 19. Standard documentation to reference

When handling special cases, prioritize Java SE and JPMS documentation for the target release:

- **JEP 261 — Module System:** https://openjdk.org/jeps/261
- **Java Platform Module System specification:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html
- **Java SE tools documentation** for **java**, **javac**, **jar**, and **jdeps** of the JDK being deployed.
- **java.lang.module** API, including ModuleFinder, Configuration, Resolver, and ModuleLayer, to understand the process of finding, resolving, and defining modules.

Gradle/Maven and vendor dependency documentation supplements how to configure the module path, but does not replace the rules of the Java module system.

---

**Conclusion:** A split package is a sign that legacy packaging boundaries do not yet align with ownership at the JPMS module level. The issue is not only duplicate class names; two modules containing different classes in the same package can also make the module graph or module layer invalid. A sustainable fix is to identify **one package owner**, adjust dependencies and public APIs intentionally, and then verify on the exact compiler, module path, runtime, and actual consumers.
