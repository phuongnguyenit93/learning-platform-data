# Naming, Package Organization, and Choosing Access Scope for Annotation Types in Java

## 1. An Annotation Type Is Also a Java Type

In Java, a custom annotation is declared using the `@interface` syntax. That declaration creates an **annotation type** with a fully qualified name, a package, access rules, and the ability to be used from other classes. Therefore, designing an annotation type requires addressing three questions: how to name it so that it conveys the right meaning, which package to place it in, and which code should be allowed to reference that name.

An example of a very small annotation type:

```java
package com.example.order.annotations;

public @interface Reviewed {
}
```

Here:

- `Reviewed` is the **simple name**, used in the form `@Reviewed` after importing it or when in the same package.
- `com.example.order.annotations.Reviewed` is the **fully qualified name** to distinguish it from `Reviewed` types in other packages.
- `public` determines the accessibility of the annotation type name from elsewhere, still subject to module restrictions if the application uses the Java Platform Module System (JPMS).
- `@interface` is the syntax for declaring an annotation type; the name after `@interface` follows Java identifier rules, just like class/interface names.

**Distinguishing two concerns:** the visibility of the *annotation type* determines where source code can use `@Reviewed`; whereas `@Target` and `@Retention` determine which elements the annotation can be applied to and until which stage it is retained. `@Target`/`@Retention` do not replace an access modifier.

## 2. Naming: Make What the Annotation Expresses Clear When Read

An annotation's name is part of the API because it appears directly before declarations. You should prefer names that are **short, clear, and carry business meaning or tool-processed behavior**, using **UpperCamelCase** (PascalCase), for example:

| Name | Intended Meaning | Notes |
| --- | --- | --- |
| `@Reviewed` | The element has passed the review step according to project conventions | Expresses a state |
| `@RequiresApproval` | The element requires an approval check | Expresses a requirement |
| `@Audited` | The element is marked to be processed by the audit system | Meaningful if there actually is an audit processor |
| `@InternalApi` | API intended for internal use | States a contractual usage restriction |
| `@A1`, `@Flag2`, `@MyAnnotation` | Meaning is hard to guess | Should be avoided unless there is a special context |

Useful naming rules:

1. **Names should express a contract**, not merely describe a technique. For example, `@RequiresApproval` conveys the meaning more clearly than `@CheckFlag`.
2. **Maintain consistency within the same module.** If a group of names describes state using adjectives, do not arbitrarily switch to vague naming conventions on related annotations.
3. **There is no need to append the `Annotation` suffix to every name.** `@Reviewed` is usually cleaner than `@ReviewedAnnotation`. Use the suffix if it genuinely helps distinguish the name.
4. **Do not choose duplicate names that can easily be confused with standard annotations**, such as `Override`, `Deprecated`, or `SuppressWarnings`. If there are two types with the same simple name, they must be distinguished by an import or a fully qualified name.
5. **Choose stable names** for annotations published as a library: changing a package or type name forces usage sites to update imports/where the annotation is applied.

A meaningful name still does not create behavior by itself. For example, applying `@Audited` to a method **does not make Java log automatically**. There must be an appropriate compiler, annotation processor, framework, or reflection code to read and act on the annotation.

## 3. Package Organization: Place Annotations by Ownership Scope and Usage

Java uses packages to create namespaces and group related types. For an annotation type, it should be placed close to **the contract or feature it serves**, especially when the annotation is part of an API used by multiple packages.

An example structure:

```text
src/
└── com/
    └── example/
        └── order/
            ├── annotations/
            │   ├── Reviewed.java
            │   └── RequiresApproval.java
            ├── internal/
            │   └── InternalOnly.java
            └── service/
                └── OrderService.java
```

- Annotations frequently used by external code can be placed in `com.example.order.annotations` (or `annotation`; choose one consistent convention).
- Annotations that only serve the implementation of part of a feature can reside directly in that feature's package or an appropriate `internal` package.
- For large projects, organizing by domain or module—for example, `com.example.payment.annotations` and `com.example.inventory.annotations`—helps each part own its contract.

Java conventions to follow:

- Package names are usually written in **lowercase**, such as `com.example.order.annotations`, which helps avoid confusion with class names and reduces case-sensitivity errors across file systems.
- Prefer reverse domain names to reduce namespace collisions. Avoid creating custom packages in platform-reserved namespaces such as `java.*`.
- In a source file, the `package` declaration should be placed at the top of the file (after comments and package annotations, if any), followed by `import` statements and type declarations.
- Following common Java project structure, `package com.example.order.annotations;` corresponds to the `com/example/order/annotations` directory. When passing files directly to `javac`, the source file location does not strictly have to match syntactically, but a structure matching the package helps IDEs/build tools and human readers work properly.
- Avoid putting all unrelated annotations into a single shared utility package, which obscures domain boundaries and introduces unnecessary dependencies.
- Avoid the **default package** for reusable code: types in an unnamed package cannot be imported from a named package.

If an annotation is intended to mark a *package*, define it with `@Target(ElementType.PACKAGE)` and place it on the `package` declaration in **`package-info.java`**. This is a different situation from annotations placed on a class or method; the same principles regarding naming and access control still apply.

## 4. Choosing Access Scope for Annotation Types

### 4.1. Top-Level Annotation Types: public or package-private

At the **top-level** (declared directly in a file, not nested inside a class or interface), the two common and valid choices are:

| Declaration Form | Who Can Directly Reference the Annotation Type? | When to Use? |
| --- | --- | --- |
| `public @interface Reviewed {}` | Other packages can use it when the package/type is validly accessible | The annotation belongs to a shared API or a contract used across multiple packages |
| `@interface InternalMarker {}` | Source code within the **same package** | The annotation is only needed internally within the package |

You cannot declare `private @interface` or `protected @interface` at the top level. `private`/`protected` have meaning for **member types nested inside a class** according to that class's rules.

For a top-level `public` annotation type named `Reviewed`, the source file must be named **`Reviewed.java`** according to Java's file-naming rule during standard source compilation. A single source file cannot contain two public top-level types with different names to act as such independent public declarations.

### 4.2. Nested Annotation Types

You can declare an annotation type inside a class as a member type:

```java
class Workflow {
    private @interface LocalMarker {}

    @LocalMarker
    void step() {}
}
```

`LocalMarker` is hidden within an access scope appropriate for a `private` member type of `Workflow`. This example only illustrates valid syntax; it does not have `main` to run standalone. Member annotation types are inherently static like member interface types; they are not tied to a `Workflow` instance.

An annotation type declared inside an **interface** is a public member type according to interface rules and cannot use `private` the way a class member does in the example above. Do not use a nested annotation merely to hide an API that should be clearly reusable from its own package.

### 4.3. Elements *Inside* an Annotation Type

Annotation elements are declared in the form of parameterless methods, for example:

```java
public @interface Reviewed {
    String reviewer() default "team";
}
```

`reviewer()` is an **annotation element**: this method has `public abstract` characteristics by default. That **does not mean the annotation type containing it is automatically public**. Access to `@interface Reviewed` itself is still determined by the modifier on the type declaration.

Annotation elements have their own restrictions on data types and default values. When designing a shared annotation, you should not confuse those constraints with the visibility of the type.

## 5. Runnable Java 17+ Example: public and package-private Across Multiple Packages

We will create a public annotation used across packages and a package-private annotation for internal use only. In the example, `Reviewed` is retained until runtime so `Main` can read it via reflection; `InternalMarker` is only used within the same package and retained in source. These `RetentionPolicy` choices serve to illustrate intended usage; they **neither open nor close access scope**.

The complete structure of the five lines of functionality is organized into four source files:

```text
src/
└── com/example/training/annotation/
    ├── api/
    │   └── Reviewed.java
    ├── impl/
    │   ├── InternalMarker.java
    │   └── ReportService.java
    └── app/
        └── Main.java
```

**File 1: `src/com/example/training/annotation/api/Reviewed.java`**

```java
package com.example.training.annotation.api;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
public @interface Reviewed {
    String reviewer() default "team";
}
```

`public` allows the `impl` and `app` packages to reference the annotation. `@Target` only allows applying it to type or method declarations; `@Retention(RUNTIME)` makes it observable via reflection at runtime. `@Documented` causes the annotation to appear in the Javadoc documentation of the annotated element when appropriate; it does not make the annotation perform business logic on its own.

**File 2: `src/com/example/training/annotation/impl/InternalMarker.java`**

```java
package com.example.training.annotation.impl;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface InternalMarker {
}
```

Because it lacks the `public` modifier, `InternalMarker` is **package-private**. Code in `impl` can use it, but `Main` in `app` cannot import or directly reference `InternalMarker`. `SOURCE` means this marker is not retained in the class file to be retrieved via reflection.

**File 3: `src/com/example/training/annotation/impl/ReportService.java`**

```java
package com.example.training.annotation.impl;

import com.example.training.annotation.api.Reviewed;

@InternalMarker
@Reviewed(reviewer = "qa")
public class ReportService {
    @Reviewed(reviewer = "dev")
    public String status() {
        return "ready";
    }
}
```

`ReportService` can use `@InternalMarker` because both declarations are in the same `impl` package, even though they reside in two different files. `ReportService` can also use `@Reviewed` because the annotation type is public and properly imported.

**File 4: `src/com/example/training/annotation/app/Main.java`**

```java
package com.example.training.annotation.app;

import com.example.training.annotation.api.Reviewed;
import com.example.training.annotation.impl.ReportService;

public class Main {
    public static void main(String[] args) throws NoSuchMethodException {
        Reviewed typeInfo = ReportService.class.getAnnotation(Reviewed.class);
        Reviewed methodInfo = ReportService.class
                .getDeclaredMethod("status")
                .getAnnotation(Reviewed.class);

        System.out.println(typeInfo.reviewer());
        System.out.println(methodInfo.reviewer());
        System.out.println(new ReportService().status());
    }
}
```

From the directory containing `src`, use JDK 17 or later to compile; the command is written on a single line for use with standard shells:

```bash
javac --release 17 -d out src/com/example/training/annotation/api/Reviewed.java src/com/example/training/annotation/impl/InternalMarker.java src/com/example/training/annotation/impl/ReportService.java src/com/example/training/annotation/app/Main.java
java -cp out com.example.training.annotation.app.Main
```

**Exact stdout:**

```text
qa
dev
ready
```

Explanation of the result:

1. `javac -d out` places the `.class` files into the package directory tree under `out`.
2. `Main` can access `ReportService` and `Reviewed` because they are public top-level types, and in this classpath example there are no additional module restrictions.
3. Reflection finds `@Reviewed` on the class and method because the annotation has `RetentionPolicy.RUNTIME`.
4. The syntax `reviewer = "qa"` and `reviewer = "dev"` sets distinct values for the annotation element; this is metadata and does not cause `status()` to do any extra work on its own.
5. `InternalMarker` is only used within `impl`, consistent with its package-private visibility.

Trying to write `import com.example.training.annotation.impl.InternalMarker;` in `Main.java` will cause a compilation error regarding access rights: a non-public top-level type cannot be accessed from outside its package.

## 6. Common Misconceptions

### 6.1. Thinking @Retention(RUNTIME) Means public

False. `@Retention(RetentionPolicy.RUNTIME)` only specifies that the annotation remains present so the runtime can observe it through supported mechanisms. It does not grant permission to import it from another package. Conversely, a `public` annotation using `SOURCE` can still be imported and used normally in code outside the package during compilation; it simply does not remain in the bytecode.

### 6.2. Thinking @Target Determines Whether a Package Can Use It

`@Target(ElementType.TYPE)` means the annotation can be applied to appropriate type declarations; `ElementType.METHOD` for methods; `ElementType.PACKAGE` for package declarations. `@Target` is not access control. To restrict where **the annotation type can be referenced according to language visibility**, use an appropriate access scope and package design.

### 6.3. Choosing package-private Even When the API Needs to Be Used Across Multiple Packages

If multiple services in different packages need to use `@Reviewed`, place the annotation in a suitable API package and make it `public`. Do not scatter copies with the same name across individual packages; doing so creates distinct annotation types that are hard to detect with metadata-reading tools/frameworks.

### 6.4. Putting All Annotations into a Shared Package

The package `com.example.annotations` is not strictly wrong, but if it contains annotations from multiple unrelated domains, it reduces discoverability, increases dependencies, and makes API ownership ambiguous. Use an intentional package such as `com.example.order.annotations` when the domain scope is clear.

### 6.5. Confusing a Type's public Modifier with Accessibility in JPMS

In a project **not using JPMS** and on the same classpath, a `public` top-level type allows other packages to reference it when the dependency is present. In a **named module**, the consuming module must also have a readability relationship to the providing module (for example, `requires`), and the package containing the public type must be appropriately exported via `exports` for normal access from another module. `opens` serves deep reflective access under JPMS rules and does not replace `exports` for compiling normal API imports.

### 6.6. Renaming an Annotation While Forgetting Consumers

For example, renaming `@Reviewed` to `@ReviewChecked` requires checking both usage sites in Java code and places where tools read the annotation. Especially with a public annotation library, the fully qualified name is part of the contract. If a framework looks for the old type in metadata, simply updating the imports of a few classes is not enough.

## 7. Annotation Type Design Workflow

When adding a new annotation to a codebase:

1. **Identify the consumer:** compiler/annotation processor, framework, reflection, documentation generator, or simply a convention marker.
2. **Name by meaning:** a developer reading `@TênAnnotation` should understand what the annotation marks.
3. **Choose the package by ownership scope:** shared annotations in an API package; internal-only markers placed near the implementation.
4. **Choose visibility:** `public` when it needs to be referenced from other packages; package-private when direct use is restricted to the same package; nested private/protected only when a nested scope is truly appropriate.
5. **Choose `@Target`, `@Retention` based on actual usage:** `RUNTIME` is required if it needs to be read via reflection at runtime; `SOURCE` may be sufficient for an annotation processor running at compile time; `CLASS` retains it in the class file without requiring availability for runtime reflection.
6. **Verify from a caller in another package:** compile an example using the annotation, and confirm the imports, access rights, package path, and runtime data if any.
7. **Keep the name/package stable** if the annotation is part of a public API; when a change is needed, manage consumer updates as a contract change.

**Remember:** `@interface` creates a **Java type**. A meaningful name makes code easier to read, the package defines location and ownership, and access modifiers control the ability to reference that type directly. `@Target` and `@Retention` address other aspects of an annotation and therefore must be chosen independently of visibility.
