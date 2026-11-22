# Incremental compilation in Java

Incremental compilation is a way of rebuilding only the affected parts of the source code after a change, instead of recompiling the entire project on every edit. For Java projects with thousands of classes, this approach helps shorten the edit, compile, and test loop.

However, determining which parts need to be recompiled requires understanding the dependency relationships between classes. A change confined to a method body typically has less impact than a change to a public signature, superclass, interface, or compile-time constant. If a dependent class is missed, the build may succeed, but the program will run with stale bytecode and encounter linkage errors or produce outdated results.

## 1. Full compilation and incremental compilation

**Full compilation** compiles the entire set of source files in a module or project according to the current build configuration. This approach takes longer on large projects, but it is reproducible and useful when verifying a clean state.

**Incremental compilation** recompiles only the compilation units that have changed and those that need to be updated because their dependencies have changed. A compilation unit is typically a Java source file compiled as a single unit.

For example, suppose a project has three classes:

- TaxPolicy calculates tax.
- Invoice calls TaxPolicy to calculate the invoice total.
- App calls Invoice and prints the result.

If only the formula inside TaxPolicy changes while keeping the method name, parameter types, and return type unchanged, the classes that call it generally do not need to be recompiled. If the method signature changes, Invoice may need to be recompiled because its bytecode invokes the method using the old descriptor.

| Type of change | Typical recompilation scope required |
|---|---|
| Editing comments or whitespace | No recompilation needed from a bytecode perspective if the build tool detects a non-impacting change; the tool may still recompile the modified file. |
| Editing a method body while keeping the API | Usually only the modified class needs to be recompiled. |
| Changing a public method signature | Recompile the modified class and dependent source classes that use that signature. |
| Changing a superclass or interface | Can affect subclasses, implementing classes, and related call sites. |
| Changing a compile-time constant | Dependent classes consuming the constant must be recompiled because the value may have been inlined into their bytecode. |
| Changing dependencies, compiler options, or module descriptors | May invalidate compilation outputs for many classes or the entire module. |

These are general guidelines. The exact set of classes that need recompilation depends on the nature of the change, how the code is used, and the build tool's dependency analysis capabilities.

## 2. What javac does and does not do

Javac is a compiler. It takes the source files and options of the current invocation, performs type checking, resolves dependencies, and generates bytecode.

Javac can locate additional referenced source files via the source path if those files were not provided directly. For example:

~~~bash
javac -sourcepath src/main/java -d out src/main/java/com/acme/app/App.java
~~~

In this invocation, javac can find and compile the source files needed to resolve App.

This mechanism of finding and compiling dependent sources in a single invocation **is not the same as a complete incremental build system**. Javac itself does not persistently manage the full build history, the project's dependency graph, output caching across runs, or test execution policies. Tools like Gradle, Maven, and IDEs orchestrate those responsibilities by tracking inputs, outputs, and dependency relationships.

You can invoke javac manually to compile a known set of sources. However, as a project grows, manually deciding which dependent classes need recompilation is error-prone. Use a build tool with dependency analysis to perform incremental compilation consistently.

## 3. Example: recompiling only the class with an implementation change

Create the project structure:

~~~text
incremental-demo/
├── src/main/java/
│   ├── com/acme/pricing/
│   │   ├── TaxPolicy.java
│   │   └── Invoice.java
│   └── com/acme/app/
│       └── App.java
└── out/
~~~

File src/main/java/com/acme/pricing/TaxPolicy.java:

~~~java
package com.acme.pricing;

public class TaxPolicy {
    public int taxFor(int subtotal) {
        return subtotal / 10;
    }
}
~~~

File src/main/java/com/acme/pricing/Invoice.java:

~~~java
package com.acme.pricing;

public class Invoice {
    private final TaxPolicy policy = new TaxPolicy();

    public int totalFor(int subtotal) {
        return subtotal + policy.taxFor(subtotal);
    }
}
~~~

File src/main/java/com/acme/app/App.java:

~~~java
package com.acme.app;

import com.acme.pricing.Invoice;

public class App {
    public static void main(String[] args) {
        System.out.println(new Invoice().totalFor(100));
    }
}
~~~

### Initial build

From the incremental-demo root directory, create the output directory and compile all three files:

~~~bash
mkdir -p out

javac -d out \
  src/main/java/com/acme/pricing/TaxPolicy.java \
  src/main/java/com/acme/pricing/Invoice.java \
  src/main/java/com/acme/app/App.java

java -cp out com.acme.app.App
~~~

Output:

~~~text
110
~~~

TaxPolicy calculates tax as 10% of the subtotal, so the total for 100 is 110.

### Changing only the implementation

Suppose the tax policy changes to 20%, while the method keeps the same signature:

~~~java
package com.acme.pricing;

public class TaxPolicy {
    public int taxFor(int subtotal) {
        return subtotal / 5;
    }
}
~~~

The method name is still taxFor, the parameter is still int, and the return type is still int. Only the method body changed.

You can recompile only TaxPolicy, using out as the classpath so javac can find the compiled classes it needs:

~~~bash
javac -cp out -d out src/main/java/com/acme/pricing/TaxPolicy.java

java -cp out com.acme.app.App
~~~

New output:

~~~text
120
~~~

Invoice.class and App.class remain valid because the binary contract they call has not changed. At runtime, the JVM loads the new TaxPolicy.class, so the result is updated.

This example illustrates the benefit of incremental compilation. It also assumes that the change only affects the implementation and does not alter behavior that callers rely on under a different contract.

## 4. Why API changes require recompiling dependent classes

The bytecode of a calling class contains information about the methods it invokes, including each method's name and descriptor. A descriptor specifies the parameter types and return type at the JVM level.

Suppose TaxPolicy initially has:

~~~java
public int taxFor(int subtotal) {
    return subtotal / 5;
}
~~~

The compiled Invoice class references a method that takes an int and returns an int. If you change the method to:

~~~java
public int taxFor(long subtotal) {
    return (int) (subtotal / 5);
}
~~~

The method descriptor has changed. If you only compile the new TaxPolicy while keeping the old Invoice.class, Invoice will still attempt to call the method with the old descriptor. At runtime, the JVM may throw:

~~~text
java.lang.NoSuchMethodError
~~~

You need to recompile the affected dependent classes:

~~~bash
javac -cp out -d out \
  src/main/java/com/acme/pricing/TaxPolicy.java \
  src/main/java/com/acme/pricing/Invoice.java \
  src/main/java/com/acme/app/App.java
~~~

The command above is a conservative way to refresh all three classes in the example. In large projects, build tools analyze dependencies to recompile only the necessary classes.

Several other changes can also alter the ABI or affect consuming code:

- Adding, removing, or changing the type of methods and fields used elsewhere.
- Changing the superclass or implemented interfaces.
- Changing visibility/accessibility so that callers can no longer access a member.
- Changing generic signatures, which can prevent dependent source code from compiling even if the post-type-erasure descriptor has not changed.
- Changing a module descriptor, such as exports or requires, which alters module readability and accessibility.

You should not judge impact merely by looking at whether a method body changed. You need to consider the contract that other classes compile against.

## 5. Compile-time constants and inlined bytecode values

One easily overlooked case is compile-time constants. For example:

~~~java
package com.acme.config;

public class AppConfig {
    public static final int RETRY_LIMIT = 3;
}
~~~

Consuming class:

~~~java
package com.acme.app;

import com.acme.config.AppConfig;

public class RetryJob {
    public static void main(String[] args) {
        System.out.println(AppConfig.RETRY_LIMIT);
    }
}
~~~

During compilation, the value of a qualifying compile-time constant can be inlined directly into the bytecode of the consuming class. If you change RETRY_LIMIT from 3 to 5 and recompile only AppConfig, the old RetryJob.class may still continue to print 3.

Therefore, when a compile-time constant changes, you must recompile the classes that consume it. This is an important reason why build tools track dependencies at a deeper level than simply checking whether a class name exists.

Not every static final field is a compile-time constant. This behavior applies to constant variables as defined by Java, such as final variables of primitive or String type initialized with a constant expression.

## 6. Dependency graph and invalidation scope

Build tools can model classes or compilation units as a dependency graph. An edge from A to B means A depends on B during compilation or usage.

For example:

~~~text
App
 |
 v
Invoice
 |
 v
TaxPolicy
~~~

When TaxPolicy changes:

- If only the implementation changes while the API stays the same, Invoice and App usually do not need to be recompiled.
- If an API used by Invoice changes, Invoice must be recompiled; classes that depend on Invoice's API may also need to be updated.
- If a shared foundational component changes, the impact can propagate across multiple modules.

An incremental compiler must determine the **invalidation set**: the set of outputs that can no longer be trusted after inputs change. The build tool then recompiles the corresponding source files and updates its dependency analysis results.

The invalidation scope does not necessarily span the entire dependency tree in every direction. Many build tools can perform ABI analysis to avoid recompiling callers when only an implementation body changes. The exact analysis depends on the tool, compiler, language, and project configuration.

## 7. Gradle and incremental Java compilation

Gradle supports incremental compilation for JavaCompile tasks. Gradle tracks task inputs and can use classpath/ABI analysis to determine which classes need to be recompiled when source code or dependencies change.

Example configuration of a Java toolchain and compile task:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.incremental = true
    options.compilerArgs += ['-Xlint:all']
}
~~~

In this example, the toolchain selects JDK 17 for Java tasks that support toolchains. Configuring incremental instructs Gradle to use incremental compilation mode for JavaCompile tasks. Gradle may decide to perform a partial or full recompilation depending on the changes, analysis state, and supporting conditions.

Run the compile task:

~~~bash
./gradlew compileJava
~~~

On Windows:

~~~powershell
.\gradlew.bat compileJava
~~~

To view more details about tasks and execution, you can use:

~~~bash
./gradlew compileJava --info
~~~

Incremental compilation does not mean every task run will compile only a single file. Changes to compiler configuration, JDK, classpath, annotation processors, or build state can cause Gradle to recompile a broader scope.

Gradle also supports incremental annotation processing when a processor declares the appropriate processing type and satisfies Gradle's contract. Isolating processors produce outputs tied to individual inputs; aggregating processors can combine information from multiple inputs. Processors that do not declare support or fail to meet the incremental contract can force the compilation to fall back to a broader strategy.

## 8. Maven and incremental compilation

Maven organizes builds around lifecycles and plugins. The Maven Compiler Plugin invokes the Java compiler with the sources and options configured in the project.

Example configuration of Java version and compiler arguments:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <release>17</release>
        <compilerArgs>
            <arg>-Xlint:all</arg>
        </compilerArgs>
    </configuration>
</plugin>
~~~

Run compile:

~~~bash
mvn compile
~~~

Exact recompilation behavior depends on the Maven Compiler Plugin version, the selected compiler, the incrementalCompilation configuration, and the inputs tracked by the plugin. Do not assume that Maven and Gradle use the same incremental compilation algorithm or the same ABI analysis.

When you need to verify that the entire project can build from a clean output state, use:

~~~bash
mvn clean compile
~~~

The clean phase removes previous build outputs according to the project lifecycle, and then compile regenerates the outputs. This is a useful check after changing dependencies, compiler plugins, annotation processors, or build configuration.

## 9. Annotation processing and generated source code

Annotation processors can generate additional .java files or resources during compilation. For example, a processor might generate mappers, metadata, or helper classes from annotations in the source code.

This makes incremental compilation more complex because the inputs to a compilation are not limited to developer-written Java files. When an annotation changes, the processor may need to re-run and generate different classes. A processor that aggregates information from multiple classes may produce different outputs whenever any of those classes change.

Keep in mind:

- A processor can generate sources that depend on one or more compilation units.
- Changing a processor or processor path can invalidate previously generated outputs.
- Deleting a source class may require deleting the files generated from it.
- Processors without incremental support can force the build tool to recompile more broadly.
- You should not edit generated source files directly if they will be regenerated on the next build.

Configure annotation processors through your build tool and store generated sources in a dedicated build directory. This separates hand-written sources from automatically generated ones and reduces the risk of leaving stale generated files behind.

## 10. Deleting classes and stale output

Incremental compilation does not only need to know which files to recompile. It also needs to handle old outputs that no longer correspond to the current sources.

For example, if you delete:

~~~text
src/main/java/com/acme/legacy/OldService.java
~~~

then the file:

~~~text
out/com/acme/legacy/OldService.class
~~~

may remain on disk if the build tool does not remove the corresponding output. Such a leftover class can allow the program to still load code that was removed from the source tree, leading to confusing build results.

This is called stale output. Similar situations can occur when renaming classes, moving packages, deleting resources, or changing generated code.

Build tools need to track task outputs so they can delete files that are no longer produced. If you use javac manually, cleaning the output directory may need to be done explicitly.

On Linux/macOS, in the example project you can remove the output directory before a full build:

~~~bash
rm -rf out
mkdir -p out
~~~

On PowerShell:

~~~powershell
if (Test-Path out) {
    Remove-Item out -Recurse -Force
}
New-Item -ItemType Directory -Force out | Out-Null
~~~

Only perform deletion operations on a known project build directory. Never run recursive delete commands on unverified paths.

## 11. Changes that can invalidate incremental state

Build tools often need to recompile more broadly when one of the foundational inputs changes:

- JDK or compiler version.
- Compiler arguments such as --release, -encoding, -parameters, or lint options.
- Classpath, module path, or library versions.
- Module descriptors and requires/exports relationships.
- Annotation processors, processor path, or annotation processing configuration.
- Source set, source root, or generated source directory configuration.
- Build scripts, plugins, or task configuration.
- Missing, corrupted, or incompatible cache/analysis state.

These changes can affect how javac analyzes code or how the build tool determines dependencies. When incremental state cannot be verified, the build tool may run a full compilation to guarantee correctness.

## 12. Incremental compilation does not replace testing

A successful compilation only verifies the compile-time conditions checked by the compiler. It does not prove that business logic is correct or that the program behaves properly for all inputs.

An implementation change can preserve the API while altering calculation results. For example, changing the tax rate in TaxPolicy does not force Invoice to be recompiled, but testing is still required to verify that the new business behavior is correct.

You should separate these activities:

1. **Incremental compile:** verify and regenerate bytecode for the affected parts.
2. **Unit test:** verify the behavior of the changed class or component.
3. **Integration test:** verify that classes and modules work together properly.
4. **Full clean build:** verify that the entire project can be built from scratch.
5. **Packaging/deployment test:** verify that the final artifact contains the expected classes, resources, and dependencies.

Depending on the risk of a change, CI can run relevant tests quickly during the development loop while still running a broader test suite before merging or releasing.

## 13. Common issues when using incremental compilation

| Symptom | Common cause | Resolution |
|---|---|---|
| Running the program still shows old results | The class with modified logic was not recompiled, or runtime is using a different output directory. | Check the output directory and classpath; verify the timestamp/contents of the new class. |
| NoSuchMethodError after changing an API signature | The calling class still contains bytecode referencing the old descriptor. | Recompile dependent source classes or run a clean build. |
| NoClassDefFoundError after moving a package | The old output class was deleted, or the classpath/module path no longer points to the right location. | Check the package, output tree, and runtime path. |
| A deleted class can still run | An old .class file remains in the output directory. | Run a clean build or delete managed outputs and recompile. |
| Gradle/Maven compiles more than expected | Changes to classpath, compiler options, processors, or build state caused broad invalidation. | Inspect task logs, check dependencies, and review compiler configuration. |
| Incremental build succeeds but clean build fails | Stale outputs are masking a missing dependency or missing generated class. | Run a clean build and fix dependency/processor/output declarations. |
| IDE and CI produce different results | Differences in JDK, compiler options, source roots, or build tool configuration. | Align project configurations and verify using the official build command. |

## 14. Recommended workflow

When modifying a Java project, you can follow this workflow:

1. Identify the classes and modules being changed.
2. Determine whether the change is confined to the implementation or alters the API/ABI.
3. Check dependent classes, modules, generated sources, and resources.
4. Run an incremental compile through your build tool for fast feedback.
5. Run tests appropriate for the change.
6. If you changed dependencies, compiler options, processors, or build scripts, check the invalidation scope and run a broader build.
7. Run a clean build before integrating or releasing when you need to verify reproducibility.
8. If an incremental build and a clean build produce different results, investigate stale outputs, undeclared dependencies, or invalid caches.

Incremental compilation saves time, but it is only reliable when dependencies and outputs are managed accurately. Let your build tool track inputs and dependency relationships, understand when an implementation change can leave consumer bytecode intact, and recognize when API or configuration changes require broader recompilation. Combining incremental builds with testing and clean builds gives you both a fast development loop and reliable Java artifacts.
