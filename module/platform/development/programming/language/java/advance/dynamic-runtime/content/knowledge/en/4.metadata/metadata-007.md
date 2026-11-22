# 4.7 Distinguishing Declaration Annotations from AnnotatedType on Type Uses

In Java, an annotation can describe a **declared entity** (class, field, method, parameter, type parameter...) or describe **a type use** (the element type in `List<String>`, a method return type, an array component, a wildcard, a type in `extends`...). The two kinds of information can look very similar in source code, but they reside in **different metadata locations** and must be read using **different reflection APIs**.

For example:

~~~java
@FieldLabel("customers")
List<@TypeLabel("element") String> customers;
~~~

- `@FieldLabel` is attached to the **field declaration** `customers`; read from `Field.getAnnotation(FieldLabel.class)`.
- `@TypeLabel` is attached to the **type use of `String` as a type argument** in `List<...>`; read via `Field.getAnnotatedType()`, cast appropriately to `AnnotatedParameterizedType`, and then access `getAnnotatedActualTypeArguments()[0]`.
- The `Field` object itself and the `AnnotatedType` object represent two different layers. Do not infer annotations on generic elements solely from `Field.getAnnotations()`.

The goal of this lesson is to distinguish the two layers, find the right API to read each location, understand `@Target`/`@Retention`, traverse nested type structures, and avoid concluding that `TYPE_USE` annotations automatically enforce constraints at runtime.

## 1. Two Metadata Layers: Declaration and Type Use

| Aspect | Declaration annotation | Type-use annotation |
| --- | --- | --- |
| Attached to | A declared entity: class, field, method, constructor, parameter, record component, type parameter... | An occurrence of a type: field type, return type, generic argument, bound, array level, wildcard... |
| Example | `@Deprecated class OldApi {}`; `@Column String name;` | `List<@NonNull String>`; `String @NonNull []`; `? extends @Checked Number` |
| Target in `@Target` | `TYPE`, `FIELD`, `METHOD`, `PARAMETER`, `CONSTRUCTOR`, `RECORD_COMPONENT`, `TYPE_PARAMETER`... | `TYPE_USE` (and special rules for annotations at type parameter declarations) |
| Reflection entry point | `Class`, `Field`, `Method`, `Constructor`, `Parameter`, `RecordComponent`, `TypeVariable`... via `AnnotatedElement` | `AnnotatedType` obtained from `getAnnotatedType` / `getAnnotatedReturnType` / `getAnnotatedParameterTypes` / `getAnnotatedBounds`... |
| Query depth | Annotations on **the declaration itself** being queried | Annotations on **the exact type node** in the type tree, which may require traversing into arguments, arrays, wildcards, or bounds |
| Runtime behavior | Annotations are usually just metadata, except for annotations whose semantics are defined by Java/compiler/framework | Type annotations also do not automatically check nullability or enforce types at runtime |

Structure visualization:

~~~text
Field declaration customers
│
├─ Field metadata
│  └─ @FieldLabel("customers")                 <-- declaration annotation
│
└─ Field type: List<String>
   └─ AnnotatedParameterizedType: List<...>
      └─ AnnotatedType: String
         └─ @TypeLabel("element")               <-- type-use annotation
~~~

A type use is not identical to the declaration of that type. For instance, `List<@NonNull String>` marks **String at this type argument position**, does not attach `@NonNull` to the `java.lang.String` declaration itself, and does not give every other `String` that annotation.

## 2. Distinguishing `ElementType.FIELD`, `TYPE_USE`, and `TYPE_PARAMETER`

`@Target` determines where an annotation can be used; `@Retention` determines how long it is retained.

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface FieldLabel {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeLabel {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_PARAMETER)
@interface TypeParameterLabel {
    String value();
}
~~~

These are standalone illustrative declarations; in the complete Java program below, they are declared inside the demo class so they can run in a single file.

- `@Target(FIELD)`: used on a **field declaration**; `Field.getAnnotation(...)` finds it if runtime retention matches.
- `@Target(TYPE_USE)`: used at **type locations** permitted by the language, including type arguments (`List<@TypeLabel String>`), field types, array dimensions, bounds, return types, parameter types, types in `throws`, cast types...
- `@Target(TYPE_PARAMETER)`: applies to **type parameter declarations** such as `class Box<@TypeParameterLabel T>`; the declaration annotation can be read on `TypeVariable<?>`.
- `@Retention(RUNTIME)`: allows standard reflection APIs to observe the annotation. `CLASS` (the default when `@Retention` is omitted) is retained in the class file but not reflected by core reflection; `SOURCE` is not retained in normal class files.

**Do not treat declaration and type-use as two mutually exclusive categories of annotations.** According to the Java Language Specification, an annotation type can carry both `@Target({FIELD, TYPE_USE})`. When placed in an appropriate position before a field's type, an annotation can be considered to apply to **both the declaration and the type-use**. Therefore, the visible position in source code alone is not enough: check the annotation's `@Target` and identify the exact metadata object to query.

Similarly, `TYPE_USE` also has rules for applying at class/interface declarations or type parameters in contexts defined by the JLS. When you want to emphasize the boundary in learning examples, use annotation types with only **one target** each to avoid mixing the two results.

## 3. `AnnotatedElement` and `AnnotatedType` Do Not Follow the Same Reflection "Path"

### 3.1. Querying Declaration Annotations

Reflection types such as `Field`, `Method`, `Class`, `Parameter`, and `RecordComponent` implement `AnnotatedElement`. Commonly used methods:

- `getAnnotation(MyAnnotation.class)`: returns an annotation of that type if *present* on the element, or `null` otherwise.
- `getDeclaredAnnotation(...)` and `getDeclaredAnnotations()`: only inspect annotations directly present on that element, without applying inherited semantics.
- `getAnnotations()`: annotations *present* on the element; does not automatically descend into nested type locations.
- `getAnnotationsByType(...)` / `getDeclaredAnnotationsByType(...)`: useful for `@Repeatable` annotations, able to unwrap the container to retrieve multiple annotations.
- `isAnnotationPresent(...)`: checks presence according to `AnnotatedElement` semantics.

For example, if `Field field` is the field from the opening example:

~~~java
FieldLabel label = field.getAnnotation(FieldLabel.class);
String name = label == null ? "(not found)" : label.value();
~~~

The snippet assumes a `field` variable and `import java.lang.reflect.Field;` already exist. Do not use `Field.getAnnotation(TypeLabel.class)` to look for an annotation on `String` **inside** `List<...>`; the `Field` object is not the node describing that `String` type use.

### 3.2. Querying Annotations of a Type Use

`AnnotatedType` is an interface that **also extends `AnnotatedElement`**, but the `getAnnotation` / `getAnnotations` methods on it refer to **type annotations of the type node itself**.

~~~java
AnnotatedType fieldUse = field.getAnnotatedType();
~~~

`AnnotatedType.getType()` returns the underlying `java.lang.reflect.Type`; that value can be `Class<?>`, `ParameterizedType`, `GenericArrayType`, `TypeVariable<?>`, or `WildcardType` depending on the type structure. `getType()` **does not replace** reading annotations from `AnnotatedType` itself and **does not guarantee** returning a `Class<?>`.

Four subtypes to recognize:

| `AnnotatedType` subtype | Example location | Traversal API |
| --- | --- | --- |
| `AnnotatedParameterizedType` | `List<@A String>`, `Map<@A String, @B Integer>` | `getAnnotatedActualTypeArguments()` |
| `AnnotatedArrayType` | `String @A []`, multidimensional arrays | `getAnnotatedGenericComponentType()` |
| `AnnotatedWildcardType` | `List<@A ? extends @B Number>` | `getAnnotatedUpperBounds()`, `getAnnotatedLowerBounds()` |
| `AnnotatedTypeVariable` | Using type parameter `T` at a location | `getAnnotatedBounds()` for bounds of the type variable |

Each node can have its own annotations. `getAnnotations()` on the outer `List<...>` does not automatically aggregate annotations on `String` or on a wildcard's bound. To find all type annotations, you need to **traverse the tree** according to the appropriate subtypes and inspect each node.

## 4. Looking Up the Right API by Where the Annotation Appears

| Declaration / type in code | Declaration API | Type-use API |
| --- | --- | --- |
| `@Service class MyService` | `Class.getAnnotation(...)` | For types used in inheritance relationships, use `getAnnotatedSuperclass()` / `getAnnotatedInterfaces()` |
| `@Column List<@A String> names` | `Field.getAnnotation(Column.class)` | `Field.getAnnotatedType()` → `AnnotatedParameterizedType` → annotated argument |
| `@Trace @A String read()` | `Method.getAnnotation(Trace.class)` | `Method.getAnnotatedReturnType()` |
| `void send(@Param @A String value)` | `Parameter.getAnnotation(Param.class)` or `Executable.getParameterAnnotations()` | `Parameter.getAnnotatedType()` or `Executable.getAnnotatedParameterTypes()` |
| `void run() throws @A IOException` | Annotation belongs to the method declaration if there is an annotation targeting `METHOD` | `Executable.getAnnotatedExceptionTypes()` |
| Instance receiver (e.g., annotated `this`) | Not a declaration annotation on the method body | `Executable.getAnnotatedReceiverType()` |
| `class Box<@TTag T extends @A Number>` | `TypeVariable.getAnnotation(TTag.class)` | `TypeVariable.getAnnotatedBounds()` |
| Record `record Row(@Col @A String key) {}` | `RecordComponent.getAnnotation(Col.class)` | `RecordComponent.getAnnotatedType()` |
| `class Impl extends @A Base implements @B Runnable` | `Class.getAnnotations()` does not interpret these marks as annotations of the `Impl` declaration | `Class.getAnnotatedSuperclass()` and `getAnnotatedInterfaces()` |

**Limitation of the table:** these snippets are syntax examples, not complete programs. Annotations `@A`, `@B`, `@Col`... must be declared with valid `@Target` and `@Retention` in real code. Java does not have a single general method on `Class` to retrieve all type-use annotations of all members. Always start from the member containing the type use to be analyzed.

`getAnnotatedReceiverType()` returns `null` for static methods and for executables that cannot have a receiver parameter; for instance methods, it may return an `AnnotatedType` **with no annotations** even when no annotated receiver is explicitly declared.

## 5. Complete Java 17+ Example: Reading Both Metadata Layers

Create file `AnnotationLocationsDemo.java`:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedArrayType;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.AnnotatedWildcardType;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.lang.reflect.TypeVariable;
import java.util.List;

public class AnnotationLocationsDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.FIELD)
    @interface ColumnLabel { String value(); }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    @interface ArgumentLabel { String value(); }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_PARAMETER)
    @interface TypeParameterLabel { String value(); }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface TypeRole { String value(); }

    static class Catalog<@TypeParameterLabel("T") T extends @TypeRole("bound") Number> {
        @ColumnLabel("names")
        List<@TypeRole("element") String> names;

        @ColumnLabel("codes")
        String @TypeRole("array") [] codes;

        List<@TypeRole("wildcard") ? extends @TypeRole("upper") Number> numbers;

        public @TypeRole("return") List<@TypeRole("return-element") String> find(
                @ArgumentLabel("query") @TypeRole("input") String query) {
            return List.of(query);
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Field names = Catalog.class.getDeclaredField("names");
        System.out.println("declaration: " + names.getAnnotation(ColumnLabel.class).value());
        System.out.println("field raw class: " + names.getType().getTypeName());
        System.out.println("field generic type: " + names.getGenericType().getTypeName());
        AnnotatedParameterizedType namesUse = (AnnotatedParameterizedType) names.getAnnotatedType();
        AnnotatedType itemType = namesUse.getAnnotatedActualTypeArguments()[0];
        System.out.println("element type-use: " + itemType.getAnnotation(TypeRole.class).value());
        System.out.println("element type: " + itemType.getType().getTypeName());
        System.out.println("field has TypeRole declaration: " + (names.getAnnotation(TypeRole.class) != null));

        Field codes = Catalog.class.getDeclaredField("codes");
        AnnotatedArrayType arrayType = (AnnotatedArrayType) codes.getAnnotatedType();
        System.out.println("array type-use: " + arrayType.getAnnotation(TypeRole.class).value());
        System.out.println("component type: " + arrayType.getAnnotatedGenericComponentType().getType().getTypeName());

        Field numbers = Catalog.class.getDeclaredField("numbers");
        AnnotatedParameterizedType numbersUse = (AnnotatedParameterizedType) numbers.getAnnotatedType();
        AnnotatedWildcardType wildcard = (AnnotatedWildcardType) numbersUse.getAnnotatedActualTypeArguments()[0];
        System.out.println("wildcard type-use: " + wildcard.getAnnotation(TypeRole.class).value());
        System.out.println("upper bound type-use: " + wildcard.getAnnotatedUpperBounds()[0].getAnnotation(TypeRole.class).value());

        Method find = Catalog.class.getDeclaredMethod("find", String.class);
        AnnotatedParameterizedType returnUse = (AnnotatedParameterizedType) find.getAnnotatedReturnType();
        System.out.println("return type-use: " + returnUse.getAnnotation(TypeRole.class).value());
        System.out.println("return element type-use: " + returnUse.getAnnotatedActualTypeArguments()[0].getAnnotation(TypeRole.class).value());
        Parameter query = find.getParameters()[0];
        System.out.println("parameter declaration: " + query.getAnnotation(ArgumentLabel.class).value());
        System.out.println("parameter type-use: " + query.getAnnotatedType().getAnnotation(TypeRole.class).value());

        TypeVariable<?> typeParameter = Catalog.class.getTypeParameters()[0];
        System.out.println("type-parameter declaration: " + typeParameter.getAnnotation(TypeParameterLabel.class).value());
        System.out.println("type-parameter bound use: " + typeParameter.getAnnotatedBounds()[0].getAnnotation(TypeRole.class).value());
    }
}
~~~

Compile and run from the directory containing the file; requires JDK 17 or later:

~~~bash
javac --release 17 AnnotationLocationsDemo.java
java AnnotationLocationsDemo
~~~

Exact `stdout`:

~~~text
declaration: names
field raw class: java.util.List
field generic type: java.util.List<java.lang.String>
element type-use: element
element type: java.lang.String
field has TypeRole declaration: false
array type-use: array
component type: java.lang.String
wildcard type-use: wildcard
upper bound type-use: upper
return type-use: return
return element type-use: return-element
parameter declaration: query
parameter type-use: input
type-parameter declaration: T
type-parameter bound use: bound
~~~

The program uses annotation types with different targets, so you can clearly see each layer:

1. `names.getAnnotation(ColumnLabel.class)` reads the annotation on the **field declaration** and returns `"names"`.
2. `names.getType()` returns raw `java.util.List` due to erasure; `names.getGenericType()` preserves `List<String>` in the generic signature but does not reflect `@TypeRole("element")`.
3. `names.getAnnotatedType()` is an `AnnotatedParameterizedType`. The first type argument is the `String` node with annotation `@TypeRole("element")`. `names.getAnnotation(TypeRole.class)` returns `null` because that annotation is not on the field declaration.
4. `String @TypeRole("array") [] codes` attaches the annotation to the **array level**. `AnnotatedArrayType` holds `@TypeRole("array")`; `getAnnotatedGenericComponentType()` steps into `String`.
5. For the wildcard, `@TypeRole("wildcard")` is attached to the `?` node; `@TypeRole("upper")` is attached to the `Number` bound. The two positions are two different nodes.
6. `find.getAnnotatedReturnType()` holds the annotation on the returned `List<...>`; `getAnnotatedActualTypeArguments()[0]` holds the separate annotation on `String`.
7. `Parameter.getAnnotation(ArgumentLabel.class)` reads the annotation on the **parameter declaration**, whereas `Parameter.getAnnotatedType().getAnnotation(TypeRole.class)` reads the annotation on the **parameter's `String` type**.
8. `TypeVariable.getAnnotation(TypeParameterLabel.class)` reads the annotation on the declaration of `T`; `getAnnotatedBounds()[0]` reads the annotation on the `Number` type used as the bound.

Compiling with `--release 17` ensures the program's syntax and APIs conform to Java SE 17. The `stdout` output above was verified with a real JDK.

## 6. Decomposing Multi-Level Generic Types: Do Not Stop at the Outer Node

Given the declaration:

~~~java
Map<@Role("key") String, List<@Role("number") Integer>> index;
~~~

This is illustrative syntax, with `@Role` declared as `@Target(TYPE_USE)`. The tree to read:

~~~text
AnnotatedParameterizedType: Map<...>
├─ AnnotatedType: String [@Role("key")]
└─ AnnotatedParameterizedType: List<...>
   └─ AnnotatedType: Integer [@Role("number")]
~~~

Sequence:

1. Obtain `Field.getAnnotatedType()` for `index`.
2. Check `instanceof AnnotatedParameterizedType` and then call `getAnnotatedActualTypeArguments()`.
3. Argument 0 is `String`: read the annotation on **this node**.
4. Argument 1 is `List<Integer>`: check `AnnotatedParameterizedType` again and descend into argument 0 to read the annotation on `Integer`.

A type-traversal utility should handle the `AnnotatedParameterizedType`, `AnnotatedArrayType`, `AnnotatedWildcardType`, and `AnnotatedTypeVariable` branches, while also maintaining a "visited" set or recursion limit if traversing cyclic bounds such as `T extends Comparable<T>`. If only a specific path is needed, direct querying is usually clearer than a general-purpose utility.

The minimal type inspector example below only inspects **generic arguments and array components**, and is not a full visitor for every `AnnotatedType` form:

~~~java
static void inspect(AnnotatedType type) {
    System.out.println(type.getType().getTypeName());
    for (var annotation : type.getAnnotations()) {
        System.out.println("  annotation: " + annotation.annotationType().getSimpleName());
    }

    if (type instanceof AnnotatedParameterizedType parameterized) {
        for (AnnotatedType argument : parameterized.getAnnotatedActualTypeArguments()) {
            inspect(argument);
        }
    } else if (type instanceof AnnotatedArrayType array) {
        inspect(array.getAnnotatedGenericComponentType());
    }
}
~~~

This is an **illustrative method** placed inside a class with `import java.lang.reflect.*;`. It does not descend into wildcard bounds, type-variable bounds, or owner types; if a task requires those locations, the corresponding branches must be added and guarded against cyclic recursion. More importantly, `AnnotatedType.getAnnotations()` only returns annotations of the **current node**, not automatically the entire tree.

## 7. Arrays: Annotation Position Determines Which Level Is Marked

Arrays in Java can have annotations on the **element type** or on **each array dimension**. For example:

~~~java
@TypeLabel("element") String @TypeLabel("outer") [] @TypeLabel("inner") [] values;
~~~

This line is an illustrative declaration for an annotation with `@Target(TYPE_USE)` and `@Retention(RUNTIME)`. How to interpret the nodes:

~~~text
AnnotatedArrayType: String[][]     [@TypeLabel("outer")]
└─ AnnotatedArrayType: String[]     [@TypeLabel("inner")]
   └─ AnnotatedType: String         [@TypeLabel("element")]
~~~

`@TypeLabel("outer")` on the first `[]` pair corresponds to the **outer array type**, `@TypeLabel("inner")` on the second `[]` pair corresponds to the **component array type**, and the annotation placed before `String` is attached to the **element type**. When using reflection, call `getAnnotatedGenericComponentType()` repeatedly to step down each level.

**Pitfall:** `Field.getType()` will report `String[][].class` but does not tell you which dimension an annotation is on; `Field.getGenericType()` does not provide the `AnnotatedType` tree either. An annotation attached to `String` does not mean it is attached to `String[]`, and vice versa.

## 8. Wildcards, Type Parameters, Bounds, and Inheritance Type Uses

### Wildcards Differ from Upper/Lower Bounds

In `List<@A ? extends @B Number>`, `@A` is attached to `?`, and `@B` is attached to the `Number` type. In reflection:

~~~java
AnnotatedWildcardType wildcard = (AnnotatedWildcardType) annotatedArgument;
AnnotatedType[] upper = wildcard.getAnnotatedUpperBounds();
AnnotatedType[] lower = wildcard.getAnnotatedLowerBounds();
~~~

The snippet assumes `annotatedArgument` has already been retrieved from a parameterized type's type argument. When there is `? super @A Integer`, the annotation on `Integer` is found via `getAnnotatedLowerBounds()`; when `? extends @B Number`, it is found via `getAnnotatedUpperBounds()`. Check the length of the bounds array and each element's type before accessing.

### The Declaration of `T` Differs from the Type Used in Its Bound

~~~java
class Container<@TypeParameterLabel("T") T extends @TypeLabel("bound") Number> {}
~~~

`TypeVariable<?> variable = Container.class.getTypeParameters()[0]` (assuming `Container` and the annotation types are declared) is metadata for the type parameter `T` itself; `variable.getAnnotation(TypeParameterLabel.class)` reads the annotation on **the declaration of `T`**. Conversely, `variable.getAnnotatedBounds()[0]` is the node for the `Number` type in the `extends` clause. The two locations can carry two different annotations.

If a field later has type `@TypeLabel("use-T") T value;`, **the use of `T` at the field** belongs to an `AnnotatedTypeVariable`; the `"use-T"` annotation resides on the type-use node at the field. This is an independent location from the annotation on the declaration of `T` and from the annotation on the `Number` bound.

### `extends` and `implements` Are Type Uses

~~~java
class Worker extends @TypeLabel("base") Base
        implements @TypeLabel("contract") Runnable {}
~~~

This is a syntax illustration assuming `Base` is a class and `@TypeLabel` has `TYPE_USE`. `Worker.class.getAnnotatedSuperclass()` reads the `"base"` annotation on **the `Base` type being used**; `Worker.class.getAnnotatedInterfaces()[0]` reads `"contract"` on **the `Runnable` type being used**. Calling `Base.class.getAnnotations()` looks for annotations of **the `Base` declaration**, not annotations on the `extends Base` clause in `Worker`.

## 9. Type-Use Annotations Do Not Enforce Runtime Checks Automatically

A common example is `@NonNull`:

~~~java
List<@NonNull String> names;
~~~

Having only `@NonNull` metadata at the `String` type use **does not make the JVM reject `null` by default** when added to the list. Checking nullability, valid data, or ownership typically requires one of the following:

- A static checker/annotation processor that understands the annotation's semantics and performs checks at compile time.
- A framework that reads metadata at runtime and **actively** checks it, such as reading a field's type argument and applying validation.
- Explicit checks in code, such as `Objects.requireNonNull(...)`, appropriate Bean Validation, or custom application contracts.

Annotations do not change the actual `Class` of `String`, do not generate a new JVM subtype, and do not disable type erasure. The generic signature may remain in the class file and be reflected via `getGenericType()`, whereas annotations on generic nodes are accessed via `AnnotatedType`.

## 10. Notes on Repeatable Annotations, Inheritance, and Retention

### Retention

| Retention | Present in class file? | Readable by standard core reflection at runtime? |
| --- | --- | --- |
| `SOURCE` | No (normally discarded at compile time) | No |
| `CLASS` | Yes | No |
| `RUNTIME` | Yes | Yes, at locations exposed by the reflection API |

If you declare an annotation and **forget `@Retention(RUNTIME)`**, `Field.getAnnotation(...)` or `AnnotatedType.getAnnotation(...)` can return `null` even though the annotation is in the source code. This is a very common mistake when designing a reflection-based library.

### `@Inherited` and `@Repeatable`

`@Inherited` only affects certain annotation queries **on class declarations** along the superclass chain. It does not make field/method annotations automatically inherited, and it does not propagate annotations on `AnnotatedType` to a subclass's types. If you want to check annotations declared directly on a class, use `getDeclaredAnnotation(...)`; if you want *present* semantics with inheritance per contract, use `getAnnotation(...)` or `getAnnotations()` with an annotation marked `@Inherited`.

For `@Repeatable` annotations, `getAnnotationsByType(...)` and `getDeclaredAnnotationsByType(...)` are useful on both elements and `AnnotatedType`, depending on whether you are reading a declaration or a type use; these two methods have logic to unwrap the container annotation, whereas `getAnnotation(...)` only returns a single annotation under normal semantics.

### One Annotation Type Can Appear at Both Layers

Suppose:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.FIELD, ElementType.TYPE_USE})
@interface Tagged {}
~~~

In a context like `@Tagged String title;`, according to the JLS annotation applicability rules, the annotation can apply **simultaneously** to the `title` declaration and the `String` type use. You need to check both `Field.getAnnotation(Tagged.class)` and `Field.getAnnotatedType().getAnnotation(Tagged.class)` if your contract wants both kinds of metadata. Do not draw conclusions just by looking at syntax position without `@Target` information.

## 11. Limitations of Java Reflection: Some Type Uses Have No Query Path via `AnnotatedType`

`TYPE_USE` also allows placing annotations in many expressions and local contexts, for example:

~~~java
Object value = "demo";
String text = (@TypeLabel("cast") String) value;
Object object = new @TypeLabel("creation") String("demo");
~~~

These are illustrative statements; the annotation is declared with `TYPE_USE`. Annotations on types in a **cast** or **new expression** are part of the type annotation metadata in the class file when retention is appropriate, but there is **no simple core reflection API** like `Field.getAnnotatedType()` to retrieve each cast/new/local-variable-use inside a method body. Tools that need to read such code-level locations typically analyze source/AST, `javax.lang.model` during annotation processing, or class files/bytecode with appropriate tools.

Do not write code that scans `Class.getDeclaredFields()` and assume you have all type annotations inside every method body. Reflection primarily provides type-use locations attached to **declarations and signatures** exposed by the API.

## 12. Diagnosing Common Errors

| Symptom | Common cause | Fix |
| --- | --- | --- |
| `field.getAnnotation(TypeLabel.class) == null` even though the annotation is visible in `List<@TypeLabel String>` | Querying annotations on the declaration while the annotation is on the type argument | `field.getAnnotatedType()` → `AnnotatedParameterizedType` → type argument |
| `getAnnotatedType().getAnnotation(TypeLabel.class) == null` in `List<@TypeLabel String>` | Only querying the outer `List` node; the annotation is on `String` | Descend into `getAnnotatedActualTypeArguments()[0]` |
| Annotation exists in source but reflection returns `null` | Default `@Retention` is `CLASS`, or `@Target`/location mismatch | Check the annotation definition, recompile, and read the right location |
| `ClassCastException` when casting `AnnotatedType` | The type being inspected is not the assumed parameterized/array/wildcard/type variable form | Check `instanceof` before downcasting |
| Annotation on `Number` in a wildcard is not found | Reading the wildcard node instead of the bound | `AnnotatedWildcardType.getAnnotatedUpperBounds()` / `getAnnotatedLowerBounds()` |
| Missing annotation on an array dimension | Only inspecting the base element or outer array, skipping intermediate array types | Traverse `AnnotatedArrayType.getAnnotatedGenericComponentType()` repeatedly |
| Annotation on `T` or `T extends Number` is not found | Confusing the type parameter declaration with its bound | `TypeVariable.getAnnotation(...)` for `T`; `getAnnotatedBounds()` for the bound |
| Interface has an annotation but it is not found via `getAnnotation` on the implementing class | No automatic inheritance from interfaces, or confusing declaration with type-use | Query `getAnnotatedInterfaces()` for the `implements` clause, or locate the right declaration |
| Annotation on cast/new cannot be found via `Field` | Core reflection does not expose type-uses at arbitrary positions in a method body | Analyze source/AST or class file/bytecode |

When writing library code that processes annotations, distinguish variable names such as `fieldDeclarationAnnotations`, `fieldTypeUse`, and `elementTypeUse`, and pass the context of the type node into the processing logic. Location-explicit naming helps prevent accidentally applying a field's policy to a type argument or vice versa.

## 13. Quick API Selection Workflow

1. **Ask whether the annotation is attached to an entity or to a type use?** For example, "does the field have `@Column`?" is declaration; "is the field's element type `@NonNull String`?" is type-use.
2. **Check the annotation type:** which `@Target` values are valid, does it have `@Retention(RUNTIME)`, and does it have `@Repeatable` or `@Inherited`?
3. **Choose the entry point:** `Field` / `Method` / `Class` / `Parameter` to read declarations; `getAnnotatedType()` / `getAnnotatedReturnType()` / `getAnnotatedParameterTypes()` / `getAnnotatedBounds()` to read type uses.
4. **Navigate to the exact node in the type tree:** parameterized argument, wildcard bound, array component, type-variable bound, or annotated owner type when present.
5. **Handle absent cases:** `getAnnotation(...)` returns `null`, annotation arrays can be empty, and `getAnnotatedSuperclass()` can return `null` for types without an applicable superclass.
6. **Apply application-specific semantics:** annotations are descriptive, not automatic validation; if constraint enforcement is needed, explicitly design the corresponding compiler checker/framework/logic.

## 14. Self-Check

**Question 1:** In `@Column List<@NonNull String> names;`, does calling `field.getAnnotation(NonNull.class)` find `@NonNull` on `String`?

Answer: **No**. The annotation is on the type argument; obtain `field.getAnnotatedType()`, cast it to `AnnotatedParameterizedType`, and read the first annotated argument.

**Question 2:** How do `getGenericType()` and `getAnnotatedType()` differ?

Answer: `getGenericType()` returns a `Type` describing the generic signature, whereas `getAnnotatedType()` returns an `AnnotatedType` describing the type use and annotations at the nodes of that type, alongside the underlying `Type`.

**Question 3:** How does `String @A [] values` differ from `@A String[] values`?

Answer: With `@A` being `TYPE_USE`, the first form attaches the annotation to the **array type**, while the second attaches the annotation to the **String element type**. You need to traverse through `AnnotatedArrayType` to distinguish them.

**Question 4:** In `class C<@P T extends @B Number>`, which APIs are used for `@P` and `@B`?

Answer: `TypeVariable.getAnnotation(P.class)` for the declaration annotation of `T`; `TypeVariable.getAnnotatedBounds()[0].getAnnotation(B.class)` for the type-use on the `Number` bound.

**Question 5:** If an annotation has both `@Target({FIELD, TYPE_USE})` and is placed before a field type, does it necessarily belong to only one side?

Answer: **No**. According to the JLS, when an annotation is valid in both contexts, it can apply to both the declaration and the nearest type use. You must determine the target, retention, and appropriate API.

**Question 6:** If `@NonNull String` has `RUNTIME` retention, does the JVM automatically throw an exception when the value is `null`?

Answer: **No**. A compiler checker, framework, or custom checking code according to your contract is required.

**Question 7:** Can an annotation `@A` attached to a type appearing in a cast inside a method be read using only `Method.getAnnotatedReturnType()`?

Answer: **No**. The return type is a different location; core reflection does not provide a direct path to individual casts inside a method body.

## Authoritative References

- [JLS Java SE 21 — `9.6.4.1 @Target` and `9.7.4` Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html)
- [Java SE 21 — `AnnotatedElement`, distinguishing declaration and type annotations](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedElement.html)
- [Java SE 21 — `AnnotatedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedType.html)
- [Java SE 21 — `AnnotatedParameterizedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html)
- [Java SE 21 — `AnnotatedArrayType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedArrayType.html)
- [Java SE 21 — `AnnotatedWildcardType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedWildcardType.html)
- [Java SE 21 — `TypeVariable` and `AnnotatedTypeVariable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/TypeVariable.html)
- [Java SE 21 — `RecordComponent.getAnnotatedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/RecordComponent.html)
