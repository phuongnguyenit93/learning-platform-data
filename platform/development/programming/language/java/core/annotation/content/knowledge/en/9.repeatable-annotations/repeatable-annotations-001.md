# The Problem of Multiple Values at the Same Location: Why Does Java Need Repeatable Annotations?

An annotation typically describes **a set of metadata** attached to a Java declaration. However, there are cases where **the same declaration** needs multiple independent values for **the same annotation type**: a method having multiple schedules, a class assigned multiple labels, or an endpoint having multiple access rules. This is the problem that led to the **repeatable annotation** mechanism, supported by Java since Java 8.

It is necessary to distinguish between two needs:

1. **A single annotation containing multiple values in an array-typed element**, for example `@Labels({"public", "internal"})`.
2. **Multiple occurrences of the same annotation type at the same location**, for example `@Label("public")` and `@Label("internal")` both placed before a class.

These two approaches can represent similar information in simple cases, but they have **different data structures and declaration rules**.

## 1. What Is “the Same Location”?

Here, a location is a **declaration or type-use** that Java allows to be marked with an annotation: class, method, field, constructor, parameter, etc. The set of valid locations also depends on the `@Target` of each annotation type.

For example, a class needs two roles:

```java
@Role("reader")
@Role("writer")
class ReportService {
}
```

Both annotations target **the same `ReportService` declaration**, both have the type `Role`, yet have different values. This is a common requirement when multiple independent rules are attached to the same target.

If `Role` is declared only as a regular annotation, **without `@Repeatable`**, then placing two `@Role(...)` lines directly on the same class **will not compile**. Having different values does not by itself make Java allow reusing the same annotation type.

Minimal **invalid** example (just to illustrate the problem):

```java
@interface Role {
    String value();
}

@Role("reader")
@Role("writer") // Error: Role is not a repeatable annotation
class ReportService {
}
```

Annotations of different types can coexist on a class, for example `@Deprecated` together with `@SuppressWarnings`. The restriction in question is **repeating the same annotation type**, not the number of annotations in general.

## 2. Why Does the Need for Multiple Values Arise?

A declaration sometimes has multiple pieces of information of the same kind, each of which must stand independently:

| Context | Single declaration | Values to describe |
| --- | --- | --- |
| Authorization | Service class | Roles `reader`, `writer` |
| Schedule | A method | Weekday schedule and weekend schedule |
| Validation rules | A field | Length check and character pattern check |
| Routing | A method | Multiple labels or multiple routing configurations |
| Mapping | A class | Multiple mappings or conversions |

These are **modeling scenarios**; it does not mean the JDK automatically performs authorization, scheduling, or routing when annotations are present. Framework or application code must read the metadata and apply the corresponding behavior.

The difference between a single value and multiple values affects how annotations are designed: should an array be used, should a container be created, or should the annotation be made repeatable?

## 3. First Approach: A Single Annotation Containing an Array

If you need to hold multiple **homogeneous values** for a single attribute, an array-typed element is a concise option:

```java
@interface Roles {
    String[] value();
}

@Roles({"reader", "writer"})
class ReportService {
}
```

This is **one** `@Roles` annotation with a `String[]`-typed `value()` element containing two strings. The syntax is valid in Java, even when the `Roles` type does not have `@Repeatable`.

To express the same meaning using the full element name, you can write:

```java
@Roles(value = {"reader", "writer"})
class AnotherService {
}
```

Advantages of an array:

- Easy to declare when all values share the same type and the same meaning.
- No need for a separate annotation type for each element.
- Readers immediately see that this is a set of strings for the same attribute.

Limitation of an array: if **each application** carries multiple pieces of accompanying metadata, a string array does not represent each data set well. For example, if a role has `name`, `scope`, and `priority`: `{"reader", "writer"}` does not indicate which scope goes with which role.

This can be addressed using a **nested annotation array**, though the usage syntax is more verbose:

```java
@interface RoleSpec {
    String name();
    String scope();
}

@interface RoleSpecs {
    RoleSpec[] value();
}

@RoleSpecs({
    @RoleSpec(name = "reader", scope = "/reports"),
    @RoleSpec(name = "writer", scope = "/drafts")
})
class CompositeRoleService {
}
```

The snippet above only illustrates **a container holding an array of `RoleSpec` annotations**. `RoleSpec` has **not yet** been declared with `@Repeatable`, so it cannot be replaced with two `@RoleSpec` annotations directly on the class while keeping those declarations unchanged.

## 4. Second Approach: Placing Multiple Annotations of the Same Type Directly

Starting with Java 8, Java allows declaring an annotation type as **repeatable** using `@Repeatable`. Developers can then represent each value with a separate annotation:

```java
@Role("reader")
@Role("writer")
class ReportService {
}
```

The advantage is the **one-annotation-per-application** structure; each application carries a set of attributes such as `name`, `scope`, and `priority`. It is easy for readers to add or remove a rule without editing a large array.

However, `@Repeatable` **does not work on its own without declaring a suitable container**. To make the `Role` type repeatable, Java requires a **containing annotation** whose `value()` element returns a **`Role[]` array**.

Declaration skeleton:

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

Here:

- `Role` is **the annotation to be repeated**.
- `Roles` is the **container annotation** storing the set of `Role` annotations.
- `@Repeatable(Roles.class)` links the two annotation types.
- The `Roles.value()` element has the exact type `Role[]`, allowing Java to represent multiple `@Role` occurrences at the same location.

When `@Role` is used twice, the source code still shows two independent annotations, while the compiler handles the corresponding representation through the container according to the language rules. Some details depend on retention and target, which will be examined in the complete example below.

## 5. Runnable Java 17+ Example: Two Roles on the Same Class

Create **a single file `RepeatableProblemDemo.java`** containing the full code:

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

@Role("reader")
@Role("writer")
class ReportService {
}

public class RepeatableProblemDemo {
    public static void main(String[] args) {
        Role[] roles = ReportService.class.getAnnotationsByType(Role.class);

        System.out.println("count=" + roles.length);
        for (Role role : roles) {
            System.out.println("role=" + role.value());
        }

        boolean hasContainer =
                ReportService.class.getAnnotation(Roles.class) != null;
        System.out.println("container=" + hasContainer);
    }
}
```

Compile/run in the directory containing the file with JDK 17 or later:

```bash
javac -encoding UTF-8 RepeatableProblemDemo.java
java RepeatableProblemDemo
```

**stdout output:**

```text
count=2
role=reader
role=writer
container=true
```

Step-by-step explanation:

1. `@Repeatable(Roles.class)` allows writing the same `@Role` annotation multiple times on **a single class**.
2. `@Target(ElementType.TYPE)` on both annotation types restricts placing them to type declarations such as `class ReportService`.
3. Both declarations use `@Retention(RUNTIME)` so that reading metadata via reflection works in the example. If the annotations only have `SOURCE` retention, runtime reflection will not be able to read them.
4. `getAnnotationsByType(Role.class)` can read `Role` annotations whether applied directly or via the container, thereby retrieving the two values `reader` and `writer`.
5. `getAnnotation(Roles.class)` shows that the container is present on the class when `@Role` is used twice. The `true` result does not mean a generator was invoked or an authorization system was activated.

From this example, we can see that **the issue is not whether two strings can be stored** (an array already does that), but rather that Java needs to support **multiple applications of the same annotation type on a single declaration** while maintaining a consistent metadata model.

## 6. Container and Explicit Syntax

With the `Role` and `Roles` types already declared, explicitly applying the container directly is also valid:

```java
@Roles({
    @Role("reader"),
    @Role("writer")
})
class ExplicitContainerService {
}
```

The logical content regarding the two roles is similar to the example applying two `@Role` annotations, though the source syntax differs:

| Syntax | Characteristics |
| --- | --- |
| `@Role("reader")` then `@Role("writer")` | Concise, focused on each rule; requires `Role` to have `@Repeatable(Roles.class)`. |
| `@Roles({@Role("reader"), @Role("writer")})` | Directly writes the container holding `Role[]`. |
| `@Roles({"reader", "writer"})` in section 3 | A **different** model: `Roles.value()` is `String[]`, not `Role[]`. |

Java 7 and earlier versions did not have syntactic support for repeatable annotations as in Java 8, so creating a container annotation holding an array of annotations is an approach to model multiple pieces of information of the same kind.

Note **not to confuse the two `Roles` definitions** across the example sections: section 3 defines `String[] value()`; from section 4 onward, `Roles` is redefined for an independent illustration with **`Role[] value()`**. They must not be copied verbatim into the same file/package as two types with the same name.

## 7. An Annotation Carrying Multiple Attributes: Why Is Repetition Useful?

Suppose each permission requires both `name` and `scope`. Define the repeatable annotation:

```java
import java.lang.annotation.Repeatable;

@Repeatable(AccessRules.class)
@interface AccessRule {
    String name();
    String scope();
}

@interface AccessRules {
    AccessRule[] value();
}
```

When used:

```java
@AccessRule(name = "reader", scope = "/reports")
@AccessRule(name = "writer", scope = "/drafts")
class ReportEndpoint {
}
```

Each annotation represents **a pair of related data**, reducing the risk of mismatch if developers had to maintain two parallel arrays such as `names = {"reader", "writer"}` and `scopes = {"/reports", "/drafts"}`.

This snippet **illustrates declaration and usage**, not a standalone program with `main`; to read it via reflection, you must add an appropriate retention policy to both the repeatable annotation and the container. `AccessRule` is not an actual permission-checking mechanism: the system itself must interpret the metadata and enforce access control.

## 8. Constraints to Remember When Repeating Annotations

Declarations using `@Repeatable` must obey the contract between the repeatable annotation and the container:

- **The container must have `value()` as an array of the exact repeatable annotation type**, for example `Role[] value()`. You cannot declare `String[] value()` for the container of `Role`.
- The container may have other elements, but if it does, they must be declared with default values so Java can create the container representation when repeated.
- **Compatible retention:** the container must not have a shorter retention than the repeatable annotation. If `Role` is `RUNTIME` while `Roles` only has `SOURCE` retention, the compiler will reject the invalid repeatable declaration.
- **Compatible target:** the container must allow the locations where the repeatable annotation is permitted to be used; cases involving `TYPE_USE`, `TYPE_PARAMETER`, and `ANNOTATION_TYPE` have detailed compatibility rules according to the Java Language Specification.
- If the repeatable annotation has `@Documented` or `@Inherited`, the container must also satisfy the corresponding constraints according to Java's rules.
- You need to consider the metadata and the API reading it when modifying an annotation already used in a library, because legacy code might look up the annotation using a different reflection API.

To make verification straightforward, the `Role` and `Roles` example places **the same `@Target(TYPE)` and the same `@Retention(RUNTIME)`**. That pair of declarations is valid and sufficient for annotating classes.

### Reflection: Reading Single or Multiple Occurrences?

For an annotation **used multiple times** such as `@Role("reader") @Role("writer")`, you should use:

```java
Role[] roles = ReportService.class.getAnnotationsByType(Role.class);
```

If you call:

```java
Role one = ReportService.class.getAnnotation(Role.class);
```

on a class that has **two `Role` annotations repeated via a container** as in the example, the result will be `null` because `getAnnotation` only looks for annotations of type `Role` that are directly present or present via supported inheritance, whereas the two `Role` annotations are represented through the `Roles` container. `getAnnotationsByType` adds the ability to look through the container for repeatable annotations.

If the class has only **one** `@Role("reader")`, the compiler may keep a single `Role` annotation directly and `getAnnotation(Role.class)` may return that value. Therefore, processing code that wants to support both single and multiple applications should choose `getAnnotationsByType`.

For examples that do not use inheritance, `getDeclaredAnnotationsByType(Role.class)` also returns the `Role` applications declared on the class itself. Lookup by inheritance between a superclass and a subclass also depends on `@Inherited` and reflection rules; you should not assume every annotation is automatically inherited.

## 9. Avoid Confusion: Multiple Elements in One Annotation Differ from Repeatable Annotations

The following example also has **multiple values**, but it is not a repeatable annotation:

```java
@interface RequestConfig {
    String path();
    String method() default "GET";
    int timeoutMs() default 1000;
}

@RequestConfig(path = "/reports", method = "POST", timeoutMs = 1500)
class ReportRequest {
}
```

Here there is a single `@RequestConfig` with **three differently named elements**. This does not require `@Repeatable`; the name–value pairs belong to the same annotation instance.

A true repetition case must be **multiple uses of the same annotation name** at the same location:

```java
@Role("reader")
@Role("writer")
class ReportService {
}
```

In the example with a valid container, the two uses of `Role` have the same type name, while each has its own data.

| Need | Typical syntax | Model |
| --- | --- | --- |
| A declaration has multiple **differently named attributes** | `@Config(path = "/x", timeout = 500)` | A single annotation with multiple elements. |
| An attribute holds **multiple strings** | `@Labels({"a", "b"})` | A single annotation with an array element. |
| The same kind of information appears **multiple times independently** | `@Role("a")` + `@Role("b")` | Multiple applications of the same repeatable annotation type. |

These are three different problems; adding `@Repeatable` is only necessary for the third case.

## 10. Common Mistakes

| Error or misconception | How to fix |
| --- | --- |
| Applying two `@Role` annotations when `Role` does not yet have `@Repeatable` | Define a valid container and add `@Repeatable(Roles.class)` to `Role`. |
| Thinking that different values alone allow repeating the same annotation | The compiler checks the **annotation type**, not just the values. |
| Container declares `String[] value()` | For `@Repeatable(Roles.class)` on `Role`, it must be **`Role[] value()`**. |
| Container retention is lower than the repeatable annotation's retention | Choose compatible retention policies; for example, both are `RUNTIME`. |
| Using `getAnnotation(Role.class)` when multiple `Role` annotations are present | Use `getAnnotationsByType(Role.class)` to retrieve the elements inside the container. |
| Confusing `@Roles({"a", "b"})` with `@Roles({@Role("a"), @Role("b")})` | You must check whether `Roles.value()` is `String[]` or `Role[]`; these are two different definitions. |
| Thinking repeatable annotations automatically execute multiple tasks | Annotations only mark metadata; code/frameworks are needed to read and process them. |
| Placing a repeatable annotation at a location disallowed by `@Target` | Check the `@Target` of both the repeatable annotation and the container. |

## 11. Self-Check

Consider the following declarations (each example uses the same `Role` and `Roles` definitions from section 5):

1. `@Role("reader")` on a class: **Valid**, a single application.
2. `@Role("reader") @Role("writer")` on the same class: **Valid** because `Role` has `@Repeatable(Roles.class)`.
3. Two `@Role(...)` annotations on the same class after removing `@Repeatable`: **Invalid**; even with different values, the same annotation type still appears twice directly.
4. `@Roles({@Role("reader"), @Role("writer")})`: **Valid** because the container has `Role[] value()`.
5. `@Role("reader")` applied to a field with `@Target(TYPE)` as in the example: **Invalid**; the target does not permit fields.
6. After repeating two `@Role` annotations on a class, how many elements does calling `getAnnotationsByType(Role.class)` return? **Two**, `reader` and `writer` respectively in the example.

When encountering the requirement “a single location needs multiple annotations”, clarify the type of data to be represented: **a simple list of values** can use one annotation with an array; **multiple independent sets of metadata** are suited for a repeatable annotation with a container. Whichever approach you choose, the usage location must match `@Target`, the value types must be valid for the annotation elements, and the business semantics require a dedicated processor.

References: [Java Language Specification 21 – Sections 9.6 Annotation Interfaces and 9.7 Annotations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html); [Java SE 21 API – `java.lang.annotation.Repeatable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/Repeatable.html).
