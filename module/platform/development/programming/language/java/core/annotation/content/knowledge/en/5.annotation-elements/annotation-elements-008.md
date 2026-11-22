# Default Values of Arrays and Nested Annotations in Java Core

Annotations in Java allow declaring **elements** and default values using the `default` keyword. When an element has an array type or is itself an annotation type, the syntax of its default value differs from that of a regular Java variable: an array is written with curly braces `{...}`, while a nested annotation is written in the form `@AnnotationName(...)`. This lesson focuses on how to declare, use, and read those values, along with rules that are easy to confuse when combining them.

## 1. Learning Outcomes

After this lesson, you will be able to:

- Write `default {}` for an empty array, `default {"a", "b"}` for an array with elements, and understand the shorthand syntax for a single element.
- Distinguish an element with a single annotation type from an element with an **annotation array** type.
- Declare `@Nested(...)` and `{@Nested(...), @Nested(...)}` defaults with valid syntax.
- Explain when Java uses the default and when a value written directly inside `@...` replaces the default.
- Read arrays and nested annotations via Reflection, including inspecting the declared default with `Method.getDefaultValue()`.
- Avoid errors related to `null`, `new`, `List` types, runtime expressions, and nested annotations with unfilled required elements.

## 2. Properly Reviewing the Concept of `default` in Annotations

An annotation type declares elements using syntax similar to a parameterless method:

~~~java
@interface Exercise {
    String title();                 // Required: no default.
    int level() default 1;         // Can be omitted when used.
    String[] tags() default {};    // Empty array by default.
}
~~~

This is an **illustrative declaration snippet**, not a standalone runnable program. When applying the annotation:

~~~java
@Exercise(title = "Java")
class Basics {}
~~~

Java treats `level()` as `1` and `tags()` as an empty `String[]` array, because they are not passed at the point of use. `title()` must be declared because it has no default.

Keep in mind:

- `default` is placed **inside the annotation type declaration**, after the element's empty parameter list `()`.
- Do not write `default` where the annotation is applied to a class/method/field; at the point of use, you only pass `name = value`.
- `default` in an annotation type is **not** a `default method` of a regular interface: an element has no Java body.
- A value declared at the point of use takes precedence over the default of the corresponding element. Other elements still use their defaults if not provided.
- There is no `null` value for an annotation element, whether as a default or as a passed value.

An annotation type can have multiple elements; each element can be required or have its own default value.

## 3. Default Values of Array Elements

### 3.1. Empty, Single-Element, and Multi-Element Arrays

~~~java
@interface ResourceInfo {
    String[] labels() default {};                   // 0 elements.
    String[] extensions() default {"txt"};          // 1 element.
    int[] retryDelays() default {100, 200, 500};    // 3 elements.
}
~~~

Ways to write array defaults:

| Declaration | Value when omitted |
| --- | --- |
| `String[] labels() default {};` | `String[]` array of length 0 |
| `String[] labels() default {"core"};` | Array of one string `"core"` |
| `String[] labels() default {"core", "java"};` | Array of two strings in exact order |
| `int[] delays() default {10, 20};` | Array of two integers |
| `Class<?>[] types() default {String.class, Integer.class};` | Array of two class literals |

The `{}` in an annotation context is an **array initializer of an annotation element**; you do not declare a default with `new String[] { ... }` or an array object created at runtime. Therefore, to default to empty you need to write `default {}`, not `default null`.

The data type rules for annotation elements only allow **one-dimensional** arrays with valid element types: primitives, `String`, `Class`, enum, or annotation types. You cannot define a `String[][]` or `List<String>` element, even though Java normally allows those types for other variables/methods.

### 3.2. Overriding Defaults at the Point of Use

Given:

~~~java
@interface Tags {
    String[] value() default {"basic", "java"};
}
~~~

Valid usages:

~~~java
@Tags
class UsesDefault {}

@Tags({})
class EmptyTags {}

@Tags({"advanced", "reflection"})
class TwoTags {}

@Tags("annotation")
class OneTag {}
~~~

All of the above are illustrative declarations only.

- `@Tags`: uses the default `{"basic", "java"}`.
- `@Tags({})`: **actively overrides** it with an empty array; it does not fall back to the default.
- `@Tags({"advanced", "reflection"})`: replaces it with a two-string array.
- `@Tags("annotation")`: shorthand when passing a single element of a `String[]` array; Java interprets it as `{"annotation"}`.

In `@Tags(...)`, the name `value` is omitted because it is the specially named element `value`. If the element name is `labels`, you must write `@ResourceInfo(labels = "one")`; you cannot omit the name `labels` as in the case of `value`.

Writing `@Tags(value = {"x"})` and `@Tags({"x"})` are also equivalent. If all elements of an annotation type have defaults, you can apply the annotation without arguments using `@Tags` or `@Tags()`.

### 3.3. An Empty Default Differs from "Not Declared"

From a usage perspective:

~~~java
@interface Flags {
    String[] value() default {};
}

@Flags
class A {}

@Flags({})
class B {}
~~~

When calling `value()` on the corresponding runtime annotation, both return an empty array. However, in terms of declaration, `A` **does not provide** a value directly, whereas `B` **explicitly provides** an empty value. This difference matters if the default of `Flags.value()` is modified later: the usage on `A` can receive the new default when read, while `B` continues using the explicitly written empty value.

A default array is not a shared variable for classes to modify configuration via `array[0] = ...`; annotations represent declarative metadata. You should not build logic that relies on mutating an array obtained from Reflection.

## 4. Elements with Nested Annotation Types

An annotation type can use **another annotation type** as the type of an element.

~~~java
@interface Author {
    String name();
    int priority() default 1;
}

@interface DocumentInfo {
    Author reviewer() default @Author(name = "system");
}
~~~

`DocumentInfo.reviewer()` returns an annotation of type `Author`. Its default value is written **directly as an annotation literal** `@Author(name = "system")`. Inside `@Author`, the `priority()` element is not passed, so it takes the default `1`.

Usage:

~~~java
@DocumentInfo
class DefaultDocument {}

@DocumentInfo(reviewer = @Author(name = "alice", priority = 3))
class ReviewedDocument {}
~~~

With `DefaultDocument`, `reviewer().name()` returns `"system"`; with `ReviewedDocument`, it returns `"alice"` and `reviewer().priority()` returns `3`.

The two annotations have a **metadata-containment relationship**, not a class inheritance relationship. "Nested annotation" in this lesson refers to *the value of an element whose type is an annotation*, which is different from declaring an annotation type inside the body of a class or the body of an annotation type.

Note: if `Author.name()` is required, an empty `@Author` default value is **invalid**; you must pass `name` or modify `Author` so that `name()` also has a default. Defaults in nested annotations are applied independently for each annotation type.

### 4.1. Nested Annotation Arrays

An element can also return an **array of annotations**:

~~~java
@interface Rule {
    String code();
    int priority() default 1;
}

@interface RuleSet {
    Rule[] rules() default {
        @Rule(code = "syntax"),
        @Rule(code = "security", priority = 2)
    };
}
~~~

`RuleSet.rules()` returns a `Rule[]` array with two elements. Each element of the array is an annotation instance holding `Rule` metadata, not a `new Rule(...)` object.

An empty array is also valid:

~~~java
@interface EmptyRuleSet {
    Rule[] rules() default {};
}
~~~

If you want a **single annotation** as the default for `Rule[]`, the array syntax is written explicitly:

~~~java
@interface OneRuleSet {
    Rule[] rules() default {@Rule(code = "syntax")};
}
~~~

In addition, Java allows the single-element shorthand form where valid:

~~~java
@interface ShortRuleSet {
    Rule[] rules() default @Rule(code = "syntax");
}
~~~

Both forms above represent the same single-annotation array. Using `{}` in learning materials is usually easier to read, especially when the number of elements may grow.

### 4.2. Passing an Annotation Array at the Point of Use

~~~java
@RuleSet(rules = {
    @Rule(code = "cache"),
    @Rule(code = "database", priority = 4)
})
class ServiceRules {}

@RuleSet(rules = {})
class NoRules {}

@RuleSet(rules = @Rule(code = "single"))
class OneServiceRule {}
~~~

The form `rules = @Rule(...)` is shorthand for a single-element array. `rules = {}` overrides the default list to be empty. If `rules` is omitted, Java uses the array declared in `RuleSet`.

A nested annotation value is a static declarative construct, not an arbitrary object constructor. Java does not allow `new Rule(...)` because an annotation type is not a class that creates objects via a regular constructor.

## 5. Standalone Java 17+ Example: From Defaults to Reflection

Create the file **`AnnotationDefaultArraysDemo.java`** with the following full contents. The example has two annotation types, two classes using annotations, and one public class containing `main`.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.stream.Collectors;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Label {
    String name();
    int priority() default 1;
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface LessonConfig {
    String[] topics() default {"java", "core"};
    String[] aliases() default {};
    Label reviewer() default @Label(name = "default-reviewer");
    Label[] checks() default {
        @Label(name = "syntax"),
        @Label(name = "runtime", priority = 2)
    };
}

@LessonConfig
class DefaultLesson {}

@LessonConfig(
    topics = {"annotation"},
    aliases = "ann",
    reviewer = @Label(name = "alice", priority = 3),
    checks = {@Label(name = "custom")}
)
class CustomLesson {}

public class AnnotationDefaultArraysDemo {
    private static void show(Class<?> type) {
        LessonConfig config = type.getAnnotation(LessonConfig.class);

        System.out.println(type.getSimpleName());
        System.out.println("topics=" + Arrays.toString(config.topics()));
        System.out.println("aliases=" + Arrays.toString(config.aliases()));
        System.out.println("reviewer=" + config.reviewer().name()
                + ":" + config.reviewer().priority());
        System.out.println("checks=" + Arrays.stream(config.checks())
                .map(label -> label.name() + ":" + label.priority())
                .collect(Collectors.joining(", ")));
    }

    public static void main(String[] args) throws NoSuchMethodException {
        show(DefaultLesson.class);
        show(CustomLesson.class);

        Object defaultAliases = LessonConfig.class
                .getDeclaredMethod("aliases")
                .getDefaultValue();
        System.out.println("default aliases="
                + Arrays.toString((String[]) defaultAliases));
    }
}
~~~

Open a terminal in the directory containing the file and run:

~~~bash
javac -encoding UTF-8 AnnotationDefaultArraysDemo.java
java AnnotationDefaultArraysDemo
~~~

Exact stdout:

~~~text
DefaultLesson
topics=[java, core]
aliases=[]
reviewer=default-reviewer:1
checks=syntax:1, runtime:2
CustomLesson
topics=[annotation]
aliases=[ann]
reviewer=alice:3
checks=custom:1
default aliases=[]
~~~

You can read and verify this step by step:

1. `@LessonConfig` on `DefaultLesson` passes no elements. All of `topics`, `aliases`, `reviewer`, and `checks` have defaults, so the annotation is valid.
2. The default for `topics` is a two-string array; `aliases` is an empty array. `Arrays.toString(...)` displays the array contents clearly.
3. The default `reviewer` holds `@Label(name = "default-reviewer")`. Because `Label.priority() default 1`, the result is `default-reviewer:1`.
4. The default `checks` consists of two annotations; the first receives priority `1` from `Label`, and the second specifies `2`.
5. `CustomLesson` directly provides all four elements, so they replace each corresponding default. `aliases = "ann"` is converted into a single-string array.
6. `checks = {@Label(name = "custom")}` contains one annotation, in which `priority` takes the default `1` from `Label`.
7. The final part reads the **default declared on the annotation type** using `Method.getDefaultValue()`. Because `aliases()` has type `String[]`, we cast it to `(String[])` and display the empty array.

Here, two different operations both return values:

- `DefaultLesson.class.getAnnotation(LessonConfig.class).aliases()` retrieves the **effective value** of the annotation attached to a class: the explicitly declared value if present, otherwise the default.
- `LessonConfig.class.getDeclaredMethod("aliases").getDefaultValue()` retrieves the **default defined on the annotation type itself**, regardless of which class uses that annotation. This method returns `null` if the element **does not declare a default**; that is a representation used by the Reflection API and **does not mean the element allows a `null` value**.

`@Retention(RUNTIME)` is placed on `LessonConfig` and `Label` so the example can read them via Reflection. `@Target(TYPE)` allows using the annotation on class declarations. If retention is omitted, the default is `CLASS`, and the `getAnnotation(...)` call at runtime will no longer see the annotation as in the example.

## 6. When Are Defaults Stored and Applied?

According to the Java Language Specification, an element's default value is associated with the **annotation type definition** and is applied when the annotation is read; it is not copied as an explicit value into every annotation usage site. This is a detail that has an impact when updating annotation libraries.

For example, suppose the initial version is:

~~~java
@interface Features {
    String[] value() default {"read"};
}

@Features
class AppA {}

@Features({})
class AppB {}
~~~

If you later change the default in `Features` to `{"read", "write"}` and provide the compatible new annotation type at runtime:

- `AppA` omitted `value`, so when read with the new definition it can receive `["read", "write"]`, even though class `AppA` itself has not been recompiled.
- `AppB` directly declared an empty array, so when read it still receives an empty array.

This does not mean every kind of annotation change is safe with respect to binary compatibility. Removing/renaming an element, changing a return type, or breaking nested annotation definitions can prevent old code from being read as intended. When evolving an API, check consistency across the compiler, runtime classpath, and metadata consumers.

If you need to know **whether a default is declared**, use `getDefaultValue()` on the method describing the element; if you only need the final value of a specific annotation, call the element method directly on the annotation instance.

## 7. Type Rules and Invalid Syntax

An annotation element is not like an arbitrary object property. The following examples are **invalid and shown only for error analysis**:

~~~java
@interface WrongDefaults {
    String[] labels() default null;                 // Invalid: null is not allowed.
    String[] names() default new String[]{"a"};     // Invalid: runtime new array.
    java.util.List<String> tags() default {};       // Invalid: List is not a valid element type.
    String[][] matrix() default {};                  // Invalid: multidimensional array.
    String[] dynamic() default {System.getenv("X")}; // Invalid: not a constant expression.
}
~~~

Do not include those syntactically invalid snippets in the main program file. Valid alternatives:

~~~java
@interface ValidDefaults {
    String[] labels() default {};
    String[] names() default {"a"};
    Class<?>[] types() default {String.class};
    int[] levels() default {1, 2, 3};
}
~~~

For elements containing annotations, values must be annotation literals of matching types:

~~~java
@interface Owner {
    String id();
    boolean active() default true;
}

@interface Ownership {
    Owner owner() default @Owner(id = "platform");
    Owner[] backups() default {
        @Owner(id = "alice"),
        @Owner(id = "bob", active = false)
    };
}
~~~

`@Owner(id = "platform")` is valid because `Owner.id()` is passed, while `Owner.active()` already has a default. `owner() default null`, `owner() default new Owner(...)`, or `owner() default @Owner` (when `id()` is still required) are all invalid.

Other array element types such as `enum[]`, `Class<?>[]`, and `int[]` can have defaults if they use values complying with Java's annotation rules. For `String[]`, string values can be literals or compile-time string constant expressions; runtime method calls do not count.

## 8. Common Mistakes When Reading and Designing Annotations

**Misconception 1: `default {}` means there is no value.** In reality, it is **a valid value**: an empty array. Users can intentionally pass `{}` to override a non-empty default.

**Misconception 2: `@Nested` is always valid even if the nested annotation has required elements.** For example, `@Owner` is only valid if `Owner.id()` is passed or has a default. The outer annotation's default does not automatically supply values for required elements inside.

**Misconception 3: You must use `new` to create a nested annotation.** In annotation declarations, use `@Owner(id = "...")`; values are not created via a constructor like regular classes.

**Misconception 4: `@Label(...)` and `{@Label(...)}` have the same type everywhere.** A single value matches an element of type `Label`; an array matches an element of type `Label[]`, and the single form can serve as shorthand for a single-element array when rules permit. Check the declared element type before choosing the syntax.

**Misconception 5: Using `null` as a default to mark the absence of a child annotation.** Java does not allow an annotation element to hold `null`. Consider an empty array `Owner[] owners() default {}` to represent having no owner, or a sentinel annotation with clearly defined semantics; choose the approach according to your API contract.

**Misconception 6: Assuming a default on an annotation type only takes effect at compile time at the usage site.** Default values are applied when read. Changing a default in a library version can change the behavior of old annotations that did not write an explicit value.

**Misconception 7: Querying via Reflection, getting `null`, and concluding the default is empty.** `getAnnotation(...)` returns `null` if **no matching annotation is present**; whereas `getDefaultValue()` returns `null` if **the element has no default**. Specifically, an array with an empty default, when read with the appropriate API, is an array of length 0, distinct from `null`.

**Misconception 8: Treating an annotation array as configuration that can be mutated directly at runtime.** Annotations are designed as declarative metadata. Do not use array-returning methods to update annotation configuration; design runtime data with separate objects/configs when mutability is needed.

**Misconception 9: Forgetting the retention of the annotation to be read.** Standard Reflection only sees annotations with `@Retention(RUNTIME)`. Nested annotations in the example also declare `RUNTIME` to clearly illustrate the Reflection path.

## 9. Progressive Practice Exercises

1. Create `@interface FileInfo` with `String[] formats() default {}`; apply it to three classes with `@FileInfo`, `@FileInfo(formats = {"json", "xml"})`, and `@FileInfo(formats = "csv")`. Print the effective arrays using `Arrays.toString`.
2. Change the default of `formats` to `{"txt"}`, and compare omitting the element with passing `formats = {}`. Explain the difference based on the source of the value.
3. Define `@interface Permission { String name(); boolean required() default true; }`. Declare `Permission permission() default @Permission(name = "read");` in another annotation. Read both `name` and `required`.
4. Replace the element above with `Permission[] permissions() default {@Permission(name = "read"), @Permission(name = "write", required = false)};`. Use Reflection to print the list in order and try overriding with an empty array.
5. In the `AnnotationDefaultArraysDemo` example, add `int[] ports() default {8080, 8081};` to `LessonConfig`. Print the default, then override `ports = {9000}` on `CustomLesson`.
6. Use `LessonConfig.class.getDeclaredMethod("topics").getDefaultValue()`, `getDeclaredMethod("reviewer").getDefaultValue()`, and `getDeclaredMethod("checks").getDefaultValue()`. Verify that the return types are `String[]`, annotation `Label`, and `Label[]`, respectively.
7. Try removing `default` from `Label.priority()`, predict which `@Label(...)` sites need `priority` added, and then compile to verify.
8. Write invalid examples with `default null` and `default new String[]{"x"}`; read the `javac` messages and explain them using the `ElementValue` rule instead of merely memorizing an error line.

## 10. Checklist Before Moving On

| Question | What you should be able to answer |
| --- | --- |
| What does `default {}` represent? | A valid array with 0 elements |
| Can you pass a single string for `String[]`? | Yes, as a single-element array shorthand at the element position |
| How is the default of an annotation-typed element written? | `default @Nested(...);` |
| How is the default of an annotation-array element written? | `default {@Nested(...), @Nested(...)};` or `default {};` |
| What if a nested annotation has required elements? | Those elements must be provided in the literal, unless they have defaults |
| Can `null` or `new` be used in a default? | No |
| How do you inspect a default using Reflection? | `AnnotationType.class.getDeclaredMethod("element").getDefaultValue()` |
| How are values at the usage site and defaults prioritized? | Explicit values take precedence; if missing, the default is applied when read |

**Key takeaway:** annotations allow representing composite metadata using arrays and nested annotations without manual object instantiation. `default` describes a fallback value on the **annotation type**; at usage sites, each element can keep the fallback or explicitly override it. Understanding this helps accurately read annotation configurations in Java Core and annotation-based Java libraries.

## References

- [Java Language Specification 17, `9.6.1–9.6.2 — Annotation interfaces and Defaults](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.2).
- [Java Language Specification 17, `9.7.1–9.7.3 — Annotation values, marker and single-element shorthand](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.1).
- [Java SE 17, Method.getDefaultValue()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#getDefaultValue()).
