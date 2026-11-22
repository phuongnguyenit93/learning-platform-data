# Marker Annotations and Syntax Without Elements in Java

## 1. What Is a Marker Annotation?

A **marker annotation** is an annotation type that **declares no annotation elements**. It uses the **presence or absence** of the annotation to mark a declaration, rather than carrying separate parameters such as a name, count, or configuration.

The simplest declaration:

~~~java
@interface Reviewed {
}
~~~

Here:

- `@interface` creates an **annotation type**, which differs from a regular `interface`.
- `Reviewed` is the annotation type name.
- The curly braces `{}` are empty because the annotation does not declare any elements, such as `String value();` or `int level();`.
- The name `Reviewed` does not by itself define any specific processing behavior. Other code or tools must be written to recognize this marker if it is meant to have an effect.

Typical usage:

~~~java
@Reviewed
class Article {
}
~~~

Meaning: the `Article` class **is marked** as `Reviewed`. An annotation can serve as a signal to the compiler, an annotation processor, or a framework, but the name itself and attaching `@Reviewed` do not automatically perform checks or change program behavior.

Familiar annotations such as `@Override` and `@FunctionalInterface` are examples of annotation types with no elements. The compiler has dedicated logic to handle them: `@Override` requires a valid method override/implementation, and `@FunctionalInterface` requires the interface type to meet functional interface rules. A **custom** marker annotation does not get such rules from the compiler by default.

## 2. Two Ways to Write Without Passing Elements: `@Reviewed` and `@Reviewed()`

With the annotation above, **both syntaxes are valid** and represent the same metadata:

~~~java
@Reviewed
class FirstArticle {
}

@Reviewed()
class SecondArticle {
}
~~~

- `@Reviewed` is the form **without parentheses**, which is concise and usually preferred for marker annotations.
- `@Reviewed()` has **empty parentheses**, explicitly showing that no `name = value` pairs are provided.
- It is not declared as `@interface Reviewed()`. The parentheses only appear at the **usage site**, as in `@Reviewed()`; the declaration structure remains `@interface Reviewed { }`.

This is **syntax for attaching metadata to a declaration**—it is not a function call `Reviewed()`, does not create an object the way `new` does, and does not call an annotation constructor.

Within the same program, two classes annotated with `@Reviewed` and `@Reviewed()` can be treated by a processor as both having the `Reviewed` marker. There is no need to preserve the form with or without parentheses to distinguish meaning.

### Examples of Invalid Syntax

Because `Reviewed` has no elements, the following forms that pass values are **invalid**:

~~~java
// The following lines only illustrate compilation errors;
// do not place them in a runnable sample program.

// @Reviewed("done")
// class InvalidA {}

// @Reviewed(value = "done")
// class InvalidB {}

// @Reviewed(status = true)
// class InvalidC {}
~~~

Even the common name `value` does not exist if the annotation type has not declared `value()`. To pass data, you must define an appropriate element; at that point, the annotation type is no longer a pure marker annotation.

## 3. Java 17 Program: Both Forms Produce the Same Result

Create a single file **`MarkerSyntaxDemo.java`**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Reviewed {
}

@Reviewed
class FirstArticle {
}

@Reviewed()
class SecondArticle {
}

class DraftArticle {
}

public class MarkerSyntaxDemo {
    public static void main(String[] args) {
        show("FirstArticle", FirstArticle.class);
        show("SecondArticle", SecondArticle.class);
        show("DraftArticle", DraftArticle.class);
    }

    private static void show(String name, Class<?> type) {
        boolean marked = type.isAnnotationPresent(Reviewed.class);
        System.out.println(name + ": " + marked);
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac MarkerSyntaxDemo.java
java MarkerSyntaxDemo
~~~

**Exact stdout:**

~~~text
FirstArticle: true
SecondArticle: true
DraftArticle: false
~~~

Explanation:

1. `FirstArticle` has `@Reviewed`, so `isAnnotationPresent(Reviewed.class)` returns `true`.
2. `SecondArticle` has `@Reviewed()`, so it also returns `true`: the empty parentheses do not create a different state.
3. `DraftArticle` is not marked, so it returns `false`.
4. The `show(...)` method itself **actively calls reflection** to read the annotation and print the result. Without this reading code, attaching `@Reviewed` will not print anything to the screen on its own.

The example uses `@Retention(RetentionPolicy.RUNTIME)` because we want to read metadata with reflection at runtime. If you change it to `RetentionPolicy.SOURCE` and recompile, all three lines will be `false` when using the reflection API on the compiled classes. Whether an annotation is validly attached in the source code is a separate matter from whether the runtime can retrieve the metadata.

### Role of the Two Meta-Annotations

- `@Target(ElementType.TYPE)` allows marking only eligible **type declarations**, such as a class, interface, enum, record, or annotation type. Placing `@Reviewed` directly on a field or method will be rejected by the compiler under this configuration.
- `@Retention(RetentionPolicy.RUNTIME)` retains metadata until runtime and allows the corresponding reflection APIs to retrieve it. If `@Retention` is not declared, the default is `RetentionPolicy.CLASS`, which cannot be read directly with `Class.isAnnotationPresent(...)` at runtime.

These two meta-annotations **configure the placement and retention lifetime of the marker**, not elements declared by the `Reviewed` type. Therefore, `Reviewed` remains a marker annotation even though its definition carries `@Target` and `@Retention`.

## 4. Distinguishing a “Marker Type” from a “Usage Form Without Arguments”

This is a very common point of confusion in Java:

> An **annotation type with no elements** is definitely a marker annotation. However, the **`@Name` syntax without parentheses or arguments** can still be valid for an annotation type *that has elements*, as long as all of its elements have default values.

Example:

~~~java
@interface FeatureFlag {
    boolean enabled() default true;
    String owner() default "team-a";
}

@FeatureFlag
class FeatureA {
}

@FeatureFlag()
class FeatureB {
}

@FeatureFlag(enabled = false)
class FeatureC {
}
~~~

All three usages are valid:

- `@FeatureFlag`: no elements are written, so `enabled = true` and `owner = "team-a"` are taken from their `default` values.
- `@FeatureFlag()`: also uses both default values.
- `@FeatureFlag(enabled = false)`: overrides one element, while the `owner` element still receives its default value.

Even though `@FeatureFlag` can be used without passing anything, `FeatureFlag` **is not a marker annotation type** because it declares two elements, `enabled()` and `owner()`.

Conversely, with a required element:

~~~java
@interface Route {
    String path();
}

// Invalid if using @Route or @Route()
// because the required path element is missing.

@Route(path = "/home")
class HomeRoute {
}
~~~

`@Route` and `@Route()` cannot substitute for `@Route(path = "...")` because `path()` has no `default` value.

Comparison table:

| Annotation type | Has declared elements? | Can `@Name` be used? | Can `@Name()` be used? |
| --- | --- | --- | --- |
| `@interface Marker {}` | No | Yes | Yes |
| `@interface Optional { int level() default 1; }` | Yes, all have defaults | Yes | Yes |
| `@interface Required { int level(); }` | Yes, has a required element | No | No |

The syntax at the usage site **is not enough** to determine whether an annotation type is truly a marker; inspect the `@interface` definition to see the number of declared elements.

## 5. Distinguishing from Single-Element `value()` Syntax

Java allows a shorthand syntax when an element has the special name `value()`:

~~~java
@interface Label {
    String value();
}

@Label("core")
class TopicA {
}

@Label(value = "core")
class TopicB {
}
~~~

`@Label("core")` and `@Label(value = "core")` supply the same value for the `value` element. This is **single-element annotation syntax**, which is completely different from `@Reviewed` (which has no elements). Because `Label.value()` is required, writing only `@Label` or `@Label()` will cause a compilation error.

Key point to remember: the name `value` has significance for Java's **shorthand syntax**. It does not turn an annotation with an element into a marker annotation. If `value()` has a `default`, you can even omit the element when using it, yet that annotation type still declares an element.

## 6. When Should You Design a Marker Annotation?

Choose a marker when the information to convey is essentially **yes/no** and requires no additional configuration data. For example, in an internal tool, `@Reviewed` might indicate that a document type has passed through a review process. A processor will use the presence of this marker to decide on the appropriate checks or reporting.

Another option is to use a boolean element:

~~~java
@interface ReviewedOption {
    boolean enabled() default true;
}
~~~

This approach makes sense when you genuinely need different states or configurability, such as `@ReviewedOption(enabled = false)`. If you only need simple marking, `@interface Reviewed {}` is cleaner and clearer.

**Before choosing a marker**, you should determine:

- **Where will the marker be placed?** Declare an appropriate `@Target` if you want to restrict where it can be used.
- **At which stage must the marker remain available?** Choose `SOURCE`, `CLASS`, or `RUNTIME` depending on how tools are expected to read the metadata.
- **What will process the marker?** A compile-time processor, a framework, or custom reflection/registration code.
- **Is presence alone truly sufficient?** If it needs to carry a path, name, priority, or configuration, consider adding elements instead of creating many hard-to-manage markers.

A marker annotation does not automatically emit business errors/warnings or alter the program. `@Override` takes effect at compile time because the Java compiler has built-in support for understanding that annotation. For custom annotations, any effect beyond basic syntax/target checks depends on the **processor or code consuming the metadata**.

## 7. Common Mistakes and How to Spot Them

**Misconception 1: “Whenever `@X` is used, type `X` has no elements.”** Not necessarily. `@X` can still be used when `X` has elements if all of them have `default` values. Check the body of the `@interface X` definition.

**Misconception 2: “`@X()` calls a constructor.”** False. This is an annotation form with an empty list of `name = value` pairs, not a constructor/method call in Java.

**Misconception 3: “A marker can still pass an argument via `value`.”** False. If `value()` is not declared, both `@X("text")` and `@X(value = "text")` are invalid.

**Misconception 4: “Having `@Retention(RUNTIME)` makes the marker do the work automatically.”** False. `RUNTIME` only determines whether metadata can be retrieved at runtime; processing code is needed to use that information.

**Misconception 5: “Without `@Target`, a marker can be used anywhere without restriction.”** You should not assume that. Java has different syntactic locations such as declarations, type uses, and type parameters; the applicability rules for annotations with or without `@Target` are not a license to attach them to arbitrary expressions. Configure the target explicitly according to your intent.

**Misconception 6: “Adding `@Target` or `@Retention` turns the annotation into a type with elements.”** False. These are meta-annotations placed on the **annotation type declaration**; only the element methods declared inside the body of `@interface X` determine whether `X` has elements.

## 8. Self-Practice

1. Define `@interface Verified {}`, then attach `@Verified` and `@Verified()` to two classes respectively. Do the two usages differ in meaning?
2. Change `Reviewed` to `@interface Reviewed { String by() default "QA"; }`. Can you still use `@Reviewed`? Is `Reviewed` still a marker annotation type?
3. Add `String by();` to the `Reviewed` type **without adding** `default`. What happens at compile time at places currently using `@Reviewed` and `@Reviewed()`?
4. Change the retention in `MarkerSyntaxDemo.java` to `SOURCE` and re-run the example. Why does reflection return `false` even though the annotation is still in the source code?
5. In a project that needs to automatically check classes annotated with `@Verified`, identify the two independent parts: declaring the `@Verified` marker and where the processing code actually checks for the marker's presence.

**Answer guidance:** (1) No difference in meaning; (2) still usable thanks to the default, but it is no longer a marker type; (3) compilation error for missing the required `by` element; (4) `SOURCE` does not retain metadata for runtime reflection to read; (5) the `@interface` definition provides metadata, while a processor/framework/reflection must actively handle it.

When reading Java code, separate two questions: **does the annotation type declare any elements?** and **does this usage pass any elements?** Making that distinction helps you accurately read both pure marker annotations and annotations with default parameters.
