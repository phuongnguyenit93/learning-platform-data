# --add-modules, --add-reads, and Temporary Usage Scope

In Java Advance Compatibility Migration, changing the JDK or migrating an application from the classpath to the Java Platform Module System (JPMS) often exposes dependencies that were previously not explicitly declared. A class may still exist in the JAR yet not be found at runtime, a named module may fail to read another module, or legacy code that worked on the classpath may fail after being moved onto the module path. During the transition phase, the two options **--add-modules** and **--add-reads** can help the development team isolate and resolve certain module resolution and readability issues.

These two options are **not equivalent**, nor are they **a long-term JPMS design solution**. --add-modules expands the list of modules included in the module graph. --add-reads adds a read relation from a named module to a target module. Neither option automatically opens packages for reflection, fixes nonexistent APIs, adds classes into a JDK image, or turns an incompatible dependency into a compatible one.

The goal of this lesson is to understand the mechanism, use both options in the right places, verify with specific Java commands, and build a plan to replace temporary exceptions with a clear module structure.

## 1. The JPMS Model to Understand Before Adding Options

JPMS was introduced in Java 9 and organizes code into **modules**. Named modules typically have a module-info.java file describing dependencies, exported packages, packages opened for reflection, and services provided or used.

Example library module:

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

Example application module:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

When the application module declares requires, JPMS knows it must read the library module. When the library module declares exports, public types in the corresponding package can be accessed by other modules according to JPMS rules.

### 1.1. Four Concepts Easily Confused

| Concept | Question | Mechanism |
|---|---|---|
| Observable module | Where can the system find the module? | System modules, module path, module finder |
| Resolved module | Is the module included in the module graph for this run? | Root modules and dependency resolution |
| Readability | Does module A have permission to read module B? | requires, requires transitive, --add-reads |
| Accessibility | Do B's package/type/member allow A to access them in the way being used? | exports, opens, --add-exports, --add-opens, Java access rules |

**Observable does not mean resolved.** A modular JAR can reside on the module path yet not be in the module graph if there is no appropriate root or dependency.

**Resolved does not mean readable.** Module B may already be added to the graph, yet module A does not have a read edge to B.

**Readable does not mean accessible.** If A can read B, but B does not export the needed package, A's code still cannot access public types in the normal way. For deep reflection, the situation also requires opens or --add-opens.

You can visualize it as follows:

~~~text
[Module B is on the module path]
               |
               v
[Is Module B resolved in graph?] ---- no ---> --add-modules or appropriate requires
               |
              yes
               v
[Can Module A read Module B?] ------- no ---> requires or --add-reads
               |
              yes
               v
[Does B export needed package?] ----- no ---> exports or --add-exports
               |
              yes
               v
[Are Java access rules valid?] ------ no ---> adjust visibility/API
               |
              yes
               v
[Public API access can succeed]

Deep reflection: see opens / --add-opens separately.
~~~

### 1.2. Named, Automatic, and Unnamed Modules

- **Explicit named module:** has module-info.class; requires, exports, and opens relationships are explicitly declared.
- **Automatic module:** a regular JAR placed on the module path and treated by JPMS as a module with an inferred name or a name specified by the manifest. It aids migration, but a module name inferred from the JAR filename can change and must be checked.
- **Unnamed module:** classes/JARs on the classpath belong to the unnamed module of the corresponding class loader. Legacy code typically runs under this model.

A named module cannot by default read classes located in the unnamed module. During gradual migration, **--add-reads module.name=ALL-UNNAMED** can create a bridge, but it should be viewed as a transitional solution.

## 2. --add-modules: Adding Root Modules to Resolution

General Java launcher syntax:

~~~bash
java --add-modules module1,module2 [other options] ...
~~~

This option instructs the launcher to treat the listed modules as **additional root modules** when resolving the module graph. If a root module has requires to other modules, resolution also brings those required dependencies into the graph according to JPMS rules.

Conceptual example:

~~~bash
java \
  --module-path mods \
  --add-modules com.example.plugin \
  --module com.example.app/com.example.app.Main
~~~

The application com.example.app is the main module; com.example.plugin is added as a root. This may be needed when the plugin module is discovered via ServiceLoader or a dynamic discovery mechanism rather than having a requires relationship from the main module.

However, --add-modules does **not** mean com.example.app is allowed to import and call public APIs of com.example.plugin if the two modules do not yet have an appropriate readability relationship. Nor does it mean the plugin's packages are exported to the app.

### 2.1. The Module Must Actually Be Observable

Suppose you run:

~~~bash
java \
  --module-path mods \
  --add-modules com.vendor.connector \
  -m com.example.app/com.example.app.Main
~~~

If com.vendor.connector is not on the module path, in system modules, or in an appropriate module source, the launcher cannot resolve that module from its name and may report a resolution error, such as module not found.

Steps to check:

1. Does the JAR/module actually exist at the expected path?
2. Is the JPMS module name correct, especially for an automatic module?
3. Is the JAR placed on the module path or the classpath?
4. Does the runtime image contain the requested JDK module?
5. Are there any module name, package, or version conflicts?

With a custom runtime image created by jlink, if a JDK module is not in the image, --add-modules does not automatically add back the omitted module content. You must rebuild the runtime image or change the deployment configuration.

### 2.2. Special Values of --add-modules

The Java launcher supports special tokens to specify a set of modules instead of a single module name:

| Token | General meaning | Notes |
|---|---|---|
| ALL-DEFAULT | Default root modules for the corresponding launch scenario | The default set varies by launch mode and JDK |
| ALL-SYSTEM | All observable system modules | Can expand the graph significantly |
| ALL-MODULE-PATH | Modules found on the module path | Can expose module/package conflicts |

Example:

~~~bash
java \
  --module-path mods \
  --add-modules ALL-MODULE-PATH \
  -m com.example.app/com.example.app.Main
~~~

This is a way to widen resolution scope, **not a recommended default production configuration**. If there are unnecessary modules on the module path, resolving all of them can expose or create conflicts, complicate startup, and make the configuration depend on the contents of the deployment directory.

When a specific plugin is needed, prefer the specific module name. When debugging resolution, broad tokens can be used in a test environment to distinguish an "unresolved module" issue from a "resolved module missing a read edge" issue.

### 2.3. Is --add-modules Always Necessary?

No. If a module is already included in the graph via requires or belongs to the default roots, adding the module name again usually accomplishes nothing. A module may already be in the runtime and resolved; verify with:

~~~bash
java --list-modules
java --show-module-resolution \
  --module-path mods \
  -m com.example.app/com.example.app.Main
~~~

--list-modules shows the modules in the runtime image, not all modules that a specific application will resolve. --show-module-resolution shows the resolution process when the launcher runs with the command being used. Those are two different viewpoints.

## 3. --add-reads: Adding a Read Edge Between Modules

Common syntax:

~~~bash
java --add-reads module.source=module.target ...
~~~

Or with multiple target modules:

~~~bash
java --add-reads module.source=module.target1,module.target2 ...
~~~

An example:

~~~bash
java \
  --module-path mods \
  --add-modules com.example.library \
  --add-reads com.example.app=com.example.library \
  -m com.example.app/com.example.app.Main
~~~

In this example:

- com.example.library must **be resolved**; --add-modules ensures an additional root if there is not yet a resolution path from the app.
- --add-reads allows com.example.app to read com.example.library.
- The package containing the needed API must still be properly exported from com.example.library.
- Java visibility rules still apply to classes, constructors, fields, and methods.

A read edge is a **directed** relationship. If A reads B, it does not imply that B also reads A. Nor does it imply that A reads all dependencies that B reads, except for relationships propagated by the module system through the corresponding mechanism.

### 3.1. When the Target Module Is Not Yet Resolved

If you only specify:

~~~bash
java \
  --module-path mods \
  --add-reads com.example.app=com.example.library \
  -m com.example.app/com.example.app.Main
~~~

while com.example.library is not yet in the resolved graph, the --add-reads option does not automatically turn B into a root module. In many cases, the JVM will warn that the module name does not exist in the graph or fail to create a useful read edge. Therefore, check resolution first; when necessary, --add-modules and --add-reads can be used together.

This must also be distinguished from the case where the app already has requires com.example.library: the read edge already exists per the descriptor, so adding --add-reads may be redundant and make the configuration confusing.

### 3.2. Read Edge to the Unnamed Module

A common migration scenario: the source code of module A already has module-info.java but still depends on a legacy JAR that developers have not yet moved onto the module path. This JAR is currently on the classpath, belonging to the unnamed module.

A temporary read edge can be opened with:

~~~bash
java \
  --module-path mods \
  --class-path "legacy/*" \
  --add-reads com.example.app=ALL-UNNAMED \
  -m com.example.app/com.example.app.Main
~~~

ALL-UNNAMED is a special token representing the corresponding unnamed modules. This option allows the named module to read classpath code, however:

- The legacy JAR must still actually be present on the classpath.
- Do not invent a fake module name for a classpath JAR and expect --add-reads to find it.
- Class loaders, reflection, and framework configuration must be tested in a real environment.
- This is a temporary way to bridge two deployment models, not a replacement for long-term dependency design.

If the code needs to be compiled as a named module while using the legacy classpath, the compiler must also be configured for this scenario. Simply adding --add-reads at runtime does not fix compile-time source errors.

### 3.3. Does Not Automatically Fix exports or opens

Suppose the library has:

~~~java
module com.example.library {
    // Does not export com.example.library.internal;
}
~~~

Even when run with:

~~~bash
--add-reads com.example.app=com.example.library
~~~

com.example.app does not automatically gain permission to use public types in unexported internal packages.

Three options have different purposes:

| Option | Adjusts | Does not do |
|---|---|---|
| --add-modules | Adds additional modules to the resolved graph | Does not allow A to read B |
| --add-reads | Adds readability A → B | Does not export/open packages |
| --add-exports | Exports a package from the source module to the target module for normal API access | Does not open everything for deep reflection |
| --add-opens | Opens a package for deep reflection at runtime | Does not replace requires or modify method descriptors |

Syntax for exporting a package to a specific module:

~~~bash
--add-exports com.example.library/com.example.library.internal=com.example.app
~~~

Syntax for opening a package for reflection:

~~~bash
--add-opens com.example.library/com.example.library.internal=com.example.app
~~~

Use the right option for the right error. If only readability is missing, do not open internal packages. If the error is InaccessibleObjectException due to reflection, adding only a read edge is also not guaranteed to fix it.

## 4. End-to-End Example: Two Named Modules Without requires

This is an intentionally broken scenario: the app module calls a library that has exported its public API, but the app's module-info.java does not yet declare requires.

### 4.1. Source Structure

~~~text
jpms-demo/
└── src/
    ├── com.example.library/
    │   ├── module-info.java
    │   └── com/example/library/Greeter.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
~~~

File src/com.example.library/module-info.java:

~~~java
module com.example.library {
    exports com.example.library;
}
~~~

File src/com.example.library/com/example/library/Greeter.java:

~~~java
package com.example.library;

public final class Greeter {
    private Greeter() {}

    public static String message() {
        return "Xin chao JPMS";
    }
}
~~~

File src/com.example.app/module-info.java intentionally omits requires:

~~~java
module com.example.app {
}
~~~

File src/com.example.app/com/example/app/Main.java:

~~~java
package com.example.app;

import com.example.library.Greeter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.message());
    }
}
~~~

### 4.2. Compile the Library First

From the jpms-demo directory:

~~~bash
mkdir -p mods

javac \
  --module-source-path src \
  -d mods \
  -m com.example.library
~~~

The output is an exploded module in mods/com.example.library.

### 4.3. Compile the App Using a Temporary Exception

Without declaring requires, compiling the app in the standard modular way will encounter a readability issue. During a migration where the module descriptor cannot be modified immediately, you can add the module and read edge at compile time:

~~~bash
javac \
  --module-source-path src \
  --module-path mods \
  --add-modules com.example.library \
  --add-reads com.example.app=com.example.library \
  -d mods \
  -m com.example.app
~~~

These options solve the exact two steps: ensuring the library module is resolved in the compilation context and allowing the app module to read the library. Compiler options must be compatible with the JDK currently in use and the specific module descriptors of the project.

Specifying --add-modules without --add-reads does not mean the compiler is allowed to use the API from the app. Conversely, adding only --add-reads when the library is not yet observable/resolved is also insufficient.

### 4.4. Run the App with the Two Corresponding Options

~~~bash
java \
  --module-path mods \
  --add-modules com.example.library \
  --add-reads com.example.app=com.example.library \
  --module com.example.app/com.example.app.Main
~~~

Sample output:

~~~text
Xin chao JPMS
~~~

Important: this example explains the mechanics of the two options; **it does not recommend keeping modules built without requires**.

### 4.5. Sustainable Fix

Once the module descriptor can be modified, update the app to:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

Then recompile according to standard JPMS rules:

~~~bash
javac \
  --module-source-path src \
  -d mods \
  -m com.example.library,com.example.app
~~~

Run without exceptions:

~~~bash
java \
  --module-path mods \
  --module com.example.app/com.example.app.Main
~~~

Now the dependency is part of the module contract; the compiler, IDE, packaging, and runtime all have the same information. This is typically the desired end state for the --add-reads exception.

### 4.6. Windows Notes

In the example above, --module-path uses only one directory mods, so no path separator is needed. If the module path has multiple paths, Linux/macOS typically uses a colon, while Windows uses a semicolon.

~~~bash
# Linux/macOS
java --module-path "mods:third-party" -m com.example.app/com.example.app.Main
~~~

~~~powershell
# Windows PowerShell
java --module-path "mods;third-party" -m com.example.app/com.example.app.Main
~~~

When invoking commands directly via PowerShell, pay attention to quoting rules; when specifying options in Gradle/Maven, the structure for passing individual arguments usually differs from typing a single shell string.

## 5. Practical Scenario: Named Module Reading a Legacy Library on the Classpath

Many applications cannot convert all JARs into named modules at once. Suppose com.company.orders already has a module descriptor, but an older library only runs properly on the classpath.

~~~text
mods/
  com.company.orders/
legacy/
  legacy-client.jar
~~~

A temporary launch command might be:

~~~bash
java \
  --module-path mods \
  --class-path "legacy/*" \
  --add-reads com.company.orders=ALL-UNNAMED \
  -m com.company.orders/com.company.orders.Main
~~~

Key points to understand:

1. --class-path places the legacy JAR into the unnamed module.
2. --add-reads adds a read edge from com.company.orders to the unnamed modules.
3. This option does not turn legacy-client.jar into a named module.
4. The classpath configuration must still be correct, including transitive JARs and class loading order.
5. For code that compiles directly against legacy-client.jar, the compiler also needs the appropriate classpath and read edge.

A long-term direction is to upgrade the library to one with JPMS support, move it to an automatic module with a controlled name, or isolate an adapter layer to limit the code surface exposed to the legacy dependency. Each direction has its own risks: automatic module names can be unstable, the module path can encounter split packages, and an adapter may require API migration and behavioral testing.

### 5.1. Do Not Force Every JAR onto the Module Path at All Costs

Some older libraries have:
- Overlapping packages across multiple JARs.
- Custom class loader mechanisms.
- Classpath-dependent service/resource discovery.
- Deep reflection into unexported packages.
- Derived automatic module names that easily change when the artifact is renamed.

Moving them onto the module path immediately can create new issues. Keeping a portion on the classpath during the transition period is a controlled choice, but its boundaries and end date must be clearly documented.

## 6. Support Scope of Options in Build and Runtime

A dangerous discrepancy: the application **compiles successfully** with --add-reads, yet at runtime it lacks the same option; or the application runs on a developer's machine, yet the test runner/production process does not have that option.

| Context | What to verify |
|---|---|
| javac | Module source/path, resolved dependencies, --add-modules, --add-reads at compile time |
| java | Module path, classpath, root modules, read edges of the runtime process |
| Test JVM | JVM args configuration of each fork/test worker; does not match compile by default |
| IDE run configuration | Whether the same JDK and module VM options are used |
| Gradle/Maven | The build tool process is separate from the compiler/test/app processes |
| Container/service | ENTRYPOINT, command, args, launcher script, and environment |
| jlink image | Whether the needed system modules are actually inside the image |
| Plugin/module layer | Which layer the module is loaded in; whether command-line options apply to that layer |

JPMS can involve multiple module layers/class loaders. Launcher options modify the boot layer's graph accordingly; they are not a blank check to modify every layer dynamically created by the application. If a framework creates its own layer, you need to inspect that layer's API and resolution mechanism rather than assuming command-line options solved everything.

### 6.1. Gradle: Separating Compile and Run/Test Arguments

With the Gradle Java plugin, compiler arguments and JVM runtime arguments are separate configurations. Conceptual example of a JavaExec task, not a complete project configuration:

~~~groovy
tasks.named("runOldModule", JavaExec) {
    jvmArgs(
        "--add-modules", "com.example.library",
        "--add-reads", "com.example.app=com.example.library"
    )
}
~~~

This only illustrates how to pass individual JVM options. If JavaExec runs on the classpath instead of the module path, or if the task has not properly configured mainModule, mainClass, and module-path, these options do not replace the missing configuration.

Compilation may need its own compiler args, and the test task may need its own jvmArgs. Do not assume that adding jvmArgs to the Gradle daemon will automatically carry over to the JVM running the application.

### 6.2. Maven: Compiler, Surefire, and Runtime Are Separate Steps

In Maven, the compiler plugin, test runner (such as Surefire/Failsafe), and application execution step may spawn separate JVM processes. Options used in javac do not automatically appear in forked test processes. When tests rely on module exceptions, you must ensure the test runtime configuration reflects the exact scope required and does not overwrite test framework options.

Conceptual Java launcher example:

~~~bash
java --module-path target/modules \
  --add-modules com.example.library \
  --add-reads com.example.app=com.example.library \
  -m com.example.app/com.example.app.Main
~~~

Record the final command generated by the build/plugin, rather than looking only at a single property in the POM.

### 6.3. Do Not Replace Module Options with Uncontrolled Environment Options

Variables such as JAVA_TOOL_OPTIONS or JDK_JAVA_OPTIONS can inject JVM/launcher options, but the scope and timing of when they are processed depend on the mechanism. Putting --add-reads into a shared environment variable can unintentionally apply it to build tools, tests, workers, and unrelated applications.

Prefer per-process/per-task configuration that has an owner, review, and documentation. If environment injection in a container is unavoidable, you must verify that the option actually takes effect for the target launcher.

## 7. Diagnosing Errors: Missing Module, Missing Readability, or Missing Exports?

### 7.1. Verify the Runtime and Observable Modules

~~~bash
java --version
java --list-modules
jar --describe-module --file lib/example-library.jar
~~~

jar --describe-module helps inspect the module descriptor of a modular JAR or automatic module information when appropriate. If the module name is not as expected, --add-modules or --add-reads with the wrong name will not work.

For the application module:

~~~bash
java --show-module-resolution \
  --module-path mods \
  --add-modules com.example.library \
  -m com.example.app/com.example.app.Main
~~~

See which modules are resolved and which roots/dependencies are selected.

### 7.2. Inspect Static Dependencies with jdeps

~~~bash
jdeps --module-path mods \
  --print-module-deps \
  app.jar
~~~

Or for a packaged named module:

~~~bash
jdeps --module-path mods \
  --check com.example.app
~~~

jdeps can help detect module dependencies of bytecode and validate descriptors according to the corresponding mode. However, reflection, name-based ServiceLoader, Class.forName, and runtime plugins may not be fully captured by static reference analysis.

### 7.3. Symptom Classification Table

| Message/symptom | Cause to check first | Resolution approach |
|---|---|---|
| Module ... not found | Module is not observable or module name is wrong | Check module path, name, and runtime image |
| Package ... is not visible / module A does not read B | Missing read edge | Declare requires or temporarily use --add-reads |
| Module B does not export package ... to A | Package is not exported appropriately | Fix API/module descriptor; consider temporary --add-exports |
| InaccessibleObjectException | Deep reflection is blocked | Adjust reflection/API, opens, or scoped --add-opens |
| NoClassDefFoundError / ClassNotFoundException | Class loader, resolution, or missing dependency | Locate the source class and actual runtime graph |
| LayerInstantiationException / split package | Conflicting module graph or package ownership | Fix packaging/module path; do not add modules indiscriminately |
| UnsupportedClassVersionError | Bytecode requires a newer JDK | Check major version and target runtime |
| Plugin not found even though JAR is on the module path | Plugin module is not resolved or ServiceLoader config is wrong | Check provider, uses/provides, root modules, and runtime layer |

A good diagnostic approach does not merely ask "can we add a flag to make it run?", it asks "is it failing at resolution, readability, accessibility, or class loading?"

### 7.4. What Happens If an Option Is Placed in the Wrong Position?

With the Java launcher, options must be passed in the JVM/launcher options section, before the main class, -jar target, or -m target according to the respective syntax.

Correct:

~~~bash
java --add-modules com.example.library \
  --module-path mods \
  -m com.example.app/com.example.app.Main
~~~

Wrongly used if passed as an application argument:

~~~bash
java -m com.example.app/com.example.app.Main \
  --add-modules com.example.library
~~~

In the second command, everything after the main target is passed as an argument to the program, no longer serving as an option for the Java launcher to modify the module graph. A similar issue can occur when translating launch commands between shells, Docker ENTRYPOINT/CMD, or a service manager.

## 8. Why Should They Only Be Used Temporarily During Migration?

--add-modules and --add-reads are useful options and can be valid in many well-designed long-term scenarios, especially with plugins or an operator-controlled launcher environment. However, when used to **compensate for an imprecise JPMS structure**, they should be treated as time-bound exceptions.

### 8.1. Risks of Keeping Flags as Hidden Dependencies

- **Hard-to-reproduce configuration:** build, test, IDE, and production end up with different sets of options.
- **Undeclared dependencies:** module-info.java does not reflect what the source or runtime requires.
- **Overly broad scope:** ALL-MODULE-PATH resolves unrelated modules; ALL-UNNAMED opens a bridge to the entire classpath.
- **Temporarily masked errors:** the module becomes readable, yet packages remain unexported, reflection remains blocked, or APIs are incompatible.
- **Harder version upgrades:** changes in automatic module names, dependency graphs, and runtime images can break the flags.
- **Unclear ownership:** an option placed in a shared environment may be passed into multiple processes that nobody manages.
- **Security/architectural cost:** widening access paths between named modules and the unnamed module can weaken designed encapsulation boundaries.

Not every read edge is a security issue: JPMS primarily provides encapsulation and reliability of the module graph. Even so, granting broader access should be evaluated in the same context of controlling dependencies and minimizing unintended access.

### 8.2. What Should a Temporary Exception Record Contain?

Example description in an issue or deployment document:

| Field | Example |
|---|---|
| Process | orders-service on JDK 21 |
| Flag | --add-reads com.company.orders=ALL-UNNAMED |
| Reason | legacy-client library is not yet modularized |
| Owner | orders-platform team |
| Scope | only run/test/production tasks of orders-service |
| Evidence | compile/runtime error when removing the flag, stack trace, and module graph |
| Risk | classpath dependency cannot yet be described in module-info |
| Replacement plan | upgrade legacy-client and move to an appropriate named/automatic module |
| Removal condition | build, tests, and runtime run without the flag |
| Review date | next dependency upgrade cycle |
| Tracking | related issue/PR and compatibility tests |

A good exception **describes its specific purpose**, rather than being a list of options copied from a stack trace on the Internet.

### 8.3. Narrowest Possible Scope

Prefer:

~~~bash
--add-modules com.company.legacyadapter
--add-reads com.company.orders=com.company.legacyadapter
~~~

instead of:

~~~bash
--add-modules ALL-MODULE-PATH
--add-reads com.company.orders=ALL-UNNAMED
~~~

if a solution targeting a specific module name is already sufficient. ALL-UNNAMED may truly be necessary when a legacy JAR resides on the classpath; in that case, document the reason and identify the list of involved classpath libraries rather than treating it as a default permission for every module.

Do not pile on --add-exports or --add-opens in a chain simply because adding --add-reads was not enough. Each option must correspond to a distinct error and a corresponding removal plan.

## 9. Roadmap for Removing Temporary Flags

### Step 1: Establish a Baseline and Reproduce the Error

Save the actual command, JDK vendor/version, module path, classpath, and the error when removing the flag. Run in an environment that simulates the production process. Do not rely on an IDE with a different configuration.

### Step 2: Identify the Actual Module Graph

Use --show-module-resolution, jar --describe-module, and jdeps. Identify which modules are observable, which modules are resolved, which modules need readability, and which packages are not yet exported.

### Step 3: Distinguish Cause from Symptoms

If a module is not resolved, find out why it is missing from the graph: missing requires, missing root, service/plugin discovery, or wrong module path. If the module is resolved but not readable, find the missing dependency in module-info.java. If only reflection fails, check opens and how the library uses reflection.

### Step 4: Replace with Explicit Dependency/Module Descriptors

Common approaches:
- Add requires to the module-info.java of the module that actually owns the dependency.
- If the public API of module A exposes types belonging to B, consider requires transitive when appropriate.
- Adjust exports/opens for the exact package and exact consumer, rather than granting global access.
- Upgrade the legacy library to support JPMS or confine it behind an adapter.
- Fix provider/uses/provides when ServiceLoader-based discovery is the cause.
- Fix the module path, eliminate split packages, and ensure the runtime image contains the required modules.

### Step 5: Remove Options Step by Step

Remove each narrow flag that has been replaced by a proper descriptor or dependency one by one, and run compilation, unit tests, integration tests, and smoke tests on the target JDK. If there are multiple flags, removing them one at a time helps reveal which exceptions are still needed.

### Step 6: Prevent Regressions with CI

Once the JPMS structure is stable, verify that the main tasks run without the old bypass flags. You can add launcher configuration checks to prevent flags from creeping back in via copied templates. Maintain the necessary logs/diagnostics to identify issues during future JDK or dependency upgrades.

## 10. Illustrative Migration Scenario

A system initially ran on the classpath with JDK 8. When migrating to JDK 21, the team creates module-info.java for the application and moves newer business libraries onto the module path. Several older JARs remain on the classpath.

Observed symptoms:

1. A plugin JAR is present on the module path, yet the application cannot see the provider: check root resolution and ServiceLoader configuration; if needed, temporarily add the plugin module with --add-modules.
2. The app's source imports a public type from another library module, but the descriptor lacks requires: for transition you can add --add-reads, then update module-info.java.
3. The app needs to call legacy classes on the classpath: use --add-reads app=ALL-UNNAMED with an explicit scope, then upgrade or wrap the legacy library.
4. Reflection into an internal package still fails: do not add --add-reads as a catch-all fix; review opens, framework versions, and API replacements.
5. A custom jlink runtime image lacks a required module: rebuild the image with the appropriate modules rather than only changing command-line flags.

After reproducing, record the exact options of every process across build, test, and deployment. Plan to replace each flag with a sustainable module structure, while also verifying application behavior rather than merely checking that the JVM starts successfully.

## 11. Common Misconceptions

- **A module being on the module path means the app can read it:** false; it also requires a resolved graph and readability.
- **--add-modules automatically creates a read edge:** false; the option adds a root and does not automatically make A read B.
- **--add-reads automatically resolves a missing module:** false; the target module name must be properly handled by resolution.
- **--add-reads automatically exports/opens packages:** false; that is a separate relationship.
- **Named modules can read the classpath by default:** usually requires explicit handling; ALL-UNNAMED is a temporary bridge during migration.
- **ALL-MODULE-PATH is the easiest and safest way:** overly broad resolution can cause conflicts and hide incorrect dependency structures.
- **Adding flags only to javac is enough:** the runtime and test JVMs may need corresponding options.
- **Adding flags to the Gradle daemon automatically affects the app:** no; each JVM/task has its own configuration.
- **All JPMS errors are caused by upgrading the JDK version:** they may be caused by the module path, class loaders, automatic module names, split packages, or descriptors.
- **A runtime image can load an unpackaged module:** no; a custom image with stripped modules must be modified.
- **There is no need to track temporary flags:** ownerless exceptions often linger for years and increase future migration costs.
- **Running successfully means behavioral compatibility:** successful module resolution does not prove that reflection, serialization, plugin discovery, and business contracts are all correct.

## 12. Checklist Before Accepting a Module Exception

- [ ] Identified the JDK vendor/version and the actual launch command of the process.
- [ ] Distinguished between classpath, module path, and custom runtime image.
- [ ] Verified the JPMS name of each module, including automatic modules.
- [ ] Determined which modules are observable, resolved, and readable.
- [ ] Identified whether a root module or a read edge is missing; did not add both options out of habit.
- [ ] Distinguished readability from exports and opens.
- [ ] If using ALL-UNNAMED, documented specifically which classpath libraries need the bridge.
- [ ] Applied options appropriately across javac, the Java launcher, and the test JVM as needed.
- [ ] Reviewed the scope to avoid ALL-MODULE-PATH or unnecessarily broad flags.
- [ ] Verified that the runtime image contains all required modules, not just the module path.
- [ ] Executed relevant functional flows, plugin discovery, and reflection.
- [ ] Each exception has an owner, reason, evidence, removal condition, and review date.
- [ ] Created a plan to replace with requires, exports/opens, an adapter, or dependency updates.
- [ ] Verified that the flag removal step does not break build, tests, and runtime.

## 13. Conclusion

In JPMS, **--add-modules** adjusts which modules are included during resolution, whereas **--add-reads** adjusts the read relationship from a named module to another module or unnamed modules. The two options address two distinct links in the module graph; they do not replace exports, opens, Java access rules, or bytecode and API compatibility.

During migration, use them to solve an identified issue with a narrow scope and concrete evidence. For static dependencies between named modules, the destination is usually declaring requires properly in module-info.java; for legacy libraries, a plan is needed to modularize, upgrade dependencies, or create an adapter. Exceptions should only be retained when they have an owner, tests, and a review deadline, so that temporary configuration does not become a hidden long-term dependency of the application.
