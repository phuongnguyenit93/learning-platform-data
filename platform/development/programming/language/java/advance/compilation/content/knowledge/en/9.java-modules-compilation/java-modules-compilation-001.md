# Why Is Module Path Different from Classpath in Java?

## 1. Goal

In Java, **classpath** is the traditional mechanism for finding classes and JARs, whereas **module path** is used by the Java Platform Module System (JPMS) to locate **named modules**, resolve dependency relationships, and enforce access boundaries specified by module descriptors.

Both mechanisms can point to .class files or JARs, yet they carry different meanings:

- Classpath mainly answers the question: **where are this class and resource located?**
- Module path additionally answers: **which module does the class belong to, which module reads which module, which package is allowed to be accessed from the outside, and which package is opened for reflection?**

JPMS appeared in Java 9. This lesson uses **Java 17+**, manually compiles two modules, reruns the same source using classpath, observes the output, and explains automatic/unnamed modules, module-info.java, requires, exports, opens, common errors, and how to migrate legacy applications.

## 2. Practical Comparison Table

| Aspect | Classpath | Module path |
| --- | --- | --- |
| Lookup unit | Class/resource in a directory or JAR | Named module from a modular JAR, exploded module, and automatic module |
| Module name | Classpath application code is usually in an unnamed module | Named module has a stable name according to its descriptor or automatic module rules |
| Dependency declaration | Usually configured by the application and Maven/Gradle outside classes | Explicit module has requires in module-info.java |
| Resolution | Class loader locates classes according to loading mechanisms and paths | Module resolver determines root modules and the dependency graph |
| Package boundaries | Java access modifiers; no separate export contract for traditional JARs | Must satisfy module readability and package exports along with Java access modifiers |
| Deep reflection | Depends on actual class/module and runtime rules | For named modules, usually requires opens for non-public reflective access |
| Common errors | ClassNotFoundException, NoClassDefFoundError, JAR conflicts | FindException, readability errors, package not exported, InaccessibleObjectException |
| Tools | javac -cp, java -cp | javac --module-path, java --module-path, --module-source-path |

You cannot simply rename the -cp option to --module-path and expect every library to automatically have the right module structure. Module path participates in a **module model resolution and verification** mechanism, not merely a list of directories.

## 3. How Classpath Works

Example command:

~~~sh
java -cp out com.example.app.Main
~~~

Given the class name com.example.app.Main, the application class loader can find the file:

~~~text
out/com/example/app/Main.class
~~~

If there are library JARs, those JARs must be placed on the classpath appropriately. The class loader looks up classes across the list of locations and corresponding class-loading rules. This mechanism does not require each JAR to declare a module-info.class stating which modules it requires and which packages it exports.

A public class in a classpath library can usually be referenced by other classpath code if the library is present and Java access rules allow it. The problem is the lack of a package boundary checked through a module descriptor: even a package named internal by the author can contain public types used by clients.

A large program often relies on Maven/Gradle to manage dependencies, but **a build tool dependency is not synonymous with a requires relationship in JPMS**. The build tool helps select and place JARs in the right locations; the module descriptor describes a module's readability and API at compile time and runtime.

Classpath remains a valid choice for many applications. Understanding its limitations helps you know when the module path brings benefits.

## 4. What Does JPMS Add?

JPMS allows a module to declare:

~~~java
module com.example.app {
    requires com.example.greetings;
}
~~~

And the library module declares:

~~~java
module com.example.greetings {
    exports com.example.greetings.api;
}
~~~

Logical structure:

~~~text
com.example.app
     |
     | requires com.example.greetings
     v
com.example.greetings
     |
     | exports com.example.greetings.api
     v
Public APIs of package api are used by other modules
~~~

When an application uses named modules, the system resolves a graph from the root modules and requires declarations. A class in another module may exist on the module path and still be **inaccessible** because the calling module does not read that module or the package is not exported.

A module can contain multiple packages. **A module name is not required to match a package name**. Having identical prefixes is only a convention to help organization.

## 5. Three Module Types to Distinguish

### Explicit named module

A module that has a module-info.class descriptor compiled from module-info.java. The descriptor has a module name and declarations such as requires, exports, opens, uses, and provides. When the artifact is resolved on the module path, the system applies the corresponding constraints.

### Unnamed module

Classes loaded from the classpath belong to an **unnamed module** of the corresponding class loader. An unnamed module has no module name for an explicit module to write requires against in the usual way. It has special rules for compatibility with legacy classpath code.

Do not assume the entire JVM has only a single unnamed module: different class loaders can have different unnamed modules. In the simple example using the application class loader, the classes together in cpout reside in one unnamed module.

### Automatic module

A JAR without module-info.class can still become an **automatic named module** when placed on the module path under JPMS rules. The module name can come from the manifest's Automatic-Module-Name or be derived from the JAR name. An automatic module has special rules to ease migration, including exporting its packages and readability appropriate to the automatic modules mechanism.

Therefore, **a plain JAR on the module path does not automatically have the same level of encapsulation as an explicit module**. When depending on an automatic module, you should choose an artifact with a stable module name, avoiding a derived name that unexpectedly changes when the filename or version changes.

## 6. What Does module-info.java Describe?

Some important declarations:

| Declaration | Meaning |
| --- | --- |
| module m { ... } | Defines a module named m |
| requires m; | The current module reads/depends on m |
| requires transitive m; | Propagates the readability relationship of m to modules that read the current module according to implied readability rules |
| requires static m; | A dependency needed at compile time but not necessarily present during runtime resolution |
| exports p; | Exposes the regular API of package p to modules that read this module |
| exports p to m; | Exports package p restricted to module m |
| opens p; | Opens package p for deep reflection |
| opens p to m; | Opens package p for reflection by module m |
| uses service.Type; | The module uses a service |
| provides service.Type with impl.Provider; | The module provides an implementation of the service |

Every module implicitly reads **java.base**. Therefore, a basic module does not need to write requires java.base. If you need APIs belonging to another JDK module, such as java.sql, an explicit named module's code usually has to declare requires java.sql.

Declarations in module-info.java are part of the module model: **placing a JAR on the module path does not automatically add requires to the application's descriptor**.

### Readability and accessibility are two separate conditions

For code in com.example.app to call public Greeter from com.example.greetings, three conditions are needed:

1. App has a readability relationship to com.example.greetings, for example via requires.
2. com.example.greetings exports the package containing Greeter to app.
3. Greeter itself and the member being called have compatible Java access permissions, such as public.

Having requires without exports still restricts the API. Having exports while app does not read the library module also does not satisfy the conditions. An internal package containing a public class can still be unusable from another module.

## 7. Two-Module Sample Project

Create the **module-lab** directory with the structure:

~~~text
module-lab/
└── src/
    ├── com.example.greetings/
    │   ├── module-info.java
    │   └── com/
    │       └── example/
    │           └── greetings/
    │               ├── api/
    │               │   └── Greeter.java
    │               └── internal/
    │                   └── Hidden.java
    └── com.example.app/
        ├── module-info.java
        └── com/
            └── example/
                └── app/
                    └── Main.java
~~~

Under src, the directory names **com.example.greetings** and **com.example.app** correspond to the module names. Inside each module, the com/example/... paths follow the standard package structure.

### File src/com.example.greetings/module-info.java

~~~java
module com.example.greetings {
    exports com.example.greetings.api;
}
~~~

The library module exports the api package. The internal package is not exported, even though it may contain public classes.

### File src/com.example.greetings/com/example/greetings/api/Greeter.java

~~~java
package com.example.greetings.api;

public final class Greeter {
    private Greeter() {
    }

    public static String hello(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

### File src/com.example.greetings/com/example/greetings/internal/Hidden.java

~~~java
package com.example.greetings.internal;

public final class Hidden {
    private Hidden() {
    }

    public static String secret() {
        return "internal";
    }
}
~~~

Hidden is declared public, yet its package is not exported. This is an example showing that the public modifier is **not enough** to remove the boundary between two named modules.

### File src/com.example.app/module-info.java

~~~java
module com.example.app {
    requires com.example.greetings;
}
~~~

This is the dependency edge from app to the library. The app module can read the library module; the library's api package is exported so app can use Greeter.

### File src/com.example.app/com/example/app/Main.java

~~~java
package com.example.app;

import com.example.greetings.api.Greeter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.hello("Lan"));
        System.out.println("App named: "
                + Main.class.getModule().isNamed());
        System.out.println("Lib named: "
                + Greeter.class.getModule().isNamed());
    }
}
~~~

The getModule().isNamed() method lets you observe whether a class belongs to a named module or an unnamed module. This exercise requires no external libraries and is suitable for Java 17.

## 8. Compiling and Running with Module Path

Set the terminal's CWD to the **module-lab** root, that is, the directory containing src.

On Bash:

~~~bash
mkdir -p mods
~~~

On PowerShell:

~~~powershell
New-Item -ItemType Directory -Path mods -Force | Out-Null
~~~

Compile both modules:

~~~sh
javac --release 17 --module-source-path src -d mods -m com.example.greetings,com.example.app
~~~

Meaning of each option:

- **--module-source-path src**: root of the modular source tree, containing directories named after modules.
- **-d mods**: writes each module's class files into the output directory tree.
- **-m com.example.greetings,com.example.app**: in the javac context, lists the names of the source modules to compile.

After compiling, main output:

~~~text
mods/
├── com.example.greetings/
│   ├── module-info.class
│   └── com/example/greetings/
│       ├── api/Greeter.class
│       └── internal/Hidden.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
~~~

The mods path is an entry on the module path containing two **exploded modules**. Each subdirectory carries the module name and contains module-info.class.

Run from the same CWD:

~~~sh
java --module-path mods -m com.example.app/com.example.app.Main
~~~

**Exact stdout:**

~~~text
Hello, Lan!
App named: true
Lib named: true
~~~

When the Java launcher resolves the root module com.example.app, the requires relationship pulls com.example.greetings into the graph; the Main and Greeter classes are loaded in their respective named modules. The -m option of java has the form moduleName/mainClass. If the module already has appropriate main class metadata, the /mainClass part can sometimes be omitted; this example intentionally writes it in full for clarity.

**Do not confuse the three paths:**

| Path | Tool | Meaning |
| --- | --- | --- |
| --module-source-path src | javac | Where to locate module sources |
| -d mods | javac | Where to write module bytecode |
| --module-path mods | java | Where to find module artifacts for resolution and execution |

If you compile app separately after the library module has already been compiled, javac may need --module-path mods to see the module dependency as bytecode. Module source path and module path play two different roles.

## 9. Same Java Code, Compiled and Run with Classpath

Keep **Greeter.java and Main.java** unchanged. In the classpath mode below, explicitly compile only the two source class files without including the two module-info.java files in the javac invocation.

From CWD = module-lab, create the output root:

~~~bash
mkdir -p cpout
~~~

~~~powershell
New-Item -ItemType Directory -Path cpout -Force | Out-Null
~~~

Compile:

~~~sh
javac --release 17 -d cpout src/com.example.greetings/com/example/greetings/api/Greeter.java src/com.example.app/com/example/app/Main.java
~~~

Run:

~~~sh
java -cp cpout com.example.app.Main
~~~

**Exact stdout:**

~~~text
Hello, Lan!
App named: false
Lib named: false
~~~

The two methods hello and main are unchanged. The difference comes from **how they are compiled and loaded**:

- In the classpath example, the compiler does not process module-info.java because they are not passed to the compilation run.
- The runtime looks up classes directly under cpout/com/example/... by package and class name.
- The two classes in the example belong to an unnamed module, so isNamed() returns false.
- No named-module graph of com.example.app and com.example.greetings is being used to check requires/exports between them.

| Comparison | Modular mode | Classpath mode |
| --- | --- | --- |
| Compile | javac --module-source-path src -d mods -m com.example.greetings,com.example.app | javac -d cpout with the two .java files |
| Run | java --module-path mods -m com.example.app/com.example.app.Main | java -cp cpout com.example.app.Main |
| Output root | mods/[moduleName]/[package]/Class.class | cpout/[package]/Class.class |
| App named | true | false |
| Lib named | true | false |

This is an important empirical proof: **a package name by itself does not turn a class into a named module**. The module descriptor and the module resolution/loading mode determine the difference.

### If a modular JAR is placed on the classpath

A JAR containing module-info.class can still be run via the classpath if the library supports that configuration. In that case, the module descriptor does not cause the JAR to be resolved as a named module just because module-info.class is inside. Conversely, a plain JAR without a descriptor can become an automatic module when placed on the module path. **Location and loading mechanism determine the role**, not just the filename.

## 10. Experimenting with Missing requires and Missing exports

The following modifications are **experiments to intentionally cause compilation errors**; restore the original source after testing.

### Experiment A — Removing requires

In src/com.example.app/module-info.java, temporarily remove the line:

~~~java
requires com.example.greetings;
~~~

Keep Main.java importing Greeter, then rerun the modular javac command. The compiler will not have the proper readability relationship for app to access the library package; the message usually mentions that the module does not read the module containing the package.

**Proper fix:** restore requires com.example.greetings. Simply adding files/JARs to the module path does not automatically add a requires edge for an explicit module.

### Experiment B — Public package without export

In Main.java, temporarily add:

~~~java
import com.example.greetings.internal.Hidden;
~~~

And inside main, try calling:

~~~java
System.out.println(Hidden.secret());
~~~

The lines above are **modifications within existing files**, not standalone programs. When compiled as named modules, javac denies access because com.example.greetings.internal is not exported to app, even though both Hidden and secret are public.

**Proper fix in library design:** use the API exposed by the com.example.greetings.api package. Only add exports for internal if you intentionally want to change the API boundary. You should not open every package just to compile past errors.

### Experiment C — Accessing the same class on the classpath

In a separate practice setup, compile Hidden.java into cpout as well and use a temporary Main.java that imports Hidden **without compiling module-info.java**. When the classpath contains the needed class, using public Hidden may be accepted because no named-module exports boundary exists for these two classes.

This illustrates **the difference between the two modes**, not a reason to expose internal classes to clients in real projects.

## 11. How Does Module Resolution Differ from Class Lookup?

**Classpath lookup** searches for classes by name and class loader mechanism. With multiple JARs containing the same binary class name, the class loader and configured source order can affect which class gets loaded. There is no mandatory module graph based on each JAR's requires.

**Module resolution** starts from the root modules, then locates the required modules via requires along with other JPMS rules. The system builds a module graph, determines readability, and checks related constraints. The JVM still uses class loaders to load classes, but named-module access adds restrictions compared to ordinary classpath lookup.

With:

~~~sh
java --module-path mods -m com.example.app/com.example.app.Main
~~~

com.example.app is the root module. com.example.greetings is pulled in because app has the corresponding requires. Simply placing a third module on the module path **does not guarantee that module will always be resolved**; there must be a root, a dependency edge, or an appropriate resolution option.

### Observing module configuration

From the module-lab root:

~~~sh
java --module-path mods --describe-module com.example.app
java --module-path mods --describe-module com.example.greetings
~~~

Commands describing descriptors/modules can show requires and exports. Exact output details may vary depending on the JDK version.

To print resolution information at runtime:

~~~sh
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main
~~~

This command also prints module resolution information. Therefore, **do not treat the full debug output as the standard three-line stdout** of the example program.

## 12. Automatic Module: How to Use JARs Without Descriptors

A plain JAR without module-info.class can be placed on the module path as an automatic module. It then receives a name determined via Automatic-Module-Name or filename-derivation rules, and benefits from the compatibility mechanism of automatic modules.

Things to remember:

- An automatic module **is named**, unlike the classpath's unnamed module.
- It typically exports all of its packages; it is not an explicit module whose API has been restricted per exports by the author.
- It has special readability rules to support migration.
- An explicit module can require the name of an automatic module.
- If the name is derived from the JAR filename, changing the artifact name can break the dependency declared in module-info.java.

An explicit named module cannot simply write requires for an unnamed module, which has no name. That is why migrating a multi-JAR application to the module path sometimes requires using automatic modules, replacing dependencies, or changing how modules are organized.

## 13. exports vs. opens

The JPMS model distinguishes between regular public API usage rights and deep access via reflection.

- **exports p**: appropriately reading modules can use accessible public types/members in package p according to Java rules.
- **opens p**: allows deep reflection into the package, such as reflective access to non-public members when runtime conditions are met.
- **exports p to m** and **opens p to m**: specify the target modules granted the corresponding permissions.
- **open module m**: opens the module's packages for reflection according to the rules of that module form.

Illustrative descriptor example, not a complete project:

~~~java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.entity to com.example.serializer;
}
~~~

The api package serves the regular API; entity is opened to a specific framework module. A package that is opened does not thereby automatically become a package exported to every module at compile time.

When a framework uses reflection (such as a serializer), a runtime **InaccessibleObjectException** can indicate that the module lacks the appropriate opens directive. The --add-opens option supports migration/diagnostics; in the long term, reflection boundaries should be placed intentionally.

**JPMS is not a security sandbox**: it controls module boundaries according to the language/JVM model, and does not replace operating system permissions or data protection mechanisms.

## 14. requires transitive and requires static

### requires transitive

Suppose a facade module exposes an API containing types belonging to a service module:

~~~text
app --requires--> facade --requires transitive--> service
~~~

When app reads facade, the **implied readability** relationship allows app to also read service according to requires transitive rules. This is useful if facade's public API exposes types from service.

However, requires transitive **does not automatically export all packages of service**. The package still has to be exported appropriately by service; Java access permission rules remain in effect.

### requires static

The requires static declaration is for a dependency needed at compile time but not required to be present when the module is resolved at runtime. It is commonly used for certain optional/annotation dependencies.

If the code actually needs a class from a missing dependency at runtime, it can still fail at runtime. **requires static does not guarantee that code referencing an absent dependency will always work**.

## 15. Split Packages and Conflicts

A **split package** occurs when multiple artifacts define classes in the same package, for example two JARs both containing com.example.shared.

The classpath can contain such JARs, although it easily causes ambiguity and version conflicts. JPMS places additional package restrictions among named modules within a configuration, especially when a module can read the same package from multiple sources. Depending on the module graph and loader, errors can occur during compilation or resolution with a message about a package conflict.

Do not conclude that all cases of same-named packages always fail identically; you must inspect the graph, exports, and readability. However, when designing explicit modules, **you should clearly assign which module owns each package**, avoiding arbitrarily splitting the same package across multiple JARs.

The module path also does not automatically resolve every version conflict or API mismatch. Even if the module graph resolves successfully, you still need to manage dependencies and run tests.

## 16. Classpath, Module Path, and JARs in Large Projects

Both paths can involve JARs, but they are interpreted differently:

- Classpath usually lists directories/JARs that provide classes.
- Module path lists locations containing modular JARs or exploded modules; eligible plain JARs can become automatic modules.
- A modular JAR has module-info.class; when recognized/resolved on the module path, named module boundaries take effect.
- When placed on the classpath, a modular JAR can run in classpath mode if dependencies and library code are compatible; the descriptor does not automatically turn it into a named module in that mode.

The classpath separator is usually **;** on Windows and **:** on Linux/macOS. The examples in this lesson use only one output directory, so no separator is needed.

Some special options:

| Option | Purpose |
| --- | --- |
| --module-path or -p | Where to locate module artifacts |
| --module or -m | Selects the root module/main in java; selects source modules in javac depending on context |
| --add-modules | Adds root modules for module resolution to consider |
| --add-reads | Adds module readability relationships in special configurations |
| --add-exports | Adds package export permissions in the configuration |
| --add-opens | Permits deep reflective access according to the configuration |
| --show-module-resolution | Prints module graph resolution when the launcher starts |

Do not try every --add-... option just to make errors disappear. Each option addresses a different kind of relationship and is usually only appropriate for controlled migration or debugging.

## 17. Troubleshooting Table

| Symptom | Cause to check | Resolution |
| --- | --- | --- |
| Module ... not found | Missing module artifact, wrong module name, wrong module path | Verify the name, module-info.class, module location, and path |
| package ... is not visible / module ... does not read | Missing readability relationship | Check requires and the graph |
| package ... is not exported | Dependency exists, but the package is not exported to the caller | Use the exported API or intentionally adjust the exports contract |
| Could not find or load main class | Wrong classpath root or fully qualified class name | Check -cp and package.Class |
| java.lang.module.FindException | Required module cannot be resolved | Check the module path, names, and dependencies |
| InaccessibleObjectException | Missing deep reflection permission into the package | Check opens and the caller module |
| Package conflict | Split package or invalid module graph | Check which modules contain the package and duplicate JARs |
| isNamed() unexpectedly false | Code is running via classpath/unnamed module | Check the java command and the actual loaded artifact |
| Runtime error despite successful compilation | Runtime path differs from compile path, stale artifact build | Compare compile/runtime dependencies and rebuild with the right scope |

Troubleshooting workflow:

1. Check javac -version and java -version, using JDK 17+ for this lesson.
2. Confirm the CWD, source paths, and output paths.
3. If using explicit modules, verify that module-info.java has been compiled into module-info.class.
4. Inspect requires in the calling module, exports in the library module, and the Java access modifiers of the class/member.
5. Distinguish between a missing artifact, a missing module graph edge, a missing export, and a missing opens.
6. Use --describe-module and --show-module-resolution when needed.
7. Verify which .class/JAR build is actually running; do not confuse cpout with mods.

## 18. When to Choose Which Mechanism?

**Classpath** is suitable for many existing applications, especially when libraries are not yet modularized and Maven/Gradle already manages packaging. Not every Java program needs to create module-info.java.

**Module path** is valuable when you want to design public API boundaries, declared dependency relationships, clear module resolution, and progressively leverage a modular runtime. JPMS also supports tools like jlink to build a custom runtime image from a suitable set of modules, though not every application needs a custom image.

A migrating project can combine classpath and module path, but you must understand named/unnamed/automatic modules; an explicit named module cannot simply write requires against an unnamed module. Migration requires checking dependencies, package conflicts, and framework reflection rather than merely changing launcher options.

## 19. Hands-On Practice Exercises

1. Create the two-module structure yourself and run javac --module-source-path src -d mods -m com.example.greetings,com.example.app. Verify that each module has module-info.class under mods.
2. Run in modular mode. Why are both App named and Lib named true?
3. Compile only the two source classes into cpout and run with -cp. Why are both values false even though the hello logic is identical?
4. Temporarily remove requires from app, recompile in modular mode, and analyze the readability error message.
5. Temporarily import Hidden. Why can a public class still not be used from another named module if its package is not exported?
6. Inspect the descriptor with --describe-module; try --show-module-resolution and identify the root module as well as its dependencies.
7. Explain in your own words the difference between exports and opens, and give an example of a framework case requiring deep reflection.
8. Suppose a plain JAR is placed on the module path. How can it be recognized, and why can a name derived from its filename pose risks?
9. Explain why module path is not merely classpath by another name and why build tools still play a role in JPMS applications.

## 20. Knowledge Check

- Classpath looks up classes/JARs; module path participates in recognizing named modules and building the module graph.
- An explicit module has module-info.java, which is compiled into module-info.class.
- requires establishes a readability relationship; exports exposes a package; opens serves deep reflection.
- A public class inside an unexported package can still be inaccessible from another named module.
- Classes on the classpath belong to the unnamed module of the corresponding class loader.
- A plain JAR on the module path can become an automatic module, without carrying all the restrictions of an explicit descriptor.
- Not every module present on the module path is resolved without an appropriate root/dependency.
- JPMS does not replace Maven/Gradle, does not automatically resolve all version conflicts, and is not a security sandbox.
- Module path commands select the root module with -m; classpath commands select the main class by its fully qualified name.
- The same source code can run in two modes with different access contracts.

### Further Reading

- **Java Language Specification**: sections on *Modules*, *Accessibility*, and module declaration requirements.
- **Java Virtual Machine Specification**: the module-info.class format and module-based access control.
- **OpenJDK JPMS**: *The State of the Module System* and documentation explaining module resolution.
- Official **java**, **javac**, **jar**, and **jlink** documentation for your JDK version to verify command-line syntax.

**Key takeaway:** classpath is the traditional class-lookup mechanism; module path organizes classes under named modules with descriptors, dependency graphs, and export/reflective access boundaries. The primary difference lies in **module semantics and how Java resolves, loads, and checks access permissions**, not merely in the two terminal option names.
