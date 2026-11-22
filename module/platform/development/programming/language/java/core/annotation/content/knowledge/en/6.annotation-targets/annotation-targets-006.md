# @Target(ElementType.MODULE): Using Annotations on `module-info.java` in Java

## 1. What Does a MODULE-Targeted Annotation Mean?

Since Java 9, the **Java Platform Module System (JPMS)** allows an application to be organized into **named modules**. Each module is declared in a `module-info.java` file, has its own name, and can describe relationships such as `requires`, `exports`, `opens`, `uses`, and `provides`.

With an annotation type declared using:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.MODULE)
@interface ModuleMarker {
}
```

`ElementType.MODULE` allows that annotation to be attached to a **module declaration**, meaning a declaration starting with the `module` or `open module` keyword in `module-info.java`. The annotation describes metadata for the **entire module**, rather than being attached individually to a class, method, package, or a `requires`/`exports` directive.

Example of a valid placement (syntax illustration, not yet a complete program):

```java
@com.example.metadata.ModuleMarker
module com.example.catalog {
    exports com.example.catalog.api;
}
```

Here, `@ModuleMarker` is placed directly **before the `module` declaration**. Writing the fully qualified name `@com.example.metadata.ModuleMarker` makes it clear which package the annotation type comes from. If the annotation type is validly accessible, `module-info.java` can also use an `import` and then write the simple name.

Three levels need to be distinguished:

| Concept | Entity Described | Typical File or Syntax |
| --- | --- | --- |
| **Module** (JPMS) | A named module, a collection of packages and module relationships | `module-info.java`; `ElementType.MODULE` |
| **Package** | A namespace containing Java types | `package-info.java`; `ElementType.PACKAGE` |
| **Type** | Class, interface, enum, annotation type, record | `class`, `interface`, ...; `ElementType.TYPE` |

A module can contain multiple packages; a package and a module are not two names for the same thing. A "Gradle module" or "Maven module" is also not synonymous by default with a **JPMS named module**: you must check whether the project has a JPMS `module-info.java` descriptor.

## 2. `module-info.java` and Annotation Placement

Example of a typical module descriptor:

```java
module com.example.catalog {
    requires java.sql;
    exports com.example.catalog.api;
    opens com.example.catalog.model;
}
```

The descriptor content describes the module's relationships with other modules. To attach an annotation targeting `MODULE`, place it **before the entire module declaration**:

```java
@com.example.metadata.BuildOwner(team = "catalog")
module com.example.catalog {
    requires java.sql;
    exports com.example.catalog.api;
    opens com.example.catalog.model;
}
```

In this illustration, `BuildOwner` must be an accessible annotation type that has `@Target(ElementType.MODULE)` (or a target that includes `MODULE`).

Key syntax points to remember:

1. `module-info.java` is a module declaration file. It **does not declare `package ...;`** like a normal class file. A module declaration contains JPMS directives, not classes or a `main` method.
2. The annotation is placed before `module` or `open module`, after any imports if present. An example using a fully qualified name is often easier to read and avoids depending on an `import` in the lesson.
3. If the annotation has required elements, all of them must be provided at the site of attachment, such as `@BuildOwner(team = "catalog")`.
4. The annotation only marks the **module declaration**. It is not used to mark individual `requires java.sql;`, `exports ...;`, `opens ...;`, `uses ...;`, or `provides ...;` lines.
5. `module-info.java` is compiled by `javac` into `module-info.class`, which represents the module descriptor, and annotation information is retained according to its retention.
6. `@Target(ElementType.MODULE)` only determines **where the annotation is allowed to be attached**; it does not automatically generate `requires`, `exports`, `opens`, or other module rules.

An annotation type can also allow multiple targets:

```java
@Target({ElementType.MODULE, ElementType.TYPE})
@interface Reviewed {
}
```

In that case, `@Reviewed` can be placed on a module declaration and on a type declaration. If it only has `@Target(ElementType.MODULE)`, attempting to attach it to a `class`, `method`, or `package` will be rejected by the compiler.

## 3. Complete Java 17+ Example: Declaring and Reading an Annotation on a Module

We will create a named module called `com.example.catalog`. The `@ModuleOwner` annotation marks module owner information and is retained until runtime. The program reads the metadata through a `java.lang.Module` object.

### 3.1. Directory Structure

Create the exact file tree below (the dots in `com.example.catalog` at the module level are part of the **module directory name** when using `--module-source-path`):

```text
src/
└── com.example.catalog/
    ├── module-info.java
    └── com/
        └── example/
            └── catalog/
                ├── meta/
                │   └── ModuleOwner.java
                └── app/
                    └── Main.java
```

In this example, there is **one module** with two packages: `com.example.catalog.meta` and `com.example.catalog.app`. This is a source layout suitable for the multi-module compilation command `--module-source-path src`.

### 3.2. `src/com.example.catalog/com/example/catalog/meta/ModuleOwner.java`

```java
package com.example.catalog.meta;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.MODULE)
public @interface ModuleOwner {
    String team();
    int revision() default 1;
}
```

This is a top-level `public` annotation type; therefore, the file must be `ModuleOwner.java`. `team()` is a required element, while `revision()` is an optional element with a default of `1`.

- `@Target(ElementType.MODULE)` requires the annotation to be applicable only to module declarations.
- `@Retention(RetentionPolicy.RUNTIME)` retains the metadata so it can be read from `Module` using reflection at runtime.
- `public` determines the accessibility of the annotation type name according to Java rules; if another module needs to use this type, `requires` and `exports` must also be considered.

### 3.3. `src/com.example.catalog/module-info.java`

```java
@com.example.catalog.meta.ModuleOwner(team = "platform")
module com.example.catalog {
    exports com.example.catalog.meta;
}
```

This is where `ElementType.MODULE` is used. `@ModuleOwner(team = "platform")` marks the **module `com.example.catalog`**, not the class `Main` or the `meta` package.

We intentionally omit `revision`, so the value observed later is the default `1`. The `exports com.example.catalog.meta;` directive allows other modules to read the **public types** in this package if there is an appropriate module readability relationship; in the example, `Main` belongs to the same module, so `exports` is not needed to import `ModuleOwner`.

### 3.4. `src/com.example.catalog/com/example/catalog/app/Main.java`

```java
package com.example.catalog.app;

import com.example.catalog.meta.ModuleOwner;

public class Main {
    public static void main(String[] args) {
        Module module = Main.class.getModule();
        ModuleOwner annotation = module.getAnnotation(ModuleOwner.class);

        System.out.println(module.getName());
        System.out.println(module.isNamed());
        System.out.println(annotation.team());
        System.out.println(annotation.revision());
    }
}
```

`Main.class.getModule()` returns the `java.lang.Module` of the `Main` class. The `Module` object implements `AnnotatedElement`, so it has the `getAnnotation(Class<T>)` method to retrieve an annotation present on the module. In the example, the annotation is guaranteed to be present and its retention is `RUNTIME`, so `annotation` is not `null`.

### 3.5. Compile and Run

From the directory containing `src`, with JDK 17 or later:

```bash
javac --release 17 -d out --module-source-path src -m com.example.catalog
java --module-path out --module com.example.catalog/com.example.catalog.app.Main
```

**Exact stdout:**

```text
com.example.catalog
true
platform
1
```

Explanation:

1. `javac --module-source-path src -m com.example.catalog` locates the source of the named module and generates the class files along with `module-info.class` in the output directory.
2. `java --module-path out --module com.example.catalog/com.example.catalog.app.Main` launches `Main` inside a **named module**, so `module.getName()` is `com.example.catalog`, and `isNamed()` is `true`.
3. `module.getAnnotation(ModuleOwner.class)` looks up the annotation attached to the module declaration.
4. `team()` returns `"platform"` because it was explicitly specified. `revision()` returns `1` because the default value is used.

This snippet has been verified by compiling with `--release 17` and running on a JDK supporting Java 17; the stdout above matches the program exactly.

## 4. The Role of `@Retention` for MODULE

`@Target(ElementType.MODULE)` answers "where is the annotation **placed**?". `@Retention` answers "how long is the annotation **retained**?". The two aspects must be decided separately.

| Retention | Characteristics | Readable via `Module.getAnnotation(...)`? |
| --- | --- | --- |
| `RetentionPolicy.SOURCE` | Present only in source; the compiler may process it and then discard it from the class file | No |
| `RetentionPolicy.CLASS` | Stored in the class file, but not retained for Java reflection to read at runtime | No |
| `RetentionPolicy.RUNTIME` | Metadata is retained so reflection can observe it at runtime | Yes, if the annotation is actually present on the module and the type is appropriately accessible |

If `@Retention` is not declared, the default is `RetentionPolicy.CLASS`. Therefore, attaching `@ModuleOwner` to `module-info.java` while forgetting `RUNTIME` will still compile, but the `getAnnotation(ModuleOwner.class)` method in the runtime example will not find that annotation.

When using reflection, a `null` check is needed because `getAnnotation(...)` returns `null` if the annotation is not present or is unavailable at runtime:

```java
ModuleOwner owner = module.getAnnotation(ModuleOwner.class);
if (owner != null) {
    System.out.println(owner.team());
}
```

This snippet is a standalone illustration of how to handle the result; it assumes the `module` variable has already been declared and `ModuleOwner` is in scope.

Note: using `@Target(MODULE)` **does not require** using `RUNTIME`. Choose the retention based on your needs: checking at the source level, analyzing the class file, or reading via reflection at runtime. For the exercise above, `RUNTIME` is a necessary condition to print `team()` via `Module.getAnnotation`.

## 5. What Can MODULE Metadata Describe, and What Does It Not Do?

Example of elements suitable for an annotation marking a module:

```java
@Target(ElementType.MODULE)
@Retention(RetentionPolicy.RUNTIME)
@interface ModuleMetadata {
    String owner();
    String[] tags() default {};
    boolean experimental() default false;
}
```

The usage site can be:

```java
@com.example.meta.ModuleMetadata(
    owner = "infra",
    tags = {"observability", "core"},
    experimental = true
)
module com.example.metrics {
}
```

This is a **syntax example**: to compile it in practice, `ModuleMetadata` must exist with the correct fully qualified name, an accessible package, and appropriate module configuration. Metadata can be used for generating reports, internal audits, build tools, or displaying information at runtime. However, Java **does not automatically enforce policies** based on `owner`, `tags`, or `experimental`.

Specifically:

- `@ModuleMetadata(owner = "infra")` **does not automatically change module access permissions**.
- `@ModuleMetadata(experimental = true)` **does not automatically enable or disable the module**.
- Annotations **do not replace** `requires`, `exports`, `opens`, `uses`, or `provides`.
- When writing a tool that consumes the annotation, you still have to define how elements are interpreted, how values are validated, and what resulting behavior occurs.
- An annotation on a module also **does not automatically propagate** to packages, classes, or modules declared in `requires`.

For sensitive metadata such as access keys, passwords, or tokens, they should not be written as annotation values because the information may be stored in the class file and retrieved by analysis tools or reflection.

## 6. Named, Automatic, and Unnamed Modules

At runtime, `Class.getModule()` returns a `Module` object, but not every `Module` comes from a `module-info.java` file declared by the author.

**Explicit named module:** Has a `module-info.java` descriptor (or the corresponding descriptor in the class file) and is identified by the module name. This is the case where you directly attach a `@Target(MODULE)` annotation to the module declaration. For example, `com.example.catalog` above.

**Automatic module:** A JAR without an explicit module descriptor can become an automatic module when placed on the module path according to JPMS rules. It has a module name, but **does not have a `module-info.java` declaration written by you on which to directly attach a module annotation as in the example**.

**Unnamed module:** Code running from a regular classpath generally resides in an unnamed module. `Main.class.getModule().isNamed()` can be `false`, and `getName()` is `null`. There is no module declaration in `module-info.java` for you to attach a `MODULE` annotation to that classpath group.

Therefore, to clearly learn `ElementType.MODULE`, you should compile and test on the **module path** with an explicit named module. If you only run classes from the classpath, you need to distinguish the results because you have changed the module environment of the program.

## 7. Annotation Type Accessibility and JPMS

The `@ModuleOwner` annotation is a real Java type, so in addition to `@Target(MODULE)`, it is also subject to access rules and module dependencies.

- **Within the same named module:** different packages belonging to the same module can access a `public` annotation type if the type and referenced members are appropriate. There is no need to export a package just so code within the same module can use each other.
- **Between named modules:** importing a `public` annotation type normally requires the consuming module to read the providing module (appropriate `requires`) and the API package to be exported (`exports`) with the proper scope. `public` alone does not cross module boundaries.
- **Runtime reflection:** for an annotation to be visible via the reflection API, it must have `RUNTIME`; in addition, the reader must still be able to access/resolve the annotation type. Deep reflection access rules and `opens` are a separate issue from attaching an annotation to a module declaration.
- If a module wants to use an annotation type from **another library module**, the corresponding dependency must be declared in the descriptor; the compiler needs to see the annotation type when processing the module declaration.

Package names within the same source tree do not by themselves establish module boundaries: boundaries arise from the descriptor, how the program is compiled, and how modules are loaded.

## 8. Common Mistakes

### Mistake 1: Attaching a MODULE Annotation to a Class

The following snippet is intentionally **invalid** when `ModuleOwner` only allows `ElementType.MODULE`:

```java
@ModuleOwner(team = "platform")
class CatalogService {}
```

The compiler reports that the annotation type is not applicable to this kind of declaration. If you want to support both modules and types, design it with `@Target({ElementType.MODULE, ElementType.TYPE})`. If the metadata only describes the module, keep `MODULE` and move the annotation into `module-info.java`.

### Mistake 2: Attaching an Annotation Directly to `exports` or `requires`

There is no place to attach an annotation on individual module directives under the syntax in this lesson:

```java
module com.example.catalog {
    @ModuleOwner(team = "platform")
    exports com.example.catalog.meta;
}
```

This is an **invalid syntax** example. To annotate the module, move the annotation before the `module` or `open module` keyword.

### Mistake 3: Having MODULE but Not Seeing the Annotation via Reflection

Things to check: whether the annotation type has `@Retention(RetentionPolicy.RUNTIME)`; whether the annotation is placed properly on the module declaration; whether the program is running in the right named module; and whether the right type `ModuleOwner.class` is being used.

Do not try to fix this by arbitrarily adding `exports` or `opens`; first distinguish between **retention**, **annotation placement**, and **JPMS runtime context**.

### Mistake 4: Classpath-Style Compilation Loses the Module Context

When launching the example with `java --module-path out --module com.example.catalog/com.example.catalog.app.Main`, the program clearly knows the named module name. If you switch to running with `java -cp ...` and omit module launch, the class may belong to the unnamed module and will not produce results reflecting the descriptor's annotation as expected.

### Mistake 5: Confusing MODULE with PACKAGE

`@Target(ElementType.PACKAGE)` is for package declarations, usually placed on the `package ...;` line in `package-info.java`. `@Target(ElementType.MODULE)` is for the `module ... { ... }` declaration line in `module-info.java`. An annotation with only `PACKAGE` cannot be attached to a module descriptor, and vice versa.

### Mistake 6: Using an Old Java API

JPMS and `ElementType.MODULE` were introduced in Java 9. A project compiling against Java 8 language/APIs cannot use module declarations and the `MODULE` target. The example here uses `javac --release 17` to standardize on a Java 17+ platform.

## 9. When Should You Choose ElementType.MODULE?

Use an annotation targeting `MODULE` when the information has **module-wide scope** and you have tooling that actually uses it: module owner, labels for reporting, support status, experimental level, or module classification. If the requirement only describes a class, method, or package, place the metadata at the appropriate level instead of marking the entire module.

A practical implementation workflow:

1. Confirm that the project uses JPMS explicit named modules and has `module-info.java`.
2. Determine that the metadata applies to the **entire module**, not just a single class or package.
3. Define the annotation type, `@Target(ElementType.MODULE)`, and required and default elements.
4. Choose `@Retention` according to how tools read the annotation; use `RUNTIME` if calling `Module.getAnnotation`.
5. Attach the annotation on the module declaration in `module-info.java`, passing all required elements.
6. Compile, run via the module path, try reading metadata from `Class.getModule()`, and test the case where the annotation is absent.
7. If releasing the annotation as an API across multiple modules, review `requires` and `exports` relationships, library versions, and how consumers use it.

**Remember:** `ElementType.MODULE` specifies that **the allowed target for attaching the annotation is the module declaration in `module-info.java`**. Java supports storing that metadata according to `@Retention` and reading it via `java.lang.Module` when the retention is appropriate; it is the JPMS directives themselves that govern dependency relationships and accessibility between modules.
