# getAnnotationsByType vs. getDeclaredAnnotationsByType in Java Reflection

## 1. Problem: finding annotations by type is not just reading an annotation list

When using Java Reflection, a class, method, or field can carry **runtime annotations**. If an annotation is declared repeatable via `@Repeatable`, a single element can have multiple annotations of the same type. If an annotation is marked `@Inherited`, a **class** can observe annotations from a superclass when it does not declare an annotation of the same type itself.

Two APIs in `java.lang.reflect.AnnotatedElement` address two different scopes:

- `getAnnotationsByType(Class<T> annotationClass)`: finds all **associated** annotations of a type on the element. For a `Class`, the result can include annotations inherited from superclasses under `@Inherited` rules.
- `getDeclaredAnnotationsByType(Class<T> annotationClass)`: finds all annotations of that type **directly present** or **indirectly present** on **the queried element itself**, without taking from superclasses.

A common point of confusion is that both support **repeatable annotations** by expanding (*unpacking*) the container annotation. Their key difference is **inheritance semantics**, not “one method understands repeatable and the other does not”.

> In this lesson, “declared” means metadata residing on the current element; it does **not** mean annotations with `private` visibility, nor is it equivalent to `getDeclaredAnnotations()`, because the method without `ByType` normally does not auto-expand containers.

## 2. Four concepts: directly present, indirectly present, present, associated

To understand both APIs accurately, distinguish these annotation states:

| Term | Practical meaning | Example |
| --- | --- | --- |
| **Directly present** | An annotation of the exact type appears directly in the element's runtime metadata | `@Label("x")` declared once |
| **Indirectly present** | The annotation is held inside a **containing annotation** of a `@Repeatable` type | Two `@Label`s packed by the compiler into `@Labels` |
| **Present** | Directly present, or an annotation inherited under `@Inherited` rules applicable to `Class` | `Child` inherits an annotation present on `Parent` |
| **Associated** | Directly present, indirectly present, or inherited under applicable rules if the current element has no annotation of that type directly/indirectly | `Child.class.getAnnotationsByType(Label.class)` can return `Label`s on `Parent` |

Specifically:

- `getDeclaredAnnotationsByType(T.class)` returns annotations of type `T` that are **directly and indirectly** on the element under inspection.
- `getAnnotationsByType(T.class)` returns annotations of type `T` **associated** with the element; if the element is a `Class` and `T` has `@Inherited`, the method may inspect superclasses.
- If a subclass **already has** annotations of type `T` directly or indirectly, the result of `getAnnotationsByType` prefers this **local** set and **does not auto-merge** with the set of the same type on the superclass.
- `@Inherited` does not cause annotations on **methods, fields, or interfaces** to be automatically inherited in the same way as annotations on classes.

### Repeatable annotations and containers

With a repeatable annotation type:

```java
@Repeatable(Labels.class)
@interface Label {
    String value();
}

@interface Labels {
    Label[] value();
}
```

This is a syntax illustration without `@Retention(RUNTIME)`, so it is **not yet sufficient** to read via Reflection at runtime. The runnable example below supplies the complete metadata.

Two annotations:

```java
@Label("alpha")
@Label("beta")
class Service {}
```

are normally represented in the class file by the **container** `@Labels` with a `value()` array holding two `@Label`s. Therefore:

- `Service.class.getDeclaredAnnotationsByType(Label.class)` sees two `Label`s.
- `Service.class.getDeclaredAnnotation(Label.class)` normally returns `null` because runtime metadata stores **container `Labels`**, not two `Label`s as two independent direct annotations.
- `Service.class.getDeclaredAnnotation(Labels.class)` sees container `Labels`.
- `Service.class.getDeclaredAnnotations()` may show container `Labels`, without automatically expanding it into two `Label`s.

This is why you must use the APIs with the **`ByType`** suffix when you want a list of repeatable annotations by the **inner annotation type**, rather than manually locating and unpacking the container.

## 3. Quick comparison of Reflection APIs

| API | Return type | Expands repeatable annotations? | Considers inheritance? |
| --- | --- | --- | --- |
| `getAnnotation(T.class)` | `T` or `null` | Not a specialized API to unpack all container elements | Possible, under `@Inherited` and present rules on `Class` |
| `getDeclaredAnnotation(T.class)` | `T` or `null` | Does not auto-return multiple annotations held in a container | No |
| `getAnnotationsByType(T.class)` | `T[]` | **Yes** | **Possible**, with `Class` and `@Inherited` |
| `getDeclaredAnnotationsByType(T.class)` | `T[]` | **Yes** | **No** |
| `getAnnotations()` | `Annotation[]` | Does not auto-convert containers into multiple `T`s | Can reflect inherited annotations under runtime rules |
| `getDeclaredAnnotations()` | `Annotation[]` | Does not auto-convert containers into multiple `T`s | No |

**Selection rule:** when reading a repeatable annotation from a class and wanting to see the effective annotations after inheritance, use `getAnnotationsByType`. When writing a tool that analyzes **only annotations placed on the current class**, use `getDeclaredAnnotationsByType`.

APIs with `Declared` do not mean “only return annotations from uncompiled classes”; `Class`, `Method`, `Field`, and other `AnnotatedElement` objects can all provide these methods within their respective scopes.

## 4. Standalone runnable Java 17+ example

Save the entire program below to **`AnnotationByTypeDemo.java`**. The program has an annotation `Label` that is both `@Repeatable` and `@Inherited`, and container `Labels` also has runtime retention/`@Inherited`. The test classes include:

- `Parent`: two repeated labels.
- `Child`: declares no own `Label`, so it can see labels from the superclass when using the associated API.
- `OwnChild`: one own label, shadowing `Parent`'s inherited label set for by-type queries.
- `TwoChild`: two own labels, testing a local container.
- `ContainerChild`: directly declares container `@Labels`.
- `Implementation`: implements an annotated interface, proving `@Inherited` does not run through interfaces.

```java
import java.lang.annotation.*;
import java.util.*;
import java.util.stream.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Inherited
@Repeatable(Labels.class)
@interface Label {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Inherited
@interface Labels {
    Label[] value();
}

@Label("parent-a")
@Label("parent-b")
class Parent {}

class Child extends Parent {}

@Label("child")
class OwnChild extends Parent {}

@Label("local-a")
@Label("local-b")
class TwoChild extends Parent {}

@Labels({@Label("explicit-a"), @Label("explicit-b")})
class ContainerChild extends Parent {}

@Label("interface-only")
interface Contract {}

class Implementation implements Contract {}

public class AnnotationByTypeDemo {
    private static String names(Label[] labels) {
        return Arrays.stream(labels)
                .map(Label::value)
                .sorted()
                .collect(Collectors.joining(", ", "[", "]"));
    }

    private static void describe(Class<?> type) {
        System.out.println(type.getSimpleName()
                + ": all=" + names(type.getAnnotationsByType(Label.class))
                + " declared="
                + names(type.getDeclaredAnnotationsByType(Label.class)));
    }

    public static void main(String[] args) {
        describe(Parent.class);
        describe(Child.class);
        describe(OwnChild.class);
        describe(TwoChild.class);
        describe(ContainerChild.class);
        describe(Implementation.class);

        System.out.println("parent direct single: "
                + (Parent.class.getDeclaredAnnotation(Label.class) != null));
        System.out.println("parent declared container: "
                + (Parent.class.getDeclaredAnnotation(Labels.class) != null));
        System.out.println("child inherited container: "
                + (Child.class.getAnnotation(Labels.class) != null));
        System.out.println("child declared container: "
                + (Child.class.getDeclaredAnnotation(Labels.class) != null));
    }
}
```

Compile with **Java 17** or a newer JDK:

```bash
javac --release 17 AnnotationByTypeDemo.java
java AnnotationByTypeDemo
```

**Exact output** when running the standalone program:

```text
Parent: all=[parent-a, parent-b] declared=[parent-a, parent-b]
Child: all=[parent-a, parent-b] declared=[]
OwnChild: all=[child] declared=[child]
TwoChild: all=[local-a, local-b] declared=[local-a, local-b]
ContainerChild: all=[explicit-a, explicit-b] declared=[explicit-a, explicit-b]
Implementation: all=[] declared=[]
parent direct single: false
parent declared container: true
child inherited container: true
child declared container: false
```

The `names` method sorts labels by name so the output is stable and easy to read, independent of how annotation order is presented in the example. When you need to preserve the appearance order of repeatable annotations, do not arbitrarily sort the results like this demo helper does.

### 4.1. Parent: both APIs return two annotations

`Parent` declares two `@Label`s itself. In runtime metadata, the compiler uses the `@Labels` container for the repeated set. Both `getAnnotationsByType(Label.class)` and `getDeclaredAnnotationsByType(Label.class)` unpack the container into two `Label`s. Thus both `all` and `declared` are `[parent-a, parent-b]`.

### 4.2. Child: only the API without Declared inherits

`Child extends Parent` but does not declare `@Label`. Because `Label` has `@Inherited`, the call:

```java
Child.class.getAnnotationsByType(Label.class)
```

returns the associated labels from the superclass: `[parent-a, parent-b]`.

Meanwhile:

```java
Child.class.getDeclaredAnnotationsByType(Label.class)
```

returns an **empty array**, because `Child` declares `Label` neither directly nor indirectly. The two APIs differ in **scope**, not in their ability to unpack containers.

### 4.3. OwnChild: local annotations do not merge with the superclass

`OwnChild` has `@Label("child")` directly. Because it already has a local `Label`, `getAnnotationsByType(Label.class)` returns `[child]`, **not** `[parent-a, parent-b, child]`. The declared method also returns `[child]`.

This is a practical difference from expectations that “annotations from all levels are all merged”. For **one repeatable annotation type**, the `@Inherited` rule of associated queries does not automatically add superclass annotations when the current class already has annotations of that type.

If business logic truly wants the set of annotations **merged from every class in the hierarchy**, you must walk `getSuperclass()` yourself and apply merging, conflict, and ordering policies as required by the application.

### 4.4. TwoChild: multiple local annotations

`TwoChild` declares two `@Label`s. Both APIs return the exact two local annotations; `Parent`'s labels are not added. `getDeclaredAnnotationsByType` returns both even though the class file contains a container rather than two separate `Label` annotations.

### 4.5. ContainerChild: explicit container declarations are also unpacked

`ContainerChild` writes directly:

```java
@Labels({@Label("explicit-a"), @Label("explicit-b")})
```

Each `Label` inside is considered *indirectly present* under repeatable rules. Both by-type APIs return `[explicit-a, explicit-b]`. Therefore, the source author does **not necessarily** have to use repeated `@Label` syntax; a valid container is also recognized.

### 4.6. Implementation: @Inherited does not traverse interfaces

`Contract` is an interface with `@Label("interface-only")`. `Implementation implements Contract` does **not** inherit annotations through interfaces under `@Inherited` rules. Therefore both queries on `Implementation.class` return empty arrays.

`@Inherited` only takes effect when looking up annotations on a **class**, following the appropriate superclass relationship; it does not turn interface annotations into default annotations for every implementing class.

### 4.7. Why does getDeclaredAnnotation(Label.class) on Parent return null?

The two `@Label`s on `Parent` are represented by the containing annotation `@Labels`. Consequently `Parent.class.getDeclaredAnnotation(Label.class)` does not see a single **directly present** `Label` annotation and returns `null`. However, `getDeclaredAnnotation(Labels.class)` returns the actual container, so it prints `true`.

`Child.class.getAnnotation(Labels.class)` is `true` because container `Labels` also has `@Inherited`, while `getDeclaredAnnotation(Labels.class)` on Child is `null`. It is the same phenomenon, applied to the **container annotation type**.

**Warning:** If you only call `getAnnotation(Label.class)` when a repeatable annotation appears twice, you may mistakenly think the annotation does not exist. Use `getAnnotationsByType(Label.class)` if you want all instances of a repeatable type.

## 5. Check retention before comparing the two APIs

Both `Label` and `Labels` in the program have `@Retention(RUNTIME)` so runtime Reflection sees the repeatable annotations. If an annotation lacks appropriate runtime retention, both `ByType` methods can return empty arrays; that is a metadata visibility error, not proof that one API handles containers differently from the other. Container declaration rules belong to the previous repeatable lesson.

## 6. Inheritance scope in the two `ByType` APIs

`getAnnotationsByType(T.class)` can look up to superclasses **when the element is a class**, annotation type `T` has `@Inherited`, and the current class has no direct/indirect annotation of type `T`. `getDeclaredAnnotationsByType(T.class)` is always restricted to the current element.

That does **not** make annotations from implemented interfaces, overridden methods, or hidden fields appear automatically on the new element. If `getMethod()` returns an original method declared on a superclass, the read annotations still belong to that `Method` itself. When a framework wants to merge across multiple classes/interfaces or a method hierarchy, it needs custom traversal and conflict-resolution policies.

## 7. Rules for choosing the API by goal

| Practical need | Appropriate API | Reason |
| --- | --- | --- |
| Read all effective `@Label`s on a class, including inherited per Java rules | `clazz.getAnnotationsByType(Label.class)` | Associated result, supports repeatable and `@Inherited` |
| Read only `@Label`s written on this class itself | `clazz.getDeclaredAnnotationsByType(Label.class)` | Does not walk up superclasses |
| Find all annotations of a repeatable type on the current method | `method.getDeclaredAnnotationsByType(Label.class)` or `getAnnotationsByType` depending on semantics | Does not auto-inherit annotations from overridden methods |
| Check if there is a **direct** annotation of type `T` | `getDeclaredAnnotation(T.class)` | Insufficient when repeatable is wrapped in a container |
| Inspect the physical container of a repeatable annotation | `getDeclaredAnnotation(Container.class)` | Inspects the declared container |
| Iterate all declared annotation metadata, including other types | `getDeclaredAnnotations()` | Returns the list of annotation metadata; does not replace by-type for unpacking |
| Want to merge annotations of **every class** in the inheritance chain, even when subclass has its own | Walk `getSuperclass()` manually and call `getDeclaredAnnotationsByType` | By-type associated rules do not auto-merge levels |
| Want to get annotations from interfaces or overridden methods under framework policy | Walk hierarchy manually and choose conflict rules | `@Inherited` does not satisfy this requirement |

### Pattern for reading local class metadata

```java
static Label[] localLabels(Class<?> clazz) {
    return clazz.getDeclaredAnnotationsByType(Label.class);
}
```

### Pattern for reading associated annotations

```java
static Label[] effectiveLabels(Class<?> clazz) {
    return clazz.getAnnotationsByType(Label.class);
}
```

These two snippets are illustrative Java methods that can be placed inside an appropriate class, using `Label` declared in the main example. Name them `localLabels` or `effectiveLabels` intentionally; a generic name like `findLabels` often leaves readers unsure whether the function includes inherited annotations.

## 8. If you want merged results from all superclasses, you must traverse manually

Many frameworks want to **combine** annotations from the current class and all superclasses, even when the current class has annotations of the same type. `getAnnotationsByType` does **not** fully satisfy this merging rule.

Example of a utility collecting local instances in order from subclass up to superclass:

```java
static java.util.List<Label> collectEveryLevel(Class<?> type) {
    java.util.List<Label> result = new java.util.ArrayList<>();

    for (Class<?> current = type;
         current != null;
         current = current.getSuperclass()) {

        Label[] local =
                current.getDeclaredAnnotationsByType(Label.class);
        java.util.Collections.addAll(result, local);
    }
    return result;
}
```

This is an **illustrative Java method** using the declared `Label`. Place it inside a class or application utility. For `OwnChild.class`, this utility collects `child`, `parent-a`, `parent-b` in level order and the order of annotations returned at each level.

Points to remember:

- This is a **custom application-defined rule**, not the default behavior of `getAnnotationsByType`.
- You may need deduplication, giving the subclass priority, allowing overrides, or merging annotation values according to the domain.
- The example above walks superclasses, **not** interfaces. Supporting interfaces requires separate logic, avoiding cycles in the interface graph, and deciding order.
- Do not call `getAnnotationsByType` at each level if you intend to merge directly: inherited annotations could be counted repeatedly across levels. `getDeclaredAnnotationsByType` is better suited to collect **only each level's metadata**.

## 9. How it differs from getDeclaredAnnotations()

When a `@Repeatable(Label)` exists, many people search using:

```java
for (Annotation a : clazz.getDeclaredAnnotations()) {
    System.out.println(a.annotationType());
}
```

If repeatable `Label` appears twice, the list may contain **`Labels`**, the container, rather than two flattened `Label` objects. On the other hand, `getDeclaredAnnotationsByType(Label.class)` is designed to return two `Label`s.

Therefore:

- If you want **all annotation metadata of any type**, `getDeclaredAnnotations()` makes sense.
- If you want **all instances of a specific repeatable type**, use `getDeclaredAnnotationsByType(T.class)`.
- If you want **all instances associated with a type, including valid inheritance**, use `getAnnotationsByType(T.class)`.

Similarly, `getAnnotations()` is the list of present annotations under that API's semantics, **not** a function that always flattens every repeatable container into its inner elements. Do not use `getAnnotations().length` to reliably infer the count of repeatable annotations.

## 10. Several easily misunderstood points

### 10.1. @Inherited is present yet the subclass still does not see the annotation

Check four things:

1. Does the annotation genuinely have `@Retention(RUNTIME)`?
2. Does the primary annotation type have `@Inherited`? If repeatable, is the container declared consistently?
3. Is the queried element truly a **class subclass** via `extends`, or does it merely `implements` an interface?
4. Does the subclass have a **local** annotation of the same type? If so, the by-type associated method returns the local set without adding the superclass set.

### 10.2. Multiple @Labels exist yet getAnnotation(Label.class) returns null

That is the expected situation when the compiler uses container `@Labels` for repeatable annotations. Using `getAnnotationsByType(Label.class)` or `getDeclaredAnnotationsByType(Label.class)` is the proper way to retrieve multiple instances.

### 10.3. Does lacking Declared mean always reading every ancestor?

**No.** `getAnnotationsByType` supports class `@Inherited` semantics, but when a local set of the same annotation type exists, it does not auto-merge superclass sets. Without `@Inherited`, it also does not automatically “scan the entire hierarchy” to return all annotations.

### 10.4. Does getDeclaredAnnotationsByType read only non-repeatable annotations?

**False.** It also supports repeatable annotations, including annotations **indirectly present** inside a container. “Declared” restricts **the element**, not **the number of annotations**.

### 10.5. Is adding @Inherited to the annotated class enough?

**False.** `@Inherited` is a meta-annotation for annotation type declarations, not a modifier you randomly add to `Child` to enable inheritance.

### 10.6. Does @Inherited apply to overriding methods?

**No.** Custom inheritance of method metadata is the job of frameworks. Java Reflection does not automatically copy annotations from superclass methods to overriding methods.

### 10.7. Depending on returned array order?

For repeatable annotations, local order can carry meaning according to the container/source. Define ordering rules if using results for a pipeline. The runnable example in section 4 **sorts** to produce stable stdout, which does not prove the JVM always returns arrays in lexicographical order.

### 10.8. If compiled with an annotation, must Reflection see it?

**No.** `SOURCE`/`CLASS` retention does not guarantee runtime Reflection sees the annotation. If the returned count is zero, check `@Retention(RUNTIME)` before concluding the API has a bug.

## 11. Notes when designing frameworks

A framework may need two different behaviors:

**Policy A — inherited, nearest class takes priority:** Call `getAnnotationsByType(T.class)` on the target class. This aligns closely with Java-defined associated annotation semantics; suitable when subclasses should be able to replace parent metadata with local values.

**Policy B — collect all levels:** Walk `getSuperclass()` and call `getDeclaredAnnotationsByType(T.class)` on each class. This is an independent framework policy; merge, order, and override rules must be explicitly decided.

If annotations sit on methods or interfaces and a framework wants custom inheritance (e.g., reading route annotations on interfaces), write a specialized traversal algorithm. Do not expect `@Inherited` or `getAnnotationsByType` to do that for every element.

What counts as an “effective annotation” in some frameworks such as dependency injection or web routing tools can have semantics **different** from standard Java Reflection (searching meta-annotations, composed annotations, aliases, multiple levels). When exact framework behavior is needed, use the framework's API; when exact Java Reflection rules are needed, rely on `AnnotatedElement` and `@Inherited`.

## 12. Self-check

**Question 1.** On a class with two `@Label`s, does `getDeclaredAnnotationsByType(Label.class)` return both?

**Answer:** Yes. The API expands the repeatable container to retrieve annotations indirectly present on the class itself.

**Question 2.** `Child extends Parent` does not declare `Label`, and `Label` has `@Inherited`. What do the two APIs return?

**Answer:** `Child.class.getAnnotationsByType(Label.class)` can return the `Label`s from Parent; `Child.class.getDeclaredAnnotationsByType(Label.class)` returns empty.

**Question 3.** If `Child` declares a `@Label("child")` itself, does `getAnnotationsByType` also return the Labels on Parent?

**Answer:** Does not auto-merge. Child's local set takes priority for that annotation type.

**Question 4.** Why can `getDeclaredAnnotation(Label.class)` on Parent with two `@Label`s return null?

**Answer:** The compiler represents repeated annotations via the containing annotation `Labels`; `getDeclaredAnnotation` is not an API that flattens multiple repeatable annotations.

**Question 5.** Does `Implementation implements Contract` automatically receive `@Label` from interface `Contract` via `@Inherited`?

**Answer:** No. `@Inherited` does not propagate annotations across `implements`.

**Question 6.** Does an overriding method automatically inherit superclass method annotations when calling `getAnnotationsByType` on the child `Method`?

**Answer:** No. Java Reflection's `@Inherited` rule applies to classes, not transferring parent method annotations to overriding methods.

**Question 7.** Why can both by-type APIs return empty arrays even when annotations exist in source code?

**Answer:** The annotation may lack `@Retention(RUNTIME)`, the wrong element/type may be queried, the subclass may lack local annotations while the annotation lacks `@Inherited`, or it may exist only on another interface/method.

**Question 8.** To retrieve all `Label`s on both Child and Parent, even when Child has declared its own, what should be used?

**Answer:** Walk the hierarchy via `getSuperclass()` and call `getDeclaredAnnotationsByType(Label.class)` at each level, then apply the application's combining rules.

**Key takeaway:** **Both `getAnnotationsByType` and `getDeclaredAnnotationsByType` understand repeatable annotations**. The API with `Declared` returns only annotations directly or indirectly **on the element itself**; the API without `Declared` can apply **`@Inherited` along superclasses when querying a class**, but **does not merge by default** the local annotation set with sets on all superclasses. If merging under another policy is desired, walk the hierarchy intentionally.