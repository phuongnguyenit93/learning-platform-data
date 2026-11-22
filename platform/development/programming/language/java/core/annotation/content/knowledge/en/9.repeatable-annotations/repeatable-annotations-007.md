# Element Ordering and Lookup Behavior for Repeatable Annotations in Java

## 1. The Problem: The Same Annotation Appearing Multiple Times

Since Java 8, Java supports **repeatable annotations**: an annotation type is allowed to appear multiple times at the same declaration or type-use site. For example, an endpoint with multiple access permissions:

```java
@Role("READ")
@Role("WRITE")
@Role("AUDIT")
class DocumentService {}
```

The snippet above is valid only when `Role` has been defined as a **repeatable** annotation, through the `@Repeatable` meta-annotation together with a **containing** annotation (*containing annotation type*, commonly called a *container*).

Learners need to distinguish three things:

1. **Ordering:** the `@Role` annotations are declared in the order `READ`, `WRITE`, `AUDIT`. When retrieving them with the API for repeatable annotations, the order is preserved.
2. **How Java represents them:** in the class file, multiple repeatable annotations of the same type are typically represented indirectly by a container annotation holding an array of the constituent annotations.
3. **How they are looked up:** `getAnnotation(Role.class)` and `getAnnotationsByType(Role.class)` are **not equivalent**. When multiple `Role` annotations are grouped into `Roles`, a single-annotation lookup may return `null` even though the annotations are actually indirectly present.

“Element ordering” in this article refers to **the order of the repeatable annotations in the resulting array** and the container elements. It is not an automatic task execution order. Java only stores metadata; a framework that wants to run `READ` before `WRITE` must itself define and execute how metadata is processed in that order.

## 2. Properly Declaring a Repeatable Annotation and Its Container

The two related annotation types are typically defined as follows (this snippet consists of **supporting declarations** and does not yet include a `main` method):

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

Meaning:

- `Role` is the **repeatable annotation type**. `@Repeatable(Roles.class)` specifies the annotation that holds the occurrences of `Role`.
- `Roles` is the **container annotation type**. It must have an element named exactly `value()`, and that element must return `Role[]`. The example above has no other elements; if any exist, those additional elements must satisfy the mandatory default-value rules of the container.
- `@Retention(RUNTIME)` allows `Role` and `Roles` to be read via reflection. If `@Retention` is not declared, the default is `RetentionPolicy.CLASS`; in that case, standard reflection cannot read the annotations on the class at runtime.
- `@Target(TYPE)` restricts the annotation to valid type declaration sites. The container and the repeatable annotation must have compatible target configurations; the container cannot be inapplicable at a site where the constituent annotation is permitted to repeat.
- The `@Repeatable` declaration can be strictly checked by the compiler for compatibility between the two types, including retention and related meta-annotations. An incompatible container cannot be paired arbitrarily.

When used:

```java
@Role("READ")
@Role("WRITE")
@Role("AUDIT")
class DocumentService {}
```

we can visualize the equivalent container form in terms of `Role` values:

```java
@Roles({
    @Role("READ"),
    @Role("WRITE"),
    @Role("AUDIT")
})
class DocumentService {}
```

**Note:** the two blocks above are **two alternative ways of writing it for illustration**, and do not appear together on one `DocumentService` declaration in the same program. The repeated source declaration form is processed by the compiler to represent the constituent annotations through the container; using the appropriate lookup API determines whether the individual components are visible.

## 3. Order Preservation When Looking Up Repeatable Annotations

Suppose a class declares:

```java
@Role("first")
@Role("second")
@Role("third")
class Pipeline {}
```

With the `Role` annotation having `RUNTIME` retention, the result:

```java
Role[] roles = Pipeline.class.getAnnotationsByType(Role.class);
```

is an array with three elements in declaration order:

| Array index | Value of `roles[index].value()` |
| --- | --- |
| `0` | `"first"` |
| `1` | `"second"` |
| `2` | `"third"` |

Important rule: when multiple annotations of the same type are **indirectly present through a container**, the order in the container's `value()` array reflects the order of the annotations of that same type in the source. The `getDeclaredAnnotationsByType` and `getAnnotationsByType` APIs return results of that same type in that corresponding order.

If the author writes the container **explicitly**:

```java
@Roles({
    @Role("third"),
    @Role("first"),
    @Role("second")
})
class OtherPipeline {}
```

then `getAnnotationsByType(Role.class)` receives the elements in the order **`third` → `first` → `second`**, because that is the array order inside the explicit container.

You should not infer that the order of **different annotation types** is always guaranteed by `getAnnotations()` or `getDeclaredAnnotations()`. These two APIs return an array of annotations looked up according to their respective rules, but the ordering across different annotation types is not a contract to rely on. For a set of repeatable annotations of the same type, use `getAnnotationsByType(Role.class)` and rely on the order of the returned components.

A subtle case: `Role` annotations may appear interleaved with other annotations. The relative order among the `Role` occurrences is still preserved when they are represented in the container, but **the position of the container relative to other annotations** does not mean they must be processed interleaved in the exact order of every annotation line in the source.

## 4. Lookup APIs: How Do They Differ?

Reflection defines key APIs on `AnnotatedElement`. `Class`, `Method`, `Field`, `Constructor`, `Parameter`, along with several other reflective types, provide these APIs (exact support depends on the target).

| API | Behavior for repeatable annotations |
| --- | --- |
| `getAnnotation(Role.class)` | Looks up **a single `Role` annotation** that is directly present or present under applicable inheritance rules; does not automatically unwrap the container to return individual indirectly present `Role` annotations. May return `null` when only `@Roles(...)` is present. |
| `getDeclaredAnnotation(Role.class)` | Looks up only a `Role` annotation **directly declared** on the element, without applying inheritance; does not unwrap the container. |
| `getAnnotationsByType(Role.class)` | Finds all `Role` annotations **directly present or indirectly present via a container**; for `Class`, also applies the appropriate `@Inherited` rules if no annotation of that type is present on the current class. |
| `getDeclaredAnnotationsByType(Role.class)` | Finds `Role` annotations directly or indirectly **declared on that exact element**, without searching superclasses. |
| `getAnnotation(Roles.class)` | Looks up the container annotation `Roles` (if it is present under the applicable rules), on which `value()` can then be called to obtain the `Role[]` array. |
| `getAnnotations()` / `getDeclaredAnnotations()` | Lists the corresponding runtime annotations; typically sees the **`Roles` container** when multiple `Role` annotations repeat, rather than individual `Role` annotations “unpacked” separately. |

**Most common pitfall:** `getAnnotation(Role.class) == null` is not enough to conclude “there is no `Role`” on the element if `Role` is repeatable. Multiple `Role` annotations may exist through `Roles`. If the goal is to collect all repeatable annotations, use **`getAnnotationsByType(Role.class)`** or **`getDeclaredAnnotationsByType(Role.class)`**, depending on whether inheritance needs to be considered.

Comparative examples:

- Case with only one `@Role("ADMIN")`: there can be a **direct `Role`**, so `getAnnotation(Role.class)` returns `Role` and `getAnnotationsByType(Role.class)` returns a single-element array.
- Case with multiple `@Role` annotations: the compiler uses the **`Roles` container**, so `getAnnotation(Role.class)` typically returns `null`, whereas `getAnnotationsByType(Role.class)` returns all components.
- Case where `@Roles({@Role("A"), @Role("B")})` is written directly: similarly, `Role` is indirectly inside the container, and the `ByType` API returns both components.
- `getAnnotation(Roles.class)` can return the container in the latter two cases, but consumers should not be forced to know the container's name if they only need the `Role` values. The `ByType` API covers both the single direct annotation case and the multiple indirect annotations case.

## 5. Complete Java 17+ Example: Ordering, Container, and Inheritance Lookup

This example uses both the repeated `@Role` form and the explicit `@Roles` form, a single annotation, as well as a superclass/subclass hierarchy to verify the APIs and ordering.

Save the complete program to the file **`RepeatableLookupDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.List;

@Inherited
@Repeatable(Roles.class)
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Role {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Roles {
    Role[] value();
}

@Role("read")
@Role("write")
@Role("audit")
class RepeatedService {}

@Roles({@Role("alpha"), @Role("beta")})
class ExplicitContainer {}

@Role("owner")
class SingleRole {}

@Role("parent-a")
@Role("parent-b")
class ParentService {}

class InheritingChild extends ParentService {}

@Role("child-only")
class OwnRoleChild extends ParentService {}

public class RepeatableLookupDemo {
    private static List<String> values(Role[] annotations) {
        return Arrays.stream(annotations).map(Role::value).toList();
    }

    public static void main(String[] args) {
        System.out.println("Repeated by type: "
                + values(RepeatedService.class.getAnnotationsByType(Role.class)));
        System.out.println("Repeated singular: "
                + RepeatedService.class.getAnnotation(Role.class));

        Roles container = RepeatedService.class.getAnnotation(Roles.class);
        System.out.println("Repeated container: " + values(container.value()));

        System.out.println("Repeated raw type: "
                + RepeatedService.class.getDeclaredAnnotations()[0]
                    .annotationType().getSimpleName());

        System.out.println("Explicit container: "
                + values(ExplicitContainer.class.getAnnotationsByType(Role.class)));

        System.out.println("Single by type: "
                + values(SingleRole.class.getAnnotationsByType(Role.class)));
        System.out.println("Single singular: "
                + SingleRole.class.getAnnotation(Role.class).value());

        System.out.println("Child inherited: "
                + values(InheritingChild.class.getAnnotationsByType(Role.class)));
        System.out.println("Child declared: "
                + values(InheritingChild.class.getDeclaredAnnotationsByType(Role.class)));
        System.out.println("Child own role: "
                + values(OwnRoleChild.class.getAnnotationsByType(Role.class)));
    }
}
```

In the directory containing the file, use **JDK 17 or later**:

```bash
javac --release 17 RepeatableLookupDemo.java
java RepeatableLookupDemo
```

**Expected stdout:**

```text
Repeated by type: [read, write, audit]
Repeated singular: null
Repeated container: [read, write, audit]
Repeated raw type: Roles
Explicit container: [alpha, beta]
Single by type: [owner]
Single singular: owner
Child inherited: [parent-a, parent-b]
Child declared: []
Child own role: [child-only]
```

How to read the lines:

1. The three `@Role` annotations on `RepeatedService` appear in the exact order `read`, `write`, `audit` in the `getAnnotationsByType(Role.class)` array.
2. `getAnnotation(Role.class)` returns `null` because `RepeatedService` has `Role` annotations **indirectly present** inside a container rather than a single directly present `Role`.
3. `getAnnotation(Roles.class).value()` gives the three elements in the same order, proving that the container stores the constituent annotations.
4. `getDeclaredAnnotations()[0].annotationType().getSimpleName()` prints `Roles`: for `RepeatedService`, the annotation directly declared at runtime is the container.
5. `ExplicitContainer` writes the container explicitly, so `ByType` also returns the elements in the order `alpha`, `beta`.
6. `SingleRole` has one direct annotation; both `getAnnotation` and `getAnnotationsByType` find it.
7. `InheritingChild` does not declare `Role` or `Roles` itself, but `@Inherited` on both annotation types allows `getAnnotationsByType` to see the two annotations from `ParentService`. `getDeclaredAnnotationsByType` inspects only the child itself, so it returns `[]`.
8. `OwnRoleChild` declares `@Role("child-only")`. The value on the child **does not accumulate** with the two roles on the superclass when looking up with `getAnnotationsByType`; the returned array contains only `child-only`.

If you change the order of the three `@Role` lines on `RepeatedService` and recompile, the order of the three printed strings on the two corresponding lines changes accordingly.

## 6. Important Details of @Inherited with Repeatable Annotations

`@Inherited` relates only to how annotations on a **class declaration are looked up via superclasses**. It does not cause annotations on an interface to be automatically inherited by implementing classes, nor does it cause annotations on methods to be inherited in the same way.

With repeatable annotations, you need to pay attention to both the **constituent annotation** and the **container**:

```java
@Inherited
@Repeatable(Roles.class)
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Role {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Roles {
    Role[] value();
}
```

In this example, both `Role` and `Roles` have `@Inherited`. When a repeatable annotation is marked with `@Inherited`, Java requires the corresponding container to also have `@Inherited` for the two types to have a valid relationship.

For `Class.getAnnotationsByType(Role.class)`:

1. If the subclass **directly** has a `Role` or **indirectly** has `Role` annotations via a container, the result comes from the **subclass**.
2. Only when the subclass **has no** `Role` in either of the two ways above and `Role` has `@Inherited` does the API look up from the appropriate superclass.
3. If the subclass declares no annotation of its own, the order of the inherited `Role` annotations reflects the order obtained from the superclass.
4. `getDeclaredAnnotationsByType(Role.class)` is always limited to annotations declared on the subclass itself, so it does not include inherited elements.

This distinction impacts configuration design: if you want the subclass's set of roles to **accumulate** with the superclass's, you should not assume that `getAnnotationsByType` automatically merges them. You must read the superclass chain yourself and define the merge/override rules according to your business logic.

You should also not confuse “container inheritance” behavior with `getAnnotation(Role.class)` automatically unwrapping the container. `getAnnotation` still applies single-annotation lookup semantics; to retrieve all repeatable components, prefer `getAnnotationsByType`.

## 7. Is Repeatable Annotation Order the Execution Order?

**Not by default.** Java preserves the order of the components so that programs can read the metadata, but annotations themselves do not execute code. For example:

```java
@Rule(step = 2, name = "verify")
@Rule(step = 1, name = "load")
class ImportWorkflow {}
```

If `Rule` is repeatable and a library reads it via `getAnnotationsByType(Rule.class)`, the array order by declaration position will be `verify` and then `load`. However, if the library author wants execution to follow the `step` attribute, they must **actively sort by `step`**, in which case the processing order can be `load` and then `verify`. These two policies are different; there is no Java rule forcing every framework to execute annotations in textual order.

When ordering **carries business meaning**, it must be designed clearly:

- If you want to preserve declaration order: use `getAnnotationsByType` or `getDeclaredAnnotationsByType`, iterate over the array in ascending index order, and document that source order is the processing order.
- If you want an order invariant to someone moving annotation lines around: add an explicit element such as `int priority()` or `int order()` and sort using a comparator according to the contract.
- If you must process multiple different annotation types interleaved together, do not rely on the array order of `getDeclaredAnnotations()` to reconstruct source line order across types. A unified metadata representation or dedicated processing logic is needed.
- If there are annotations inherited from a superclass, clearly specify whether inheritance **replaces**, **accumulates**, or **prioritizes the subclass**. `getAnnotationsByType` has Java's own rules and does not satisfy every application policy by default.

## 8. Common Mistakes and Pitfalls

### 8.1. Calling Only getAnnotation for a Repeatable Annotation

```java
Role role = RepeatedService.class.getAnnotation(Role.class);
```

In the example with multiple `@Role` annotations, `role` is `null`. Calling `role.value()` immediately will cause a `NullPointerException`. Fix it with:

```java
Role[] roles = RepeatedService.class.getAnnotationsByType(Role.class);
for (Role role : roles) {
    System.out.println(role.value());
}
```

The snippets in this section are illustrative code using the types defined in the full program.

### 8.2. Forgetting Runtime Retention

`@Repeatable` does not automatically set `@Retention(RUNTIME)`. If `Role` and `Roles` are defined with the default `CLASS` retention, Java reflection does not provide those annotations through the runtime APIs discussed here. For tools that operate only at compile time or perform bytecode analysis, a different retention can be used, but the proper reading mechanism must be chosen.

### 8.3. Container Declaring the Wrong Element

```java
@Repeatable(Roles.class)
@interface Role {
    String value();
}

@interface Roles {
    String[] value(); // Wrong: must be Role[]
}
```

This is an **intentionally invalid** example; `javac` does not accept the container because the `value()` element does not return the constituent annotation array `Role[]`. Beyond this array type, the compiler also checks applicability, retention, and related properties of the annotation/container pair.

### 8.4. Using getDeclaredAnnotations and Casting to Role

When multiple `@Role` annotations are grouped into `@Roles`, the element returned by `getDeclaredAnnotations()` may be a **`Roles`**, not a `Role`. An incorrect direct cast can cause a `ClassCastException`. Use `getDeclaredAnnotationsByType(Role.class)` to properly read the constituent elements.

### 8.5. Confusing Annotation Order with Element Order

For example, the container `@Roles({@Role("A"), @Role("B")})` has **two array elements** whose order matters. Within a single annotation, element-value pairs such as `@Config(name = "A", level = 2)` and `@Config(level = 2, name = "A")` represent the same assigned values; Java does not assign any sequential execution meaning to the order in which those attribute pairs are written.

### 8.6. Assuming Superclass and Subclass Always Accumulate

If the parent class has `@Role("base")` and the child class has `@Role("child")`, `getAnnotationsByType(Role.class)` on the child class prioritizes the annotation present on the child class. It does not automatically return `[base, child]`. If you want merging behavior, define a custom rule and traverse inheritance explicitly.

### 8.7. Thinking an Annotation Appears Only Once When a Container Is Present

The container holds an **array value** consisting of multiple constituent annotations; seeing a single annotation when reflecting on the container does not mean the constituent data has been lost. The `ByType` API provides the appropriate view for properly reading multiple values.

## 9. How to Verify with javap and Reflection

You can use a JDK tool to inspect the bytecode after compiling the example:

```bash
javap -v RepeatedService
```

For definitions with `RUNTIME` retention, the annotation metadata section in the class file will contain information about the `Roles` container and the constituent `Role` annotations in array order. The detailed output lines of `javap -v` can vary across JDK versions, so no fixed stdout is provided for this command. When you only need the runtime values with the right type and order, the `getAnnotationsByType` example above is a more direct and clearer way to test.

To inspect a real library:

1. Read the repeatable annotation definition: `@Repeatable(Container.class)`, `@Retention`, `@Target`, and `@Inherited` if present.
2. Create fixtures with a single annotation, multiple annotations, and an explicit container; test `getAnnotation` and `getAnnotationsByType` on each fixture.
3. Try different declaration orders and confirm that the `ByType` array preserves that exact order.
4. If inheritance is supported, test a subclass with no declared annotation and a subclass with its own declared annotation.
5. If metadata dictates business ordering, confirm that the consuming code uses the **array order** properly or sorts by an `order` element as specified by the contract.

**Key takeaway:** For repeatable annotations, the order of constituent annotations of the same type is preserved in both the container and the lookup array. `getAnnotation(T.class)` handles only single-annotation lookup and may return `null` when `T` annotations reside indirectly inside a container; **`getAnnotationsByType(T.class)`** is the primary API for collecting all values. `@Inherited` rules affect whether superclasses are searched, while business processing order is a decision left to the code consuming the annotations.
