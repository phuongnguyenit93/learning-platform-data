# `getAnnotations()` vs. `getDeclaredAnnotations()`

When reading annotations via Reflection, you need to determine two things: **which element's annotations are being queried** and **whether inherited annotations are accepted**. Both methods return `Annotation[]`, yet they answer two different questions. The difference is easiest to see when the element under inspection is a class with a superclass.

For example, a superclass may carry a shared policy while a subclass declares no policy of its own. A configuration checker may want the effective policy applying to the subclass; a source analysis tool may want only what the subclass itself declares. Choosing the wrong method causes the two tools to interpret the same class differently.

## 1. Meaning and conditions for seeing annotations

| Method | Question to answer | Result when no annotation exists |
| --- | --- | --- |
| `getDeclaredAnnotations()` | Which directly present annotations does this element have? | Empty array |
| `getAnnotations()` | Which present annotations does this element have, including inherited ones when rules allow? | Empty array |

For `Class<?>`, `getDeclaredAnnotations()` ignores inherited annotations. `getAnnotations()` can include annotations from a superclass; it does not simply collect every annotation in the type hierarchy. This is the semantics of [the `Class` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getAnnotations()).

**`Declared` refers to where the annotation is declared, not access visibility.** It does not mean returning only `private` annotations, nor returning extra hidden annotations. Nor do these two APIs list the annotations of all methods, fields, and parameters inside a class. To read a method's annotations, you must have the corresponding `Method` object.

The general requirement is that the annotation must be retained at runtime via `@Retention(RetentionPolicy.RUNTIME)`. `SOURCE` is discarded at compile time; `CLASS` is not exposed through these Reflection APIs. [Annotation retention policies](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/RetentionPolicy.html) govern that behavior.

If `@Retention` is not declared, the default policy is `CLASS`, not `RUNTIME`. Therefore, seeing `@SomeAnnotation` in source code does not prove Reflection will find it. See [the default rule of `@Retention`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/Retention.html).

## 2. How does annotation inheritance on classes work?

For an annotation on a superclass to be considered for a subclass, the **annotation type** must be marked with `@Inherited`. This marker is placed on the `@interface` declaration, not placed on a subclass to ask it to automatically receive all annotations.

For a non-repeatable annotation type, the lookup process can be pictured as follows:

1. If the current class declares that annotation, use the value on the current class.
2. If not, and the annotation type has `@Inherited`, inspect the direct superclass.
3. Continue up the superclass chain until found or until no superclass remains.

This mechanism walks only **superclasses**; it does not pull annotations from implemented interfaces. Nor does it automatically propagate annotations on methods, fields, or constructors down to other members. [The `@Inherited` specification](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/Inherited.html) limits the scope in this way.

For instance, if `Parent` has `@Policy("parent")`, then `Child extends Parent` can receive that policy when `Policy` has `@Inherited`. If `Child` declares `@Policy("child")` itself, querying `Policy` selects the policy on `Child`; it does not also return `"parent"` as a second list entry.

## 3. Full experiment on Java 17+

The following program puts the cases side by side: regular annotations, `@Inherited` annotations, interfaces, inherited methods, overridden methods, and repeatable annotations.

Save the entire file to **`AnnotationLookupDemo.java`**:

```java
import java.lang.annotation.Annotation;
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.Arrays;

public class AnnotationLookupDemo {
    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    public @interface Policy {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    public @interface LocalTag {
    }

    @Policy("parent")
    @LocalTag
    public static class Parent {
        @Policy("method-parent")
        public void work() {
        }
    }

    public static class Child extends Parent {
    }

    @Policy("child")
    public static class OwnPolicy extends Parent {
    }

    @Policy("interface")
    public interface Contract {
    }

    public static class Impl implements Contract {
    }

    public static class Overrides extends Parent {
        @Override
        public void work() {
        }
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

    @Label("red")
    @Label("blue")
    public static class Tagged {
    }

    public static class TaggedChild extends Tagged {
    }

    @Label("green")
    public static class OwnTagged extends Tagged {
    }

    private static String names(Annotation[] annotations) {
        return Arrays.stream(annotations)
                .map(a -> a.annotationType().getSimpleName())
                .sorted()
                .toList()
                .toString();
    }

    private static String labels(Label[] annotations) {
        return Arrays.stream(annotations)
                .map(Label::value)
                .toList()
                .toString();
    }

    private static void show(Class<?> type) {
        System.out.println(type.getSimpleName() + " annotations = "
                + names(type.getAnnotations()));
        System.out.println(type.getSimpleName() + " declared = "
                + names(type.getDeclaredAnnotations()));
    }

    public static void main(String[] args) throws NoSuchMethodException {
        show(Parent.class);
        show(Child.class);
        show(OwnPolicy.class);
        System.out.println("Child policy = "
                + Child.class.getAnnotation(Policy.class).value());
        System.out.println("OwnPolicy policy = "
                + OwnPolicy.class.getAnnotation(Policy.class).value());
        System.out.println("Impl annotations = "
                + names(Impl.class.getAnnotations()));

        Method inherited = Child.class.getMethod("work");
        Method overridden = Overrides.class.getMethod("work");
        System.out.println("Child.work declaring = "
                + inherited.getDeclaringClass().getSimpleName());
        System.out.println("Child.work annotations = "
                + names(inherited.getAnnotations()));
        System.out.println("Child.work declared = "
                + names(inherited.getDeclaredAnnotations()));
        System.out.println("Overrides.work annotations = "
                + names(overridden.getAnnotations()));
        System.out.println("Overrides.work declared = "
                + names(overridden.getDeclaredAnnotations()));

        show(Tagged.class);
        System.out.println("Tagged getAnnotation(Label) = "
                + Tagged.class.getAnnotation(Label.class));
        System.out.println("Tagged labels = "
                + labels(Tagged.class.getAnnotationsByType(Label.class)));
        System.out.println("TaggedChild declared = "
                + names(TaggedChild.class.getDeclaredAnnotations()));
        System.out.println("TaggedChild labels = "
                + labels(TaggedChild.class.getAnnotationsByType(Label.class)));
        System.out.println("TaggedChild declared labels = "
                + labels(TaggedChild.class.getDeclaredAnnotationsByType(Label.class)));
        System.out.println("OwnTagged labels = "
                + labels(OwnTagged.class.getAnnotationsByType(Label.class)));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 --release 17 AnnotationLookupDemo.java
java AnnotationLookupDemo
```

Result:

```text
Parent annotations = [LocalTag, Policy]
Parent declared = [LocalTag, Policy]
Child annotations = [Policy]
Child declared = []
OwnPolicy annotations = [Policy]
OwnPolicy declared = [Policy]
Child policy = parent
OwnPolicy policy = child
Impl annotations = []
Child.work declaring = Parent
Child.work annotations = [Policy]
Child.work declared = [Policy]
Overrides.work annotations = []
Overrides.work declared = []
Tagged annotations = [Labels]
Tagged declared = [Labels]
Tagged getAnnotation(Label) = null
Tagged labels = [red, blue]
TaggedChild declared = []
TaggedChild labels = [red, blue]
TaggedChild declared labels = []
OwnTagged labels = [green]
```

The `names()` method intentionally sorts annotation names so the output is easy to compare. Do not use position in the annotation array as a precedence rule. The `labels()` method preserves the order of read values to observe the repeatable annotation case.

## 4. Interpreting the results on classes

### Superclass and subclass with no own declaration

`Parent` directly carries `LocalTag` and `Policy`, so both calls see both annotations.

`Child` declares no annotations, so `getDeclaredAnnotations()` produces `[]`. Even so, `getAnnotations()` still sees `Policy` because this annotation type has `@Inherited`. `LocalTag` lacks that marker, so it does not appear when querying `Child`.

What must be distinguished is **annotations found when querying** versus **annotations declared directly**. `Child` does not have an `@Policy` declaration injected into its source code just because `getAnnotations()` finds it via the superclass.

### Subclass declaring its own policy

`OwnPolicy` directly declares `@Policy("child")`. The result of `getAnnotation(Policy.class).value()` is `"child"`; whereas `Child` receives `"parent"`.

You can use this difference to choose between two application rules:

- Read configuration applied under Java inheritance: query without `Declared`.
- Accept only configuration declared on the current class: query with `Declared`.

If you need to know which class an annotation originated from, the returned array does not carry the search path. Your tool needs to check direct declarations on each class in the superclass chain rather than guessing from array order.

### Interfaces do not pass annotations to implementing classes

`Contract` has `@Policy("interface")`, yet `Impl.class.getAnnotations()` still returns an empty array. `@Inherited` on `Policy` does not change that.

If an application wants to apply policies from interfaces, that must be a rule designed by the application itself: which interfaces to traverse, how to handle multiple interfaces, and how to resolve conflicts. That rule must not be treated as the default behavior of `Class.getAnnotations()`.

## 5. An inherited method is not an inherited annotation

This is the easiest place in the example to draw the wrong inference.

`Child.class.getMethod("work")` finds the public method declared by `Parent`. The returned `Method` object still represents **`Parent.work`**, shown by `getDeclaringClass()` printing `Parent`. Because that method itself directly carries `@Policy`, both its `getAnnotations()` and `getDeclaredAnnotations()` see `Policy`.

Conversely, `Overrides` declares a new `work()` method to override it. That method does not carry `@Policy`, so both calls yield `[]`. `@Override` present in source code does not appear in the output because it is not retained at runtime.

Therefore, you cannot conclude that method annotations automatically propagate downward just because you found an annotation when calling `Child.class.getMethod(...)`. First check **which declaration the `Method` object represents**. This meaning ties directly to [the `Method.getDeclaringClass()` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html#getDeclaringClass()).

For a standard `Method` object, `getAnnotations()` and `getDeclaredAnnotations()` both inspect the direct annotations on the represented method; they do not automatically merge annotations from overridden methods in a superclass.

## 6. Repeatable annotations: why does the container appear?

`Label` is marked `@Repeatable(Labels.class)`, where `Labels` is a container annotation type holding `Label[]`. When `Tagged` has two `@Label`s, the compiler represents them via the container annotation `Labels`. [The role of `@Repeatable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/Repeatable.html) is to link the repeatable type with the container type.

The experiment's results are therefore:

- `getDeclaredAnnotations()` sees `[Labels]`, not two separate `Label` elements.
- `getAnnotations()` on `Tagged` also sees `[Labels]`.
- `getAnnotation(Label.class)` gives `null` when two `Label`s are inside the container.
- `getAnnotationsByType(Label.class)` gives the two values `red`, `blue`.

In API terminology, the container is **directly present**; the repeated annotations inside are **indirectly present**. The two plural methods without `ByType` do not automatically unpack the container into child elements. Choose `...AnnotationsByType(Label.class)` when you need the logical `Label` list. See [the semantics of `AnnotatedElement`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedElement.html).

In the program, both `Label` and `Labels` have `@Inherited` and `RUNTIME`. The container type must obey the corresponding constraints, including having `@Inherited` when the repeatable type has this marker; that is a requirement specified for [repeatable annotations and container types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.6.3).

Observe the two subclasses:

- `TaggedChild` does not declare `Label`: `getAnnotationsByType(Label.class)` receives `[red, blue]`, while `getDeclaredAnnotationsByType(Label.class)` produces `[]`.
- `OwnTagged` has one `@Label("green")`: querying `getAnnotationsByType(Label.class)` produces `[green]`, rather than appending to `[red, blue]` from the superclass.

Thus, “retrieving with inheritance” does not mean “accumulating every value across the entire class tree”. In particular, do not infer repeatable annotation rules from the result of `getAnnotations()`; use the API typed for the annotation you want to read.

## 7. Choosing the right API for your use case

| What do you need? | Appropriate API |
| --- | --- |
| List direct annotations on an element | `getDeclaredAnnotations()` |
| List present annotations, accounting for valid class inheritance | `getAnnotations()` |
| Get a specific annotation directly on an element | `getDeclaredAnnotation(MyAnnotation.class)` |
| Get a specific annotation, accounting for valid inheritance | `getAnnotation(MyAnnotation.class)` |
| Get repeatable annotations of a type only on the current element | `getDeclaredAnnotationsByType(MyAnnotation.class)` |
| Get repeatable annotations of a type, accounting for valid inheritance | `getAnnotationsByType(MyAnnotation.class)` |

The array-returning group yields an empty array when there are no results; the single-annotation group yields `null`. Once you know the target type, querying by type avoids iterating and comparing annotation names as strings.

`isAnnotationPresent(MyAnnotation.class)` corresponds to checking `getAnnotation(MyAnnotation.class) != null`. Therefore, do not use it to conclude that a repeatable annotation definitely does not exist when multiple elements are represented via a container; check `getAnnotationsByType(...)` in that case.

## 8. Common mistakes and how to self-check

| Wrong inference | Correct check |
| --- | --- |
| `getAnnotations()` gets every annotation from the superclass | Check `@Inherited` on each annotation type |
| Having `@Inherited` automatically inherits annotations from interfaces | Check the class inheritance path; interfaces are outside this mechanism |
| `Declared` relates to `public` or `private` | Identify the element that actually declares the annotation |
| Overriding methods receive the parent method's annotations | Check annotations on the overriding declaration itself |
| Finding a method through a subclass means the `Method` belongs to the subclass | Read `Method.getDeclaringClass()` |
| Seeing an annotation in source code means Reflection can read it | Check `@Retention(RUNTIME)` |
| Each `@Label` is always an element in `Annotation[]` | Check the container and use the `ByType` APIs |
| Annotations on an annotation are automatically merged onto the target class | Distinguish the queried element; the API does not automatically traverse all meta-annotations |

To verify this lesson yourself, tweak one small detail in the experiment at a time and predict the output before running:

1. Remove `@Inherited` from `Policy`: does `Child` still see `Policy`?
2. Add `@Policy("own-method")` on `Overrides.work()`: what do both APIs on the method return?
3. Switch `LocalTag` to `RetentionPolicy.CLASS`: does `Parent` still list it?
4. Keep only one `@Label` on `Tagged`: why can the single-annotation query result differ from the two-`@Label` case?

When a change causes an annotation to no longer be present, check for `null` before calling `.value()` on a single-lookup result. If you remove `@Inherited` from `Policy` while keeping the call `Child.class.getAnnotation(Policy.class).value()`, the program will throw `NullPointerException` on that call.

The key points to grasp are **declaration scope**, **inheritance rules**, and **how repeatable annotations are represented**. Determining all three factors before choosing a Reflection method will ensure query results have clear meaning.