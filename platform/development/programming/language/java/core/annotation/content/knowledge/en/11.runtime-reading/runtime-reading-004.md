# Reading Annotations on Package, Module, and RecordComponent at Java Runtime

When working with reflection, many developers start with `Class.getAnnotation(...)`, `Method.getAnnotation(...)`, or `Field.getAnnotation(...)`. However, Java also allows placing and reading annotations on three components with quite different scopes: **package**, **module**, and **record component**.

- **Package annotation** describes package-level metadata; the source is typically placed in `package-info.java` and read at runtime through a `java.lang.Package` object.
- **Module annotation** describes metadata of a **named module** under JPMS (Java Platform Module System); the source is placed on the `module` declaration in `module-info.java` and read through `java.lang.Module`.
- **Record-component annotation** is attached to components in a record declaration, for example `record Account(@Label String id) {}`; at runtime, it is read through `java.lang.reflect.RecordComponent`.

All three support the API based on **`AnnotatedElement`**, but they represent **different entities**. Getting the annotations of a class is not equivalent to getting the annotations of the package, module, or record component containing that class.

## 1. Common Conditions for Reflection to Read Annotations

An annotation type can be declared with meta-annotations:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.PACKAGE)
@Retention(RetentionPolicy.RUNTIME)
@interface PackageLabel {
    String value();
}
~~~

Two conditions need to be separated:

1. **`@Target`** specifies **where placement is valid**. For example, `PACKAGE` is for package declarations, `MODULE` is for module declarations, and `RECORD_COMPONENT` is for record component declarations.
2. **`@Retention(RUNTIME)`** specifies that the annotation is retained until runtime so that reflection APIs return it. If `@Retention` is not declared, the default is `CLASS`; `SOURCE` or `CLASS` annotations are not read as runtime declaration annotations via `getAnnotation(...)` calls.

An annotation without a consumer does not create functionality on its own. For example, `@PackageLabel("catalog")` only stores a label; the program or framework must retrieve the metadata and interpret the label if it wants to handle it differently.

### Common API: AnnotatedElement

`Package`, `Module`, and `RecordComponent` all implement `java.lang.reflect.AnnotatedElement`. Common methods include:

| Method | Result and Purpose |
| --- | --- |
| `getAnnotation(A.class)` | An annotation of type `A` that is directly present or present under the present rules; returns `null` if absent |
| `getDeclaredAnnotation(A.class)` | An annotation of type `A` directly declared; returns `null` if absent |
| `getAnnotations()` | Array of annotations present according to the `AnnotatedElement` contract |
| `getDeclaredAnnotations()` | Array of directly declared annotations, without searching other elements |
| `isAnnotationPresent(A.class)` | Checks whether an annotation of type `A` is present |
| `getAnnotationsByType(A.class)` | Retrieves all annotations of type `A` according to repeatable/container rules |
| `getDeclaredAnnotationsByType(A.class)` | Retrieves annotations of type `A` directly or indirectly through a container declared on the element itself |

For **`Package`, `Module`, and `RecordComponent`**, an annotation is not automatically "inherited" from a related class or superclass. `@Inherited` has special semantics mainly when querying **class annotations** along superclasses; it is not a propagation mechanism for package, module, or component metadata.

If repeatable annotations (`@Repeatable`) are needed, use `getAnnotationsByType`/`getDeclaredAnnotationsByType` to retrieve the base annotations that may reside in a container; a single `getAnnotation` call does not automatically unpack the entire container.

## 2. Package Annotation: Defined in package-info.java

### 2.1. Valid Placement

Package metadata is attached to the **package declaration**. For package `demo.meta`, create the file **`package-info.java`**:

~~~java
@PackageLabel("catalog")
package demo.meta;
~~~

This is an **illustrative source snippet**: the `PackageLabel` annotation type must be within appropriate import/lookup scope and must declare `@Target(PACKAGE)` and `@Retention(RUNTIME)` if it is to be read at runtime. A complete example with the corresponding files is in Section 5.

`package-info.java` is the standard location to centralize package documentation and annotations. This file will be compiled into **`package-info.class`** when it needs to hold metadata. The `Package` API reads runtime package annotations from the `package-info.class` corresponding to that package's code source.

Do **not** place a package annotation before a regular `class` and expect it to become a package annotation. Adding `@PackageLabel` to a class is an invalid placement if the target only allows `PACKAGE`.

### 2.2. How to Obtain a Package and Read Metadata

~~~java
Package pkg = Account.class.getPackage();
PackageLabel tag = pkg.getAnnotation(PackageLabel.class);
if (tag != null) {
    System.out.println(tag.value());
}
~~~

This is a **code snippet inside a method**, assuming the types `Account` and `PackageLabel` already exist. Meaning:

- `Account.class.getPackage()` looks up the runtime package associated with class `Account`.
- `pkg.getAnnotation(PackageLabel.class)` reads the annotation on the **package**, not on the class `Account`.
- Check for `null` because the package might not declare that annotation; do not assume every class sharing the same package name has the expected metadata.

### 2.3. Runtime Package Depends on Class Loader / Code Source

`Package` represents a **runtime package**, which is tied to the class loader and how the package is defined, rather than just a package name string. With the same package name but different class loaders, you should not assume that the metadata/package object are completely identical.

For typical applications, **prefer `SomeClass.class.getPackage()`** when a class belonging to the target package is already known. Older static APIs like `Package.getPackage(String)` have limitations regarding already-defined packages and class loader context, so it is not appropriate to infer that any package can be queried by name alone.

If you forget to compile or package `package-info.class`, the runtime may not see the annotation even though `package-info.java` exists in the source. When diagnosing issues, check the build artifacts, not just the source files.

## 3. Module Annotation: Placed in module-info.java

### 3.1. A Module Is Not a Package

Java 9 introduced JPMS and `java.lang.Module`. A **named module** is declared in `module-info.java`:

~~~java
@demo.meta.ModuleInfoTag("inventory")
module demo.meta {
}
~~~

The annotation must have `@Target(ElementType.MODULE)` and appropriate retention if it needs to be read at runtime. When the module is compiled, this metadata resides in the module's **`module-info.class`**.

A module declaration is different from a package declaration: `module demo.meta` and `package demo.meta` are two independent concepts even if their names happen to match textually. `module-info.java` is not the place for package annotations; `package-info.java` is not the place for module annotations.

A module contains multiple packages; a package belongs to a module in a configured runtime (subject to JPMS constraints on package ownership). Annotations on a module **do not automatically propagate to all Package objects** inside it.

### 3.2. Reading the Module of a Class

~~~java
Module module = Account.class.getModule();
System.out.println(module.isNamed());
ModuleInfoTag marker = module.getAnnotation(ModuleInfoTag.class);
if (marker != null) {
    System.out.println(marker.value());
}
~~~

This is an illustrative snippet, assuming `Account` belongs to a module that declares `ModuleInfoTag`.

- `Class.getModule()` returns the `Module` object that the class belongs to.
- `module.isNamed()` distinguishes a **named module** from an **unnamed module**.
- `module.getAnnotation(ModuleInfoTag.class)` looks up metadata on the module declaration.

If classes are run on the regular **classpath**, they reside in the **unnamed module**. The `Module` object still exists and `isNamed()` returns `false`, but there is no `module-info.class` of a named module to hold annotations. According to the API, `Module.getAnnotation(...)` on an unnamed module returns `null`; `getAnnotations()` returns an empty array.

To truly test module annotations, you need to compile and run using the **module path** with `module-info.java`. Simply placing a file named `module-info.java` into a project running on the classpath is not enough to ensure the code executes in named-module mode.

### 3.3. Module Descriptor Is Not an Annotation Query

`module.getDescriptor()` returns `java.lang.module.ModuleDescriptor` containing JPMS information such as `requires`, `exports`, `opens`, `uses`, and `provides`. To read annotations on the module declaration, use `module.getAnnotation(...)` per the `AnnotatedElement` API. These are two different kinds of metadata.

In practice, a class being in a named module **does not mean that package is exported or opened to other modules**. When writing a framework that scans external modules, you must still consider module readability and access rules; the example in Section 5 reads from code within the same module, so no special `exports` or `opens` configuration is needed.

## 4. RecordComponent: Reading Metadata in a Record Declaration

A record is a form of class standardized since Java 16. For example:

~~~java
record Account(@ComponentInfoTag("record-only") String id, int age) {}
~~~

Each name/type pair in the header, such as `String id` or `int age`, is a **record component**. It is neither a `Field` object nor a `Method`, even though Java generates the corresponding field, accessor, and constructor components.

### 4.1. Obtaining RecordComponent via Reflection

~~~java
if (Account.class.isRecord()) {
    for (java.lang.reflect.RecordComponent component
            : Account.class.getRecordComponents()) {
        System.out.println(component.getName());
    }
}
~~~

This is a code snippet inside a method. `Class.isRecord()` helps check beforehand. `getRecordComponents()` returns an array of `RecordComponent` objects in **declaration order** if the class is a record; for a non-record class, the API returns **`null`**, so do not iterate directly without checking first.

`RecordComponent` provides:

| Method | Purpose |
| --- | --- |
| `getName()` | Component name, for example `id` |
| `getType()` | Raw type as `Class<?>` |
| `getGenericType()` | Generic type when the component has a generic type |
| `getAccessor()` | `Method` representing the accessor such as `id()` |
| `getDeclaringRecord()` | Record class declaring the component |
| `getAnnotation(...)` / `getAnnotationsByType(...)` | Declaration annotations on the record component itself |
| `getAnnotatedType()` | Annotations on the **type use** of the component's type (if any) |

Important point: **the declaration annotation of a record component** and **an annotation on the type used to declare the component** are two distinct metadata locations.

### 4.2. @Target(RECORD_COMPONENT) Keeps the Annotation Specifically on RecordComponent

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.RECORD_COMPONENT)
@Retention(RetentionPolicy.RUNTIME)
@interface ComponentInfoTag {
    String value();
}

record Account(@ComponentInfoTag("record-only") String id) {}
~~~

With the target set only to `RECORD_COMPONENT`, the metadata applies to the component element and is read via:

~~~java
var component = Account.class.getRecordComponents()[0];
var info = component.getAnnotation(ComponentInfoTag.class);
System.out.println(info.value());  // record-only
~~~

This is an **illustrative snippet** (it needs to be placed inside a method) and is not a complete application example. Do not use `Account.class.getAnnotation(ComponentInfoTag.class)` to look up a component's annotation: the class and the component are two different `AnnotatedElement` instances.

### 4.3. Propagation: One Annotation Can Appear in Multiple Places

The JLS also allows an annotation written on a record component to be **propagated** to the corresponding generated declarations if the annotation type permits those targets. For example:

~~~java
@Target({
    ElementType.RECORD_COMPONENT,
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER
})
@Retention(RetentionPolicy.RUNTIME)
@interface CrossCheck {
    String value();
}

record Account(@CrossCheck("copied") String id, int age) {}
~~~

In a record with **an implicit accessor and canonical constructor**, the annotation can appear on:

1. `RecordComponent id` thanks to `RECORD_COMPONENT`.
2. Field `id` generated by the record thanks to `FIELD`.
3. Implicitly generated accessor method `id()` thanks to `METHOD`.
4. Formal parameter `id` of the inferred canonical constructor thanks to `PARAMETER`.

Do not assume that Java automatically creates four copies of **every** annotation. Only the corresponding declarations matching valid targets receive the annotation; retention also determines whether they can be read at runtime. When an accessor or canonical constructor is **explicitly declared**, the propagation rules differ: do not assume that an annotation on the component is automatically attached to an explicitly declared accessor or explicitly written formal parameters. Check the JLS and the actual source code instead of assuming propagation always happens.

An annotation with only `@Target(RECORD_COMPONENT)` **does not automatically appear on the field, accessor, or parameter**. This is a very useful control case when debugging a framework that mistakenly reads `Field` instead of `RecordComponent`.

### 4.4. TYPE_USE Differs from RECORD_COMPONENT

Suppose we define:

~~~java
@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface NonNullLike {}

record Customer(@NonNullLike String name) {}
~~~

`@NonNullLike` is a **type annotation** attached to the `String` type being used. To read type-use annotations, go through `RecordComponent.getAnnotatedType().getAnnotations()` or call `getAnnotation(NonNullLike.class)` on that `AnnotatedType`.

`RecordComponent.getAnnotations()` returns the **declaration annotations** of the component. An annotation targeting only `TYPE_USE` should not be looked up by assuming it is also present as a declaration annotation on `RecordComponent`. If you design an annotation with both `RECORD_COMPONENT` and `TYPE_USE`, the metadata may be stored in separate areas depending on each role.

The name `NonNullLike` only expresses intent; a custom annotation does not automatically make the Java compiler check for non-null. To validate, you need a checker/processor or a runtime consumer.

## 5. Runnable Java 17 Example: Package, Module, and Record in the Same Program

We create a named module **`demo.meta`** containing the annotation types and a record. All sources reside in this module, so both `module-info.java` and `package-info.java` are actually compiled. Directory structure:

~~~text
src/
└── demo.meta/
    ├── module-info.java
    └── demo/
        └── meta/
            ├── ModuleInfoTag.java
            ├── PackageInfoTag.java
            ├── ComponentInfoTag.java
            ├── CrossCheck.java
            ├── package-info.java
            ├── Account.java
            └── Main.java
~~~

### File 1: src/demo.meta/module-info.java

~~~java
@demo.meta.ModuleInfoTag("inventory")
module demo.meta {
}
~~~

We use the fully qualified name of the annotation type because `module-info.java` is annotating the module declaration. No `exports` is needed because the example runs `Main` inside the module itself.

### File 2: src/demo.meta/demo/meta/ModuleInfoTag.java

~~~java
package demo.meta;

import java.lang.annotation.*;

@Target(ElementType.MODULE)
@Retention(RetentionPolicy.RUNTIME)
public @interface ModuleInfoTag {
    String value();
}
~~~

### File 3: src/demo.meta/demo/meta/PackageInfoTag.java

~~~java
package demo.meta;

import java.lang.annotation.*;

@Target(ElementType.PACKAGE)
@Retention(RetentionPolicy.RUNTIME)
public @interface PackageInfoTag {
    String value();
}
~~~

### File 4: src/demo.meta/demo/meta/ComponentInfoTag.java

~~~java
package demo.meta;

import java.lang.annotation.*;

@Target(ElementType.RECORD_COMPONENT)
@Retention(RetentionPolicy.RUNTIME)
public @interface ComponentInfoTag {
    String value();
}
~~~

### File 5: src/demo.meta/demo/meta/CrossCheck.java

~~~java
package demo.meta;

import java.lang.annotation.*;

@Target({
    ElementType.RECORD_COMPONENT,
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER
})
@Retention(RetentionPolicy.RUNTIME)
public @interface CrossCheck {
    String value();
}
~~~

### File 6: src/demo.meta/demo/meta/package-info.java

~~~java
@PackageInfoTag("catalog")
package demo.meta;
~~~

The `@PackageInfoTag` annotation here is attached to the **package declaration**, not to a class inside the package.

### File 7: src/demo.meta/demo/meta/Account.java

~~~java
package demo.meta;

public record Account(
        @ComponentInfoTag("record-only")
        @CrossCheck("copied") String id,
        int age) {
}
~~~

`ComponentInfoTag` targets only `RECORD_COMPONENT`; `CrossCheck` allows all four positions: component/field/method/parameter. The record here has a compiler-generated accessor and canonical constructor.

### File 8: src/demo.meta/demo/meta/Main.java

~~~java
package demo.meta;

import java.lang.reflect.RecordComponent;

public class Main {
    public static void main(String[] args) throws Exception {
        Package pkg = Account.class.getPackage();
        Module module = Account.class.getModule();
        RecordComponent[] components = Account.class.getRecordComponents();
        RecordComponent id = components[0];

        var field = Account.class.getDeclaredField("id");
        var accessor = id.getAccessor();
        var ctorParam = Account.class
                .getDeclaredConstructor(String.class, int.class)
                .getParameters()[0];

        System.out.println("package=" +
                pkg.getAnnotation(PackageInfoTag.class).value());
        System.out.println("moduleNamed=" + module.isNamed());
        System.out.println("module=" +
                module.getAnnotation(ModuleInfoTag.class).value());
        System.out.println("record=" + Account.class.isRecord());
        System.out.println("components=" + components.length);
        System.out.println("component=" + id.getName() + ":" +
                id.getAnnotation(ComponentInfoTag.class).value());
        System.out.println("recordOnlyOnField=" +
                (field.getAnnotation(ComponentInfoTag.class) != null));
        System.out.println("crossField=" +
                (field.getAnnotation(CrossCheck.class) != null));
        System.out.println("crossAccessor=" +
                (accessor.getAnnotation(CrossCheck.class) != null));
        System.out.println("crossParameter=" +
                (ctorParam.getAnnotation(CrossCheck.class) != null));
    }
}
~~~

### Compile and Run

In the directory **containing `src`**, using JDK 17 or newer:

~~~bash
javac --release 17 -d out --module-source-path src -m demo.meta
java --module-path out -m demo.meta/demo.meta.Main
~~~

**Exact stdout (verified with JDK 21 using `--release 17`):**

~~~text
package=catalog
moduleNamed=true
module=inventory
record=true
components=2
component=id:record-only
recordOnlyOnField=false
crossField=true
crossAccessor=true
crossParameter=true
~~~

The results confirm:

- `package=catalog`: the value read via `Account.class.getPackage().getAnnotation(PackageInfoTag.class)` comes from `package-info.class`.
- `moduleNamed=true` and `module=inventory`: the code runs on the **module path**, so `Account.class.getModule()` is the named module `demo.meta`; the metadata comes from `module-info.class`.
- `record=true`: `Account` is indeed a record.
- `components=2`: the declared components are `id` and `age`; the order reflects the record header.
- `component=id:record-only`: `ComponentInfoTag` is retrieved through `RecordComponent`.
- `recordOnlyOnField=false`: the target is only `RECORD_COMPONENT`, so that declaration annotation is not present on field `id`.
- The three results `crossField=true`, `crossAccessor=true`, and `crossParameter=true`: `CrossCheck` is propagated to the corresponding compiler-generated declarations because its target permits it.

If you want to test failure cases yourself, you can remove `@Retention(RUNTIME)` from **one** annotation type and observe that reflection cannot read that annotation after recompiling. However, the lines in `Main` currently call `.value()` directly without checking for `null` to keep the example concise; when experimenting with changing retention, add a `null` check before calling `value()`.

## 6. Common Mistakes When Reading These Three Types of Annotations

### Mistake 1: Looking Up Package Metadata Using Class.getAnnotation

~~~java
// Illustrative snippet; not a standalone file.
var label = Account.class.getAnnotation(PackageInfoTag.class);
~~~

`PackageInfoTag` has `@Target(PACKAGE)`, so the call above will not see the annotation in `package-info.java`. Correct approach:

~~~java
var label = Account.class.getPackage()
        .getAnnotation(PackageInfoTag.class);
~~~

### Mistake 2: Forgetting package-info.java in the Build

Having an annotation in the source without `package-info.class` being built or copied to the output can cause the runtime not to see the metadata. Check the output directory/module/JAR and ensure package-info is compiled along with the related classes.

### Mistake 3: Looking Up Module Annotations While Running on the Classpath

When running on the classpath, `Class.getModule()` typically returns the **unnamed module**. Even if you place module annotations in code elsewhere, calling it on an unnamed module cannot read metadata of a named module that is not participating in that execution mode. Check `isNamed()` and how `--module-path` and `-m` are used.

### Mistake 4: Confusing ModuleDescriptor with Module AnnotatedElement

`ModuleDescriptor` reflects JPMS dependency/export/open/service declarations; to retrieve module annotations, use `java.lang.Module.getAnnotation(...)`.

### Mistake 5: Confusing Record Component with Field or Accessor

A record has field `id`, method `id()`, and component `id`, but the three entities are reflected through different objects. With `@Target(RECORD_COMPONENT)`, you must read through `getRecordComponents()`. If a framework only scans fields, metadata present only on the component will be missed.

### Mistake 6: Failing to Distinguish Declaration Annotations from Type-Use Annotations

`RecordComponent.getAnnotation(...)` reads declaration metadata on the component; `getAnnotatedType()` is used when metadata belongs to the declared type. An annotation on `List<@NonNullLike String>` can even reside on a type argument: in that case, you must traverse `AnnotatedParameterizedType` to find the appropriate annotation location.

### Mistake 7: Assuming @Inherited Applies Generally

`@Inherited` does not propagate package annotations into enclosed classes, nor module annotations into packages, nor component annotations into the record class. If an annotation appears on a field or accessor generated from a component, that is due to **record propagation rules and target compatibility**, not `@Inherited`.

### Mistake 8: Using Reflection Without Null Checks and Access Scope

`getAnnotation(...)` returns `null` when the annotation is absent; `getRecordComponents()` returns `null` if the `Class` object is not a record. Framework code should check beforehand. Reflection on non-public members may require specific module access rules when reading/writing values or invoking methods; do not confuse the ability to read metadata with permission to invoke or access every member.

## 7. How to Design a Maintainable Metadata API

1. **Choose the right ownership level for the metadata.** Package-wide policies → package annotation; module-wide capabilities/metadata → module annotation; per-field metadata of a record → record component annotation.
2. **Restrict @Target appropriately.** Set `PACKAGE`, `MODULE`, or `RECORD_COMPONENT` when you only want one location; only add `FIELD/METHOD/PARAMETER/TYPE_USE` when intentionally supporting consumers at those locations.
3. **Choose retention based on the consumer.** Compile-time tools can use SOURCE/CLASS annotations; runtime reflection requires RUNTIME. Do not overuse reflection when unnecessary.
4. **Define package/module build conventions.** For packages, compile and package `package-info.class`. For modules, compile and run properly in named-module mode so that `module-info.class` takes effect.
5. **Test with real sources.** You can write a test that creates package-info/module-info/record, compiles with `javac --release 17`, and then verifies through `Package`/`Module`/`RecordComponent` instead of testing only `Class`.
6. **Define explicit business semantics.** Annotations carry metadata; the framework must specify when scanning occurs, how missing annotations are handled, precedence when multiple values exist, and the effect of runtime configuration.

### Quick Decision Scenarios

| Requirement | Annotation Location | How to Read at Runtime |
| --- | --- | --- |
| Categorize an entire package of APIs | `package-info.java`, `@Target(PACKAGE)` | `AnyClassInPackage.class.getPackage().getAnnotation(...)` |
| Label at the JPMS module level | `module-info.java`, `@Target(MODULE)` | `SomeClass.class.getModule().getAnnotation(...)` |
| Metadata specific to record component `id` | Record header, `@Target(RECORD_COMPONENT)` | Iterate `RecordComponent[]`, `component.getAnnotation(...)` |
| Constraint attached to a type argument | `@Target(TYPE_USE)` | `AnnotatedType` and its corresponding subtypes |
| Want an annotation from a component to also appear on generated field/accessor/parameter | Add `FIELD/METHOD/PARAMETER` targets | Read the corresponding `Field`/`Method`/`Parameter` and verify propagation |

## 8. Knowledge Self-Check

**1. Why does `Account.class.getAnnotation(PackageInfoTag.class)` return null even though Account's package has the annotation?** Because `Class` and `Package` are two different `AnnotatedElement` instances. Read `Account.class.getPackage().getAnnotation(...)`.

**2. Can you retrieve module annotations when running in an unnamed module?** The `Module` still exists, but an unnamed module does not carry annotations declared in a named module's `module-info.class`. With `Module.getAnnotation`, the result is `null` on an unnamed module.

**3. What does `Account.class.getRecordComponents()` return if Account is a regular class, not a record?** `null`. If it is a record, it returns an array in component declaration order.

**4. Does an annotation with only `@Target(RECORD_COMPONENT)` automatically appear in `getDeclaredField("id")`?** No. This target only allows a declaration annotation on the component.

**5. Why is `@CrossCheck` read on the accessor and canonical constructor parameter in the example?** Because the annotation also includes the `METHOD` and `PARAMETER` targets and the example uses compiler-generated implicit members. You must not extrapolate that result to every explicitly declared accessor or constructor.

**6. Does `@Retention(RUNTIME)` automatically carry an annotation from a package into a class or from a record component into the record class?** No. Retention only determines when the data remains present; ownership location and propagation are governed by separate rules.

**7. Through what should an annotation with only `@Target(TYPE_USE)` on a component's `String` type be read?** Through `RecordComponent.getAnnotatedType()`, rather than treating it as a declaration annotation on the component.

## 9. Official References

- Java SE 21 API — **Package**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Package.html
- Java SE 21 API — **Module**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html
- Java SE 21 API — **RecordComponent**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/RecordComponent.html
- Java SE 21 API — **AnnotatedElement**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedElement.html
- Java Language Specification — **Record classes `8.10** and **annotation placement `9.7.4**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html and https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.7.4
- Java Language Specification — **Package and module declarations, Chapter 7**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html

When writing a tool that reads annotations, start by asking **"which entity is this metadata declared on?"**. If it is a package, module, or record component, retrieve the corresponding `Package`, `Module`, or `RecordComponent` object and query it through `AnnotatedElement`; choosing the right object is just as important as `@Target`, `@Retention`, and how the program is compiled and launched.
