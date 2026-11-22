# Moving Libraries to the Module Path Incrementally

When a long-lived Java project uses the classpath, JARs are usually placed together in a single list of paths and the application can reference their public classes without declaring explicit module relationships. The Java Platform Module System (JPMS), introduced in Java 9, adds the **module path**, **named modules**, **module descriptors**, and rules for readability, exports, and service loading.

In practice, it is rarely possible to migrate all libraries to JPMS in one go. Some JARs already have `module-info.class`, some only have `Automatic-Module-Name`, and many libraries are still traditional JARs. A pragmatic approach is **incremental migration**: keeping the application running through each stage and converting dependencies into named modules once conditions are met.

This lesson describes a step-by-step roadmap: **classpath → automatic modules on the module path → application with module-info.java → explicit module libraries**, along with verification methods after each step.

## Objectives

After this lesson, you will be able to:

- Distinguish classpath, unnamed module, module path, automatic module, and explicit named module.
- Move a traditional JAR onto the module path without needing to write `module-info.java` immediately.
- Verify a JAR's actual module name and pin it with `Automatic-Module-Name`.
- Run a classpath application that consumes libraries on the module path.
- Convert the application into an explicit named module with `requires`.
- Understand when remaining dependencies on the classpath must also be migrated.
- Detect split packages, missing modules, mismatched module names, and exports/services issues.
- Plan a migration with verification steps and clear rollback paths.

## 1. Why Migrate Incrementally?

An application might have a dependency graph like this:

~~~text
com.acme.app
  ├── acme-math.jar
  ├── acme-client.jar
  │     └── legacy-http.jar
  └── acme-report.jar
        └── thirdparty-util.jar
~~~

In the classpath model, JARs can be supplied with a `-cp` argument:

~~~bash
java -cp "app.jar:libs/*" com.acme.app.Main
~~~

On Windows, the classpath separator is a semicolon:

~~~powershell
java -cp "app.jar;libs/*" com.acme.app.Main
~~~

When using JPMS, modules are resolved by name and dependencies. Requiring every JAR to become an explicit module simultaneously can hit snags:

- Libraries that have not yet published descriptors.
- Unstable module names.
- Overlapping packages across dependencies.
- Dependencies that only work through reflection or SPI.
- Frameworks expecting the thread context class loader.
- Application code directly calling classes on the classpath that a named module cannot read.

Moving incrementally helps isolate errors: move one group of JARs at a time, compile, run smoke tests, and inspect the graph before moving the next group.

## 2. Five Concepts to Keep Distinct

| Concept | Practical meaning |
|---|---|
| Classpath | Traditional set of directories/JARs, typically provided with `-cp` or `--class-path` |
| Unnamed module | Classes loaded by a class loader from the classpath belong to that loader's unnamed module |
| Module path | Source for locating named modules, provided with `-p` or `--module-path` |
| Automatic module | A JAR without a descriptor placed on the module path that assumes a named module identity |
| Explicit named module | A module with a `module-info.class` descriptor defining its name and directives like `requires`, `exports` |

### 2.1. Automatic Modules Are a Migration Bridge

A traditional JAR without `module-info.class` can be placed on the module path so Java treats it as an **automatic module**.

An automatic module:

- Has a module name determined by the manifest or filename.
- Is treated as exporting all of its packages.
- Can read all resolved modules and the unnamed module, easing migration.
- Lacks explicitly declared `requires`/`exports` directives like an explicit module.

That **does not mean the JAR is fully modularized**. An automatic module still lacks an explicit module contract, and a module name derived from the filename can change when a publisher changes artifact naming.

### 2.2. Explicit Named Modules Have Stricter Boundaries

Example of an explicit module library:

~~~java
module com.acme.math {
    exports com.acme.math;
}
~~~

A modular application using it:

~~~java
module com.acme.app {
    requires com.acme.math;
}
~~~

A named module cannot declare `requires` on the regular unnamed module. Therefore, when turning the **application** into an explicit named module, ensure the libraries the application directly uses are visible as named modules (explicit or automatic), or have a controlled transitional solution.

## 3. Principles for Ordering Library Migration

Start from **dependencies low in the graph**, usually utilities or libraries with few dependencies on other modules. Once they are stable on the module path, move higher-level libraries, and finally the main application.

Example:

~~~text
                 com.acme.app
                  /        \
                 v          v
           acme-client    acme-report
                 |          |
                 v          v
            legacy-http  thirdparty-util
~~~

A sensible order might be:

1. Inventory module names and packages of `legacy-http` and `thirdparty-util`.
2. Move lower-layer dependencies onto the module path if there are no conflicts.
3. Convert `acme-client` and `acme-report` into automatic/explicit modules.
4. Convert `com.acme.app` into an explicit module once types the app uses directly are in named modules.
5. Replace automatic modules with explicit modules library by library as suitable descriptors become available.

This is a **recommended strategy**, not a rigid rule forcing every project to migrate in that exact order. A library with split packages or a special framework might need attention first.

## 4. Pre-Migration Inventory

Before changing launch commands, build a table for each dependency:

| Information | How to determine |
|---|---|
| Is the JAR on the classpath or module path? | Actual launch commands, IDE and build configs |
| Does it have `module-info.class`? | `jar --describe-module` |
| What is its actual module name? | `jar --describe-module --file ...` |
| Does it have `Automatic-Module-Name`? | The JAR's manifest |
| Which packages does it contain? | `jar tf ...` |
| Are there service providers/resources/reflection? | Source code and runtime configuration |
| Which libraries does the dependency depend on? | `jdeps`, Maven/Gradle dependency graph |

Inspect descriptor or automatic module name:

~~~bash
jar --describe-module --file libs/acme-math.jar
~~~

List classes in the JAR:

~~~bash
jar tf libs/acme-math.jar
~~~

Analyze static dependencies of a classpath application:

~~~bash
jdeps --print-module-deps --class-path "libs/*" app.jar
~~~

`jdeps` does not detect every dependency loaded by class name, reflection, or plugins; combine it with runtime configurations and real tests.

With Maven:

~~~bash
mvn dependency:tree
~~~

With Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

On Windows, you can use `gradlew.bat`. The goal of this step is to identify exactly which artifacts are in use and avoid keeping two copies of the same library on different paths.

## 5. Hands-On Example: A Legacy Math Library

We will create a traditional library JAR, then incrementally migrate both it and the application to JPMS. The example uses Java 17+ and runs from the project directory.

Initially:

~~~text
project/
├── legacy-src/
│   └── com/acme/math/TaxCalculator.java
├── app-src/
│   └── com/acme/app/Main.java
├── libs/
└── out/
~~~

Library:

~~~java
// legacy-src/com/acme/math/TaxCalculator.java
package com.acme.math;

public final class TaxCalculator {
    private TaxCalculator() {}

    public static int totalWithTax(int amount, int taxPercent) {
        return amount + amount * taxPercent / 100;
    }
}
~~~

Application:

~~~java
// app-src/com/acme/app/Main.java
package com.acme.app;

import com.acme.math.TaxCalculator;

public class Main {
    public static void main(String[] args) {
        System.out.println(TaxCalculator.totalWithTax(100, 10));
    }
}
~~~

### 5.1. Compiling the JAR the Classpath Way

Compile the library:

~~~bash
javac -d out/math legacy-src/com/acme/math/TaxCalculator.java
~~~

Package a traditional JAR:

~~~bash
jar --create --file libs/acme-math.jar -C out/math .
~~~

Compile the application:

~~~bash
javac -cp libs/acme-math.jar -d out/app app-src/com/acme/app/Main.java
~~~

Run on Linux/macOS:

~~~bash
java -cp "out/app:libs/acme-math.jar" com.acme.app.Main
~~~

Run on Windows:

~~~powershell
java -cp "out/app;libs/acme-math.jar" com.acme.app.Main
~~~

Output:

~~~text
110
~~~

This is the starting baseline for comparison when moving to the module path.

## 6. Step 1: Assigning a Stable Module Name to the Library

If you put `acme-math.jar` without a descriptor onto the module path, Java can derive the automatic module name from the filename. A derived name can be surprising or change with filename conventions.

To control migration, the library publisher can add a manifest:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.math

~~~

Save the content to `math.mf` (with an appropriate trailing newline), then recreate the JAR:

~~~bash
jar --create --file libs/acme-math.jar \
    --manifest math.mf \
    -C out/math .
~~~

On Windows PowerShell:

~~~powershell
jar --create --file libs/acme-math.jar --manifest math.mf -C out/math .
~~~

Verify:

~~~bash
jar --describe-module --file libs/acme-math.jar
~~~

The JAR does not have `module-info.class` yet, but now has a stable automatic module name of `com.acme.math`.

**Note:** `Automatic-Module-Name` only supplies a module name. It does not declare actual `requires` or `exports`, nor does it fix split packages.

## 7. Step 2: Moving the JAR to the Module Path, App Still on Classpath

Keep the application's code and classes on the classpath, while placing `acme-math.jar` on the module path.

Launch command on Linux/macOS:

~~~bash
java --module-path libs/acme-math.jar \
     --add-modules com.acme.math \
     --class-path out/app \
     com.acme.app.Main
~~~

Equivalent single-line command (works on Windows):

~~~powershell
java --module-path libs/acme-math.jar --add-modules com.acme.math --class-path out/app com.acme.app.Main
~~~

Expected output is still:

~~~text
110
~~~

### 7.1. Why Is --add-modules Needed?

When running a main class from the classpath, the application lives in the unnamed module. An application module placed on the module path **is not automatically resolved** merely because its JAR appears on the path.

`--add-modules com.acme.math` adds that automatic module as a root to resolve, allowing the classpath application to use classes published by the module.

If the library is not in the resolved module set, the launch command can fail to find the class even though the JAR is on the module path. Thus, you must check both the **module path** and **root modules**.

### 7.2. Do Imports Need to Change?

No. The Java class name remains:

~~~java
import com.acme.math.TaxCalculator;
~~~

Moving a JAR from the classpath to the module path does not rename packages or classes.

### 7.3. What Changed?

Before:

~~~text
Unnamed module (app + acme-math)
~~~

After:

~~~text
Unnamed module (app)
        |
        | uses public API
        v
Automatic named module: com.acme.math
~~~

This is an important intermediate step: the application does not yet need `module-info.java`, but you have already verified that the library can participate in the module graph.

## 8. Step 3: Converting the Application to an Explicit Named Module

Once the libraries the app directly uses have stable module names, you can add `module-info.java` to the application.

Move the app code to a module source path layout:

~~~text
project/
└── src/
    └── com.acme.app/
        ├── module-info.java
        └── com/acme/app/Main.java
~~~

`module-info.java`:

~~~java
module com.acme.app {
    requires com.acme.math;
}
~~~

`Main.java` remains unchanged:

~~~java
package com.acme.app;

import com.acme.math.TaxCalculator;

public class Main {
    public static void main(String[] args) {
        System.out.println(TaxCalculator.totalWithTax(100, 10));
    }
}
~~~

Compile the app with the automatic module library:

~~~bash
javac --module-path libs/acme-math.jar \
      --module-source-path src \
      -d out/mods \
      -m com.acme.app
~~~

Single-line command:

~~~bash
javac --module-path libs/acme-math.jar --module-source-path src -d out/mods -m com.acme.app
~~~

Run on Linux/macOS:

~~~bash
java --module-path "out/mods:libs/acme-math.jar" \
     -m com.acme.app/com.acme.app.Main
~~~

Run on Windows:

~~~powershell
java --module-path "out/mods;libs/acme-math.jar" -m com.acme.app/com.acme.app.Main
~~~

Output:

~~~text
110
~~~

At this stage:

- The application is now the explicit named module `com.acme.app`.
- The library is still the automatic named module `com.acme.math`.
- The app has an explicit readability relationship via `requires com.acme.math;`.
- The automatic library's packages are exported according to automatic module rules.

### 8.1. Why Not Leave All Dependencies on the Classpath?

The named module `com.acme.app` cannot declare a valid `requires` clause pointing to the unnamed module. If the app directly uses classes from a JAR still on the classpath, the compiler may report that the package is not visible or that the module does not read the unnamed module.

Therefore, before converting the app, you must address at least the dependencies that app code accesses directly: move them onto the module path as explicit/automatic modules or refactor the architecture so they sit behind a suitable abstraction.

Workarounds like `--add-reads com.acme.app=ALL-UNNAMED` exist for some legacy scenarios, but should not be treated as the final design because they bypass the benefits of explicitly declared dependencies.

## 9. Step 4: Converting the Automatic Library to an Explicit Module

Once the app runs reliably with the automatic module, you can modularize the library itself. For example, organize the library source as:

~~~text
lib-src/
└── com.acme.math/
    ├── module-info.java
    └── com/acme/math/TaxCalculator.java
~~~

The library's descriptor:

~~~java
module com.acme.math {
    exports com.acme.math;
}
~~~

`TaxCalculator.java` keeps its package and public API.

Compile the library:

~~~bash
javac --module-source-path lib-src \
      -d out/libs \
      -m com.acme.math
~~~

Package the modular JAR:

~~~bash
jar --create --file libs/acme-math-modular.jar \
    -C out/libs/com.acme.math .
~~~

Verify the descriptor:

~~~bash
jar --describe-module --file libs/acme-math-modular.jar
~~~

Recompile the app with the new modular JAR:

~~~bash
javac --module-path libs/acme-math-modular.jar \
      --module-source-path src \
      -d out/mods \
      -m com.acme.app
~~~

Run on Linux/macOS:

~~~bash
java --module-path "out/mods:libs/acme-math-modular.jar" \
     -m com.acme.app/com.acme.app.Main
~~~

On Windows:

~~~powershell
java --module-path "out/mods;libs/acme-math-modular.jar" -m com.acme.app/com.acme.app.Main
~~~

The output is still:

~~~text
110
~~~

**Important:** When moving to an explicit module, packages not listed in `exports` are no longer automatically exported as they were in an automatic module. Hence, design the public API carefully and update the descriptor accordingly.

Do not place **both** `acme-math.jar` and `acme-math-modular.jar` on the same module path when both provide module `com.acme.math`. Remove the old version from your configuration before testing the new version.

## 10. When Many Unmodularized Libraries Remain

In a real application, an intermediate structure might look like:

~~~text
                Explicit named module: com.acme.app
                        |
                  requires
                        v
                Automatic module: com.acme.client
                        |
               legacy implementation
                        v
                 Unnamed module
                    (classpath)
~~~

Automatic modules are designed to support some legacy dependencies from the unnamed module, so they can act as a bridge during the transition. However, the app's explicit named module should not directly rely on classes in the unnamed module if you want a sustainable graph.

Distinguish these cases:

- **App directly imports classes in a JAR still on the classpath:** move that JAR or redesign the dependency before modularizing the app.
- **App only calls the automatic module's API, while that module's implementation uses classpath dependencies:** can be a temporary migration state, though thorough testing is needed.
- **Library transitions from automatic to explicit:** the library no longer inherits automatic access to the unnamed module; actual dependencies must be declared and moved appropriately.

A safe path is listing direct and indirect dependencies, then migrating gradually until the main graph no longer depends on automatic-module-to-classpath access.

## 11. Common Errors During Incremental Migration

### 11.1. Module not found

Example:

~~~text
error: module not found: com.acme.math
~~~

Possible causes:

- The JAR is not on `--module-path` in the compile/run command.
- The module name differs from what is written in `requires`.
- The build uses a different JAR or version.
- The dependency exists only in IDE configuration, not in the actual launch command.

Check:

~~~bash
jar --describe-module --file libs/acme-math.jar
~~~

And double-check the entire `--module-path`.

### 11.2. NoClassDefFoundError or ClassNotFoundException

When a JAR has been placed on the module path without being resolved, classes may not be found by a classpath application.

If the app still runs from the classpath, check root modules via `--add-modules`:

~~~bash
java --module-path libs/acme-math.jar \
     --add-modules com.acme.math \
     --class-path out/app com.acme.app.Main
~~~

If the module is resolved, next check whether the class is inside the JAR, which class loader is loading it, and whether transitive dependencies are complete.

### 11.3. Package is not visible

With explicit modules, a package must be exported by the providing module and the consuming module must read that module.

Example:

~~~java
module com.acme.math {
    exports com.acme.math.api;
}
~~~

~~~java
module com.acme.app {
    requires com.acme.math;
}
~~~

If the app imports `com.acme.math.internal` and the library does not export it, the compiler will reject it. This is JPMS encapsulation, not a sign of a broken JAR.

### 11.4. Split package

Two JARs may contain the same package, for example:

~~~text
acme-core.jar
└── com/acme/shared/Util.class

acme-extra.jar
└── com/acme/shared/Helper.class
~~~

When both become named modules and join the graph, split packages can cause resolution or access errors. Identify which module owns the package, then rename the package, merge modules, or upgrade the dependency as appropriate.

`--add-exports` does not solve split packages, because it alters export visibility rather than package ownership.

### 11.5. Duplicate module name

Two JARs on the module path may share the same module name, for example both declaring `Automatic-Module-Name: com.acme.math`. The outcome depends on finder order and configuration, and can cause a module to be shadowed or a configuration failure.

Do not keep two versions of the same module simultaneously. Inspect artifacts and remove duplicates to keep the graph clean.

### 11.6. Reflection failures

Frameworks using reflection may encounter `InaccessibleObjectException` after a library becomes an explicit module.

In that case, determine which packages need to be opened to the framework:

~~~java
module com.acme.app {
    requires com.acme.framework;

    opens com.acme.app.model to com.acme.framework;
}
~~~

`exports` is for normal public API access; `opens` is for deep reflection into non-public members under appropriate conditions.

Use qualified opens when only one framework module needs access, avoiding opening the entire implementation.

### 11.7. ServiceLoader fails to find providers

Plugin systems often use `ServiceLoader`. When moving to explicit named modules, the service contract should be declared explicitly:

Module using the service:

~~~java
module com.acme.app {
    requires com.acme.spi;
    uses com.acme.spi.PaymentProvider;
}
~~~

Module providing the implementation:

~~~java
module com.acme.payment.impl {
    requires com.acme.spi;
    provides com.acme.spi.PaymentProvider
        with com.acme.payment.internal.DefaultPaymentProvider;
}
~~~

For a provider to be discovered, the provider module must be present in the appropriate configuration/layer and resolved in a manner compatible with service loading.

Do not just move JARs between paths without re-checking `META-INF/services`, descriptors, and provider instantiation.

## 12. Tools for Monitoring Migration

### 12.1. jar --describe-module

~~~bash
jar --describe-module --file libs/acme-math.jar
~~~

Used to check whether a JAR is an explicit or automatic module and see its actual module name.

### 12.2. java --list-modules

~~~bash
java --module-path libs --list-modules
~~~

Lists modules observable from the runtime/module path of the invocation. A module appearing in this list is not necessarily resolved into the application's boot layer.

### 12.3. --show-module-resolution

~~~bash
java --module-path "out/mods:libs" \
     --show-module-resolution \
     -m com.acme.app/com.acme.app.Main
~~~

On Windows, replace `:` with `;`. Use the log to identify root modules, dependencies, and which modules actually participate in the startup graph.

### 12.4. java --validate-modules

~~~bash
java --module-path libs --validate-modules
~~~

Useful for detecting module path problems such as conflicting or shadowed modules.

### 12.5. jdeps

For a traditional application JAR:

~~~bash
jdeps --class-path "libs/*" --print-module-deps app.jar
~~~

For a named module:

~~~bash
jdeps --module-path "out/mods:libs" --check com.acme.app
~~~

On Windows, use `;` instead of `:` in multi-entry module paths. `jdeps` output helps analyze static dependencies, but does not replace runtime smoke tests.

### 12.6. Inspecting JAR Contents

~~~bash
jar tf libs/acme-math.jar
~~~

Find the packages and classes actually packaged. If a JAR is empty, has classes in the wrong package, or contains stale bytecode, changing the module path will not solve the problem.

## 13. Migration in Maven and Gradle

### 13.1. Maven

Inspect dependencies:

~~~bash
mvn dependency:tree
~~~

Compile and test after each phase:

~~~bash
mvn clean verify
~~~

In Maven projects, the compiler plugin needs a module-path configuration matching the JDK version and current module structure. Do not assume every project plugin or profile will automatically route all dependencies to the module path as intended.

If multiple Maven modules correspond to multiple JPMS modules, distinguish:

- Maven module: a build unit within the reactor.
- JPMS module: a named module identified by a module descriptor or automatic module name.

These two concepts can be related, but are not synonymous.

### 13.2. Gradle

Inspect the dependency graph:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Test:

~~~bash
./gradlew clean test
~~~

Some Gradle versions can infer the module path from `module-info.java` and dependency metadata, though exact behavior depends on plugins/build configuration. Therefore, inspect the actual compiler and launcher commands rather than relying solely on the build tool's dependency list.

### 13.3. Maintaining a Single Source of Truth for Dependencies

During incremental migration, avoid having the same JAR appear on both the classpath and the module path in a single run. That situation easily creates split class identities, version mismatches, or harder diagnostics.

Explicitly document which dependencies are on the classpath, which are on the module path, and the next migration step for each artifact.

## 14. When Should You Use requires transitive?

After converting a library into an explicit module, if its public API exposes types from another module, consider `requires transitive`.

Example:

~~~java
module com.acme.client {
    requires transitive com.acme.model;
    exports com.acme.client.api;
}
~~~

If a class in `com.acme.client.api` has a method returning a public type from `com.acme.model`, clients reading `com.acme.client` also need to see the model types in the API.

`requires transitive` propagates readability; it does not automatically export unexported packages from the model module.

Do not mechanically declare every dependency as transitive. Use it only when the dependency module is genuinely part of the public API contract.

## 15. What Not to Do

**Moving all JARs onto the module path at once.**

A bulk move can expose many conflicts simultaneously. Moving small groups of dependencies makes root causes easier to pinpoint.

**Guessing module names from filenames.**

Automatic module names may be determined by the manifest. Use `jar --describe-module` to verify before writing `requires`.

**Using --add-exports as a substitute for module design.**

This flag only changes export visibility in specific contexts. It does not fix missing JARs, duplicate module names, or split packages.

**Assuming automatic modules already have good encapsulation.**

Automatic modules export all packages by default. When converting to an explicit module, identify true API packages and export only what needs to be published.

**Forgetting to check service providers and reflection.**

A project can compile successfully yet fail when a framework scans annotations, loads plugins, or discovers service providers. Runtime/integration tests are required.

**Forgetting clean builds and distinguishing compile/runtime paths.**

Stale classes left in output or compile-only dependencies can cause failures after deployment. Verify with the exact runtime artifact.

**Treating workarounds as the final architecture.**

`--add-reads` or `--add-exports` can be useful for difficult migrations, but should be narrowly scoped and scheduled for removal.

## 16. Migration Plan with Verification Milestones

A practical rollout plan can be divided into the following milestones:

| Milestone | State | Transition condition |
|---|---|---|
| M0 | Entire app and dependencies run on the classpath | Current build and smoke tests run stably |
| M1 | One low-level library is an automatic module on the module path | Classpath app runs with appropriate `--add-modules` |
| M2 | Multiple dependencies are on the module path | No split packages/duplicate modules in the required graph |
| M3 | App is an explicit named module | Complete `requires`; no direct dependency on the unnamed module |
| M4 | Key libraries have explicit descriptors | API packages exported cleanly; reflection/services work |
| M5 | Build and deployment stable on JPMS | CI and production runtime use the verified module graph |

### 16.1. Verification After Each Milestone

After each JAR migration:

1. Record the new artifact name and version.
2. Run `jar --describe-module` to confirm the module name.
3. Compile with the exact target JDK and module path.
4. Run `--show-module-resolution` to inspect the graph.
5. Run relevant tests and application smoke tests.
6. Verify class/service loading if the library uses plugins or reflection.
7. Proceed to the next dependency only when the current step runs stably.

If an error occurs, roll back to the classpath/module-path configuration of the most recent verified milestone instead of piling on multiple patch flags at once.

## 17. Self-Check Questions

**Question 1.** A JAR does not yet have `module-info.class` but is placed on the module path. Can Java treat it as a module?

**Answer:** Yes. The JAR can become an automatic module; its module name is taken from the `Automatic-Module-Name` manifest entry or derived according to JDK rules.

**Question 2.** The app still runs from the classpath. After moving `acme-math.jar` onto the module path, why might `--add-modules com.acme.math` be needed?

**Answer:** Because having the JAR on the module path does not guarantee that module is resolved as a root. `--add-modules` instructs Java to resolve the named module.

**Question 3.** Can you write `requires unnamed;` in the application's `module-info.java`?

**Answer:** No. The unnamed module has no name to declare in `requires` the way a named module does.

**Question 4.** An automatic module library was already working. When converting it to an explicit module, what could cause the app to fail compilation?

**Answer:** Packages that were previously exported automatically may no longer be exported. You need to design `exports` for the APIs to expose and update dependencies accordingly.

**Question 5.** Two JARs on the module path both contain package `com.acme.common`. Can you solve it simply by adding `--add-exports`?

**Answer:** No. You must resolve the split package by determining which module owns the package or by changing packages/dependency versions appropriately.

**Question 6.** Why should libraries with fewer dependencies be migrated first?

**Answer:** Because you can verify lower dependency layers first and then migrate higher-level dependent libraries, making errors easier to isolate.

**Question 7.** Which command shows a JAR's actual module name?

**Answer:** `jar --describe-module --file path/to/library.jar`.

**Question 8.** The application has become a named module, yet still directly imports classes from a JAR that exists only on the classpath. Is this a sustainable state?

**Answer:** Generally no. The app cannot declare `requires` on the unnamed module; you should move direct dependencies to the module path or adjust the design accordingly.

**Question 9.** Is an automatic module a secure sandbox for untrusted code?

**Answer:** No. JPMS is a mechanism for module organization and encapsulation; the module path or class loaders should not be treated as a security isolation mechanism.

**Question 10.** After migrating a library, the build succeeds but `ServiceLoader` fails to find providers. What should you check?

**Answer:** Check `uses`/`provides`, service descriptors, whether the provider module is resolved in the right layer, and whether the runtime configuration includes all required modules.

## Summary

**Moving libraries to the module path incrementally** is the process of bringing a traditional classpath application into JPMS without forcing every dependency to have `module-info.java` immediately.

A common roadmap is: inventory dependencies → move some JARs onto the module path as automatic modules → run the classpath app with suitable root modules → convert the app into an explicit named module → convert libraries one by one into explicit modules and narrow API exports.

At each stage, verify the **actual module name, JAR source, resolved modules, package access permissions, and runtime behavior**. This prevents confusion between classpath errors, module lookup errors, split packages, and encapsulation failures while reducing migration risk in large systems.
