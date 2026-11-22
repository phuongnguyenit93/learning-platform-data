# @Repeatable and Containing Annotation Types in Java

## 1. What Is a Repeatable Annotation?

In Java, an annotation is normally applied **once per program element**. Starting in Java 8, an annotation type can be declared as a **repeatable annotation** using the **`@Repeatable`** meta-annotation, allowing **the same annotation type to be used multiple times at the same valid location**.

For example, a method can have two pieces of metadata of the same type:

```java
@Tag("performance")
@Tag("security")
void check() {}
```

The syntax above is valid when `Tag` is defined as a repeatable annotation. The two lines carry two different values for **the same `check()` declaration**. They are not two method calls and do not cause `check()` to execute twice.

To support this syntax, Java requires declaring a **containing annotation type (also called a container)**. For example:

```java
import java.lang.annotation.Repeatable;

@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@interface Tags {
    Tag[] value();
}
```

There are two annotation types involved:

- **`Tag`**: the annotation type to be repeated, having a single `String value()` element.
- **`Tags`**: the containing annotation type, having a `Tag[] value()` element, meaning an array of `Tag`.
- **`@Repeatable(Tags.class)`**: tells Java that repeated uses of `Tag` at the same location are contained by the `Tags` type.

`@Repeatable` is a standard meta-annotation in `java.lang.annotation`; `Tag` and `Tags` in the example are two custom-defined annotations. Without a valid container declaration, repeating two `@Tag` annotations directly on the same declaration causes a compilation error.

## 2. Why Is a Containing Annotation Type Needed?

A Java class file represents annotations using structured metadata. When a developer uses multiple `@Tag` annotations on the same declaration, the compiler can **package the repeated occurrences into a single `@Tags` container annotation** in that element's metadata.

This can be visualized as:

```java
@Tag("performance")
@Tag("security")
class Service {}
```

In terms of representing the values, this corresponds to:

```java
@Tags({
    @Tag("performance"),
    @Tag("security")
})
class Service {}
```

The two snippets above illustrate **two alternative ways of writing** the annotations for a class; do not place both forms on the same class. When multiple `Tag` annotations are directly present, Java uses the container to describe those occurrences. This explains why, when using reflection, **the API that reads `Tag` directly and the API that reads by `Tag` type can return different results**.

In practice, developers usually write `@Tag` multiple times because it is easier to read. The containing type must still be defined according to the contract and can be used directly when needed.

### 2.1. A Container Is a Regular Annotation Type

A containing type is neither an array field of a Java class nor a wrapper object instantiated with `new`. It is an **annotation type** declared with `@interface`, with a special element named **`value`** whose return type is strictly a **one-dimensional array of the repeated annotation**.

```java
@interface Tags {
    Tag[] value();
}
```

`Tag[] value()` allows storing 0, 1, or more `@Tag(...)` values when using the container explicitly. However, `@Repeatable(Tags.class)` is only required when you want to use the form with **multiple `@Tag` annotations directly on the same declaration**, not to allow a regular annotation element to accept an array of values.

### 2.2. Minimal Compilable Declaration

The following snippet is sufficient to demonstrate the relationship between a repeatable annotation and its container:

```java
import java.lang.annotation.Repeatable;

@Repeatable(Labels.class)
@interface Label {
    String value();
}

@interface Labels {
    Label[] value();
}

@Label("first")
@Label("second")
class Note {}
```

The annotations here do not declare `@Retention`, so they **default to `RetentionPolicy.CLASS`**. They are syntactically valid and are recorded in the class file at supported locations; if you want to use Java reflection at runtime, you need to specify `RUNTIME` as shown in the complete example in Section 5.

## 3. Required Contract Between a Repeatable Annotation and Its Container

`@Repeatable(Container.class)` cannot point to just any annotation type. The container must satisfy several conditions checked by the compiler.

### 3.1. Must Have a value() Element of the Correct Array Type

Suppose the annotation to be repeated is named `Role`:

```java
@interface Roles {
    Role[] value();
}
```

**`value()` must return `Role[]`**. Forms such as `Role value()`, `String[] value()`, or `List<Role> value()` violate the contract. `List<Role>` is not even a valid annotation element type in Java.

The container may have additional elements, but **any elements other than `value` must have default values**. Valid example:

```java
@interface Roles {
    Role[] value();
    String source() default "manual";
}
```

When the compiler synthesizes the container from repeated `@Role` annotations, `source` can use its default value. If `source()` lacks `default`, the container is invalid as a containing type for `Role`.

### 3.2. Container Retention Must Be Compatible

When a repeatable annotation `@Role` has `@Retention(RUNTIME)`, its container must be retained long enough so that the information is not lost before runtime. The most common, clearest, and safest approach is to **set the same `RUNTIME` policy on both**:

```java
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Roles.class)
@interface Role {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@interface Roles {
    Role[] value();
}
```

The compatibility rule to remember is that **the container must not have a shorter retention than the repeatable annotation**:

| Repeatable annotation retention | Allowed container retention duration |
| --- | --- |
| `SOURCE` | `SOURCE`, `CLASS`, or `RUNTIME` |
| `CLASS` | `CLASS` or `RUNTIME` |
| `RUNTIME` | `RUNTIME` |

If the repeatable annotation is `RUNTIME` while the container is `CLASS`, the program **will not compile** with that `@Repeatable` declaration. When `@Retention` is omitted, an annotation type defaults to `CLASS`; this also applies to the container.

### 3.3. Container Target Must Permit the Repeatable Annotation's Locations

If `Role` is only used on methods, set both to use `METHOD`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Repeatable(Roles.class)
@interface Role {
    String value();
}

@Target(ElementType.METHOD)
@interface Roles {
    Role[] value();
}
```

Then:

```java
class AccountService {
    @Role("READ")
    @Role("WRITE")
    void update() {}
}
```

is a valid usage. However, if the container is not allowed to be applied at a location permitted by the repeatable annotation (for example, the container only has `TYPE` while the repeatable annotation has `METHOD`), the compiler will reject the incompatible `@Repeatable` configuration.

Setting the **same `@Target`** on both is the clear choice in typical examples. Java has detailed compatibility rules for individual target groups such as `TYPE`, `ANNOTATION_TYPE`, `TYPE_USE`, and `TYPE_PARAMETER`; when designing a multi-target container, you should check the applicability semantics rather than assuming any arbitrary set of targets is equivalent.

### 3.4. @Documented and @Inherited Must Be Compatible

When the repeatable annotation is declared with `@Documented`, the container **also needs to declare `@Documented`**. When the repeatable annotation is declared with `@Inherited`, the container **also needs to declare `@Inherited`**.

`@Documented` controls whether the annotation appears in documentation generated by supporting tools. `@Inherited` affects annotation lookup from superclasses for annotations on **class** declarations, under Java's conditions; it does not cause annotations on methods or fields to be automatically inherited under the same rules.

Neither meta-annotation **replaces `@Retention`**. If you need to read repeatable annotations via reflection, you still need to pay attention to the retention of both the repeatable annotation and its container.

## 4. Direct Usage and Container Form

There are three ways to observe the same `Tag` type:

```java
// Approach A: a single direct annotation
@Tag("one")
class SingleTag {}

// Approach B: directly repeated annotations
@Tag("one")
@Tag("two")
class RepeatedTags {}

// Approach C: using the explicit container
@Tags({@Tag("one"), @Tag("two")})
class ExplicitContainer {}
```

Suppose `Tag` and `Tags` are declared as in the Section 5 example with `RUNTIME` retention. The cases above have the following meaning when using reflection:

| Declaration form | `getDeclaredAnnotation(Tag.class)` | `getDeclaredAnnotation(Tags.class)` | `getDeclaredAnnotationsByType(Tag.class)` |
| --- | --- | --- | --- |
| One `@Tag` | Returns `Tag` | Usually returns `null` | Array with 1 `Tag` |
| Two direct `@Tag` annotations | Usually `null`: they are indirectly contained | Returns the `Tags` container | Array with 2 `Tag` elements |
| One `@Tags` containing 2 `@Tag` annotations | `null` | Returns `Tags` | Array with 2 `Tag` elements |

The terms **directly present** and **indirectly present** are important. When two `@Tag` annotations are represented using a container, direct reflection on that element does not necessarily find a standalone `Tag` object. The `getDeclaredAnnotationsByType(Tag.class)` API unpacks the container and returns the `Tag` elements.

You should not write both `@Tag(...)` and the `@Tags(...)` container in a way that makes the same type both directly and indirectly present on **the same element**; Java does not allow that combination for the same repeatable type on the same declaration.

## 5. Complete Java 17+ Example: @Repeatable, Container, and Reflection

Create the file **RepeatableAnnotationDemo.java** with the following complete contents. The program uses only the JDK and requires no external libraries.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Tags {
    Tag[] value();
}

@Tag("core")
@Tag("annotation")
class Lesson {
    @Tag("single")
    public void read() {}
}

public class RepeatableAnnotationDemo {
    public static void main(String[] args) throws NoSuchMethodException {
        Tag[] classTags = Lesson.class.getDeclaredAnnotationsByType(Tag.class);

        System.out.println("class count=" + classTags.length);
        for (Tag tag : classTags) {
            System.out.println("tag=" + tag.value());
        }

        Tag direct = Lesson.class.getDeclaredAnnotation(Tag.class);
        Tags container = Lesson.class.getDeclaredAnnotation(Tags.class);
        System.out.println("direct Tag? " + (direct != null));
        System.out.println("container? " + (container != null));
        System.out.println("container count=" + container.value().length);

        Method method = Lesson.class.getDeclaredMethod("read");
        Tag methodTag = method.getDeclaredAnnotation(Tag.class);
        System.out.println("method tag=" + methodTag.value());
    }
}
```

Compile and run it in the directory containing the file using JDK 17+:

```bash
javac RepeatableAnnotationDemo.java
java RepeatableAnnotationDemo
```

Stdout output:

```text
class count=2
tag=core
tag=annotation
direct Tag? false
container? true
container count=2
method tag=single
```

**Explanation of the output:**

1. `@Tag("core")` and `@Tag("annotation")` are both placed on the `Lesson` class thanks to `@Repeatable(Tags.class)`. Java uses the container to represent those repeated occurrences.
2. `getDeclaredAnnotationsByType(Tag.class)` reads both directly present `Tag` annotations and those indirectly present through the container. The resulting array has two elements; when synthesized by the compiler from multiple `@Tag` lines, the order reflects the order in which the repeated annotations were declared.
3. `Lesson.class.getDeclaredAnnotation(Tag.class)` returns `null` because when repeated multiple times, `Tag` is indirectly contained inside `Tags`. `getDeclaredAnnotation(Tags.class)` retrieves the container.
4. The container's `value()` returns an array of two `Tag` elements, so `container.value().length` equals 2.
5. The `read()` method carries only **a single `@Tag("single")`**; this is a directly present annotation, so `getDeclaredAnnotation(Tag.class)` retrieves the `Tag`.

If you want a consistent API for cases with 0, 1, or multiple `Tag` annotations, prefer **`getAnnotationsByType(Tag.class)`** (which includes inheritance rules when applicable) or **`getDeclaredAnnotationsByType(Tag.class)`** (which inspects only annotations declared on the current element).

### 5.1. How Does Reflection Know the Container?

A program can read the `@Repeatable` meta-annotation on the annotation type:

```java
// Additional snippet after Tag and Tags have been defined:
Repeatable info = Tag.class.getAnnotation(Repeatable.class);
Class<?> containerType = info.value(); // Tags.class
```

`info.value()` holds **the container type**, not the array of `Tag` annotations used on a specific class. To read the `Tag` values of the `Lesson` class, call `getAnnotationsByType(Tag.class)` on that class.

## 6. getAnnotation, getAnnotationsByType, and getDeclaredAnnotationsByType

With the Java Reflection API, choosing the right method is crucial:

- **`getAnnotation(Tag.class)`**: returns a `Tag` annotation that is directly present or present via inheritance according to Java semantics; **it does not unpack the container to return multiple `Tag` annotations**. The result is a single `Tag` or `null`.
- **`getAnnotationsByType(Tag.class)`**: returns a **`Tag[]` array**, considering both directly present annotations and those indirectly present via the container, along with inheritance rules when the type is marked with `@Inherited` on a class declaration.
- **`getDeclaredAnnotation(Tag.class)`**: queries for an annotation of type `Tag` directly present on the current element, without searching inherited annotations and without unpacking containers.
- **`getDeclaredAnnotationsByType(Tag.class)`**: returns `Tag[]` on **the element itself**, unpacking the container if present, without retrieving annotations from superclasses.

For example, a class with two `@Tag` annotations will typically produce:

```java
// Illustrative code in the context of the Lesson class from Section 5
Lesson.class.getAnnotation(Tag.class);                  // null
Lesson.class.getAnnotationsByType(Tag.class).length;    // 2
Lesson.class.getAnnotation(Tags.class);                 // Tags
Lesson.class.getDeclaredAnnotationsByType(Tag.class).length; // 2
```

The two methods whose names look similar except for `ByType` **are not interchangeable**. This is a common source of bugs: developers call `getAnnotation(Tag.class)` and think `@Tag` is absent because the result is `null`.

### 6.1. Is the Container Automatically Generated by Java?

The Java compiler **can synthesize a container *usage*** when it encounters multiple repeated annotations, but **it does not automatically generate the container type definition** `Tags`. The developer or library must define `@interface Tags` beforehand, then pass `Tags.class` to `@Repeatable`.

When there is only one `@Tag`, the compiler can keep it as a directly present annotation without needing to synthesize a container. Therefore, do not assume every element with a single `@Tag` also has `@Tags`. When you want to read them uniformly, use `getAnnotationsByType(Tag.class)`.

## 7. Retention, Target, and Inheritance in Repeatable Annotations

### 7.1. If @Retention Is Omitted

Suppose:

```java
import java.lang.annotation.Repeatable;

@Repeatable(Markers.class)
@interface Marker {
    String value();
}

@interface Markers {
    Marker[] value();
}
```

Both `Marker` and `Markers` default to `RetentionPolicy.CLASS`. Uses of `@Marker` may be recorded in the class file, but **Java reflection at runtime does not read them as RUNTIME annotations**. A common design mistake is putting `@Retention(RUNTIME)` on `Marker` and forgetting to raise the container's retention to match.

When runtime reflection is needed, declare `@Retention(RetentionPolicy.RUNTIME)` on **both types**, as in the complete example.

### 7.2. Targets of the Repeatable Annotation and Its Container

Repeating `@Tag` on a class or method is invalid if `Tag` is not permitted at those locations, or if the `Tags` container has an incompatible target. The simplest approach is to place the same:

```java
@Target({ElementType.TYPE, ElementType.METHOD})
```

on both. If `Tag` only specifies `METHOD`, you cannot use `@Tag` on a class just because the container permits `TYPE`.

### 7.3. @Inherited Has a Limited Effect

If you want a **subclass** to be able to inherit repeated metadata from its superclass via appropriate APIs, the repeatable annotation can use `@Inherited`, and the container must also use `@Inherited`. At the same time, `RUNTIME` retention is required if you intend to read it via reflection.

Standalone illustrative example (assuming `Tag` and `Tags` are both marked with `@Inherited` and `RUNTIME`):

```java
@Tag("parent-1")
@Tag("parent-2")
class Parent {}

class Child extends Parent {}
```

In the case above, `Child.class.getAnnotationsByType(Tag.class)` can return the two `Tag` annotations inherited from `Parent`, following the rules of `@Inherited`.

Conversely, if `Child` **declares one or more `@Tag` annotations of its own** of the same type, `Child`'s own annotations take precedence when looking up this type via `getAnnotationsByType`, rather than automatically accumulating with `Parent`'s `Tag` annotations.

**`@Inherited` does not cause method annotations on a superclass to be automatically inherited through method overriding**, nor does it automatically apply to interfaces. Those are Java's specific contracts regarding class-level annotation inheritance.

## 8. Comparing @Repeatable with an Annotation Array as a Value

These are two different models:

### A. Repeatable Annotations on the Same Element

```java
@Role("EDITOR")
@Role("REVIEWER")
class DocumentService {}
```

Both `@Role` annotations are attached **directly to the class declaration**, which is only valid when `Role` has `@Repeatable(Roles.class)` with a proper container.

### B. An Annotation Array Inside a Larger Annotation

```java
@interface Permission {
    String name();
}

@interface AccessPolicy {
    Permission[] permissions();
}

@AccessPolicy(permissions = {
    @Permission(name = "EDITOR"),
    @Permission(name = "REVIEWER")
})
class DocumentService {}
```

In Case B, the class only carries **a single `@AccessPolicy`**. The two `@Permission` annotations are **values of the `permissions()` element**, so `Permission` does not need `@Repeatable`.

**Choose the model based on the data's meaning**: if independent items need to be placed repeatedly and directly on a declaration, `@Repeatable` keeps the source code concise; if they are components of a larger configuration, an annotation-valued array element can express the parent-child relationship more clearly.

## 9. Common Errors and How to Fix Them

**Error 1 — Repeating an annotation without declaring @Repeatable.** Writing two `@Tag` annotations on the same class when `Tag` lacks `@Repeatable` causes a compilation error. Declare a valid container and attach `@Repeatable(Container.class)`.

**Error 2 — Container has the wrong value() signature.** `String[] value()`, `Tag value()`, or `List<Tag> value()` all fail to satisfy the `Tag[] value()` requirement.

**Error 3 — Container has a required element other than value().** `String category();` without a default prevents the compiler from synthesizing a valid container. Add a valid default or remove that element if it is unnecessary.

**Error 4 — Container retention is shorter than the repeatable annotation's retention.** If `Tag` is RUNTIME while `Tags` is CLASS, the compiler rejects the repeatable annotation definition. Give the container a compatible retention, usually the same RUNTIME policy.

**Error 5 — Incompatible targets.** The container must be applicable at the required targets of the repeatable annotation; declare `@Target` explicitly on both.

**Error 6 — Omitting @Documented or @Inherited on the container.** When the repeatable annotation has either of these meta-annotations, the container must satisfy the corresponding rule.

**Error 7 — Using getAnnotation(Tag.class) to find all Tag annotations.** With multiple `@Tag` annotations, the data may reside indirectly inside `@Tags`; use `getAnnotationsByType(Tag.class)` or `getDeclaredAnnotationsByType(Tag.class)`.

**Error 8 — Assuming the compiler auto-generates the @interface container.** Java synthesizes *a container usage value* when needed, but defining `@interface Tags` is the responsibility of the annotation designer.

**Error 9 — Directly combining @Tag and @Tags on the same element.** When `Tag` becomes both directly and indirectly present on the same element, Java does not allow that configuration. Choose one declaration style.

**Error 10 — Thinking @Repeatable executes a task multiple times.** It only allows storing multiple metadata values. To execute multiple rules, some component must read `Tag[]` and process each value itself.

**Error 11 — Forgetting RUNTIME retention when using reflection.** A repeatable annotation with the default CLASS retention is invisible to normal reflection, even if the repeatable/container declarations are completely valid syntactically.

**Error 12 — Thinking repeatable annotation inheritance always accumulates.** `@Inherited` only applies to class annotation rules, gives precedence when a subclass declares annotations of the same type itself, and does not apply straightforwardly to method overrides.

## 10. Practice Exercises

1. **Change the count:** In `RepeatableAnnotationDemo.java`, add `@Tag("reflection")` to `Lesson`, recompile, and predict the count, the order of the `tag=` lines, and `container count=`.
2. **Self-check reflection:** Change `getDeclaredAnnotationsByType(Tag.class)` to `getDeclaredAnnotation(Tag.class)`. Explain why the two APIs do not return the same data type and why the direct lookup result can be `null` when annotations are repeated.
3. **Try removing the container:** Delete the `@interface Tags` definition while keeping `@Repeatable(Tags.class)`. Note the compilation error caused by the container type no longer being defined.
4. **Try an invalid value():** Change `Tag[] value()` in `Tags` to `String[] value()`, then explain the contract required by the compiler.
5. **Try an invalid retention:** Keep `@Retention(RUNTIME)` on `Tag` but change `Tags` to `@Retention(CLASS)`. Identify the compilation error and fix it with an appropriate retention.
6. **Write an explicit container:** Create another class with `@Tags({@Tag("a"), @Tag("b")})`; use `getAnnotationsByType(Tag.class)` to observe the array unpacked from the container.
7. **Distinguish data types:** Write `@AccessPolicy` with a `Permission[]` element as in Section 8 and explain why `@Repeatable` is not needed on `Permission`.
8. **Design your own:** Create `@HttpHeader(name = "...", value = "...")` and an `@HttpHeaders` container to attach multiple headers to the same method. Choose the target and retention, then write reflection code to print every header. Keep in mind that annotations only store information; actually sending HTTP headers requires separate logic.

**Key takeaway:** `@Repeatable(Container.class)` allows applying **an annotation type multiple times on the same element**, while the container must be an **annotation type whose `value()` returns an array of the repeatable annotation**, with compatible retention, target, and meta-annotations. When reading multiple annotations of the same type via reflection, prefer the **`getAnnotationsByType`** or **`getDeclaredAnnotationsByType`** API.
