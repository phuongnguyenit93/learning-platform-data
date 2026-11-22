# RUNTIME Condition and the AnnotatedElement Interface When Reading Java Annotations

## 1. Problem to Understand: An Annotation in Source Code Is Not Necessarily Readable at Runtime

When looking at the code:

```java
@Track("checkout")
class CheckoutService {}
```

one might assume that the program can always retrieve `@Track` via reflection. This is **only true when the necessary conditions are met**, especially the `@Retention(RetentionPolicy.RUNTIME)` retention policy, where the annotation is placed, and querying through the appropriate API.

In Java, an annotation is **metadata**; by itself, it does not execute business logic, generate logging, or perform validation automatically. A program, library, or framework must read the metadata and actively execute the related behavior.

The two concepts that need to be connected are:

1. **`RetentionPolicy.RUNTIME`:** the annotation is retained so that the Java Reflection API can see it after the JVM loads the class.
2. **`java.lang.reflect.AnnotatedElement`:** the common interface that provides methods to read annotations on reflected elements, such as a class, method, field, or constructor.

Conceptual example:

```java
@Retention(RetentionPolicy.RUNTIME)
@interface Track {
    String value();
}
```

With the proper definition and an annotated `CheckoutService`, the following snippet can read the value:

```java
Track track = CheckoutService.class.getAnnotation(Track.class);
if (track != null) {
    System.out.println(track.value());
}
```

This example is only an **illustrative** snippet that requires the appropriate imports; a complete program with `javac`/`java` commands is provided in Section 8.

## 2. Mandatory Requirement: `@Retention(RetentionPolicy.RUNTIME)`

`@Retention` resides in `java.lang.annotation` and is placed **on the annotation type**, not on each usage site of that annotation:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface RuntimeInfo {
    String name();
}
```

The three retention policies:

| Policy | When `javac` compiles source | In the class file | Visible via standard reflection? |
|---|---|---|---|
| `RetentionPolicy.SOURCE` | Present in source for compiler/processor processing | Not retained | No |
| `RetentionPolicy.CLASS` | Present and written to the class file | Yes | No |
| `RetentionPolicy.RUNTIME` | Present and written to the class file | Yes | Yes |

If **there is no `@Retention`**, Java defaults to `CLASS`:

```java
@interface NotRuntimeByDefault {
    String value();
}
```

This is completely valid at compile time. However, if `@NotRuntimeByDefault("x")` is placed on a class, `Class.getAnnotation(NotRuntimeByDefault.class)` does **not** return the applied annotation because it does not have `RUNTIME` retention.

To make it accessible via reflection, ensure that:

- The annotation type declares `@Retention(RetentionPolicy.RUNTIME)`.
- The annotation is actually applied to the **exact element** you are querying.
- `@Target`, if declared, permits the corresponding placement.
- The class files are **recompiled** after retention changes and loaded from the correct artifact/classpath.
- The program uses the reflection API appropriate for the annotation's location, including repeatable and inheritance rules when relevant.

**Distinction:** `@Target` answers "where can it be annotated?", whereas `@Retention` answers "how long is the annotation retained?". An annotation with `@Target(METHOD)` and `@Retention(RUNTIME)` still will not appear on the `Class` object if it is only placed on a method.

## 3. What Is `AnnotatedElement`?

`java.lang.reflect.AnnotatedElement` is an interface in the Java Reflection API used to query annotations on an *element* capable of being annotated.

Types that provide this capability include:

- `Class<?>`: a type declaration, such as a class/interface/enum.
- `Method`: a specific method.
- `Field`: a field.
- `Constructor<?>`: a constructor.
- `Parameter`: a method/constructor parameter.
- `Package`: package metadata.
- `RecordComponent`: a component of a Java record (Java 16+).
- `AnnotatedType`: represents annotations attached to a **type-use position** (*type use*), such as a return type or a type argument.

Example of obtaining the objects to query:

```java
Class<?> type = OrderService.class;                  // Class
Method method = type.getDeclaredMethod("submit");    // Method
Field field = type.getDeclaredField("orderId");      // Field
Constructor<?> ctor = type.getDeclaredConstructor(); // Constructor
```

This is an illustrative snippet, assuming `OrderService` has a `submit()` method, an `orderId` field, and a no-arg constructor, and that the calls take place in a context capable of handling `ReflectiveOperationException`.

A single variable can hold multiple kinds of elements thanks to the common interface:

```java
AnnotatedElement element = OrderService.class;
```

The corresponding import is:

```java
import java.lang.reflect.AnnotatedElement;
```

As a result, shared code can accept an `AnnotatedElement` and query for an annotation type without having to write a separate function for `Class`, `Method`, or `Field`.

### Declared Elements and Type-Use Positions Are Two Different Things

Example:

```java
@NonNull
String name;
```

The meaning of `@NonNull` depends on `@Target`: it can be an annotation on the field declaration, or on the `String` type used here (or both if the target permits). When you need to read *type-use annotations*, APIs via `AnnotatedType` such as `Field.getAnnotatedType()` are the appropriate path; do not assume that `Field.getAnnotation(...)` reads every annotation in a type signature.

## 4. Core Methods of `AnnotatedElement`

| Method | Primary Meaning | Return Type |
|---|---|---|
| `getAnnotation(A.class)` | An annotation of type `A` that is *present* according to API rules; does not automatically unwrap repeatable containers | `A` or `null` |
| `getDeclaredAnnotation(A.class)` | An annotation of type `A` directly declared on the element itself | `A` or `null` |
| `getAnnotations()` | Array of annotations *present* on the element | `Annotation[]` |
| `getDeclaredAnnotations()` | Array of directly declared annotations | `Annotation[]` |
| `getAnnotationsByType(A.class)` | Array of annotations of type `A`, including values inside a repeatable container when applicable | `A[]` |
| `getDeclaredAnnotationsByType(A.class)` | Annotations `A` directly declared or indirectly contained on the element **itself** | `A[]` |
| `isAnnotationPresent(A.class)` | Checks whether an annotation of type `A` is *present* | `boolean` |

These APIs accept `Class<A>`, where `A` is a specific annotation type. Example:

```java
Audit audit = clazz.getAnnotation(Audit.class);
boolean audited = clazz.isAnnotationPresent(Audit.class);
```

Here, `clazz` is a valid `Class<?>`, and `Audit` is a defined annotation type.

Key principles:

- `getAnnotation(...)` and `getDeclaredAnnotation(...)` return **a single annotation** or `null`; they do not return `Optional`.
- `isAnnotationPresent(A.class)` is semantically equivalent to `getAnnotation(A.class) != null`.
- `getAnnotationsByType(...)` returns **an array**; if there are no matching elements, it is an empty array, not `null`.
- Do not rely on any particular ordering of `getAnnotations()` results across **different types**. For repeatable annotations, the order of repeated occurrences is preserved according to language and API rules.
- `getAnnotationsByType` understands the indirect containment mechanism, whereas `getAnnotation` does not automatically convert a container into one of its inner annotations.

## 5. When Do `getAnnotation` and `getDeclaredAnnotation` Differ?

The **`Declared`** keyword emphasizes "declared **directly on this element**". APIs without `Declared` may include *present/inherited* rules for annotations on a class.

Consider:

```java
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@interface ModuleGroup {
    String value();
}

@ModuleGroup("billing")
class ParentService {}

class ChildService extends ParentService {}
```

When reading:

```java
ModuleGroup viaPresent =
        ChildService.class.getAnnotation(ModuleGroup.class);
ModuleGroup viaDeclared =
        ChildService.class.getDeclaredAnnotation(ModuleGroup.class);
```

Result:

- `viaPresent` can retrieve the `ModuleGroup("billing")` annotation via the `@Inherited` rule on the superclass.
- `viaDeclared` is `null` because `ChildService` does not declare `@ModuleGroup` itself.

**`@Inherited` applies only to annotations on class declarations when looking up through superclasses.** It does not automatically apply to overridden methods, fields, constructors, implemented interfaces, or packages. Nor does an annotation on an interface automatically appear when querying annotations of a class implementing that interface.

For a `RUNTIME` annotation **without `@Inherited`**, both `getAnnotation` and `getDeclaredAnnotation` on a subclass without the annotation applied will return `null`.

### "Inherited Method" Does Not Mean "Method Annotations Are Inherited"

`ChildService.class.getMethod("run")` can return a `Method` representing a public method declared in the superclass. When calling `getAnnotation` on that `Method` itself, you are querying the annotation of the **reflected method**. This is not an `@Inherited` mechanism for methods. If a subclass overrides the method without reapplying the annotation, the parent method's annotation is not automatically copied to the overriding method.

To find an annotation from a parent method according to a business rule, the program must explicitly traverse the class hierarchy and look up the matching method.

## 6. Reading Repeatable Annotations: Why Is `getAnnotationsByType` Important?

Suppose a repeatable annotation `@Tag` has a container `@Tags`:

```java
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@interface Tags {
    Tag[] value();
}

@Tag("core")
@Tag("backend")
class Example {}
```

When the compiler sees two `@Tag` annotations on the same class, the repeated annotations are indirectly contained in a `@Tags` annotation.

```java
Tag one = Example.class.getAnnotation(Tag.class);
Tag[] all = Example.class.getAnnotationsByType(Tag.class);
Tags container = Example.class.getAnnotation(Tags.class);
```

In the example above:

- `one` is `null` because no single `Tag` is directly *present* on the class after being wrapped in the container.
- `all` is an array containing **two `Tag` annotations**, in the order `"core"` followed by `"backend"`.
- `container` is non-`null` and `container.value()` contains both `Tag` annotations.

If there is only a single `@Tag` directly present, `getAnnotation(Tag.class)` can return that annotation itself and the container typically does not appear.

**Practical rule:** If an annotation type is marked with `@Repeatable` and you want to retrieve **all** occurrences, use `getAnnotationsByType(T.class)` or the `getDeclaredAnnotationsByType(T.class)` variant depending on inheritance needs. Do not use `getAnnotation` to count repeatable annotations.

For repeatable annotations to be readable at runtime in the way described above, the retention of the repeatable annotation and its container must be compatible; typically, both use `RUNTIME`.

## 7. Does a `CLASS`-Only Annotation "Disappear"?

No. `RetentionPolicy.CLASS` retains metadata in the class file, but standard Java reflection does not return that annotation.

Example:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.CLASS)
@interface BuildMarker {
}

@BuildMarker
class OrderWorker {}
```

At runtime:

```java
boolean found =
        OrderWorker.class.isAnnotationPresent(BuildMarker.class);
```

`found` is `false`, even though a post-compilation bytecode-reading tool can find the metadata in the `OrderWorker.class` file.

Use `javap -v OrderWorker` to inspect the class-file attributes, such as `RuntimeInvisibleAnnotations` for a declaration annotation stored with `CLASS` retention. Annotations with `RUNTIME` typically appear in `RuntimeVisibleAnnotations`. For annotations at type-use positions, the attribute name may end with `TypeAnnotations`.

If the goal is to read bytecode using the ASM library or a classfile analysis tool, `CLASS` may be sufficient. If the program actually uses `AnnotatedElement.getAnnotation` at runtime, `RUNTIME` is required.

**Note:** Reflection and bytecode-scanning tools are two different consumption paths. A framework stating that it "scans annotations" is not enough to infer the retention without knowing whether it reads class bytes or reflects on `Class` objects.

## 8. Complete Java 17+ Program: SOURCE/CLASS/RUNTIME, Inherited, and Repeatable

Create a single file named **`AnnotatedElementDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedElement;
import java.lang.reflect.Method;
import java.util.Arrays;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface CompileHint {}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface BuildHint {}

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Audit {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Group {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tags {
    Tag[] value();
}

@CompileHint
@BuildHint
@Audit("orders")
@Group("backend")
@Tag("core")
@Tag("api")
class BaseService {
    @Audit("submit")
    public void submit() {}
}

class ChildService extends BaseService {}

public class AnnotatedElementDemo {
    private static String tagsOf(AnnotatedElement element) {
        Tag[] tags = element.getAnnotationsByType(Tag.class);
        String[] names = Arrays.stream(tags)
                .map(Tag::value)
                .toArray(String[]::new);
        return Arrays.toString(names);
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        AnnotatedElement element = BaseService.class;

        System.out.println("SOURCE visible="
                + element.isAnnotationPresent(CompileHint.class));
        System.out.println("CLASS visible="
                + element.isAnnotationPresent(BuildHint.class));
        System.out.println("RUNTIME value="
                + element.getAnnotation(Audit.class).value());
        System.out.println("tags=" + tagsOf(element));
        System.out.println("one direct Tag="
                + (element.getAnnotation(Tag.class) != null));
        System.out.println("container present="
                + element.isAnnotationPresent(Tags.class));

        System.out.println("child Group="
                + ChildService.class.getAnnotation(Group.class).value());
        System.out.println("child declares Group="
                + (ChildService.class.getDeclaredAnnotation(Group.class) != null));
        System.out.println("child Audit="
                + (ChildService.class.getAnnotation(Audit.class) != null));

        Method method = BaseService.class.getDeclaredMethod("submit");
        System.out.println("method Audit="
                + method.getAnnotation(Audit.class).value());
    }
}
```

From the directory containing the file, run:

```bash
javac AnnotatedElementDemo.java
java AnnotatedElementDemo
```

Expected stdout:

```text
SOURCE visible=false
CLASS visible=false
RUNTIME value=orders
tags=[core, api]
one direct Tag=false
container present=true
child Group=backend
child declares Group=false
child Audit=false
method Audit=submit
```

Explanation by result group:

1. `CompileHint` and `BuildHint` are applied in the source, but `AnnotatedElement` does not see them via reflection: their corresponding policies are `SOURCE` and `CLASS`.
2. `Audit` has `RUNTIME`, so `"orders"` can be read from the `BaseService` class.
3. The two `@Tag` annotations on the class are combined by the compiler inside `Tags`; `getAnnotationsByType(Tag.class)` returns both elements in order, whereas `getAnnotation(Tag.class)` does not unwrap the container.
4. `Group` has both `@Inherited` and `RUNTIME`, so `ChildService` can find the annotation from `BaseService` using `getAnnotation(Group.class)`, whereas `getDeclaredAnnotation(Group.class)` does not find a `Group` declaration directly on `ChildService`.
5. `Audit` does **not** have `@Inherited`, so `ChildService.class.getAnnotation(Audit.class)` returns `null` even though the superclass has that annotation.
6. `Method` is also an `AnnotatedElement`. Looking up the `submit` method of `BaseService` allows reading `@Audit("submit")`.

In the example, only `AnnotatedElementDemo` is a public class, with a name matching the file; the remaining types have package-private access so they can reside in the same source file. The example uses built-in Java 17 APIs and requires no external libraries.

## 9. How to Quickly Check Whether an Element Has an Annotation

In a metadata processor, avoid calling `.value()` on the result of `getAnnotation(...)` without checking for `null` first.

```java
static String describe(AnnotatedElement element) {
    Audit audit = element.getAnnotation(Audit.class);
    if (audit == null) {
        return "not audited";
    }
    return "audited: " + audit.value();
}
```

This is an illustrative helper, using `Audit` defined in Section 8.

If only a boolean is needed:

```java
boolean annotated = element.isAnnotationPresent(Audit.class);
```

When you need to read all annotations regardless of type:

```java
java.lang.annotation.Annotation[] annotations =
        element.getAnnotations();
```

This array may contain container annotations if an annotation is repeated multiple times; if you want the data for a repeatable type, use `getAnnotationsByType`.

The `getDeclaredAnnotations` and `getDeclaredAnnotationsByType` APIs are useful when the logic wants to **consider only metadata on the declaration itself**, without receiving inherited metadata from a superclass.

## 10. Reflecting at the Right Location: class, method, field, parameter, package, type-use

Suppose we have the following definition:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.TYPE,
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER
})
@interface Label {
    String value();
}
```

Application sites:

```java
@Label("service")
class InvoiceService {
    @Label("identifier")
    private String id;

    @Label("operation")
    void send(@Label("recipient") String recipient) {}
}
```

**You need to obtain the right `AnnotatedElement`:**

```java
Class<?> type = InvoiceService.class;
Label classLabel = type.getAnnotation(Label.class);

Field field = type.getDeclaredField("id");
Label fieldLabel = field.getAnnotation(Label.class);

Method method = type.getDeclaredMethod("send", String.class);
Label methodLabel = method.getAnnotation(Label.class);

Parameter parameter = method.getParameters()[0];
Label parameterLabel = parameter.getAnnotation(Label.class);
```

These are illustrative snippets running in a context that handles `ReflectiveOperationException` and imports `java.lang.reflect.Field`, `Method`, and `Parameter`. Each object corresponds to a different location, and an annotation on the class **does not automatically appear on a method or field**.

For package annotations, call `SomeClass.class.getPackage()` and read the metadata on the `Package`; a `package-info.java` file with the annotation and `RUNTIME` retention is needed if you want to access it at runtime.

For type-use annotations, declare `@Target(ElementType.TYPE_USE)` and query the appropriate `AnnotatedType`. For example, for a field with a type-use annotation, you can call `field.getAnnotatedType()` and read the annotation from that object. Calling `getAnnotations` directly on `Field` is not equivalent to reading all annotations on the type positions within the field.

## 11. Common Mistakes When Reading Annotations via Reflection

### 11.1. Missing `@Retention(RUNTIME)` While Calling `getAnnotation`

```java
@interface Config {
    String value();
}

@Config("fast")
class FastTask {}
```

`Config` defaults to `RetentionPolicy.CLASS`. `FastTask.class.getAnnotation(Config.class)` returns `null`. Fix this by adding `@Retention(RetentionPolicy.RUNTIME)` to `Config` if the processing path needs reflection, and **recompile the classes that use the annotation as well**.

### 11.2. Confusing Class Annotations with Method Annotations

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Work {}

class Worker {
    @Work
    void run() {}
}
```

Calling `Worker.class.getAnnotation(Work.class)` does not find `@Work` because it is placed on `run()`. You must obtain the appropriate `Method`, such as `Worker.class.getDeclaredMethod("run")`, and then call `getAnnotation(Work.class)`.

### 11.3. Reading a Repeatable Annotation Using `getAnnotation`

Two `@Tag` annotations are typically stored via a container, so `getAnnotation(Tag.class)` can return `null`. Use `getAnnotationsByType(Tag.class)` to retrieve all values.

### 11.4. Expecting `@Inherited` to Work on Methods or Interfaces

`@Inherited` only has inheritance semantics on a **class declaration** through a superclass under the API's conditions. If a method is overridden or an interface is implemented, reflection does not automatically include the corresponding annotations in the result for the new element. If you want different rules, you must design a custom lookup function.

### 11.5. Using `getDeclaredAnnotations` and Assuming Runtime Annotations Were Lost

A subclass can read an `@Inherited` annotation from its parent class via `getAnnotations()` or `getAnnotation(...)`, whereas `getDeclaredAnnotations()` does not contain that annotation because the subclass does not declare it directly. This is a difference in **lookup scope**, not an incorrect retention.

### 11.6. Forgetting to Check for `null` or an Empty Array

`getAnnotation(...)` returns `null` when not found. `getAnnotationsByType(...)` returns an **empty array** when there are no matching annotations. Handle both cases properly instead of calling an element method directly on a `null` result.

### 11.7. Changing Only `@Retention` While Running Old Class Files

Changing `SOURCE` or `CLASS` to `RUNTIME` in the annotation definition does not automatically update all already-compiled usage sites. Clean and recompile the relevant classes, then verify the actual classpath/JAR being executed. You can use `javap -v` to determine which class files retain the annotation.

### 11.8. Assuming `RUNTIME` Causes a Framework to Automatically Recognize an Annotation

`RUNTIME` only allows the metadata to be reflected. A framework still must know the annotation type, have the proper scan scope, and have code to process it. If `@CustomRoute` is completely custom and the router never reads it, no URL routes will be registered automatically.

## 12. Notes When Designing APIs That Use `AnnotatedElement`

A function that accepts `AnnotatedElement` can support multiple locations:

```java
static <A extends java.lang.annotation.Annotation>
A find(AnnotatedElement element, Class<A> annotationType) {
    return element.getAnnotation(annotationType);
}
```

This is an illustrative generic helper, requiring the import of `java.lang.reflect.AnnotatedElement`. The name `find` does not mean the function automatically searches superclasses, overridden methods, or containers beyond the default semantics of `getAnnotation`.

If you want to support repeatable annotations, an API returning **an array** is usually more appropriate:

```java
static <A extends java.lang.annotation.Annotation>
A[] findAll(AnnotatedElement element, Class<A> annotationType) {
    return element.getAnnotationsByType(annotationType);
}
```

When using this code in a real-world application:

- Determine whether the feature requires **directly declared** metadata or accepts class-level inheritance.
- Identify annotation types that may be repeatable, and choose the `ByType` API when all values are needed.
- Identify which `AnnotatedElement` is being passed in, avoiding confusing method annotations with class annotations.
- Verify handling for missing annotations, missing types on the classpath, or incompatible changes between the annotation version and the annotated class.
- Do not treat metadata as a source of secrets: `RUNTIME` annotations reside in the artifact and can be observed; even `CLASS` annotations can be read from bytecode.

## 13. Self-Check Exercises

Suppose we have the following definitions:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.CLASS)
@interface BinaryOnly {}

@Retention(RetentionPolicy.RUNTIME)
@Inherited
@interface Owner {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Flags.class)
@interface Flag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@interface Flags {
    Flag[] value();
}

@BinaryOnly
@Owner("platform")
@Flag("secure")
@Flag("logged")
class Parent {}

class Child extends Parent {}
```

Answer the following:

1. What does `Parent.class.isAnnotationPresent(BinaryOnly.class)` return?
2. What value does `Parent.class.getAnnotation(Owner.class)` have?
3. Does `Child.class.getAnnotation(Owner.class)` return an annotation?
4. What does `Child.class.getDeclaredAnnotation(Owner.class)` return?
5. Can `Parent.class.getAnnotation(Flag.class)` read both `Flag` annotations?
6. How many elements does `Parent.class.getAnnotationsByType(Flag.class)` have?
7. Does `Child.class.getAnnotationsByType(Flag.class)` automatically inherit the two flags from Parent?
8. If you want to read `BinaryOnly` in the `Parent.class` file after compilation, what kind of tool should you use?
9. If you want `BinaryOnly` to be found by standard reflection, what must be changed and what needs to be done afterward?

Answers:

1. **`false`**: `BinaryOnly` only has `CLASS` retention.
2. An `Owner` whose `value()` is `"platform"`.
3. **Yes**: `Owner` has `@Inherited` and `RUNTIME`, so it is inherited from the superclass.
4. **`null`**: `Child` does not declare `@Owner` directly.
5. **No**: `getAnnotation(Flag.class)` does not unwrap the repeatable container.
6. **Two** elements, with values `"secure"` and `"logged"` in order.
7. **No**: `Flag` does not have `@Inherited`, so the flags on `Parent` are not automatically resolved from `Child`.
8. A **class file/bytecode** reading tool such as `javap -v` or a bytecode parser; standard reflection does not see `CLASS` retention.
9. Add `@Retention(RetentionPolicy.RUNTIME)` to `BinaryOnly` and **recompile `Parent` along with the related sources**, then verify that the new artifact is being run.

## 14. End-of-Article Checklist

- Placed `@Retention(RetentionPolicy.RUNTIME)` on the annotation type if runtime reflection is needed.
- Do not confuse the default `CLASS` retention with `RUNTIME`.
- Distinguish `@Retention` (lifetime) from `@Target` (application location).
- Calling `getAnnotation` on the **right `AnnotatedElement`**: class, method, field, constructor, parameter, package, or the appropriate `AnnotatedType`.
- Use `getDeclaredAnnotation(s)` when direct metadata is needed; understand that `getAnnotation(s)` may include inherited annotations on a class.
- Understand that `@Inherited` is limited to class/superclass; do not assume inheritance for methods/interfaces/packages.
- Use `getAnnotationsByType` to retrieve all indirectly contained repeatable annotations.
- Check for `null` on `getAnnotation` and handle empty arrays for `getAnnotationsByType`.
- Distinguish bytecode scanners that see `CLASS` retention from Java reflection that only sees `RUNTIME`.
- Rebuild classes that use the annotation after changing retention, and verify the correct artifact/classpath.
- A framework/tool must **actually read the metadata** for behavior to happen; applying an annotation alone does not execute logic.

Key takeaway: `RUNTIME` retention determines **whether metadata is observable via reflection**, while `AnnotatedElement` provides **the interface to read the right element**. Choosing the right API, the right reflected object, and the right inheritance/repeatable rules will prevent most errors where annotations appear to "disappear" at runtime.
