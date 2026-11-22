# Directly Present, Indirectly Present, Present, and Associated Annotations in Java

## 1. Why are these four terms important?

When using the **Java Reflection API** to look up annotations, the two questions “is the annotation on this element?” and “is the annotation returned by the API?” are not precise enough. Java distinguishes four types of relationships between an annotation and the element under consideration:

- **Directly present** — present directly on the element.
- **Indirectly present** — present indirectly through the **container** of a repeatable annotation.
- **Present** — present, including the direct relationship and limited inheritance rules for classes.
- **Associated** — associated, including direct, indirect, and limited inheritance rules for classes.

These four concepts are defined in the standard `java.lang.reflect.AnnotatedElement` interface; the methods `getAnnotation`, `getDeclaredAnnotation`, `getAnnotationsByType`, and `getDeclaredAnnotationsByType` do not have the exact same meaning.

The difference is clearest when combining **`@Repeatable`** with **`@Inherited`**. If you read via the wrong API, the program may miss repeated annotations, confuse an inherited annotation with one declared on the subclass, or misapply a configuration from the superclass.

This article uses the terms in their technical Java sense and does not treat “present” as a general synonym for every way an annotation is found.

## 2. Basic requirement: annotations can be read at runtime

For reflection to see an annotation on a suitable declaration or type-use, the annotation needs to be retained at **`RetentionPolicy.RUNTIME`**:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Label {
    String value();
}
```

If there is **no `@Retention`**, the default policy is **`CLASS`**. CLASS-level annotations can typically be written into the class file, but the `AnnotatedElement` API does not return them as runtime annotations. Therefore, when analyzing the result of `getAnnotation` or `getAnnotationsByType`, you must first determine the retention.

**A note on scope:** the directly present/indirectly present/present/associated relationships specify how annotations can be queried on *an element*; the inheritance relationship in these definitions applies only to **class declarations** under the `@Inherited` rule, and does not mean that every method, field, parameter, or interface inherits annotations.

## 3. Directly present — direct annotation presence

An annotation `A` of type `T` is **directly present** on an element `E` when `E` directly has annotation `A` in the runtime metadata of that element itself.

Example:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Review {
    String value();
}

@Review("approved")
class Article {}
```

`@Review("approved")` is attached directly to `Article`. With reflection:

```java
Review direct = Article.class.getDeclaredAnnotation(Review.class);
Review present = Article.class.getAnnotation(Review.class);
```

Both can find the annotation on this class because it is **declared directly**.

The word “directly” describes **the source of the annotation in metadata**, not that the annotation is processed immediately. It does not perform an article review or generate `approved` logic.

APIs commonly used for direct lookup:

- `getDeclaredAnnotation(T.class)`: returns a **directly present** annotation of type `T`, or `null` if none exists.
- `getDeclaredAnnotations()`: returns the **directly present** annotations on the element itself as an `Annotation[]` array; it does not automatically unwrap all repeatable annotations inside a container.

`Declared` here means querying on **the element under consideration**, without walking up to the superclass. This is why this lookup approach is useful for distinguishing locally declared metadata from inherited metadata.

## 4. Indirectly present — indirect annotations through a container

An annotation of type `T` is **indirectly present** when:

1. `T` is a **repeatable annotation type**, marked with `@Repeatable(Container.class)`.
2. An annotation of `T`'s **container** type is directly present on the element.
3. The container has a `value()` element containing the annotation `T` under consideration.

Example:

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

@Tag("fast")
@Tag("safe")
class Job {}
```

On `Job`, the two `@Tag` annotations on the same declaration are represented by Java through the `@Tags` container. Therefore, in normal runtime metadata:

- `Tags.class` is the **direct** annotation type of the container on `Job`.
- The two `Tag` values inside the container are **indirect** annotations on `Job`.
- `Job.class.getDeclaredAnnotation(Tag.class)` returns `null` because there is no single **directly present** `Tag`.
- `Job.class.getDeclaredAnnotation(Tags.class)` returns the container.
- `Job.class.getDeclaredAnnotationsByType(Tag.class)` returns **two `Tag` annotations** by reading through the container.

**Note:** “Indirectly” here has a very specific meaning: **via the containing annotation type of `@Repeatable`**. It **does not mean inherited** from a superclass. Inheritance belongs to the two concepts *present* and *associated*, presented later.

### One @Tag vs. two @Tag annotations

If there is only:

```java
@Tag("single")
class SoloJob {}
```

then `Tag` is normally **directly present** on `SoloJob`, with no need for the compiler to synthesize a container. Therefore `getDeclaredAnnotation(Tag.class)` retrieves `Tag`; whereas when there are two `@Tag` annotations, we need the `ByType` API to read both.

If the programmer writes an **explicit container**:

```java
@Tags({@Tag("fast"), @Tag("safe")})
class ManualJob {}
```

then the two `Tag` annotations are also **indirectly present**. The concept does not depend on whether the container is written explicitly or synthesized by the compiler.

## 5. Present — present annotations

An annotation `A` of type `T` is **present** on an element `E` when either of two conditions holds:

1. `A` is **directly present** on `E`; or
2. No annotation of type `T` is **directly present** on `E`, `E` is a **class**, the annotation type `T` is marked **`@Inherited`**, and `A` is **present** on the superclass of `E`.

The definition uses the **directly present** property when checking `T`; it **does not automatically unwrap containers**. Therefore, calling `getAnnotation(Tag.class)` to look up a repeatable annotation does not mean the API will return all indirect `Tag` annotations.

Example of inheriting a single annotation:

```java
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@interface Owner {
    String value();
}

@Owner("team-core")
class BaseService {}

class ChildService extends BaseService {}
```

For `ChildService.class`:

- `getDeclaredAnnotation(Owner.class)` is `null`: the subclass does not declare `@Owner` directly.
- `getAnnotation(Owner.class)` retrieves `Owner("team-core")`: the annotation is **present** via the `@Inherited` rule.
- `getDeclaredAnnotations()` does not include `@Owner` inherited from the superclass.

If `ChildService` declares `@Owner("team-child")` itself, the local annotation takes precedence when looking up `Owner`.

**Scope of `@Inherited`:** applies only to lookups from **class to superclass**. It does not cause annotations on an interface to be inherited this way; nor does it make a superclass method's annotation automatically appear on an overridden method. Java reflection requires applying separate rules for each element.

## 6. Associated — associated annotations

An annotation `A` of type `T` is considered **associated** with an element `E` when:

1. `A` is **directly present or indirectly present** on `E`; or
2. No annotation of type `T` is directly **or indirectly** present on `E`, `E` is a **class**, `T` has `@Inherited`, and `A` is **associated** with the superclass.

Thus, *associated* adds the ability to **look through containers** while still supporting conditional inheritance. This is the concept used by **`getAnnotationsByType(T.class)`**.

Conceptual example:

```java
@Tag("read")
@Tag("write")
class RolesForAction {}
```

`getDeclaredAnnotationsByType(Tag.class)` and `getAnnotationsByType(Tag.class)` can both return two values if they have RUNTIME retention; the first checks only the element itself, whereas the second can also follow the `@Inherited` rule if the annotation is inheritable and the query source is a class.

If the subclass declares `Tag` annotations directly or indirectly itself, then **the subclass's annotations of the same type take precedence** when evaluating *associated*; all `Tag` annotations from the superclass are not automatically accumulated into the result. Only if the subclass has no `Tag` directly or indirectly can `getAnnotationsByType` inherit the superclass's result under the `@Inherited` rule.

### Present and associated are not interchangeable

For a repeatable annotation with a container, `getAnnotation(T.class)` checks **present**, whereas `getAnnotationsByType(T.class)` checks **associated**. In particular, on a subclass that inherits annotations, having a local **container** does not mean the subclass has a direct annotation `T`.

For example, if both `@Tag` and its container `@Tags` have `@Inherited`, the superclass has one `@Tag("parent")`, and the subclass has two annotations `@Tag("local-a")` and `@Tag("local-b")`, then:

- `Child.class.getAnnotationsByType(Tag.class)` finds **Child's own two Tags** (indirectly through the container); it does not add `parent`.
- `Child.class.getAnnotation(Tag.class)` can still return the inherited `Tag("parent")`, because on Child **there is no directly present Tag**, only a direct container. This is a consequence of the exact definition of *present*, which differs from *associated*.

This is a case where you should **intentionally choose the API based on your needs** and not interpret the result of one method in place of the other.

## 7. Mapping table of the four terms to Java Reflection

| API on `AnnotatedElement` | Relationship type queried | Unwraps `@Repeatable` container? | Checks superclass via `@Inherited`? |
| --- | --- | --- | --- |
| `getDeclaredAnnotation(T.class)` | **Directly present** | No | No |
| `getDeclaredAnnotations()` | **Directly present** (all types) | No | No |
| `getAnnotation(T.class)` | **Present** | No | Yes, classes only and when conditions match |
| `getAnnotations()` | **Present** (all types) | Does not unwrap container into `T[]` | Yes, classes only and when conditions match |
| `getDeclaredAnnotationsByType(T.class)` | **Directly + indirectly present** | Yes | No |
| `getAnnotationsByType(T.class)` | **Associated** | Yes | Yes, classes only and when conditions match |

**Quick selection guide:**

- Need exactly **one directly declared annotation**? Use `getDeclaredAnnotation`.
- Need to retrieve **multiple annotations of the same type** on the element itself? Use `getDeclaredAnnotationsByType`.
- Need an annotation that supports `@Inherited` via class relationships? Use `getAnnotation`, keeping in mind that this API does not unwrap indirect repeatable elements.
- Need **multiple annotations of the same type** and want inheritance applied when eligible? Use `getAnnotationsByType`.

`getAnnotations()` and `getDeclaredAnnotations()` return an array of the direct/present annotation types respectively, including the **container** if the container itself is a direct annotation. You should not use those two APIs and assume that all repeatable annotations inside the container have already become separate elements of the array.

## 8. Complete Java 17+ example: the four relationships in one program

Create a file named **AnnotationLookupKindsDemo.java** with the following full content. The example uses only Java SE and includes a **repeatable annotation**, a **container**, **`@Inherited`**, and reflection calls for comparison.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.stream.Collectors;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Labels.class)
@interface Label {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Labels {
    Label[] value();
}

@Label("base")
class Base {}

class InheritedChild extends Base {}

@Label("first")
@Label("second")
class Repeated {}

@Labels({@Label("manual-a"), @Label("manual-b")})
class ExplicitContainer {}

public class AnnotationLookupKindsDemo {
    private static String values(Label[] annotations) {
        return Arrays.stream(annotations)
                .map(Label::value)
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        System.out.println("base direct="
                + Base.class.getDeclaredAnnotation(Label.class).value());

        System.out.println("child direct="
                + (InheritedChild.class.getDeclaredAnnotation(Label.class)
                    != null));
        System.out.println("child present="
                + InheritedChild.class.getAnnotation(Label.class).value());
        System.out.println("child associated="
                + values(InheritedChild.class.getAnnotationsByType(Label.class)));

        System.out.println("repeated direct="
                + (Repeated.class.getDeclaredAnnotation(Label.class) != null));
        System.out.println("repeated container="
                + (Repeated.class.getDeclaredAnnotation(Labels.class) != null));
        System.out.println("repeated declaredByType="
                + values(Repeated.class.getDeclaredAnnotationsByType(Label.class)));

        System.out.println("explicit associated="
                + values(ExplicitContainer.class.getAnnotationsByType(Label.class)));
    }
}
```

In the directory containing the file, using JDK 17 or newer:

```bash
javac AnnotationLookupKindsDemo.java
java AnnotationLookupKindsDemo
```

Stdout:

```text
base direct=base
child direct=false
child present=base
child associated=base
repeated direct=false
repeated container=true
repeated declaredByType=first,second
explicit associated=manual-a,manual-b
```

**Reading each result:**

1. `Base` has a direct `@Label("base")`, so `getDeclaredAnnotation` returns this annotation.
2. `InheritedChild` does not declare `@Label`, so `getDeclaredAnnotation` returns `null`; the boolean condition prints `false`.
3. `Label` has `@Inherited`, allowing `getAnnotation` on the **subclass** to look up to `Base`. This is an annotation that is **present** through inheritance.
4. `getAnnotationsByType` on `InheritedChild` can also trace back to the superclass because there is no direct or indirect `Label` on the subclass, and `Label` is inheritable.
5. `Repeated` has two `@Label` annotations of the same type. The metadata is represented by a container, so there is no single directly present `Label`; however, `Labels` is directly present. Therefore, the two booleans are `false` and `true` respectively.
6. `getDeclaredAnnotationsByType(Label.class)` unwraps the container into `first,second`, matching the order of annotation values in the container.
7. `ExplicitContainer` declares the container explicitly. `getAnnotationsByType` still reads both `Label` annotations inside, showing that *indirectly present* does not apply only when the compiler synthesizes the container automatically.

**Conditions for the example to work:** both `Label` and `Labels` must have `RUNTIME` retention so the program can read the data at runtime, and for repeatable annotation inheritance, the container must have a compatible `@Inherited`. `@Target(TYPE)` allows attaching the annotation to a class.

## 9. Roles of @Repeatable, @Inherited, and @Retention

### 9.1. @Repeatable controls repeatability and the container

`@Repeatable(Labels.class)` allows an annotation type to appear multiple times on the same declaration. The `Labels` container has a `Label[] value()` element. It is the container that enables the **indirectly present** concept.

`@Repeatable` does not make each `@Label` a separate execution; it only defines how multiple annotations of the same type are represented.

### 9.2. @Inherited controls inheritance rules on classes

`@Inherited` relates only to **looking up class annotations through superclasses**. It does not automatically apply to:

- Annotations declared on **methods**, including overridden methods in a subclass.
- Annotations on **fields** or **formal parameters**.
- Annotations on an **interface** simply because a class `implements` that interface.

If a repeatable annotation type is marked `@Inherited`, the container must satisfy the `@Inherited` compatibility constraint for the repeatable declaration to be valid.

### 9.3. @Retention determines whether an annotation is available at runtime

Omitting `@Retention` means the default is `CLASS`. Such annotations can still be useful at compile time or for class-file reading tools, but they do not appear in `AnnotatedElement` query results as in the reflection examples.

When designing a repeatable annotation to be read via reflection, `@Retention(RUNTIME)` is typically declared on **both the repeatable annotation and its container**.

## 10. Commonly misunderstood scenarios

**Scenario 1 — A direct annotation does not appear through reflection.** Check `@Retention`: if it is `SOURCE` or `CLASS`, do not expect runtime APIs to return it.

**Scenario 2 — There are two @Tag annotations in source, but getDeclaredAnnotation(Tag.class) is null.** With repeatable annotations, the compiler may store them indirectly through a container. Use `getDeclaredAnnotationsByType(Tag.class)`.

**Scenario 3 — The container is present, but the child annotations are missing from getDeclaredAnnotations().** `getDeclaredAnnotations()` returns the container as a direct annotation; to unwrap the elements, use a `ByType` API.

**Scenario 4 — getAnnotation on a subclass returns the superclass's annotation.** If the annotation type has `@Inherited` and the subclass has no directly present annotation of the same type, this is the result of the *present* rule. Query `getDeclaredAnnotation` if you only want metadata declared on the subclass.

**Scenario 5 — Expecting getAnnotationsByType to always merge all annotations across the inheritance hierarchy.** The *associated* rule prioritizes direct or indirect annotations on the class under consideration; it checks the superclass only when the current class has no annotation of the same type in either of those two forms.

**Scenario 6 — Using @Inherited on a method annotation to receive data from an overridden method.** `@Inherited` only works under class rules and does not automatically apply to methods.

**Scenario 7 — Confusing indirectly present with inherited.** “Indirectly” relates to the `@Repeatable` **container**; “inherited” relates to `@Inherited` and the class/superclass relationship.

**Scenario 8 — Assuming getAnnotationsByType only retrieves directly declared annotations.** `getAnnotationsByType` checks *associated*, including both repeatable containers and inheritance when eligible. To exclude inheritance, use `getDeclaredAnnotationsByType`.

**Scenario 9 — Passing an annotation type from the wrong package.** Two annotations with the same simple name in two different packages are two different types; `getAnnotation` takes the `Class<T>` object of the exact annotation type.

**Scenario 10 — Expecting annotations to apply runtime configuration automatically.** The APIs here only **retrieve metadata**; the system still needs to implement its own logic to use that metadata for validation, routing, authorization, logging, or other business tasks.

## 11. API selection workflow when building a library

Suppose a custom framework needs to read `@Rule` from a class:

1. Open the `@Rule` definition: check whether `@Retention(RUNTIME)` is present.
2. Check `@Repeatable`: if `@Rule` can repeat, container support is needed; prefer `getAnnotationsByType(Rule.class)` or `getDeclaredAnnotationsByType(Rule.class)`.
3. Decide whether inheritance from a superclass is desired: use `Declared` when reading only the current element; use the non-`Declared` variant to follow the appropriate Java inheritance rules.
4. Check `@Inherited` (which only has meaning as described for classes) and a compatible container.
5. If the element under consideration is not a class, do not assume that an annotation will automatically be inherited from a similarly named element elsewhere.
6. Distinguish between **not found**, **single value**, and **multiple values**; the `ByType` APIs return an empty array if no matching annotation exists.

Choosing the right relationship to query makes results more stable if the annotation type is later extended to be repeatable or configured for inheritance.

## 12. Self-check exercises

1. Add `@Label("third")` to `Repeated`; predict `getDeclaredAnnotation(Label.class)`, the container result, and `getDeclaredAnnotationsByType(Label.class)`.
2. Place a `@Label("local")` directly on `InheritedChild`. Observe `getDeclaredAnnotation`, `getAnnotation`, and `getAnnotationsByType` to explain the precedence mechanism for local annotations.
3. Place two `@Label` annotations on `InheritedChild` instead of one; predict the difference between `getAnnotation(Label.class)` and `getAnnotationsByType(Label.class)` based on the *present* and *associated* concepts.
4. Remove `@Inherited` from `Label` **and the `Labels` container**, then recompile. Predict the lookup results on the `InheritedChild` class; explain why the annotation is no longer inherited.
5. Change the `RUNTIME` retention of both `Label` and `Labels` to `CLASS`. Observe the results when using reflection, then use `javap -v` to inspect the class file metadata.
6. Replace the `getDeclaredAnnotationsByType(Label.class)` call on `Repeated` with `getDeclaredAnnotations()`. Identify the container in the resulting array and explain why it is not split into two `Label` annotations.
7. Create a similar method with `@Label` after adjusting `@Target(METHOD)` for both annotations; compare whether `@Inherited` helps an overridden method automatically receive the annotation.

**Key takeaway:** *Directly present* refers to an annotation stored directly; *indirectly present* comes from a repeatable annotation's container; *present* adds limited class inheritance for direct annotations; and *associated* includes both repeatable annotations through a container and inheritance when permitted. Java Reflection maps these concepts to dedicated APIs. For repeatable annotations, use **`getAnnotationsByType`** when you need all associated values and **`getDeclaredAnnotationsByType`** when you only need the values on the current element.
