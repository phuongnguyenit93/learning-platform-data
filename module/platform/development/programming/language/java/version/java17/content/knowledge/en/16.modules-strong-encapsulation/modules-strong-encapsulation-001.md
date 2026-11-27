# Named Modules, Unnamed Modules, and Automatic Modules in Java 17

> **Topic:** Java 17
> **Chapter:** Modules and Strong Encapsulation

## 1. Overview

The Java Platform Module System (JPMS) groups packages into modules. A module can declare dependencies, specify which packages are exposed publicly, and restrict reflective access. In Java 17, there are three cases to distinguish:

1. **Named module:** a module with a name and a descriptor declared via `module-info.java` or `module-info.class`.
2. **Unnamed module:** a module without a name, typically containing classes loaded from the classpath.
3. **Automatic module:** a JAR without a module descriptor that is placed on the module path; Java synthesizes a named module from that JAR.

An automatic module is still a **named module**. The difference is that its descriptor is derived rather than explicitly declared by the author.

## 2. Named Module: Explicitly Declared Module

A named module has a valid name and a descriptor. For source code, the descriptor resides in `module-info.java` at the root of the module source tree. When compiled, this file becomes `module-info.class`.

### 2.1. Module descriptor example

Suppose an order management application needs to use logging and expose an API to other modules:

```java
module com.acme.orders {
    requires java.logging;

    exports com.acme.orders.api;

    opens com.acme.orders.persistence
        to com.fasterxml.jackson.databind;
}
```

The descriptor above expresses three relationships:

- `requires java.logging`: the current module needs to read the `java.logging` module.
- `exports com.acme.orders.api`: allows code in other modules to access `public`/`protected` types in the exported API package and their corresponding members.
- `opens com.acme.orders.persistence to ...`: allows the specified framework to use deep reflection on the persistence package at runtime, including on non-public members.

Module names typically follow the reverse-domain naming convention, for example `com.acme.orders`. A module name consists of one or more Java identifiers separated by dots. Package names and module names are distinct identifiers, even though they often follow the same convention.

### 2.2. Modules control both dependencies and exposed packages

A named module has two directions of control:

| Direction | Mechanism | Question answered |
|---|---|---|
| Current module uses other modules | `requires` | Which modules is my code allowed to read? |
| Other modules use current module | `exports` / `opens` | Which packages do I expose and where do I allow reflection? |

For example, if module `com.acme.orders` has a `public` class in package `com.acme.orders.internal` but does not export this package, code in other modules still cannot reference that class as a normal API. The `public` keyword does not cross module boundaries on its own.

This helps a module keep implementation details internal and publish a small, clear API surface.

### 2.3. Distinguishing requires, exports, and opens

```java
module com.acme.application {
    requires com.acme.orders;
}

module com.acme.orders {
    exports com.acme.orders.api;
}
```

`requires` establishes a **readability** relationship: the application module is permitted to read the orders module. However, reading a module does not automatically make all packages of orders accessible. A package must be exported by the orders module.

`exports` grants normal compile-time and runtime access to `public`/`protected` types and members in the exported package.

`opens` is primarily for runtime reflection. It does not make a package an API for other modules to import and reference types from at compile time.

| Directive | Normal code access | Reflection |
|---|---|---|
| `exports p;` | Yes, for `public` and `protected` types/members | Yes, with corresponding `public`/`protected` scope |
| `opens p;` | Does not grant compile-time reference access through that package | Allows deep reflection into types and members in the package |
| Neither exported nor opened | No | No, for code outside the module |

If a module uses a serialization, ORM, or dependency injection framework that needs deep reflection, open only the specific packages for the corresponding framework instead of opening the entire module indiscriminately.

### 2.4. Open module

Java also allows declaring:

```java
open module com.acme.application {
    requires com.acme.orders;
    exports com.acme.application.api;
}
```

An `open module` opens all of its packages for reflection at runtime. It still only exports explicitly declared packages for normal access.

Within an `open module`, additional `opens` directives may not be written in the descriptor. If only a few packages need reflection, use a normal module with narrowly scoped `opens` directives.

## 3. Unnamed Module: Classes Not Belonging to a Named Module

The unnamed module is provided by Java so that code without module declarations can still run within the JPMS ecosystem. In the common execution model, classes and JARs placed on the **classpath** belong to the unnamed module of their corresponding class loader.

For example:

```bash
javac -d out src/com/example/Main.java
java -cp out com.example.Main
```

Or:

```bash
java -classpath "out;lib/example.jar" com.example.Main
```

In the second Windows example, a semicolon separates classpath entries. On Linux/macOS, the separator is a colon.

### 3.1. The unnamed module has no name

There is no module name to write in a `requires` directive. Therefore, another module cannot write:

```java
module com.acme.app {
    // No valid name exists to require the unnamed module.
}
```

When inspecting a class's module:

```java
Module module = Main.class.getModule();
System.out.println(module.getName());
```

If the class belongs to the unnamed module, `getName()` returns `null`.

### 3.2. The unnamed module reads all observable modules

The unnamed module has broad readability rules to support classpath code:

- It reads every observable module in the corresponding environment.
- It exports all packages belonging to that unnamed module.
- It opens all packages belonging to that unnamed module for reflection.

However, there is an important asymmetry: **a named module cannot use `requires` to read the unnamed module**. There is no valid module name to write in the descriptor, and compilation units of the unnamed module are not visible as normal dependencies to named modules.

For example, a legacy application running on the classpath can call the exported API of a named module when that module is present and resolved into the module graph. Conversely, a named module cannot simply write `requires` to use a library that remains on the classpath.

This is a critical difference when migrating an application from the classpath to the module path.

### 3.3. Unnamed module does not mean unnamed package

These two concepts are easily confused:

- **Unnamed package:** A Java source file without a `package` declaration.
- **Unnamed module:** A module without a name, typically containing classes from the classpath.

A class belonging to a named package such as `com.example.service` can still belong to the unnamed module if it is loaded from the classpath. Therefore, "unnamed module" does not mean all classes inside must omit package declarations.

### 3.4. The unnamed module and reflection

Packages of the unnamed module are treated as exported and opened. This provides high compatibility with legacy libraries that use reflection. However, you should not infer that a named module also has similar deep access to every package of other named modules.

For named modules, reflective access remains governed by `opens` or an `open module` declaration. This is part of the strong encapsulation mechanism.

## 4. Automatic Module: Legacy JAR Placed on the Module Path

A JAR might not yet contain `module-info.class` and still be used on the module path. In this case, Java creates an **automatic module**.

An automatic module is an implicitly declared named module. It allows libraries that have not yet migrated to JPMS to participate in the module graph so that other named modules can declare `requires` on them.

### 4.1. When does a JAR become an automatic module?

Basic recognition rules in Java 17:

| JAR location | Status |
|---|---|
| On classpath | Classes belong to the unnamed module |
| On module path, with module descriptor | Explicit named module |
| On module path, without module descriptor | Automatic module |

This means **the exact same JAR file without a module descriptor** can belong to an unnamed module or an automatic module depending on how it is launched:

```bash
# JAR treated as a classpath dependency
java -cp "app-classes;lib/legacy-json-2.4.1.jar" com.acme.Main

# JAR treated as an automatic module
java --module-path "mods;lib/legacy-json-2.4.1.jar" \
     --module com.acme.app/com.acme.Main
```

The command example above uses semicolons as on Windows. On Linux/macOS, replace them with colons.

### 4.2. Naming an automatic module

The module name is determined in the following order:

1. If the JAR's manifest has the `Automatic-Module-Name` attribute in its main attributes, use that value.
2. Otherwise, the system derives the name from the JAR file name.

Manifest example:

```text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.legacyjson
```

With this manifest, the module name is `com.acme.legacyjson` even though the file might be named `legacy-json-2.4.1.jar`.

If the attribute above is absent, Java 17 processes the file name in the following main steps:

- Strip the `.jar` suffix.
- If a recognizable version portion appears after a hyphen, separate the version portion from the module name.
- Replace non-ASCII-alphanumeric characters with dots.
- Collapse multiple consecutive dots into a single dot.
- Remove leading and trailing dots.

Examples:

| JAR file name | Derived automatic module name |
|---|---|
| `foo-bar.jar` | `foo.bar` |
| `legacy-json-2.4.1.jar` | `legacy.json` |
| `acme-client-3.0.jar` | `acme.client` |

File names can change when a library version is upgraded. Therefore, for libraries wishing to support JPMS users during a transition period, authors should declare a stable `Automatic-Module-Name` in the manifest. This prevents the module name from depending on the file name and version number.

### 4.3. What permissions does an automatic module have?

An automatic module has important characteristics:

- Has a name and participates in the module graph as a named module.
- Reads all other modules in the configuration, including unnamed modules.
- All of its packages are treated as exported.
- All of its packages are also treated as opened for reflection.
- Has no explicit module descriptor for the author to declare individual `requires`, `exports`, or `opens` directives like an explicit named module.

The "reads all modules" behavior makes automatic modules easy to bridge with legacy libraries. The "exports/opens all packages" behavior lets clients continue accessing APIs and using reflection without requiring the JAR author to design a module descriptor immediately.

However, these broad permissions also mean an automatic module does not yet provide strong encapsulation and clear API boundaries like an explicit named module.

### 4.4. Using an automatic module from a named module

Suppose `legacy-json-2.4.1.jar` has no `module-info.class` and its manifest has no `Automatic-Module-Name`. The derived module name is `legacy.json`.

A named module can declare:

```java
module com.acme.application {
    requires legacy.json;
}
```

Then the code can import public types in the JAR's packages, because an automatic module exports all packages.

Keep in mind that `legacy.json` is the module name, not necessarily the Java package name used by the library. Module names and package names are two separate naming systems.

### 4.5. Automatic modules are still subject to module conflict checks

Automatic modules do not bypass the rules of the module graph. For example:

- Two JARs deriving the same module name can cause a conflict when found at the same time.
- Split packages across modules that a module reads can cause resolution to fail.
- A module name derived from a file can change if the JAR naming scheme changes.

Do not use automatic modules as a way to skip dependency organization. Inspect module names, packages, and the application's dependency graph.

## 5. Comparing the Three Module Types

| Criterion | Explicit named module | Unnamed module | Automatic module |
|---|---|---|---|
| Has a module name? | Yes | No | Yes |
| Descriptor | Has `module-info.java`/`module-info.class` | No | Derived descriptor |
| Typically originates from | Modular source or modular JAR | Classes/JARs on classpath | Non-modular JAR on module path |
| Declares dependencies with `requires` | Yes | No | No explicit descriptor to declare them |
| Readability | Per module graph and `requires` | Reads all observable modules | Reads all modules in the configuration |
| Exported packages | Per `exports` | All packages of the module | All packages |
| Opened packages for reflection | Per `opens`/`open module` | All packages | All packages |
| Strong encapsulation | Explicitly controllable | No strict package boundaries like explicit modules | Broad, compatible, but less controlled |
| Common role | Modularized applications/libraries | Code running on classpath | Bridge for non-modularized JARs |

Identification diagram:

```text
classpath
   |
   v
unnamed module
   - unnamed
   - reads all observable modules
   - exports/opens all its packages

module path
   |
   +--> JAR with module-info.class
   |       |
   |       v
   |    explicit named module
   |       - author-declared descriptor
   |       - explicit requires/exports/opens
   |
   +--> JAR without module descriptor
           |
           v
        automatic module
           - name derived or taken from manifest
           - reads all modules
           - exports/opens all packages
```

## 6. Readability and Package Accessibility Are Two Separate Conditions

A common mistake when learning JPMS is thinking that simply having module A declare `requires B` allows A to access every class in B.

In reality, for code in module A to reference a type from module B, both conditions must generally be met:

1. **Readability:** A reads B, directly or through a relationship established by the module graph.
2. **Accessibility:** The package containing that type is exported by B to A, and the type/member satisfies Java access rules.

For example:

```java
module com.acme.orders {
    exports com.acme.orders.api;
}

module com.acme.web {
    requires com.acme.orders;
}
```

Code in `com.acme.web` can use the public API in `com.acme.orders.api`. However, it cannot reference a class in `com.acme.orders.internal` if that package is not exported.

### 6.1. requires transitive

`requires transitive` means the current module requires the target module and also propagates that readability to modules that depend on it.

For example:

```java
module com.acme.orders {
    requires transitive com.acme.money;
}

module com.acme.web {
    requires com.acme.orders;
}
```

In this case, `com.acme.web` reads `com.acme.money` through the transitive relationship of `com.acme.orders`. This is useful if the public API of orders exposes types belonging to money and users of orders need to read those types.

Do not add `transitive` to every dependency. It makes the dependency part of the module's usage contract and can make a client's dependency graph broader than intended.

### 6.2. requires static

`requires static` indicates a dependency that is mandatory at compile time but may be absent at runtime:

```java
module com.acme.library {
    requires static com.acme.optional.annotations;
}
```

It is suitable for dependencies only needed in certain compile-time scenarios, such as annotations or optional APIs. The code must ensure it does not invoke classes from that dependency along execution paths where the module is absent.

### 6.3. Named modules do not read the unnamed module

Asymmetry to remember:

- The unnamed module reads all observable modules.
- Automatic modules read all modules in the configuration, including the unnamed module.
- An explicit named module cannot declare `requires` on the unnamed module.

Therefore, if a named module needs to use a library currently on the classpath, move that library to the module path (if it can be used as an automatic module) or convert the library into a named module. Do not rely on a named module automatically seeing classes on the classpath.

## 7. Example Project Structure with Two Named Modules

A small project with an API module and an application module:

```text
src/
  com.acme.greeting/
    module-info.java
    com/acme/greeting/api/Greeter.java
  com.acme.app/
    module-info.java
    com/acme/app/Main.java
```

Library module:

```java
module com.acme.greeting {
    exports com.acme.greeting.api;
}
```

API class:

```java
package com.acme.greeting.api;

public class Greeter {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

Application module:

```java
module com.acme.app {
    requires com.acme.greeting;
}
```

Main class:

```java
package com.acme.app;

import com.acme.greeting.api.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(new Greeter().greet("Java 17"));
    }
}
```

Compile the modules from the source root:

```bash
javac --module-source-path src -d mods -m com.acme.greeting,com.acme.app
```

Run the application module:

```bash
java --module-path mods -m com.acme.app/com.acme.app.Main
```

Output:

```text
Hello, Java 17
```

In the run command:

- `--module-path mods` specifies where to find the modules.
- `-m` (or `--module`) selects the module and main class in the form `module/class`.
- The app module reads the greeting module because its descriptor declares `requires`.
- The API package is accessible because greeting declares `exports`.

## 8. Example Using a Library Without a Module Descriptor as an Automatic Module

Suppose the application has a JAR named `legacy-json-2.4.1.jar`. The JAR has no `module-info.class`. If placed on the module path without an `Automatic-Module-Name` manifest attribute, the name derived by Java 17 rules is `legacy.json`.

The application's module descriptor can be written as:

```java
module com.acme.application {
    requires legacy.json;
}
```

The code can then import public types in the JAR's packages, since an automatic module exports all packages.

Compiling and running require putting both the output modules and the JAR on the module path:

```bash
javac --module-path lib --module-source-path src -d mods -m com.acme.application
java --module-path "mods;lib/legacy-json-2.4.1.jar" \
     -m com.acme.application/com.acme.application.Main
```

If the application runs on Windows, use a semicolon to separate paths. On Linux/macOS, use a colon.

This example illustrates the module mechanism; actual package and class names should come from the API of the library being used. Do not assume every non-modular JAR can be placed on the module path immediately: the JAR must meet the requirements for forming an automatic module, such as not containing classes in the unnamed package and producing a valid module name.

## 9. Migration Path from Classpath to JPMS

Automatic modules and the unnamed module support a step-by-step migration process.

### Step 1 — Application still runs on the classpath

Application classes and dependencies on the classpath belong to the unnamed module. Code does not yet need `module-info.java`.

### Step 2 — Move some libraries to the module path

JARs that already have a module descriptor become explicit named modules. JARs without a descriptor become automatic modules. The classpath application can interact with modules it reads and their exported packages.

### Step 3 — Convert the application into a named module

Add `module-info.java` and declare `requires` for the needed dependencies. Dependencies remaining on the classpath will belong to the unnamed module and cannot be read by a named module via `requires`.

### Step 4 — Convert automatic dependencies to explicit modules when possible

When library authors provide explicit module descriptors, the application can use exported packages according to the published API. Module descriptors also help define dependencies and restrict reflection more effectively.

### Step 5 — Narrow APIs and reflective access

Export only packages that need to be public; open packages to frameworks only where necessary. This clarifies module boundaries and reduces reliance on implementation details.

Diagram:

```text
Everything runs on classpath
          |
          v
Move modular dependencies to module path
          |
          v
Legacy JARs become automatic modules
          |
          v
Application gets module-info.java
          |
          v
Libraries progressively gain explicit module descriptors
          |
          v
Module graph and APIs are clearly controlled
```

Automatic modules remain a valid JPMS mechanism, not deprecated syntax. However, the JLS warns that the name and exported package set of an automatic module may change when its author converts it to an explicit module. Therefore, do not build a long-term API that depends too heavily on the name and broad exports of an automatic module.

## 10. Checking Which Module Type a Class Belongs To

The Java Reflection API allows inspecting a class's module:

```java
public class ModuleIdentityDemo {
    public static void main(String[] args) {
        Module module = ModuleIdentityDemo.class.getModule();

        System.out.println("name = " + module.getName());
        System.out.println("descriptor = " + module.getDescriptor());
        System.out.println("named = " + module.isNamed());
    }
}
```

Interpretation:

- For a class in the unnamed module, `getName()` returns `null` and `isNamed()` is `false`.
- For an explicit named module, `getName()` returns the module name; the descriptor reflects the explicit declaration.
- For an automatic module, `getName()` returns the automatic module name; the descriptor can be inspected to see that it is an automatic descriptor.

You can check the descriptor:

```java
import java.lang.module.ModuleDescriptor;

ModuleDescriptor descriptor = module.getDescriptor();
if (descriptor != null && descriptor.isAutomatic()) {
    System.out.println("This class belongs to an automatic module");
}
```

For the unnamed module, the descriptor can be `null` because this module has no explicit module descriptor.

## 11. Common Errors When Working with the Three Module Types

| Symptom | Cause | Resolution |
|---|---|---|
| Named module cannot find class of a dependency on the classpath | Named modules do not read the unnamed module | Move the dependency to the module path or modularize the dependency |
| Declared `requires` but still cannot import class | The package containing the class is not exported or the type is inaccessible | Check `exports` and type/member modifiers |
| Framework cannot access private fields via reflection | Package has not been opened | Use `opens package to framework.module` or `open module` when genuinely needed |
| `requires legacy-json` cannot find module | Name derived from JAR differs from expectation or JAR is on the wrong path | Check `Automatic-Module-Name` and file name; use module tools to inspect the module path |
| Same dependency works on classpath but fails on module path | Module boundaries, package exports, or split packages are enforced | Check module descriptors, packages, and dependency graph |
| Two libraries produce the same module name | Manifest or derived JAR names collide | Select a version/distribution with a unique module name |
| Two modules read by the application export the same package | Split package causes a conflict in the module graph | Reorganize packages or choose a single owning source for the package |
| Assumed a named package implies a named module | Confused package with module | Check `Class.getModule()`; a named package can still live in the unnamed module |
| Automatic module mistaken for an explicit module | JAR has no descriptor but was placed on the module path | Check `ModuleDescriptor.isAutomatic()` and provide a descriptor when explicit control is needed |

## 12. Design Principles to Apply

- Use explicit named modules for applications and libraries that need clear dependency and API declarations.
- Keep internal packages unexported if clients do not need access to them.
- Use narrowly scoped `opens` for frameworks requiring deep reflection; avoid opening all packages unnecessarily.
- Do not place a library on the classpath and expect a named module to `requires` it.
- For non-modularized JARs used on the module path, verify the automatic module name and prefer a stable `Automatic-Module-Name` published by the vendor.
- Do not rely on an automatic module exporting/opening all packages as a long-term API contract.
- Distinguish between a module reading another module and a package of that module being exported.
- When migrating an application, change incrementally and document the module path, classpath, and module descriptors.

## 13. Practice Exercises

### Exercise 1 — Identify module type by launch mode

A JAR `payment-client-2.1.jar` has no `module-info.class` and no `Automatic-Module-Name`.

1. If run with `-cp payment-client-2.1.jar`, which module type do the classes belong to?
2. If the JAR is placed on `--module-path`, which module type does it belong to?
3. What is the derived automatic module name?

**Hint:** On the classpath, classes belong to the unnamed module. On the module path, the JAR becomes an automatic module. The derived name is `payment.client`.

### Exercise 2 — Reading a module descriptor

Given:

```java
module com.acme.web {
    requires com.acme.orders;
    exports com.acme.web.api;
    opens com.acme.web.dto to com.fasterxml.jackson.databind;
}
```

Explain:

- Why can `com.acme.web` reference types exported by `com.acme.orders`?
- Which package is the public API of web?
- Why is the DTO package opened to Jackson?
- Is Jackson allowed to use the DTO package as a normal compile-time API solely because of `opens`?

**Hint:** `requires` creates readability; orders' package must be exported. `exports` exposes the web API. `opens` grants runtime reflection access, not replacing `exports`.

### Exercise 3 — Detecting a classpath dependency

Application `com.acme.app` is a named module. A library `legacy-utils.jar` has no module descriptor and remains on the classpath.

Why can't declaring `requires legacy.utils;` let the application read this library? State two ways to resolve it.

**Hint:** A JAR on the classpath belongs to the unnamed module and has no name to `requires`. You can move the JAR to the module path so it becomes an automatic module, or convert the library into an explicit named module.

### Exercise 4 — Distinguishing exports and opens

A package has a public class and private fields. A serialization framework needs to read/write private fields via reflection.

- Is `exports` sufficient to grant deep reflection access to private fields?
- Does `opens` allow client code to import the class at compile time?
- Write a scoped `opens` directive for the framework module.

**Hint:** `exports` does not grant deep reflection into private members. `opens` grants runtime reflection without changing compile-time access rules. Example: `opens com.acme.model to com.example.serializer;`.

### Exercise 5 — Stable automatic module naming

A library has the file `search-engine-4.5.0.jar`. Without a manifest attribute, the module name is derived from the file name. Write the main manifest attribute to publish a stable name `com.acme.search` and explain the benefit when upgrading the JAR version.

### Exercise 6 — Inspecting a class's module

Write a program that prints:

- `Class.getModule().getName()`
- `Class.getModule().isNamed()`
- `Class.getModule().getDescriptor()`

Run the class once on the classpath and once from an automatic module. Observe the differences in name and descriptor.

## 14. Official Java 17 References

- [Java Language Specification 17 — Chapter 7: Packages and Modules](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html): module declarations, dependencies, exports/opens, and unnamed modules.
- [Java SE 17 API — java.lang.module package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/package-summary.html): module resolution, readability graph, and automatic module handling.
- [Java SE 17 API — ModuleFinder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html): locating modular JARs, automatic modules, and rules for deriving names from manifests/file names.
- [Java SE 17 API — ModuleDescriptor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleDescriptor.html): module description, automatic status, and directives.
- [Java SE 17 API — Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): inspecting modules, module names, exports, and opens at runtime.
- [Dev.java — Code on the Class Path: The Unnamed Module](https://dev.java/learn/modules/unnamed-module/): description of the unnamed module interacting with JPMS.
- [Dev.java — Incremental Modularization with Automatic Modules](https://dev.java/learn/modules/automatic-module/): how to use automatic modules when migrating libraries to the module path.

**Key takeaway:** A named module has an explicit descriptor and controls dependencies as well as exposed packages. An unnamed module has no name and typically contains code on the classpath; it reads observable modules, but named modules cannot declare `requires` on it. An automatic module is a named module synthesized from a non-modular JAR on the module path; it has a derived or manifest-specified name, reads all modules, and exports/opens all packages. Understanding these three types clearly helps structure the module path, classpath, and strong encapsulation boundaries properly in Java 17.
