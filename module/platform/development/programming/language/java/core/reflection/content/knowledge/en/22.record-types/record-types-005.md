# Record component annotations differ from annotations on fields, accessors, and parameters

## 1. One declaration line, multiple metadata locations

Consider a record with a `name` component:

~~~java
record Person(String name) {
}
~~~

From a single component in the record header, we have these related declaration elements:

~~~text
record component name
    -> private final backing field name
    -> accessor method name()
    -> canonical constructor parameter name
~~~

These elements are related to each other, yet **they are not the same annotated element**. Reflection provides a distinct object for each location:

- `RecordComponent`: the record component.
- `Field`: the backing field.
- `Method`: the accessor.
- `Parameter`: the constructor parameter.

Therefore, you cannot see `@SomeAnnotation` next to a component in source code and conclude that all four `getAnnotation(...)` queries must return the same result.

To understand the results, you must know **where the annotation is permitted to apply**, **whether the member or parameter is implicit or explicitly written**, and **whether the annotation is retained for Reflection at runtime**.

## 2. Target and Retention answer two different questions

### 2.1. Target determines applicable locations

`@Target` on an annotation declaration determines the valid contexts.

| `ElementType` | Corresponding location in this article |
| --- | --- |
| `RECORD_COMPONENT` | Record component declaration |
| `FIELD` | Backing field declaration |
| `METHOD` | Accessor method declaration |
| `PARAMETER` | Constructor parameter declaration |
| `TYPE_USE` | A type use location, such as the component's `String` type |

These constants are described in [ElementType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/ElementType.html).

An annotation can allow multiple targets. For example, an annotation with both `RECORD_COMPONENT` and `FIELD` can appear on both component metadata and the corresponding field when applied via the record header.

An annotation with only the `FIELD` target can still be written at the component position in the record header and propagated to the corresponding field. That does **not** make it appear as a declared annotation of `RecordComponent`. The program in a later section verifies this case.

### 2.2. Retention determines runtime visibility

| Policy | Effect on Reflection at runtime |
| --- | --- |
| `SOURCE` | Annotation is discarded at compile time; not observable by ordinary Reflection |
| `CLASS` | Present in the class file but not retained to be returned by ordinary Reflection annotation queries |
| `RUNTIME` | Can be read via Reflection at the appropriate location |

If `@Retention` is omitted, the default is `CLASS`.

Thus, `getAnnotation(...)` returning `null` may be because the wrong location is queried, the annotation is absent at that location, or the retention policy does not allow runtime observation. Do not fix only `@Target` while overlooking `@Retention`.

## 3. Choosing the right Reflection object

For a record with a `name` component and a canonical constructor taking `String name`, the corresponding query points are:

| Where to query the annotation? | Object to read |
| --- | --- |
| Record component | `recordType.getRecordComponents()[index]` |
| Backing field | `recordType.getDeclaredField(component.getName())` |
| Accessor | `component.getAccessor()` |
| Canonical constructor parameter | `canonical.getParameters()[index]` |
| Component type | `component.getAnnotatedType()` |
| Accessor return type | `accessor.getAnnotatedReturnType()` |

Each declaration object can be queried with `getAnnotation(...)`, `isAnnotationPresent(...)`, or the corresponding annotation-reading APIs.

Do not confuse a **parameter** annotation with a **constructor** annotation. `parameter.getAnnotation(A.class)` queries a different location than `constructor.getAnnotation(A.class)`. Target `PARAMETER` does not mean target `CONSTRUCTOR`.

Nor is it necessary to open access permissions just to read annotations on a private field. Reading metadata with `Field.getAnnotation(...)` differs from reading or writing field values with `Field.get(...)` or `Field.set(...)`.

## 4. Complete program: comparing four locations

The following program declares annotations dedicated to each individual location, one annotation shared across four locations, and one annotation for types only.

It also compares:

- A record with implicit accessor and canonical constructor.
- A record with an explicitly written accessor and canonical constructor with an explicit parameter list.
- A record with a compact constructor.
- A record placing different annotation values at each location.

Save into `RecordAnnotationLocationsDemo.java`:

~~~java
import java.lang.annotation.Annotation;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedElement;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.lang.reflect.RecordComponent;
import java.util.Arrays;

public class RecordAnnotationLocationsDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.RECORD_COMPONENT)
    public @interface OnComponent {
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.FIELD)
    public @interface OnField {
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    public @interface OnMethod {
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    public @interface OnParameter {
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.RECORD_COMPONENT, ElementType.FIELD,
             ElementType.METHOD, ElementType.PARAMETER})
    public @interface Everywhere {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    public @interface TypeMark {
    }

    @Retention(RetentionPolicy.CLASS)
    @Target(ElementType.RECORD_COMPONENT)
    public @interface ClassOnly {
    }

    public record Automatic(
            @OnComponent @OnField @OnMethod @OnParameter
            @Everywhere("header") @TypeMark @ClassOnly String text) {
    }

    public record Manual(@Everywhere("header") @TypeMark String text) {
        public Manual(String text) {
            this.text = text;
        }

        public String text() {
            return text;
        }
    }

    public record Compact(@Everywhere("header") @TypeMark String text) {
        public Compact {
            text = text.strip();
        }
    }

    public record ExplicitValues(@Everywhere("header") String text) {
        public ExplicitValues(@Everywhere("parameter") String text) {
            this.text = text;
        }

        @Everywhere("accessor")
        public String text() {
            return text;
        }
    }

    static String names(AnnotatedElement element) {
        return Arrays.stream(element.getDeclaredAnnotations())
                .map(Annotation::annotationType)
                .map(Class::getSimpleName)
                .sorted()
                .toList()
                .toString();
    }

    static void inspect(Class<?> type) throws NoSuchMethodException,
            NoSuchFieldException {
        RecordComponent component = type.getRecordComponents()[0];
        Field field = type.getDeclaredField(component.getName());
        Method accessor = component.getAccessor();
        Constructor<?> constructor =
                type.getDeclaredConstructor(component.getType());
        Parameter parameter = constructor.getParameters()[0];

        System.out.println("== " + type.getSimpleName() + " ==");
        System.out.println("component: " + names(component));
        System.out.println("field: " + names(field));
        System.out.println("accessor: " + names(accessor));
        System.out.println("parameter: " + names(parameter));
        System.out.println("component type: "
                + names(component.getAnnotatedType()));
        System.out.println("field type: "
                + names(field.getAnnotatedType()));
        System.out.println("accessor return type: "
                + names(accessor.getAnnotatedReturnType()));
        System.out.println("parameter type: "
                + names(parameter.getAnnotatedType()));
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        inspect(Automatic.class);
        inspect(Manual.class);
        inspect(Compact.class);

        RecordComponent component =
                Automatic.class.getRecordComponents()[0];
        System.out.println("ClassOnly visible at runtime: "
                + component.isAnnotationPresent(ClassOnly.class));

        Class<?> type = ExplicitValues.class;
        RecordComponent explicit = type.getRecordComponents()[0];
        System.out.println("explicit component value: "
                + explicit.getAnnotation(Everywhere.class).value());
        System.out.println("explicit field value: "
                + type.getDeclaredField("text")
                        .getAnnotation(Everywhere.class).value());
        System.out.println("explicit accessor value: "
                + explicit.getAccessor()
                        .getAnnotation(Everywhere.class).value());
        System.out.println("explicit parameter value: "
                + type.getDeclaredConstructor(String.class)
                        .getParameters()[0]
                        .getAnnotation(Everywhere.class).value());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 -encoding UTF-8 RecordAnnotationLocationsDemo.java
java RecordAnnotationLocationsDemo
~~~

Exact output:

~~~text
== Automatic ==
component: [Everywhere, OnComponent]
field: [Everywhere, OnField]
accessor: [Everywhere, OnMethod]
parameter: [Everywhere, OnParameter]
component type: [TypeMark]
field type: [TypeMark]
accessor return type: [TypeMark]
parameter type: [TypeMark]
== Manual ==
component: [Everywhere]
field: [Everywhere]
accessor: []
parameter: []
component type: [TypeMark]
field type: [TypeMark]
accessor return type: []
parameter type: []
== Compact ==
component: [Everywhere]
field: [Everywhere]
accessor: [Everywhere]
parameter: [Everywhere]
component type: [TypeMark]
field type: [TypeMark]
accessor return type: [TypeMark]
parameter type: [TypeMark]
ClassOnly visible at runtime: false
explicit component value: header
explicit field value: header
explicit accessor value: accessor
explicit parameter value: parameter
~~~

The `names(...)` method intentionally sorts annotation names so stdout is stable. Do not rely on the order of annotations in Reflection arrays.

The records in the example all have a single `String` component. Therefore, the inspection code uses index `0` and a single-parameter constructor signature. For a general-purpose tool, you must map positions properly according to the record header; section 8 shows how.

## 5. Reading the key results

### 5.1. Automatic: target determines where annotations appear

For record `Automatic`, the declaration results are:

| Location | Observable annotations |
| --- | --- |
| Component | `Everywhere`, `OnComponent` |
| Field | `Everywhere`, `OnField` |
| Accessor | `Everywhere`, `OnMethod` |
| Parameter | `Everywhere`, `OnParameter` |

`OnField`, `OnMethod`, and `OnParameter` do not appear when querying declared annotations on the component, even though all of them were written in the record header.

`Everywhere` has all four targets so it appears at all four locations when the corresponding accessor and constructor are implicitly generated. This is propagation of annotations to applicable contexts, not four Reflection objects sharing a single annotation list.

Rules for components and related members are located in [JLS §8.10.1–8.10.3](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10.1).

### 5.2. Manual: explicit declarations change what is observed

Record `Manual` has annotations in the header:

~~~java
@Everywhere("header") @TypeMark String text
~~~

Yet the accessor is explicitly written without adding annotations:

~~~java
public String text() {
    return text;
}
~~~

And the canonical constructor also has an explicitly written parameter list:

~~~java
public Manual(String text) {
    this.text = text;
}
~~~

The snippets above are excerpts from the complete program, not standalone programs.

Results:

- The component and field still have `Everywhere`.
- The accessor does not automatically inherit `Everywhere` from the component.
- The explicitly written parameter does not automatically inherit `Everywhere` from the component.
- Annotations on the component type and field type still have `TypeMark`.
- The explicitly written return type and parameter type do not automatically have `TypeMark`.

Therefore, refactoring from an implicit accessor to a handwritten accessor can change the metadata a tool reads on `Method`, even when the method still returns the exact same value as before.

Do not conclude that component metadata was lost: `RecordComponent` still has its own annotations. Different locations are simply giving different results.

### 5.3. Compact: parameters are still implicitly declared

Record `Compact` writes:

~~~java
public Compact {
    text = text.strip();
}
~~~

This is a compact canonical constructor. The author provides the body, without rewriting the parameter list. Its parameters are still inferred from the record header and are implicitly declared.

Therefore, in the program:

- The `Everywhere` annotation applicable to parameters still appears on `Parameter`.
- The `TypeMark` annotation is still present on the parameter type.
- The accessor is not explicitly written so it still receives applicable annotations.

Do not mechanically apply a rule like "if a constructor is written, annotations are not propagated." Distinguish a **normal canonical constructor with an explicit parameter list** from a **compact constructor with implicit parameters**. Rules for both constructor forms are described in [JLS §8.10.4](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10.4).

### 5.4. ExplicitValues: same annotation type, potentially different values

The last four lines of the program output are:

~~~text
explicit component value: header
explicit field value: header
explicit accessor value: accessor
explicit parameter value: parameter
~~~

The program is valid. The annotation on the component has the value `header`, while the explicitly written accessor and canonical constructor parameter have different values.

Therefore, a tool cannot assume:

~~~text
Found the same annotation type
    -> every location expresses the same configuration
~~~

If a tool wants to combine configuration from multiple places, it must clearly define precedence and conflict handling. Do not concatenate all found annotations and treat them as equivalent duplicates.

### 5.5. ClassOnly: right target, yet Reflection still cannot see it

`ClassOnly` has target `RECORD_COMPONENT` but retention is `CLASS`. The check line gives:

~~~text
ClassOnly visible at runtime: false
~~~

This is not evidence that the compiler ignored the annotation. It shows that the annotation is not exposed via the runtime Reflection API under that retention policy.

If you need to inspect annotations with `CLASS` retention, that is a problem of reading class files with an appropriate tool, different from simply calling `RecordComponent.getAnnotation(...)`.

## 6. Declaration annotations differ from annotations on types

`RecordComponent.getAnnotation(...)` answers about annotations **of the component declaration**. To query annotations **on the type-use location**, use `getAnnotatedType()`.

In record `Automatic`, `TypeMark` only has the `TYPE_USE` target. Therefore:

- It does not appear in the component's declared annotation list.
- It appears on `component.getAnnotatedType()`.
- For the corresponding implicit members, it also appears on the field type, accessor return type, and parameter type.

You can picture two separate channels:

~~~text
RecordComponent
    -> getAnnotation(...)          : declaration annotation
    -> getAnnotatedType()
         -> getAnnotation(...)     : annotation on the type
~~~

An annotation with both `RECORD_COMPONENT` and `TYPE_USE` targets can apply in both roles. In that case both queries can see the same annotation type, yet they are still reading two different metadata locations.

Reading `getGenericType()` does not substitute for reading `getAnnotatedType()` either. `Type` describes the type structure; `AnnotatedType` allows inspecting that structure along with annotations on type-use locations.

### Nested annotations in generic arguments

For the component `List<@TypeMark String> values`, `TypeMark` is attached to **the type use of `String`**, not the component declaration or the outermost `List` type. Therefore, queries on the component and on the root `component.getAnnotatedType()` may not see the annotation.

The illustrative snippet below assumes you already have `RecordComponent component` for the `values` component, and annotation `TypeMark` with `@Target(TYPE_USE)` and `@Retention(RUNTIME)`:

~~~java
java.lang.reflect.AnnotatedType root = component.getAnnotatedType();
if (root instanceof java.lang.reflect.AnnotatedParameterizedType listType) {
    boolean marked = listType.getAnnotatedActualTypeArguments()[0]
            .isAnnotationPresent(TypeMark.class);
    System.out.println(marked); // true for List<@TypeMark String>
}
~~~

Use `instanceof` because not every component has a generic type. For arrays, wildcards, or type variables, choose the corresponding `AnnotatedType` interface and navigate to the right node; do not flatten annotations from different type positions into a single set.

## 7. A rule matrix for self-prediction

Suppose an annotation has `RUNTIME` retention and is written on a component in the record header:

| Annotation target | Component | Backing field | Implicit accessor | Implicit canonical constructor parameter |
| --- | --- | --- | --- | --- |
| `RECORD_COMPONENT` only | Yes | No | No | No |
| `FIELD` only | No | Yes | No | No |
| `METHOD` only | No | No | Yes | No |
| `PARAMETER` only | No | No | No | Yes |
| All four targets above | Yes | Yes | Yes | Yes |
| `TYPE_USE` only | Not on declaration annotations | Read on field type | Read on return type | Read on parameter type |

For the `TYPE_USE` row, you also read `component.getAnnotatedType()` to observe the annotation on the component type. The location can be nested deep inside the type structure, as in the `List<@ItemMark String>` example.

The matrix applies to implicit parts. An explicitly written accessor and a parameter of a canonical constructor with an explicitly written parameter list must be examined on their own declarations.

Record annotation propagation is a language rule, not the annotation inheritance mechanism via `@Inherited`. Do not use `@Inherited` as a way to request automatic propagation between component, field, accessor, and parameter.

## 8. Mapping the canonical constructor accurately in a general-purpose tool

The first program has one component, making it easy to identify the corresponding parameter. For records with multiple components, start from the order of `getRecordComponents()` and construct the canonical constructor signature from the component types.

The following snippet is illustrative code placed inside a method; `recordType` is the token of a known record class. Corresponding Reflection imports and `java.util.Arrays` are required; the containing method must handle `NoSuchMethodException`.

~~~java
RecordComponent[] components = recordType.getRecordComponents();
if (components == null) {
    throw new IllegalArgumentException("Expected a record class");
}

Class<?>[] parameterTypes = Arrays.stream(components)
        .map(RecordComponent::getType)
        .toArray(Class<?>[]::new);

Constructor<?> canonical =
        recordType.getDeclaredConstructor(parameterTypes);
Parameter[] parameters = canonical.getParameters();

for (int i = 0; i < components.length; i++) {
    RecordComponent component = components[i];
    Parameter parameter = parameters[i];

    System.out.println(component.getName() + " -> "
            + parameter.getDeclaredAnnotations().length);
}
~~~

Points to preserve:

- Select the canonical constructor by the exact type list and component order.
- Do not pick the first constructor in `getDeclaredConstructors()`; a record can have additional constructors.
- Use `getType()` to obtain `Class<?>` for signature lookup; do not cast every `getGenericType()` to `Class`.
- Map parameters in component order; do not guess from field order.
- When you only need parameter annotations, there is no need to create a record object or invoke the constructor.

With an explicitly written canonical constructor, there is still a positional relationship between component and parameter, yet the parameter's annotations can differ from the component's annotations. Being able to map the two positions does not mean their annotation data is identical.

## 9. How to design annotation-reading rules

A tool should start from a specific domain question:

- If the annotation describes a component in the record data schema, determine whether the configuration source is `RecordComponent`.
- If the tool operates through accessors, decide how to handle annotations on `Method` and the return type.
- If the tool prepares arguments to call a constructor, `Parameter` annotations are a separate source of information.
- If the annotation describes the data type or elements inside a generic structure, inspect `AnnotatedType`.

Do not assume an annotation at another location "must be the same annotation missed by Reflection." Read each necessary place and define a clear policy.

When encountering different configurations across multiple locations, the tool can prioritize one location, report a conflict, or support a defined combination rule. That choice belongs to the tool's contract, not automatic Reflection behavior.

If the annotation is repeatable, use `getAnnotationsByType(...)` or `getDeclaredAnnotationsByType(...)` as needed to read occurrences through the container. This is still an operation on **one chosen location**, not automatically merging the four record locations.

## 10. Self-check

1. An annotation with only the `FIELD` target is written before a record component. Can it be read with `RecordComponent.getAnnotation(...)`?
2. An annotation has target `RECORD_COMPONENT` and default retention. Why might runtime Reflection not see it?
3. When explicitly writing an accessor without copying annotations from the record header, are annotations on the accessor automatically propagated like an implicit accessor?
4. Does a compact constructor have implicit parameters or an explicitly declared parameter list?
5. Does an annotation on a canonical constructor parameter mean the annotation is on the constructor itself?
6. For `List<@ItemMark String>`, why might querying annotations on the component and on the outermost `List` type both fail to see it?
7. If a component has `@Everywhere("header")` while a handwritten accessor has `@Everywhere("accessor")`, does the program necessarily fail to compile?
8. Why should a tool not pick the first constructor to read record parameter annotations?

Answers:

1. No for an annotation with only that target. Read it on the corresponding `Field`.
2. Default retention is `CLASS`, not `RUNTIME`.
3. No. You must inspect the annotations of the explicitly written accessor itself.
4. Implicit parameters, inferred from the record header; applicable annotations are applied according to the rules for inferred parameters.
5. No. Those are two different declaration locations.
6. The annotation is on the `String` type argument; you need to drill down via `AnnotatedParameterizedType`.
7. No. The sample program shows that values at those locations can validly differ.
8. A record can have additional constructors and the constructor array has no desired selection order; you must look up the exact canonical signature based on the components.
