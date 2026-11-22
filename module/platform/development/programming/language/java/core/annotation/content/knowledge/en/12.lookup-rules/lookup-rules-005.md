# When Does Java Reflection Look Through a Container Annotation?

## 1. The Main Question

Since Java 8, an annotation type can be declared as **repeatable** using `@Repeatable`, meaning the same annotation can be attached multiple times at a single location. Java uses a **containing annotation type** (a container annotation, or *container* for short) to represent the component annotations.

Example:

```java
@Role("READ")
@Role("WRITE")
class DocumentService {}
```

The two lines above are valid if `Role` is declared as repeatable with the container `Roles`. During compilation, these two `@Role` annotations are represented indirectly through a single `@Roles` annotation with an array containing the `@Role` instances. Consequently, there is an important point: **not every reflection API automatically unwraps the container**.

- `getAnnotation(Role.class)` looks up **one present `Role` annotation** according to the rules of `AnnotatedElement`; it **does not automatically unwrap `Roles`** to retrieve a component `Role`.
- `getAnnotationsByType(Role.class)` is an API that **understands repeatable annotations**: it finds `Role` annotations appearing directly or **indirectly inside the corresponding container**, and returns an array.
- `getDeclaredAnnotationsByType(Role.class)` also unwraps the container, but only retrieves annotations declared **on the element itself**; it does not search up to superclasses.
- `getAnnotation(Roles.class)` looks up the **container annotation** itself and does not automatically convert the result into `Role[]`; after obtaining `Roles`, you can call `value()` to get the array of elements.

In short: **to see all repeated annotations of type T, use the `*AnnotationsByType(T.class)` methods**. The singular API `getAnnotation(T.class)` can return `null` even when the source shows multiple `@T` annotations.

## 2. Properly Defining a Repeatable Annotation and Its Container

For the `@Role` example to be repeatable, **both annotation types** are required:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Repeatable(Roles.class)
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Role {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Roles {
    Role[] value();
}
```

This is a supporting declaration example, with no `main` yet.

Part-by-part explanation:

1. `@Repeatable(Roles.class)` is placed on the **component annotation type** `Role`; its argument specifies which annotation type serves as the container.
2. `Roles` must declare an **element named exactly `value()`** with return type **`Role[]`**. A container holding `String[]` or `Object[]` is not considered a valid container for `Role`.
3. If the container also has other elements besides `value()`, those elements must have default values according to the Java constraints applied to containers.
4. Retention and target between `Role` and `Roles` must be compatible according to `@Repeatable` rules. For example, both have `@Retention(RUNTIME)` and `@Target(TYPE)` for a program that reads annotations on a class via reflection.
5. `RUNTIME` is required for reflection examples. If `CLASS` retention (the default when `@Retention` is not declared) is used, the annotation may be stored in the class file but will **not** be returned by these runtime reflection APIs.
6. If the component annotation is marked with `@Inherited`, the corresponding container annotation must also satisfy the `@Inherited` rules; a later section will illustrate both carrying `@Inherited`.

In the case above, the two syntaxes:

```java
@Role("READ")
@Role("WRITE")
class DocumentService {}
```

and:

```java
@Roles({@Role("READ"), @Role("WRITE")})
class DocumentService {}
```

describe the same two `Role` elements in the same order for the `Role`-typed lookup API. **They are two alternative ways of writing shown for illustration, not two `DocumentService` declarations placed together in one Java file.**

You should not understand this as Java creating two `Role`-type annotations considered "directly present" in the exact same way as when there is only one `@Role`. When repeated multiple times, the reflection model distinguishes between **direct** annotations and annotations **indirectly present** inside a container.

## 3. Four Foundational Concepts: Direct, Indirect, Present, and Associated

The Javadoc of the `AnnotatedElement` interface distinguishes several relationships between an annotation and the reflected element under consideration.

### 3.1. Directly Present

If a declaration has only a single `@Role("READ")`, then `Role` can be directly present on the element. Therefore:

```java
@Role("READ")
class SingleRole {}
```

`SingleRole.class.getAnnotation(Role.class)` will find `Role` when it has `RUNTIME` retention. `getAnnotationsByType(Role.class)` also returns a single-element array.

### 3.2. Indirectly Present — Through a Container

If the source declares multiple `@Role` annotations on the same target:

```java
@Role("READ")
@Role("WRITE")
class TwoRoles {}
```

then `Role` is considered **indirectly present** via `Roles`. With the `RUNTIME` retention configuration in this article:

- `TwoRoles.class.getAnnotation(Role.class)` returns `null` if `Role` appears only indirectly.
- `TwoRoles.class.getAnnotation(Roles.class)` returns a `Roles` instance on which `value()` can be called.
- `TwoRoles.class.getAnnotationsByType(Role.class)` returns two `Role` instances, in the order `READ`, `WRITE`.
- `TwoRoles.class.getDeclaredAnnotationsByType(Role.class)` also returns two `Role` instances because they are declared on this class itself.

Key point: **the existence of the container does not automatically convert `getAnnotation(Role.class)` into a multi-element API**.

### 3.3. Present — According to Singular Lookup Rules

An annotation type `T` is considered **present** on an element when it is directly present, or, in appropriate `Class` and `@Inherited` cases, inherited according to the API rules. "Present" in this sense is not synonymous with "indirectly present" for repeatable annotations.

Therefore, `getAnnotation(T.class)` can look up to a superclass for a class annotation marked with `@Inherited`, but that does **not** mean it unwraps the container of `T`.

### 3.4. Associated — According to ByType Rules

The `getAnnotationsByType` APIs use the concept of **associated**. For an element, an annotation type can be associated with it because there is a **direct** annotation, because there are multiple annotations **indirectly inside a container**, or because it is **inherited** according to the `@Inherited` rules applicable to classes.

This explains why `getAnnotationsByType(T.class)` is the right API when you need to cover both a single direct annotation and multiple component annotations inside a container.

## 4. Lookup Table: Which APIs Look Through the Container?

Assume `Role` is declared as in Section 2 and the classes have valid runtime annotations.

| API | Single direct `@Role("A")` | Two `@Role("A") @Role("B")` | Explicit container `@Roles({@Role("A"), @Role("B")})` |
| --- | --- | --- | --- |
| `getAnnotation(Role.class)` | One `Role("A")` | `null` if only container is present | `null` if only container is present |
| `getDeclaredAnnotation(Role.class)` | One `Role("A")` | `null` | `null` |
| `getAnnotationsByType(Role.class)` | `[A]` | `[A, B]` | `[A, B]` |
| `getDeclaredAnnotationsByType(Role.class)` | `[A]` | `[A, B]` | `[A, B]` |
| `getAnnotation(Roles.class)` | Normally `null` | `Roles` container | `Roles` container |
| `getDeclaredAnnotations()` | Contains `Role` | Contains `Roles` | Contains `Roles` |

This table examines annotations declared **right on the queried class**, without considering superclasses. When inheritance is involved, APIs without `Declared` on `Class` are also subject to `@Inherited` rules; see Section 7.

### Why Is getAnnotation(Roles.class) Not ByType?

When calling:

```java
Roles container = TwoRoles.class.getAnnotation(Roles.class);
Role[] parts = container == null ? new Role[0] : container.value();
```

you are **explicitly reading the container itself** and then retrieving its array. That is a valid approach when you know the exact `Roles` type and the container is actually present. However, this approach does not cover the case where there is only a direct `@Role` and no `@Roles`. Conversely:

```java
Role[] all = TwoRoles.class.getAnnotationsByType(Role.class);
```

covers both the case of a single direct annotation and multiple annotations indirectly inside a container. The condition is that `Role` is defined as repeatable with a valid container and has the desired runtime retention.

**Not every annotation containing an array of annotations is automatically unwrapped.** If an arbitrary container has `T[] value()` but `T` **does not declare `@Repeatable(Container.class)`**, then `getAnnotationsByType(T.class)` does not automatically treat that container as a source of `T`. The `@Repeatable` relationship in the **annotation type definition** is the deciding factor.

## 5. Java 17+ Example: Verifying on Classes, Explicit Containers, Inheritance, and Fields

This complete example demonstrates the trickiest points in a single run:

- A single directly attached annotation.
- Two repeated annotations represented by the compiler via a container.
- An explicitly written container, including an empty container.
- A subclass receiving repeated annotations from its superclass via `@Inherited`.
- A subclass declaring its own new annotation, replacing the type-based lookup result from the superclass.
- A field with two repeated annotations; the `ByType` API unwraps the container directly on the `Field` object.

Save the entire program below to **`ContainerLookupDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.List;

@Inherited
@Repeatable(Roles.class)
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.FIELD})
@interface Role {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.FIELD})
@interface Roles {
    Role[] value();
}

@Role("single")
class SingleRole {}

@Role("read")
@Role("write")
class RepeatedRole {}

@Roles({@Role("alpha"), @Role("beta")})
class ExplicitContainer {}

@Roles({})
class EmptyContainer {}

@Role("parent-a")
@Role("parent-b")
class ParentRole {}

class ChildWithoutRole extends ParentRole {}

@Role("child-only")
class ChildWithOwnRole extends ParentRole {}

class FieldHolder {
    @Role("encrypted")
    @Role("indexed")
    private String payload;
}

public class ContainerLookupDemo {
    static List<String> names(Role[] annotations) {
        return Arrays.stream(annotations).map(Role::value).toList();
    }

    public static void main(String[] args) throws NoSuchFieldException {
        System.out.println("single.get: "
                + SingleRole.class.getAnnotation(Role.class).value());
        System.out.println("single.byType: "
                + names(SingleRole.class.getAnnotationsByType(Role.class)));
        System.out.println("single.container: "
                + (SingleRole.class.getAnnotation(Roles.class) != null));

        System.out.println("repeated.get: "
                + RepeatedRole.class.getAnnotation(Role.class));
        System.out.println("repeated.byType: "
                + names(RepeatedRole.class.getAnnotationsByType(Role.class)));
        System.out.println("repeated.container: "
                + names(RepeatedRole.class.getAnnotation(Roles.class).value()));
        System.out.println("repeated.rawType: "
                + RepeatedRole.class.getDeclaredAnnotations()[0]
                    .annotationType().getSimpleName());

        System.out.println("explicit.byType: "
                + names(ExplicitContainer.class.getAnnotationsByType(Role.class)));
        System.out.println("empty.byType: "
                + names(EmptyContainer.class.getAnnotationsByType(Role.class)));
        System.out.println("empty.hasContainer: "
                + (EmptyContainer.class.getAnnotation(Roles.class) != null));

        System.out.println("child.associated: "
                + names(ChildWithoutRole.class.getAnnotationsByType(Role.class)));
        System.out.println("child.declared: "
                + names(ChildWithoutRole.class.getDeclaredAnnotationsByType(Role.class)));
        System.out.println("child.singular: "
                + ChildWithoutRole.class.getAnnotation(Role.class));
        System.out.println("childOwn.associated: "
                + names(ChildWithOwnRole.class.getAnnotationsByType(Role.class)));

        Field field = FieldHolder.class.getDeclaredField("payload");
        System.out.println("field.byType: "
                + names(field.getDeclaredAnnotationsByType(Role.class)));
        System.out.println("field.singular: "
                + field.getAnnotation(Role.class));
    }
}
```

Compile and run with **JDK 17 or later**, in the directory containing the file:

```bash
javac --release 17 ContainerLookupDemo.java
java ContainerLookupDemo
```

**Expected stdout, in exact program order:**

```text
single.get: single
single.byType: [single]
single.container: false
repeated.get: null
repeated.byType: [read, write]
repeated.container: [read, write]
repeated.rawType: Roles
explicit.byType: [alpha, beta]
empty.byType: []
empty.hasContainer: true
child.associated: [parent-a, parent-b]
child.declared: []
child.singular: null
childOwn.associated: [child-only]
field.byType: [encrypted, indexed]
field.singular: null
```

How to interpret the results:

1. `SingleRole` has exactly one direct `Role`: `getAnnotation(Role.class)` returns `Role` and `getAnnotationsByType(Role.class)` returns the array `[single]`. In this case, there is no `Roles` container.
2. `RepeatedRole` has two `Role` annotations: via reflection, the two components are indirectly present inside the `Roles` container. Therefore, `getAnnotation(Role.class)` is `null`, while `ByType` returns `[read, write]`.
3. `getAnnotation(Roles.class)` finds the container, and `container.value()` yields the two elements in order.
4. `getDeclaredAnnotations()[0]` on `RepeatedRole` is of annotation type `Roles` because here it has a runtime container on the class; you should not rely on index `0` if multiple different annotation types are present together.
5. `ExplicitContainer` uses an explicit container; `getAnnotationsByType(Role.class)` still looks through it to retrieve `alpha` and `beta`.
6. `EmptyContainer` has a **container but no `Role` elements**. `getAnnotationsByType(Role.class)` returns `[]` while `getAnnotation(Roles.class)` is non-`null`. Finding a container does not mean the container holds at least one element.
7. `ChildWithoutRole` declares neither `Role` nor `Roles`; `@Inherited` on both types allows `getAnnotationsByType(Role.class)` to see the two annotations on the superclass. `getDeclaredAnnotationsByType` returns an empty array. `getAnnotation(Role.class)` still does not unwrap the container on the superclass, so it returns `null`.
8. `ChildWithOwnRole` declares one direct `Role`: `getAnnotationsByType(Role.class)` returns `[child-only]`, **without automatically adding** `parent-a`/`parent-b` to the result.
9. `FieldHolder.payload` holds two `Role` annotations indirectly via a container. `Field.getDeclaredAnnotationsByType(Role.class)` unwraps the container; `Field.getAnnotation(Role.class)` does not unwrap it, so it returns `null`. `@Inherited` only means superclass inheritance for annotations **on classes**; it does not make field annotations inherit automatically.

The entire example only reads metadata; it does not invoke constructors, does not read the value of `payload`, and does not need `setAccessible(true)` to retrieve annotations of a private field.

## 6. Ordering When the Container Is Unwrapped

When declaring:

```java
@Role("first")
@Role("second")
@Role("third")
class Workflow {}
```

`Workflow.class.getAnnotationsByType(Role.class)` yields the `Role`-typed elements in the order `first`, `second`, `third`. In the container representation, that order corresponds to the order of the component annotations in the `value()` array.

With an explicit container:

```java
@Roles({
    @Role("third"),
    @Role("first"),
    @Role("second")
})
class ExplicitWorkflow {}
```

the result of `getAnnotationsByType(Role.class)` is in the order `third`, `first`, `second`. The `ByType` API may preserve the order of repeatable components, but **it does not cause Java to automatically execute** the corresponding actions sequentially. If order carries business meaning, the code consuming the metadata must define how to iterate or sort them.

In addition, do not infer **ordering across different annotation types** from `getAnnotations()` or `getDeclaredAnnotations()`. Those APIs do not provide a general ordering contract across annotation types. When you need to iterate over one type, retrieve the `ByType(T.class)` array directly.

## 7. @Inherited: When Does ByType Look Up to Superclasses?

`@Inherited` is a special meta-annotation intended for **annotations on class declarations**. It does not cause annotations on methods, fields, constructors, or interfaces to be inherited automatically in the same way.

In the full example, both types have `@Inherited`:

```java
@Inherited
@Repeatable(Roles.class)
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.FIELD})
@interface Role {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.FIELD})
@interface Roles {
    Role[] value();
}
```

When `Role` is repeatable and marked with `@Inherited`, its container must be appropriately marked with `@Inherited`. Otherwise, the annotation pair declaration may be invalid at compile time.

Useful rules for `Child.class.getAnnotationsByType(Role.class)`:

1. If `Child` itself has a direct `Role` or has a `Roles` container holding `Role` indirectly, the annotations on that class itself determine the result.
2. If `Child` itself has no direct/indirect `Role` and the `Role` type is marked with `@Inherited`, the API can find matching associated annotations from the nearest superclass according to the lookup rules.
3. `getDeclaredAnnotationsByType(Role.class)` does **not** search superclasses, even if the type has `@Inherited`.
4. The result of `getAnnotationsByType` does not merge all elements from the subclass and superclass by default. If merging is desired, business logic must walk the superclass chain manually and handle duplicates and ordering.

**Subtlety:** `Class.getAnnotation(Role.class)` on a subclass is also not considered an API that "unwraps a container on the superclass." It still looks up `Role` via the **present** relationship, whereas `getAnnotationsByType(Role.class)` uses the **associated** relationship and can find indirect elements inside an inherited `Roles` container.

If the annotation does not have `@Inherited`, `getAnnotationsByType` and `getDeclaredAnnotationsByType` on a subclass will not automatically see annotations declared solely on a superclass simply because they share the same hierarchy.

## 8. Boundaries of Looking Through Containers

### 8.1. Only Containers Declared via @Repeatable Are Unwrapped

The `getAnnotationsByType(T.class)` API does not unwrap an arbitrary annotation just because it has an element returning `T[]`. Type `T` must be marked with `@Repeatable(Container.class)` so the runtime recognizes the appropriate relationship.

Illustrative example:

```java
@interface Item {
    String name();
}

@interface ItemGroup {
    Item[] value();
}
```

If `Item` is **not** declared with `@Repeatable(ItemGroup.class)`, `getAnnotationsByType(Item.class)` does not automatically unwrap `ItemGroup`. The snippet above also lacks `RUNTIME`, so experimenting with reflection requires adding the appropriate retention. These two conditions address **two different concerns**: the container relationship and keeping metadata until runtime.

### 8.2. Retention Must Allow Runtime Observation

`@Repeatable` does not replace `@Retention(RUNTIME)`. With `SOURCE` annotations, information on classes/fields is generally absent from the class file. With `CLASS`, metadata is stored in the class file, but reflection does not expose it through the APIs discussed here. If you want to use `getAnnotationsByType` at runtime, design both the repeatable annotation and its container with appropriate `RUNTIME` retention.

### 8.3. Absence of Data Yields an Empty Array, Not null

`getAnnotationsByType(T.class)` and `getDeclaredAnnotationsByType(T.class)` return an **array**; when no matching elements exist, the array normally has length `0`, not `null`. Conversely, `getAnnotation(T.class)` and `getDeclaredAnnotation(T.class)` can return `null`.

In Java, you should handle this as follows:

```java
Role[] roles = type.getAnnotationsByType(Role.class);
if (roles.length == 0) {
    System.out.println("No roles");
}
```

This is an illustrative snippet assuming the variable `type` already has type `Class<?>` and the `Role` annotation is already defined.

### 8.4. The Difference Between Declared and Non-Declared

`getDeclaredAnnotationsByType(T.class)` returns annotations directly or indirectly declared on the element itself. `getAnnotationsByType(T.class)` can apply `@Inherited` when the element is a `Class` and the annotation meets the conditions. For `Field` or `Method`, `@Inherited` does not create an equivalent superclass lookup mechanism for metadata on member declarations.

Therefore, if you want only the metadata of a single class without considering inheritance, use `getDeclaredAnnotationsByType`; if you want to follow the standard inheritance rules for class annotations, use `getAnnotationsByType`.

### 8.5. The Actual Container Can Appear via Raw APIs

`getDeclaredAnnotations()` and `getAnnotations()` should not be treated as APIs that automatically unwrap each repeatable annotation. When a class has multiple `@Role` annotations, raw reflection can return the `Roles` container as a separate annotation. If code iterates over the raw results and checks `annotation.annotationType() == Role.class`, it may miss data.

The practical solution is to query `getDeclaredAnnotationsByType(Role.class)` or `getAnnotationsByType(Role.class)` directly when you know the type you are looking for.

### 8.6. TYPE_USE and Other APIs

Repeatable annotations can also be applied at type-use positions if `@Target` includes `ElementType.TYPE_USE`. However, to read annotations at a type-use position, you typically need the appropriate `AnnotatedType` API (for example, `Field.getAnnotatedType()` or `Method.getAnnotatedReturnType()`), rather than `Field.getAnnotation(...)` if the metadata actually resides at the type-use position. The issue of **"placing the annotation in the right location"** and the issue of **"unwrapping the container"** are two independent steps.

## 9. Common Pitfalls and Quick-Check Questions

| Symptom | Why? | How to Handle |
| --- | --- | --- |
| Source has two `@Role` annotations, yet `getAnnotation(Role.class) == null` | Both annotations are indirectly present inside a container | Use `getAnnotationsByType(Role.class)` |
| `getAnnotation(Roles.class)` sees the container, while `getAnnotation(Role.class)` does not | The two APIs query **two different types**; the singular API does not unwrap the container | Use `Roles.value()` or `ByType(Role.class)` |
| One direct `@Role`, yet `getAnnotation(Roles.class) == null` | A single case is not necessarily held inside a container | Use `getAnnotationsByType(Role.class)` to cover all cases |
| `getAnnotationsByType(Role.class)` returns `[]` even though the container exists | The container has an empty `value()` array | Check `Roles.value().length` and the semantics of the data |
| `ByType` does not unwrap a `Group` containing `Role[]` | There is no proper `@Repeatable(Group.class)` relationship | Design a valid annotation/container pair |
| `ByType` does not see the annotation at runtime | Retention is not `RUNTIME`, or the wrong member or type is queried | Verify the definition, placement, and reading mechanism |
| Subclass does not inherit roles as expected | Missing `@Inherited`, or metadata is already present on the subclass itself | Check the `@Inherited` rules for repeatable/container annotations |
| `getDeclaredAnnotationsByType` does not see roles on the superclass | APIs with `Declared` only read current declarations | Switch to `getAnnotationsByType` if inheritance lookup is desired |
| Code iterates over `getDeclaredAnnotations()` and casts every annotation to `Role` | The raw array may contain `Roles` | Use `getDeclaredAnnotationsByType(Role.class)` |
| Assuming the returned order is necessarily the execution order | Metadata does not execute itself | Write consumer logic and define processing rules |

For libraries with public annotation APIs, you should test with at least four configurations: **a single direct annotation**, **multiple repeated annotations**, **an explicit container**, and **no annotations**, plus **inheritance** if the type has `@Inherited`. These are the configurations that commonly expose confusion between `getAnnotation` and `getAnnotationsByType`.

## 10. Checklist for Choosing the Right API

When reading metadata at runtime:

1. Identify the exact **annotation type T** the program wants to read, and check whether T has `@Repeatable(Container.class)`.
2. Confirm that annotation T and its container have appropriate runtime retention.
3. Obtain the right reflection element: `Class`, `Field`, `Method`, `Constructor`, or `AnnotatedType`, depending on the location.
4. If you want **all T annotations**, including those inside a container: choose **`getAnnotationsByType(T.class)`**.
5. If you want only T annotations **declared on that exact element**, without searching superclasses: choose **`getDeclaredAnnotationsByType(T.class)`**.
6. If you need the metadata of the **container** itself, query `getAnnotation(Container.class)` and read its elements; do not use the container as a default substitute for all single-direct-annotation cases.
7. With classes and `@Inherited`, decide explicitly whether data from superclasses is needed. Do not confuse standard lookup behavior with accumulating business values.
8. Do not rely on the ordering of all annotation types in a raw reflection array. If the order of **the T components** matters, iterate directly over the `ByType(T.class)` array in the order returned.

**Conclusion:** Java "looks through the container annotation" when the program uses **`getAnnotationsByType(T.class)`** or **`getDeclaredAnnotationsByType(T.class)`** for a validly defined **repeatable annotation type T** with appropriate metadata visible to reflection. The singular APIs `getAnnotation(T.class)` and `getDeclaredAnnotation(T.class)` **do not automatically unwrap containers**; `getAnnotation(Container.class)` only looks up the container. Properly understanding the difference between direct, indirect, and inherited presence will help prevent missing repeated annotations.
