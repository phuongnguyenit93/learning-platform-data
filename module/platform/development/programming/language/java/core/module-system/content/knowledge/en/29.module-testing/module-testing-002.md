# Testing module-info.java and requires static

The Java Platform Module System (JPMS) uses **module-info.java** to describe a module: which modules it depends on, which packages are exported or opened, and which services it uses or provides. Because the descriptor determines how a program compiles and runs, JPMS testing should not rely solely on unit tests of business classes. You should also verify the **module contract** and dependency resolution behavior across different runtime configurations.

An important case is **requires static**: a dependency that is mandatory when compiling the module, yet optional at runtime. If tests only run with all dependencies present, it is easy to miss that a module still accidentally depends on a library intended to be optional.

This article walks through building a small modular example, inspecting **module-info.java** after compilation, and writing both positive tests and intentional failure tests for **requires static**.

## 1. What Needs to Be Tested in module-info.java?

Directives in the descriptor express the contract between a module and the rest of the application:

| Directive | Meaning | Testing Approach |
|---|---|---|
| **requires m;** | Mandatory dependency; module m must be resolved at runtime. | Running without m must fail during module resolution. |
| **requires transitive m;** | Propagates readability of m to modules that read the current module. | Compile an external consumer module and verify readability. |
| **requires static m;** | Mandatory dependency at compile time, optional at runtime. | Compiling without m must fail; running without m still starts if code does not need m. |
| **exports p;** | Exposes public API in package p. | External consumer can import allowed API, cannot import internal packages. |
| **exports p to m;** | Exposes package p only to module m. | Consumer m can use it; another module is denied access. |
| **opens p;** | Opens package p for deep reflection. | Runtime caller can perform appropriate reflection. |
| **opens p to m;** | Opens p only to module m. | Test reflection from module m and from an unauthorized module. |
| **uses S;** | Module consumes service S. | Check descriptor and ServiceLoader in the consumer module. |
| **provides S with P;** | Module registers provider P of service S. | Check descriptor and provider discovery/instantiation. |

A test may focus on only part of the contract, but it must distinguish outcomes from the **compiler**, **module resolver**, and **class loader**. These three layers can fail for different reasons.

## 2. What Are the Exact Semantics of requires static?

Descriptor:

~~~java
module com.acme.app {
    requires static com.acme.annotations;
}
~~~

There are two situations to understand:

**At compile time:** the **com.acme.annotations** module must be observable and resolved so javac can check the types referenced by the application module. A missing dependency causes module compilation to fail.

**At runtime:** a dependency declared with **requires static** does not have to be present in the module configuration. The application can start without that module, provided the execution path does not require the omitted runtime types or functionality.

Compare with regular **requires**:

~~~java
module com.acme.app {
    requires com.acme.annotations;
}
~~~

If changed to regular **requires**, missing **com.acme.annotations** at runtime causes root module resolution to fail, even if **main** never calls the dependency's API.

**requires static** does not automatically provide a fallback implementation. If code actually loads a class from the optional dependency when the dependency is absent, it can still encounter **ClassNotFoundException**, **NoClassDefFoundError**, or class linking errors. Designing the optional execution path is the application's responsibility.

## 3. Example: Compile-Only Annotations Module

Suppose there are two modules:

~~~text
src/
  com.acme.annotations/
    module-info.java
    com/acme/annotations/ApiMarker.java
  com.acme.app/
    module-info.java
    com/acme/app/CompileTimeModel.java
    com/acme/app/Main.java
~~~

Annotation module:

~~~java
// src/com.acme.annotations/module-info.java
module com.acme.annotations {
    exports com.acme.annotations;
}
~~~

Annotation definition:

~~~java
// src/com.acme.annotations/com/acme/annotations/ApiMarker.java
package com.acme.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
public @interface ApiMarker {
}
~~~

**RetentionPolicy.CLASS** allows the annotation to appear in class files without being retained for runtime reflection via the Java reflection API. It is appropriate for an example annotation that supports compiler tools or bytecode processing without the application needing it directly at runtime.

App descriptor:

~~~java
// src/com.acme.app/module-info.java
module com.acme.app {
    requires static com.acme.annotations;
}
~~~

Class using the annotation:

~~~java
// src/com.acme.app/com/acme/app/CompileTimeModel.java
package com.acme.app;

import com.acme.annotations.ApiMarker;

@ApiMarker
public final class CompileTimeModel {
}
~~~

Main does not depend on the annotation at runtime:

~~~java
// src/com.acme.app/com/acme/app/Main.java
package com.acme.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Modular application started successfully");
    }
}
~~~

This example has a specific goal: **javac requires the annotations module at compile time**, while **Main** can run even when the annotations module is not provided at runtime.

In real projects, you must examine every class loaded along the execution path, especially when annotations have **RUNTIME** retention, when frameworks read annotations via reflection, or when public method signatures mention types from an optional dependency.

## 4. Compiling Both Modules

With the **src** structure above, you can compile into the **mods** directory:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.acme.annotations,com.acme.app
~~~

Compilation command in multi-module mode:

- **--module-source-path src**: tells javac the module-named source structure.
- **-d mods**: specifies the output directory.
- **-m**: selects the source modules to compile.

After compilation, the main structure looks like:

~~~text
mods/
  com.acme.annotations/
    module-info.class
    com/acme/annotations/ApiMarker.class
  com.acme.app/
    module-info.class
    com/acme/app/CompileTimeModel.class
    com/acme/app/Main.class
~~~

You can inspect the app module's metadata after packaging. Example packaging both modules:

~~~bash
jar --create \
    --file com.acme.annotations.jar \
    -C mods/com.acme.annotations .

jar --create \
    --file com.acme.app.jar \
    --main-class com.acme.app.Main \
    -C mods/com.acme.app .
~~~

The **--main-class** option records the main class in module metadata when packaging a modular JAR. If this metadata is not used, you can still run by explicitly specifying the main class after the slash in **-m**.

## 5. Positive Compile Test: Dependency Present

The first verification step is confirming the project compiles successfully when the optional module is present at compile time.

The example compiled both modules from source:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.acme.annotations,com.acme.app
~~~

If the annotation module does not export the **com.acme.annotations** package, the app cannot import **ApiMarker** even if the module is on the module path.

Therefore, the positive test simultaneously verifies:

1. The dependency module exists within compilation scope.
2. The name in **requires static** matches the actual module name.
3. The app module is permitted to read the dependency at compile time.
4. The annotation package is exported to the app module.
5. Source code using the annotation compiles successfully.

If a test merely checks that the source contains the string **requires static**, it does not verify these conditions. For solid evidence, let javac actually compile the consumer module.

## 6. Negative Compile Test: Missing Dependency Must Fail

This is the second half of the **requires static** contract. An optional dependency is **only optional at runtime**, not optional at compile time.

To test this, compile only the app module in a command where the annotation module is neither on the module path nor provided via module-source-path:

~~~bash
mkdir -p empty-module-path

javac --module-path empty-module-path \
      -d negative-build \
      src/com.acme.app/module-info.java \
      src/com.acme.app/com/acme/app/Main.java \
      src/com.acme.app/com/acme/app/CompileTimeModel.java
~~~

The command above is expected to fail with a diagnostic similar to:

~~~text
module not found: com.acme.annotations
~~~

The reason is not that **Main** needs the annotation at runtime. The reason is that the descriptor requires **com.acme.annotations** to compile the app module.

For CI, check:

- **javac** exit code is non-zero.
- The diagnostic mentions that module **com.acme.annotations** was not found, rather than a syntax error or wrong source path.

Example Bash script illustrating expected failure:

~~~bash
set +e
javac --module-path empty-module-path \
      -d negative-build \
      src/com.acme.app/module-info.java \
      src/com.acme.app/com/acme/app/Main.java \
      src/com.acme.app/com/acme/app/CompileTimeModel.java \
      > negative-compile.log 2>&1
code=$?
set -e

if [ "$code" -eq 0 ]; then
    echo "FAIL: compilation without com.acme.annotations still succeeded"
    exit 1
fi

grep -q "com.acme.annotations" negative-compile.log || {
    echo "FAIL: error is unrelated to the module dependency"
    exit 1
}
~~~

Do not mark the test as passed just because javac produced any error. If the fixture is broken or the command didn't run properly, the test proves nothing about **requires static** semantics.

## 7. Runtime Test: Dependency Absent Yet App Still Runs

After successful compilation, copy **only the app module** into a dedicated module path for the runtime test.

Linux/macOS:

~~~bash
mkdir -p runtime-only
cp -R mods/com.acme.app runtime-only/
~~~

Run:

~~~bash
java --module-path runtime-only \
     --show-module-resolution \
     -m com.acme.app/com.acme.app.Main
~~~

Expected output from **Main**:

~~~text
Modular application started successfully
~~~

The **com.acme.annotations** module is absent from **runtime-only**, yet the app is allowed to start because the dependency was declared **requires static**.

To avoid confusion between the classpath and module path, use **-m** to run the named module. Also keep a separate runtime test directory instead of reusing the **mods** output containing both modules.

On Windows PowerShell, you can copy the module with:

~~~powershell
New-Item -ItemType Directory -Force -Path runtime-only
Copy-Item -Recurse -Path mods/com.acme.app -Destination runtime-only/
java --module-path runtime-only -m com.acme.app/com.acme.app.Main
~~~

This is a critical test because it proves the runtime contract: **requires static does not turn a compile-time dependency into a mandatory runtime dependency**.

## 8. Runtime Test: Dependency Present

You should also test an environment where the optional module is present. For example:

~~~bash
java --module-path mods \
     --add-modules com.acme.annotations \
     --show-module-resolution \
     -m com.acme.app/com.acme.app.Main
~~~

Here:

- The **com.acme.annotations** module is present on the module path.
- **--add-modules com.acme.annotations** actively requests adding this module to the root set during resolution.
- The app still declares **requires static**, so it can use the dependency if it gets resolved in the runtime configuration.

Do not confuse **a JAR being on the module path** with **a module definitely being resolved**. For a static dependency, merely having the module in the path does not guarantee any of its code participates in the module graph. If the application wants to use an optional feature at runtime, you must design a way to ensure the right module is resolved, such as selecting appropriate root modules or configuring service binding properly.

You can print the status to observe it:

~~~java
package com.acme.app;

public final class Main {
    public static void main(String[] args) {
        boolean available = ModuleLayer.boot()
            .findModule("com.acme.annotations")
            .isPresent();

        System.out.println("Optional module resolved: " + available);
    }
}
~~~

With **runtime-only**, the expected output is **false**. With the command using **--add-modules com.acme.annotations**, the expected output is **true**.

The fact that the module is resolved does not imply the application must directly access the annotation via reflection. These are two separate aspects: the module graph and the program's business logic.

## 9. Testing the Descriptor with ModuleDescriptor

Beyond compile and runtime tests, inspect the compiled descriptor directly to confirm the dependency did not accidentally change from static to mandatory.

The **java.lang.module.ModuleFinder** API lets you locate modules in artifacts:

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;

public final class DescriptorTest {
    public static void main(String[] args) {
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

        ModuleReference ref = finder.find("com.acme.app")
            .orElseThrow(() ->
                new AssertionError("com.acme.app not found"));

        ModuleDescriptor descriptor = ref.descriptor();

        ModuleDescriptor.Requires dependency = descriptor.requires()
            .stream()
            .filter(r -> r.name().equals("com.acme.annotations"))
            .findFirst()
            .orElseThrow(() ->
                new AssertionError("Missing requires com.acme.annotations"));

        boolean isStatic = dependency.modifiers()
            .contains(ModuleDescriptor.Requires.Modifier.STATIC);

        if (!isStatic) {
            throw new AssertionError(
                "Dependency turned into a mandatory runtime requires"
            );
        }

        System.out.println("Static dependency contract preserved");
    }
}
~~~

This is a structural test of the module descriptor, requiring no business class loading. It verifies:

- Module **com.acme.app** exists in the artifact under test.
- **requires com.acme.annotations** is actually present in the descriptor.
- The dependency has the **STATIC** modifier.

If you want to verify the exact contract, you can also check the **TRANSITIVE** modifier and the **exports**, **opens**, **uses**, and **provides** directives against the project's allowlist.

Note: **ModuleDescriptor.requires()** may include a **java.base** dependency with the **MANDATED** modifier added by JPMS. Do not assume every entry in the **requires()** set was written directly in the **module-info.java** source.

## 10. Testing from the Final Modular JAR

To ensure the release artifact genuinely preserves the descriptor, inspect the modular JAR after packaging:

~~~bash
jar --describe-module --file com.acme.app.jar
~~~

The tool prints the module name and directives. When reviewing the output, locate the **com.acme.annotations** dependency and confirm it is marked static. Text formatting may vary across JDKs, so for automated tests prefer the **ModuleDescriptor** API instead of relying solely on CLI text output.

Inspect JAR contents:

~~~bash
jar --list --file com.acme.app.jar
~~~

Ensure it includes:

~~~text
module-info.class
com/acme/app/Main.class
com/acme/app/CompileTimeModel.class
~~~

If **module-info.class** is lost during packaging, the artifact may be treated as an automatic module when placed on the module path. Automatic modules have broad export/open semantics and a different dependency graph than explicit modules. A test that only runs business code on the classpath may fail to detect this discrepancy.

Verify the module kind using the descriptor:

~~~java
if (descriptor.isAutomatic() || descriptor.isOpen()) {
    throw new AssertionError(
        "Artifact is no longer an explicit closed module per policy"
    );
}
~~~

Here, the example policy requires a non-open explicit module. Another project might allow open modules, but that should be decided upfront rather than letting unintended changes slip by.

## 11. requires static Does Not Protect Code from Runtime Errors If the Dependency Is Used

A common misconception is that a dependency marked static is always safe when missing at runtime. In reality, only **module resolution** permits its absence; the JVM still needs the corresponding class if an execution path actually uses a type from the dependency.

Suppose:

~~~java
package com.acme.app;

import com.acme.annotations.ApiMarker;

public final class OptionalFeature {
    public static Class<?> markerType() {
        return ApiMarker.class;
    }
}
~~~

When **com.acme.annotations** is absent at runtime, code calling **OptionalFeature.markerType()** can fail during class loading or linking because the reference to **ApiMarker** cannot be resolved.

Therefore, when using **requires static** for an optional library that actually provides runtime functionality, you must:

1. Place code using the dependency behind a branch that runs only when the feature is enabled and the dependency is present.
2. Avoid having the main class, static initializers, or public API force resolution of optional types immediately at application startup.
3. Consider isolating an adapter for the optional dependency into its own module if the boundary is complex.
4. Test both **without the dependency** and **with the dependency** in fresh JVMs with controlled module paths.

In particular, if an annotation has **RUNTIME** retention and a framework needs to read it for business processing, the annotation module is no longer purely compile-only. In that case, include the appropriate dependency at runtime and test the actual processing.

## 12. Distinguishing requires static and requires transitive

The two modifiers address two different needs.

**requires static** allows a dependency to be absent at runtime:

~~~java
module com.acme.library {
    requires static com.acme.optional;
}
~~~

**requires transitive** propagates readability of a dependency to consuming modules:

~~~java
module com.acme.library {
    requires transitive com.acme.api;
}
~~~

In Java, modifiers can be combined according to language rules, but do not combine them just to make a build pass. Decide whether the dependency is genuinely part of the public API or only needed for compilation.

When a type from a dependency appears in a public signature, consumers generally need to know the module containing that type to compile. If that dependency can disappear at runtime, compatibility policy must be carefully evaluated. A module whose public API deeply depends on an optional runtime type can cause consumer errors that **requires static** cannot resolve on its own.

A module descriptor test can check both **STATIC** and **TRANSITIVE** modifiers if required by the design contract, but do not treat the modifiers as equivalent.

## 13. Negative Runtime Test: Switching to Regular requires Must Fail When Module Is Missing

To clearly demonstrate the difference, you can prepare an experimental version of the descriptor:

~~~java
module com.acme.app {
    requires com.acme.annotations;
}
~~~

Recompile the app with the full dependencies. Then run in the **runtime-only** directory containing only the app:

~~~bash
java --module-path runtime-only \
     -m com.acme.app/com.acme.app.Main
~~~

The expected result is an error during module layer initialization or module resolution, typically with a message similar to:

~~~text
Module com.acme.annotations not found, required by com.acme.app
~~~

This is a control test proving the difference between regular **requires** and **requires static**. Never use the modified descriptor as the actual release version if the original design requires an optional runtime dependency.

In CI, manage control fixtures separately or create temporary test modules so you never accidentally alter the descriptor of the released artifact.

## 14. Testing When Using JUnit

If using JUnit to verify the descriptor, tests can read module metadata via Java APIs rather than relying on CLI tool output:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;

class ModuleContractTest {

    @Test
    void annotationsDependencyMustRemainStatic() {
        ModuleDescriptor descriptor = ModuleFinder
            .of(Path.of("mods"))
            .find("com.acme.app")
            .orElseThrow()
            .descriptor();

        var dependency = descriptor.requires()
            .stream()
            .filter(r -> r.name().equals("com.acme.annotations"))
            .findFirst()
            .orElseThrow();

        assertTrue(dependency.modifiers().contains(
            ModuleDescriptor.Requires.Modifier.STATIC
        ));

        assertFalse(descriptor.isAutomatic());
    }
}
~~~

This is a unit test of the metadata contract. Combine it with **integration tests using real javac and java**, because seeing the STATIC modifier alone does not prove the whole application runs cleanly when the dependency is absent.

Depending on whether JUnit runs on the classpath or module path, the test module may need separate configuration. Avoid letting flags like **--add-reads**, **--add-exports**, or **--patch-module** accidentally mask errors the test is meant to catch.

## 15. Do Maven and Gradle Replace requires static?

Build tools manage artifact dependencies; JPMS manages named module dependencies. These are two different layers.

In Gradle, a compile-only dependency is typically configured with **compileOnly**:

~~~groovy
dependencies {
    compileOnly("com.acme:annotations:1.0")
}
~~~

In Maven, a dependency not packaged as a runtime dependency may use a scope such as **provided** in appropriate situations:

~~~xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>annotations</artifactId>
    <version>1.0</version>
    <scope>provided</scope>
</dependency>
~~~

However, **compileOnly** or **provided** does not automatically write **requires static** into the descriptor. Conversely, **requires static** does not automatically pull dependencies onto the classpath/module path during a build.

You must synchronize them:

- The build tool must supply the right artifacts for javac to compile the module.
- **module-info.java** must declare JPMS module names, not Maven/Gradle artifact coordinates.
- Runtime packaging must deliberately decide whether to include the optional dependency.
- Integration tests must run on the actual module path, not just the IDE classpath.

If an artifact only has **Automatic-Module-Name** or a derived module name from its JAR, inspect the actual module name with **jar --describe-module** before writing **requires static**.

## 16. Inspecting the Module Graph at Runtime

The **--show-module-resolution** option lets you observe which modules are selected at startup:

~~~bash
java --show-module-resolution \
     --module-path runtime-only \
     -m com.acme.app/com.acme.app.Main
~~~

You can compare this with a configuration that actively resolves the optional module:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --add-modules com.acme.annotations \
     -m com.acme.app/com.acme.app.Main
~~~

When inspecting the output, pay attention to root modules, **requires**, and module locations. Do not conclude a module is resolved just because its JAR appears in a directory specified by **--module-path**.

You can use:

~~~bash
java --module-path mods --list-modules
~~~

to view modules observable by the launcher, but this command is not equivalent to confirming every module is included in the application's runtime configuration. To verify modules actually present in the boot layer, use **ModuleLayer.boot().findModule(...)** as shown in the earlier example.

## 17. Recommended CI Test Matrix

| Scenario | Compile-Time Dependency | Runtime Dependency | Expected Outcome |
|---|---|---|---|
| A. Full compile | Present | N/A | **javac** succeeds. |
| B. Compile missing static module | Absent | N/A | **javac** fails specifically due to missing module. |
| C. Minimal run | Compiled with module | Absent | Main not using the dependency still starts. |
| D. Run with optional module | Compiled with module | Present and resolved | App starts; optional module is observable. |
| E. Change descriptor to regular requires | Present | Absent | Resolution fails when module is missing. |
| F. Read packaged artifact | Present | Independent | Descriptor has exact **STATIC**, module name, and module kind. |
| G. Invoke feature truly needing optional module | Present | Absent | May fail; code must handle per feature design. |

Run the matrix in separate JVM processes to avoid interference from the test runner's class loaders, state, and module path. When testing a release artifact, point to the exact packaged JAR rather than another build in an IDE folder.

For expected-failure tests, verify both the exit code and the specific cause. A command failing due to a missing Java executable or wrong path is not evidence for the **requires static** contract.

## 18. Common Errors and Misconceptions

| Symptom | Possible Cause | How to Handle |
|---|---|---|
| **module not found** in javac | Module declared **requires static** is absent at compile time. | Add the right named module to the compilation path. |
| App module runs even without dependency | This may be the expected behavior of **requires static**. | Verify the execution path does not use optional runtime types. |
| Runtime has JAR yet **findModule** returns empty | JAR is on the module path but the module has not been resolved. | Configure appropriate roots/module resolution, e.g. **--add-modules**. |
| **NoClassDefFoundError** when invoking optional feature | Runtime code needs a type from the omitted dependency. | Design an optional feature boundary or supply the dependency. |
| Tests pass in IDE yet fail after packaging | IDE uses a classpath or module path different from the artifact. | Run tests against the final modular JAR using **-m**. |
| **requires static** turned into **requires** | Descriptor was edited or build used another artifact. | Read **ModuleDescriptor.Requires.Modifier.STATIC** from the JAR. |
| Automatic module instead of explicit module | Descriptor missing or packaged incorrectly. | Check **module-info.class** and **isAutomatic()**. |
| Negative test reports success due to syntax error | Script only checks for non-zero exit code. | Confirm diagnostic mentions the exact dependency/module. |

## 19. Practical Checklist

- Identify which dependencies are mandatory only at compile time and can genuinely be absent at runtime.
- Declare **requires static** using the exact JPMS module name in **module-info.java**.
- Verify the dependency's packages are sufficiently exported for compile-time usage.
- Compile with the dependency present and confirm success.
- Compile without the dependency and confirm failure specifically due to the missing module.
- Run the app module with **-m** when the dependency is completely absent from the runtime module path.
- Run with the dependency resolved and verify required behavior.
- Read the descriptor of the packaged modular JAR using **ModuleFinder/ModuleDescriptor**.
- Confirm the **STATIC** modifier was not lost and the module did not accidentally become automatic.
- Run runtime tests with and without the dependency in separate JVM processes.
- Do not equate build tool scopes with the **requires static** directive.
- If code uses the dependency at runtime, add feature tests or extract an adapter to avoid class loading failures when the module is absent.

**Testing module-info.java and requires static** means testing a dependency contract at both compile time and runtime. A properly designed module must have sufficient dependencies for javac, preserve the **STATIC** modifier in its artifact, and provide a valid execution path when the optional module is absent. Combining descriptor tests, expected-failure compilation tests, and runtime tests in both configurations catches JPMS issues early before release.