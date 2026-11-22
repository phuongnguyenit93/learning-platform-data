# Module path in Maven

The Java Platform Module System (JPMS) uses the **module path** to locate named modules during compilation, dependency resolution, and application startup. In a Maven project, the module path is closely tied to **module-info.java**, the dependencies in **pom.xml**, and the plugins that perform compilation, testing, and packaging. Understanding how these coordinate helps prevent **module not found**, **package is not visible**, package conflicts, and errors that only appear after packaging.

The core point: **Maven manages artifacts and the build lifecycle**, while **JPMS manages the module graph and accessibility between modules**. The two systems complement each other, but neither replaces the other.

## 1. How does the module path differ from the classpath?

The traditional classpath provides JARs/directories for a class loader to locate classes. When a class is loaded from the classpath, it typically belongs to the **unnamed module** of that class loader.

The module path provides JARs or directories that Java recognizes as a **named module**. Java can read the module descriptor, resolve **requires** relationships, check **exports** packages, and enforce JPMS boundaries.

| Aspect | Classpath | Module path |
|---|---|---|
| Lookup mechanism | Locates classes/resources via entries | Locates modules by name and descriptor |
| Class's module | Typically the unnamed module | Named or automatic module |
| Dependencies | Does not rely on requires | requires in module-info.java |
| Public API access | Mainly follows traditional Java access rules | Requires readability and an exported package |
| Missing module errors | May surface when using the class | May surface during module graph resolution |
| Legacy JAR libraries | Works on the classpath | Can become an automatic module |

Maven can pass dependencies to JDK tools in a manner appropriate for the project. However, an artifact existing in a Maven repository **does not automatically guarantee** it is in the runtime module graph.

## 2. A Maven module is not synonymous with a Java module

In Maven, a “module” is usually a **subproject of a reactor build**. For example, a parent POM has:

~~~xml
<modules>
    <module>catalog-api</module>
    <module>catalog-app</module>
</modules>
~~~

The two elements above are two project directories that Maven organizes to build together.

In JPMS, a module is a named unit described by **module-info.java**:

~~~java
module com.example.catalog.api {
    exports com.example.catalog.api;
}
~~~

Distinguish clearly:

- **catalog-api** can be a Maven artifactId.
- **com.example.catalog.api** is a Java module name.
- **Maven dependency** declares an artifact needed to build.
- **JPMS requires** declares a module that needs to be read.
- A Maven project without module-info.java can still be a Java project running on the classpath.
- A JAR without a descriptor on the module path can become an automatic module.

When code specifies **requires com.example.catalog.api**, the name used is the actual Java module name, not necessarily the artifactId.

## 3. When does the Maven Compiler Plugin use the module path?

A key indicator of a modular project is having the file:

~~~text
src/main/java/module-info.java
~~~

For example:

~~~java
module com.example.catalog.app {
    requires com.example.catalog.api;
}
~~~

With a JDK that supports JPMS and a compatible Maven Compiler Plugin version, a project with module-info.java is compiled in a named module context. The plugin helps organize the required artifacts for javac so the module graph can be resolved.

Important conditions:

1. The JDK used for building must support JPMS (Java 9 or later).
2. The compiler plugin must support modular projects.
3. module-info.java is in the right location and compiles cleanly.
4. Required Maven dependencies are resolved into artifacts.
5. The module name in requires matches the actual name of the dependency.
6. The API package used by code must be exported to the calling module.

You should not assume that every Maven dependency is automatically placed on the module path for every project. The actual path depends on whether the project is modular, the plugin, the JDK, and the build configuration.

## 4. Multi-module Maven project example

An application consists of two parts:

- **catalog-api** contains shared contracts.
- **catalog-app** has the main class and uses catalog-api.

Structure:

~~~text
catalog-parent/
├── pom.xml
├── catalog-api/
│   ├── pom.xml
│   └── src/main/java/
│       ├── module-info.java
│       └── com/example/catalog/api/
│           └── ProductCatalog.java
└── catalog-app/
    ├── pom.xml
    └── src/main/java/
        ├── module-info.java
        └── com/example/catalog/app/
            └── Main.java
~~~

API descriptor:

~~~java
module com.example.catalog.api {
    exports com.example.catalog.api;
}
~~~

API:

~~~java
package com.example.catalog.api;

public interface ProductCatalog {
    String findName(String sku);
}
~~~

Application descriptor:

~~~java
module com.example.catalog.app {
    requires com.example.catalog.api;
}
~~~

Main:

~~~java
package com.example.catalog.app;

import com.example.catalog.api.ProductCatalog;

public final class Main {
    public static void main(String[] args) {
        ProductCatalog catalog = sku -> "Product-" + sku;
        System.out.println(catalog.findName("A-100"));
    }
}
~~~

The app module reads the API module via requires. The API module exports the package containing ProductCatalog. These are two independent conditions: having a readability relationship and the package being exported.

## 5. Parent POM configuration

File **catalog-parent/pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>catalog-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>catalog-api</module>
        <module>catalog-app</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.14.1</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.4</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
~~~

This configuration illustrates the key ideas:

- **packaging=pom** makes the root project act as a parent/aggregator.
- **modules** lists the subprojects of the Maven reactor.
- **maven.compiler.release=17** requests compilation targeting the Java 17 platform.
- **maven-compiler-plugin** is the plugin that compiles source code.
- **maven-surefire-plugin** is used when running unit tests.
- **pluginManagement** standardizes plugin versions/configurations used across the lifecycle or declared in child projects.

The plugin versions are configuration examples. In a real project, pin versions that have been tested by the team and update them in a controlled way rather than letting plugin versions change implicitly.

## 6. POM of catalog-api

File **catalog-api/pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>catalog-parent</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>catalog-api</artifactId>
    <packaging>jar</packaging>
</project>
~~~

The source contains **module-info.java**, so the compiled output will include **module-info.class**. In a modular JAR, this file appears at the root of the JAR and defines the module name.

Maven does not automatically set the Java module name to the artifactId. In the example, the module name is taken from the descriptor **com.example.catalog.api**.

## 7. POM of catalog-app and Maven dependencies

File **catalog-app/pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>catalog-parent</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>catalog-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>catalog-api</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
~~~

In the app, two complementary declarations exist:

The POM provides the artifact:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>catalog-api</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

The module descriptor provides the readability relationship:

~~~java
module com.example.catalog.app {
    requires com.example.catalog.api;
}
~~~

Declaring a Maven dependency without requires may not be enough for code in a named module to use public APIs from another named module. Conversely, if requires is present but the POM does not supply the dependency to the compiler, a **module not found** error can occur.

## 8. Building Maven modules in the reactor

From the **catalog-parent** directory:

~~~bash
mvn clean compile
~~~

The Maven reactor builds subprojects according to their dependency relationships. In the example, catalog-api is built before catalog-app.

Output:

~~~text
catalog-api/target/classes/
├── module-info.class
└── com/example/catalog/api/ProductCatalog.class

catalog-app/target/classes/
├── module-info.class
└── com/example/catalog/app/Main.class
~~~

To build only the application and its dependencies in the reactor:

~~~bash
mvn -pl catalog-app -am clean package
~~~

- **-pl catalog-app** selects the Maven project.
- **-am** includes projects in the reactor that the selected project depends on.
- **clean package** deletes old outputs, compiles, and creates the JARs.

Running only **mvn -pl catalog-app package** can fail if the catalog-api dependency is not already available in the local repository and is not built in the same invocation.

The **-pl** option uses a Maven reactor project selector, **not** the Java module name used after **--module**.

## 9. Packaging and running via the module path

Package the entire reactor:

~~~bash
mvn clean package
~~~

Example artifacts:

~~~text
catalog-api/target/catalog-api-1.0.0.jar
catalog-app/target/catalog-app-1.0.0.jar
~~~

Run directly using the Java launcher:

~~~bash
java --module-path \
     "catalog-api/target/catalog-api-1.0.0.jar:catalog-app/target/catalog-app-1.0.0.jar" \
     --module com.example.catalog.app/com.example.catalog.app.Main
~~~

Java selects the root module **com.example.catalog.app**, reads requires in module-info.class, and then resolves **com.example.catalog.api** from the module path.

On Windows, the separator between module path entries is **;**:

~~~powershell
java --module-path "catalog-api\target\catalog-api-1.0.0.jar;catalog-app\target\catalog-app-1.0.0.jar" --module com.example.catalog.app/com.example.catalog.app.Main
~~~

On Linux/macOS, the separator is **:**. The commands above are minimal examples, sufficient only when the application has no other required module dependencies.

When distributing, ensure all runtime dependencies appear together on the module path or appropriate module sources. The Maven repository used for building is not a default module path when users launch a standalone JAR.

## 10. Checking the module name in the final artifact

After packaging, inspect the actual JAR instead of inferring from the artifact name.

~~~bash
jar --list --file catalog-api/target/catalog-api-1.0.0.jar
~~~

Expected output includes:

~~~text
module-info.class
com/example/catalog/api/ProductCatalog.class
~~~

Inspect the module descriptor:

~~~bash
jar --describe-module --file catalog-api/target/catalog-api-1.0.0.jar
~~~

The output should show the module name **com.example.catalog.api** and the exported package.

For the app:

~~~bash
jar --describe-module --file catalog-app/target/catalog-app-1.0.0.jar
~~~

The corresponding output should indicate **com.example.catalog.app** and dependency **com.example.catalog.api**.

If the Java module name differs from the name the app wrote in requires, the compiler or runtime may report an error even though the Maven dependency resolved successfully.

## 11. Automatic modules for unmodularized dependencies

Not every library in Maven Central or internal repositories has module-info.class.

For example, a legacy JAR:

~~~text
legacy-utils-2.1.jar
└── com/vendor/legacy/Util.class
~~~

If this JAR is placed on the module path, Java can recognize it as an **automatic module**. The module name may come from the **Automatic-Module-Name** manifest attribute or be derived from the JAR filename.

A descriptor might need:

~~~java
module com.example.catalog.app {
    requires com.example.catalog.api;
    requires legacy.utils;
}
~~~

The name **legacy.utils** here is only valid if that is genuinely the Java module name of the dependency.

Check:

~~~bash
jar --describe-module --file path/to/legacy-utils-2.1.jar
~~~

Do not use the artifactId as a module name without verifying it.

Automatic modules assist migration, but they export every package and have broader readability rules than explicit named modules with descriptors. They can also cause **split package** conflicts with other modules.

## 12. Maven scopes are not JPMS directives

Maven has scopes such as **compile**, **provided**, **runtime**, and **test**. Scopes determine in which build/runtime phases an artifact is needed.

JPMS, on the other hand, has directives such as:

~~~java
requires com.example.catalog.api;
requires static com.example.annotations;
requires transitive com.example.shared.api;
~~~

The two systems solve different problems:

- Maven **compile scope** typically provides the artifact for both compile and runtime.
- Maven **provided scope** is typically available at compile/test time, but is not distributed as a runtime dependency by default.
- Maven **runtime scope** serves runtime and tests rather than main source compilation.
- Maven **test scope** is for compiling/running tests.
- **requires** requires the dependency module during compile and runtime resolution.
- **requires static** requires the dependency at compile time, but allows it to be absent at runtime.
- **requires transitive** propagates module readability to modules that read the current module.

A **provided** scope dependency does not make Maven automatically generate a **requires static** directive. The development team must design declarations consistently.

If the module descriptor uses a mandatory requires while the dependency is excluded from runtime, the application can fail module resolution immediately at startup.

## 13. Specific Maven Compiler Plugin configuration

You can configure the plugin in the build:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.1</version>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

A project can use **maven.compiler.release** in properties or **release** in the plugin as two ways to configure the same intent.

Do not manually add **--module-path** parameters to compilerArgs when the compiler plugin already organizes dependencies properly. Doing so can create duplicate module paths or depend on a specific machine. Only add compilerArgs when you clearly understand the goal and interaction with the plugin.

To inspect the build configuration:

~~~bash
mvn -X clean compile
~~~

Debug mode reveals plugin details, dependencies, and compilation execution. On error, determine whether it is a Maven artifact resolution error or a JPMS module resolution error.

## 14. Module path and unit tests with Maven Surefire

In a modular project, the test runtime can differ from the compile runtime. Maven Surefire Plugin supports JPMS projects and provides the **useModulePath** option.

Example:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.5.4</version>
            <configuration>
                <useModulePath>true</useModulePath>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

When testing, consider:

- Are test classes organized as a separate module or patched into the production module?
- By what mechanism are the test framework and test engine loaded?
- Can the test module read the module containing the code under test?
- Does the test framework need reflection into packages that are not open?
- Are the modules in test dependencies included in the test execution configuration?

Test frameworks such as JUnit may use reflection to discover test classes. In JPMS, deep reflective access may require **opens** or appropriate test configuration. You should not disable the module path by default just to make tests pass if the goal is to verify a modular system.

Crucially, arguments passed to javac do not automatically appear in the test JVM launched by Maven Surefire. Configure the exact phase where they are needed.

## 15. Common runtime options

During a JPMS migration phase, additional Java options may be needed:

| Option | Purpose |
|---|---|
| **--add-reads A=B** | Adds readability from module A to B |
| **--add-exports A/p=B** | Allows module B to access public types in package p of A |
| **--add-opens A/p=B** | Opens package p of A for deep reflection from B |
| **--add-modules M** | Adds a root module for resolution |

For example, when a framework on the classpath needs deep access to a model package of a named module:

~~~bash
java --module-path dist/modules \
     --add-opens com.example.catalog.app/com.example.catalog.app.model=ALL-UNNAMED \
     --module com.example.catalog.app/com.example.catalog.app.Main
~~~

This is a syntax example; only use it when the module/app actually has the stated package and the framework needs this permission. Replace module/package names according to the real structure.

The options above do not replace Maven dependencies or requires directives. They handle JPMS-specific permissions and configuration. Whenever possible, solve the issue through module descriptors and properly exported APIs rather than maintaining long-term launcher workarounds.

## 16. Why does javac fail even when the Maven dependency is present?

A project may declare:

~~~xml
<dependency>
    <groupId>com.vendor</groupId>
    <artifactId>legacy-utils</artifactId>
    <version>2.1</version>
</dependency>
~~~

Maven finds the JAR, but the Java compiler also cares about:

1. Is the JAR on the classpath or the module path?
2. What is the Java module name of the JAR?
3. Does module-info.java have a requires for that exact name?
4. Is the package being used exported?
5. Is there a package conflict between modules?

Therefore, errors like **package is not visible** or **module not found** are not necessarily solved by re-adding the same dependency in pom.xml.

A helpful diagnostic workflow:

~~~bash
mvn dependency:tree
jar --describe-module --file path/to/dependency.jar
mvn -X compile
~~~

**dependency:tree** helps inspect Maven's artifact graph, but does not directly replace inspecting the actual Java module graph.

## 17. Split packages in a Maven modular build

If two dependencies contain the same Java package and both are used as separate modules, JPMS may encounter a conflict.

Example:

~~~text
catalog-common.jar
└── com/example/shared/Formatter.class

legacy-format.jar
└── com/example/shared/LegacyParser.class
~~~

The two JARs have different classes but share the same package **com.example.shared**. That is a split package when both become separate modules.

Maven may resolve both artifacts validly, but module resolution or module definition by the class loader may fail.

Solutions:

- Identify a single owning module for the package.
- Remove duplicate/unnecessary dependencies.
- Use an appropriately modularized library version.
- Extract shared code into a common module.
- Only use relocation/shading if you can control the classes and related metadata.

Do not add **--add-reads** or **--add-opens** expecting them to eliminate split packages: those options do not change package ownership.

## 18. Maven Shade Plugin needs careful control

In classpath applications, the Maven Shade Plugin is often used to create a fat JAR. With JPMS, merging multiple modular JARs into one JAR can lead to:

- Multiple competing module-info.class files.
- Descriptors being dropped, overwritten, or no longer reflecting the classes accurately.
- Implementation packages of multiple modules being merged together.
- Service provider metadata not being handled properly.
- Differences between classpath launch and module-path launch.

If you want to distribute a true JPMS application, prefer keeping modules distributed as separate artifacts and running with **java --module-path ... --module ...** or an appropriate runtime image.

If a project genuinely needs a fat JAR, you must explicitly determine whether it is still run as a named module or switched to the classpath mechanism, and then inspect the shaded artifact. Do not assume the shaded output remains modular just because the input sources had module-info.java.

## 19. Verifying dependencies with jdeps

The JDK provides **jdeps** to analyze dependencies between classes/JARs and evaluate modularization.

Example:

~~~bash
jdeps --module-path \
      "catalog-api/target/catalog-api-1.0.0.jar:catalog-app/target/catalog-app-1.0.0.jar" \
      --module com.example.catalog.app
~~~

You can use jdeps with the constructed module path to inspect static dependencies. This tool assists verification, but does not replace running the actual application.

Some dependencies only appear when using reflection, reading configuration, using ServiceLoader, or calling Class.forName. Static analysis may not detect all of those dependencies.

To verify a release, combine:

- Inspecting JARs and module-info.class.
- Verifying actual module names.
- Checking dependencies with jdeps.
- Running the Java command with the exact runtime module path.
- Running unit tests/integration tests in a production-like configuration.

## 20. Common errors and troubleshooting

### module not found

The compiler or launcher cannot find a module listed in requires or root selection. Verify that the dependency JAR exists, check the Java module name, and check the module path entries.

### package ... is not visible

The source module may not read the target module, or the target package is not exported. Distinguish readability from package accessibility.

### class not found at runtime

The library may have been present during the Maven build but was not distributed on the runtime module path/classpath. Check startup scripts, dependency scopes, and actual artifacts.

### Tests compile but Surefire fails

The test JVM may use a different module path, class loader, or reflection permissions. Check Surefire configuration, test dependencies, and required module opens.

### Java module name differs from artifactId

Do not infer the module name from Maven coordinates. Use **jar --describe-module** to confirm.

### Automatic module exposes internal packages

An automatic module exports all packages. If selective encapsulation is required, use a modular JAR with an explicit descriptor.

### Build passes locally but fails on CI

Check the JDK, Maven version, Maven Wrapper, plugin versions, test configuration, and module path entries on each operating system. Avoid hardcoding path separators or developer machine directories in the POM.

## 21. Practical implementation checklist

For a Maven project using JPMS:

1. Choose a Java release version consistent with the pipeline's JDK.
2. Manage versions of the Maven Compiler Plugin and Surefire Plugin.
3. Add **module-info.java** to projects intended to be named modules.
4. Declare dependencies in **pom.xml** so Maven can locate artifacts.
5. Declare **requires** using the exact Java module names.
6. Export the right API packages; keep implementation packages unexported.
7. Check for automatic modules and split packages among dependencies.
8. Build the reactor with **mvn clean package** or select projects via **-pl ... -am**.
9. Inspect artifacts with **jar --describe-module**.
10. Run the application via the module path on the actual packaged JARs.
11. Configure Surefire and appropriate reflection permissions for tests.
12. Run integration tests in an environment close to the deployment runtime.
13. Update distribution scripts when new dependencies/modules are added.
14. Remove --add-reads/--add-exports/--add-opens workarounds once no longer needed.

A successful Maven build only proves that the build lifecycle ran to completion; it is not enough to guarantee the production module path is right. Final verification must be based on the actual JARs and run commands.

## 22. Key takeaways

- **Classpath** is used for the traditional class loader model; **module path** provides named/automatic modules to JPMS.
- A Maven reactor module is not automatically a Java module.
- **module-info.java** is the primary component that helps the compiler recognize a named module.
- A Maven dependency provides an artifact; the **requires** directive represents a readability relationship in JPMS.
- A Maven artifactId does not necessarily match the Java module name.
- **maven.compiler.release** or compiler plugin **release** must match the JDK used.
- Maven Compiler Plugin and Maven Surefire Plugin handle different phases; test runtime configuration may differ from compilation.
- Maven dependency scopes do not automatically become requires or requires static directives.
- A JAR without a descriptor on the module path can become an automatic module.
- Fat JARs/shading can break module boundaries unless specifically designed for it.
- Use **jar --describe-module**, **jdeps**, and **java --module-path** commands to verify release artifacts.

In summary, the module path in Maven is the intersection between Maven's artifact management and JPMS's module graph. For a reliable modular application, keep **pom.xml** and **module-info.java** consistent, configure compilation/testing compatibly with the JDK, and verify results against the exact JARs that will actually be deployed.
