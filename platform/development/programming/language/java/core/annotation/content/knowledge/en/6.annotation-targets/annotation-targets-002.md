# `ElementType.TYPE` and `ElementType.ANNOTATION_TYPE`: targets applied to classes, interfaces, enums, and annotation types

## 1. What to understand: `@Target` controls where annotations can be placed

When **declaring an annotation type** with `@interface`, you can use the `java.lang.annotation.Target` meta-annotation to restrict **the syntactic locations** where that annotation is allowed to be placed. Each option is represented by a constant in the `ElementType` enum.

For Java type declarations, two constants that are easily confused are:

- **`ElementType.TYPE`**: the annotation is allowed to be placed on **type declarations**, including classes (`class`), interfaces (`interface`), enums (`enum`), **annotation types (`@interface`)**, and records (`record`, since Java 16).
- **`ElementType.ANNOTATION_TYPE`**: the annotation is only allowed to be placed on **annotation type declarations** (`@interface`). This is a specialized target commonly seen in *meta-annotations*.

Example of declaring two annotation types:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@interface TypeLabel {
    String value();
}

@Target(ElementType.ANNOTATION_TYPE)
@interface MetaLabel {
    String value();
}
```

These two declarations specify the **valid usage locations** for `@TypeLabel` and `@MetaLabel`. They do not produce any runtime processing yet. `@Target` helps the compiler check placement locations; the metadata processing, if needed, must still be performed by a compiler/processor or library code.

## 2. Scope comparison table

| Annotation placement location | `@Target(TYPE)` | `@Target(ANNOTATION_TYPE)` |
| --- | --- | --- |
| Before a `class Service {}` declaration | Valid | Invalid |
| Before an `interface Repository {}` declaration | Valid | Invalid |
| Before an `enum Status {}` declaration | Valid | Invalid |
| Before an `@interface Audited {}` declaration | **Valid** | **Valid** |
| Before a `record Point(int x, int y) {}` declaration | Valid (Java 16+) | Invalid |
| Before a method declaration | Invalid with `TYPE` alone | Invalid |
| Before a field declaration | Invalid with `TYPE` alone | Invalid |

**Most important point:** `ANNOTATION_TYPE` is a **narrower** target than `TYPE` when considering *declarations*. An annotation type marked with `@Target(TYPE)` **is allowed** to be placed on an `@interface` declaration; there is no need to add `ANNOTATION_TYPE` just to gain that capability.

Conversely, an annotation type that has **only** `@Target(ANNOTATION_TYPE)` cannot be used on regular classes, interfaces, or enums. The code example below will verify both possibilities.

The table only considers **declaration** locations. Syntax that uses a type in expressions, casts, generic type arguments, or `implements` relates to `TYPE_USE`, which is a different concept. `TYPE` does not mean “everywhere a type name appears”.

## 3. `TYPE`: marking a type declaration

Define `@TypeLabel` as shown above and then use it:

```java
@TypeLabel("class")
class PaymentService {}

@TypeLabel("interface")
interface PaymentGateway {}

@TypeLabel("enum")
enum PaymentStatus { NEW, PAID }

@TypeLabel("annotation")
@interface Logged {}

@TypeLabel("record")
record PaymentRequest(String id) {}
```

All of the placement locations above are valid for `ElementType.TYPE` (on a JDK that supports records). Specifically:

- **Class**: `PaymentService` is declared with `class`.
- **Interface**: `PaymentGateway` is declared with `interface`.
- **Enum**: `PaymentStatus` is declared with `enum`. Placing an annotation on an **enum declaration** is different from placing it on **individual enum constants**.
- **Annotation type**: `Logged` is an annotation type declared with `@interface`; it also belongs to the type declaration group, so `TYPE` can be used.
- **Record**: `PaymentRequest` is a record type (Java 16+), which is also a valid target for `TYPE`.

The snippets above **illustrate declaration locations** and must be combined with the `@TypeLabel` definition to compile. A complete standalone example is in Section 5.

### Do not confuse an enum declaration with enum constants

```java
// TYPE applies to the enum declaration:
@TypeLabel("payment-status")
enum Stage { NEW, DONE }
```

If you want to place an annotation on each `NEW` or `DONE`, that is a different location (an enum constant corresponds to the `FIELD` target), not the enum declaration itself. An annotation type with only `@Target(TYPE)` cannot be placed directly on individual enum constants.

Similarly, placing an annotation before the name of a **class declaration** does not mean it can be placed on every field, constructor, or method *inside* that class. Those locations require the appropriate targets such as `FIELD`, `CONSTRUCTOR`, and `METHOD` if you want to support them separately.

## 4. `ANNOTATION_TYPE`: placing only on annotation type declarations

Given the declaration:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.ANNOTATION_TYPE)
@interface MetaLabel {
    String value();
}
```

A **valid** usage location is an `@interface` declaration:

```java
@MetaLabel("used-for-auditing")
@interface Audited {}
```

Some **invalid** examples, used to recognize compiler errors (do not include these in the runnable program file):

```java
// INVALID: MetaLabel only has ANNOTATION_TYPE.
@MetaLabel("service")
class OrderService {}

// INVALID: a regular interface is not an @interface.
@MetaLabel("repository")
interface OrderRepository {}

// INVALID: a regular enum is not an @interface.
@MetaLabel("status")
enum OrderStatus { OPEN, CLOSED }
```

The name `MetaLabel` suggests a common usage: an annotation that **describes another annotation type**. That is precisely the meaning of a *meta-annotation*. For example, standard meta-annotations such as `@Target` and `@Retention` are designed to be applied to **annotation type declarations**.

Three layers must be distinguished:

1. `@MetaLabel` is **declared** as an annotation type with `@Target(ANNOTATION_TYPE)`.
2. `@MetaLabel("used-for-auditing")` is **used** on the `@interface Audited` declaration.
3. `@Audited` (if used on another element and declared to allow it) is **a separate annotation**; it does not implicitly cause that element to directly carry `@MetaLabel`.

For example, if a class has `@Audited`, then `SomeClass.class.getAnnotation(MetaLabel.class)` **does not automatically** look up the meta-annotation through `@Audited`. A framework that wants to infer meta-annotation relationships must actively find the annotation type and inspect the metadata on that type according to its own mechanism. Therefore, `@MetaLabel` does not automatically trigger auditing just because it is placed on `Audited`.

## 5. Standalone Java 17+ example: checking both targets with Reflection

Create the file **`TypeTargetsDemo.java`**. This file includes the definitions of the two annotation types, valid placement locations, and Reflection reading code. No Spring or libraries outside the JDK are needed.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface TypeLabel {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface MetaLabel {
    String value();
}

@TypeLabel("class")
class PaymentService {}

@TypeLabel("interface")
interface PaymentGateway {}

@TypeLabel("enum")
enum PaymentStatus { NEW, PAID }

@TypeLabel("annotation")
@MetaLabel("meta")
@interface Audited {}

@TypeLabel("record")
record PaymentRequest(String id) {}

public class TypeTargetsDemo {
    private static void inspect(Class<?> type) {
        TypeLabel typeLabel = type.getAnnotation(TypeLabel.class);
        MetaLabel metaLabel = type.getAnnotation(MetaLabel.class);

        String typeValue = typeLabel == null ? "-" : typeLabel.value();
        String metaValue = metaLabel == null ? "-" : metaLabel.value();

        System.out.println(type.getSimpleName()
                + " | TYPE=" + typeValue
                + " | ANNOTATION_TYPE=" + metaValue);
    }

    public static void main(String[] args) {
        inspect(PaymentService.class);
        inspect(PaymentGateway.class);
        inspect(PaymentStatus.class);
        inspect(Audited.class);
        inspect(PaymentRequest.class);
    }
}
```

Run in the directory containing the file:

```bash
javac -encoding UTF-8 TypeTargetsDemo.java
java TypeTargetsDemo
```

Stdout output:

```text
PaymentService | TYPE=class | ANNOTATION_TYPE=-
PaymentGateway | TYPE=interface | ANNOTATION_TYPE=-
PaymentStatus | TYPE=enum | ANNOTATION_TYPE=-
Audited | TYPE=annotation | ANNOTATION_TYPE=meta
PaymentRequest | TYPE=record | ANNOTATION_TYPE=-
```

### Why is the output like this?

- `TypeLabel` is declared with `TYPE`, so it is validly placed on **all five** type declarations (class, interface, enum, annotation type, and record).
- `MetaLabel` is declared with `ANNOTATION_TYPE`, so in the program it only validly appears on **`@interface Audited`**.
- `@Retention(RUNTIME)` on both annotation types allows Reflection `getAnnotation(...)` to read the metadata at runtime. Without `RUNTIME`, the example can still compile, but ordinary Reflection lookups will not find the metadata.
- `Audited.class` is a `Class` object describing **the `Audited` annotation type**. Here, `getAnnotation(MetaLabel.class)` reads `@MetaLabel` directly on **the `Audited` declaration**.
- The `"-"` value in the table is a placeholder string when `getAnnotation(...)` returns `null`; it is not a value automatically provided by Java.
- `inspect(...)` takes a `Class<?>`, reads the metadata, and prints the description line. There is no special framework logic; the processing is Java code within the program itself.

Because `TYPE` allows placement on `@interface`, the line `Audited | TYPE=annotation` is practical proof that `TYPE` and `ANNOTATION_TYPE` **overlap at annotation type declarations**.

### Try making a change to see a compile error

Keep the sample file as is, and **try** adding `@MetaLabel("wrong")` before `class PaymentService`. `javac` will reject it because `@MetaLabel` cannot be applied to that kind of declaration. After trying this, revert the change to run the valid example again.

Conversely, if you only remove `@MetaLabel("meta")` before `@interface Audited`, the program still compiles and runs, but the line for `Audited` will display `ANNOTATION_TYPE=-`. This helps distinguish between **whether placement is permitted by `@Target`** and **whether an annotation has actually been placed at a specific location**.

## 6. Differences between `TYPE`, `TYPE_USE`, and `TYPE_PARAMETER`

Constant names containing `TYPE` do not share the same meaning:

| `ElementType` | Primary scope | Illustrative example |
| --- | --- | --- |
| `TYPE` | Declarations of classes, interfaces, enums, annotation types, records | `@TypeLabel("x") class Service {}` |
| `ANNOTATION_TYPE` | `@interface` declarations only | `@MetaLabel("x") @interface Trace {}` |
| `TYPE_USE` | Type use locations according to Java rules | `List<@NonNull String>` or `(@NonNull String) obj` with an appropriate annotation type |
| `TYPE_PARAMETER` | Type parameter declaration locations | `class Box<@TypeParameterMarker T> {}` with an appropriate annotation type |

The examples in the last two rows **only illustrate locations** and require the corresponding annotation declarations to compile. `TYPE_USE` relates to **type contexts** and has some overlap with declaration locations, but it is not synonymous with `TYPE`. You should verify the annotation's exact `@Target` before choosing a placement location.

A concrete example of the difference: if `@TypeLabel` only has `@Target(TYPE)`, using it in `List<@TypeLabel("arg") String>` is **invalid**, because this is a *type argument* location, which requires `TYPE_USE` support rather than just `TYPE`.

When you want an annotation to apply to multiple kinds of locations, you can specify an **array of targets**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target({ElementType.TYPE, ElementType.METHOD})
@interface Marker {}
```

Then `@Marker` can be placed on a type declaration **or** a method declaration. Adding multiple targets is an API design decision: you should only allow locations that are actually supported by consumers. Adding `ANNOTATION_TYPE` to `{TYPE, ANNOTATION_TYPE}` generally does not expand the set of declarations already covered by `TYPE`; it can only clarify intent in documentation/APIs.

## 7. How does `@Target` differ from `@Retention`?

These are two independent questions:

- **`@Target`**: “Where is this annotation allowed **to be placed**?” `TYPE` and `ANNOTATION_TYPE` are answers about *location*.
- **`@Retention`**: “Until which stage is this annotation **retained**?” `SOURCE`, `CLASS`, and `RUNTIME` are answers about *metadata lifecycle*.

An annotation with `@Target(ANNOTATION_TYPE)` but **without** `@Retention(RUNTIME)` is still a valid meta-annotation in terms of placement. However, to read it with `getAnnotation(...)` at runtime, that annotation must be retained with `RUNTIME`. You cannot infer retention from target, or infer target from retention.

When **`@Target` is not declared**, the annotation can be used on many **declaration locations** according to Java's default rules; it does not implicitly extend to type-use locations. When **`@Retention` is not declared**, the default retention is `CLASS`. The two defaults serve different purposes.

## 8. Some design scenarios

### 8.1 Labeling all business types

You want application developers to mark processing classes, contract interfaces, status enums, or annotation types with the same declaration label. `@Target(TYPE)` has a broad enough scope. The processor can decide for itself which types to scan and distinguish `Class.isInterface()`, `Class.isEnum()`, `Class.isAnnotation()`, or `Class.isRecord()`.

**Note:** the target only permits **placement**. It does not guarantee that a framework scans those types or automatically creates beans for every class with the annotation.

### 8.2 Designing an annotation to describe another annotation

You want to define `@BusinessQualifier` exclusively for `@interface` annotations. `@Target(ANNOTATION_TYPE)` expresses the exact boundary: it cannot be accidentally placed directly on a regular business class.

If a consumer needs to find `@BusinessQualifier` through another annotation, you must program/configure a mechanism to look up metadata on the corresponding annotation type. Java Reflection `getAnnotation` on a class does not automatically perform meta-annotation lookup across all levels.

### 8.3 Controlling placement locations to avoid misleading APIs

An annotation used to control processing **intended only for classes** that specifies `@Target(TYPE)` can also be placed on interfaces, enums, annotation types, and records. If the consumer actually handles only regular classes, you need to specify this and add extra checks in the tool/processor or runtime code, rather than mistakenly assuming that `TYPE` means `class` only.

`ElementType` provides **syntactic target groups**, not a filter for every semantic classification (such as “only non-abstract classes”, “only interfaces of module X”). Such rules require additional checks.

## 9. Common mistakes and self-check questions

**Mistake 1: “`TYPE` means classes only.”** False. `TYPE` includes interfaces, enums, annotation types, and records at the declaration level.

**Mistake 2: “To place an annotation on `@interface`, `ANNOTATION_TYPE` is required.”** False. `TYPE` also allows annotation type declaration locations. `ANNOTATION_TYPE` is useful when you want to **restrict it solely to** that location.

**Mistake 3: “An enum constant is a type, so `TYPE` can be placed on individual constants.”** False. An enum constant is a different location; it normally requires the `FIELD` target.

**Mistake 4: “`@Target(TYPE)` also allows annotating the type argument of `List<T>`.”** False. A type argument is a type-use location; it requires `TYPE_USE` support.

**Mistake 5: “A meta-annotation on `@interface Audited` will automatically be applied by Java to every class with `@Audited`.”** False. An annotation placed on an **annotation type** and an annotation placed on a **class** are distinct direct metadata. Meta-annotation inference is the job of a consumer that supports it.

**Self-check 1.** Given `@Target(ElementType.ANNOTATION_TYPE) @interface OnlyMeta {}`. Can `@OnlyMeta` be placed on `interface Gateway`?

Answer: **No**. A regular interface declared with `interface` is not an annotation type declaration with `@interface`.

**Self-check 2.** Given `@Target(ElementType.TYPE) @interface TypeTag {}`. Can `@TypeTag @interface Marker {}` be used?

Answer: **Yes**. An `@interface` declaration is also a type declaration, which belongs to the `TYPE` target.

**Self-check 3.** Why does `@MetaLabel("meta")` appear on `Audited.class` in the running program?

Answer: it is placed **directly** on the `@interface Audited` declaration; the `MetaLabel` type has `@Retention(RUNTIME)`, and the Reflection code calls `getAnnotation(MetaLabel.class)` on `Audited.class` itself.

**Self-check 4.** An annotation with only `@Target(TYPE)` can be used on `@interface` but cannot be used on a method parameter. What controls this difference?

Answer: `@Target` determines the set of **target locations** permitted by the compiler. A method parameter is `PARAMETER`, which is not part of `TYPE`.

**Self-check 5.** If a framework wants to scan only classes with `@TypeLabel`, can it rely solely on `@Target(TYPE)`?

Answer: **No**. `TYPE` is also valid on interfaces, enums, records, and annotation types. The framework needs to check the declaration kind and its own conditions.

When choosing between `TYPE` and `ANNOTATION_TYPE`, ask **does the annotation need to mark all type declarations or only annotation types themselves?** Then clearly determine who will read the metadata and at what point in time; `@Target` only addresses the validity of the placement location.
