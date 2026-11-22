# Distinguishing Type and AnnotatedType When Reading Type Metadata in Java Core

In Java Reflection, **`java.lang.reflect.Type` describes the structure of a type** (for example `List<String>`, `T`, or `? extends Number`), whereas **`java.lang.reflect.AnnotatedType` associates that type structure with the annotations placed directly on the *type use***. When reading annotations that use `@Target(TYPE_USE)`, relying solely on `Type` is usually not enough: you must start from an API that returns an `AnnotatedType` and then follow the right branch in the type tree.

This lesson focuses on reading metadata at runtime, assuming the relevant annotations have `@Retention(RUNTIME)`. This is a Java Core mechanism, independent of any framework.

## 1. Learning Objectives

After this lesson, you will be able to:

- Clearly explain the information that `Type` and `AnnotatedType` represent.
- Recognize the structural forms `Class`, `ParameterizedType`, `TypeVariable`, `WildcardType`, and `GenericArrayType`.
- Use the right API pairs: `getGenericType()` / `getAnnotatedType()` on fields, `getGenericReturnType()` / `getAnnotatedReturnType()` on methods, and `getBounds()` / `getAnnotatedBounds()` on type parameters.
- Read annotations on outer types, nested type arguments, generic upper bounds, and wildcard upper/lower bounds.
- Distinguish annotations on a **field/method/class declaration** from annotations on the **type being used** within that declaration.
- Understand why `getType()` on `AnnotatedType` does not automatically put annotations into `Type`, and why type erasure does not prevent Reflection from reading stored generic metadata.
- Run the Java 17+ example yourself and predict the Reflection output.

## 2. Starting with the Question: Do You Want to Read the Type Structure or Annotations on the Type?

Consider a declaration:

~~~java
List<@Mark("item") String> names;
~~~

Suppose `@Mark` is an annotation with target `TYPE_USE` and retention `RUNTIME`.

There are at least three distinct layers of information:

1. The field named `names` is **a field declaration**.
2. The type of the field is `List<String>`, where `List` is the generic type and `String` is the type argument.
3. The annotation `@Mark("item")` is attached to **the use of the `String` type as a type argument** in `List<String>`.

The `Field.getGenericType()` API provides layer 2 — the type structure. The `Field.getAnnotatedType()` API provides the path to read layer 3. If an annotation is attached to the field declaration itself with target `FIELD`, you read it via `Field.getAnnotation(...)`: that is a different location.

An example with both kinds of annotations:

~~~java
@FieldTag
List<@Mark("item") String> names;
~~~

`@FieldTag` (if its target is `FIELD`) describes the field; `@Mark` (target `TYPE_USE`) describes the type argument `String`. They do not replace each other; a single field can contain both declaration metadata and type-use metadata.

## 3. `Type`: The Generic Structure Model, Not Yet the Place to Retrieve Annotations

`Type` is an interface in the `java.lang.reflect` package. It helps describe a reflected Java type, including types with generic arguments. Important implementations/branches include:

| `Type` Form | Source Example | Meaning |
| --- | --- | --- |
| `Class<?>` | `String`, `int[]`, or a raw class | A class, interface, primitive, or array type represented by `Class` when appropriate |
| `ParameterizedType` | `List<String>` | A generic type with actual type arguments |
| `TypeVariable<?>` | `T` in `class Box<T>` | A type parameter declared by a class, method, or constructor |
| `WildcardType` | `? extends Number` or `? super Integer` | A wildcard with upper/lower bounds |
| `GenericArrayType` | `T[]` or `List<String>[]` | An array type whose component needs to be described by a generic type |

Basic APIs:

~~~java
Type type = SomeClass.class
        .getDeclaredField("names")
        .getGenericType();

System.out.println(type.getTypeName());
~~~

This is just an illustrative snippet: `SomeClass` must exist, and the `java.lang.reflect.Type` import must be provided. If the field is `List<String>`, `getTypeName()` typically represents `java.util.List<java.lang.String>`.

What **`Type` does not provide directly** is `getAnnotation(Mark.class)`; the `Type` interface does not extend `AnnotatedElement`. Although a concrete object such as `Class` or `TypeVariable` also has annotation APIs because those interfaces/classes implement additional contracts, calling an annotation API on `Class` or `TypeVariable` does not by default mean you are reading **an annotation at a type-use position**.

For example, `Box.class.getAnnotation(...)` reads declaration metadata on the class; `TypeVariable.getAnnotation(...)` reads annotations on the type parameter declaration. Neither of these is equivalent to reading an annotation on a type argument nested inside `List<...>`.

## 4. `AnnotatedType`: Type at a Use Site Along with TYPE_USE Metadata

`AnnotatedType` is also in `java.lang.reflect`, but it extends `AnnotatedElement`; therefore, you can call these methods:

- `getAnnotation(Tag.class)` or `getDeclaredAnnotation(Tag.class)` to retrieve an annotation at **the exact current type position**.
- `getAnnotations()`, `getDeclaredAnnotations()` to retrieve the annotations at this position.
- `getType()` to retrieve the underlying `Type` of that type position.

Example:

~~~java
AnnotatedType annotated = SomeClass.class
        .getDeclaredField("names")
        .getAnnotatedType();

Type underlying = annotated.getType();
Mark here = annotated.getAnnotation(Mark.class);
~~~

If `names` is declared as `List<@Mark("item") String>`, then the `here` variable on the **outer type `List`** may be `null`, because `@Mark` is on the **inner type argument**, not on `List`. To read it, you must traverse deeper into the structure.

Important subtypes:

| Interface Extending `AnnotatedType` | When Is It Used? | API to Access Child Parts |
| --- | --- | --- |
| `AnnotatedParameterizedType` | `List<...>`, `Map<...>` | `getAnnotatedActualTypeArguments()` |
| `AnnotatedArrayType` | Array types | `getAnnotatedGenericComponentType()` |
| `AnnotatedWildcardType` | `? extends X`, `? super Y` | `getAnnotatedUpperBounds()`, `getAnnotatedLowerBounds()` |
| `AnnotatedTypeVariable` | A use of a type parameter, for example `T` | `getAnnotatedBounds()` |
| Plain `AnnotatedType` | A type without a special substructure | `getType()` and the annotation API |

**Important principle:** Each `AnnotatedType` represents only one **position** in the type structure. Annotations on `List`, `String` inside `List`, the wildcard `?`, and the wildcard's bound are different positions. To read accurately, traverse the `AnnotatedType` tree properly.

## 5. Comparison via Reflection API Table

| Starting Point | API Returning Only `Type` Structure | API Preserving Annotations at Type-Use Position |
| --- | --- | --- |
| `Field` | `getGenericType()` | `getAnnotatedType()` |
| `Method` return value | `getGenericReturnType()` | `getAnnotatedReturnType()` |
| `Method` parameters | `getGenericParameterTypes()` | `getAnnotatedParameterTypes()` |
| `Executable` `throws` | `getGenericExceptionTypes()` | `getAnnotatedExceptionTypes()` |
| `Constructor` parameters | `getGenericParameterTypes()` | `getAnnotatedParameterTypes()` |
| `Class` and superclass | `getGenericSuperclass()` | `getAnnotatedSuperclass()` |
| `Class` and interfaces | `getGenericInterfaces()` | `getAnnotatedInterfaces()` |
| `TypeVariable<?>` and bounds | `getBounds()` | `getAnnotatedBounds()` |
| `ParameterizedType` and arguments | `getActualTypeArguments()` | Use `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` on a position already obtained via an annotated API |

Note: `ParameterizedType` does not have a `getAnnotatedActualTypeArguments()` method. You must have an instance of `AnnotatedParameterizedType`; for example, obtain it from `Field.getAnnotatedType()` if the field declaration is a parameterized type. Not every `AnnotatedType` can be cast to `AnnotatedParameterizedType`.

When you only need to know that a field is `List<String>`, `getGenericType()` is usually sufficient. When you need to know the annotations on the `List` or `String` type, choose `getAnnotatedType()`.

## 6. Standalone Java 17+ Example: Type, AnnotatedType, and Nested Branches

Create the file **`TypeVsAnnotatedTypeDemo.java`** without a `package` declaration for simple compilation. The entire program below resides in a single file; only the class containing `main` is `public`.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.AnnotatedWildcardType;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Mark {
    String value();
}

class Catalog<T extends @Mark("bound") Number> {
    @Mark("outer")
    List<@Mark("item") String> names;

    List<? extends @Mark("upper") Number> sources;

    List<? super @Mark("lower") Integer> sinks;

    @Mark("return")
    List<@Mark("resultItem") String> find() {
        return List.of("ok");
    }
}

public class TypeVsAnnotatedTypeDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {

        Field field = Catalog.class.getDeclaredField("names");
        Type rawType = field.getGenericType();
        AnnotatedParameterizedType decorated =
                (AnnotatedParameterizedType) field.getAnnotatedType();

        System.out.println("generic=" + rawType.getTypeName());
        System.out.println("outer="
                + decorated.getAnnotation(Mark.class).value());
        System.out.println("argument="
                + decorated.getAnnotatedActualTypeArguments()[0]
                           .getAnnotation(Mark.class).value());

        System.out.println("fieldAnnotations="
                + field.getAnnotations().length);

        TypeVariable<?> variable = Catalog.class.getTypeParameters()[0];
        System.out.println("bound=" + variable.getAnnotatedBounds()[0]
                .getAnnotation(Mark.class).value());

        for (String name : List.of("sources", "sinks")) {
            Field wildcardField = Catalog.class.getDeclaredField(name);
            AnnotatedParameterizedType listType =
                    (AnnotatedParameterizedType)
                    wildcardField.getAnnotatedType();
            AnnotatedWildcardType wildcard =
                    (AnnotatedWildcardType)
                    listType.getAnnotatedActualTypeArguments()[0];

            if (name.equals("sources")) {
                System.out.println("upper="
                        + wildcard.getAnnotatedUpperBounds()[0]
                                  .getAnnotation(Mark.class).value());
            } else {
                System.out.println("lower="
                        + wildcard.getAnnotatedLowerBounds()[0]
                                  .getAnnotation(Mark.class).value());
            }
        }

        Method method = Catalog.class.getDeclaredMethod("find");
        AnnotatedType returnType = method.getAnnotatedReturnType();
        System.out.println("return="
                + returnType.getAnnotation(Mark.class).value());

        AnnotatedParameterizedType listReturn =
                (AnnotatedParameterizedType) returnType;
        System.out.println("returnArg="
                + listReturn.getAnnotatedActualTypeArguments()[0]
                            .getAnnotation(Mark.class).value());
    }
}
~~~

Compile and run using JDK 17 or later:

~~~bash
javac -encoding UTF-8 TypeVsAnnotatedTypeDemo.java
java TypeVsAnnotatedTypeDemo
~~~

**Exact stdout:**

~~~text
generic=java.util.List<java.lang.String>
outer=outer
argument=item
fieldAnnotations=0
bound=bound
upper=upper
lower=lower
return=return
returnArg=resultItem
~~~

### Where Does Each Line of Output Come From?

1. `Field.getGenericType()` returns the type `List<String>`, so `getTypeName()` displays `java.util.List<java.lang.String>`. This value does not tell you about the strings `"outer"` and `"item"`.
2. `field.getAnnotatedType()` returns an `AnnotatedParameterizedType`. `getAnnotation(Mark.class)` on the **outer type `List`** reads `"outer"`.
3. `getAnnotatedActualTypeArguments()[0]` descends into the `String` type inside `List`; at that position, `"item"` is read.
4. `field.getAnnotations().length` equals `0` because `Mark` only has the `TYPE_USE` target, meaning the annotations describe **how the type is used**, and are not attached as a `FIELD`-style field declaration annotation. If an annotation type simultaneously has multiple targets and is used in a qualifying context, you need to check the exact declared targets/annotations.
5. `Catalog.class.getTypeParameters()[0]` retrieves the type parameter `T`; `getAnnotatedBounds()[0]` points to the type-use `Number` in `T extends @Mark("bound") Number`, yielding `"bound"`.
6. `sources` contains the wildcard `? extends @Mark("upper") Number`; `AnnotatedWildcardType.getAnnotatedUpperBounds()[0]` reads `"upper"`.
7. `sinks` contains the wildcard `? super @Mark("lower") Integer`; `AnnotatedWildcardType.getAnnotatedLowerBounds()[0]` reads `"lower"`.
8. `find()` returns the outer type `@Mark("return") List<...>`, and `"return"` is read on `getAnnotatedReturnType()`.
9. Inside the return type, the type argument `String` has `@Mark("resultItem")`, read via `getAnnotatedActualTypeArguments()[0]`.

The program does not call `Catalog.find()`; it only reads metadata on the method declaration and type-use positions. `@Mark` does not automatically run checks or change the result of the method.

## 7. Deep Dive into Important Positions

### 7.1. Outer Type and Type Arguments Inside the Outer Type

Consider:

~~~java
@Mark("outer")
List<@Mark("item") String> names;
~~~

There is a small tree:

~~~text
AnnotatedParameterizedType: List<String>
    |
    +-- annotation on List: @Mark("outer")
    |
    +-- AnnotatedType for type argument String
            |
            +-- @Mark("item")
~~~

`getAnnotatedType()` from the field enters the outer node. If you only call `getAnnotation(Mark.class)` on the outer node, you cannot assume you have read every annotation inside nested type arguments. You need to iterate over each type argument, and continue descending deeper if an argument is also a parameterized type or an array.

For example, `Map<@Mark("key") String, List<@Mark("value") Integer>>` has more branches: the first argument is an annotated `String`, and the second argument is `List<Integer>`; to get `"value"`, you must traverse from the annotated outer `Map` to the second argument (`List`), and then to the argument of `List` (`Integer`).

### 7.2. Wildcards and Bounds

The structures:

~~~java
List<? extends @Mark("upper") Number> sources;
List<? super @Mark("lower") Integer> sinks;
~~~

`List<...>` has a wildcard as its type argument. A wildcard can have an upper bound (`extends`) or a lower bound (`super`). The appropriate APIs:

~~~java
AnnotatedWildcardType wildcard =
        (AnnotatedWildcardType)
        ((AnnotatedParameterizedType) someField.getAnnotatedType())
                .getAnnotatedActualTypeArguments()[0];

AnnotatedType[] upperBounds = wildcard.getAnnotatedUpperBounds();
AnnotatedType[] lowerBounds = wildcard.getAnnotatedLowerBounds();
~~~

This is an illustrative snippet using the `someField` variable provided by the caller, not a standalone runnable program. For `? extends @Mark("upper") Number`, read the `upperBounds[0]` position. For `? super @Mark("lower") Integer`, read `lowerBounds[0]`. When `?` has no explicit bound, the effective upper bound is `Object`; do not assume every branch has an annotation.

You can annotate **the wildcard type-use itself** (where permitted by Java syntax) and **the bound type**; these are distinct positions in the annotated type tree. Identify which token the annotation immediately precedes, and traverse to that exact point.

### 7.3. Type Variables: Declaration Differs from Use

Declaration:

~~~java
class Holder<@ParamTag T extends @Mark("bound") Number> {}
~~~

Suppose `@ParamTag` has target `TYPE_PARAMETER` and retention `RUNTIME`. Then:

- `Holder.class.getTypeParameters()[0].getAnnotation(ParamTag.class)` reads from **the declaration of type parameter `T`**.
- `Holder.class.getTypeParameters()[0].getAnnotatedBounds()[0].getAnnotation(Mark.class)` reads from **the `Number` type used as the bound**.
- A use of `T` in `T value;` can be annotated with another `TYPE_USE` annotation; metadata at that use site does not automatically appear on the declaration of `T`.

`TypeVariable` can read annotations on its declaration because it is itself an `AnnotatedElement`. This **does not turn every `Type` object into an `AnnotatedType`**. If you want to read an annotation at a type variable use site in a field or method, start from the annotated API of the element containing that use and inspect the corresponding `AnnotatedTypeVariable`.

### 7.4. Array Types Can Have Multiple Annotation Positions

With arrays, the dimensionality is part of the type structure. `AnnotatedArrayType` lets you traverse from the outer array into the component type using `getAnnotatedGenericComponentType()`.

Syntax example:

~~~java
@Mark("element") String @Mark("dimension") [] values;
~~~

`@Mark("element")` is on the component type `String`, whereas `@Mark("dimension")` is at the array dimension position. Calling the annotation API on the annotated outer array and then descending to the component type can return different metadata. You should not treat `String[]` as a single leaf when reading type-use annotations.

For multidimensional arrays, there can be multiple annotation placement points corresponding to each dimension; you must follow the chain of `AnnotatedArrayType`. If you only need to know that the array type is `String[]`, `getGenericType()` may still suffice, though it does not provide a path to read each type-use annotation.

### 7.5. Method Return and Parameters

A method can have annotations on its return type and on each parameter type:

~~~java
@Mark("result") String convert(@Mark("argument") String text) {
    return text;
}
~~~

This is an illustrative method inside a class that already has the `Mark` annotation type. To read it:

~~~java
Method method = SomeClass.class.getDeclaredMethod(
        "convert", String.class);

AnnotatedType result = method.getAnnotatedReturnType();
AnnotatedType firstParam = method.getAnnotatedParameterTypes()[0];
~~~

If you only need the structure, use `getGenericReturnType()` and `getGenericParameterTypes()` respectively. A `Parameter` also provides `getAnnotatedType()`. If you need a declaration annotation on the **parameter** with target `PARAMETER`, use `Parameter.getAnnotation(...)` instead; it is different from a `TYPE_USE` annotation on the **type** of the parameter itself.

## 8. Do Not Confuse `AnnotatedType` with a Declaration's `AnnotatedElement`

A very common misconception is that "any Reflection object with `getAnnotation` is querying the same metadata." That is incorrect.

| Target Object Queried | What `getAnnotation(Tag.class)` Reads From |
| --- | --- |
| `Class<?>` | Class/interface declaration (with class inheritance semantics when applicable) |
| `Method` | Method declaration |
| `Field` | Field declaration |
| `Parameter` | Parameter declaration |
| `TypeVariable<?>` | Type parameter declaration |
| `AnnotatedType` | **A type-use position** |

For example, `Field.getAnnotation(Mark.class)` and `Field.getAnnotatedType().getAnnotation(Mark.class)` can return different results. In the main example, the former finds no `Mark` annotation on the field declaration; the latter finds `@Mark("outer")` on the `List` type.

An annotation type can have multiple targets, for example `@Target({FIELD, TYPE_USE})`. In that case, a position in Java syntax may apply to multiple contexts, and the compiler has rules to store metadata under the appropriate targets. To avoid guessing from the `@` symbol, check the target declaration, the Java construct, and the API you use to read it.

**Important:** `@Retention(RUNTIME)` is an important requirement for Reflection to read type-use metadata. If `@Retention` is omitted, the default is `CLASS`: the information may exist in the `.class` file, but it is not exposed via standard runtime Reflection.

## 9. Does Type Erasure Lose All of This Information?

Java generics use *type erasure* to produce runtime signatures compatible with the JVM model. For example, a `List<String>` manipulated by runtime code is not treated as a "reified object" carrying the full `String` type argument inside each instance.

However, class files can retain the **Signature attribute** and annotation attributes on **declarations**, so Reflection can still read the generic structure of fields, method returns, superclasses, or generic bounds saved by the compiler.

Therefore, the following two statements can both be true at the same time:

- An object `new ArrayList<String>()` does not reveal its full `String` type argument solely through `object.getClass()`.
- A field declared as `List<@Mark String> names;` allows Reflection to read `List<String>` and the annotation on the `String` type argument via `Field.getAnnotatedType()`.

**Metadata content depends on the declaration site and the compiled bytecode**; you cannot expect `getClass()` on an arbitrary object to always recover every generic type argument used at the object's instantiation site. Nor does a `TYPE_USE` annotation automatically force the JVM to enforce validation.

## 10. Verifying Metadata in Bytecode with `javap`

After compiling the main example:

~~~bash
javap -v Catalog
~~~

With `RUNTIME` retention, the Java compiler can record metadata in attributes such as `RuntimeVisibleTypeAnnotations` on fields, methods, and generic declarations. The `javap -v` output can show different targets/type paths: the outer type `List`, the type argument `String`, the `Number` bound, wildcard bounds, and the annotated return type.

Display details such as constant pool indices, bytecode offsets, or target path notation may vary across toolchain versions. What needs to be verified is that **the annotations reside at the right type-use positions**. You should not hardcode long `javap` output into examples if the environment in use differs.

`javap` is a tool for inspecting bytecode metadata; Reflection uses Java APIs to query the metadata supported by the runtime. `Type` and `AnnotatedType` are two different views over the stored structure/annotations, not a single API you can arbitrarily cast back and forth between.

## 11. How to Choose the Right API in Practice

Start from the **declaration object**, then move to the structural part you need to read:

1. If you have a `Field`, decide whether you want to read **an annotation attached to the field** or **an annotation on the field's type**. Use `field.getAnnotation(...)` for the first case; `field.getAnnotatedType()` for the second case.
2. If you have a `Method`, use `method.getAnnotatedReturnType()` or `method.getAnnotatedParameterTypes()` for annotations at type-use positions. Use `method.getAnnotation(...)` when the annotation is attached to the method declaration.
3. If you have a `Class<?>`, use `getAnnotatedSuperclass()` or `getAnnotatedInterfaces()` when you need annotations on the declared superclass/interfaces; use `getAnnotation(...)` for declaration annotations on the class.
4. If you have a `TypeVariable<?>`, use `getAnnotation(...)` to read from the type parameter declaration, and `getAnnotatedBounds()` to read from the type parameter's bounds.
5. If the annotated type is parameterized, an array, or a wildcard, descend using the appropriate specialized interface. Check the runtime type of the annotated object before casting to avoid `ClassCastException`.
6. When an annotation might be absent, check for `null`; when a collection of annotated children might be empty, check the length before indexing.

A general pattern for when the field is a parameterized type:

~~~java
AnnotatedType type = field.getAnnotatedType();

if (type instanceof AnnotatedParameterizedType parameterized) {
    for (AnnotatedType argument :
            parameterized.getAnnotatedActualTypeArguments()) {
        Mark annotation = argument.getAnnotation(Mark.class);
        if (annotation != null) {
            System.out.println(annotation.value());
        }
    }
}
~~~

The snippet above is **an illustrative pattern in a context where the `field` variable and the `Mark` annotation already exist**; it does not run standalone. Java 17 supports the `instanceof` pattern variable syntax. If `field` holds an array or a non-parameterized type, the processing branch does not execute — which is safer than unconditional casting.

## 12. Common Mistakes

**1. Calling `Type.getAnnotation(...)`.** `Type` does not declare this method. If you need type-use annotations, start from an `AnnotatedType` obtained through the appropriate annotated API.

**2. Calling only `getGenericType()` and concluding there are no annotations.** APIs returning `Type` only provide structure; annotations on type arguments can still be retained in the class file and read via `getAnnotatedType()`.

**3. Reading the annotation on the outer type when it is on the type argument.** `List<@Mark String>` has the annotation on `String`. To read it, you must call `getAnnotatedActualTypeArguments()[0]` from `AnnotatedParameterizedType`.

**4. Calling `Field.getAnnotation(...)` when the annotation has target `TYPE_USE`.** That queries declaration metadata, not type-use metadata. Choose `field.getAnnotatedType()` to read annotations on the type.

**5. Casting every `AnnotatedType` to `AnnotatedParameterizedType`.** If the actual type is a plain class, an array, or a wildcard, the cast can fail. Use `instanceof` or determine the structure beforehand.

**6. Skipping the nested type path.** For `Map<String, List<@Mark Integer>>`, you must go into the second argument of `Map`, and then the first argument of `List` to reach `Integer`. There is no rule that automatically propagates annotations up to parent nodes.

**7. Using `TypeVariable.getAnnotation(...)` to read annotations on a bound.** That API reads annotations on the declaration of `T`, whereas an annotation after `extends` is on the type use of the bound. Use `getAnnotatedBounds()`.

**8. Confusing wildcard bounds with type variable bounds.** `? extends Number` is read via `AnnotatedWildcardType`; `T extends Number` uses `TypeVariable.getAnnotatedBounds()`. The two syntaxes and Reflection traversal paths are different.

**9. Assuming Java will use the annotation to coerce types or validate.** An annotation does not automatically alter type erasure, check for null, block values, or create runtime behavior. You need a processor that understands the annotation to add such logic.

**10. Forgetting `@Retention(RUNTIME)`.** An annotation with target `TYPE_USE` but the default `CLASS` retention still cannot be read via standard runtime Reflection.

**11. Thinking generic type arguments can always be recovered from an instance.** That information can only be reflected from declarations/types where the compiler stored metadata; `object.getClass()` does not retain all type arguments used to create the object.

**12. Confusing `@Target(TYPE_USE)` with `@Target(TYPE)`.** `TYPE` targets class/interface/enum/annotation type declarations; `TYPE_USE` targets places where types are used. You must declare the target that matches your intended purpose.

## 13. Self-Practice Exercises

1. **Structure:** Declare `List<String> names;`. Use `Field.getType()`, `Field.getGenericType()`, and `Field.getAnnotatedType().getType()`; compare what information each API provides.
2. **Type argument annotation:** Change it to `List<@Mark("element") String>`. Predict `getAnnotation(Mark.class)` on the field declaration, the annotated outer type, and the annotated argument.
3. **Nested generics:** Try `Map<@Mark("key") String, List<@Mark("nested") Integer>>`. Use `AnnotatedParameterizedType` multiple times to read the two annotations on the right type arguments.
4. **Wildcard:** Create a field `List<? extends @Mark("limit") Number>`. Use `AnnotatedWildcardType.getAnnotatedUpperBounds()`, then switch to `? super @Mark("floor") Integer` and use the lower bounds.
5. **Type variable:** Create `class NumberBox<T extends @Mark("number") Number>`. Use `getTypeParameters()[0].getAnnotatedBounds()[0]`, and compare it with `getBounds()[0]`.
6. **Declaration and type use:** Create an annotation with target `FIELD` distinct from `Mark` with target `TYPE_USE`; attach both to a field. Read them separately via `Field.getAnnotation` and `Field.getAnnotatedType`.
7. **Array type:** Create a field with `String @Mark("array") []`. Traverse `AnnotatedArrayType` to the component type, and observe the exact location where the annotation is returned.
8. **Method:** Create a method returning `List<@Mark("output") String>` and taking `List<@Mark("input") Integer>`; compare `getGenericReturnType`/`getAnnotatedReturnType` and `getGenericParameterTypes`/`getAnnotatedParameterTypes`.
9. **Erasure:** Create `new ArrayList<String>()` and print `getClass()`, then compare it with the metadata on a field declared as `List<String>` to see that not all type arguments can be inferred from a runtime object.
10. **Bytecode:** Run `javap -v Catalog`. Locate the type-use annotations and the bound/type argument positions; match them against each line of stdout from the main program.

## 14. Summary Checklist

- **`Type`**: what type it is and what its generic structure looks like; primary APIs such as `getTypeName()`, `ParameterizedType.getActualTypeArguments()`, and `TypeVariable.getBounds()`.
- **`AnnotatedType`**: which type-use position it is and the annotations attached to that exact position; provides `getType()` along with the annotation API.
- **`Field.getGenericType()`** and **`Field.getAnnotatedType()`** return two different views of the same field type.
- **`AnnotatedParameterizedType`**: descends into annotated type arguments.
- **`AnnotatedWildcardType`**: descends into the annotated upper/lower bounds of a wildcard.
- **`AnnotatedArrayType`**: descends into the annotated component type of an array.
- **`TypeVariable.getAnnotatedBounds()`**: reads annotations on the bounds of a type parameter.
- **`Method.getAnnotatedReturnType()`** and **`getAnnotatedParameterTypes()`**: read at type-use positions in a method signature.
- **`@Retention(RUNTIME)`** and **`@Target(TYPE_USE)`** are two important choices so that annotations on types can be queried via Reflection at runtime.
- Annotations attached to a **declaration** and annotations attached to a **type use** must be distinguished by their syntactic position and the appropriate reading API.

Understanding these two interfaces properly helps analyze generics metadata accurately, especially when working with validation libraries, static analysis tools, or frameworks that process annotations deep inside type structures.

### References

- [Java SE 17 — Type](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Type.html).
- [Java SE 17 — AnnotatedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html).
- [Java SE 17 — AnnotatedParameterizedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html).
- [Java SE 17 — AnnotatedWildcardType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedWildcardType.html).
- [Java SE 17 — TypeVariable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/TypeVariable.html).
- [Java Language Specification 17 — `9.7.4, Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4).
