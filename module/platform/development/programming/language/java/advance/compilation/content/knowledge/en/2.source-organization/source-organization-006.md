# Role of package-info.java and module-info.java in Java Source Code Organization

In Java, a **package** groups related types into a namespace; a **module** (Java Platform Module System – JPMS, since Java 9) groups packages into a unit with dependency declarations and access boundaries. Two special files, **package-info.java** and **module-info.java**, describe these two organizational levels. They add metadata to source code, yet solve different problems.

## 1. Quick Comparison

| Criterion | package-info.java | module-info.java |
| --- | --- | --- |
| Associated with | One package, e.g., com.example.math | One named module, e.g., com.example.math |
| Location | Same source directory as classes in the package | Root of the module's source directory |
| Main contents | Package-level Javadoc, annotations applied to the package | Module declaration, dependencies, API boundaries, reflection, services |
| Primary effect | Documentation and metadata for tools/libraries | Module readability, access checks, JPMS runtime configuration |
| Required? | No | Needed to declare an explicit named module; applications running on classpath do not need it |
| Interchangeable? | No | No |

**A package is not a module.** A module usually contains multiple packages. Each package can have its own package-info.java file, whereas each explicit named module has one module-info.java at its source root. A package name does not have to match the module name.

## 2. package-info.java: Documentation and Annotations for a Package

### 2.1. Writing package-level documentation

**package-info.java** is the standard place to write Javadoc explaining a package's responsibilities, API contract, usage conventions, and relationships among types in the package. Example:

~~~java
// src/com.example.math/com/example/math/package-info.java
/**
 * Provides arithmetic operations shared across the application.
 *
 * <p>Public classes here form the stable API of the package.
 * Operations may throw ArithmeticException on overflow.
 */
package com.example.math;
~~~

The Javadoc comment block sits **immediately before the package declaration**, optionally separated by package-level annotations. The Javadoc tool uses this description as the package documentation; an ordinary Java file with many class comments cannot automatically fulfill the package-description role.

Documentation should cover the **overall responsibilities and contract** of the package; details specific to individual classes/methods remain on those classes/methods. When renaming a package or moving classes, review the documentation to avoid misdescribing scope.

### 2.2. Declaring annotations at the package level

An annotation with **@Target(ElementType.PACKAGE)** can be placed on the package declaration. For example, suppose there is an annotation **PackagePurpose** with **@Retention(RetentionPolicy.RUNTIME)**:

~~~java
/** Package providing arithmetic APIs. */
@PackagePurpose("math-api")
package com.example.math;
~~~

The annotation is placed **before the package keyword**, not on any class. When compiled, the compiler can emit **package-info.class** containing annotation metadata; frameworks/tools or reflection code can read this information. The annotation must be validly defined with appropriate visibility; a complete example is in section 4.

A practical use is nullability convention annotations, default mapping configurations, or package categorization supported by a library. **An annotation by itself does not enforce null checks or business rules**: there must be a compiler, annotation processor, static analyzer, or framework that actually reads and interprets it. Annotations retained only at SOURCE/CLASS cannot be read by runtime reflection like RUNTIME annotations.

### 2.3. Rules and limitations

- The file name is **package-info.java** and the package declaration must match the path/source layout used by the build. Usually there is only one package-info declaration per package within the same source set during compilation.
- The file normally contains only the package declaration, Javadoc, package annotations, and needed imports; do not use it as a place to put business classes.
- Simply adding **package-info.java** does not make the package public, does not create a module, and does not change the accessibility of classes or methods.
- A package without metadata to describe may not need this file. Do not create the file merely as a formality.
- If there is only Javadoc and no annotation needing retention in bytecode, whether **package-info.class** is emitted depends on how compilation runs; **the .java file is the source of documentation**, so do not rely on the class file's existence.

## 3. module-info.java: The Module Contract in JPMS

### 3.1. Declaring modules and dependencies

The **module-info.java** file is placed at a module's source root and has a declaration structure, for example:

~~~java
module com.example.app {
    requires com.example.math;
}
~~~

The name **com.example.app** is the module name. **requires** declares that the app module reads the math module to access the public types that math permits exporting. **java.base** is read by every module by default; there is no need to write requires java.base.

JPMS lets the compiler and module system validate readability relationships and package accessibility, catching missing dependencies or configuration conflicts early. When running on the **module path**, module-info.class provides the descriptor for the runtime. Without module-info.java, source code can still be compiled/run using the traditional classpath model.

### 3.2. Key directives

| Directive | Meaning and scenario |
| --- | --- |
| **requires other.module;** | The current module reads the specified module. |
| **requires transitive other.module;** | The module depends on and forwards readability to other modules that read the current module; useful when the public API exposes types from the dependency. Does not automatically export all packages. |
| **requires static other.module;** | Dependency required at compile time but optional at runtime; executing code must tolerate its absence when using the feature. |
| **exports some.pkg;** | Allows other modules to access public types of the package through normal mechanisms, given appropriate readability. |
| **exports some.pkg to client.module;** | Exports the package only to the named modules. |
| **opens some.pkg;** | Allows deep reflection into the package at runtime, e.g., frameworks needing access to non-public members. Does not grant normal compile-time import access. |
| **opens some.pkg to framework.module;** | Opens reflective access only to the target modules. |
| **uses some.Service;** | Declares that the module consumes a service via ServiceLoader. |
| **provides some.Service with some.Impl;** | Registers a service implementation so the service loader can discover it. |

You can declare **open module module.name { ... }** to open all packages of the module for deep reflection, though it is usually better to open only the needed packages. A package can have both **exports** (compile-time API) and **opens** (runtime reflection); the two meanings are independent. **exports** also does not turn package-private classes into public ones and does not permit accessing private fields.

### 3.3. Module-level encapsulation

Suppose **com.example.math** contains **com.example.math** (public API) and **com.example.math.internal** (implementation). When the module only has:

~~~java
module com.example.math {
    exports com.example.math;
}
~~~

Other modules with a readability relationship can use **public classes** in the exported package **com.example.math**, yet cannot directly import types in **com.example.math.internal** across the module boundary. Even if a class in internal is declared public, **public does not mean the package has been exported**.

When a serialization/DI framework needs reflective access to non-public members of an internal package, you can consider:

~~~java
module com.example.math {
    exports com.example.math;
    opens com.example.math.internal to some.framework;
}
~~~

This snippet **illustrates syntax**, to be used only when **some.framework** is the actual module name of the framework in use. If the framework only needs to call public APIs, do not open packages unnecessarily. When migrating a legacy application from classpath to module path, **IllegalAccessException** or **InaccessibleObjectException** errors often relate to differences among exports, opens, and standard Java access controls.

## 4. Java 17+ Example: Combining Both Files, Compiling, and Running

The example has **two modules**: com.example.math provides the API; com.example.app uses that API. The math package has Javadoc and a runtime annotation we define. Directory structure:

~~~text
src/
├── com.example.math/
│   ├── module-info.java
│   └── com/example/math/
│       ├── package-info.java
│       ├── PackagePurpose.java
│       └── Calculator.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/
        └── Main.java
~~~

**File 1 — src/com.example.math/module-info.java:**

~~~java
module com.example.math {
    exports com.example.math;
}
~~~

Math publishes its API package so app can use it. No requires java.base is needed.

**File 2 — src/com.example.math/com/example/math/PackagePurpose.java:**

~~~java
package com.example.math;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PACKAGE)
public @interface PackagePurpose {
    String value();
}
~~~

This is an annotation defined for the example, targeting **PACKAGE** and retained at runtime. Declared public so code in the app module can reference the annotation type.

**File 3 — src/com.example.math/com/example/math/package-info.java:**

~~~java
/**
 * Provides simple arithmetic operations for other applications.
 *
 * <p>Public API of module {@code com.example.math}.
 */
@PackagePurpose("math-api")
package com.example.math;
~~~

The package is documented with Javadoc and annotated. The compiler will emit the metadata needed to read the annotation via reflection.

**File 4 — src/com.example.math/com/example/math/Calculator.java:**

~~~java
package com.example.math;

public final class Calculator {
    private Calculator() {}

    public static int add(int a, int b) {
        return Math.addExact(a, b);
    }
}
~~~

**File 5 — src/com.example.app/module-info.java:**

~~~java
module com.example.app {
    requires com.example.math;
}
~~~

**File 6 — src/com.example.app/com/example/app/Main.java:**

~~~java
package com.example.app;

import com.example.math.Calculator;
import com.example.math.PackagePurpose;

public class Main {
    public static void main(String[] args) {
        System.out.println(Calculator.add(2, 3));

        PackagePurpose purpose = Calculator.class.getPackage()
                .getAnnotation(PackagePurpose.class);
        System.out.println(purpose.value());
    }
}
~~~

From the directory **containing src**, run with JDK 17+:

~~~bash
javac -d out --module-source-path src -m com.example.math,com.example.app
java --module-path out -m com.example.app/com.example.app.Main
~~~

**Standard output:**

~~~text
5
math-api
~~~

The javac command compiles the named modules and writes class/module descriptors to **out**. The java command uses **--module-path** to locate modules and **-m module/main.class** to run the entry point. Calling **Calculator.class.getPackage().getAnnotation(...)** shows the package-level annotation is retained and properly retrieved at runtime.

Try removing **exports com.example.math;** so the package is not exported and recompile: app still declares requires, yet importing Calculator/PackagePurpose from a non-exported package will be rejected by the compiler. That is the clearest difference between **module readability** and **package accessibility**.

## 5. Which File to Choose in Real Projects?

| Need | Solution |
| --- | --- |
| Explain purpose and usage of a group of APIs in the same package | Write Javadoc in package-info.java |
| Apply default annotations for an entire package with library support | Place annotations in package-info.java |
| Create a named module and explicitly state module dependencies | Create module-info.java with requires |
| Publish only packages forming the public API | Use exports in module-info.java |
| Allow a framework to perform deep reflection on a specific package | Use appropriate opens in module-info.java |
| Organize classes by namespace without using JPMS yet | Organize packages normally; module-info.java is not required yet |
| Need both package documentation and module boundaries | Use both, in their two respective locations |

In Maven/Gradle projects, keep the build tool's standard source layout; with JPMS modules, typically place **module-info.java** at the root of the corresponding source set (e.g., **src/main/java** of each project/module) and package-info.java inside the package directory. Placing multiple modules under one source root as in section 4 suits demonstrating javac commands; not every project needs that layout.

When packaging a named module into a JAR, **module-info.class** sits at the root of the JAR. Maven/Gradle dependency configuration and JPMS **requires** declarations serve two different management layers: the build tool fetches artifacts; the module system establishes relationships among modules at compile/run time. Having a dependency in Gradle does not mean automatically declaring the matching requires for a named module.

## 6. Common Mistakes and How to Check

1. **Confusing package with module.** A class's package declaration only specifies its namespace; it does not create a JPMS descriptor. One module can contain multiple packages and export a subset of them.
2. **Placing module-info.java in the wrong location.** The descriptor must be at the source root of the corresponding module; placing it inside a package makes the structure invalid.
3. **Missing requires or exports.** requires enables reading a module, while exports lets reading modules access the package's public API. Missing either one can cause compile errors.
4. **Confusing opens with exports.** opens only supports reflective access at runtime. For other Java code to directly import public classes, appropriate exports and requires are needed.
5. **Assuming package-info.java enforces rules automatically.** Annotations are just metadata; actual effect depends on tools reading the annotations and retention policy.
6. **Forgetting path or package declarations.** For instance, a file under com/example/math must declare package com.example.math; the module source path layout in the example must match module names.
7. **Mixing classpath and module path.** JARs on the classpath belong to the unnamed module and do not receive the same encapsulation as explicit named modules. Verify which mode the project runs under before expecting module-info to take effect.
8. **Putting the same package in multiple resolved named modules.** Configurations causing split packages can fail module resolution or module layer creation; module design should keep packages cleanly separated.
9. **Opening every package to fix reflection errors.** Use opens for the exact package and consumer module; use command-line options like **--add-opens** only for intentional migration scenarios.
10. **Assuming package annotations always exist at runtime.** Only annotations retained with RetentionPolicy.RUNTIME can be queried via reflection as shown in section 4.

To inspect the descriptor after compilation, you can run:

~~~bash
java --module-path out --describe-module com.example.math
~~~

This command prints information about the compiled module, including exported packages; exact line formatting and ordering may vary by JDK, so do not rely on fixed stdout. Package documentation can be generated with **javadoc** following the corresponding source layout.

## 7. Self-Check Questions

- If a library has three packages but only two are public API, where would you configure exports and why?
- If a framework only needs to read private fields via reflection, is exports sufficient or is opens needed?
- When package-info.java has a @Target(PACKAGE) annotation but lacks @Retention(RUNTIME), what happens when calling getAnnotation at runtime?
- Why must the app in the example have requires com.example.math AND math have exports com.example.math?
- In an application still running on the classpath, when is package-info.java still useful even without creating module-info.java?

**Takeaway:** **package-info.java** documents and attaches metadata to a **package**; **module-info.java** describes dependencies, exposed APIs, and reflection permissions of a **module**. Use both when you want source code with proper package-level documentation and clear module boundaries.
