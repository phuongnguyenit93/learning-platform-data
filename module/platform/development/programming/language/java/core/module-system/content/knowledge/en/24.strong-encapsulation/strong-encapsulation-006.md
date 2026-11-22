# Exporting Packages for Compile or Runtime Access

## 1. Exporting Packages in the Java Platform Module System

The Java Platform Module System (JPMS) controls which packages of a module can be accessed by other modules. A module may contain multiple public packages, but a package becomes an API usable by other modules only when the source module exports that package.

There are two phases to consider:

- **Compile time:** the compiler must allow source code to reference public types and members in the package.
- **Runtime:** the JVM must allow bytecode of the target module to access those types when the application runs.

If permission is granted at only one phase, the program may compile successfully yet fail at runtime. The **--add-exports** option can add export access at the compiler or JVM level without modifying the source module's descriptor.

This lesson focuses on access to a package's public API. If the goal is to access private fields, private methods, or constructors via deep reflection, you also need to understand **opens** and **--add-opens**.

## 2. Declaring exports in module-info.java

When you own a module's source code, the clearest approach is to declare exported packages in the module descriptor file.

Example domain module structure:

~~~text
com.acme.domain/
  module-info.java
  com/acme/domain/api/Customer.java
  com/acme/domain/internal/CustomerRepositoryImpl.java
~~~

The module-info.java file:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
}
~~~

Other modules can read public types in package com.acme.domain.api if they also read module com.acme.domain. Package com.acme.domain.internal remains hidden at the module level.

An exported package does not mean every class and member in the package becomes public. Java access rules still apply:

- A class or interface must be declared public for other modules to use it directly.
- Public members can be accessed according to language rules.
- Protected, package-private, and private members remain subject to their respective access rules.
- Exporting does not grant deep reflection permission into private members.

### 2.1. Qualified exports

If a package should only be used by specific modules, you can use a qualified export:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    exports com.acme.domain.spi to com.acme.plugin;
}
~~~

In this example, any module can access the public API in package api, but only module com.acme.plugin is permitted to access package spi under JPMS export rules.

Qualified exports are useful when a module needs to provide an SPI or internal API to a specific integration without exposing that package to the entire module graph.

The module names after the to keyword are target module names, not packages or JAR filenames. Target modules can be listed separated by commas.

## 3. --add-exports Syntax

The command-line option has the form:

~~~text
--add-exports source-module/package=target-module
~~~

You can grant export permission to multiple target modules:

~~~text
--add-exports source-module/package=target-one,target-two
~~~

Meaning of each part:

- **source-module:** the module owning the package, such as java.base or com.acme.domain.
- **package:** the full package name, such as sun.nio.ch or com.acme.domain.internal.
- **target-module:** the module that needs permission to access the package.
- **ALL-UNNAMED:** a special token representing unnamed modules, typically code loaded from the classpath.

Example exposing an internal JDK package to an application running on the classpath:

~~~bash
java --add-exports=java.base/sun.nio.ch=ALL-UNNAMED -jar app.jar
~~~

Example exposing a package to a named module:

~~~bash
java --add-exports=java.base/sun.nio.ch=com.acme.app --module-path mods --module com.acme.app/com.acme.app.Main
~~~

The source module comes before the slash. The target module comes after the equals sign. Do not reverse the two sides: this option opens the source module's package to the target module.

**ALL-UNNAMED** may only be used in the target module position. It is not the name of a source module and does not mean exporting the package to all named modules.

## 4. --add-exports at Compile Time

If source code references a public type in an unexported package, javac may report that the package is not exported or is not visible.

Example of a class attempting to use an internal JDK type:

~~~java
package com.acme.app;

import sun.nio.ch.DirectBuffer;
import java.nio.ByteBuffer;

public class InternalApiProbe {
    public static boolean isDirectBuffer(ByteBuffer buffer) {
        return buffer instanceof DirectBuffer;
    }
}
~~~

Package sun.nio.ch belongs to module java.base and is not a broadly exported API for applications. For an application on the classpath, you can instruct javac to export the package to the unnamed module:

~~~bash
javac --add-exports=java.base/sun.nio.ch=ALL-UNNAMED -d out InternalApiProbe.java
~~~

For source belonging to named module com.acme.app, the target module must be the module name:

~~~bash
javac --module-path mods --add-exports=java.base/sun.nio.ch=com.acme.app --module-source-path src -d out -m com.acme.app
~~~

This option allows the compiler to accept references to public types in that package. It does not turn the package into a stable public API and does not guarantee the code will run if the runtime lacks the corresponding export permission.

### 4.1. Note on Using --release

When javac is invoked with **--release**, the compiler uses the API and module metadata of the target Java version. javac does not allow using **--add-exports** to expand the set of packages exported from system modules in --release mode.

If the compiler rejects combining these two options, that is an intentional restriction of cross-compilation mode. Do not try to bypass the restriction by relying on implementation details of another JDK. Prefer public APIs; if the project strictly requires an internal API, explicitly select the JDK/compiler baseline and accept the compatibility risk.

## 5. --add-exports When Running the Application

Compile-time and runtime export permissions are two independent configurations. If source compiled thanks to a javac option but the JVM is not granted the corresponding permission, the program can throw **IllegalAccessError** when performing the access.

For a classpath application:

~~~bash
java --add-exports=java.base/sun.nio.ch=ALL-UNNAMED -cp out com.acme.app.InternalApiProbe
~~~

For a modular application:

~~~bash
java --add-exports=java.base/sun.nio.ch=com.acme.app --module-path mods --module com.acme.app/com.acme.app.Main
~~~

The option must be passed to the exact JVM running the application. Passing the flag to the javac command does not automatically embed the export permission into class files or JARs. Passing the flag to a build process also does not mean the production JVM will receive that flag.

If the application spawns a child JVM, the child process must have its own configuration. Parent JVM options are not automatically inherited as module permissions of the new process.

## 6. Comparing exports, --add-exports, and --add-opens

These mechanisms relate to access control but do not replace one another.

| Mechanism | Where Placed | Permission Granted |
| --- | --- | --- |
| exports package | module-info.java of source module | Exports the package to all modules under public access rules. |
| exports package to target | module-info.java of source module | Exports the package restricted to target modules. |
| --add-exports | javac or JVM | Dynamically adds export for the source module's package to the target module. |
| opens package | module-info.java of source module | Opens the package for deep reflection within the declared scope. |
| --add-opens | JVM | Adds deep reflection permission for the package and target module. |

If code needs to import a public class in an unexported package, consider **--add-exports**.

If a framework needs to read private fields, invoke private methods, or access private constructors via reflection, consider **--add-opens**.

Exporting a package does not automatically open the package for deep reflection. Conversely, opens does not allow source code to import a public type in an unexported package as a regular API.

Example:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model to com.acme.json;
}
~~~

Consumer modules can use the public API in package api. Framework com.acme.json can perform deep reflection into package model.

## 7. Distinguishing Export from Readability

For a target module to access a package of a source module, two basic conditions must be met:

1. The target module must read the source module.
2. The source module must export the package to the target module.

The **requires** directive in the module descriptor typically establishes readability. **exports** establishes package accessibility.

Example:

~~~java
module com.acme.app {
    requires com.acme.domain;
}
~~~

If com.acme.domain does not export package com.acme.domain.internal, module app still cannot reference public types in that package.

The **--add-exports** option adds export permission. It should not be understood as a general replacement for dependencies or readability. When the target module does not yet read the source module, you may need to configure **--add-reads target-module=source-module** separately, while ensuring the source module is resolved.

For classpath applications, the unnamed module can read relevant named modules in the module graph, which is why examples commonly use ALL-UNNAMED.

## 8. Configuring in Gradle and Maven

Compile options must be passed to the compiler. Runtime options must be passed to the JVM running the application or tests. These two configuration locations must be managed separately.

### 8.1. Gradle compile

With Groovy DSL and source running on the classpath:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += [
        '--add-exports=java.base/sun.nio.ch=ALL-UNNAMED'
    ]
}
~~~

If the source is a named module, replace ALL-UNNAMED with the target module name, for example:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += [
        '--add-exports=java.base/sun.nio.ch=com.acme.app'
    ]
}
~~~

Configure only the tasks that actually need access to that package. If using a toolchain or a separate compiler fork, verify that the compiler receives the right arguments.

### 8.2. Gradle runtime and test

For the Test task:

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs '--add-exports=java.base/sun.nio.ch=ALL-UNNAMED'
}
~~~

For the JavaExec task:

~~~groovy
tasks.withType(JavaExec).configureEach {
    jvmArgs '--add-exports=java.base/sun.nio.ch=ALL-UNNAMED'
}
~~~

If using the Application plugin, you can configure default JVM arguments:

~~~groovy
application {
    applicationDefaultJvmArgs = [
        '--add-exports=java.base/sun.nio.ch=ALL-UNNAMED'
    ]
}
~~~

Do not assume Test configuration also applies to JavaExec or the application distribution. Each task can launch its own JVM.

### 8.3. Maven Compiler Plugin

Example configuring compiler arguments for a classpath application:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <compilerArgs>
            <arg>--add-exports</arg>
            <arg>java.base/sun.nio.ch=ALL-UNNAMED</arg>
        </compilerArgs>
    </configuration>
</plugin>
~~~

For a named module, replace the target with the actual module name. Check the compiler plugin configuration and the JDK version running Maven.

### 8.4. Maven Surefire

To grant permission in the JVM running tests:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <argLine>--add-exports=java.base/sun.nio.ch=ALL-UNNAMED</argLine>
    </configuration>
</plugin>
~~~

If the project already has an argLine for JaCoCo or a Java agent, append the option to the existing value. Overwriting argLine can drop previously configured agents or JVM flags.

## 9. Diagnosing Compile and Runtime Access Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| javac reports package is not visible or package is not exported | Source module has not exported the package to the target module | Use exports in module-info.java or --add-exports at compile time. |
| javac does not recognize target module | Target module name is wrong or source is running on the classpath | Use the exact named module name or ALL-UNNAMED. |
| Compiles successfully but runtime throws IllegalAccessError | JVM running the application has not been granted the corresponding export | Pass --add-exports to the java command or configure the runtime task. |
| Runtime reports module does not read source module | Readability is not established or module is not resolved | Check requires, module path, and consider --add-reads where appropriate. |
| setAccessible(true) throws InaccessibleObjectException | Code needs deep reflection instead of public access | Use opens or --add-opens if deep reflection is truly needed. |
| Flag is in Gradle config but running the app still fails | Flag was passed only to the compiler or a different task | Check arguments of the exact JVM process running. |
| App works on one JDK but fails when upgrading | Code depends on an internal API that changed or became more strictly encapsulated | Replace with a public API and inspect with jdeps. |

You can use the jdeps tool to detect dependencies on JDK internal APIs:

~~~bash
jdeps --jdk-internals app.jar
~~~

The output points out the internal classes/packages referenced by the artifact. Treat this as a list of items to address during a JDK upgrade, not a list of packages to expose wholesale with --add-exports.

You can inspect a JAR's module descriptor:

~~~bash
jar --describe-module --file app.jar
~~~

This command helps confirm the module name and exported packages in the descriptor. It does not reflect dynamic exports granted by the command line at runtime.

## 10. Choosing the Right Fix

When you need access to an unexported package, choose based on ownership and purpose:

- **Module managed by the project:** declare exports or qualified exports in module-info.java.
- **Only one integration module needs the API:** use qualified exports to restrict the target module.
- **Third-party dependency or JDK module that cannot be edited:** use --add-exports at compile time and runtime if public types in that package are truly needed.
- **Private reflection needed:** use opens or --add-opens, not --add-exports as a substitute.
- **Needed only at compile time, while runtime does not need that annotation/API:** consider an appropriate compile-time dependency and avoid adding unnecessary modules at runtime.
- **Using a JDK internal API:** prioritize replacing with a public API before maintaining long-term flags.

Do not expose all internal packages broadly to ALL-UNNAMED just to make the build pass. Every flag should specify the exact source module, package, and target module needing permission. Once a dependency is upgraded and no longer needs access to that package, remove the flag and re-verify both compile and runtime.

## 11. Complete Verification Workflow

When encountering a package access error in a modular application, proceed step by step:

1. Read the error message to identify the source module, package, and target module.
2. Inspect the source module's descriptor: is the package exported, and is the export target-restricted?
3. Check whether the target module reads the source module; confirm requires and module resolution.
4. If you own the source module, choose exports or qualified exports in module-info.java.
5. If you cannot edit the source module, add --add-exports to javac to compile source needing permission.
6. Add the same export permission to the runtime JVM if bytecode will access that package when running.
7. If the actual error is deep reflection, switch to opens or --add-opens.
8. Verify the actual command line of Gradle, Maven, IDE, container, or service process.
9. Use jdeps to find internal dependencies and plan removal of unstable references.

JPMS requires both readability and package export to allow access to public types between modules. Properly distinguishing these two conditions, while configuring compile time and runtime separately, helps resolve access errors in a controlled manner without weakening module boundaries more than necessary.
