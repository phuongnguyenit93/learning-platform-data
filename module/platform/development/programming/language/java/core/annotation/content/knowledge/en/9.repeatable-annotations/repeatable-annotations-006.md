# Rules for Coordinating Repeatable Annotations with Containing Annotations in Java

## 1. Two Annotation Types Involved in the Repeatable Mechanism

In Java, a regular annotation cannot appear multiple times at the same declaration site or in the same type-use context. To write multiple annotations **of the same type** on a single element, you use the *repeatable annotation* mechanism introduced in Java 8.

That mechanism requires two annotation types working together:

- **Repeatable annotation:** the type that a developer wants to write multiple times, for example `@Role("READ")` and `@Role("WRITE")`.
- **Containing/container annotation:** a separate annotation type that has a `value()` element returning a **one-dimensional array of the exact repeatable annotation type**, for example `Role[] value();` in `@Roles`.

Basic example:

```java
import java.lang.annotation.Repeatable;

@Repeatable(Roles.class)
@interface Role {
    String value();
}

@interface Roles {
    Role[] value();
}

@Role("READ")
@Role("WRITE")
class AccountService {}
```

Here `Role` is the repeatable annotation type; `Roles` is the containing type. When encountering two `@Role` annotations on the same class, the compiler treats them as an **implicitly declared container annotation** whose `value` holds the `@Role` uses in the order they appear.

The logical result can be pictured as:

```java
@Roles({
    @Role("READ"),
    @Role("WRITE")
})
class AccountService {}
```

The two versions above are equivalent for the purpose of retrieving `Role` annotations under the repeatable mechanism. However, **the source syntax and the result when calling specific reflection APIs can differ between a single annotation and a container**. A later section distinguishes this clearly.

Keep in mind: `@Repeatable` only indicates the **container type**. It does not generate the `Roles` type automatically, and it only takes effect when `Roles` satisfies all of Java's validity rules.

## 2. First Rule: The Container Must Have `value()` Returning Exactly `T[]`

For a repeatable annotation named `T` and a container named `TC`, the required element in the container structure is:

```java
T[] value();
```

A valid definition:

```java
import java.lang.annotation.Repeatable;

@Repeatable(Alerts.class)
@interface Alert {
    String message();
}

@interface Alerts {
    Alert[] value();
}
```

The following container declarations are **intentionally invalid**; examine each case separately:

```java
// Invalid: no value() element
@interface WrongContainerA {
    Alert[] items();
}

// Invalid: value() has type Object[], not Alert[]
@interface WrongContainerB {
    Object[] value();
}

// Invalid: value() returns a single Alert instead of Alert[]
@interface WrongContainerC {
    Alert value();
}

// Invalid: two-dimensional array is not a valid annotation element type
@interface WrongContainerD {
    Alert[][] value();
}
```

The example above uses `Alert` as an existing annotation type; the `WrongContainer...` types are not selected via `@Repeatable` in the valid example. If you change `@Repeatable(Alerts.class)` to `@Repeatable(WrongContainerA.class)`, the compiler will detect that the container is invalid.

One easily confused detail: `@Repeatable(Alerts.class)` takes the **class literal of the containing annotation type**, not an `@Alerts(...)` instance or the name string `"Alerts"`.

The container name is usually the plural form of the repeatable annotation name (`Role`/`Roles`, `Tag`/`Tags`), but that is only a convention. The compiler relies on the exact type in `@Repeatable(....class)` and the return type of `value()`.

## 3. Second Rule: Additional Container Elements Must Have Defaults

A container **may have additional elements**, but every element other than `value()` **must declare `default`**.

Valid:

```java
import java.lang.annotation.Repeatable;

@Repeatable(Permissions.class)
@interface Permission {
    String action();
}

@interface Permissions {
    Permission[] value();
    String source() default "policy";
    boolean verified() default false;
}
```

When the compiler generates an implicit container upon seeing multiple `@Permission` annotations, there is nowhere for the user to supply `source` or `verified`; the default values allow the container to still be formed validly.

Invalid:

```java
@interface InvalidPermissions {
    Permission[] value();
    String source(); // Invalid when selected as a container: missing default
}
```

`InvalidPermissions` by itself can be a valid annotation type, but it is **not eligible to serve as the container for `Permission`** if specified in `@Repeatable(InvalidPermissions.class)`, because `source()` has no default.

If you need to pass custom values to the container, you can use the container **explicitly**:

```java
@Permissions(
    value = {
        @Permission(action = "READ"),
        @Permission(action = "WRITE")
    },
    source = "security-config",
    verified = true
)
class DocumentService {}
```

Distinction:

- Writing repeated `@Permission(...)`: the compiler generates an implicit container; the additional elements use `default`.
- Writing `@Permissions(...)`: the developer specifies the container and can pass the additional elements using standard annotation syntax.

You should not add additional elements to a container unless they have a clear purpose; they can cause metadata differences between the repeated syntax and an explicit container.

## 4. Third Rule: The Container's `@Retention` Must Not Be Shorter Than That of the Repeatable Annotation

`@Retention` determines up to which stage an annotation is retained. The lifecycle order by retention level is:

```text
SOURCE  <  CLASS  <  RUNTIME
```

**The container must be retained at least as long as the repeatable annotation**.

| Retention of repeatable annotation `T` | Valid retention of container `TC` |
|---|---|
| `SOURCE` | `SOURCE`, `CLASS`, `RUNTIME` |
| `CLASS` | `CLASS`, `RUNTIME` |
| `RUNTIME` | Only `RUNTIME` |

Valid and convenient for reflection:

```java
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Labels.class)
@interface Label {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@interface Labels {
    Label[] value();
}
```

Invalid:

```java
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@Repeatable(BrokenLabels.class)
@interface BrokenLabel {
    String value();
}

@Retention(RetentionPolicy.CLASS)
@interface BrokenLabels {
    BrokenLabel[] value();
}
```

In the invalid snippet, the repeatable annotation needs to persist until `RUNTIME`, whereas the container only has `CLASS`. The compiler rejects this because when repeated multiple times, the `BrokenLabel` instances held inside `BrokenLabels` cannot be properly retained until runtime through the container.

**Default note:** If `@Retention` is omitted, Java uses `RetentionPolicy.CLASS`. For instance, giving `T` a `RUNTIME` retention while omitting `@Retention` on `TC` is an error because `TC` then defaults to `CLASS`.

In practical designs, using the **same retention** for both is usually simpler, easier to maintain, and avoids discrepancies in observed behavior. Java's rules allow the container to be retained longer, but that does not make every annotation in every context automatically visible via reflection if the repeatable annotation itself does not have `RUNTIME` retention.

## 5. Fourth Rule: `@Target` Must Be Compatible, and the Repeated Site Must Allow Both

`@Target` specifies where an annotation may be used. For the two types `T` and `TC`:

- The container `TC` must not allow target kinds that `T` does not allow according to the JLS compatibility rules (there are special subsumption relationships among `TYPE_USE`, `TYPE`, `TYPE_PARAMETER`, and `ANNOTATION_TYPE`).
- **To repeat `@T` at a specific site, both `T` and the container `TC` must be applicable at that site.**
- The container is allowed to be **narrower** than the repeatable annotation. In that case, `@T` can be used **once** in many places, but can only be **repeated multiple times** at sites where the container is also permitted to appear.

The most common and straightforward configuration: place the same `@Target` on both.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Repeatable(RetryPolicies.class)
@interface RetryPolicy {
    int attempts();
}

@Target(ElementType.METHOD)
@interface RetryPolicies {
    RetryPolicy[] value();
}

class NetworkClient {
    @RetryPolicy(attempts = 2)
    @RetryPolicy(attempts = 3)
    void connect() {}
}
```

Example of a narrower container:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Target;

@Target({ElementType.TYPE, ElementType.METHOD})
@Repeatable(AuditTags.class)
@interface AuditTag {
    String value();
}

@Target(ElementType.TYPE)
@interface AuditTags {
    AuditTag[] value();
}

@AuditTag("service")
@AuditTag("critical")
class PaymentService {
    @AuditTag("traced")
    void pay() {}
}
```

Here:

- Two `@AuditTag` annotations on `PaymentService` are **valid**: `TYPE` is included in both targets.
- One `@AuditTag` on `pay()` is **valid**: `METHOD` is permitted by `AuditTag`.
- Two `@AuditTag` annotations on the same `pay()` are **invalid**: the container `AuditTags` does not permit `METHOD`, so the compiler cannot generate the container on the method.

Conversely, placing `@Target({TYPE, FIELD})` on the container when the repeatable annotation only has `@Target(TYPE)` will be rejected right at the repeatable **definition**, because the container expands the allowed sites beyond the type it contains.

Special target relationships in JLS `9.6.3` allow certain forms of subsumption—for example, an annotation applicable to `TYPE` is also applicable to an annotation type declaration; `TYPE_USE` covers many type contexts. When encountering `TYPE_USE`/`TYPE_PARAMETER`, you should check the JLS rules directly and test writing code at the **exact site** where repetition is needed, rather than reasoning solely from the enum names.

If the goal is to allow repetition at every site that `T` permits, design the container's `@Target` accordingly. There is no requirement that the two target sets **must be completely identical**.

## 6. Fifth Rule: `@Documented` and `@Inherited` Must Be Synchronized in One Direction

Java imposes two additional meta-annotation constraints:

1. **If the repeatable annotation `T` has `@Documented`, the container `TC` must also have `@Documented`.**
2. **If the repeatable annotation `T` has `@Inherited`, the container `TC` must also have `@Inherited`.**

Valid example:

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Policies.class)
@interface Policy {
    String value();
}

@Documented
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Policies {
    Policy[] value();
}
```

This ensures that the implicit container does not lose the documentation/inheritance properties declared by `Policy`.

**The reverse direction is not required:** A container may carry `@Documented` or `@Inherited` while the repeatable annotation does not. However, you should only design it that way when you clearly understand the impact on documentation and reflection, because behavior can differ between the direct annotation and the container.

Meaning of the two meta-annotations:

- `@Documented` is a signal for Javadoc to include the annotation in API documentation according to the corresponding rules; it does not change retention.
- `@Inherited` affects annotation lookup via a **class's superclass**, according to the APIs/conditions defined by Java; it does not automatically propagate annotations on methods, fields, interfaces, or packages.
- When inheritance needs to be observed via reflection, an appropriate retention is required, typically `RUNTIME` for both `T` and `TC`.

A configuration missing `@Inherited` on the container when `T` has `@Inherited` will be rejected by the compiler right at the definition of `T`. The same applies to `@Documented`.

## 7. How Does the Compiler Combine Repeated Uses into a Container?

Consider again:

```java
import java.lang.annotation.Repeatable;

@Repeatable(Checks.class)
@interface Check {
    String value();
}

@interface Checks {
    Check[] value();
}

@Check("syntax")
@Check("semantic")
@Check("performance")
class Report {}
```

At the declaration site of `Report`, the three annotations of the same type `Check` are transformed by the compiler into **one implicit container** with three elements in `value()`. The order of the `@Check` uses is preserved:

```java
@Checks({
    @Check("syntax"),
    @Check("semantic"),
    @Check("performance")
})
class Report {}
```

The two snippets above represent the same sequence of repeated values, but are merely **two alternative ways of writing it**. Do not place both sets of declarations on the same class.

Key points:

- A single use of `@Check("syntax")` does not need to generate an implicit container just because `Check` is declared repeatable.
- Starting from two or more uses in the same applicable context, the compiler uses an implicit container.
- Annotations of other types may appear between the `@Check` uses; the `Check` annotations still form a sequence in the order they appear.
- You should not think of a "repeatable annotation" as the JVM storing multiple direct annotations of the same type that reflection can always see via `getAnnotations()`. The format/container and the query APIs are parts of the same mechanism.

The repeatable mechanism also applies in type-use contexts when the target permits, not only on class declarations. The example above uses a class so it is easy to inspect with reflection.

## 8. Writing an Explicit Container: Possibilities and Limits

Besides writing repeated annotations directly:

```java
@Check("syntax")
@Check("semantic")
class DirectRepeats {}
```

Developers can write the container explicitly:

```java
@Checks({
    @Check("syntax"),
    @Check("semantic")
})
class ExplicitContainer {}
```

This is valid syntax when `Check` and `Checks` have been defined according to the rules in section 7. Some frameworks or libraries may generate an explicit container annotation during source generation; when reading annotations, you need to handle both representations.

### Combining One `@T` and One `@TC`

The following case **can be valid**:

```java
@Check("fast")
@Checks({@Check("secure"), @Check("stable")})
class MixedAllowed {}
```

It consists of **one** direct `Check` annotation and **one** explicit `Checks` container. No implicit container needs to be generated because `Check` appears directly only once.

However, this mixed style can easily cause readers to confuse the results of `getAnnotation` and `getAnnotationsByType`. In regular code, you should choose a consistent style unless there is a specific reason.

### Combining Two `@T` Annotations with One `@TC` Is an Error

```java
// INTENTIONALLY INVALID: 2 direct @Check annotations + one explicit @Checks
@Check("a")
@Check("b")
@Checks({@Check("c")})
class MixedInvalid {}
```

Because two `@Check` annotations already require an **implicit container**, the presence of an explicit `@Checks` at the same site causes a conflict. Java forbids having multiple repeatable `T` annotations together with the container annotation `TC` in the same context.

When the container structure is itself repeatable, the JLS also forbids combining **one** direct `@T` with **multiple** `@TC` annotations in the same context. These cases are language restrictions, not bugs in a specific framework.

Tip to avoid ambiguity: If you want the list `a, b, c`, write:

```java
@Check("a")
@Check("b")
@Check("c")
class AllDirect {}
```

or:

```java
@Checks({@Check("a"), @Check("b"), @Check("c")})
class AllContained {}
```

## 9. Choosing the Right Reflection API to Read Repeatable Annotations

If the retention is `RUNTIME`, Java reflection allows looking up annotations on the appropriate class/method/field. For repeatable annotations, there are two important API groups:

- `getAnnotation(T.class)` and `getDeclaredAnnotation(T.class)`: look up **a single** annotation of type `T` according to the direct/present rules. They **do not automatically unpack a container** into multiple `T` instances.
- `getAnnotationsByType(T.class)` and `getDeclaredAnnotationsByType(T.class)`: return an **array** of `T` annotations applied directly or **indirectly contained inside a container** according to the API rules. This is the usual choice for reading repeatable annotations.

When there is an implicit container resulting from writing two or more `@T` annotations, `getAnnotation(T.class)` is typically `null` on that declaration; `getAnnotationsByType(T.class)` returns the `T` annotations contained in the container in order.

If you want to query the **container itself**, call `getAnnotation(TC.class)`. In the case where there is only a single direct `@T`, the container is usually not present, so `getAnnotation(TC.class)` can be `null`.

`getDeclaredAnnotationsByType` focuses on annotations declared directly on the element itself; `getAnnotationsByType` also has the appropriate inheritance behavior when the annotation has `@Inherited` and the queried element is a class. Do not use `getAnnotation(T.class)` as a way to count repeatable annotations.

### Standalone Runnable Java 17+ Example

Create the file **`RepeatableContainerDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

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
    String source() default "declared";
}

@Role("read")
@Role("write")
class AccountService {}

@Role("read")
class CatalogService {}

@Roles({@Role("audit"), @Role("notify")})
class BatchService {}

public class RepeatableContainerDemo {
    private static void inspect(Class<?> type) {
        Role[] roles = type.getAnnotationsByType(Role.class);
        String[] names = Arrays.stream(roles)
                .map(Role::value)
                .toArray(String[]::new);

        System.out.println(type.getSimpleName() + ": "
                + Arrays.toString(names));
        System.out.println("direct="
                + (type.getAnnotation(Role.class) != null)
                + ", container="
                + (type.getAnnotation(Roles.class) != null));
    }

    public static void main(String[] args) {
        inspect(AccountService.class);
        inspect(CatalogService.class);
        inspect(BatchService.class);
    }
}
```

Compile and run from the directory containing the file with JDK 17+:

```bash
javac RepeatableContainerDemo.java
java RepeatableContainerDemo
```

Stdout:

```text
AccountService: [read, write]
direct=false, container=true
CatalogService: [read]
direct=true, container=false
BatchService: [audit, notify]
direct=false, container=true
```

Explanation:

1. The two `@Role` annotations on `AccountService` are stored via the implicit `Roles` container. `getAnnotationsByType(Role.class)` unpacks the container into two `Role` elements.
2. A single `@Role` on `CatalogService` is declared directly. `getAnnotation(Role.class)` finds it; no container needs to be present.
3. `BatchService` uses `@Roles` explicitly. The `getAnnotationsByType(Role.class)` API still returns the `Role` instances inside `Roles.value()`.
4. The `source() default "declared"` value is valid because every additional container element has a default.

The example uses three different classes to clearly compare the cases. None of the classes places both an explicit container and multiple direct repeatable annotations at the same site.

## 10. Distinguishing "Directly Present", "Indirectly Present", "Present", and "Associated"

When reading Java reflection documentation, you should recognize several technical terms:

- **Directly present:** an annotation of type `T` declared directly on the element being inspected.
- **Indirectly present (via a container):** a container `TC` directly holds `T` annotations in `value()`, and the `T` annotations are recognized under the repeatable mechanism.
- **Present/associated:** Java reflection terms that include rules related to class inheritance under certain conditions.
- **Declared:** prioritizes annotations on the declaration itself, without relying on the superclass as APIs without `Declared` in their name do.

In practice, what is usually needed is to **retrieve all repeatable values** with `getAnnotationsByType`, then process the resulting array. If you only use `getAnnotation`, the code may work when there is one `@T` but "lose" data when a second `@T` is added because the compiler has switched the representation to a container.

With class inheritance, `@Inherited` also affects lookup: a subclass that does not declare the relevant annotation can be treated as having the repeatable annotation from its superclass via `getAnnotationsByType`. However, when the subclass already has a group of `T` annotations directly or in a container according to the API rules, all `T` annotations from the superclass are not automatically accumulated unconditionally into the result. If you need "merge across the entire inheritance hierarchy" semantics, you must write custom business logic.

Annotation inheritance here does not apply automatically to method overrides, interface implementations, or packages.

## 11. Common Compilation Errors in a `T` and `TC` Pair

### 11.1. Writing Only `@Repeatable` Without Declaring the Container

```java
import java.lang.annotation.Repeatable;

@Repeatable(Tags.class)
@interface Tag {
    String value();
}
// Invalid: the annotation type Tags does not exist
```

The compiler needs to resolve `Tags.class` and verify that it is actually a valid containing annotation type. You need to declare `@interface Tags { Tag[] value(); }` or reference the right name.

### 11.2. Container Returns the Wrong Type

```java
import java.lang.annotation.Repeatable;

@Repeatable(Items.class)
@interface Item {
    String value();
}

@interface Items {
    String[] value(); // Invalid: must be Item[]
}
```

`String[]` is a valid annotation element type in general, but it is **not** the correct `value()` type for the container of `Item`.

### 11.3. Container Has a Required Additional Element

```java
import java.lang.annotation.Repeatable;

@Repeatable(Flags.class)
@interface Flag {
    String value();
}

@interface Flags {
    Flag[] value();
    String owner(); // Invalid: container adds an element without a default
}
```

Change it to `String owner() default "unknown";` if you actually need that element, or remove the additional element.

### 11.4. `@Retention` Mismatch

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Events.class)
@interface Event {
    String value();
}

@Retention(RetentionPolicy.SOURCE)
@interface Events {
    Event[] value();
}
```

Invalid: the `SOURCE` container is shorter than the `RUNTIME` repeatable annotation.

### 11.5. Container Widens `@Target`

```java
import java.lang.annotation.*;

@Target(ElementType.METHOD)
@Repeatable(Marks.class)
@interface Mark {
    String value();
}

@Target({ElementType.METHOD, ElementType.FIELD})
@interface Marks {
    Mark[] value();
}
```

Invalid: the container allows `FIELD`, but the `Mark` annotation cannot be applied to `FIELD`. Change the container's target to `METHOD` if repetition is only needed on methods.

### 11.6. Missing Corresponding `@Documented` or `@Inherited`

When `T` has `@Documented` and `TC` does not, or `T` has `@Inherited` and `TC` does not, Java rejects the definition of this pair. Fix it by placing the corresponding meta-annotation on the container, if that is the intent of `T`.

### 11.7. Using Two Direct Annotations and an Explicit Container

```java
// With Item and Items properly declared:
@Item("a")
@Item("b")
@Items({@Item("c")})
class InvalidMix {}
```

Invalid because it simultaneously requires an implicit container for the two `@Item` annotations and has an explicit `@Items` container. Combine all elements into either the repeated syntax or a single explicit container.

### 11.8. Using the Wrong Reading API

The following logic usually fails to achieve the goal of retrieving **all** repeatable annotations:

```java
Role role = AccountService.class.getAnnotation(Role.class);
```

When `AccountService` has two `@Role` annotations, `role` will be `null` because the `Role` annotations are contained inside `@Roles`. Fix it with:

```java
Role[] roles = AccountService.class.getAnnotationsByType(Role.class);
```

The two snippets are merely for comparison and use the types declared in section 9.

## 12. How to Design a Maintainable Repeatable Annotation and Container Pair

A practical workflow:

1. Give **`T`** a meaningful singular name, such as `@Route` or `@Permission`, and give **`TC`** a collective name such as `@Routes` or `@Permissions`.
2. Define the elements on `T` first, ensuring each element has a valid annotation element type.
3. In `TC`, create exactly `T[] value();`.
4. If `TC` has additional elements, provide a `default` for all of them.
5. Apply `@Repeatable(TC.class)` on `T`.
6. Decide on retention based on the metadata consumer; usually place the same retention on both `T` and `TC`.
7. Decide on the target based on the sites where **repetition** is needed, usually placing the same `@Target` on both; if the container is narrower, clearly document the sites that can only be used once.
8. If `T` has `@Documented` or `@Inherited`, place those annotations on `TC`.
9. If the application uses runtime reflection, read the array with `getAnnotationsByType(T.class)`.
10. Test all cases: a single `@T`, multiple `@T` annotations, an explicit `@TC`, and invalid mixed cases.

In a public API, changing the container type, the `value()` return type, retention, or target can break client compilation or cause frameworks to read metadata differently than before. Compatibility checks are needed when upgrading library versions.

Even if the container has additional metadata, avoid forcing users to guess how values are combined between the container and individual child annotations. If accumulative semantics are needed, prefer an explicit representation and document the consumer rules.

## 13. Practice Exercises

Suppose you have the following declarations:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@Repeatable(Rules.class)
@interface Rule {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Rules {
    Rule[] value();
    String source() default "manual";
}
```

Determine which scenarios are valid:

1. One `@Rule("read")` on a class.
2. Two annotations `@Rule("read")` and `@Rule("write")` on the same class.
3. One `@Rule("read")` on a method.
4. Two annotations `@Rule("read")` and `@Rule("write")` on the same method.
5. `@Rules({@Rule("read"), @Rule("write")})` on a class.
6. One `@Rule("read")` together with one `@Rules({@Rule("write")})` on a class.
7. Two `@Rule` annotations together with one `@Rules` on a class.
8. If the `@Retention` of `Rules` is changed to `SOURCE`, is the annotation pair still valid?
9. If `Rules.value()` is changed to `String[] value()`, is the annotation pair still valid?
10. When two `@Rule` annotations are on a class, is `getAnnotation(Rule.class)` sufficient to read both?

Answers:

1. **Valid:** `Rule` is applicable to `TYPE`.
2. **Valid:** both `Rule` and `Rules` are applicable to `TYPE`, and the compiler generates an implicit container.
3. **Valid:** `Rule` is applicable to `METHOD` and appears only once.
4. **Invalid:** `Rules` is not applicable to `METHOD`, so it cannot hold two `@Rule` annotations on a method.
5. **Valid:** the explicit container is valid on `TYPE`.
6. **Valid:** one direct `@Rule` and one explicit `@Rules` can coexist.
7. **Invalid:** two direct `@Rule` annotations require an implicit container, which conflicts with the explicit container.
8. **No:** `SOURCE` is shorter than `Rule`'s `RUNTIME`.
9. **No:** the container requires `Rule[] value()`, not `String[]`.
10. **No:** use `getAnnotationsByType(Rule.class)` to retrieve all repeated elements.

## 14. Final Checklist

- The repeatable annotation `T` has `@Repeatable(TC.class)`, where `TC` exists and is a valid annotation type.
- The container `TC` declares `T[] value();` exactly.
- Every element other than `value()` in the container has a `default`.
- The container's retention is **no shorter than** `T`'s retention; do not forget the `CLASS` default when `@Retention` is omitted.
- The container's target falls within a scope compatible with `T`'s target; to allow repetition at a site, **both** must be applicable there.
- If `T` has `@Documented` or `@Inherited`, `TC` must also have the corresponding meta-annotation.
- Two or more `@T` annotations at the same site create an **implicit container**, preserving the order of the `T` annotations.
- One direct `@T` may appear alongside one explicit `@TC`, but do not place **multiple `@T`** alongside a `@TC` in the same context.
- To read all repeatable annotations at runtime, choose `getAnnotationsByType(T.class)` with an appropriate `RUNTIME` retention.
- `getAnnotation(T.class)` does not unpack the container, so it can return `null` when `T` appears repeatedly.
- Do not assume `@Inherited` automatically merges all annotations from all superclasses, or applies to methods/interfaces/packages.
- Compiled and verified both the **definitions of the two annotation types** and each actual usage scenario.

Java SE 17 specification reference for detailed rules: *Java Language Specification*, sections **9.6.3 — Repeatable Annotation Interfaces** and **9.7.5 — Multiple Annotations of the Same Interface**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html

Clearly understanding the contract between the repeatable annotation and the containing annotation helps prevent errors right at `@Repeatable`, control where repetition is permitted, preserve metadata across compile/runtime stages, and choose the reflection API that retrieves all values.
