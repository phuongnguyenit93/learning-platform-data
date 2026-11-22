# Reference Table: Direct, Indirect, and Inherited Annotations in Java Reflection

An annotation written on a class, method, or field is not necessarily returned by every annotation lookup API. The result depends on **whether the annotation exists in runtime metadata**, **whether it is attached directly or sits inside a repeatable container**, **whether the queried target is a class or a member**, and **whether the annotation type has `@Inherited`**.

Java defines four terms with precise meanings: **directly present**, **indirectly present**, **present**, and **associated**. Understanding these four terms helps you choose between `getAnnotation`, `getDeclaredAnnotation`, `getAnnotationsByType`, and `getDeclaredAnnotationsByType` without guessing from API names.

> **Quick rule:** To find an annotation that may be inherited, use `getAnnotation(T.class)`; to find annotations that are repeatable **and** inherited, use `getAnnotationsByType(T.class)`. To search **only on the current element**, use the corresponding `getDeclared...` variants. First and foremost, however, the annotation must have `RetentionPolicy.RUNTIME` for standard Reflection to see it.

## 1. Prerequisite: The Annotation Still Exists at Runtime

`@Retention` specifies the retention policy for annotations after compilation:

| Retention Policy | Present in class file | Readable by standard Reflection via `getAnnotation(...)` |
|---|---|---|
| `RetentionPolicy.SOURCE` | Not retained on the element in the class file | No |
| `RetentionPolicy.CLASS` | Retained in the class file but not runtime-visible | No |
| `RetentionPolicy.RUNTIME` | Retained in the class file and runtime-visible | Yes, given the right element/lookup method |

`CLASS` is the default retention if `@Retention` is not declared. For annotations used to drive framework behavior at runtime, you normally need to write `@Retention(RetentionPolicy.RUNTIME)` explicitly.

Example:

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Category {
    String value();
}
~~~

This is a **declaration fragment**, not a program with `main`. `@Target(ElementType.TYPE)` states that the annotation can be attached to declarations of classes, interfaces, enums, or annotation types; it **does not mean** the annotation is automatically inherited from interfaces.

Reading the annotation on a class is:

~~~java
Category category = SomeClass.class.getAnnotation(Category.class);
~~~

This snippet assumes `SomeClass` has already been declared and annotated with `@Category(...)`; it does not run standalone. If the result is `null`, the cause may be that the annotation is absent, the `retention` is unsuitable, the annotation is on another element, or inheritance rules are not satisfied.

## 2. Four Concepts: Direct, Indirect, Present, Associated

According to the contract of `java.lang.reflect.AnnotatedElement` in Java 17:

| Javadoc Term | Interpretation | Typical Example |
|---|---|---|
| **Directly present** | Runtime-visible metadata on the element itself containing that annotation instance | `@Role("base")` attached directly on `Base` |
| **Indirectly present** | A repeatable annotation sitting **inside a container annotation** directly on the element | Two `@Label`s on `Base` represented via a `@Labels` container |
| **Present** | Directly present; or an inheritable annotation found along the superclass chain when no instance of the same type is directly on the class | `Child` has no `@Role` of its own, yet `getAnnotation(Role.class)` sees `Base`'s `@Role` |
| **Associated** | Directly **or** indirectly present; or inherited from a superclass when there is no direct/indirect one of the same type on the class | `Child.getAnnotationsByType(Label.class)` returns `Base`'s two labels |

In the case of **non-repeatable** annotations, there is no container unwrapping step, so the main difference is **declared/local** versus **inherited**. With **repeatable** annotations, both axes must be distinguished:

~~~text
                                Unwrap repeatable container?
                                    NO               YES
                                +-----------+--------------------+
On the element itself only      |  Declared | Declared ByType    |
Does not walk up superclass     | Annotation|                    |
                                +-----------+--------------------+
Allows @Inherited               | Annotation| AnnotationsByType  |
along superclass chain          +-----------+--------------------+
~~~

The cell names in the diagram are shortened from the `get...` method names. "Allows @Inherited" does **not** mean a method will automatically pick up annotations from an interface or an overridden method.

### Direct and Indirect Example

~~~java
@Label("A")
@Label("B")
class Base {}
~~~

In Java supporting repeatable annotations, when multiple `@Label`s are attached, the compiler can place the labels inside the container annotation `@Labels`. Therefore, right on `Base`:

- `getDeclaredAnnotation(Label.class)` returns `null` if only the `Labels` container is directly present.
- `getDeclaredAnnotationsByType(Label.class)` returns both `Label("A")` and `Label("B")` by "opening" the container.
- `getAnnotation(Label.class)` can also return `null` for the two labels inside the container, even though the annotations are clearly visible in source code.
- `getAnnotationsByType(Label.class)` returns both labels and can also walk up the superclass chain via `@Inherited` when no labels are directly/indirectly present on the subclass.

Conversely, with **a single** `@Label("C")`, the annotation is normally directly present under type `Label`: `getAnnotation(Label.class)` can return that label itself.

**Important:** "Indirect" here **does not mean** "an annotation taken from a superclass" as in everyday usage. In the `AnnotatedElement` Javadoc, *indirectly present* applies to repeatable annotations inside a **container**. Inheritance is a separate rule, participating in *present* or *associated*.

## 3. Complete API Table: Which Presence Type Does Each Method Accept?

| API on `AnnotatedElement` | Presence Type Considered | Unwraps Repeatable Container? | Can Walk Up Superclass? | Result When Not Found |
|---|---|---|---|---|
| `getAnnotation(T.class)` | **Present** | No | Yes, with `@Inherited` on a class | `null` |
| `getAnnotations()` | **Present** for each direct/inherited annotation type | Does not individually unwrap repeatable containers | Yes, for `@Inherited` types | Empty array |
| `getDeclaredAnnotation(T.class)` | **Directly present** | No | No | `null` |
| `getDeclaredAnnotations()` | **Directly present** | Does not individually unwrap containers | No | Empty array |
| `getAnnotationsByType(T.class)` | **Associated** | **Yes** | Yes, with `@Inherited` on a class | Empty array |
| `getDeclaredAnnotationsByType(T.class)` | **Directly/indirectly present** | **Yes** | No | Empty array |
| `isAnnotationPresent(T.class)` | Equivalent to `getAnnotation(T.class) != null` | No | Yes, with `@Inherited` on a class | `false` |

This table follows the **Java 17 semantics** of `AnnotatedElement`. Depending on the object kind, these methods appear on `Class`, `Method`, `Field`, `Constructor`, `Parameter`, `Package`, etc.; however, **the `@Inherited` mechanism only walks up the class superclass chain**, and does not apply generally to every `AnnotatedElement`.

In the two `get...AnnotationsByType(T.class)` methods, if `T` is a repeatable annotation, Java finds the appropriate container annotation, unpacks the `value()` array in the container, and returns the child annotations. When the same element has multiple annotations of the same type, the order is determined as if the annotations inside the container appeared at the container's position, in `value()` order.

### Examples of Choosing the Right API for the Need

| Question | Appropriate API |
|---|---|
| Does the class have a `@Service` directly or inherited? | `type.getAnnotation(Service.class)` |
| Does the class **itself declare** `@Service`, ignoring superclasses? | `type.getDeclaredAnnotation(Service.class)` |
| Which `@Route`s does the class have (possibly multiple and inherited)? | `type.getAnnotationsByType(Route.class)` |
| Only the `@Route`s declared directly on the class, including repeatable ones? | `type.getDeclaredAnnotationsByType(Route.class)` |
| List annotations directly on the class to display raw metadata? | `type.getDeclaredAnnotations()`, keeping in mind you may see the container instead of child labels |
| List annotations attached directly or inherited? | `type.getAnnotations()`, which is not synonymous with flattening repeatables |
| Check annotation on an overridden method? | `method.getAnnotation(...)` on the exact `Method` object, without assuming `@Inherited` works |

In general code, do not use `getAnnotations()` and merely compare annotation names to "unpack" repeatables when `getAnnotationsByType(T.class)` already exists. The ByType API expresses the exact intent and handles containers defined by `@Repeatable`.

## 4. Where Does `@Inherited` Work and When Does It Stop?

`java.lang.annotation.Inherited` is a **meta-annotation** placed on an annotation type declaration. It allows looking up annotations from **a class's superclass**, according to the rules in the table above. Example:

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Role {
    String value();
}

@Role("base")
class Base {}

class Child extends Base {}
~~~

This is an illustrative snippet requiring imports like the program in Section 6. `Child` does not directly have `@Role`, yet `Child.class.getAnnotation(Role.class)` returns `Role("base")`, while `getDeclaredAnnotation(Role.class)` returns `null`.

Very important limitations:

1. **Not through interfaces:** If interface `API` has `@Role` and class `Service implements API`, `Service.class.getAnnotation(Role.class)` **does not** automatically receive `Role` from the interface. `Class.getInterfaces()` allows you to traverse manually if that is a framework policy, but **that is a custom algorithm, not default `@Inherited`**.
2. **Does not apply to methods/fields/constructors:** `@Inherited` does not make an overridden method receive annotations from the base class method. If you call `getMethod(...)` on a subclass and receive a `Method` declared by the superclass (because the subclass **did not override** it), the annotation may appear because **you are querying the superclass's method itself**, not because the annotation on the method was inherited.
3. **Subclass has an annotation of the same type:** If a class directly declares `@Role("child")`, looking up `Role` on the subclass returns the child value, without adding the base one.
4. **Inheritance by annotation type, not aggregating every instance:** With `getAnnotationsByType`, if the subclass already has annotations of the same type directly or indirectly, the API takes the subclass instances; it **does not automatically concatenate** the subclass list with the superclass list.
5. **`@Inherited` does not alter the subclass's class file source:** It changes Reflection lookup logic; `getDeclaredAnnotation` still clearly distinguishes what is declared directly on the subclass.

A system that needs annotation inheritance from interfaces, overridden methods, or all superclasses under a merge policy must define its own traversal, resolution order, conflict handling, and precedence. You cannot call `getAnnotation` once and assume the JVM implemented a custom policy.

## 5. Repeatable Annotations, Containers, and Combining with Inheritance

An annotation type can be made repeatable with `@Repeatable(Container.class)`:

~~~java
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
~~~

This snippet is a **declaration fragment** with appropriate imports. `Labels` is the container annotation. If `Label` is marked `@Inherited`, **the container `Labels` must also be marked `@Inherited`** per language constraints; forgetting this can prevent the program from compiling.

Some rules:

- The container's signature must have an element named `value` of type `Label[]`. The container's retention must not be shorter than the contained annotation's retention; the container's target must be compatible.
- When two `@Label`s are written on the same class, the compiler typically stores the `@Labels` container instead of two direct `Label` annotation instances in runtime metadata.
- `getAnnotationsByType(Label.class)` recognizes both **directly** and **indirectly** present annotations, making it suitable for repeatable types.
- `getAnnotation(Label.class)` does not automatically unwrap containers. A single query for `Label.class` on a class with two repeated labels can return `null`.
- **Local shadows inherited:** When the superclass has `@Label("A")`, `@Label("B")` and the subclass has `@Label("C")`, `subclass.getAnnotationsByType(Label.class)` returns `[C]`, **not** `[C, A, B]`.
- The order of annotations of the same type returned by `...ByType` is based on the order inside the container at the container's position, rather than an arbitrary sort order. If you want canonical tool output, you can sort separately by a business key after reading, but you must document the rule.

**Warning about containers and inheritance:** The container is also an independent annotation type when querying metadata. Do not mix querying `Labels.class` with `Label.class` and assume the same merge rules. To ask for "all Label annotations attached/inherited under the repeatable contract", call `getAnnotationsByType(Label.class)` directly.

## 6. Java 17+ Program Illustrating and Verifying Results

Save the entire code as **`AnnotationPresenceDemo.java`**. The code needs no libraries outside the JDK. We will observe:

- `Role`: non-repeatable annotation with `@Inherited`.
- `Local`: annotation without `@Inherited`.
- `Label`: repeatable annotation with `@Inherited`, together with container `Labels`.
- `Base` has two `Label`s, `Child` attaches no new annotations, `OverrideChild` has its own annotations.
- Interface `AnnotatedInterface` has `@Role`, yet implementing classes do not automatically inherit that annotation.
- Method `act` has `@MethodNote` in base; an overriding subclass does not automatically receive it, while a non-overriding subclass still retrieves base's `Method`.

~~~java
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;
import java.util.Arrays;

public class AnnotationPresenceDemo {
    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    public @interface Role {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    public @interface Local {
        String value();
    }

    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @Repeatable(Labels.class)
    public @interface Label {
        String value();
    }

    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    public @interface Labels {
        Label[] value();
    }

    @Role("base")
    @Local("local")
    @Label("A")
    @Label("B")
    public static class Base {}

    public static class Child extends Base {}

    @Role("child")
    @Label("C")
    public static class OverrideChild extends Base {}

    @Role("interface")
    public interface AnnotatedInterface {}

    public static class Implementation implements AnnotatedInterface {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    public @interface MethodNote {}

    public static class ParentMethods {
        @MethodNote
        public void act() {}
    }

    public static class OverridingMethods extends ParentMethods {
        @Override
        public void act() {}
    }

    public static class NonOverridingMethods extends ParentMethods {}

    private static String role(Role annotation) {
        return annotation == null ? "<none>" : annotation.value();
    }

    private static String labels(Label[] annotations) {
        return Arrays.toString(
                Arrays.stream(annotations).map(Label::value).toArray(String[]::new));
    }

    private static void report(String title, Class<?> type) {
        System.out.println(title);
        System.out.println("  Role getAnnotation = " +
                role(type.getAnnotation(Role.class)));
        System.out.println("  Role getDeclaredAnnotation = " +
                role(type.getDeclaredAnnotation(Role.class)));
        System.out.println("  Local getAnnotation = " +
                (type.getAnnotation(Local.class) != null));
        System.out.println("  Label getAnnotation = " +
                (type.getAnnotation(Label.class) != null));
        System.out.println("  Label getDeclaredAnnotationsByType = " +
                labels(type.getDeclaredAnnotationsByType(Label.class)));
        System.out.println("  Label getAnnotationsByType = " +
                labels(type.getAnnotationsByType(Label.class)));
    }

    public static void main(String[] args) throws NoSuchMethodException {
        report("Base", Base.class);
        report("Child", Child.class);
        report("OverrideChild", OverrideChild.class);
        report("Implementation", Implementation.class);

        boolean parent = ParentMethods.class.getMethod("act")
                .isAnnotationPresent(MethodNote.class);
        boolean overriding = OverridingMethods.class.getMethod("act")
                .isAnnotationPresent(MethodNote.class);
        boolean nonOverriding = NonOverridingMethods.class.getMethod("act")
                .isAnnotationPresent(MethodNote.class);
        System.out.println("method ParentMethods = " + parent);
        System.out.println("method OverridingMethods = " + overriding);
        System.out.println("method NonOverridingMethods = " + nonOverriding);
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 AnnotationPresenceDemo.java
java AnnotationPresenceDemo
~~~

**Verified stdout:**

~~~text
Base
  Role getAnnotation = base
  Role getDeclaredAnnotation = base
  Local getAnnotation = true
  Label getAnnotation = false
  Label getDeclaredAnnotationsByType = [A, B]
  Label getAnnotationsByType = [A, B]
Child
  Role getAnnotation = base
  Role getDeclaredAnnotation = <none>
  Local getAnnotation = false
  Label getAnnotation = false
  Label getDeclaredAnnotationsByType = []
  Label getAnnotationsByType = [A, B]
OverrideChild
  Role getAnnotation = child
  Role getDeclaredAnnotation = child
  Local getAnnotation = false
  Label getAnnotation = true
  Label getDeclaredAnnotationsByType = [C]
  Label getAnnotationsByType = [C]
Implementation
  Role getAnnotation = <none>
  Role getDeclaredAnnotation = <none>
  Local getAnnotation = false
  Label getAnnotation = false
  Label getDeclaredAnnotationsByType = []
  Label getAnnotationsByType = []
method ParentMethods = true
method OverridingMethods = false
method NonOverridingMethods = true
~~~

### Why Did the Results Turn Out That Way?

**`Base`:** `Role` and `Local` are declared directly so `getAnnotation` finds them. The two `Label`s are placed in a repeatable container; therefore `getAnnotation(Label.class)` is `null`, while both `...ByType` APIs receive `[A, B]`.

**`Child`:** declares no new `Role` or `Label`. `getAnnotation(Role.class)` walks up to `Base` because `Role` has `@Inherited`, whereas `getDeclaredAnnotation(Role.class)` does not walk up so it is `null`. `Local` has no `@Inherited` so it is not seen. `getDeclaredAnnotationsByType(Label.class)` is `[]`, while `getAnnotationsByType(Label.class)` receives `[A, B]` from `Base`.

**`OverrideChild`:** has `@Role("child")` and `@Label("C")` directly; they shadow the same-type values on `Base` in the corresponding present/associated lookups. A single `Label` is returned via `getAnnotation(Label.class)`, and `getAnnotationsByType(Label.class)` is `[C]` rather than merging with `[A, B]`.

**`Implementation`:** merely `implements AnnotatedInterface`. Even though the interface has `@Role("interface")` and `Role` has `@Inherited`, it is not searched across `implements` edges, so all `Role` queries on `Implementation` are absent.

**`ParentMethods` / `OverridingMethods` / `NonOverridingMethods`:** the base method directly has `@MethodNote`. When the subclass overrides the method with a new declaration without the annotation, Reflection on the new `Method` does not receive `@MethodNote`. For the non-overriding subclass, `Class.getMethod("act")` returns the public method declared by the superclass; the `true` result is the annotation **of the original Method**, not an annotation "inherited" onto a new method.

## 7. Core Result Matrix for Quick Lookup

From the program above, we have two tables:

### 7.1. Single Annotation (`Role`) and Non-Inherited Annotation (`Local`)

| `Class` Object | `getAnnotation(Role.class)` | `getDeclaredAnnotation(Role.class)` | `getAnnotation(Local.class)` |
|---|---|---|---|
| `Base` | `base` | `base` | Yes |
| `Child` | `base` (inherited) | `null` | No |
| `OverrideChild` | `child` | `child` | No |
| `Implementation` | `null` (not taken from interface) | `null` | No |

### 7.2. Repeatable Annotation (`Label`)

| `Class` Object | `getAnnotation(Label.class)` | `getDeclaredAnnotationsByType(Label.class)` | `getAnnotationsByType(Label.class)` |
|---|---|---|---|
| `Base`: two `@Label`s | `null` | `[A, B]` | `[A, B]` |
| `Child`: none declared | `null` | `[]` | `[A, B]` (inherited) |
| `OverrideChild`: one `@Label("C")` | `Label("C")` | `[C]` | `[C]` |
| `Implementation` | `null` | `[]` | `[]` |

The table uses `[A, B]` to denote **the values of `Label.value()`**, not the `toString()` string of the annotation proxy itself. When data is needed, retrieve each `Label` and call `value()`; do not rely on `toString()` as a stable data interchange format.

## 8. Easy-to-Confuse Cases When Writing Lookup Tools

### 8.1. Confusing `getDeclared...` with "private" or "public"

The word `declared` here **is unrelated to public/private access rights**. It refers to **metadata attached directly on the current element**, ignoring inheritance rules. `getDeclaredAnnotation` is not "stronger" or "bypassing permissions" compared to `getAnnotation`; it simply has different semantics.

On a member, `getDeclaredAnnotations()` also does not mean you can access a private field's value. Reading annotation metadata is different from `Field.get` or `Method.invoke`, which are subject to separate access rules.

### 8.2. Confusing the Container Annotation with Contained Annotations

`getDeclaredAnnotations()` can return the `Labels` container directly, rather than listing the two `Label`s at the same level. Using `getDeclaredAnnotationsByType(Label.class)` is the right way to get the `Label`s inside the container.

A framework that needs to display **verbatim runtime annotation metadata** may care about the container. A framework that needs to read the list of labels for business logic should usually use ByType.

### 8.3. Expecting `@Inherited` to Perform a "Deep Merge"

`getAnnotationsByType(Label.class)` on `OverrideChild` gives `[C]`, not `[A, B, C]`. If the business policy is "all labels along the entire superclass chain", write a custom algorithm:

~~~java
for (Class<?> current = targetClass;
        current != null;
        current = current.getSuperclass()) {
    Label[] local = current.getDeclaredAnnotationsByType(Label.class);
    // Define custom merge, priority, and deduplication logic here.
}
~~~

This snippet is an **algorithm fragment**, requiring code with `Class<?> targetClass` and a `Label` definition. It reads each class's annotations accurately without accidentally receiving `@Inherited` values twice at each level. However, the merged result is **not** the default semantics of `getAnnotationsByType`.

If you want annotation inheritance on interfaces, you must also actively traverse `getInterfaces()` (possibly recursively), handle diamond branches, and resolve multiple interfaces with conflicting annotations. `@Inherited` does not resolve those conflicts for you.

### 8.4. Confusing Overriding with `Method` Inheritance

A **non-overriding** subclass can find a `Method` from its superclass via `getMethod(...)`, and `Method.getAnnotation(...)` sees the annotation on that declaration. An **overriding** subclass creates a different declaration; annotations on the original method are not automatically copied. If a framework wants a method annotation inheritance policy, it must locate matching methods on superclasses/interfaces according to its own contract.

### 8.5. Annotation Targets Other Than Declaration Targets

Java also supports **type-use annotations** (for example on type parameters, array components, generic type arguments) via `ElementType.TYPE_USE`. Reading these annotations may require `AnnotatedType`, `Method.getAnnotatedReturnType()`, `Parameter.getAnnotatedType()`, and related APIs, rather than just `Method.getAnnotations()`. The table here covers general `AnnotatedElement` semantics when querying the right element; it is not a promise that annotations at every syntactic position will appear on a given `Class` or `Method`.

### 8.6. Unreadable Does Not Mean Bytecode Lacks Metadata

`CLASS` annotations exist in the class file but are not runtime-visible via standard Reflection. `SOURCE` annotations can be read by annotation processors at compile time but are gone after compilation. If the requirement is to analyze `CLASS` annotations in bytecode as well, an appropriate bytecode parser/tool is needed; do not try to use `getDeclaredAnnotations()` to recover metadata not exposed by Reflection.

### 8.7. When Annotations Return `null` / Empty Arrays

`getAnnotation(T.class)` and `getDeclaredAnnotation(T.class)` return `null` when not found. The two `...ByType(T.class)` methods return arrays of length `0`. Avoid:

~~~java
String name = targetClass.getAnnotation(Role.class).value();
~~~

This is an **illustrative snippet**: if the annotation is absent, calling `value()` causes a `NullPointerException`. You can check:

~~~java
Role role = targetClass.getAnnotation(Role.class);
if (role != null) {
    String name = role.value();
    // Use name according to application needs.
}
~~~

When an annotation has default values, that does not mean `getAnnotation(...)` synthesizes an annotation instance if it is not attached to the element. Default values only apply **inside an annotation instance that is actually present**.

## 9. Implementation Checklist When Building an Annotation Reader

Before implementing an annotation scanner, answer these questions:

1. **Does the annotation type have `RUNTIME` retention?** If not, Reflection is not the right reading tool.
2. **Which element should be queried?** Class, method, field, parameter, package, or type-use? Do not query the wrong object.
3. **Can there be multiple annotations of the same type?** If `@Repeatable` is used, use `...ByType` when container unpacking is needed.
4. **Do you want to find annotations from superclasses?** For classes and `@Inherited` annotations, use the methods without `Declared`.
5. **Do you want to merge annotations across multiple levels?** If so, define a custom algorithm and use `getDeclaredAnnotationsByType` at each level for control.
6. **Do you want to receive annotations from interfaces?** By default `@Inherited` does not do that.
7. **Are you looking for metadata on overridden methods?** If so, clarify which declaration is read, then design the policy yourself.
8. **Are you combining repeatable and inherited?** The container must comply with compatible `@Inherited`/`@Retention`/`@Target`; test subclasses declaring new labels.
9. **Do you need stable output when serializing?** Do not rely on the general order of `getAnnotations()` or annotation `toString()`; normalize keys and order per tool contract.
10. **Do you need to distinguish not-found from metadata reading errors?** Some Reflection calls can throw metadata errors (e.g. invalid annotation type or missing referenced class); do not lump every exception into "annotation absent".

## 10. Self-Check Exercises

1. Add `@Inherited` to `@Local` and re-run the example. Does `Child` see `Local`? Does `Implementation` see it from the interface?
2. Remove one of the two `@Label`s on `Base`. When **one** `@Label` remains, predict `getAnnotation(Label.class)` and `getDeclaredAnnotationsByType(Label.class)`.
3. Keep `Base` with `[A, B]` but change `OverrideChild` to two labels `[C, D]`. Predict `getAnnotation(Label.class)`, `getDeclaredAnnotationsByType`, and `getAnnotationsByType`.
4. Delete `@Role("child")` on `OverrideChild`. After a clean compile, compare `getAnnotation(Role.class)` and `getDeclaredAnnotation(Role.class)`.
5. On `AnnotatedInterface.class`, read `@Role`; on `Implementation.class`, read the same annotation. Explain why the results differ.
6. Remove `@Override`/the overriding method in `OverridingMethods` (keep only `extends ParentMethods`). When calling `getMethod("act")`, what is `getDeclaringClass()` of the resulting `Method` object?
7. Write a function `allLabels(Class<?>)` that collects labels from the entire superclass chain using `getDeclaredAnnotationsByType`, deduplicates by `value`, and documents the precedence order.
8. Change `Label`'s retention to `CLASS` and adjust the container compatibly. What do the compiler and Reflection still return? Why can a compile-time processor still work with `CLASS` annotations while standard runtime Reflection cannot?
9. Design a table comparing `getAnnotations()` and `getDeclaredAnnotations()` for `Base`/`Child`, stating which container appears and distinguishing "listing the container" from "unwrapping Label".

**Summary:** "Directly present" = annotation instance on the element itself; "indirectly present" = repeatable annotation inside a container; "present" = direct or inherited via `@Inherited`; "associated" = direct/indirect or appropriately inherited. `getAnnotation` follows **present**, `getDeclaredAnnotation` follows **direct**, `getAnnotationsByType` follows **associated**, and `getDeclaredAnnotationsByType` follows **direct + indirect**. `@Inherited` only resolves lookups through class superclasses, not through interfaces or method overrides, and does not accumulate across all levels when a subclass already has annotations of the same type.

### Official References (Java 17)

- [`AnnotatedElement` — definitions of the four presence kinds, API matrix](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html)
- [`Inherited` — limitations and how it works](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html)
- [`Repeatable` — container annotations](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html)
- [`RetentionPolicy` — SOURCE, CLASS, RUNTIME](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/RetentionPolicy.html)
- [JLS 17, `9.6.3` — repeatable annotation types and containing annotation types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.3)
