# Repeatable Annotations and Container Annotations in Java Reflection

## 1. Why can an annotation appear multiple times?

Normally, an annotation is attached once to a Java element. However, there are situations requiring **multiple configurations of the same kind** on a class, method, field, or another allowed location: multiple routes for an endpoint, multiple access roles, multiple schedules, or multiple test conditions.

Since Java 8, Java supports **repeatable annotations** through the `@Repeatable` meta-annotation. Example:

```java
@Tag("stable")
@Tag("audited")
class OrderService { }
```

To use this syntax, `Tag` must be declared as repeatable and linked to a **container annotation** whose `value()` element returns a `Tag[]` array. The compiler handles multiple `@Tag`s at the same location using the container mechanism. When reading metadata via Reflection, developers need to understand the difference between **annotations declared in source**, **the container stored in the class file**, and **the APIs that read single vs. multiple annotations**.

Key objectives of this lesson:

1. Properly declare `@Repeatable(Container.class)` and the corresponding container type.
2. Understand how the compiler groups multiple annotations of the same type into a container.
3. Use `getAnnotationsByType` and `getDeclaredAnnotationsByType` to query **all** repeated annotations.
4. Distinguish `getAnnotation`, `getAnnotations`, `getDeclaredAnnotation`, container annotations, and repeatable elements.
5. Understand `@Retention`, `@Target`, `@Inherited`, element ordering, and the non-repeated case.
6. Avoid common mistakes in frameworks using runtime Reflection.

## 2. Three components that make a repeatable annotation

### 2.1. Repeatable annotation: `@Tag`

The primary annotation describes one unit of configuration. To make it readable at runtime, use `@Retention(RetentionPolicy.RUNTIME)`; to allow applying it to classes and methods, use the corresponding `@Target`.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@Repeatable(Tags.class)
@interface Tag {
    String value();
}
```

The decisive part is `@Repeatable(Tags.class)`: it declares **`Tags` as the type containing `Tag` elements**. `@Repeatable` is a meta-annotation applied to the **annotation type declaration**, not an annotation used directly on `OrderService`.

### 2.2. Container annotation: `@Tags`

The container holds an array of the primary annotation:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Tags {
    Tag[] value();
}
```

`value()` must return **`Tag[]` of the exact type**. You cannot replace it with `String[]`, `List<Tag>`, or `Object[]`. This element is the bridge the compiler and Reflection APIs use to pack and unpack `@Tag` instances.

A container can have other elements, but any additional elements must have a **default value** conforming to Java's container declaration rules. The simplest, least surprising design is having only `Tag[] value();`.

Note that `@Retention` and `@Target` apply to **both declarations**. The container must satisfy the compatible meta-annotation constraints required by Java. To read repeated annotations at runtime, keep **both the repeatable type and the container type at `RUNTIME`**. If the repeatable type is `@Inherited`, the container must also be declared `@Inherited`. If the repeatable type uses `@Documented`, the container also needs `@Documented`.

### 2.3. Usage syntax

Once declared properly, the program can attach multiple `@Tag`s at the same location:

```java
@Tag("stable")
@Tag("audited")
class OrderService {
    @Tag("read")
    @Tag("cache")
    public void load() { }
}
```

The two `@Tag` attachments are **two separate annotation values**, in declared order. The source code stays readable: there is no need to manually write the container every time there are multiple instances.

Writing the container explicitly is also valid:

```java
@Tags({
    @Tag("stable"),
    @Tag("audited")
})
class ExplicitOrderService { }
```

When using `getAnnotationsByType(Tag.class)`, these two forms usually yield the same result. However, code using `getAnnotation(Tag.class)` or iterating `getDeclaredAnnotations()` can receive results very different from intuition if the container is not understood.

## 3. What does the compiler do when an annotation is repeated?

When the compiler encounters:

```java
@Tag("stable")
@Tag("audited")
class OrderService { }
```

It processes the two `@Tag` annotations using the container mechanism corresponding to the conceptual structure:

```java
@Tags({
    @Tag("stable"),
    @Tag("audited")
})
class OrderService { }
```

This is an **equivalent model for how metadata is stored**, not a step that edits the source file or requires the programmer to invoke a container constructor. In the class file, multiple `@Tag`s at the same location are represented via `@Tags` according to Java rules.

Hence there are two levels of view:

| Perspective | What is seen |
|---|---|
| Java source | Two consecutive `@Tag`s |
| Stored metadata | One `@Tags` container whose `Tag[] value()` element holds two values |
| `getDeclaredAnnotation(Tags.class)` | Reads the container if it is directly present |
| `getDeclaredAnnotationsByType(Tag.class)` | API unpacks and returns both `@Tag`s |
| `getDeclaredAnnotation(Tag.class)` | Can return `null` because `@Tag` is not directly present, only indirectly present via the container |

This perspective explains why legacy code using `getAnnotation(Tag.class)` can start **failing to find the annotation** once that annotation is made repeatable and used multiple times on the same element.

You should not rely on parsing annotation names directly from bytecode when `AnnotatedElement` already provides standard APIs to obtain the underlying values.

## 4. Rules that container declarations must follow

Java does not accept an arbitrary pair of annotations as repeatable/container. Some key rules:

| Constraint | Matching example | Why it is required |
|---|---|---|
| Container is an annotation type | `@interface Tags` | The compiler must recognize the containing type |
| Has a `value()` element returning the exact repeatable array type | `Tag[] value();` | Holds the `@Tag` instances |
| Any other container elements (if present) all have default values | `String group() default "";` | Allows the compiler to construct a valid container when encountering multiple `@Tag`s |
| Container's retention is no shorter than the repeatable type's retention | `RUNTIME` / `RUNTIME` | Prevents losing information that must be retained |
| Container's target is compatible with where the repeatable type can appear | Same `TYPE`, `METHOD` in the example | The container must be valid at the location where the compiler packs it |
| If the repeatable type has `@Inherited`, the container also has `@Inherited` | Both are marked | Preserves supported inheritance behavior |
| If the repeatable type has `@Documented`, the container also has `@Documented` | Both are marked | Ensures documentation visibility contract |

For this foundational lesson, **putting the same retention and target on both annotations in the pair** is the most readable approach and avoids mismatches. Actual language rules permit certain non-identical target relationships provided they satisfy the JLS; do not assume any arbitrary set of targets is valid.

### Invalid example: wrong array type

```java
// Invalid: container does not have Tag[] for value().
// @Repeatable(BadTags.class)
// @interface Tag { String value(); }
// @interface BadTags { String[] value(); }
```

### Invalid example: insufficient runtime retention

```java
// Unsuitable for reading values via runtime Reflection:
// @Retention(RetentionPolicy.RUNTIME)
// @Repeatable(BadTags.class)
// @interface Tag { String value(); }
//
// @Retention(RetentionPolicy.CLASS)
// @interface BadTags { Tag[] value(); }
```

The two blocks above are only **commented counterexamples**, not meant to be placed into a runnable program file. Depending on the violation, the compiler will report an invalid repeatable/container declaration error.

## 5. Retention of repeatable annotations and containers

When using runtime Reflection, both the repeatable annotation and the container must have appropriate retention (`RUNTIME` in these examples). `@Repeatable` only enables **repetition**; it does not change retention. If `@Retention` is omitted, the default is `CLASS`, and runtime APIs will not see those annotations. See the retention lesson to distinguish compile-time and runtime annotation processing.

## 6. Reflection APIs: reading one annotation or reading multiple?

`Class`, `Method`, `Field`, `Constructor`, `Parameter`, and several other Reflection types implement the `java.lang.reflect.AnnotatedElement` interface. Representative APIs:

| API | Annotation kind considered | Unpacks container? | Inheritance for class |
|---|---|---|---|
| `getAnnotation(A.class)` | *Present* annotation of type `A` | Does **not** auto-unpack `A` from container | Yes under `@Inherited` rules and *present* concept |
| `getDeclaredAnnotation(A.class)` | **Directly present** annotation of type `A` | **No** | No |
| `getAnnotationsByType(A.class)` | **Associated** annotations of type `A` | **Yes** if `A` is repeatable | Possible under `@Inherited` |
| `getDeclaredAnnotationsByType(A.class)` | Direct annotations or indirect via container | **Yes** | No |
| `getAnnotations()` | *Present* annotations as an array | Does **not** auto-flatten repeated elements | Possible |
| `getDeclaredAnnotations()` | Direct annotations as an array | Does **not** auto-flatten repeated elements | No |
| `isAnnotationPresent(A.class)` | Equivalent to `getAnnotation(A.class) != null` | **No** | Follows `getAnnotation` |

The table uses terminology from the Java 17 `AnnotatedElement` Javadoc.

**Practical rule:** If an annotation type is declared `@Repeatable` and the goal is to collect **all values**, call:

```java
Tag[] tags = element.getAnnotationsByType(Tag.class);
```

or when you only want annotations declared by the element itself:

```java
Tag[] localTags = element.getDeclaredAnnotationsByType(Tag.class);
```

Here `element` has an appropriate `AnnotatedElement` type. Both methods return an **array**; if there are no matching annotations, the array is **empty**, not `null`. The main difference is that the method without `Declared` can consider inheritance in the class + `@Inherited` case.

### Why can `getAnnotation(Tag.class)` return `null`?

With **two** consecutive `@Tag`s, the compiler normally stores a `@Tags` container. Then `Tag` is only **indirectly present**, not **directly present** on the element. `getAnnotation(Tag.class)` does not “see through” the container, so on that very element it can return `null`, even while `getAnnotationsByType(Tag.class)` still returns two elements.

Conversely, with a single standalone `@Tag("one")`, `Tag` is normally stored directly and `getAnnotation(Tag.class)` can return that annotation. This is an important difference between attaching the same annotation type **once** versus **multiple times**.

## 7. Why does `getAnnotation` differ from `getAnnotationsByType`?

In `AnnotatedElement` terminology, a single `@Tag` can be **directly present**, while multiple `@Tag`s wrapped in a `@Tags` container make them **indirectly present**. `getAnnotation(Tag.class)` checks *present* and does not auto-flatten containers; `getAnnotationsByType(Tag.class)` checks *associated*, covering direct annotations, indirect annotations, and valid inherited fallback.

Try three states: no tag, only one `@Tag`, and two `@Tag`s. With two tags, `getAnnotation(Tag.class)` can be `null` even though `getAnnotationsByType(Tag.class).length == 2`. The difference between the two `ByType` variants and `@Inherited` handling is illustrated separately in the next lesson.

## 8. Querying the container annotation directly

The container is still an independent annotation type. It can be accessed via Reflection:

```java
Tags container = OrderService.class.getDeclaredAnnotation(Tags.class);

if (container != null) {
    for (Tag tag : container.value()) {
        System.out.println(tag.value());
    }
}
```

The snippet above assumes `OrderService` has two `@Tag`s and the corresponding annotation type declarations; it is not a standalone program with `main`.

This is manual unpacking. In most cases, `getDeclaredAnnotationsByType(Tag.class)` or `getAnnotationsByType(Tag.class)` is shorter and more faithful to the contract. Advantages of the by-type APIs:

- Works even when there is only **one direct `@Tag`**, with no container present.
- Works when there are **multiple `@Tag`s indirectly via a container**.
- Works when the user writes **`@Tags({ ... })` explicitly**.
- Follows the repeatable annotation ordering specified by `AnnotatedElement`.
- With `getAnnotationsByType`, applies inheritance properly for classes annotated with `@Inherited`.

**Do not assume the container is always present.** If an element has only one base annotation, calling `getDeclaredAnnotation(Tags.class)` normally returns `null`. Treat the container as a storage mechanism, not the sole API to query in all cases.

## 9. The order of repeatable annotations matters

With:

```java
@Tag("first")
@Tag("second")
@Tag("third")
class Example { }
```

`getDeclaredAnnotationsByType(Tag.class)` returns the annotations in `first`, `second`, `third` order respectively. When read from a container, the order follows the order of elements in `value()`. Java's `AnnotatedElement` specifies the order as if the indirect elements were placed at the position of the corresponding container.

This matters if annotations express an **ordered pipeline**, filter list, ordered evaluation rules, or repeated configuration entries. However, annotation order does not automatically become a business ordering rule: the framework should clearly state **whether it uses source order**.

If order affects logic, test it. Do not arbitrarily sort `@Tag`s alphabetically unless the framework specification requires it, as doing so can alter the meaning of the declared configuration.

## 10. `@Inherited` combined with repeatable annotations

For a repeatable `@Tag` to be inherited when looking up on a **class**, mark `@Inherited` on **both `Tag` and container `Tags`**, along with valid retention/target. With `@Tag("a") @Tag("b")` on `Parent` and `Child extends Parent` having no own tags, `Child.class.getAnnotationsByType(Tag.class)` returns `[a,b]`, while `getDeclaredAnnotationsByType(Tag.class)` returns an empty array.

```java
@Inherited @Repeatable(Tags.class) @Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tag { String value(); }

@Inherited @Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tags { Tag[] value(); }
```

If `Child` declares `@Tag("local")`, `getAnnotationsByType(Tag.class)` prefers `[local]`: the inheritance mechanism is a fallback, not an automatic sum of all values from superclasses. If you want multi-level merging or interface/method-override scanning, the framework must implement it itself. The runnable example in section 13 demonstrates these branches.

## 11. Which elements can hold repeatable annotations?

Valid locations are still determined by `@Target` on both the annotation and the container: `TYPE` (class), `METHOD` (method), `FIELD`, `CONSTRUCTOR`, `PARAMETER`, or `TYPE_USE`. To read repeated annotations on a method, obtain the exact `Method` object and call `method.getDeclaredAnnotationsByType(Tag.class)`; for type-use, obtain the exact `AnnotatedType` before calling the API.

```java
Method method = SomeClass.class.getDeclaredMethod("load");
Tag[] tags = method.getDeclaredAnnotationsByType(Tag.class);
```

This is a fragment requiring a valid class/method and `Method` import. `@Inherited` does not make annotations on overriding methods propagate automatically. `AnnotatedElement` and `TYPE_USE` sites are explained thoroughly in the first lesson of the chapter.

## 12. How to design an API for handling repeatable annotations

In an annotation scanner or framework, proceed in order:

1. **Clarify the element:** Class, method, field, constructor, parameter, or type use? Choose the corresponding `AnnotatedElement`.
2. **Verify retention:** Annotations needed at runtime must have appropriate `RUNTIME` retention.
3. **Use by-type APIs:** `getDeclaredAnnotationsByType` to read annotations of the declaration itself; `getAnnotationsByType` when intentionally considering class inheritance.
4. **Do not depend on the container being null/non-null:** A single direct annotation and multiple indirect annotations have different storage representations.
5. **Preserve order:** If configuration uses order, process according to the array returned by the API.
6. **Define duplicate rules:** Are two tags with the same value allowed? Java permits repeatable annotations with duplicate contents; the framework must specify whether to merge or report an error.
7. **Do not confuse @Inherited with merging:** If you want both subclass and superclass annotations, traverse the hierarchy yourself and state the policy.
8. **Distinguish base annotations from containers:** When supporting metadata introspection, you may need to inspect the container separately, but business annotation processing should prefer the by-type APIs.
9. **Be careful with meta-annotations:** If you want a scanner to read annotations on an annotation type itself (e.g., handling stereotype/composed annotations), custom logic is required; `@Repeatable` itself does not provide “recursive meta-annotation scanning”.

A minimal utility usable with many element types:

```java
import java.lang.annotation.Annotation;
import java.lang.reflect.AnnotatedElement;

public final class AnnotationReaders {
    private AnnotationReaders() { }

    public static <A extends Annotation> A[] locallyDeclared(
            AnnotatedElement element, Class<A> annotationType) {
        return element.getDeclaredAnnotationsByType(annotationType);
    }
}
```

This is a standalone compilable utility class, without its own `main`. It intentionally uses `Declared` to avoid inferring annotations from superclasses. When class inheritance with `@Inherited` is desired, `getAnnotationsByType` can be chosen, though a different helper name should be used so the contract is clear.

## 13. Runnable Java 17+ program: containers, methods, and inheritance

This standalone runnable example proves:

- The compiler packs two `@Tag`s into `@Tags`.
- `getDeclaredAnnotation(Tag.class)` can return `null` even when two tags exist.
- `getDeclaredAnnotationsByType`/`getAnnotationsByType` unpack both values.
- `@Inherited` allows a subclass to read tags from a superclass if the subclass has no own tags.
- A subclass with its own tag will **not** automatically accumulate tags from the superclass.
- Explicitly declared containers are also handled by the by-type APIs.
- Querying annotations on methods works similarly without assuming method inheritance.

### 13.1. Source code

Save the entire contents below to **`RepeatableDemo.java`**:

```java
import java.lang.annotation.*;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.stream.Collectors;

public class RepeatableDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @Inherited
    @Repeatable(Tags.class)
    @interface Tag { String value(); }

    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @Inherited
    @interface Tags { Tag[] value(); }

    @Tag("stable") @Tag("audited")
    static class Base {
        @Tag("read") @Tag("cache")
        public void run() { }
    }

    static class Child extends Base { }

    @Tag("local")
    static class Local extends Base { }

    @Tags({@Tag("manual-a"), @Tag("manual-b")})
    static class Explicit { }

    static String values(Tag[] tags) {
        return Arrays.stream(tags).map(Tag::value)
                .collect(Collectors.joining(", ", "[", "]"));
    }

    public static void main(String[] args) throws Exception {
        System.out.println("base byType: "
                + values(Base.class.getAnnotationsByType(Tag.class)));
        System.out.println("base direct single: "
                + (Base.class.getDeclaredAnnotation(Tag.class) != null));
        System.out.println("base container: "
                + (Base.class.getDeclaredAnnotation(Tags.class) != null));
        System.out.println("base declared count: "
                + Base.class.getDeclaredAnnotations().length);
        System.out.println("child byType: "
                + values(Child.class.getAnnotationsByType(Tag.class)));
        System.out.println("child declared byType: "
                + Child.class.getDeclaredAnnotationsByType(Tag.class).length);
        System.out.println("local byType: "
                + values(Local.class.getAnnotationsByType(Tag.class)));
        System.out.println("explicit byType: "
                + values(Explicit.class.getAnnotationsByType(Tag.class)));

        Method method = Base.class.getDeclaredMethod("run");
        System.out.println("method byType: "
                + values(method.getDeclaredAnnotationsByType(Tag.class)));
        System.out.println("method container: "
                + (method.getDeclaredAnnotation(Tags.class) != null));
        System.out.println("method direct single: "
                + (method.getDeclaredAnnotation(Tag.class) != null));
    }
}
```

### 13.2. Compile and run

Use Java Development Kit 17 or a newer compatible version:

```bash
javac --release 17 RepeatableDemo.java
java RepeatableDemo
```

The program was compiled with `javac --release 17` and executed directly. Result:

```text
base byType: [stable, audited]
base direct single: false
base container: true
base declared count: 1
child byType: [stable, audited]
child declared byType: 0
local byType: [local]
explicit byType: [manual-a, manual-b]
method byType: [read, cache]
method container: true
method direct single: false
```

### 13.3. Interpreting the output

**`base byType`:** `Base` has two `@Tag`s, so `getAnnotationsByType(Tag.class)` returns both values in declaration order.

**`base direct single: false`:** Even though `Base` has two tag configurations, `getDeclaredAnnotation(Tag.class)` does not find a direct `@Tag` because the values sit indirectly inside the container.

**`base container: true` and `base declared count: 1`:** The compiler represents two `@Tag`s via one direct `@Tags` container. Because `Base` has no other direct annotations besides that container, `getDeclaredAnnotations().length` is `1`.

**`child byType` and `child declared byType`:** `Child` does not declare `@Tag`; thanks to `@Inherited` on the annotation pair, `getAnnotationsByType(Tag.class)` retrieves both tags from `Base`. `getDeclaredAnnotationsByType` returns an empty array because `Child` itself declares no tags.

**`local byType: [local]`:** `Local` has its own tag; `getAnnotationsByType` selects the local tag without adding `stable` or `audited` from `Base`.

**`explicit byType`:** An explicitly written container `@Tags({ ... })` is also unpacked by Reflection into two `@Tag`s.

**`method byType`:** `Base.run` has two `@Tag`s declared on the method; `getDeclaredAnnotationsByType` reads both values accurately, `getDeclaredAnnotation(Tags.class)` reads the container, and `getDeclaredAnnotation(Tag.class)` has no direct value.

### 13.4. A small change to try yourself

Change the line `@Tag("stable") @Tag("audited")` before `Base` to just `@Tag("stable")`, then recompile. When there is only **one direct annotation**, `Base.class.getDeclaredAnnotation(Tag.class) != null` will normally be `true`; `getDeclaredAnnotation(Tags.class) != null` will be `false`; `getAnnotationsByType(Tag.class)` still returns a one-element array.

That experiment demonstrates why **the by-type APIs are the stable choice** for libraries that may receive 0, 1, or many repeated configurations.

## 14. Common mistakes in projects

| Mistake | Cause | Correct approach |
|---|---|---|
| Attaching two `@Tag`s while forgetting `@Repeatable` | Compiler knows no valid container | Add `@Repeatable(Tags.class)` to type `Tag` |
| Container declares `String[] value()` | Not `Tag[]` | Declare `Tag[] value();` |
| Putting `RUNTIME` only on `Tag` | Container lacks compatible retention | Put `@Retention(RUNTIME)` on both |
| `Tag` has `@Inherited` while container lacks it | Violates meta-annotation constraint | Put `@Inherited` on the container |
| Using `getAnnotation(Tag.class)` to get multiple tags | Method does not unpack the container | Use `getAnnotationsByType(Tag.class)` |
| Iterating `getDeclaredAnnotations()` and casting directly to `Tag` | Usually the actual element is container `Tags` | Use by-type or check `annotation.annotationType()` |
| Using `getDeclaredAnnotation(Tags.class)` and assuming it always exists | A single `@Tag` can be stored directly | Query `Tag` via by-type APIs |
| Thinking `getDeclaredAnnotationsByType` inherits automatically | `Declared` reads only local annotations | Consider `getAnnotationsByType` on classes with `@Inherited` |
| Thinking a tag on a subclass auto-appends tags from parent | Associated inheritance API is a fallback | If merging is wanted, walk the hierarchy and define a policy |
| Expecting `@Inherited` to affect method annotations | Mechanism applies to class inheritance | Scan overridden methods manually if needed |
| Using `@Target(TYPE)` then attaching to a field | Annotation is not permitted at that location | Choose appropriate targets |
| Mistaking `RUNTIME` as required for compile-time processors | Annotation processing can run at compile time | Choose retention by need; use RUNTIME for runtime Reflection |
| Relying on the order of the list of all annotation types | Not a business processing order contract | Use repeatable order per API only when specified; design order separately for other metadata |
| Treating the container as a “mutable array” edited at runtime | Annotation metadata is not a place to update running configuration | Process the read values; do not try to mutate annotation proxies/class metadata |

A maintenance note: when **upgrading a non-repeatable annotation to repeatable**, existing source code using one annotation may continue working, but adding a second repetition switches the Reflection representation to a container. Any legacy scanner relying solely on `getAnnotation` or `getDeclaredAnnotations` may need updating.

## 15. Self-check questions

1. Why does Java need `@Repeatable(Tags.class)` even though source code can write two `@Tag`s on a class?
2. What type must the container's `value()` element return?
3. When two `@Tag`s are repeated on a class, how can `getDeclaredAnnotation(Tag.class)` and `getDeclaredAnnotationsByType(Tag.class)` return different results?
4. Why must an annotation have `@Retention(RUNTIME)` if a framework wants to read it via Reflection while the program is running?
5. What is the difference between `getAnnotationsByType` and `getDeclaredAnnotationsByType` when `@Inherited` is present?
6. If a subclass declares a `@Tag("local")`, does Reflection automatically also return `@Tag`s from the superclass?
7. Does `@Inherited` cause an overriding method to automatically inherit annotations from the overridden method?
8. When should `@Target({TYPE, METHOD})` be used on both the repeatable type and the container?
9. If a method has two `@Tag`s yet the program only sees one `@Tags` via `getDeclaredAnnotations()`, is that a compiler bug?
10. To read repeatable configuration reliably with 0/1/n annotations, which API should be called?
11. When does an explicit `@Tags({@Tag("A"), @Tag("B")})` declaration have the same by-type reading effect as two consecutive `@Tag`s?
12. For a framework that needs to merge annotations on a subclass and multiple superclasses, why must it design merge logic itself?

**Key takeaway:** `@Repeatable(Container.class)` allows **multiple annotations of the same type on one element**; the container holds them in its `value()` array. To read all values properly with Java Reflection, prefer `getAnnotationsByType` or `getDeclaredAnnotationsByType`. Consider retention, target, and inheritance separately; do not confuse indirect annotations inside a container with directly present annotations.

Official Java 17 references: [`Repeatable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html), [`AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html), [`Inherited`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html), [`Retention`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Retention.html), [JLS `9.6.3 — Repeatable Annotation Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.3) and [JLS `9.7.5 — Multiple Annotations of the Same Interface](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.5).