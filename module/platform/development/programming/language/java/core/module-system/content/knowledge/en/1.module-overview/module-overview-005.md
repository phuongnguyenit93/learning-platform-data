# Distinguishing modules from packages, JARs, and build projects

When learning the Java Platform Module System (JPMS), four concepts—**package**, **JAR**, **build project**, and **module**—often appear together. They can have a one-to-one relationship in a simple project, but they are not the same thing and do not solve the same problem.

Put briefly:

- **Package** organizes Java types into namespaces and language-level access boundaries.
- **JAR** is a file format for packaging classes, resources, and metadata.
- **Build project** is the unit managed by Maven, Gradle, or a build tool to compile, test, and publish artifacts.
- **Java module** is a named unit in JPMS that declares dependencies and decides which packages are exposed externally.

Importantly, **the boundaries of these four concepts do not automatically coincide**. A Maven project can produce one JAR, that JAR can contain one Java module, and that Java module can contain multiple packages. But that is a common arrangement, not a mandatory definition.

## 1. What is a package?

A package is a way of grouping classes, interfaces, enums, records, and other Java types into a namespace.

Example:

~~~java
package com.example.catalog.api;

public interface ProductCatalog {
    String titleFor(String sku);
}
~~~

The fully qualified name of this type is:

~~~text
com.example.catalog.api.ProductCatalog
~~~

A package helps:

- Avoid class name collisions across different parts of code.
- Organize code by feature or responsibility.
- Support package-private access in the Java language.
- Provide the basis for a module to export or open a set of APIs.

Usually, the source directory structure reflects the package:

~~~text
src/main/java/
└── com/example/catalog/api/
    └── ProductCatalog.java
~~~

However, a package is **not** a JAR file, a build project, or a Java module. Many packages can belong to a single module; in a traditional classpath environment, the same package can appear in multiple JARs.

Packages with similar names are also not necessarily the same package. **com.example.catalog** and **com.example.catalog.internal** are two separate packages, even though one name is a prefix of the other.

## 2. What is a JAR?

JAR stands for **Java ARchive**. Essentially, it is a ZIP-format archive used to package files:

- Compiled **.class** files.
- Resources such as properties, JSON, templates, or images.
- Metadata, especially **META-INF/MANIFEST.MF**.
- Other information such as service provider configuration.
- For a modular JAR, **module-info.class**.

Example:

~~~text
catalog-api.jar
├── META-INF/
│   └── MANIFEST.MF
├── module-info.class
├── com/example/catalog/api/ProductCatalog.class
└── com/example/catalog/internal/MemoryCatalog.class
~~~

Its contents can be viewed with:

~~~bash
jar --list --file catalog-api.jar
~~~

A JAR is a **packaging unit**, not automatically a JPMS named module by itself.

The same JAR can be perceived differently by Java depending on its location and metadata:

- A JAR with a valid **module-info.class** placed on the module path: recognized as an explicit named module.
- A JAR without a descriptor placed on the module path: can become an automatic module.
- A JAR loaded from the classpath: its classes are defined in the unnamed module of the corresponding class loader.

Placing a file named **catalog.jar** on the module path does not automatically give its Java module the name **catalog** if the JAR has a descriptor declaring a different name.

## 3. What is a build project?

A build project is a unit managed by Maven, Gradle, or a build system. It describes source sets, dependencies, compiler options, tests, packaging, and output artifacts.

In Maven, a project typically has a **pom.xml** file:

~~~text
catalog-api/
├── pom.xml
└── src/
    └── main/
        └── java/
~~~

In Gradle, a project can be configured with **build.gradle**, **build.gradle.kts**, and settings files:

~~~text
catalog-api/
├── build.gradle.kts
└── src/
    └── main/
        └── java/
~~~

A build project can:

- Compile source code into classes.
- Resolve dependencies from repositories or other projects.
- Run unit tests/integration tests.
- Package JARs or other artifacts.
- Publish artifacts with versions and metadata.

In Maven, artifact naming and coordinates typically look like:

~~~text
groupId    = com.example
artifactId = catalog-api
version    = 1.0.0
~~~

These values identify the **artifact in the Maven ecosystem**; they do not automatically become the Java module name in JPMS.

Maven also has the concept of a **multi-module reactor**, meaning an aggregator POM coordinates multiple subprojects. This is a "module" in Maven's terminology; it does not mean each subproject must be a JPMS module.

## 4. What is a Java module in JPMS?

A Java module is a configuration unit consisting of a module name, the packages owned by the module, and relationships with other modules.

An explicit named module typically has a **module-info.java** file:

~~~java
module com.example.catalog.api {
    exports com.example.catalog.api;
}
~~~

The descriptor can declare:

- **requires**: other modules that the current module needs to read.
- **exports**: packages permitted for public API access from other modules.
- **opens**: packages opened for deep reflection at runtime.
- **uses**: service interfaces consumed by the module.
- **provides ... with ...**: providers for a service.

Example:

~~~java
module com.example.catalog.app {
    requires com.example.catalog.api;
}
~~~

The **com.example.catalog.app** module reads the **com.example.catalog.api** module. For app to use **ProductCatalog**, the API module must also export the package containing that type.

Thus, JPMS does more than name a group of classes. It creates a **module graph**, enabling Java to resolve dependencies and enforce access boundaries between named modules.

## 5. Comparison table of the four concepts

| Criterion | Package | JAR | Build project | Java module |
|---|---|---|---|---|
| Nature | Namespace for Java types | Archive file | Build and artifact management unit | Dependency/encapsulation unit in JPMS |
| Defined by | Package declaration | Archive file structure | POM, Gradle script, build configuration | Module descriptor or automatic module rules |
| Example name | com.example.catalog.api | catalog-api-1.0.0.jar | Maven artifactId catalog-api | com.example.catalog.api |
| What does it contain? | Types belonging to the package | Classes, resources, metadata | Sources, dependencies, tests, build tasks | Packages, readability relationships, and export/open policies |
| Primary purpose | Organize types and package access | Distribute code | Automate build/test/release | Strong encapsulation and dependency control |
| Has its own version? | No standard package versioning mechanism in the language | Can carry name/version metadata | Usually has an artifact version | Descriptor can carry version metadata; runtime resolution does not operate like Maven dependency versions |
| Dependency relationships | No requires-style declarations | Can have metadata depending on mechanism | Maven/Gradle dependencies | requires, requires transitive, requires static |
| Exposure boundary | public and package-private | Does not create a JPMS boundary on its own | Does not create a JPMS boundary on its own | exports, opens, and readability |

When hearing a phrase like "put the module into a JAR", ask whether it refers to a **Java module** or a **Maven module**. A modular JAR is a JAR packaged as a JPMS module; it is still just **one way of distributing** a module.

## 6. Relationship between module, package, JAR, and project

In a small project, you might organize things as:

~~~text
Maven project: catalog-api
       |
       | build
       v
JAR: catalog-api-1.0.0.jar
       |
       | contains module-info.class
       v
Java module: com.example.catalog.api
       |
       +-- package com.example.catalog.api
       |
       +-- package com.example.catalog.internal
~~~

In the example:

- The Maven project is responsible for building.
- The JAR is the packaging output.
- module-info.class defines the JPMS module.
- The module owns multiple packages.
- You can export the API package while keeping the internal package unexported.

However, not all modules are distributed as JARs. Java also has **exploded modules** (directories containing module-info.class and classes), system modules in a runtime image, and other packaging formats used by JDK tools.

Therefore, the statement "one module always equals one JAR" is **incorrect**.

## 7. Complete example: two Java modules in two projects

Suppose you want to build a catalog application:

~~~text
workspace/
├── src/
│   ├── com.example.catalog.api/
│   │   ├── module-info.java
│   │   └── com/example/catalog/
│   │       ├── api/
│   │       │   ├── ProductCatalog.java
│   │       │   └── Catalogs.java
│   │       └── internal/
│   │           └── MemoryCatalog.java
│   └── com.example.catalog.app/
│       ├── module-info.java
│       └── com/example/catalog/app/
│           └── Main.java
├── out/
└── dist/
~~~

This is a source layout illustrating javac's **--module-source-path**. In Maven/Gradle, you can place each module in its own project, with sources under **src/main/java** of the corresponding project.

### API module: module-info.java

~~~java
module com.example.catalog.api {
    exports com.example.catalog.api;
}
~~~

The module exports the API package but does not export the implementation package.

### Public interface

~~~java
package com.example.catalog.api;

public interface ProductCatalog {
    String titleFor(String sku);
}
~~~

### Unexported implementation

~~~java
package com.example.catalog.internal;

import com.example.catalog.api.ProductCatalog;

public final class MemoryCatalog implements ProductCatalog {
    @Override
    public String titleFor(String sku) {
        return "Product " + sku;
    }
}
~~~

The **MemoryCatalog** class is public so a factory in the same module can instantiate it, but the package containing the class is **not exported**. Another named module cannot import this class in the ordinary way merely because the class is declared public.

### Factory in the API package

~~~java
package com.example.catalog.api;

import com.example.catalog.internal.MemoryCatalog;

public final class Catalogs {
    private Catalogs() {
    }

    public static ProductCatalog create() {
        return new MemoryCatalog();
    }
}
~~~

Consuming modules use the **ProductCatalog** interface and the **Catalogs** factory, without needing to know the implementation's name.

### Application module

~~~java
module com.example.catalog.app {
    requires com.example.catalog.api;
}
~~~

Main:

~~~java
package com.example.catalog.app;

import com.example.catalog.api.Catalogs;
import com.example.catalog.api.ProductCatalog;

public final class Main {
    public static void main(String[] args) {
        ProductCatalog catalog = Catalogs.create();
        System.out.println(catalog.titleFor("A-100"));
    }
}
~~~

In this structure, app does not depend directly on the implementation package. If the API module replaces MemoryCatalog with another implementation while preserving the API contract, app's code may not need any changes.

## 8. Compiling modules without a JAR

Even before packaging, both modules can be compiled into **exploded modules**.

From the workspace directory, run:

~~~bash
javac --module-source-path src \
      -d out \
      -m com.example.catalog.api,com.example.catalog.app
~~~

After compilation:

~~~text
out/
├── com.example.catalog.api/
│   ├── module-info.class
│   └── com/example/catalog/...
└── com.example.catalog.app/
    ├── module-info.class
    └── com/example/catalog/app/Main.class
~~~

Run directly:

~~~bash
java --module-path out \
     --module com.example.catalog.app/com.example.catalog.app.Main
~~~

Here, **out** contains exploded modules and is used as the module path. There is no need to create JARs first for these modules to be recognized.

This demonstrates that **a Java module is a JPMS concept, not synonymous with a JAR file**.

## 9. Packaging modules into modular JARs

After compiling, you can package them:

~~~bash
mkdir -p dist

jar --create \
    --file dist/com.example.catalog.api.jar \
    -C out/com.example.catalog.api .

jar --create \
    --file dist/com.example.catalog.app.jar \
    -C out/com.example.catalog.app .
~~~

Both JARs contain the compiled classes and the corresponding module-info.class.

Run from JARs:

~~~bash
java --module-path dist \
     --module com.example.catalog.app/com.example.catalog.app.Main
~~~

At this point:

- The build project or source code is no longer needed by the JVM.
- The two modular JARs serve as the distribution medium.
- The Java module name still comes from **module-info.class**.
- The module graph is still constructed based on requires.
- The API module still exports only its declared package.

The JAR filenames here were chosen for readability; in principle, they do not have to match the module names.

## 10. Maven dependencies and JPMS requires are two distinct relationships

If using Maven with two projects **catalog-api** and **catalog-app**, the app's POM might declare the dependency:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>catalog-api</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

The Maven dependency tells Maven that app needs the **catalog-api** artifact to build.

In app's Java source:

~~~java
module com.example.catalog.app {
    requires com.example.catalog.api;
}
~~~

The **requires** directive states that the named module app reads the named module API.

The two declarations need to be consistent, but they **do not replace each other**.

If only the Maven dependency exists without a matching requires, javac may report that the app module does not read the API module. If only requires exists without the build supplying the artifact, the compiler may report **module not found**.

Similarly, a Gradle dependency like **implementation(project(":catalog-api"))** defines a build dependency; it does not automatically turn into a requires directive in module-info.java.

## 11. Why doesn't a Java module name have to match the JAR name?

Suppose the released file is named:

~~~text
catalog-api-1.0.0.jar
~~~

But the descriptor inside is:

~~~java
module com.example.catalog.api {
    exports com.example.catalog.api;
}
~~~

The Java module name is **com.example.catalog.api**; the JAR filename is only the artifact name. Renaming the JAR file does not change the declared module name.

You can check:

~~~bash
jar --describe-module --file catalog-api-1.0.0.jar
~~~

This command is useful when reading build documentation or integrating third-party libraries: do not write requires based on the assumption that artifactId is the module name.

For a JAR without a descriptor placed on the module path, Java can derive an automatic module name using its own rules or use the **Automatic-Module-Name** manifest attribute if present. That is a different mechanism from an explicit named module.

## 12. Named, automatic, and unnamed modules

Three common cases:

| Case | Characteristics | Example |
|---|---|---|
| Explicit named module | Has an explicit module descriptor | JAR with module-info.class on the module path |
| Automatic module | Unmodularized JAR placed on the module path | legacy-util.jar on the module path |
| Unnamed module | Classes defined from the classpath | legacy-util.jar on the classpath |

Example with the same legacy JAR file:

~~~bash
java --class-path libs/legacy-util.jar com.example.Main
~~~

Classes in the JAR are loaded via the classpath and belong to the unnamed module of the associated class loader.

When that JAR is placed on the module path, Java can recognize it as an automatic module:

~~~bash
java --module-path libs \
     --add-modules legacy.util \
     --class-path app \
     com.example.Main
~~~

The name **legacy.util** is only illustrative; the actual automatic module name must be verified with JDK tools. An automatic module exports all of its packages and aids legacy library integration, but does not offer selective export boundaries like an explicit named module.

Key takeaway: **a JAR is an artifact; placing the artifact on the classpath or module path and its internal metadata determine how JPMS perceives it**.

## 13. Can a package span multiple JARs?

In a traditional classpath environment, a package can have classes packaged across multiple JARs:

~~~text
utils-a.jar -> com/example/common/TextUtil.class
utils-b.jar -> com/example/common/DateUtil.class
~~~

The class loader can find classes from both JARs on the same classpath, despite risks of duplicate classes and search-order dependencies.

However, when each JAR becomes **a separate named module**, having the same **com.example.common** package appear in two modules creates a **split package**.

JPMS enforces constraints on readability, exports, and class loader mapping. Split packages can cause compilation, module resolution, or module definition errors when the involved modules are used together.

Therefore, module design should maintain **clear package ownership**: each package belongs to one module within the same set of modules intended to work together. Do not treat "runs fine on the classpath" as proof that JARs are ready to move to the module path.

## 14. Can one project output multiple JARs?

Yes. Build tools can produce multiple artifacts, such as:

- A JAR containing main classes.
- A JAR containing test fixtures.
- A JAR containing sources.
- A JAR containing Javadoc.
- A JAR with another classifier for a specific environment.
- Artifacts that are shaded, repackaged, or produced by profiles.

This does not mean each JAR is a new Java module. For example, a source JAR is not an artifact that runs as a named module in the module graph simply because it has the **.jar** extension.

Conversely, a Java module can be defined from an exploded module directory instead of a JAR file.

When designing a build, clearly distinguish **which output artifacts are actually placed onto the runtime module path**.

## 15. Can one build project contain multiple Java modules?

Technically, build tools can be configured to manage and compile multiple Java modules from one set of sources. **javac** supports **--module-source-path** and **-m** to compile multiple named modules.

The illustrative example above placed two modules under one **src** directory and compiled them in a single command. That did not require two Maven projects.

However, in typical Maven/Gradle setups, the easier-to-manage model is usually **one subproject per main modular JAR**, so dependencies, tests, packaging, and publishing stay clearly organized.

Therefore:

- "One build project = one Java module" is a **common architectural convention**.
- "One build project must equal one Java module" is **conceptually incorrect**.

Choose an organization that fits your build needs and tool versions, rather than treating a convention as the definition of JPMS.

## 16. Module boundary vs. package boundary

Packages provide the **package-private** access level in the Java language. Types and members without public/protected/private modifiers can be accessed within package scope according to Java rules.

JPMS adds a coarser level:

~~~text
com.example.catalog.api module
├── exports com.example.catalog.api
│   ├── ProductCatalog
│   └── Catalogs
└── com.example.catalog.internal
    └── MemoryCatalog
~~~

In the module descriptor:

~~~java
module com.example.catalog.api {
    exports com.example.catalog.api;
}
~~~

If code in the app module attempts to import:

~~~java
import com.example.catalog.internal.MemoryCatalog;
~~~

javac forbids ordinary access because the internal package is not exported, even though the class has the public modifier.

JPMS thus lets a module **expose the API of certain packages and keep implementation packages internal**. Merely naming a package "internal" or separating build directories does not create this kind of boundary.

## 17. At what level do requires, exports, opens, and uses/provides belong?

The following directives live in the **module descriptor**:

~~~java
module com.example.app {
    requires com.example.catalog.api;
}
~~~

~~~java
module com.example.catalog.api {
    exports com.example.catalog.api;
}
~~~

A module using a reflection-based framework can open a package:

~~~java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.entity to com.example.serializer;
}
~~~

For service providers:

~~~java
module com.example.app {
    requires com.example.catalog.api;
    uses com.example.catalog.api.ProductCatalog;
}
~~~

~~~java
module com.example.catalog.memory {
    requires com.example.catalog.api;

    provides com.example.catalog.api.ProductCatalog
        with com.example.catalog.memory.MemoryCatalog;
}
~~~

Role of each directive:

- **requires** establishes a module readability dependency.
- **exports** specifies packages exposed to other modules.
- **opens** serves deep reflection at runtime.
- **uses** declares a service consumed by the module.
- **provides ... with ...** registers a provider for a service.

This information **does not live in the package declaration of individual classes**, nor does it appear automatically just because a Maven dependency is added to a POM.

## 18. Common real-world misconceptions

**"I created a new package, so I have a new module."**

False. A new package only further organizes types. To have a separate named module, you need a corresponding standalone module configuration.

**"I split the Maven project, so that's two JPMS modules."**

Not necessarily. Two projects might just produce JARs without module descriptors and run on the classpath.

**"This JAR is a module because it ends in .jar."**

Inaccurate. A JAR may be a modular JAR, an automatic module when on the module path, or merely a classpath artifact.

**"A module can only contain one package."**

False. A named module can own multiple packages, including unexported packages.

**"All public classes in a module are accessible from other modules."**

False. A public type in an unexported package does not automatically become public API across the module boundary.

**"The module name must match the Maven artifactId."**

False. An explicit module name comes from module-info.java; Maven coordinates identify the artifact for the build system.

**"Classpath and module path only differ in flag names."**

False. The module path participates in module resolution and enforces JPMS rules. The traditional classpath does not create equivalent named module boundaries.

**"module-info.java is always a standalone packaged file."**

False. The module descriptor is compiled into module-info.class and typically lives inside an exploded module or modular JAR.

## 19. How to choose module boundaries when designing a project

Consider Java modules when you want to define:

1. Which APIs are used by other parts of the system.
2. Which packages need to keep their implementations private.
3. Directional and explicitly declared dependencies between major components.
4. Features that can be released or tested as a cohesive unit.
5. Which service interfaces and providers need to connect across modules.
6. Which parts of code can change implementation without breaking consumers.

Do not split out a new module merely because a package has many classes. Splitting a module brings descriptors, module paths, dependency graphs, testing, and packaging overhead.

Too small a module can inflate the number of dependencies and complicate builds. Too large a module can export too many unnecessary packages and make encapsulation hard to maintain. Good boundaries usually follow **responsibilities and stable API contracts**, not file counts.

## 20. Checklist when inspecting a Java project structure

When taking over a repository, answer in order:

1. **Where are the build projects?** Find pom.xml, build.gradle, or build.gradle.kts.
2. **Which artifacts do the build projects produce?** Identify the actual JARs and outputs.
3. **Does the artifact have module-info.class?** Use jar --list or jar --describe-module.
4. **What is the Java module name?** Read module-info.java or the descriptor inside the JAR.
5. **Which packages does the module own?** Inspect sources and packages in the descriptor.
6. **Which packages are exported/opened?** Do not infer from the public modifier.
7. **Which other modules does the module read via requires?** Cross-check with Maven/Gradle dependencies.
8. **Does the application run via classpath or module path?** Check the actual launcher/scripts.
9. **Are there automatic or unnamed modules?** Check unmodularized dependencies.
10. **Are there split packages?** Avoid the same package existing in multiple co-used named modules.

A project can have a completely valid POM yet an invalid module graph, or a valid module graph yet a runtime script that fails to supply all required JARs. Thus, both the **build model** and the **runtime module model** must be verified.

## 21. Key takeaways

- **Package** organizes Java types into namespaces; it is not a build unit or artifact.
- **JAR** is an archive packaging code/resources; it can contain a module descriptor, but not every JAR is an explicit named module.
- **Build project** is a Maven/Gradle unit managing sources, dependencies, tasks, and artifacts.
- **Java module** is a JPMS unit with a module name, package ownership, and requires/exports/opens/uses/provides declarations.
- One Java module can contain multiple packages.
- One Java module can exist as an exploded module; it does not have to be a JAR.
- One Maven project can produce a modular JAR, and the project name and module name do not have to match.
- A **pom.xml dependency** differs from a **requires** directive.
- **public** does not cross an unexported package boundary of a named module.
- JARs on the classpath typically belong to the unnamed module; JARs without descriptors on the module path can become automatic modules.
- Splitting a package across multiple modules can cause split packages; splitting a build project does not guarantee creating a JPMS boundary.

**Conclusion:** a package answers "which namespace does this type belong to?", a JAR answers "which file is the code packaged in?", a build project answers "how is the artifact built?", and a Java module answers "which modules does this component read and which packages does it expose?". Properly distinguishing these four layers is the foundation for understanding the module path, module graph, and encapsulation design in modern Java.