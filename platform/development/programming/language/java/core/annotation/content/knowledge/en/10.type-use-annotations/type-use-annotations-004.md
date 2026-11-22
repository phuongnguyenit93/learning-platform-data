# Annotations on Type Parameter Declarations and Type Bounds in Java Core

In Java generics, a type parameter such as `T` in `class Box<T>` is **a type parameter declaration**. If you write `T extends Number & Comparable<T>`, the types `Number` and `Comparable<T>` are the **upper bounds** of that parameter. Java allows placing annotations in **two positions with different meanings**: on the declaration of `T` itself and on the types used as bounds of `T`.

Distinguishing these two positions is the focus of this lesson:

~~~java
class Box<@ParamInfo T extends @BoundInfo Number & @BoundInfo Comparable<T>> {}
~~~

`@ParamInfo` appears before the **type parameter name `T`**, whereas `@BoundInfo` appears before the **bound type `Number` or `Comparable<T>`**. The example above only illustrates the positions, assuming the corresponding annotation types have already been defined. The two kinds of annotations have different targets, meanings, and required Reflection APIs.

## 1. Learning Objectives

After this lesson, you should be able to explain and practice:

- Distinguishing a *type parameter* `T` from a *type argument* `String` in `Box<String>` and from an *upper bound* in `T extends Number`.
- Writing annotations on type parameter declarations of classes, interfaces, and generic methods.
- Attaching annotations to one or more type bounds, including components after `&`.
- Understanding the difference between `ElementType.TYPE_PARAMETER` and `ElementType.TYPE_USE`.
- Using Reflection to obtain `TypeVariable<?>`, read annotations at the **declaration** with `getAnnotation(...)`, and read annotations on a **bound** with `getAnnotatedBounds()`.
- Reading annotations in a type argument nested inside a parameterized bound using `AnnotatedParameterizedType` when needed.
- Grasping the limitations of metadata: annotations do not by themselves change type assignability, inheritance relationships, erasure, or null checks.
- Avoiding syntax errors and common misconceptions with `@Target`, `@Retention`, and generic Reflection APIs.

## 2. Generic Syntax Review: Type Parameters, Type Arguments, and Bounds

Example:

~~~java
class Store<T> {
    private T item;

    public Store(T item) {
        this.item = item;
    }

    public T get() {
        return item;
    }
}
~~~

Here, `T` in `Store<T>` is a **declared type parameter**. When you write `Store<String>`, `String` is a **type argument** supplied at a type use site. They are related, but they are not the same syntactic position.

Upper bounds are placed after `extends`:

~~~java
class NumericStore<T extends Number> {}
~~~

`T extends Number` means the type argument used for `T` must satisfy the bound `Number`. With multiple bounds:

~~~java
class ComparableNumber<T extends Number & Comparable<T>> {}
~~~

`T` must satisfy both: be a subtype of `Number` and implement `Comparable<T>`. For example, `Integer` meets this condition because `Integer` is a `Number` and implements `Comparable<Integer>`.

Standard Java rules still apply when adding annotations:

- If there is a specific **class bound**, the class bound comes first, before any interface bounds.
- There can be multiple interface bounds, separated by `&`; two class bounds cannot be listed.
- If no bound is written, the type variable has a default upper bound of `Object`.
- Annotations do not make an incompatible type valid; the compiler still checks generic bounds as usual.

An illustrative example for `ComparableNumber`: `ComparableNumber<Integer>` is valid with respect to the bounds; `ComparableNumber<String>` is invalid because `String` does not extend `Number`.

## 3. `TYPE_PARAMETER`: Annotations on Type Parameter Declarations

To mark the type parameter name itself, declare an annotation with target `TYPE_PARAMETER`:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_PARAMETER)
@interface ParamInfo {
    String value();
}
~~~

Usage on class, interface, and method declarations:

~~~java
class Holder<@ParamInfo("class-T") T> {}

interface Provider<@ParamInfo("interface-E") E> {}

class Utility {
    public <@ParamInfo("method-R") R> R identity(R value) {
        return value;
    }
}
~~~

The snippets above illustrate only the syntax; you can save them together with the declared annotation types if you need to compile them.

`@ParamInfo("class-T")` describes **the declaration of parameter `T`**; it does not describe individual concrete values held by `Holder<T>`, and it does not automatically apply to all subsequent uses of `T`.

This declaration annotation is read through the `TypeVariable` object returned by Reflection:

~~~java
java.lang.reflect.TypeVariable<?> typeParameter =
        Holder.class.getTypeParameters()[0];

ParamInfo info = typeParameter.getAnnotation(ParamInfo.class);
System.out.println(typeParameter.getName()); // T
System.out.println(info.value());            // class-T
~~~

`Class.getTypeParameters()` returns the type parameters **declared by the class itself**, in declaration order. Similarly, `Method.getTypeParameters()` or `Constructor.getTypeParameters()` are for the type parameters declared on the corresponding generic method or constructor. `TypeVariable` implements `AnnotatedElement`, so you can use `getAnnotation(...)`, `getAnnotations()`, and the usual metadata lookup APIs.

The condition for the Reflection example to read `@ParamInfo` is `RUNTIME` retention. If changed to `CLASS`, the metadata may still remain in `.class` but cannot be queried using standard runtime Reflection; `SOURCE` will not store that annotation usage in the class file.

## 4. `TYPE_USE`: Annotations on Types Used as Bounds

Bounds such as `Number` and `Comparable<T>` are **type uses**. Annotations used here typically declare `@Target(ElementType.TYPE_USE)`:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface BoundInfo {
    String value();
}
~~~

How to attach them:

~~~java
class Box<T extends @BoundInfo("number") Number
        & @BoundInfo("comparable") Comparable<T>> {}
~~~

Here there are two independent pieces of metadata: one annotation on the use of the type `Number` as the first bound, and one annotation on the use of the type `Comparable<T>` as the second bound.

The `&` symbol is the intersection syntax for bounds. Each annotation is placed immediately before its corresponding type, including types after `&`. Do not place a bound's annotation before the name `T` and assume it will describe `Number`.

### Comparing Positions and Targets

| Source position | Example | Appropriate target | Reflection API to use |
| --- | --- | --- | --- |
| Type parameter declaration | `class C<@ParamInfo T>` | `TYPE_PARAMETER` | `C.class.getTypeParameters()[0].getAnnotation(...)` |
| First bound | `T extends @BoundInfo Number` | `TYPE_USE` | `TypeVariable.getAnnotatedBounds()[0]` then `getAnnotation(...)` |
| Subsequent bound | `T extends Number & @BoundInfo Comparable<T>` | `TYPE_USE` | `getAnnotatedBounds()[1]` |
| Type argument inside a bound | `Comparable<@BoundInfo T>` | `TYPE_USE` | `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[0]` |

**Note on `TYPE_USE`:** By Java's definition, the `TYPE_USE` target also allows an annotation to appear on a **type parameter declaration** as a language convenience. Therefore, do not say that an annotation before `T` *must* have the `TYPE_PARAMETER` target. What is true is: `TYPE_PARAMETER` is dedicated to the type parameter declaration position; `TYPE_USE` is used for type use positions, including bounds, and can also be used at type parameter declarations according to Java's rules. Conversely, an annotation that **only** has the `TYPE_PARAMETER` target is invalid when placed directly before the bound type `Number`.

A clear combined pattern:

~~~java
class Box<
    @ParamInfo("T") T extends
        @BoundInfo("number") Number
        & @BoundInfo("comparable") Comparable<T>
> {}
~~~

If you use two separate annotation types, the code and Reflection express the meaning explicitly: `ParamInfo` describes the declaration of `T`; `BoundInfo` describes the type uses in the bounds list.

## 5. Complete Java 17+ Example: Reading Declarations and Bounds with Reflection

Create the file **`TypeParameterAnnotationsDemo.java`** with all of the following code. The annotation types and auxiliary classes are non-`public`; `TypeParameterAnnotationsDemo` is the only `public` class, so the file name must match.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Method;
import java.lang.reflect.TypeVariable;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_PARAMETER)
@interface ParamInfo {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface BoundInfo {
    String value();
}

class Box<
    @ParamInfo("T") T extends
        @BoundInfo("number") Number
        & @BoundInfo("comparable") Comparable<@BoundInfo("argument") T>
> {
    public <@ParamInfo("U") U extends @BoundInfo("sequence") CharSequence>
    U echo(U input) {
        return input;
    }
}

class Free<@ParamInfo("V") V> {}

public class TypeParameterAnnotationsDemo {
    public static void main(String[] args) throws NoSuchMethodException {
        TypeVariable<?> t = Box.class.getTypeParameters()[0];

        System.out.println("name=" + t.getName());
        System.out.println("declaration="
                + t.getAnnotation(ParamInfo.class).value());
        System.out.println("bounds=" + Arrays.toString(t.getBounds()));

        for (AnnotatedType bound : t.getAnnotatedBounds()) {
            BoundInfo tag = bound.getAnnotation(BoundInfo.class);
            System.out.println("bound=" + bound.getType().getTypeName()
                    + ", tag=" + tag.value());
        }

        AnnotatedParameterizedType comparableBound =
                (AnnotatedParameterizedType) t.getAnnotatedBounds()[1];
        AnnotatedType argument =
                comparableBound.getAnnotatedActualTypeArguments()[0];
        System.out.println("argument="
                + argument.getAnnotation(BoundInfo.class).value());

        Method method = Box.class.getDeclaredMethod(
                "echo", CharSequence.class);
        TypeVariable<?> u = method.getTypeParameters()[0];
        System.out.println("method=" + u.getName() + ":"
                + u.getAnnotation(ParamInfo.class).value());
        System.out.println("methodBound=" + u.getAnnotatedBounds()[0]
                .getAnnotation(BoundInfo.class).value());

        TypeVariable<?> v = Free.class.getTypeParameters()[0];
        System.out.println("freeBound="
                + v.getAnnotatedBounds()[0].getType().getTypeName());
        System.out.println("freeAnnotations="
                + v.getAnnotatedBounds()[0].getAnnotations().length);
    }
}
~~~

Compile and run in the directory containing the file using JDK 17 or later:

~~~bash
javac -encoding UTF-8 TypeParameterAnnotationsDemo.java
java TypeParameterAnnotationsDemo
~~~

**Expected stdout:**

~~~text
name=T
declaration=T
bounds=[class java.lang.Number, java.lang.Comparable<T>]
bound=java.lang.Number, tag=number
bound=java.lang.Comparable<T>, tag=comparable
argument=argument
method=U:U
methodBound=sequence
freeBound=java.lang.Object
freeAnnotations=0
~~~

### Part-by-Part Explanation

1. `Box.class.getTypeParameters()[0]` retrieves the `TypeVariable` representing `T`; `t.getName()` returns `"T"`.
2. `t.getAnnotation(ParamInfo.class)` reads the annotation on the **declaration of `T`**, returning `"T"` from the `value()` element.
3. `t.getBounds()` returns `Type[]` for the bounds; its contents indicate `Number` and `Comparable<T>`, but it is not the API for reading annotations placed on type-use bounds.
4. `t.getAnnotatedBounds()` returns `AnnotatedType[]` in the exact order the bounds were declared. Reading `@BoundInfo` on each `AnnotatedType` retrieves `"number"` and `"comparable"`.
5. The bound `Comparable<@BoundInfo("argument") T>` is a parameterized type. `AnnotatedParameterizedType` holds the annotated type argument structure. `getAnnotatedActualTypeArguments()[0]` leads to the use of `T` inside `Comparable<T>`, where the `"argument"` annotation is located.
6. The generic method `echo` declares **its own type parameter `U`**, rather than reusing the class's `T`. `Method.getTypeParameters()[0]` retrieves `U`, while `u.getAnnotatedBounds()[0]` reads the `"sequence"` annotation on the `CharSequence` bound.
7. `Free<V>` declares no upper bound. Reflection still returns **one implicit `Object` bound with no annotations** via `getAnnotatedBounds()`, so the last two lines are `java.lang.Object` and `0`.
8. The call `getDeclaredMethod("echo", CharSequence.class)` uses the `CharSequence.class` parameter because the `echo(U)` method has `CharSequence` as its first bound and the **erasure** of `U` is `CharSequence`. Do not use `Object.class` for this method signature.

The example code only **reads** metadata. It does not need to create a `Box` instance or call `echo`. Attaching `@ParamInfo` and `@BoundInfo` does not automatically insert runtime validation or null checks.

## 6. What Is Stored in the Class File?

In this program, both `ParamInfo` and `BoundInfo` have `RUNTIME` retention, so `javac` writes the required metadata into the `.class` file:

- An annotation on a **type parameter declaration** has target information relating to the type parameter of the class or method.
- An annotation on an **upper bound** has target information relating to which bound of which type parameter it applies to.
- An annotation on the **type argument** `T` inside `Comparable<T>` also carries a path to the type argument position within the type structure.

Annotations of this kind belong to the **type annotations** mechanism added by Java in Java 8; they are typically represented in the `RuntimeVisibleTypeAnnotations` class file attribute when retention is `RUNTIME`. The metadata storage structure makes it possible to distinguish whether an annotation is attached to `T`, the `Number` bound, the `Comparable<T>` bound, or a type argument inside a bound. They are not merely `@...` text strings concatenated onto type names.

To inspect this, after compiling you can run:

~~~bash
javap -v Box
~~~

In the detailed output, look for `RuntimeVisibleTypeAnnotations` and entries related to **CLASS_TYPE_PARAMETER**, **CLASS_TYPE_PARAMETER_BOUND**, **METHOD_TYPE_PARAMETER**, or **METHOD_TYPE_PARAMETER_BOUND** (the displayed names may depend on the `javap` version). If you inspect `ParamInfo.class` and `BoundInfo.class` separately, you will also see the meta-annotations describing their target/retention. Do not try to predict constant pool indices or bytecode offsets; they are compiler details.

Querying with Reflection via `getAnnotation(...)` requires the annotation to have `RUNTIME` retention. If declared with `SOURCE` or `CLASS`, whether it is stored in the binary and whether it can be read at runtime change according to the retention policy. That is a rule of annotations, independent of how type `T` is bounded.

## 7. Distinguishing `TypeVariable` and `AnnotatedType`

When debugging annotations on generics, ask yourself: "Do I want to read an annotation **on a declaration** or **on a type use**?"

### 7.1. `TypeVariable<?>` Represents the Declared Type Parameter

For example, `Box.class.getTypeParameters()[0]` is a `TypeVariable` for `T`. It has:

- `getName()` to get the name `T`.
- `getGenericDeclaration()` to find out which generic declaration created `T` (a class, method, or constructor).
- `getBounds()` returning `Type` objects representing the bounds, without holding the annotation API layer.
- `getAnnotatedBounds()` returning `AnnotatedType` objects representing **how the bound types are written and annotated**.
- `AnnotatedElement` APIs such as `getAnnotation(ParamInfo.class)` to retrieve metadata attached to the **type parameter declaration**.

Example:

~~~java
TypeVariable<?> t = Box.class.getTypeParameters()[0];
ParamInfo declaration = t.getAnnotation(ParamInfo.class);
AnnotatedType firstBound = t.getAnnotatedBounds()[0];
BoundInfo bound = firstBound.getAnnotation(BoundInfo.class);
~~~

This snippet illustrates using the types from the full program. `declaration` and `bound` are reading from **two different places**, even though both relate to the same `T`.

### 7.2. `AnnotatedType` Represents a Type Use and Annotations on It

`AnnotatedType` has `getType()` to obtain the underlying type and annotation APIs such as `getAnnotation(...)`. When a type has a complex structure, subtypes of `AnnotatedType` represent its structural parts:

- `AnnotatedParameterizedType` for a parameterized type, with `getAnnotatedActualTypeArguments()`.
- `AnnotatedArrayType` for an array type, with `getAnnotatedGenericComponentType()`.
- `AnnotatedWildcardType` for a wildcard with upper/lower bounds, with APIs to retrieve annotated bounds.
- `AnnotatedTypeVariable` for **a use of a type variable** in a type position, which can provide information about the variable's annotated bounds.

Do not confuse `AnnotatedTypeVariable` (an annotated *use* of a type variable) with `TypeVariable` (which represents a type variable in a generics declaration). To read the annotation on `<@ParamInfo T>`, start from `getTypeParameters()` on the declaration. To read the annotation on `extends @BoundInfo Number`, start from `t.getAnnotatedBounds()`.

### 7.3. Type Parameter Declarations Differ from Type Arguments

~~~java
class Bucket<@ParamInfo("decl") T> {}

class Example {
    Bucket<@BoundInfo("use") String> names;
}
~~~

`@ParamInfo("decl")` marks **`T` at the declaration of `Bucket`**. `@BoundInfo("use")` marks **the use of `String` as a type argument** for the `names` field. An annotation on a field type argument typically needs to be queried starting from `Field.getAnnotatedType()`, and then inspecting `AnnotatedParameterizedType`.

An object of type `Bucket<String>` does not imply that "the annotation on `T` is automatically converted into an annotation on `String`." Java does not automatically propagate an annotation from a declaration to every argument or reference.

## 8. Annotations Do Not Replace Generic Bound Rules

The generic bound `T extends Number & Comparable<T>` is checked by the **Java type system**. Adding `@BoundInfo("number")` only adds metadata; it does not make a class missing `Comparable<T>` valid, and it does not cause bound checking to happen at runtime.

Invalid type argument example:

~~~java
// Invalid generic bound: String does not extend Number.
// Box<String> invalid;
~~~

Conversely, `Box<Integer>` satisfies the generic bounds regardless of whether the annotations on the bounds are named `"number"` or `"comparable"`. Those strings are not logical conditions understood by default by the Java compiler.

For annotations that act purely as markers, the Java compiler itself does not know by default that they represent "nonnull", "thread safe", or "validated". An annotation processor, static analyzer, compiler plugin, or runtime framework can **define and enforce its own rules**, but that is the logic of that tool.

**Erasure:** The generic type variable `T` and its upper bounds affect how the compiler checks types and the erased type form when generating bytecode. Type-use annotations **do not by themselves change erasure**; in the example, the `echo(U)` method is erased to a `CharSequence` parameter by the `CharSequence` upper bound, not by the `"sequence"` string in the annotation.

## 9. Multiple Bounds and Annotation Positions

Multiple bounds can be combined:

~~~java
interface Readable {
    void read();
}

interface Writable {
    void write();
}

class Resource<
    @ParamInfo("resource") T extends
        @BoundInfo("read") Readable
        & @BoundInfo("write") Writable
> {}
~~~

In this example, both `Readable` and `Writable` are interfaces, so the bounds list contains only interface types and is valid. The `&` symbol joins upper bounds; it is not a runtime conditional AND operation.

If a class bound is added, the class must come first:

~~~java
class Good<
    @ParamInfo("item") T extends
        @BoundInfo("number") Number
        & @BoundInfo("order") Comparable<T>
> {}
~~~

Wrong-order example (only for recognizing the error):

~~~java
// Wrong: class Number cannot appear after an interface in the bounds list.
// class Wrong<T extends Comparable<T> & Number> {}
~~~

If annotations need to be placed on each bound, they must be written individually for each type after `extends`/`&`. If an annotation is placed only before `T`, that position is the type parameter declaration and is not interpreted as an annotation on the entire set of bounds.

### When a Bound Is a Parameterized Type

In the main example, `Comparable<@BoundInfo("argument") T>` has two layers of metadata:

- The `"comparable"` annotation on the bound type `Comparable<T>` itself.
- The `"argument"` annotation on the use of `T` as a **type argument** inside `Comparable<T>`.

Therefore, `t.getAnnotatedBounds()[1].getAnnotation(BoundInfo.class)` gives `"comparable"`; to retrieve `"argument"`, you must step one level down into `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[0]`. This is why Reflection has an `AnnotatedType` family rather than just a flat list of annotations.

## 10. Common Mistakes

**1. Using `@Target(TYPE_PARAMETER)` to annotate an upper bound.** An annotation with that target is for the declaration of `T`. To place it on the `Number` type after `extends` or on a type after `&`, declare the target `TYPE_USE`.

**2. Confusing `TYPE_PARAMETER` with `TYPE`.** `TYPE` is primarily for class/interface/enum/annotation type declarations; it is not the target name dedicated to generics type parameters. `TYPE_USE` is broader and covers type uses.

**3. Thinking bound annotations determine generic constraints.** Only `extends Number & Comparable<T>` determines Java's constraints; annotations do not add new type checks unless a tool understands them.

**4. Calling `getBounds()` and expecting to read annotations.** `getBounds()` returns `Type[]` representing the bounds; use `getAnnotatedBounds()` to retrieve metadata attached to each type use.

**5. Calling only `Class.getAnnotation(...)` and not finding the annotation on `T`.** Those are two different Reflection elements. An annotation declared on a type parameter belongs to the `TypeVariable` from `Class.getTypeParameters()`, and does not automatically become an annotation on the class.

**6. Forgetting retention.** By default, an annotation type has `CLASS` retention; to query declarations and bounds at runtime, the annotation needs `@Retention(RUNTIME)`.

**7. Using the wrong index.** `getAnnotatedBounds()` returns bounds in declaration order; for `T extends Number & Comparable<T>`, index 0 is `Number` and index 1 is `Comparable<T>`. For a type variable without an explicit bound, the array typically contains an unannotated `Object`.

**8. Confusing an annotated bound with an annotated type argument inside the bound.** A `Comparable<@BoundInfo T>` is read via `AnnotatedParameterizedType`. The annotation on `Comparable` and the one on `T` inside it are at different positions.

**9. Confusing a class type parameter with a method type parameter.** `Box<T>` and `<U> U echo(U input)` declare different type variables. To retrieve `U`, use `Method.getTypeParameters()`.

**10. Ordering class/interface bounds incorrectly.** A specific class bound, if present, must precede interface bounds. Adding annotations does not fix syntax errors or generic constraint errors.

**11. Thinking `TYPE_USE` is only valid on bounds.** It is also valid in many type use positions such as type arguments, casts, return types, and in certain declaration contexts, including type parameter declarations according to language rules.

**12. Assuming annotations already exist on each instance.** Metadata on the declaration of `T` or on its bounds is attached to the class/method structure in the class file. Creating multiple instances of the same generic class does not generate separate metadata for each instance.

## 11. Practice Exercises

1. Create `class Pair<@ParamInfo("K") K, @ParamInfo("V") V> {}`. Use `Pair.class.getTypeParameters()` to print the name and `@ParamInfo` value of both declarations.
2. Add `@BoundInfo("numeric")` to `Number` in `T extends Number`. Predict why `getAnnotation(BoundInfo.class)` on `TypeVariable<T>` and on `getAnnotatedBounds()[0]` return different results.
3. Create a generic method `<@ParamInfo("X") X extends @BoundInfo("text") CharSequence> X choose(X value)`. Use `Method.getTypeParameters()` to read the declaration and bounds annotations. Explain why the erased parameter type is `CharSequence`.
4. Extend the `Box` example to `Comparable<@BoundInfo("arg") T>`; use `AnnotatedParameterizedType` to read the annotation on the type argument. Compare it with the annotation on the `Comparable` bound.
5. Remove the upper bound from `class Free<V>` and use `getAnnotatedBounds()`. Explain why Java reports `Object` even though the source does not write `extends Object`.
6. Try attaching `@ParamInfo` directly onto `Number` after `extends` when `@ParamInfo` only has target `TYPE_PARAMETER`. Record the compiler error and explain the `@Target` choice.
7. Create an annotation `@Check` with `@Target(TYPE_USE)`. Try attaching it both before the name `T` and before the bound `Number`. Observe compilation behavior and the Reflection API that reads each position.
8. Use `javap -v Box` to distinguish the metadata for the type parameter declaration, type parameter bound, and the annotation on the type argument inside the bound. Trace the path of each value `T`, `number`, `comparable`, and `argument`.

## 12. Key Takeaways Checklist

- `<@ParamInfo T>`: annotation at the **type parameter declaration** `T`.
- `T extends @BoundInfo Number`: annotation on the **use of type `Number` as a bound**.
- `T extends Number & @BoundInfo Comparable<T>`: annotation on the second bound.
- `Comparable<@BoundInfo T>`: annotation on a type argument that is a use of `T`.
- `TYPE_PARAMETER` is dedicated to declarations; `TYPE_USE` is valid for bounds and many other type use positions, and can also be used at type parameter declarations.
- `TypeVariable.getAnnotation(...)` reads annotations on the type parameter declaration; `TypeVariable.getAnnotatedBounds()` returns the annotated upper bounds.
- `AnnotatedParameterizedType` helps drill down into type arguments inside a parameterized bound.
- `@Retention(RUNTIME)` is required to read the corresponding annotations via runtime Reflection; the default retention is `CLASS`.
- Annotation metadata does not by itself change generic type checking, erasure, or JVM behavior.

Understanding these points will help you accurately read annotations on generics in Java Core, while preparing you for advanced tools that process type-use annotations.

### References

- [Java Language Specification 17 — `4.4: Type Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.4).
- [Java Language Specification 17 — `9.6.4.1: @Target](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.1).
- [Java SE 17 — ElementType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/ElementType.html).
- [Java SE 17 — TypeVariable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/TypeVariable.html).
- [Java SE 17 — AnnotatedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html).
- [Java SE 17 — AnnotatedParameterizedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html).
