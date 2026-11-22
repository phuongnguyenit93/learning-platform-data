# Annotations on Generic Type Arguments and Wildcards in Java

Java allows attaching annotations to **type-use** positions (*type use*), including types between `<...>` in generics, the wildcard `?` itself, and types serving as **upper/lower bounds** of a wildcard. These annotations describe *how a type is used at a specific location*, rather than merely marking a class, field, or method.

For example:

```java
List<@Label("element") String> names;
List<@Label("wildcard") ? extends @Label("upper") Number> numbers;
List<? super @Label("lower") Integer> receivers;
```

These are **illustrative field declarations**; you need to import `java.util.List` and define your own `@Label` with `@Target(ElementType.TYPE_USE)`. Across these three lines, the annotation placement differs:

- `@Label("element")` before `String`: marks the **generic type argument `String`**.
- `@Label("wildcard")` directly before `?`: marks the **wildcard**.
- `@Label("upper")` before `Number`: marks the **upper bound type** in `? extends Number`.
- `@Label("lower")` before `Integer`: marks the **lower bound type** in `? super Integer`.

Even though all of them appear in a field declaration, these are **TYPE_USE annotations at nested positions within a generic type**, not annotations directly on the *field declaration*. Distinguishing the position is key to reading and inspecting metadata accurately.

## 1. Basics: What Is a Type-Use Annotation?

Type-use annotations have been supported by Java since Java 8, together with `ElementType.TYPE_USE`. Minimal definition:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Label {
    String value();
}
```

Meaning:

- `@Target(ElementType.TYPE_USE)` allows the annotation to appear at **type-use contexts** defined by Java, including generic type arguments and wildcards.
- `@Retention(RetentionPolicy.RUNTIME)` allows eligible annotations to be retained in the class file for reading via **annotated type reflection** at runtime.
- The `value()` element provides a string to illustrate the attached information. Java does not interpret the content of this string as a business rule.

If you only declare `@Target(FIELD)`, you can mark a field, but **cannot** use that annotation on `String` inside `List<String>` using the syntax `List<@Label String>`. To mark type positions inside generics, the annotation needs the `TYPE_USE` target.

### Example Comparing Declaration and Type Use

```java
import java.util.List;

// Assume FieldTag only allows FIELD,
// while TypeTag only allows TYPE_USE.
@FieldTag
List<@TypeTag String> names;
```

This is a **non-standalone snippet**; it requires declaring appropriate `FieldTag` and `TypeTag` annotations and placing the field inside a class.

- `@FieldTag` is attached to the **field declaration** named `names`.
- `@TypeTag` is attached to the **`String` type used as a generic type argument**.
- You should not expect `Field.getAnnotation(TypeTag.class)` to read the annotation placed on `String` inside the generic. When reading TYPE_USE metadata, you must go through `Field.getAnnotatedType()` and then the nested type layers.

An annotation declaring only `TYPE_USE` should not simply be understood as an "annotation of every field". Writing it near a field declaration does not mean that metadata belongs to the field declaration.

## 2. Annotations on Generic Type Arguments

Java generics use type arguments such as `List<String>`, `Map<String, Integer>`, or `Optional<User>`. When you want to record metadata for a **specific type argument**, place the annotation before the type being used:

```java
List<@Label("name") String> names;

Map<
    @Label("key") String,
    @Label("value") Integer
> counts;

List<List<@Label("nested-element") String>> nested;
```

These are **illustrative field declarations**, not yet forming a class or runnable program. The annotations appear before:

- `String` in `List<String>`.
- `String` and `Integer` in `Map<String, Integer>`.
- `String` nested **inside** `List<List<String>>`.

Placement within a generic expression matters. The following two declarations carry different metadata:

```java
@Label("outer")
List<String> first;

List<@Label("inner") String> second;
```

These are **two illustrative fields**, with `Label` allowing `TYPE_USE`.

- `@Label("outer")` is placed before `List<String>` to annotate the **List** type-use position of field `first`.
- `@Label("inner")` is placed directly before `String` to annotate the **String type argument** of field `second`.

The fact that both fields have the visible Java type `List<String>` does not make the metadata at the two positions equivalent. A tool processing type annotations must know **which position** is annotated.

### Type Arguments Are Not Type Parameter Declarations

Distinguish:

```java
class Box<T> { }                       // Type parameter T declaration.

class Demo {
    Box<@Label("actual-argument") String> box;
}
```

This is an **illustrative snippet**, assuming `Label` is already defined.

- `T` in `class Box<T>` is a **type parameter declaration**.
- `String` in `Box<String>` is a **type argument use** at a usage site of `Box`.

The target `ElementType.TYPE_PARAMETER` exists specifically for **type parameter declarations**, whereas `TYPE_USE` is for type-use contexts and is also allowed at certain type parameter declaration positions according to Java rules. When your use case involves annotating **concrete type arguments** such as `Box<@Label String>`, check for `TYPE_USE`.

## 3. Wildcards: Annotations on the ? Token Itself

A type argument can be a concrete type or a **wildcard**. Wildcard syntax according to the Java Language Specification has the form:

```text
{Annotation} ? [WildcardBounds]

WildcardBounds can be:
    extends ReferenceType
    super ReferenceType
```

The `?` token represents an unknown type subject to certain constraints. To annotate a **wildcard**, place the annotation **directly before the question mark**:

```java
List<@Label("any") ?> anyList;

List<@Label("source") ? extends Number> source;

List<@Label("destination") ? super Integer> destination;
```

These are **illustrative field declarations** with TYPE_USE annotations. All three annotations above are attached to the **wildcard**, not directly to `Number` or `Integer`.

Distinguish this clearly from:

```java
List<? extends @Label("numeric-upper-bound") Number> source;
List<? super @Label("integer-lower-bound") Integer> destination;
```

Here, the annotation appears **after `extends` or `super`**, before the type name, so the metadata belongs to the **bound type**, not to the wildcard node `?`.

Both levels can be written simultaneously:

```java
List<@Label("wildcard") ? extends @Label("upper-bound") Number> values;
```

Within a single declaration:

- `@Label("wildcard")` belongs to the wildcard.
- `@Label("upper-bound")` belongs to the `Number` type serving as the upper bound.
- Having two different values is intentional; reflection can retrieve them separately.

### Wildcard and Generic Semantics Remain Unchanged

For example, `List<? extends Number>` is commonly used when an API needs to read `Number`-compatible values without knowing the concrete type argument. `List<? super Integer>` is used when a suitable container type is needed to insert `Integer` values.

Those are Java's **variance/generic rules**; annotations do not replace these rules.

```java
// Illustrates Java methods with wildcards;
// requires importing java.util.List.
static double firstValue(List<? extends Number> source) {
    return source.get(0).doubleValue();
}

static void addOne(List<? super Integer> destination) {
    destination.add(1);
}
```

If you attach `@Label` to a wildcard or bound, the Java compiler by default **does not automatically turn that label into a business constraint**. For example, placing the label `"non-null"` does not automatically make Java check for null. To check nullability or data flow, you must use a tool that understands that specific annotation, such as a corresponding static analysis/checker.

## 4. Three Metadata Layers: Container, Wildcard, and Bound

Consider a declaration:

```java
List<@Label("wild") ? extends @Label("bound") Number> numbers;
```

You can visualize the type structure as:

```text
Field numbers
└── parameterized type: List<...>
    └── type argument: wildcard ?
        ├── annotation on '?': @Label("wild")
        └── upper bound: Number
            └── annotation on Number: @Label("bound")
```

Library authors processing annotations should not just "look for `@Label` on the field" but must know the target:

| Position | Element reflecting metadata | Example |
| --- | --- | --- |
| Field declaration | `Field` and `Field.getAnnotation(...)` | Annotation declared with `@Target(FIELD)` |
| Declared field type | `Field.getAnnotatedType()` | Annotation on the `List` type-use position |
| Type argument `String` | `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` | `List<@Label String>` |
| Wildcard `?` | `AnnotatedWildcardType` representing the wildcard argument | `List<@Label ?>` |
| Bound `Number` / `Integer` | `getAnnotatedUpperBounds()` / `getAnnotatedLowerBounds()` | `? extends @Label Number` |

These APIs were added to reflect annotations **on type uses**. Calling only `Field.getGenericType()` or `ParameterizedType.getActualTypeArguments()` tells you the *generic type structure*, but is **not enough** to traverse all annotation information at nested type uses.

## 5. Complete Java 17+ Example: Reading Type Arguments, Wildcards, and Bounds

Create a single file **`TypeUseDemo.java`** with the following complete content. This is a **standalone program compiled and verified with the JDK**, illustrating all the annotation levels discussed.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.AnnotatedWildcardType;
import java.util.List;
import java.util.Map;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Mark {
    String value();
}

class TypeSamples {
    List<@Mark("element") String> names;

    List<@Mark("wildcard") ? extends @Mark("upper") Number> readOnlyNumbers;

    List<@Mark("sink") ? super @Mark("lower") Integer> writeNumbers;

    Map<@Mark("key") String, List<@Mark("nested") Integer>> index;
}

public class TypeUseDemo {
    private static String mark(AnnotatedType t) {
        Mark a = t.getAnnotation(Mark.class);
        return a == null ? "none" : a.value();
    }

    private static AnnotatedParameterizedType fieldType(String name)
            throws NoSuchFieldException {
        return (AnnotatedParameterizedType)
                TypeSamples.class.getDeclaredField(name).getAnnotatedType();
    }

    public static void main(String[] args) throws Exception {
        AnnotatedType arg = fieldType("names").getAnnotatedActualTypeArguments()[0];
        System.out.println("names-arg=" + mark(arg));

        AnnotatedWildcardType upper = (AnnotatedWildcardType)
                fieldType("readOnlyNumbers").getAnnotatedActualTypeArguments()[0];
        System.out.println("upper-wildcard=" + mark(upper));
        System.out.println("upper-bound=" + mark(upper.getAnnotatedUpperBounds()[0]));

        AnnotatedWildcardType lower = (AnnotatedWildcardType)
                fieldType("writeNumbers").getAnnotatedActualTypeArguments()[0];
        System.out.println("lower-wildcard=" + mark(lower));
        System.out.println("lower-bound=" + mark(lower.getAnnotatedLowerBounds()[0]));

        AnnotatedType nestedList = fieldType("index").getAnnotatedActualTypeArguments()[1];
        AnnotatedType nestedArg = ((AnnotatedParameterizedType) nestedList)
                .getAnnotatedActualTypeArguments()[0];
        System.out.println("nested-arg=" + mark(nestedArg));
        System.out.println("field-declaration=" +
                TypeSamples.class.getDeclaredField("names")
                        .isAnnotationPresent(Mark.class));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 TypeUseDemo.java
java TypeUseDemo
```

**Exact** stdout:

```text
names-arg=element
upper-wildcard=wildcard
upper-bound=upper
lower-wildcard=sink
lower-bound=lower
nested-arg=nested
field-declaration=false
```

Explanation of each output:

1. `names-arg=element`: the `String` type argument of `List` is annotated with `@Mark("element")`, so `getAnnotatedActualTypeArguments()[0]` reads that value.
2. `upper-wildcard=wildcard`: the annotation directly before `?` belongs to the `AnnotatedWildcardType` itself.
3. `upper-bound=upper`: the annotation after `extends` belongs to the upper-bound type `Number`.
4. `lower-wildcard=sink`: `@Mark("sink")` is placed on the wildcard `?` of `? super Integer`.
5. `lower-bound=lower`: `@Mark("lower")` is placed on `Integer`, returned by `getAnnotatedLowerBounds()[0]`.
6. `nested-arg=nested`: you must traverse through `Map`, select the second argument `List<Integer>`, and then go down one more `AnnotatedParameterizedType` layer to retrieve the annotation on `Integer`.
7. `field-declaration=false`: the annotation is on the **String type argument**, not declared directly on the `names` field. Therefore, `Field.isAnnotationPresent(Mark.class)` returns `false`.

The code uses `@Retention(RUNTIME)` because the goal of this section is to observe reflection at runtime. If `SOURCE` or `CLASS` were used, these annotations would not be returned by standard reflection APIs as in the example. The fact that type arguments still exist in the source code does not mean metadata of every retention policy can be read at runtime.

### Trying to Separate the Wildcard Annotation from the Bound Annotation

Replace:

```java
List<@Mark("wildcard") ? extends @Mark("upper") Number> readOnlyNumbers;
```

with:

```java
List<? extends @Mark("upper") Number> readOnlyNumbers;
```

and keep the corresponding reflection calls. Then:

- `mark(upper)` returns `"none"` because the wildcard is not annotated.
- `mark(upper.getAnnotatedUpperBounds()[0])` still returns `"upper"`.

Similarly, if you only write `List<@Mark("wildcard") ? extends Number>`, the annotation exists on the wildcard and is not automatically copied to `Number`.

### For a Wildcard Without an Explicit Bound

```java
List<@Mark("any") ?> unknownValues;
```

`getAnnotatedUpperBounds()` of a wildcard without an explicit `extends` still has an implicit bound of `Object` (which does not carry this annotation); `getAnnotatedLowerBounds()` returns an empty array. The `@Mark("any")` annotation belongs to the wildcard, not to the implicit `Object`.

## 6. Generic Annotations on Method Parameters and Return Types

Annotations on type arguments can appear in many **type contexts**, not just fields.

```java
import java.util.List;

class SampleApi {
    public List<@Mark("response-element") String> names() {
        return List.of("An", "Binh");
    }

    public void receive(List<@Mark("request-element") String> input) {
        System.out.println(input.size());
    }
}
```

This is an **illustrative snippet**, assuming `Mark` has already been defined with `@Target(TYPE_USE)`. To read the metadata, reflection must go through:

- `Method.getAnnotatedReturnType()` for annotations on the type argument of the **return type**.
- `Method.getAnnotatedParameterTypes()`, then inspecting the parameter element that has type `AnnotatedParameterizedType`.
- Then using `getAnnotatedActualTypeArguments()` to access the annotated `String`.

`Method.getAnnotation(Mark.class)` does not automatically return `@Mark` nested inside `List<@Mark String>`. Similarly, passing an `ArrayList` object to the method at runtime does not automatically make the type-use annotation appear on the `ArrayList` class.

## 7. Type Annotations and Limitations of Java Generics

### Type Erasure Does Not Mean Annotations Used as Configuration Data Are All Lost

Java generics use **type erasure**: for the most part, the distinction between `List<String>` and `List<Integer>` does not exist as separate runtime object types. However, generic signature information on **declarations** and type-use annotations with an appropriate retention policy can still be stored in the class file for reflection APIs to read back.

Distinguish two things:

- **Actual runtime type of an object:** `new ArrayList<String>() ` and `new ArrayList<Integer>() ` do not create two separate runtime classes.
- **Metadata on a compiled declaration:** reflection on a field declared as `List<@Mark String>` can go through `AnnotatedParameterizedType` to inspect the annotation on `String`, if the retention is `RUNTIME`.

You need a **declaration containing the metadata** to read it. You cannot arbitrarily inspect any `List` instance and infer which generic annotations were written at some call site.

### Annotations Do Not Automatically Replace Nullability Checks or Generic Rules

```java
// If this is just a custom annotation with no tool understanding its content:
List<@Mark("non-null") String> names;
```

The Java compiler by default does not automatically reject adding `null` to `names` just because `"non-null"` appears in a custom annotation. For an annotation to have static checking semantics, an appropriate checker/plugin/extension that understands the annotation's policy is required.

Similarly, `List<@Mark("allowed") ? extends Number>` still follows the read/write rules of `? extends Number`. The annotation does not turn the wildcard into a fixed type argument and does not grant arbitrary `add()` permission.

### Not Every Annotation Is Valid at TYPE_USE

Intentional compilation error example:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;
import java.util.List;

@Target(ElementType.FIELD)
@interface FieldMarker {}

class Invalid {
    List<@FieldMarker String> values; // ERROR: FIELD does not allow annotating a type argument.
}
```

To use an annotation on `String` as a type argument, the annotation type must allow `ElementType.TYPE_USE`. Changing where it can be used and expanding its target is a decision about the annotation contract; you should not arbitrarily add `TYPE_USE` if consumers do not yet support reading that position.

## 8. Easily Confused Syntax Cases

| Syntax | Where does the annotation attach? | Notes |
| --- | --- | --- |
| `@Mark List<String> list;` | Type-use position of `List<String>` | Does not automatically mark the `String` argument |
| `List<@Mark String> list;` | Type argument `String` | Metadata resides inside the parameterized type |
| `List<@Mark ?> list;` | Wildcard `?` | Metadata belongs to `AnnotatedWildcardType` |
| `List<? extends @Mark Number> list;` | Upper-bound type `Number` | Read via `getAnnotatedUpperBounds()` |
| `List<? super @Mark Integer> list;` | Lower-bound type `Integer` | Read via `getAnnotatedLowerBounds()` |
| `List<@Mark ? extends @Mark Number> list;` | Both wildcard and upper bound | Two separate annotation positions |
| `Map<String, List<@Mark Integer>> data;` | `Integer` type nested inside the second argument | Reflection must traverse two generic levels |

The table above uses `@Mark` as shorthand notation; if the annotation has a required `String value();` element as in the executable example, you must provide a value such as `@Mark("x")` when writing code.

### Position Relative to < and the extends/super Keywords

To annotate a **wildcard**, the syntax must place the annotation before the `?` token. To annotate a **bound**, the annotation must be placed before the bound type itself, **after** the `extends` or `super` keyword. Moving an annotation between the two places can change its meaning for a static analyzer, even though the Java type part remains unchanged.

A wildcard `?` cannot appear in every position where a type name can appear. For example, you cannot declare a variable whose type is solely `?`; a wildcard belongs to a **type argument** of a parameterized type. Annotations do not change this rule.

## 9. How to Design and Consume Annotations on Generics Properly

When you want to use metadata for checking or code generation, decide specifically:

1. **Choose the target being checked.** Is it `List` itself, the `String` element, the wildcard, or the wildcard's bound type?
2. **Declare @Target accurately.** For annotations placed inside type arguments and wildcards, `TYPE_USE` is required.
3. **Specify retention.** Annotation processors/compiler plugins can observe them at compile time through the appropriate mechanism; runtime reflection requires `RUNTIME`.
4. **Document the semantics.** Metadata such as `"not-null"`, `"safe"`, `"validated"` are just strings on their own; documentation must state what inspects them and within what scope the behavior is guaranteed.
5. **Traverse the type structure properly.** Use `AnnotatedParameterizedType`, `AnnotatedWildcardType`, and when needed `AnnotatedArrayType` / `AnnotatedTypeVariable`, instead of assuming `Field.getAnnotations()` contains everything.
6. **Account for type erasure and declaration sites.** Do not design APIs that require inferring type-use annotations from an arbitrary runtime instance.
7. **Write real metadata tests.** A reflection example like the one in section 5 helps prove that annotations are written to the exact right positions after compilation.

In validation, serialization, or static analysis systems, this distinction is especially important. A framework may choose to interpret an annotation on `List<@Rule Item>` as a policy for **each element**, whereas `@Rule List<Item>` may be interpreted as a policy for the **container**. Java lets you express both forms; the final behavior depends on the tool being used.

## 10. Common Mistakes

**Mistake 1 — Confusing TYPE_PARAMETER with TYPE_USE.** Declaring `<T>` and using `Box<String>` are two different things. For `Box<@Mark String>`, an annotation supporting type use is needed.

**Mistake 2 — Using an annotation with only @Target(FIELD) inside <...>.** Annotations placed on type arguments or wildcards are not permitted with `FIELD` alone.

**Mistake 3 — Confusing @Mark ? with ? extends @Mark Number.** The first marks the **wildcard**, the second marks the **bound**; the two pieces of metadata do not sit on the same node in the annotated-type tree.

**Mistake 4 — Only reading Field.getAnnotation().** This API reads annotations directly on the field, so it misses annotations on nested generic type arguments. Use `Field.getAnnotatedType()` and traverse down appropriately.

**Mistake 5 — Having TYPE_USE but forgetting retention.** The default `RetentionPolicy.CLASS` does not make type-use annotations accessible via runtime reflection like a `RUNTIME` annotation.

**Mistake 6 — Assuming every List instance carries generic type annotations at runtime.** Generic type erasure and metadata on declarations are two different mechanisms; an `ArrayList` instance does not carry "the annotation on the type argument of the variable it was assigned to".

**Mistake 7 — Assuming annotations inherently provide null-checking or data-constraint functionality.** The Java compiler by default does not automatically understand custom annotations; there must be a checker/processor/framework that knows the metadata.

**Mistake 8 — Assuming annotations are added to implicit bounds.** For the wildcard `?`, the implicit upper bound is `Object`, which is not automatically annotated just because the wildcard is annotated.

**Mistake 9 — Treating an annotation on a nested generic as an annotation on the outer type.** `Map<String, List<@Mark Integer>>` marks `Integer`, not directly `Map` or `List`.

## 11. Self-Check Questions

**Question 1.** Do `List<@Mark("x") String>` and `@Mark("x") List<String>` have the same metadata position?

**Answer:** No. The first annotates `String` as a type argument; the second annotates the `List` type-use position.

**Question 2.** To place an annotation directly before `?` in `List<?>`, do you need `ElementType.FIELD` or `ElementType.TYPE_USE`?

**Answer:** `TYPE_USE`, because the wildcard is inside a type argument.

**Question 3.** How many annotated positions does `List<@Mark("a") ? extends @Mark("b") Number>` have?

**Answer:** Two: the wildcard `?` has label `a`, and the upper-bound type `Number` has label `b`.

**Question 4.** Which reflection calls retrieve `@Mark` on `String` in the field `List<@Mark String> names;`?

**Answer:** `getDeclaredField("names").getAnnotatedType()`, cast/check as `AnnotatedParameterizedType`, call `getAnnotatedActualTypeArguments()[0]`, and then `getAnnotation(Mark.class)`.

**Question 5.** If you only have `@Target(TYPE_USE)` without `@Retention(RUNTIME)`, will the reflection example in section 5 retrieve the annotation?

**Answer:** Not in the way the demo works. `TYPE_USE` permits the position; `RUNTIME` determines availability via reflection.

**Question 6.** Does `List<? super @Mark("low") Integer>` mark the wildcard or the lower bound?

**Answer:** The lower-bound type `Integer`, because the annotation appears after `super` and before the type name.

**Question 7.** Why does `List<@Mark("non-null") String>` not automatically prevent adding `null`?

**Answer:** A custom annotation is merely metadata; Java by default does not interpret that name/value as a checking rule. An appropriate checker or consumer is needed.

## Official Documentation

- [Java Language Specification 17, §4.5.1 — Type Arguments of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.1).
- [Java Language Specification 17, §9.7.4 — Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4).
- [Java SE 17 API — ElementType.TYPE_USE](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/ElementType.html).
- [Java SE 17 API — AnnotatedParameterizedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html).
- [Java SE 17 API — AnnotatedWildcardType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedWildcardType.html).

When reading or writing `List<...>`, determine whether **the annotation belongs to the container, type argument, wildcard, or bound**. These are distinct positions with different metadata access mechanisms and interpretation capabilities. Practicing with `TypeUseDemo.java` helps you see each position accurately through reflection.
