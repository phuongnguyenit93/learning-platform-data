# Declaring value() Returning an Array of the Repeated Annotation

When you want to apply **the same annotation type multiple times to the same declaration**, Java uses the **repeatable annotation** mechanism. To declare a repeatable annotation, in addition to the main annotation, you need to define a **container annotation**: a separate annotation with a **`value()` element returning a one-dimensional array of the repeated annotation itself**.

Target example:

```java
@Role("ADMIN")
@Role("AUDITOR")
class ReportService {
}
```

For the syntax of two `@Role` lines coexisting to be valid, the `Role` declaration must have `@Repeatable(Roles.class)`, and `Roles` must declare **`Role[] value();`**. When it needs to wrap repeated occurrences, the compiler uses the `@Roles` container to store the list of `@Role` annotations. This is a relationship between two *annotation types* declared by the developer, checked by the compiler at compile time.

The goal of this lesson is to properly understand the `value()` signature, the meaning of the annotation array, the rules for placing `@Repeatable`, how to write valid/invalid cases, and how to read the results, including the difference between **annotations appearing directly** and **annotations inside a container**.

## 1. Why Does the Container Need value() to Return an Array?

Consider a single annotation:

```java
@interface Role {
    String value();
}
```

`String value()` in `Role` describes **the data of a single `@Role`**. A usage of `@Role("ADMIN")` contains the string `"ADMIN"`. This element **is unrelated to allowing repetition**.

To group multiple `@Role` annotations at the same location, we need a **different annotation type**:

```java
@interface Roles {
    Role[] value();
}
```

`Role[] value()` means: one `@Roles` contains **an array of elements of annotation type `Role`**, for example:

```java
@Roles({
    @Role("ADMIN"),
    @Role("AUDITOR")
})
class ReportService {
}
```

This is the explicit way to write the container. To write `@Role` twice instead of `@Roles({...})`, you must link the two declarations with `@Repeatable`:

```java
import java.lang.annotation.Repeatable;

@Repeatable(Roles.class)
@interface Role {
    String value();
}

@interface Roles {
    Role[] value();
}
```

After that, both ways of writing represent a list of `Role` annotations; the Reflection mechanism has an API to uniformly read direct annotations and annotations inside a container.

**Two different signatures, two different functions:**

| Declaration | `value()` returns | Meaning |
| --- | --- | --- |
| `@interface Role { String value(); }` | `String` | Content of **a single `@Role`** |
| `@interface Roles { Role[] value(); }` | `Role[]` | List of **`@Role` annotations** contained inside the container |

The main annotation is not required to name its element `value()`; it can have `String name();` or multiple other elements. However, **the container of a repeatable annotation must have an element named exactly `value` with a return type that is a one-dimensional array of the main annotation**.

## 2. Complete Declaration Pair to Run with Java 17+

A standard example needs to align the annotation types, retention, and target:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Roles.class)
@interface Role {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Roles {
    Role[] value();
}
```

Explanation of each part:

1. `@interface Role` creates the annotation type that users want to apply multiple times.
2. `@Repeatable(Roles.class)` is placed **on the repeated annotation type**, telling the compiler that **`Roles` is the container of `Role`**.
3. `@interface Roles` declares the container type. The name `Roles` is a readable convention, **not a mandatory name**; `RoleContainer` or another name is also valid if referenced properly in `@Repeatable`.
4. `Role[] value();` is mandatory. It must not be changed to `String[] value();`, `Object[] value();`, `Role value();`, or `Role[][] value();`.
5. The `@Retention(RUNTIME)` pair makes these usages readable by Reflection when the program runs. **Repeatability does not strictly require `RUNTIME` retention**; choose the retention according to your usage needs.
6. Both use `@Target(TYPE)` so that the annotations are applied to the corresponding type declarations.

You do not need to write any Java method to "add `Role` to the array". When compiling valid repeated usages, the compiler handles how annotations are wrapped according to Java rules.

**Special point:** `@Repeatable` takes the argument `Roles.class`, which is a *class literal* pointing to the container annotation. This is not a container object, does not create an instance with `new Roles()`, and is also not the string name `"Roles"`.

## 3. How to Use: Writing Repeatedly, Writing the Container, and Writing Once

Three common cases:

### 3.1. Repeating the main annotation

```java
@Role("ADMIN")
@Role("AUDITOR")
class ReportService {
}
```

The compiler accepts placing two `@Role` annotations on the same declaration because `Role` is marked with `@Repeatable(Roles.class)` and the `Roles` container satisfies the validity conditions.

### 3.2. Writing the container annotation directly

```java
@Roles({
    @Role("ADMIN"),
    @Role("AUDITOR")
})
class ReportService {
}
```

This approach is explicit about the container, providing an array of `Role` annotations. Java allows one-dimensional annotation arrays, and the `@Role(...)` elements are valid annotation values.

`@Roles({@Role("ADMIN"), @Role("AUDITOR")})` **is not a `String[]` array**. It is a **`Role[]` array**; each `@Role` element in turn has a `String value()` inside it.

### 3.3. A single usage of the main annotation

```java
@Role("ADMIN")
class ReportService {
}
```

A single `@Role` is valid; the compiler **is not required to wrap it in a container**. This difference matters if you use a Reflection API that only reads directly declared annotations without unwrapping the container.

### 3.4. The container can accept an empty array

```java
@Roles({})
class NoRoleService {
}
```

An explicit container declaration with an empty array can be valid according to the `Role[]` signature. However, **an empty array does not mean a `Role` annotation exists**; the API that returns `Role` annotations by type via `getAnnotationsByType(Role.class)` will give an empty array. Whether the design permits an empty configuration from a business perspective is the responsibility of the annotation-reading tool.

## 4. Standalone Example: Compile, Run, and Read Results with Reflection

Create the file **`RepeatableContainerDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.stream.Collectors;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Topics.class)
@interface Topic {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Topics {
    Topic[] value();
}

@Topic("java")
@Topic("annotation")
class Lesson {
}

@Topic("single")
class Single {
}

@Topics({@Topic("a"), @Topic("b")})
class Explicit {
}

public class RepeatableContainerDemo {
    private static String joinedTopics(Class<?> type) {
        return Arrays.stream(type.getAnnotationsByType(Topic.class))
                .map(Topic::value)
                .collect(Collectors.joining(", "));
    }

    public static void main(String[] args) {
        System.out.println(joinedTopics(Lesson.class));

        // No direct @Topic in the normal repeated representation.
        System.out.println(Lesson.class.getDeclaredAnnotation(Topic.class));

        Topics container = Lesson.class.getDeclaredAnnotation(Topics.class);
        System.out.println(container.value().length);

        System.out.println(joinedTopics(Single.class));
        System.out.println(Single.class.getDeclaredAnnotation(Topics.class));
        System.out.println(joinedTopics(Explicit.class));
    }
}
```

Using JDK 17+ in the directory containing the file:

```bash
javac --release 17 RepeatableContainerDemo.java
java RepeatableContainerDemo
```

Exact stdout:

```text
java, annotation
null
2
single
null
a, b
```

Reading the results in order:

- `getAnnotationsByType(Topic.class)` on `Lesson` returns **two `Topic` annotations** in declaration order; `joinedTopics` extracts the `value()` strings and joins them with commas.
- `getDeclaredAnnotation(Topic.class)` on `Lesson` returns `null` in this example because the repeated `@Topic` occurrences are represented via **`@Topics`**, rather than a directly declared `@Topic` occurrence.
- `getDeclaredAnnotation(Topics.class)` returns the container, and `container.value().length` equals `2`.
- `Single` has only one direct `@Topic`, so `getAnnotationsByType` reads `"single"`, while `getDeclaredAnnotation(Topics.class)` returns `null`.
- `Explicit` uses the explicit container; `getAnnotationsByType(Topic.class)` can still **unwrap the container** and return `"a"`, `"b"`.

This is a test of **the exact Java mechanism**, not relying on a specific framework. `@Retention(RUNTIME)` makes the metadata queryable at runtime; the Reflection calls in `main` are where the code actively reads the annotations.

## 5. What Does the Compiler Do with Repeated Usages?

When encountering:

```java
@Topic("java")
@Topic("annotation")
class Lesson {
}
```

The compiler handles it semantically equivalent to containing two `Topic` annotations inside a `Topics` container annotation, matching the `Topic[] value()` declaration. Because the same `Topic` type appears multiple times at a single location, the container allows representing the list.

One way to visualize this:

```text
Source code:
  @Topic("java")
  @Topic("annotation")
  class Lesson {}

                   compiler
                      |
                      v

Semantic container:
  @Topics(value = {
      @Topic("java"),
      @Topic("annotation")
  })

                      |
                      v

Reflection:
  getDeclaredAnnotation(Topics.class) -> Topics containing Topic[2]
  getAnnotationsByType(Topic.class)  -> Topic[2]
```

Java does not automatically generate a **`Topics` annotation type definition**. You must declare a valid container beforehand; the compiler only handles how repeated usages are represented. The syntax in the diagram is an **explanatory model**; it is not a requirement that Java code be rewritten into an identical source file.

When retention is `RUNTIME`, a tool can read the container explicitly:

```java
Topics topics = Lesson.class.getDeclaredAnnotation(Topics.class);
if (topics != null) {
    for (Topic topic : topics.value()) {
        System.out.println(topic.value());
    }
}
```

This snippet is based on `Topic`, `Topics`, and `Lesson` from the complete example. The result prints two lines: `java` then `annotation`. However, if only one `@Topic` is used directly, `topics` can be `null`. Therefore, if you want to read **every `Topic`** regardless of whether it is declared once, repeated multiple times, or placed in an explicit container, the appropriate API is usually `getAnnotationsByType(Topic.class)`.

## 6. The Container's value() Signature Must Be Strictly Exact

For the repeated annotation `@Topic`, the `@Topics` container must declare:

```java
@interface Topics {
    Topic[] value();
}
```

All three details are mandatory:

1. **Method name `value`**: not `items`, `topics`, `getValue`, `entries`.
2. **No parameters**: the syntax is `value()`, not `value(int index)`.
3. **Exact return type `Topic[]`**: a one-dimensional array of annotations of the same **annotation type annotated with `@Repeatable`**.

Note: the element type **`Topic`** is itself a valid annotation type. Therefore, `Topic[]` belongs to the category of **one-dimensional arrays of an annotation type**, which Java allows as an annotation element type.

### 6.1. Intentionally invalid containers

Each following snippet is an **independent error illustration**. Do not combine these invalid declarations into the runnable program in section 4.

**Invalid because the array contains String, not the repeated annotation:**

```java
@Repeatable(WrongTags.class)
@interface Tag {
    String value();
}

@interface WrongTags {
    String[] value(); // Invalid: must be Tag[].
}
```

Even though `Tag.value()` returns `String`, **`WrongTags.value()` must still return `Tag[]`**. The content type inside a single `@Tag` and the type of the list of `@Tag` annotations are two different levels of data.

**Invalid because the container uses the wrong element name:**

```java
@Repeatable(WrongTags.class)
@interface Tag {
}

@interface WrongTags {
    Tag[] items(); // Invalid: no element named value().
}
```

`@Repeatable` has no option to rename the containing element. The compiler requires `value()` specifically.

**Invalid because it holds only a single annotation:**

```java
@Repeatable(WrongTags.class)
@interface Tag {
}

@interface WrongTags {
    Tag value(); // Invalid: must be Tag[].
}
```

The container must have the ability to represent **multiple** annotations, so a single `Tag` does not satisfy the contract.

**Invalid because of a two-dimensional array:**

```java
@Repeatable(WrongTags.class)
@interface Tag {
}

@interface WrongTags {
    Tag[][] value(); // Invalid: multidimensional arrays are not a valid element type.
}
```

Java allows multidimensional arrays in many other contexts, but the return type of an annotation element only allows **one-dimensional arrays**.

### 6.2. Can a container declare additional elements?

Yes, **if the other elements have default values**. For example:

```java
@Repeatable(Labels.class)
@interface Label {
    String value();
}

@interface Labels {
    Label[] value();
    String source() default "manual";
}
```

`source()` is an additional element, not the list of repeated annotations, and is provided with a default. The compiler can create the container for repeated `@Label` occurrences without requiring the usage site to specify `source`.

Conversely, the following declaration **is not suitable as a container for repeated `Label`**:

```java
@interface Labels {
    Label[] value();
    String source(); // Missing default.
}
```

When the compiler needs to create an implicit container from repeated `@Label` annotations, there is no value available to supply for the required `source`. Therefore, every element other than `value()` in the container must have a default.

You should keep the container minimal with only `value()` if you do not have another clear metadata need.

## 7. Constraints That Must Align Besides value()

`Topic[] value()` is **necessary but not sufficient**. Java also has conditions that apply to the repeatable annotation type and its container.

### 7.1. The container's @Retention must be long enough

If the repeated annotation has:

```java
@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Tags.class)
@interface Tag {
}
```

then the `Tags` container **must not** have `SOURCE` or `CLASS` retention; use:

```java
@Retention(RetentionPolicy.RUNTIME)
@interface Tags {
    Tag[] value();
}
```

Reason: to query repeated `Tag` annotations at runtime, the container's metadata must also exist and be visible.

Retention rules:

| Repeated annotation | Valid container retention |
| --- | --- |
| `SOURCE` | `SOURCE`, `CLASS`, or `RUNTIME` |
| `CLASS` | `CLASS` or `RUNTIME` |
| `RUNTIME` | `RUNTIME` only |

The table expresses the retention rule **between the two annotation types**. If `@Retention` is not applied, an annotation type defaults to `CLASS` retention. Applying `@Repeatable` does not automatically change retention to `RUNTIME`.

### 7.2. @Target must be compatible

If the repeated annotation is allowed to be applied to both types and methods:

```java
@Target({ElementType.TYPE, ElementType.METHOD})
@Repeatable(Tags.class)
@interface Tag {
}
```

then the container must also **be permitted at the appropriate locations to hold those repetitions**. Example of a matching configuration:

```java
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Tags {
    Tag[] value();
}
```

A container that only allows `TYPE` while `Tag` allows `METHOD` will not satisfy the rule on locations for holding repeated `@Tag` annotations on methods. Usually, the easiest approach to maintain is to declare a corresponding `@Target` on both and let the compiler verify validity.

Certain scenarios with `TYPE_USE`, `TYPE_PARAMETER`, `ANNOTATION_TYPE`, and specialized targets have additional target compatibility rules in the Java Language Specification. When designing annotations used across multiple target kinds, verify the specific `@Target` pair with the compiler rather than assuming all target sets are equivalent.

### 7.3. @Documented and @Inherited

If the repeated annotation has `@Documented`, its container also needs `@Documented`. If the repeated annotation has `@Inherited`, the container also needs `@Inherited` to satisfy the validity rules.

Example:

```java
import java.lang.annotation.Documented;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Documented
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Labels.class)
@interface Label {
    String value();
}

@Documented
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Labels {
    Label[] value();
}
```

The snippet above is **a standalone declaration example**, not mixed with the other `Label` types in this lesson. `@Inherited` has its own rules when querying classes along an inheritance hierarchy and does not mean annotations on interfaces or methods are automatically inherited as well. Just keep in mind here that additional metadata on the repeated annotation and its container must be designed compatibly.

## 8. Distinguishing Reflection APIs When Repeated Annotations Are Present

A common source of errors is **reading a single annotation with an API designed for a single annotation** and then concluding that the annotation does not exist.

| Reflection API | On a class with two direct `@Topic` annotations | Meaning |
| --- | --- | --- |
| `getDeclaredAnnotation(Topic.class)` | `null` in the standard example | Does not automatically unwrap the `Topics` container to find a `Topic` |
| `getDeclaredAnnotation(Topics.class)` | Container with `Topic[2]` | Reads the container type directly |
| `getDeclaredAnnotationsByType(Topic.class)` | Array containing two `Topic` annotations | Finds the `Topic` type declared directly **or indirectly via a container** |
| `getAnnotationsByType(Topic.class)` | Array containing two `Topic` annotations | Similar in this case; also includes inheritance semantics according to the corresponding rules |
| `getDeclaredAnnotations()` | Contains one `Topics` container in this example | Retrieves annotations considered directly declared, without automatically unpacking into two `Topic` annotations |

Key point: **`getAnnotationsByType` and `getDeclaredAnnotationsByType` are designed to support repeated annotations**. The `getAnnotation` and `getDeclaredAnnotation` APIs that return a single annotation do not automatically interpret a container into a collection of repeated elements.

If you use a container with an extra element (for example, `String source() default "manual"`), the `getAnnotationsByType(Topic.class)` API primarily gives the individual `Topic` annotations. To read the extra metadata on the container, you must retrieve `Topics` appropriately.

### 8.1. "Present" and "associated" can differ

In Java, an annotation can be **directly declared**, **present indirectly through a container**, or **found according to inheritance rules**. Therefore, you should not assume all Reflection APIs dealing with annotations produce the same result.

Specifically:

- With **one** direct `@Topic`, `getDeclaredAnnotation(Topic.class)` sees that annotation.
- With **two** direct `@Topic` annotations at the same location, normally only the `Topics` container is stored as a directly declared annotation; to retrieve the two `Topic` annotations, use `getDeclaredAnnotationsByType(Topic.class)`.
- With an **explicitly** written container, `getAnnotationsByType(Topic.class)` can still unwrap the container.
- With `@Inherited`, `getAnnotationsByType` has a mechanism to consider annotations from an appropriate superclass, but you need to understand the rules regarding declarations on the subclass; avoid assuming that results from parent and child are always concatenated into a single list.

In many applications reading metadata on the exact annotated class, the simplest and least error-prone choice is `getDeclaredAnnotationsByType(MyAnnotation.class)` if inheritance does not need to be considered, or `getAnnotationsByType(MyAnnotation.class)` when you want to follow the inheritance rules supported by the API.

## 9. What Happens If the Annotation Is Not Marked with @Repeatable?

If:

```java
@interface Step {
    String value();
}
```

then the declaration:

```java
@Step("one")
@Step("two")
class Workflow {
}
```

**Invalid**: `Step` is not a repeatable annotation type, even though you can write a standalone container annotation such as `Steps`. Specifying the container in `@Repeatable(Steps.class)` is what creates the relationship the compiler recognizes.

Adding a container declaration like the following **is still not enough if `@Repeatable` is missing on `Step`**:

```java
@interface Steps {
    Step[] value();
}
```

Both parts are needed: `@Repeatable(Steps.class)` on the repeated annotation **and** a compatible `Step[] value()` signature in the container.

Similarly, if the container is present but fails to meet the conditions in sections 6 and 7, the compiler will report an annotation type design error, rather than waiting until runtime for the application to discover it.

## 10. Avoid Mixing Direct Repetition with an Explicit Container at the Same Location

The following ways of writing are **equivalent approaches in purpose**; choose one for a given usage site:

```java
@Topic("a")
@Topic("b")
class FirstWay {
}

@Topics({@Topic("a"), @Topic("b")})
class SecondWay {
}
```

Avoid writing both `@Topic` and `@Topics` on **the same declaration** to represent the same list. Direct/container combinations on the same declaration are subject to strict rules on repeated annotations and can cause the compiler to reject them. A consistent approach helps prevent confusion about occurrence counts, order, and Reflection results.

In a code review, seeing a container like `@Topics({...})` **is not necessarily a bad or outdated design**: it is valid syntax, especially when you need to write the container manually. However, placing multiple individual `@Topic` annotations is usually easier to read when the only need is to apply multiple annotations of the same type.

## 11. Real-World Case: Multiple Check Rules of the Same Type

Suppose a system has multiple rules applied to the same data type:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Checks.class)
@interface Check {
    String field();
    String rule();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Checks {
    Check[] value();
}

@Check(field = "email", rule = "required")
@Check(field = "email", rule = "format")
class Registration {
}
```

When processing:

```java
for (Check check : Registration.class.getAnnotationsByType(Check.class)) {
    System.out.println(check.field() + ":" + check.rule());
}
```

The loop snippet is **illustrative code placed inside a method**, using the three types declared above.

Stdout of the loop:

```text
email:required
email:format
```

Important points:

- `Check` holds **a set of data** `field`/`rule`.
- `Checks.value()` holds **multiple `Check` annotations**, not strings from each individual `rule`.
- `getAnnotationsByType(Check.class)` returns the `Check` annotations in the list in the appropriate order for processing code to iterate over.
- Annotations **do not validate input data on their own**. To turn `rule = "required"` metadata into actual validation behavior, the program/framework must implement the logic itself, controlling input, processing order, and error reporting.

This is why an annotation array in the container is valuable: each element stores **multiple structured metadata fields**, rather than just a single `String` element.

## 12. Common Mistakes and How to Fix Them

**Mistake 1 — The container returns an array of the value inside the annotation.**

```java
@interface Roles {
    String[] value(); // Invalid if this is the container for @Role.
}
```

Fix it to `Role[] value();`. `String` can be the return type of `Role.value()`, but the container must hold **`Role` annotation objects**.

**Mistake 2 — Using the name `roles()` because it sounds more natural.**

```java
@interface Roles {
    Role[] roles(); // Cannot replace the value() element.
}
```

In the `@Repeatable(Roles.class)` pair, the container is required to provide `value()`; you can name the **annotation type** according to context, but you cannot change this element naming convention.

**Mistake 3 — Giving `value()` a single annotation, or a multidimensional array.**

`Role value()` cannot represent a list according to the contract; `Role[][] value()` violates the annotation element type restriction.

**Mistake 4 — The container has an additional required element.**

If `Roles` has `String version();` without a default, the compiler has no value to supply when generating the container for repeated `@Role` usages. Use `String version() default "v1";` if an extra element is truly needed.

**Mistake 5 — Mismatched retention.**

`@Role` having `RUNTIME` while `@Roles` only has `CLASS` will be rejected by the compiler under the container rules. Both types should have retention matching the Reflection goal.

**Mistake 6 — Declaring only the container while forgetting `@Repeatable`.**

A standalone container annotation does not automatically make `@Role` repeatable. Add `@Repeatable(Roles.class)` in the proper place.

**Mistake 7 — Using `getAnnotation(Role.class)` to find all Roles.**

For repeated annotations wrapped via a container, querying for a single annotation can return `null`. Use `getAnnotationsByType(Role.class)` or `getDeclaredAnnotationsByType(Role.class)` to receive the list.

**Mistake 8 — Assuming the container is an arbitrary runtime collection.**

`Role[] value()` is an annotation element, checked by Java at compile time. It **is not a `List<Role>`**, does not automatically support adding/removing elements at runtime, and cannot return `null`.

## 13. Review Exercises

### Exercise 1: Fill in the required signature

Given:

```java
@Repeatable(Permissions.class)
@interface Permission {
    String resource();
    String action();
}
```

Complete the following:

```java
@interface Permissions {
    // Fill in the required element here.
}
```

**Answer:** `Permission[] value();`. Since `Permission` does not declare `@Retention`, the default is `CLASS`; if you plan to use Reflection at runtime, consider `RUNTIME` for both `Permission` and `Permissions`.

### Exercise 2: Distinguish between the two value() elements

In:

```java
@Repeatable(Flags.class)
@interface Flag {
    String value();
}

@interface Flags {
    Flag[] value();
}
```

What is the value of `@Flag("alpha")`, and what is the value of `@Flags({@Flag("alpha"), @Flag("beta")})`?

**Answer:** `Flag.value()` returns `"alpha"`; `Flags.value()` returns an array containing two `Flag` annotations. They share the same element name but belong to **two different annotation types**, with different return types.

### Exercise 3: Reflection

With `@Topic("a") @Topic("b")` on a class and `RUNTIME` retention for the annotation pair, predict:

- `getDeclaredAnnotation(Topic.class)`
- `getDeclaredAnnotation(Topics.class).value().length`
- `getAnnotationsByType(Topic.class).length`

**Answer:** `null`, `2`, and `2` respectively in the standard example (with no other standalone `Topic` annotation on that class).

### Exercise 4: Spot the errors in the container definition

Find the errors:

```java
@Repeatable(MarkList.class)
@Retention(RetentionPolicy.RUNTIME)
@interface Mark {
    int id();
}

@Retention(RetentionPolicy.CLASS)
@interface MarkList {
    Mark[] value();
    String source();
}
```

**Answer:** the retention of `MarkList` is insufficient for `Mark` which has `RUNTIME`; besides `value()`, the `source()` element has no default. Change `MarkList` to `@Retention(RUNTIME)` and give `source()` a default or remove it.

### Exercise 5: Metadata check design

Why is a `Check[]` array more suitable than `String[]` if each check has both `field` and `rule`? Which API would you use to read **all checks** when a class has only one `@Check` or multiple `@Check` annotations?

**Answer:** each `Check` represents a strongly typed set of values. Use `getAnnotationsByType(Check.class)` to uniformly read one, multiple, or an explicit container.

## 14. Checklist Before Creating a Repeatable Annotation

1. Has the **repeated** annotation type declared `@Repeatable(Container.class)`?
2. Is the container **an annotation type** that actually exists with an element named exactly **`value()`**?
3. Is the exact element signature **`RepeatedAnnotation[] value();`** and is it a **one-dimensional** array?
4. Do the container's other elements, if any, have a **default**?
5. Are `@Retention`, `@Target`, and when needed `@Documented`/`@Inherited` of the two types compatible?
6. If Reflection is needed, have both selected `RUNTIME`?
7. Does the code reading multiple annotations use `getAnnotationsByType` or `getDeclaredAnnotationsByType` instead of the single-annotation reading approach?
8. Have you tested all three cases: **once**, **repeated twice**, and **explicit container**?

**Remember:** `@Repeatable` points to the container; whereas **`RepeatedAnnotation[] value()` is the mandatory contract of the container**. The compiler needs that exact signature to group occurrences of the same annotation type. When querying after compilation, choose the right API to read annotations directly or indirectly from the container, and keep in mind that metadata does not automatically produce business behavior.
