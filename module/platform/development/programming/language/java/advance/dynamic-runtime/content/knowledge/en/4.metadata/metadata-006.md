# 4.6 Reading Annotations at Runtime, Repeatable Annotations, and Inheritance Rules

## 1. Objectives and Scope

After this lesson, you will be able to:

- Identify which annotations are **retained until runtime** and read their values using Reflection.
- Distinguish between the APIs `getAnnotation`, `getDeclaredAnnotation`, `getAnnotationsByType`, and `getDeclaredAnnotationsByType`, including when an annotation appears multiple times.
- Declare repeatable annotations using `@Repeatable` and a **container annotation**, and then properly read all elements.
- Explain accurately when `@Inherited` takes effect and the cases where it is **not** automatically inherited via interfaces, methods, fields, or overrides.
- Design a metadata reader for a framework/plugin with clear rules for ordering, overriding, merging, and error handling.

The scope here is **reading annotations while the JVM is running** (runtime reflection). Writing compile-time annotation processors and generating/modifying bytecode are different techniques and are not prerequisites for using Reflection.

## 2. How Do Annotations Become Runtime Data?

An annotation is **metadata** attached to a declaration or a type use site. An annotation does not execute logic by itself: a framework component reads the metadata and decides what to do with it. For example, `@Route("/users")` only serves to register an HTTP route if code or a framework actively scans and processes `@Route`.

Simplified lifecycle:

1. Source code declares an annotation interface, for example `@interface Route`, and attaches the annotation to a class or method.
2. The compiler checks usage based on type rules, `@Target`, and annotation element signatures; metadata is retained or discarded according to `@Retention`.
3. When appropriate metadata remains at runtime, Reflection uses `Class`, `Method`, `Field`, `Constructor`, `Parameter`, or `AnnotatedType` objects to read it.
4. The application processes that data: building a route table, applying policies, selecting plugins, registering handlers, validating schemas, etc.

### 2.1. `@Retention` Determines Runtime Readability

| Retention policy | Present in `.class`? | Readable via Reflection at runtime? | Example purpose |
| --- | --- | --- | --- |
| `RetentionPolicy.SOURCE` | Not required to be kept in class file; discarded by compiler | No | Supporting source code analysis, annotation processors. |
| `RetentionPolicy.CLASS` | Present in class file | No, via standard Reflection APIs | Metadata for bytecode-reading tools. This is also the **default value** when `@Retention` is not declared. |
| `RetentionPolicy.RUNTIME` | Present, with runtime-visible attributes | **Yes** | Frameworks/DI/ORM/routers reading in the running JVM. |

Therefore, for `SomeType.class.getAnnotation(MyTag.class)` to find `@MyTag`, the `MyTag` type must first be declared with `@Retention(RetentionPolicy.RUNTIME)`. Simply writing `@interface MyTag` without adding a retention defaults to `CLASS`; Java Reflection will typically return `null` or an empty array when searching for it.

`@Target` restricts where an annotation can be written, such as `TYPE`, `METHOD`, `FIELD`, `PARAMETER`, `CONSTRUCTOR`, `ANNOTATION_TYPE`, `TYPE_USE`. `@Target` **does not make an annotation appear at runtime**; that is the role of `@Retention`. `@Documented` mainly affects Javadoc documentation and also does not substitute for `RUNTIME`.

### 2.2. Runnable Example: Reading Annotations on a Class and Method

Create the file **`RuntimeAnnotationDemo.java`**:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Route {
    String value();
}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface CompileTag {}

@Route("catalog")
@CompileTag
class Catalog {
    @Route("lookup")
    public void lookup() {}
}

public class RuntimeAnnotationDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {
        Route typeAnnotation =
                Catalog.class.getAnnotation(Route.class);
        Route methodAnnotation = Catalog.class
                .getDeclaredMethod("lookup")
                .getAnnotation(Route.class);

        System.out.println("class: " + typeAnnotation.value());
        System.out.println("method: " + methodAnnotation.value());
        System.out.println("CLASS visible at runtime: "
                + (Catalog.class.getAnnotation(CompileTag.class) != null));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 --release 17 RuntimeAnnotationDemo.java
java RuntimeAnnotationDemo
```

Stdout:

```text
class: catalog
method: lookup
CLASS visible at runtime: false
```

**Explanation:** `Route` has `RUNTIME` retention, so `Class` and `Method` can read it via `getAnnotation`. `CompileTag` has `CLASS` retention; it still has metadata for class file tools, but is not present through this runtime Reflection query. `value()` is an **annotation element**; it returns the string declared at the usage site. In real applications, check that the return value is not `null` before calling `value()`.

**API to select the right element:** `Catalog.class.getDeclaredMethod("lookup")` requires the exact name and parameter type list; an overloaded method needs its types specified, e.g., `getDeclaredMethod("lookup", String.class)`. Finding a method via Reflection and reading annotations on that method are two independent steps.

## 3. Six Main Ways to Read from `AnnotatedElement`

Types such as `Class`, `Method`, `Field`, `Constructor`, and `Parameter` support the `java.lang.reflect.AnnotatedElement` interface. Distinguish four states according to the API contract:

- **Directly present:** the annotation is present directly on the reflected element.
- **Indirectly present:** the annotation is **repeatable**, and a **container annotation** on the element contains it.
- **Present:** directly present, or inherited from a superclass via `@Inherited` when querying annotations on a **class** and there is no directly present annotation of the same type.
- **Associated (with an element for multi-result queries):** directly or indirectly present, or inherited via `@Inherited` when querying a class and there is no directly or indirectly present annotation of the same type.

| API | Recognizes | "Unwraps" repeatable container? | Considers `@Inherited` on class? | When to use |
| --- | --- | --- | --- | --- |
| `getAnnotation(A.class)` | **Present** | No | Yes | Finding a non-repeatable annotation or getting a direct annotation of the desired type. |
| `getDeclaredAnnotation(A.class)` | **Directly present** | No | No | Considering only annotations directly on the element. |
| `getAnnotationsByType(A.class)` | **Associated** | **Yes** | Yes, if on a class and inheritance conditions apply | Reading **all** repeatable annotations, considering superclasses. |
| `getDeclaredAnnotationsByType(A.class)` | **Directly/indirectly present** | **Yes** | No | Reading all repeatable annotations **declared only on the element**. |
| `getAnnotations()` | **Present** of each annotation type | Does not automatically expand into all repeated instances | Yes for inheritable annotations on a class | Inventorying present annotations; may see the **container** instead of individual repeated instances. |
| `getDeclaredAnnotations()` | **Directly present** | Does not automatically expand into all repeated instances | No | Inventorying directly declared annotations. |

`isAnnotationPresent(A.class)` is logically equivalent to `getAnnotation(A.class) != null`. Because it uses the **present** concept, for **a repeatable annotation type contained inside a container**, this method can return `false` even though `getAnnotationsByType(A.class)` returns multiple elements.

Common mistake: using `getAnnotations()` and expecting each `@Tag` occurrence to become a `Tag` element in the array. With repeatable annotations, the compiler may record a **container** like `@Tags`. When you know the type being read can repeat, use the `...AnnotationsByType(Tag.class)` API.

**Return value convention:** `getAnnotation` / `getDeclaredAnnotation` return `null` when not found; `getAnnotationsByType` / `getDeclaredAnnotationsByType` return a **zero-length array**, not `null`, when there are no annotations. The returned array can be modified by the caller without affecting arrays returned by subsequent queries.

## 4. Defining Repeatable Annotations with `@Repeatable`

Since Java 8, an annotation can appear multiple times on the same element, for example:

```java
@Tag("read")
@Tag("write")
class Handler {}
```

To declare this validly, you need:

1. The **repeatable annotation** `Tag` marked with `@Repeatable(Tags.class)`.
2. The **container annotation** `Tags` must have a **`value()` element returning `Tag[]`**.
3. The retention of the container must be compatible and not shorter than the retention of the repeatable annotation; for Reflection targets, declare **both as `RUNTIME`**.
4. The `@Target` of the container must be compatible with the usage scope of the repeatable annotation. If the repeatable annotation is `@Inherited`, the corresponding container must also carry `@Inherited` (a Java rule enforced by the compiler).
5. The compiler can transform multiple `@Tag` occurrences into a single container `@Tags({@Tag(...), @Tag(...)})` in metadata. Therefore, APIs that read individual `Tag` instances need to unwrap the container.

**Single annotation:** `@Tag("read")` on a class is usually a direct `Tag` annotation, and `getAnnotation(Tag.class)` can return it. **Multiple annotations:** `@Tag("read") @Tag("write")` is typically represented via `Tags`; `getAnnotation(Tag.class)` **does not unwrap the container** and may return `null`. `getAnnotationsByType(Tag.class)` handles both situations.

### 4.1. Order of Repeated Instances

For `getAnnotationsByType` and `getDeclaredAnnotationsByType`, the specification defines how order is determined when an element has directly/indirectly present repeatable annotations: repeated instances in a container are considered **in the order of the `value()` array**, and indirectly present annotations are treated as appearing at the position of the container.

This **does not mean** every array from Reflection APIs has a default order suitable for business logic. If `@Tag` instances represent an unordered set of permissions, treat them as a set; if order implies priority, establish an explicit policy and test it. Do not infer the order of **different annotation types** from the result of `getAnnotations()`.

## 5. Runnable Example: Repeatable Annotations and Inheritance

This is a combined example because the interaction between `@Repeatable` and `@Inherited` is a very error-prone area. Create the file **`RepeatableInheritanceDemo.java`**:

```java
import java.lang.annotation.*;
import java.util.Arrays;
import java.util.stream.Collectors;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tags {
    Tag[] value();
}

@Tag("base-a")
@Tag("base-b")
class Parent {}

class Child extends Parent {}

@Tag("child")
class OwnChild extends Parent {}

@Tag("interface")
interface Contract {}

class Implementation implements Contract {}

public class RepeatableInheritanceDemo {
    private static String names(Tag[] tags) {
        return Arrays.stream(tags)
                .map(Tag::value)
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        System.out.println("Parent tags: "
                + names(Parent.class.getAnnotationsByType(Tag.class)));
        System.out.println("Child associated: "
                + names(Child.class.getAnnotationsByType(Tag.class)));
        System.out.println("Child declared count: "
                + Child.class.getDeclaredAnnotationsByType(Tag.class).length);
        System.out.println("Child single Tag: "
                + (Child.class.getAnnotation(Tag.class) != null));
        System.out.println("Child container: "
                + (Child.class.getAnnotation(Tags.class) != null));
        System.out.println("OwnChild associated: "
                + names(OwnChild.class.getAnnotationsByType(Tag.class)));
        System.out.println("OwnChild inherited container: "
                + (OwnChild.class.getAnnotation(Tags.class) != null));
        System.out.println("Implementation tags count: "
                + Implementation.class.getAnnotationsByType(Tag.class).length);
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 --release 17 RepeatableInheritanceDemo.java
java RepeatableInheritanceDemo
```

Stdout:

```text
Parent tags: base-a,base-b
Child associated: base-a,base-b
Child declared count: 0
Child single Tag: false
Child container: true
OwnChild associated: child
OwnChild inherited container: true
Implementation tags count: 0
```

### 5.1. Explaining Potentially Surprising Results

**`Parent`:** Has two `@Tag` annotations; the compiler represents them via `@Tags` containing two elements. `Parent.class.getAnnotationsByType(Tag.class)` receives both in the order declared in the container.

**`Child`:** Declares no `Tag` of its own. Because both `Tag` and container `Tags` have `@Inherited`, `getAnnotationsByType(Tag.class)` inspects the superclass and receives `base-a,base-b`. `getDeclaredAnnotationsByType(Tag.class)` still returns an empty array because `Child` declares neither `Tag` nor `Tags`.

**Why is `Child.getAnnotation(Tag.class)` `false`?** This method only checks for **present** annotations of type `Tag` and does not unwrap the `Tags` container. The two `Tag` instances on `Parent` are **indirectly present**, not a direct `Tag`. Conversely, `Child.getAnnotation(Tags.class)` sees the inherited `Tags` container, so it returns non-`null`.

**`OwnChild`:** Has a direct `@Tag("child")`. Querying `getAnnotationsByType(Tag.class)` returns **only the subclass's element**, without automatically appending `base-a,base-b` from the superclass. Under **associated** semantics, once the subclass has a directly or indirectly present annotation of the same type, searching the superclass for that type stops.

**Why is `OwnChild.getAnnotation(Tags.class)` still `true`?** This is a separate query for the **container type `Tags`**. `OwnChild` does not directly declare `@Tags`, so querying this container can still inherit the container from `Parent`. That **does not make** `getAnnotationsByType(Tag.class)` automatically merge the two levels. Avoid using `getAnnotation(Tags.class)` and manually adding it to `getAnnotationsByType(Tag.class)`, as this easily duplicates or mixes data under different rules.

**`Implementation`:** `@Tag("interface")` is on the `Contract` interface. `@Inherited` **does not propagate from an implemented interface** to the `Implementation` class. There is no `Tag` directly on `Implementation` or on its superclass, so the count is 0.

### 5.2. Inheritance Rules for Repeatable Annotations

When `A` is repeatable and has `@Inherited`:

- Subclass **has no** `A` directly or via a container: `getAnnotationsByType(A.class)` can inherit elements from the nearest superclass where they are found.
- Subclass **has at least one** `A` of its own: the result of `getAnnotationsByType(A.class)` uses that class's own `A` annotations; it does not merge with `A` annotations on superclasses by default.
- `getDeclaredAnnotationsByType(A.class)` is always scoped to the element itself; it does not walk up the hierarchy.
- Querying the **container** `As.class` is a query for a different annotation type and can yield a different result than querying `A.class`.

If business logic wants to **merge policies across all superclasses** (for example, cumulative rules), you must traverse the hierarchy yourself and define how to merge, override, and handle duplicates; do not assume `@Inherited` does this automatically.

## 6. Where Does `@Inherited` Apply?

The Javadoc of `java.lang.annotation.Inherited` clearly specifies:

1. The annotation type must have the `@Inherited` meta-annotation.
2. When querying an annotation on a **class**, if the class does not have an annotation of that type according to the API's semantics, the runtime may look on the **superclass** and continue upward.
3. `@Inherited` **does not pull annotations from implemented interfaces**.
4. `@Inherited` **does not make annotations on methods, fields, constructors, or parameters automatically inherited**.
5. In the hierarchy, a declaration of the same type closer to the queried class can shadow superclass annotations according to `present` or `associated` rules.

Statements like "annotations are all inherited according to Java inheritance" or "implementing an interface also receives `@Inherited`" are false. Annotation inheritance has a separate contract from type/method inheritance.

### 6.1. Runnable Example: Classes Inherit; Methods and Interfaces Do Not

Create the file **`AnnotationInheritanceDemo.java`**:

```java
import java.lang.annotation.*;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Label {
    String value();
}

@Label("parent")
class ParentType {
    @Label("method-parent")
    public void work() {}
}

class ChildType extends ParentType {
    @Override
    public void work() {}
}

@Label("contract")
interface Marker {}

class Implementor implements Marker {}

public class AnnotationInheritanceDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {
        System.out.println("Child class: "
                + ChildType.class.getAnnotation(Label.class).value());
        System.out.println("Child declared? "
                + (ChildType.class.getDeclaredAnnotation(Label.class) != null));
        System.out.println("Child method annotated? "
                + (ChildType.class.getDeclaredMethod("work")
                    .getAnnotation(Label.class) != null));
        System.out.println("Parent method: "
                + ParentType.class.getDeclaredMethod("work")
                    .getAnnotation(Label.class).value());
        System.out.println("Interface transferred? "
                + (Implementor.class.getAnnotation(Label.class) != null));
    }
}
```

```bash
javac -encoding UTF-8 --release 17 AnnotationInheritanceDemo.java
java AnnotationInheritanceDemo
```

Stdout:

```text
Child class: parent
Child declared? false
Child method annotated? false
Parent method: method-parent
Interface transferred? false
```

- Class `ChildType` receives `@Label("parent")` via `getAnnotation` because `Label` has `@Inherited`.
- `ChildType.getDeclaredAnnotation(Label.class)` is `null`: `ChildType` itself does not declare `@Label`.
- Method `work()` in `ChildType` **overrides** the same-named method in `ParentType`, but does not automatically carry `@Label("method-parent")`. To consider annotations on the superclass method, you must actively locate the corresponding method in the superclass according to framework rules.
- Class `Implementor` is not automatically tagged with `@Label("contract")` just because it implements `Marker`.

**Crucial distinction:** if the subclass **does not override** `work()` and you call `ChildType.class.getMethod("work")`, Reflection may return the `Method` object **declared on the superclass**; reading annotations on that `Method` object itself finds `@Label("method-parent")`. This is the result of **inherited method lookup**, not `@Inherited` applying to method annotations. Use `getDeclaredMethod` when you need to know which methods the current class **declares itself**.

## 7. Real-World Scenarios: How Frameworks Read Metadata

### 7.1. Registering Endpoints with Annotations

Suppose a framework wants to find methods annotated with `@Route`:

- Put `@Retention(RUNTIME)` and `@Target(METHOD)` on `Route`.
- Find the exact set of classes to scan based on configuration or a registration mechanism; Reflection **does not automatically scan the entire classpath**.
- Read methods using `getDeclaredMethods()` or a strategy that includes inherited methods; each approach yields a different set of methods.
- For each `Method`, call `getDeclaredAnnotation(Route.class)` or `getAnnotationsByType(Route.class)` if `Route` is repeatable.
- Check for duplicate routes, path/method values, access permissions, and registration order according to explicit rules.

If a framework wants an annotation on an interface method to affect an implementation, it must **intentionally query the interface hierarchy and match methods by signature**; `@Inherited` does not do this.

### 7.2. Multi-Layered Permission Policies

Suppose `@Permission` is repeatable:

```java
@Permission("read")
@Permission("write")
class AdminHandler {}
```

This is an **illustrative usage pattern**, assuming `Permission` is properly defined with `@Repeatable`, a container, and `@Retention(RUNTIME)`. There are at least three reasonable but distinct policies:

- **Override:** if a subclass declares its own policy, discard the superclass policy. `getAnnotationsByType` with `@Inherited` is close to this style.
- **Merge/union:** combine permissions from parent and child; must traverse superclasses manually, deduplicate, and define how `deny` vs. `allow` is handled.
- **Deny by default:** if there is no valid policy or there is a conflict, disallow; metadata is only input, and security decisions require dedicated logic and testing.

Do not build an authorization mechanism solely on the assumption that an annotation array automatically merges all hierarchy levels.

### 7.3. Repeatable Annotation Order and Determinism

With `@Tag("first") @Tag("second")`, `getAnnotationsByType(Tag.class)` reflects the order of repeated instances according to container rules. However, a system that uses tags as a **set of choices** can normalize them by name to avoid output changes with no business meaning. If **execution order** matters, it is better to define `order()` / `priority()` or explicit dependencies, rather than relying on the listing order of annotations across different elements.

### 7.4. When Annotations Are Attached to Parameters or Type Uses

Not all metadata sits on `Class` and `Method`:

- Annotations declared on a **parameter** can be read via `method.getParameters()[i].getAnnotationsByType(MyTag.class)`, with `@Target(PARAMETER)`.
- Annotations used at a **type use site** (for example `List<@NonNull String>` if `NonNull` has `@Target(TYPE_USE)`) require the `AnnotatedType` API and variants such as `Method.getAnnotatedReturnType()`, `Field.getAnnotatedType()`, and `Parameter.getAnnotatedType()`. `Class.getAnnotations()` only returns declaration metadata of the class itself, not all annotations in every type expression.

This is the difference between **declaration annotations** and **type annotations**, not a bug in `@Retention(RUNTIME)`.

## 8. Common Errors and Diagnostics

| Symptom / Error | Common Cause | How to Fix |
| --- | --- | --- |
| `getAnnotation(X.class) == null` even though `@X` is visible in source | `@Retention` defaults to `CLASS`, or `X` is only present inside a repeatable container | Declare `@Retention(RUNTIME)`; if `X` is repeatable, use `getAnnotationsByType(X.class)`. |
| Only receives one element when writing `@X` twice | Reading with `getAnnotation(X.class)` or raw `getAnnotations()`, ignoring the container | Use `getDeclaredAnnotationsByType` / `getAnnotationsByType` depending on inheritance needs. |
| Subclass does not see interface annotation | `@Inherited` only traverses **superclasses** | Manually traverse interfaces/superinterfaces, define precedence order, and deduplicate. |
| Overridden method does not see parent method annotation | `@Inherited` does not apply to methods | Manually look up the method with matching signature in the hierarchy, if the framework contract calls for it. |
| Subclass only sees its own repeatable annotations | `getAnnotationsByType` prioritizes direct/indirect elements on the subclass | If merging is desired, traverse the hierarchy and merge according to an explicit policy. |
| `getAnnotation(X.class)` misses it, but `getAnnotation(Xs.class)` finds it | `Xs` is the container and `getAnnotation` does not unwrap it | Use `getAnnotationsByType(X.class)`; do not manually add container results. |
| Compile error when defining `@Repeatable` | Container lacks `value(): X[]`, or retention/target/`@Inherited` are incompatible | Fix both repeatable and container annotation declarations according to Java rules. |
| Missing annotation on type used in generics | Using declaration annotation APIs instead of `AnnotatedType` | Switch to `getAnnotated...` APIs when `@Target(TYPE_USE)`. |
| Results "work on my machine" but break when scanning changes | Confusing class/method/annotation order from multiple sources with business order | Normalize and sort results by an application-defined key/priority. |

### 8.1. Notes on Runtime Errors and Compatibility

Reflection code does not automatically succeed just because an annotation existed at compile time. When JARs are swapped, annotation definitions change, or types referenced in annotation values are missing, errors can occur when reading annotation elements: `TypeNotPresentException`, `EnumConstantNotPresentException`, `AnnotationTypeMismatchException`, or `IncompleteAnnotationException`. A framework should report the **class, member, annotation type, and attribute** causing the error, rather than swallowing exceptions and mistakenly treating the annotation as absent.

If you only need to check a marker, `isAnnotationPresent` is suitable for **non-repeatable** annotations or when "present" semantics are understood. When dealing with repeatable annotations, checking `getAnnotationsByType(A.class).length > 0` is usually clearer.

### 8.2. Security and Limitations

Annotations are **data**, not an automatic protection mechanism. `@Permission("admin")` does not lock an endpoint by itself; the framework must evaluate the policy on every appropriate call path. Do not arbitrarily instantiate classes or invoke methods just because metadata comes from untrusted JARs or configurations. Apply allowlists, test precedence logic, and restrict plugin sources.

**Reading annotations** is different from enabling access to private members. Normally you do not need `setAccessible(true)` just to inspect metadata; JPMS can restrict deep reflection, and you should not broadly open modules to work around an undiagnosed annotation-reading error.

## 9. Testing Annotation Rules Properly

A test suite should cover at least the following independent cases:

1. `SOURCE`, `CLASS`, and `RUNTIME` annotations on the same element kind; verify that only `RUNTIME` is readable via Reflection.
2. Single annotation and repeatable annotation **2+ times**; compare `getAnnotation` with `getAnnotationsByType`.
3. Repeatable and container properly declared with `@Retention(RUNTIME)`, `@Target`, and `@Inherited` (if applicable).
4. Subclass declaring no annotation; subclass declaring one annotation of the same type; verify the difference between `getAnnotationsByType` and `getDeclaredAnnotationsByType`.
5. Interface carrying `@Inherited` and an implementing class; ensure the annotation is not automatically inherited from the interface.
6. Overridden method and inherited non-overridden method; distinguish `getDeclaredMethod` from `getMethod`.
7. A class with no annotations; single-element result from `getAnnotation` is `null` while array result from `getAnnotationsByType` has length 0.
8. For frameworks with a **merge** policy, write dedicated tests for parent/child order, duplicates, allow/deny, and conflicts; do not rely on `@Inherited` defaults.

When testing repeatable annotations, assert **values in the exact order required by the contract**, for example:

```text
Parent tags: base-a,base-b
Child associated: base-a,base-b
Child declared count: 0
```

These are three lines taken from the Section 5 example, not the entire stdout. Avoid writing tests that check the raw order of **unrelated annotation types** in `getAnnotations()`.

## 10. Self-Check Questions

**Question 1.** Why is `@MyTag` present in source code, yet `SomeClass.class.getAnnotation(MyTag.class)` returns `null`?

**Answer:** A common reason is that `MyTag` defaults to `CLASS` retention. If `MyTag` is repeatable and wrapped in a container, `getAnnotation(MyTag.class)` also does not unwrap the container automatically. Check the annotation definition, then use the appropriate API.

**Question 2.** Two `@Tag` annotations on a superclass, and the subclass declares none. Which API returns both if both `Tag` and its container are `@Inherited`?

**Answer:** `Child.class.getAnnotationsByType(Tag.class)`. `getDeclaredAnnotationsByType(Tag.class)` returns an empty array; `getAnnotation(Tag.class)` does not unwrap the container.

**Question 3.** When a subclass declares one `@Tag` of its own, does `getAnnotationsByType(Tag.class)` also return the two tags from the superclass?

**Answer:** No. Tags declared on the subclass take precedence; the API does not merge the entire hierarchy by default. If a union is desired, you must design your own algorithm.

**Question 4.** Does `@Inherited` cause an interface's annotation to transfer to an implementing class, or a parent method's annotation to transfer to an overriding method?

**Answer:** No. Java's `@Inherited` applies to querying annotations **on a class through the superclass chain**, not every form of Java language inheritance.

**Question 5.** If an inherited non-overridden method returns the annotation written on the parent method, is that `@Inherited` working on methods?

**Answer:** No. Reflection is returning the exact `Method` object declared on the superclass when looking up an inherited member. When overridden, the new method does not automatically have that annotation.

## 11. Key Takeaways

- **Reading annotations at runtime requires `@Retention(RUNTIME)`**; `CLASS` and `SOURCE` do not appear through standard Reflection.
- **Read repeatable annotations using `getAnnotationsByType` / `getDeclaredAnnotationsByType`**. `getAnnotation` and `getDeclaredAnnotation` do not unwrap containers automatically.
- **`@Inherited` only takes effect on class declarations via superclasses**; it does not apply automatically to interfaces, methods, fields, or parameters. For repeatable annotations, a subclass declaring its own instance will not automatically merge with instances on the superclass.
- **Distinguish data from policy.** A framework must explicitly choose rules for reading on an element, whether to inherit, whether to merge or override, and processing order according to the application contract.
- When designing a metadata API, combine tests for retention, containers, inheritance, overrides, and absent annotations; avoid depending on accidental runtime behavior.

### Official Documentation (Java SE 17)

- [`AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): defines **directly present**, **indirectly present**, **present**, **associated**, the API semantics table, and repeatable element ordering.
- [`Retention`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Retention.html) and [`RetentionPolicy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/RetentionPolicy.html): annotation visibility after compilation and at runtime.
- [`Repeatable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html): declaring repeatable annotations and containers.
- [`Inherited`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html): superclass-only inheritance rules for class annotations.
- [`Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html), [`Method`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html), and [`AnnotatedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html): querying metadata on classes, executables, and type use sites.
