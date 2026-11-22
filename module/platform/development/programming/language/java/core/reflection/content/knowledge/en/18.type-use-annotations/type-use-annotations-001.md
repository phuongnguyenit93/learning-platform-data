# Distinguishing Declaration Annotations from Type-Use Annotations in Java Reflection

## 1. Why distinguish between the two annotation placement locations?

In Java, an annotation can describe **a declaration** or **a type use**. At a glance in source code, both annotations start with the `@` symbol, but their meaning and their access paths through Reflection are different.

Example:

```java
@Decl("field")
private @Use("type") List<@Use("element") String> names;
```

This is an illustrative snippet **inside a class**, assuming `Decl` is allowed on field declarations, `Use` is allowed on type uses, and the annotations have appropriate retention.

- `@Decl("field")` describes **the declaration of field `names`**.
- `@Use("type")` describes **the `List<...>` type used by the field**.
- `@Use("element")` describes **the generic type argument `String`** inside `List`.

If you only call `field.getDeclaredAnnotations()`, the program may see the declaration annotation but **not** see the type-use annotations. To find type-use annotations, you must obtain the `AnnotatedType` structure via `field.getAnnotatedType()` and, when needed, drill down into type arguments.

This lesson targets three capabilities:

1. Distinguish the placement and semantics of a *declaration annotation* from a *type-use annotation*.
2. Choose the right `@Target`, `@Retention`, and Reflection API to read annotations in Java 17+.
3. Avoid mistaking runtime metadata for an automatic type-checking mechanism or treating the annotation kinds as completely mutually exclusive.

## 2. What is a declaration annotation?

A *declaration annotation* is attached to **a program declaration**: class, interface, method, constructor, field, formal parameter, type parameter, etc. It typically provides metadata for the compiler, build tools, or frameworks.

Some familiar examples:

- `@Override` on a method declaration: the compiler checks whether the method properly overrides/satisfies the contract.
- `@Deprecated` on a class/member declaration: describes an API that is no longer recommended for use.
- `@Entity` (in ORM libraries) on a class: an example of an annotation describing a declaration.
- A custom `@Route` annotation on a method: metadata about an endpoint.
- `@Qualifier` or a custom annotation on a parameter declaration: describes how injection is performed.

Where an annotation is allowed to be placed is governed by the `@Target` meta-annotation.

| `ElementType` | Typical declaration scope |
| --- | --- |
| `TYPE` | Class, interface, enum, record declarations and corresponding types |
| `FIELD` | Field declaration |
| `METHOD` | Method declaration |
| `CONSTRUCTOR` | Constructor declaration |
| `PARAMETER` | Formal parameter declaration |
| `TYPE_PARAMETER` | Generic type parameter declaration such as `T` |
| `LOCAL_VARIABLE` | Local variable declaration |
| `ANNOTATION_TYPE` | Annotation type declaration |
| `PACKAGE` | Package declaration |
| `MODULE` | Module declaration |

The entries in the table are some of the `ElementType` values relevant to this topic; Java also has `TYPE_USE` for type-use locations. Do not treat `TYPE` and `TYPE_USE` as synonymous ways of writing the same thing.

Defining an annotation dedicated to field declarations:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface ColumnInfo {
    String value();
}
```

Using it on a field:

```java
class Book {
    @ColumnInfo("book_title")
    private String title;
}
```

After compiling, Reflection can find it:

```java
java.lang.reflect.Field f = Book.class.getDeclaredField("title");
ColumnInfo info = f.getDeclaredAnnotation(ColumnInfo.class);
System.out.println(info.value()); // book_title
```

The Reflection query snippet is **illustrative code inside a method** that handles/declares `NoSuchFieldException`. Because `ColumnInfo` has `RUNTIME` retention and is attached to a *field declaration*, reading the annotation directly from `Field` is appropriate.

## 3. What is a type-use annotation?

A *type-use annotation* is attached to **a use of a type**: the type of a field, a return type, a parameter type, a generic type argument, an array component, a superclass/interface type, a wildcard bound, a cast, a `new` expression, and other type-use contexts according to Java rules.

Definition:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface MarkType {
    String value();
}
```

Illustrative positions:

```java
class Basket {
    private @MarkType("field-type") String title;

    private java.util.List<@MarkType("element") String> labels;

    public @MarkType("return-type") String find(
            @MarkType("parameter-type") String key) {
        return key;
    }
}
```

In the example, the `@MarkType` markers apply to **type positions** rather than simply being annotations of `Field` or `Method`. If you want to read `@MarkType("element")` on `String` inside `List<String>`, you must traverse into the `AnnotatedParameterizedType` structure.

Key points:

- `@Target(TYPE_USE)` allows an annotation to appear in **type-use contexts**; it does not turn the annotation into a modifier like `public` or `private`, nor into a new runtime type.
- `String` and `@MarkType String` still share the same Java type `String` in terms of runtime class identity. The annotation only adds metadata.
- Compilers or static analysis tools can use type-use annotations to check nullness, ownership, thread-safety, etc., **if** a supporting checker is present. Java/the JVM does not automatically know how a custom `@NonNull` should reject null.
- An annotation with `@Retention(RUNTIME)` can be read by Reflection at **the type-use locations that the Reflection API can represent**. Not every annotation in every source expression has a high-level Reflection API for querying it.

## 4. A comparison table of positions and APIs

| What you want to observe | Reflection object | Primary API |
| --- | --- | --- |
| Annotation on class declaration | `Class<?>` | `getDeclaredAnnotations()`, `getDeclaredAnnotation(T.class)` |
| Annotation on field declaration | `Field` | `getDeclaredAnnotations()`, `getDeclaredAnnotation(T.class)` |
| Annotation on **field's type** | `Field` → `AnnotatedType` | `field.getAnnotatedType().getAnnotations()` |
| Annotation on method declaration | `Method` | `method.getDeclaredAnnotations()` |
| Annotation on **method's return type** | `Method` → `AnnotatedType` | `method.getAnnotatedReturnType().getAnnotations()` |
| Annotation on parameter declaration | `Parameter` | `parameter.getAnnotations()` or `getDeclaredAnnotations()` |
| Annotation on **parameter's type** | `Parameter` → `AnnotatedType` | `parameter.getAnnotatedType().getAnnotations()` |
| Annotation on exception types in `throws` | `Executable`/`Method` | `getAnnotatedExceptionTypes()` |
| Annotation on superclass type | `Class<?>` | `getAnnotatedSuperclass()` |
| Annotation on implemented interface types | `Class<?>` | `getAnnotatedInterfaces()` |
| Annotation on generic argument like `List<@T String>` | `AnnotatedParameterizedType` | `getAnnotatedActualTypeArguments()` |
| Annotation on array component/dimension type | `AnnotatedArrayType` | `getAnnotatedGenericComponentType()` |
| Annotation on wildcard bound | `AnnotatedWildcardType` | `getAnnotatedUpperBounds()`/`getAnnotatedLowerBounds()` |
| Annotation on type variable bound | `TypeVariable<?>` | `getAnnotatedBounds()` |
| Annotation on type parameter `T` declaration | `TypeVariable<?>` | `getAnnotations()`/`getDeclaredAnnotations()` |

**Do not confuse:** `Field.getGenericType()` returns a `Type` containing generic signature information, but it is **not sufficient** to retrieve all annotations located on each part of the type. When you need annotations, use the `getAnnotated...` family and subtypes of `AnnotatedType`.

## 5. Complete Java 17+ example: one declaration annotation, one type-use annotation

Save the following contents verbatim into **`AnnotationLocationDemo.java`**. The program uses two independent annotations:

- `@Decl`: applies only to **declarations** such as class, field, method, and parameter.
- `@Use`: declares only `@Target(TYPE_USE)` to mark **type-use locations**.

```java
import java.lang.annotation.*;
import java.lang.reflect.*;
import java.util.*;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.FIELD,
         ElementType.METHOD, ElementType.PARAMETER})
@interface Decl {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Use {
    String value();
}

class Base {}

@Decl("class")
class Example extends @Use("base") Base
              implements @Use("interface") Runnable {

    @Decl("field")
    private @Use("field-type") List<@Use("element") String> names;

    @Decl("method")
    public @Use("return") List<@Use("return-element") String> process(
            @Decl("parameter") @Use("param-type") String input) {
        return List.of(input);
    }

    @Override
    public void run() {}
}

public class AnnotationLocationDemo {
    private static String declared(AnnotatedElement element) {
        Decl annotation = element.getDeclaredAnnotation(Decl.class);
        return annotation == null ? "-" : annotation.value();
    }

    private static String typeUse(AnnotatedType type) {
        Use annotation = type.getAnnotation(Use.class);
        return annotation == null ? "-" : annotation.value();
    }

    public static void main(String[] args) throws Exception {
        Class<Example> type = Example.class;
        Field field = type.getDeclaredField("names");
        Method method = type.getDeclaredMethod("process", String.class);
        Parameter parameter = method.getParameters()[0];

        AnnotatedParameterizedType fieldType =
                (AnnotatedParameterizedType) field.getAnnotatedType();
        AnnotatedParameterizedType returnType =
                (AnnotatedParameterizedType) method.getAnnotatedReturnType();

        System.out.println("class declaration: " + declared(type));
        System.out.println("field declaration: " + declared(field));
        System.out.println("field type: " + typeUse(fieldType));
        System.out.println("generic argument: "
                + typeUse(fieldType.getAnnotatedActualTypeArguments()[0]));
        System.out.println("method declaration: " + declared(method));
        System.out.println("method return type: " + typeUse(returnType));
        System.out.println("return argument: "
                + typeUse(returnType.getAnnotatedActualTypeArguments()[0]));
        System.out.println("parameter declaration: "
                + declared(parameter));
        System.out.println("parameter type: "
                + typeUse(parameter.getAnnotatedType()));
        System.out.println("superclass type: "
                + typeUse(type.getAnnotatedSuperclass()));
        System.out.println("interface type: "
                + typeUse(type.getAnnotatedInterfaces()[0]));

        System.out.println("field use on declaration: "
                + (field.getDeclaredAnnotation(Use.class) != null));
        System.out.println("field decl on type: "
                + (field.getAnnotatedType().getAnnotation(Decl.class) != null));
    }
}
```

Compile targeting Java 17 and run:

```bash
javac --release 17 AnnotationLocationDemo.java
java AnnotationLocationDemo
```

Output from the program:

```text
class declaration: class
field declaration: field
field type: field-type
generic argument: element
method declaration: method
method return type: return
return argument: return-element
parameter declaration: parameter
parameter type: param-type
superclass type: base
interface type: interface
field use on declaration: false
field decl on type: false
```

The example intentionally does not instantiate `Example`; it only uses runtime metadata. All auxiliary classes/annotations are placed in the same Java file so that `javac` can compile it without extra libraries.

## 6. Explaining how to interpret the results

### 6.1. Class declaration

`@Decl("class")` is attached to the `class Example` declaration because `Decl` permits `ElementType.TYPE`.

```java
Decl d = Example.class.getDeclaredAnnotation(Decl.class);
```

This directly queries the annotation of the **Class**. It differs from annotations in `extends @Use Base` or `implements @Use Runnable`: those two places are **type uses** of the superclass/interface and must be looked up via `getAnnotatedSuperclass()` and `getAnnotatedInterfaces()`.

### 6.2. Field declaration and field type

Example:

```java
@Decl("field")
private @Use("field-type") List<@Use("element") String> names;
```

Three different metadata items:

1. `field.getDeclaredAnnotation(Decl.class)` returns `@Decl("field")`.
2. `field.getAnnotatedType().getAnnotation(Use.class)` returns `@Use("field-type")`.
3. `((AnnotatedParameterizedType) field.getAnnotatedType()).getAnnotatedActualTypeArguments()[0].getAnnotation(Use.class)` returns `@Use("element")` on the generic argument `String`.

**Why can't you just call `field.getDeclaredAnnotations()`?** Because that API queries annotations attached directly to the **field declaration**. Annotations used to describe the **field type** and **generic element type** live in a separate metadata branch, represented through `AnnotatedType`.

### 6.3. Method declaration and return type

`@Decl("method")` marks the method declaration `process`. `@Use("return")` marks the **return type `List<...>`**; `@Use("return-element")` marks the **generic type argument `String`** of the return type.

Therefore:

```java
method.getDeclaredAnnotation(Decl.class); // @Decl("method")
method.getAnnotatedReturnType()
      .getAnnotation(Use.class);           // @Use("return")
```

To see `return-element`, obtain `AnnotatedParameterizedType` and traverse `getAnnotatedActualTypeArguments()`. The `method.getReturnType()` API only returns `List.class` and does not contain the annotation position on `String`.

### 6.4. Parameter declaration and parameter type

In the declaration:

```java
@Decl("parameter") @Use("param-type") String input
```

The two annotations carry two different semantics:

- `parameter.getDeclaredAnnotation(Decl.class)`: annotation of the **parameter declaration**.
- `parameter.getAnnotatedType().getAnnotation(Use.class)`: annotation of the **`String` type** used by the parameter.

You should not infer that `method.getParameterAnnotations()` is enough to read all type-use annotations. That API provides annotations on parameter declarations; to retrieve annotations of the parameter's type, use `getAnnotatedParameterTypes()` or `Parameter.getAnnotatedType()`.

### 6.5. Annotated superclass and interfaces

`Example extends @Use("base") Base implements @Use("interface") Runnable` contains two type-use annotations at **type-use positions**. Retrieve them with:

```java
AnnotatedType parent = Example.class.getAnnotatedSuperclass();
AnnotatedType[] interfaces = Example.class.getAnnotatedInterfaces();
```

Then check `getAnnotation(Use.class)` on each `AnnotatedType`.

The distinction: `Example.class.getDeclaredAnnotations()` describes annotations of the **declaration of class Example**, and does not replace the annotated superclass/interface APIs.

### 6.6. What are the two `false` lines evidence of?

- `field.getDeclaredAnnotation(Use.class) == null`: in this example, `@Use("field-type")` does not appear as an annotation on the **field declaration**.
- `field.getAnnotatedType().getAnnotation(Decl.class) == null`: `@Decl("field")` does not describe the **field type**.

The last two lines print `false`. They illustrate a clean separation of metadata because the example uses two annotations with distinct `@Target` definitions.

**Do not generalize this into "an annotation cannot be both a declaration annotation and a type-use annotation."** In other contexts and with other `@Target` values, the same annotation type may be allowed on both declarations and type uses. The next section explains this boundary.

## 7. @Target determines valid locations, not just the annotation name

An annotation can be declared as:

```java
@Target(ElementType.FIELD)
@interface FieldOnly {}

@Target(ElementType.TYPE_USE)
@interface TypeOnly {}

@Target({ElementType.FIELD, ElementType.TYPE_USE})
@interface EitherLocation {}
```

This is an illustrative snippet on `@Target` (assuming `import java.lang.annotation.*;` is present). Without `@Retention(RUNTIME)`, these are not suitable examples for runtime querying via Reflection; they are used only to compare targets.

| Target | Intent |
| --- | --- |
| `FIELD` | Attach annotation to a field declaration |
| `TYPE_USE` | Attach annotation where a type is used, e.g., field type/generic argument |
| `FIELD, TYPE_USE` | Annotation may be used in both kinds of positions per Java rules |
| `PARAMETER` | Describe a parameter declaration |
| `TYPE_PARAMETER` | Describe a generic type parameter declaration |
| `TYPE` | Describe a class/interface/corresponding type declaration |

### An important nuance: TYPE_USE is not completely separate from declarations

Under Java rules, `TYPE_USE` can also apply at **certain type declaration positions**, including class/interface declarations and type parameter declarations. Therefore, from a source line that looks like "an annotation placed before a class name", you cannot conclude that the annotation is strictly a declaration annotation and cannot be a type-use annotation.

Furthermore, an annotation declaring targets that include **both `FIELD` and `TYPE_USE`** can cause the compiler to record the annotation at an eligible position for both declaration and type use. When writing analysis tools, clearly identify **which metadata you want to read** (declaration or type position), use the corresponding API, and inspect compiler output if the context has multiple `@Target` entries.

The two metadata kinds are two **descriptive dimensions**, not two Java type groups that are mutually exclusive by an absolute label.

## 8. @Retention directly affects Reflection

`@Target` determines **where an annotation may be validly placed**; `@Retention` determines **up to which stage the information is retained**.

| Retention policy | How long is the annotation retained? | Runtime Reflection |
| --- | --- | --- |
| `SOURCE` | For source/processors, usually not stored in the class file | Not readable at runtime |
| `CLASS` | Can be stored in the class file, but not runtime-visible | Not returned by standard Reflection APIs |
| `RUNTIME` | Stored in the class file under appropriate runtime-visible metadata | Readable via Reflection **if an API supports that position** |

The runnable example uses:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Use { String value(); }
```

If you omit `RetentionPolicy.RUNTIME`, the annotation defaults to `CLASS` retention and calls to `getAnnotation(Use.class)` in the program typically will not see the type-use metadata. Therefore, when getting `null`, check **retention**, **target**, **the exact element/type position**, and **post-compilation metadata** before assuming Reflection has a bug.

Never assume "present in source" = "present in runtime Reflection".

## 9. Routing by the shape of `AnnotatedType`

When a compound type contains multiple annotation positions, first obtain `AnnotatedType` from the declaration site (`Field.getAnnotatedType()`, `Method.getAnnotatedReturnType()`, etc.). `getType()` returns the **underlying type** as a `Type`; `getAnnotations()` only returns annotations of the **current position**, and does not automatically collect child branches.

| If the node is | How to access deeper annotations |
| --- | --- |
| `AnnotatedParameterizedType` | `getAnnotatedActualTypeArguments()` for each generic argument; `getAnnotatedOwnerType()` when an owner exists |
| `AnnotatedArrayType` | `getAnnotatedGenericComponentType()` to step down each dimension to the element |
| `AnnotatedWildcardType` | `getAnnotatedUpperBounds()` / `getAnnotatedLowerBounds()` for `? extends` / `? super` |
| `AnnotatedTypeVariable` | `getAnnotatedBounds()` for bounds of the type variable |
| Plain `AnnotatedType` | Read the node's annotations; there may be no child branches |

For example, `List<@Use("item") String>` has its annotation on the **`String` argument**, so you must go through `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[0]`, rather than querying `List.class` or `Field.getDeclaredAnnotations()`. Similarly, `? extends @Use("bound") Number` has its marker on the upper bound, while `String @Use("dimension") []` marks the array dimension.

A type parameter like `<@ParameterMark T extends @Use("bound") Number>` has **the declaration annotation on `T`** (read via `TypeVariable.getAnnotations()`) and **the type-use annotation on the bound** (read via `TypeVariable.getAnnotatedBounds()`): these are two separate places. Subsequent lessons build in-depth examples for each node kind, receiver/exception/return types, and hierarchies.

When writing a general recursive traverser, you must preserve **the path of each position**, explore the owner when present, and guard against bound cycles like `T extends Comparable<T>`. The chapter "Building a type tree traverser while preserving annotation positions" provides a visitor with cycle protection; do not use unconditional bound recursion in production.

## 10. How do declaration and type-use differ on a parameter?

Suppose an injection framework uses `@FromHeader` on a parameter declaration and a static checker uses `@NonNull` as a type use.

```java
void send(
    @FromHeader("X-Request") @NonNull String requestId) {
}
```

This snippet is **illustrative**: the two annotation types are not defined in this lesson, so it is not a standalone program. `@FromHeader` describes **the data source of the parameter**; `@NonNull` describes **the contract of the `String` type at the point of use**.

A framework can read:

```java
Parameter parameter = method.getParameters()[0];
Annotation[] declaration = parameter.getDeclaredAnnotations();
Annotation[] typeUse = parameter.getAnnotatedType().getAnnotations();
```

If each annotation is defined with the appropriate `@Target`/`@Retention`, the two arrays can reflect different metadata. Do not use `getParameterAnnotations()` as the sole path to collect type-use contracts, and do not use `getAnnotatedParameterTypes()` to replace injection information attached to the parameter declaration.

## 11. Declaration annotations vs. type-use annotations on a method

Consider the meaning of these two annotations:

```java
@Transaction
public @NonNull String findUser() {
    return "Ada";
}
```

This is an illustrative snippet; `Transaction`/`NonNull` are not yet defined.

- `@Transaction` describes the **method declaration**: requires a transaction (if supported by the framework).
- `@NonNull` describes the **return type `String`**: information that helps a static checker or framework validate the result (if enforced by the framework).

API:

```java
method.getDeclaredAnnotation(Transaction.class);
method.getAnnotatedReturnType().getAnnotation(NonNull.class);
```

The choice of API stems from the question: "Does this information describe **the declaration of a method** or **the type of the returned value**?"

With a generic return `List<@NonNull String>`, `@NonNull` can also be attached to the **type argument**, requiring traversal of `AnnotatedParameterizedType`.

## 12. Type-use annotations do not implicitly change Java behavior

Suppose an annotation is named `@NonNull`:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NonNull {}
```

Without a dedicated checker/framework, Java/the JVM **does not automatically throw an error** just because a `@NonNull String` variable receives a `null` value. An annotation is metadata, not a mechanism that automatically inserts `if (value == null) throw ...` statements.

With annotations like `@Nullable`/`@NonNull`, enforcement still depends on the **tooling**: static analysis, annotation processor, compiler plugin, runtime validation library, etc. Do not equate Reflection **reading metadata** with the JVM automatically enforcing that contract.

Similarly, a type-use annotation does not create a new `Class<?>`: `String.class` remains `String.class` even when uses of the `String` type carry different annotations.

## 13. Boundary of Reflection: it cannot read every type use inside a body

Type-use positions appear in:

- Field types, return types, and method parameters.
- Generic arguments and bounds.
- Declared superclasses/interfaces.
- Types in `throws`.
- Types in `new`, casts, `instanceof`, local variables, lambdas, and many other expressions.

Java Reflection provides a fairly rich API for **declaration signatures** and their associated annotated types, but it is **not an analyzer for the entire method body**. Annotations on local variables, casts, or expressions in bytecode usually require a class file/bytecode reader such as ASM to accurately analyze type annotation attributes and target locations.

Therefore, a scanner that only runs `Class.getDeclaredFields()` followed by `Field.getAnnotatedType()` **cannot prove** that no other type-use annotations exist inside any method body. A tool's scope is the metadata that the API actually provides.

For runtime annotations in class files, the separation usually corresponds to attributes for declaration annotations and **runtime-visible type annotations**; they should not be treated as a single flat list.

## 14. Common mistakes when using Reflection with annotations

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Using `Field.getAnnotations()` to find type annotations of `List<@X String>` | Field declaration differs from type argument | Use `getAnnotatedType()` then traverse `AnnotatedParameterizedType` |
| Using `Method.getAnnotations()` to find `@X` on the return type | Method declaration differs from return type | Use `getAnnotatedReturnType()` |
| Using `Parameter.getAnnotations()` to find all type-use annotations | Parameter declaration does not cover annotations on the type | Use `Parameter.getAnnotatedType()` |
| Forgetting `Retention(RUNTIME)` | Metadata is not runtime-visible | Define the right retention when runtime Reflection is needed |
| Checking only `getReturnType()` or `getGenericReturnType()` | Does not retrieve annotations at each type-use position | Use `getAnnotatedReturnType()` and related subtypes |
| Treating `TYPE` as equivalent to `TYPE_USE` | The two semantics and targets are not identical | Distinguish class declarations from type-use positions |
| Treating a type-use annotation as JVM validation | Metadata does not automatically catch errors | Integrate a checker or runtime validation if needed |
| Thinking `TYPE_USE` never appears on declarations | Certain type declarations/type parameter declarations are also valid | Understand `@Target` rules and inspect metadata with the right API |
| Observing only the outermost generic type | Misses annotations on nested type arguments | Recursively traverse `AnnotatedParameterizedType`, array/wildcard/bounds |
| Assuming Reflection understands annotations in method bodies | High-level APIs do not represent every expression/local position | Use a bytecode scanner when body coverage is required |
| Guessing storage from where `@` visually appears | Dual-applicable contexts or multi-target annotations exist | Identify the annotation's meaning and inspect the class file if needed |

## 15. Patterns for handling information by role

### 15.1. Building a field scanner

When scanning a field, separate the two streams:

```java
static void inspectField(java.lang.reflect.Field field) {
    // Metadata belonging to the field declaration itself:
    java.lang.annotation.Annotation[] fieldAnnotations =
            field.getDeclaredAnnotations();

    // Metadata on the field's type use:
    java.lang.reflect.AnnotatedType type = field.getAnnotatedType();
    java.lang.annotation.Annotation[] typeAnnotations =
            type.getAnnotations();

    System.out.println("Declaration: " + fieldAnnotations.length);
    System.out.println("Type use: " + typeAnnotations.length);
}
```

This is a complete Java method when placed inside a class, excluding traversal of generic arguments: if `field.getAnnotatedType()` is an `AnnotatedParameterizedType`, you must read the type arguments separately per section 9.

### 15.2. Reading type-use annotations in generics

If a scanner needs to know annotations on each direct argument of `List` or `Map`, read node by node:

```java
static void inspectArguments(java.lang.reflect.Field field) {
    if (field.getAnnotatedType()
            instanceof java.lang.reflect.AnnotatedParameterizedType p) {
        for (java.lang.reflect.AnnotatedType arg
                : p.getAnnotatedActualTypeArguments()) {
            System.out.println(arg.getType().getTypeName()
                    + ": " + java.util.Arrays.toString(arg.getAnnotations()));
        }
    }
}
```

This snippet handles **one level of generic arguments** and does not automatically collect deeper annotations. If you need to traverse arrays, wildcards, nested generics, owners, and type-variable bounds, use the visitor with path/cycle guards in the final lesson of the chapter. Limiting the scope this way keeps the example safe against recursive bounds and keeps the focus on declaration vs. type use.

### 15.3. When only declaration metadata is needed

If an annotation is explicitly designed with `@Target(FIELD)`, read it directly from `Field`:

```java
ColumnInfo column = field.getDeclaredAnnotation(ColumnInfo.class);
```

There is no need to traverse `AnnotatedType` just to look up a declaration annotation. The two API families should be used complementarily according to the goal.

## 16. Self-check questions

**Question 1.** What is the difference between `@Decl` on a field declaration and `@Use` on the field's type?

**Answer:** `@Decl` describes the declared member, while `@Use` describes a type-use position. With runtime Reflection, `Field.getDeclaredAnnotation` and `Field.getAnnotatedType().getAnnotation` read the two respective positions.

**Question 2.** To read `@X` from `List<@X String>`, is calling `field.getDeclaredAnnotations()` alone enough?

**Answer:** No. You need to get `field.getAnnotatedType()`, cast appropriately to `AnnotatedParameterizedType`, iterate `getAnnotatedActualTypeArguments()`, and then read the annotation on the `String` type argument.

**Question 3.** A method has `@Audit` on its declaration and `@NonNull` on its return type. Which APIs should be used?

**Answer:** `method.getDeclaredAnnotation(Audit.class)` for the declaration; `method.getAnnotatedReturnType().getAnnotation(NonNull.class)` for the return type.

**Question 4.** Does `@Target(TYPE_USE)` automatically guarantee the JVM forbids assigning `null` to a variable annotated with `@NonNull`?

**Answer:** No. Annotations are metadata; a checker/framework must enforce the rule.

**Question 5.** Are `@Target(TYPE)` and `@Target(TYPE_USE)` synonymous?

**Answer:** No. `TYPE` is primarily for type declarations, whereas `TYPE_USE` is for type-use positions and is also permitted on certain type/type-parameter declarations under Java rules.

**Question 6.** Why is `@Retention(RUNTIME)` important?

**Answer:** If an annotation is not retained until runtime, standard Reflection cannot read it while the program runs, even though the annotation appears in source code.

**Question 7.** Can `getAnnotatedSuperclass()` be used to read an annotation on `extends @X Base`?

**Answer:** Yes. This is metadata at the **type-use** position of the superclass, distinct from annotations on the subclass declaration.

**Question 8.** Can Java Reflection list every type-use annotation on casts and local variables inside a method body?

**Answer:** Not through the usual high-level signature APIs. Reading that kind of metadata completely requires an appropriate bytecode/class-file analysis tool.

**Question 9.** Can an annotation with `@Target({FIELD, TYPE_USE})` appear in connection with both declaration and type-use metadata?

**Answer:** There are contexts where an annotation applies to both forms. Therefore, you must check `@Target`, the syntactic context, and the actual class-file metadata; do not claim the two domains are completely mutually exclusive.

**Remember:** A *declaration annotation* answers "which program element is declared and how is it described?", whereas a *type-use annotation* answers "where is a type being used and what metadata does it carry?". In Reflection, APIs on `Class`/`Field`/`Method`/`Parameter` read declaration metadata; the `getAnnotated...` API family and `AnnotatedType` read metadata of **type positions**. Choose the API by position, ensure matching `@Target`/`@Retention`, and never equate metadata with automatic validation.
