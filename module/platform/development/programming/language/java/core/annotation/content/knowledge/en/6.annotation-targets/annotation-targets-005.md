# `ElementType.PACKAGE` and `package-info.java` in Java Annotations

## 1. The Problem: Attaching Metadata to an Entire Package

In Java, a *package* groups classes, interfaces, and other types by namespace. Sometimes we need to describe **the package itself**: who is responsible for it, which team the module belongs to, whether it requires auditing, or whether it is a package for public APIs. If the goal is to place metadata at the package level, Java provides the `ElementType.PACKAGE` annotation target and the conventional `package-info.java` file.

An example of the idea:

```java
@PackagePolicy(owner = "platform", audited = true)
package com.example.orders;
```

This is an **annotated package declaration**, not an annotation attached to a class. In a typical Java project, that declaration is placed in the `package-info.java` file of the corresponding package.

Three things should be clear from the start:

1. `@Target(ElementType.PACKAGE)` specifies the **allowed target** of an annotation type.
2. `package-info.java` is the conventional place to write **package annotations** and package-level Javadoc.
3. Annotations are only metadata. Java does not automatically perform authorization checks, log entries, or apply policies to every class because the package is annotated. A tool or program must read and process it.

This lesson focuses on how to declare, use, compile, and read annotations targeting `PACKAGE`; other target types are mentioned only for distinction.

## 2. What Is `ElementType.PACKAGE`?

`java.lang.annotation.ElementType` is an enum describing the syntactic locations where an annotation can be applied. Among them, `ElementType.PACKAGE` represents a **package declaration**.

We restrict an annotation type to this target using `@Target`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.PACKAGE)
@interface PackageTag {
    String value();
}
```

`PackageTag` is allowed to be placed before a **package declaration**. It cannot be applied to a class or method declaration:

```java
// INTENTIONALLY INVALID: PackageTag only has target PACKAGE, not TYPE
@PackageTag("orders")
class OrderService {
}
```

The compiler may report `annotation type not applicable to this kind of declaration`. The issue lies in the **applicable target**, not the `String` type or the `value` element name.

Table distinguishing commonly confused targets:

| `ElementType` | Where is it attached? | Example placement |
|---|---|---|
| `PACKAGE` | `package ...;` declaration | `package-info.java` |
| `TYPE` | Class/interface/enum/annotation declaration | `class Order {}` |
| `METHOD` | Method declaration | `void submit() {}` |
| `FIELD` | Field declaration | `String id;` |
| `MODULE` | JPMS module declaration | `module-info.java` |

`TYPE` **does not replace** `PACKAGE`, and `MODULE` is a separate mechanism of the Java Platform Module System. If you want an annotation to apply to both packages and classes, you can declare `@Target({ElementType.PACKAGE, ElementType.TYPE})`; only do this if the metadata genuinely makes sense in both places.

## 3. Why Use the `package-info.java` File?

In a Java codebase structure, each `.java` file typically has a package declaration like this:

```java
package com.example.orders;

public class OrderService {
}
```

This line places `OrderService` into the `com.example.orders` package, but the `OrderService.java` file itself is not the appropriate place to store annotations for the package.

**Language rule:** Annotations placed on a package declaration must be written in a compilation unit named `package-info.java`. Therefore, we create files following this structure:

```text
src/
└── com/
    └── example/
        └── orders/
            ├── package-info.java
            ├── PackagePolicy.java
            ├── OrderService.java
            └── Main.java
```

The contents of `package-info.java` can include Javadoc for the package, annotations, and the package declaration:

```java
/**
 * Order processing services.
 *
 * <p>The package is managed by the platform team.</p>
 */
@PackagePolicy(owner = "platform")
package com.example.orders;
```

This is an actual Java file, not a Markdown or separate configuration file. The file name consists of lowercase `package-info` and the `.java` extension, and must be spelled accurately. The directory location should match the package name according to the source layout of the project and build tool.

Note: `package-info.java` **does not declare a class named `package-info`**. This hyphenated name is a file-naming convention, not a Java identifier used to name a class.

## 4. Defining an Annotation for `PACKAGE`

We design a custom annotation containing the package owner and an audit flag.

File **`PackagePolicy.java`** in the `com.example.orders` package:

```java
package com.example.orders;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PACKAGE)
public @interface PackagePolicy {
    String owner();
    boolean audited() default false;
}
```

Meaning of each part:

- `@interface PackagePolicy` declares an annotation type named `PackagePolicy`.
- `@Target(ElementType.PACKAGE)` restricts its usage location to a package declaration.
- `@Retention(RetentionPolicy.RUNTIME)` retains the annotation at runtime so that reflection APIs can read it.
- `owner()` is a **required** `String` element that must be provided when applying the annotation.
- `audited() default false` allows omitting `audited` to receive the default value `false`.

Because the annotation is declared in the `com.example.orders` package, the `package-info.java` file in the same package can reference `@PackagePolicy` by its simple name. If the annotation is in a different package, you must ensure the name resolves validly via an import or a fully qualified name.

Omitting `@Retention(RUNTIME)` does not make a package annotation definition invalid. However, if you intend to read it with `Package.getAnnotation(...)` at runtime, the retention policy is a crucial requirement.

## 5. Attaching an Annotation to a Package Declaration

File **`package-info.java`**:

```java
/**
 * APIs and services in the orders domain.
 *
 * <p>The package policy describes the owner and audit requirement.</p>
 */
@PackagePolicy(owner = "platform", audited = true)
package com.example.orders;
```

Reading in order:

1. The `/** ... */` block is the Javadoc for the package.
2. `@PackagePolicy(owner = "platform", audited = true)` is the annotation placed immediately before the package declaration.
3. `package com.example.orders;` specifies the annotated package.

If `audited` uses its default value, you can write:

```java
@PackagePolicy(owner = "platform")
package com.example.orders;
```

You cannot omit `owner` because `PackagePolicy.owner()` has no `default`:

```java
// INTENTIONALLY INVALID: owner is a required element
@PackagePolicy(audited = true)
package com.example.orders;
```

The snippets above are **separate alternatives** for the contents of the same file. In the runnable example later, only one valid `package-info.java` version is used.

### Placement of `import` Statements

Java syntax places the package declaration before import declarations. Therefore, if imports are needed for a package annotation, the `import` lines must come **after** the `package ...;` statement:

```java
@com.example.metadata.PackagePolicy(owner = "orders")
package com.example.orders;
```

Using a fully qualified name as above is a simple approach when the annotation type is in a different package. Avoid moving `import` before the package declaration; that violates the compilation unit syntax order.

## 6. Complete Java 17+ Example: Declaring, Applying, and Reading a Package Annotation

The following example has **three files**, all belonging to the `com.example.orders` package.

### File 1 — `src/com/example/orders/PackagePolicy.java`

```java
package com.example.orders;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PACKAGE)
public @interface PackagePolicy {
    String owner();
    boolean audited() default false;
}
```

### File 2 — `src/com/example/orders/package-info.java`

```java
/**
 * Package demonstrating package-level metadata.
 *
 * <p>Classes in this package handle order business logic.</p>
 */
@PackagePolicy(owner = "platform", audited = true)
package com.example.orders;
```

### File 3 — `src/com/example/orders/Main.java`

```java
package com.example.orders;

public class Main {
    public static void main(String[] args) {
        Package currentPackage = Main.class.getPackage();
        PackagePolicy policy =
                currentPackage.getAnnotation(PackagePolicy.class);

        System.out.println("package=" + currentPackage.getName());
        System.out.println("owner=" + policy.owner());
        System.out.println("audited=" + policy.audited());
    }
}
```

In the directory containing `src`, run the following commands (JDK 17 or later):

```bash
javac -d out src/com/example/orders/PackagePolicy.java src/com/example/orders/package-info.java src/com/example/orders/Main.java
java -cp out com.example.orders.Main
```

**Exact stdout:**

```text
package=com.example.orders
owner=platform
audited=true
```

Explanation of the data flow:

1. `javac` compiles the `PackagePolicy` annotation type, the annotated package declaration, and `Main`.
2. Thanks to `RetentionPolicy.RUNTIME`, the package metadata is available to be read at runtime.
3. `Main.class.getPackage()` retrieves the `java.lang.Package` object representing the package of the `Main` class.
4. `getAnnotation(PackagePolicy.class)` reads the annotation of type `PackagePolicy` on that package.
5. `owner()` and `audited()` return the two values declared in `package-info.java`.

**Example limitation:** `Main` assumes the package has a runtime annotation of the expected type; if you remove `@PackagePolicy`, change the retention, exclude `package-info.class` from the build output, or run with an out-of-sync set of class files, `getAnnotation(...)` may return `null` and the `policy.owner()` line will throw a `NullPointerException`. Production code needs to check for `null` or handle the case where the annotation is absent.

## 7. `package-info.class` and Retention Policies

`package-info.java` is source code. When a package annotation needs to be retained in a class file, the compiler can generate a metadata class file named **`package-info.class`** for that package. This is the basis for reading package annotations at runtime after compilation and packaging.

With `@Retention`:

| Policy | At compile time and runtime |
|---|---|
| `RetentionPolicy.SOURCE` | The annotation is only needed in source code; it is not recorded in the class file |
| `RetentionPolicy.CLASS` | The annotation is present in the class file, but is not exposed via standard reflection mechanisms |
| `RetentionPolicy.RUNTIME` | The annotation is stored and can be read via reflection at runtime |

If you **do not write `@Retention`**, the default is `RetentionPolicy.CLASS`, not `RUNTIME`.

Therefore, to run the `Package.getAnnotation(PackagePolicy.class)` example and receive a value, place `@Retention(RetentionPolicy.RUNTIME)` on `PackagePolicy`.

Additional build notes:

- When packaging a JAR, check that `com/example/orders/package-info.class` is preserved if the program needs runtime metadata. If the build tool strips this file, the information to be read may be lost.
- The `package-info.java` file does not automatically appear on the classpath when only running `java`; the program uses the compiled `.class` files.
- You should not assume that a package always has a `package-info.class` file in every situation. That depends on the contents of the package declaration, the retention policy, and how the compiler/build handles it.
- If the metadata is only intended for a compile-time processor or Javadoc, it is not necessary to choose `RUNTIME`.

You can inspect the compiled output by looking inside the `out/com/example/orders` directory. In the example above, the class file containing the runtime package annotation will be present alongside the regular class files.

## 8. Reading Package Annotations via Reflection

Java uses `java.lang.Package` to represent the metadata of a package. A practical approach, once you have a class belonging to the package to inspect, is:

```java
Package pkg = SomeClass.class.getPackage();
```

Then check:

```java
PackagePolicy policy = pkg.getAnnotation(PackagePolicy.class);
if (policy != null) {
    System.out.println(policy.owner());
}
```

Useful APIs:

- `pkg.getName()`: the package name, for example `com.example.orders`.
- `pkg.isAnnotationPresent(PackagePolicy.class)`: whether an annotation of the specified type is present at runtime.
- `pkg.getAnnotation(PackagePolicy.class)`: retrieves the specific annotation; may return `null`.
- `pkg.getAnnotations()`: retrieves the annotations present on the package according to the reflection API.

A way to read with a `null` check:

```java
package com.example.orders;

public class PolicyReader {
    static String ownerOf(Class<?> type) {
        Package pkg = type.getPackage();
        if (pkg == null) {
            return "<unnamed package>";
        }
        PackagePolicy policy = pkg.getAnnotation(PackagePolicy.class);
        return policy == null ? "<unspecified>" : policy.owner();
    }
}
```

This snippet is an **illustrative fragment** that can compile when `PackagePolicy` is already in the same package; it is not a standalone `main` program.

### Distinguishing Package Annotations from Class Annotations

`PackagePolicy` is attached to `package com.example.orders;`, not to individual classes. Therefore:

```java
PackagePolicy fromPackage =
        Main.class.getPackage().getAnnotation(PackagePolicy.class);

PackagePolicy fromClass =
        Main.class.getAnnotation(PackagePolicy.class);
```

In the example from section 6, `fromPackage` receives the annotation, while `fromClass` is `null`: because `Main` is **not** annotated with `@PackagePolicy`. Furthermore, `@Target(PACKAGE)` does not allow annotating `Main` with that annotation type.

A framework that wants to apply package metadata rules to individual classes must **actively look up the class's package and read the annotation at the package level**. Java does not automatically add the annotation onto classes.

### Packages and Class Loaders

At runtime, packages are associated with the class loader that defines the class. Therefore, when inspecting metadata in an application that uses multiple class loaders, you should start from a **specific class** and call `SomeClass.class.getPackage()`. Do not assume that simply having the same package name string always yields the same `Package` object and the same metadata across all class loaders.

## 9. Using `package-info.java` for Javadoc

In addition to package annotations, `package-info.java` is the recommended place to write **package-level Javadoc**. The description in the `/** ... */` block placed right before the annotation and package declaration will be processed by Javadoc.

Example:

```java
/**
 * Provides payment validation and processing operations.
 *
 * <p>Types in this package provide internal services.</p>
 *
 * @since 1.0
 */
package com.example.payment;
```

This is a completely valid `package-info.java` even **without any annotations**. It demonstrates that the two purposes of the file are independent:

1. Describing the package with Javadoc.
2. Attaching annotations to the package declaration when metadata is needed.

Both can be used in the same file. If an annotation type has `@Documented`, that annotation can also appear in the API documentation generated by Javadoc according to Java's documentation mechanism.

Do not confuse the `@since` marker inside a **Javadoc comment** with a Java annotation. `@since` is a Javadoc tag, whereas `@PackagePolicy(...)` is a Java annotation located outside the comment.

## 10. Common Mistakes with `PACKAGE` and `package-info.java`

### 10.1. Placing a package annotation in a regular class file

An **invalid** example if placed in `OrderService.java`:

```java
@PackagePolicy(owner = "platform")
package com.example.orders;

public class OrderService {}
```

Annotations on a package declaration may only be placed in a compilation unit named `package-info.java`. How to fix: move the annotation and the annotated `package ...;` line to `package-info.java`; keep the regular package declaration and the class in `OrderService.java`.

### 10.2. Using the wrong `@Target`

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@interface TypeOnly {}
```

The `TypeOnly` annotation only allows the `TYPE` target, so `@TypeOnly package com.example.orders;` in `package-info.java` is invalid. If you intend to attach it to a package, change it to `@Target(ElementType.PACKAGE)` or add `PACKAGE` to the set of allowed targets.

### 10.3. Missing `@Retention(RUNTIME)` when reflection is needed

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.PACKAGE)
@interface BuildMarker {}
```

`BuildMarker` is valid and has the default retention `CLASS`. If you apply `@BuildMarker` in `package-info.java`, do not expect `pkg.getAnnotation(BuildMarker.class)` to return the annotation at runtime. If the program needs to read it via reflection, add `@Retention(RetentionPolicy.RUNTIME)` to the annotation type and recompile/repackage.

### 10.4. Missing a required element

```java
@interface OwnerInfo {
    String team();
    String contact() default "";
}
```

Both `@OwnerInfo` and `@OwnerInfo(contact = "dev@example.test")` are invalid if `team` has no `default`. You need to pass `team = "platform"` or redesign a default value if there is a business reason to do so.

In addition, to make this annotation type attach to packages explicitly, you should add `@Target(ElementType.PACKAGE)`.

### 10.5. Wrong package name or source path

For example, the package declaration says `package com.example.order;` (singular), whereas the project intends to lay out the `com.example.orders` package (plural). The actual package name is the value **in the `package` statement**, not inferred from the directory name. A mismatch can cause the annotation to end up in a different package from the class being read, or cause a build error depending on configuration.

Verify that the source path, the contents of `package-info.java`, and the `package` statement of the class in question all point to the same package.

### 10.6. Assuming annotations automatically apply to subpackages

`com.example.orders` and `com.example.orders.internal` are **two different packages**. An annotation on `com.example.orders` is not automatically inherited by `com.example.orders.internal`.

If a subpackage also needs package-level metadata, declare a separate `package-info.java` for the subpackage, or build a hierarchical lookup rule on the framework side when needed. This is custom-defined logic, not built-in `@Inherited` semantics for packages.

### 10.7. Declaring package metadata in multiple places

Do not create multiple compilation units containing an **annotated package declaration** for the same package. Java allows at most one annotated package declaration per package within an applicable compilation scope.

In practice, keep a single clear `package-info.java` file in the corresponding package and avoid duplicates across multiple source roots that could cause build errors or conflicts.

### 10.8. Confusing `package-info.java` with `module-info.java`

`package-info.java` describes a **package**; `module-info.java` declares a **module** (Java 9+). Annotations for modules target `ElementType.MODULE` and are placed on the module declaration; annotations for packages target `ElementType.PACKAGE` and are placed on the package declaration. The two are not interchangeable.

## 11. When Should You Use Package Annotations?

Some reasonable use cases:

- Tagging a package domain with the responsible team or unit name so internal tools can generate reports.
- Providing metadata for architecture checkers: which layer, group, or scope a package belongs to.
- Configuring package-level rules when a framework is actually **programmed to read package annotations**.
- Producing metadata needed during compilation via an annotation processor, or needed for reflection at runtime.

Design example:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

enum Layer {
    API, SERVICE, PERSISTENCE
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PACKAGE)
@interface Architecture {
    Layer layer();
    String owner();
}
```

Usage site, in `package-info.java` in the same package as `Architecture` (or with a fully qualified reference to the annotation type):

```java
@Architecture(layer = Layer.SERVICE, owner = "platform")
package com.example.service;
```

**Key point to understand:** this is data describing architecture. By default, the compiler does not prevent a `SERVICE` package from calling a `PERSISTENCE` package because of this annotation. To enforce dependency rules, you need a checker, build plugin, or framework dedicated to reading and evaluating the metadata.

Good design should keep elements well-typed, provide sensible defaults, and choose `@Retention` based on where processing actually occurs. Avoid embedding frequently changing data or secrets into annotations because metadata may be distributed along with compiled artifacts.

## 12. Self-Check Exercises

Consider the following annotation type:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PACKAGE)
@interface ResponsibleTeam {
    String value();
    int priority() default 1;
}
```

Assume you have the files `src/com/example/catalog/package-info.java` and `src/com/example/catalog/CatalogService.java`.

Determine the answer for each question:

1. Is writing `@ResponsibleTeam("catalog")` immediately before `package com.example.catalog;` in `package-info.java` valid?
2. Is writing `@ResponsibleTeam(value = "catalog", priority = 2)` in the same position valid?
3. Is placing `@ResponsibleTeam("catalog")` immediately before `class CatalogService` valid?
4. Is replacing `package-info.java` with `CatalogService.java` containing an annotated package declaration compliant with the rules?
5. Can `CatalogService.class.getAnnotation(ResponsibleTeam.class)` read the annotation placed on the package?
6. Can `CatalogService.class.getPackage().getAnnotation(ResponsibleTeam.class)` read the annotation at runtime when `package-info.class` is compiled and packaged properly?
7. If the retention is changed to `SOURCE`, will the `getAnnotation` query at runtime still find the annotation?
8. Does the `com.example.catalog.internal` package automatically receive the annotation from `com.example.catalog`?

Answers:

1. **Yes.** `value()` is a required element and is used in shorthand form.
2. **Yes.** Both elements are passed with the correct types, and `priority` can be specified explicitly.
3. **No.** `ResponsibleTeam` only allows `PACKAGE`, not `TYPE`.
4. **No.** Package annotations must be placed in a compilation unit named `package-info.java`.
5. **No.** The annotation is attached to the package, not directly to the class.
6. **Yes, if runtime metadata and the classpath are prepared properly.** `@Retention(RUNTIME)` allows reflection to read the package annotation.
7. **No.** `SOURCE` is not retained in the class file for reflection at runtime.
8. **No.** Subpackages are independent and do not inherit package annotations under default Java rules.

## 13. Checklist Before Using in a Project

- The annotation type declares `@Target(ElementType.PACKAGE)` if it is only used at the package level.
- If runtime reflection is needed, `@Retention(RetentionPolicy.RUNTIME)` is set.
- In `package-info.java`, the annotation is placed before the `package ten.package;` statement.
- The file name is kept strictly as `package-info.java`; the source path and package name match according to the build layout.
- All elements without a `default` are provided with the correct names, types, and Java annotation value rules.
- Package Javadoc is written in a `/** ... */` block if the package needs API documentation.
- The runtime artifact contains the appropriate package metadata, including `package-info.class` when needed.
- Read using `SomeClass.class.getPackage().getAnnotation(...)` when querying a package's annotation, handling the case where it returns `null`.
- Do not expect package annotations to propagate automatically down to classes, methods, or subpackages.
- If the annotation has business meaning, identify which tool/framework will actually read and process the metadata.

Understanding `PACKAGE` properly helps place metadata **at the right level**. `package-info.java` connects an `@interface` annotation definition with a package declaration, while retention and the annotation-reading code determine whether that metadata is used at runtime.
