# Reference Table of `Class`, `Type`, `AnnotatedType`, and Generic Types in Java Reflection

## 1. Why Do We Need a Type Classification Table?

When using Reflection to write a framework, serializer, API doc generator, schema validator, or annotation analysis tool, the question is not just "what class is this?" but also:

- Is the field declared as `List<String>` or a raw-type `List`?
- Where is type parameter `T` declared, and is it bounded by `extends Number` or which interface?
- On which bound do `List<? extends Number>` and `List<? super Integer>` differ?
- How do `T[]` and `List<String>[]` differ from `String[]`?
- Is an annotation like `@NotNull` or `@Mark` placed **on the outer type use** or placed on the type argument?

Java distinguishes three layers:

1. `Class<?>`: represents a **loaded runtime type** (class, interface, array type, primitive, `void`); generic types have usually undergone erasure.
2. `java.lang.reflect.Type` and its subtypes: represent a **declared type** with generic components, such as `List<String>`, `T`, `? extends Number`, `T[]`.
3. `java.lang.reflect.AnnotatedType` and its subtypes: represent **a type use that may carry type-use annotations**, such as `List<@Mark String>`. It allows querying both the underlying type via `getType()` and the annotations attached at that position.

**Important note:** `AnnotatedType` **does not extend `Type`**; the two interfaces serve two different layers of information. `AnnotatedType.getType()` returns the underlying `Type` for further analysis.

## 2. Relationship Diagram

~~~text
java.lang.reflect.Type
  ├── java.lang.Class<?>              [Class implements Type]
  ├── ParameterizedType               [List<String>, Map<K,V>]
  ├── TypeVariable<D>                 [T, E, K, V]
  ├── WildcardType                     [? extends Number, ? super Integer]
  └── GenericArrayType                [T[], List<String>[]]

java.lang.reflect.AnnotatedElement
  └── AnnotatedType
        ├── AnnotatedParameterizedType
        ├── AnnotatedTypeVariable
        ├── AnnotatedWildcardType
        └── AnnotatedArrayType

AnnotatedType.getType() -> Type
~~~

The diagram only summarizes **the interfaces needed for lookup**, not every implementation relationship in the JDK. `Class<?>` both implements `Type` and supports the annotation APIs of `AnnotatedElement`, yet a `Class<?>` object does not automatically become an `AnnotatedType`.

Therefore, **do not** cast `Type` to `AnnotatedType` by guesswork. You must obtain `AnnotatedType` from APIs such as `Field.getAnnotatedType()`, `Method.getAnnotatedReturnType()`, `Method.getAnnotatedParameterTypes()`, or `Class.getAnnotatedSuperclass()`.

## 3. Table for Identifying the 5 `Type` Shapes

| Declared Type Value | Common `Type` Result | Core APIs |
| --- | --- | --- |
| `String`, `int`, `String[]`, raw `List` | `Class<?>` | `getName()`, `getTypeName()`, `isArray()`, `getComponentType()`, `getTypeParameters()` |
| `List<String>`, `Map<String,Integer>`, `Parent<Long>` | `ParameterizedType` | `getRawType()`, `getActualTypeArguments()`, `getOwnerType()` |
| `T` of `class Box<T>` | `TypeVariable<?>` | `getName()`, `getBounds()`, `getGenericDeclaration()`, `getAnnotatedBounds()` |
| `?`, `? extends Number`, `? super Integer` | `WildcardType` | `getUpperBounds()`, `getLowerBounds()` |
| `T[]`, `List<String>[]` | `GenericArrayType` | `getGenericComponentType()` |

**Do not infer solely from `getTypeName()`:** the type string helps display, whereas `instanceof` on the `Type` interfaces reveals the structure for proper branching.

Example:

~~~java
Type type = field.getGenericType();
if (type instanceof ParameterizedType p) {
    Type raw = p.getRawType();
    Type[] arguments = p.getActualTypeArguments();
} else if (type instanceof TypeVariable<?> variable) {
    Type[] bounds = variable.getBounds();
} else if (type instanceof GenericArrayType array) {
    Type component = array.getGenericComponentType();
} else if (type instanceof Class<?> clazz) {
    boolean isRuntimeArray = clazz.isArray();
}
~~~

*This is an illustrative fragment: `field` is an already retrieved `java.lang.reflect.Field` and `Type` is imported from `java.lang.reflect`. `WildcardType` typically appears **inside** a type argument of a `ParameterizedType`, rather than directly as the type of the whole field.*

### 3.1. `Class<?>`: Runtime Types, Including Primitives and Arrays

`String.class`, `int.class`, `List.class`, and `String[].class` are all `Class` objects, and also implement `Type`. For an array `Class`, `getComponentType()` returns the component type at **one dimension** (e.g. `String[][].class.getComponentType() == String[].class`).

Do not confuse `List.class` with `List<String>`: syntax like `List<String>.class` **does not exist**. Due to erasure, `new ArrayList<String>().getClass()` still only reveals the runtime class `ArrayList`, without recovering `String` from the object itself.

`Class.getTypeParameters()` can describe **the type variables declared by a generic class**, but an object's `Class<?>` **does not carry per-instance type argument values**.

### 3.2. `ParameterizedType`: Parameterized Generic Type

For a field `List<String> names`, `field.getGenericType()` can be a `ParameterizedType`:

- `getRawType()` → `List.class` (in this example).
- `getActualTypeArguments()[0]` → `String.class`.
- `getOwnerType()` → can be `null` for types that do not need an owner; for types nested inside a generic owner, observe the exact owner type rather than assuming all nested types behave identically.

A type argument **does not have to be** a `Class`. It can be a `TypeVariable` (`List<T>`), a `WildcardType` (`List<? extends Number>`), another `ParameterizedType` (`List<Map<String,Integer>>`), or a `GenericArrayType`.

When reading a `ParameterizedType`, **recurse** through `getActualTypeArguments()` when you need to describe the full structure; stop at base forms (`Class`) or type variables.

### 3.3. `TypeVariable<?>`: Type Variable at the Declaration Site

Example:

~~~java
class NumericBox<T extends Number & Comparable<T>> {
    T value;
}
~~~

`NumericBox.class.getTypeParameters()[0]` is a `TypeVariable` representing `T`. It knows:

- `getName()` → `T`.
- `getGenericDeclaration()` → the declaration where `T` was introduced (class, method, or constructor).
- `getBounds()` → the declared upper bounds; here, `Number` and `Comparable<T>`.
- `getAnnotatedBounds()` → the bounds along with type-use annotations if present.

If no bounds are declared, the default upper bound is `Object`. `TypeVariable` **does not automatically know** that in some subclass `T` was substituted with `Long`. To find the type in `class LongBox extends NumericBox<Long>`, inspect `LongBox.class.getGenericSuperclass()` and read the type argument of the returned `ParameterizedType`.

**Common trap:** casting `TypeVariable.getBounds()[i]` directly to `Class` can fail, because `Comparable<T>` is represented as a `ParameterizedType`.

### 3.4. `WildcardType`: Bounds of a Wildcard

With `List<? extends Number>`, the first type argument is a `WildcardType`:

- `getUpperBounds()[0]` is typically `Number.class`.
- `getLowerBounds()` is an empty array.

With `List<? super Integer>`:

- `getLowerBounds()[0]` is `Integer.class`.
- `getUpperBounds()[0]` is `Object.class`.

With `List<?>`, the default upper bound is `Object` and there is no lower bound. **Do not** infer from `? super Integer` that the upper bound is `Integer`; that is the **lower bound**. The values of `WildcardType` describe constraints in the *generic declaration*, not the actual contents stored in a collection at runtime.

### 3.5. `GenericArrayType`: Array Whose Component Is Not a Plain `Class`

`T[]` inside a generic class and `List<String>[]` in a declared signature are forms of `GenericArrayType` because the component cannot be represented by a single reifiable `Class<?>`.

Meanwhile, `String[]` and `int[][]` are `Class<?>` with `isArray() == true`. Two APIs retrieve one level of component:

| Case | Reflection Runtime Type | Getting the Component |
| --- | --- | --- |
| `String[]` | `Class<?>` | `((Class<?>) t).getComponentType()` |
| `T[]` | `GenericArrayType` | `((GenericArrayType) t).getGenericComponentType()` |
| `List<String>[]` | `GenericArrayType` | `getGenericComponentType()` returns `ParameterizedType` |
| `List[]` (raw array) | `Class<?>` | `getComponentType()` returns `List.class` |

Java forbids `new List<String>[5]` directly because generic array creation is illegal; that **does not** prevent declaring a field or parameter of type `List<String>[]` for Reflection tools to analyze.

## 4. `AnnotatedType` Table: Seeing Where Annotations Live

| Type-use Metadata | Corresponding Interface | API for Inspecting Annotated Components |
| --- | --- | --- |
| Any type-use position | `AnnotatedType` | `getType()`, `getAnnotation(...)`, `getAnnotations()`, `getAnnotatedOwnerType()` |
| `List<@Mark String>` | `AnnotatedParameterizedType` | `getAnnotatedActualTypeArguments()` |
| `T` at a position using a generic variable | `AnnotatedTypeVariable` | `getAnnotatedBounds()` |
| `? extends @Mark Number` | `AnnotatedWildcardType` | `getAnnotatedUpperBounds()`, `getAnnotatedLowerBounds()` |
| `String @Mark []`, `T[]` | `AnnotatedArrayType` | `getAnnotatedGenericComponentType()` |

An annotation with `@Target(ElementType.TYPE_USE)` can be placed at type-use positions, such as a type argument or array dimension. For Reflection to read it at runtime, the annotation must have retention `RetentionPolicy.RUNTIME`. `CLASS` or `SOURCE` annotations will not appear through runtime Reflection the way `RUNTIME` annotations do.

Distinguish three positions:

~~~java
@Mark("field-type") List<@Mark("argument") String> names;
~~~

*The fragment above must reside inside a class, with `@Mark` defined using `TYPE_USE`; the program in Section 7 provides a complete example.*

- `Field.getAnnotatedType()` represents the **field's type** position, returning the `field-type` annotation.
- If the type is `AnnotatedParameterizedType`, `getAnnotatedActualTypeArguments()[0]` represents the **type argument** position, receiving `argument`.
- `Field.getDeclaredAnnotations()` returns **annotations declared on the field** under declaration-annotation semantics, not replacing the `AnnotatedType` tree. Annotations targeting both `FIELD` and `TYPE_USE` can appear from multiple viewpoints; choose the API matching your purpose.

A type-use annotation at one level **does not automatically propagate down** to type arguments or array components. To know which level an annotation is on, traverse via `AnnotatedType`, rather than only inspecting the string from `getTypeName()`.

## 5. Where to Retrieve Generic Metadata?

| Declaration Site | Read Generic `Type` Structure | Read Type-use Annotations |
| --- | --- | --- |
| Field | `Field.getGenericType()` | `Field.getAnnotatedType()` |
| Method parameters | `Method.getGenericParameterTypes()` | `Method.getAnnotatedParameterTypes()` |
| Method return type | `Method.getGenericReturnType()` | `Method.getAnnotatedReturnType()` |
| Exceptions in `throws` | `Method.getGenericExceptionTypes()` | `Method.getAnnotatedExceptionTypes()` |
| Constructor parameters | `Constructor.getGenericParameterTypes()` | `Constructor.getAnnotatedParameterTypes()` |
| Generic superclass | `Class.getGenericSuperclass()` | `Class.getAnnotatedSuperclass()` |
| Generic interfaces | `Class.getGenericInterfaces()` | `Class.getAnnotatedInterfaces()` |
| Type parameters on class | `Class.getTypeParameters()` | `TypeVariable.getAnnotatedBounds()` on each variable |
| Type parameters on method | `Method.getTypeParameters()` | `TypeVariable.getAnnotatedBounds()` on each variable |

**Check for null and length:** `Class.getGenericSuperclass()` can return `null` (for instance on `Object` or an interface); the interface list can be empty. `Method.getGenericExceptionTypes()` can be empty. When inspecting annotations of the generic superclass, verify a superclass exists first.

For types declared on a parameter, `java.lang.reflect.Parameter` also provides `getParameterizedType()` and `getAnnotatedType()`. If parameter names are needed, note `Parameter.isNamePresent()` and the `-parameters` compiler option; do not assume source parameter names are always retained.

## 6. Example of Reading a Generic Tree: Branching by `instanceof`

When writing a tool to output a type diagram, branch by **actual shape**:

~~~java
static String kind(Type type) {
    if (type instanceof Class<?>) return "Class";
    if (type instanceof ParameterizedType) return "ParameterizedType";
    if (type instanceof TypeVariable<?>) return "TypeVariable";
    if (type instanceof WildcardType) return "WildcardType";
    if (type instanceof GenericArrayType) return "GenericArrayType";
    return "Other Type";
}
~~~

*The fragment requires `import java.lang.reflect.*;` and must be placed inside a class.*

A general-purpose traverser can apply:

1. `Class` → retrieve `getTypeName()`; if an array, handle `getComponentType()`.
2. `ParameterizedType` → retrieve `getRawType()`, `getOwnerType()` (if present), then traverse `getActualTypeArguments()` in order.
3. `TypeVariable` → retrieve `getName()`, `getGenericDeclaration()`, and traverse `getBounds()` if displaying constraints.
4. `WildcardType` → traverse upper/lower bounds.
5. `GenericArrayType` → traverse `getGenericComponentType()` and add an array level.

When traversing recursively, recognize the possibility of **reference cycles** through type variables, such as `T extends Comparable<T>`. An algorithm descending through `TypeVariable.getBounds()` and returning to `Comparable<T>` can encounter `T` itself again. Use an active-visiting set (*active recursion path*) or track/mark visited type variables to avoid infinite recursion.

With `AnnotatedType`, you must **traverse the annotation tree in parallel**, rather than assuming from `Type` that annotations at every level are identical.

## 7. Complete Java 17+ Program: `Type` and `AnnotatedType` Together

Create the file **`GenericTypeLookupDemo.java`**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Field;
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.lang.reflect.WildcardType;
import java.util.List;

public class GenericTypeLookupDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    public @interface Mark {
        String value();
    }

    public static class Holder<T extends Number & Comparable<T>> {
        public @Mark("outer") List<@Mark("element") String> list;
        public List<? extends Number> upper;
        public List<? super Integer> lower;
        public T[] values;
        public List<String>[] genericArray;
        public String[] ordinaryArray;
        public List rawList;
    }

    public static class LongHolder extends Holder<Long> {}

    static String kind(Type t) {
        if (t instanceof Class<?>) return "Class";
        if (t instanceof ParameterizedType) return "ParameterizedType";
        if (t instanceof TypeVariable<?>) return "TypeVariable";
        if (t instanceof WildcardType) return "WildcardType";
        if (t instanceof GenericArrayType) return "GenericArrayType";
        return "Other";
    }

    static Field field(String name) throws NoSuchFieldException {
        return Holder.class.getDeclaredField(name);
    }

    public static void main(String[] args) throws Exception {
        Type list = field("list").getGenericType();
        ParameterizedType parameterized = (ParameterizedType) list;
        System.out.println("list kind: " + kind(list));
        System.out.println("list raw: "
                + parameterized.getRawType().getTypeName());
        System.out.println("list argument: "
                + parameterized.getActualTypeArguments()[0].getTypeName());

        TypeVariable<?> variable = Holder.class.getTypeParameters()[0];
        System.out.println("variable: " + variable.getName());
        System.out.println("variable bounds: " + variable.getBounds().length);
        System.out.println("first bound: "
                + variable.getBounds()[0].getTypeName());

        WildcardType upper = (WildcardType)
                ((ParameterizedType) field("upper").getGenericType())
                        .getActualTypeArguments()[0];
        WildcardType lower = (WildcardType)
                ((ParameterizedType) field("lower").getGenericType())
                        .getActualTypeArguments()[0];
        System.out.println("upper bound: "
                + upper.getUpperBounds()[0].getTypeName());
        System.out.println("lower bound: "
                + lower.getLowerBounds()[0].getTypeName());

        Type values = field("values").getGenericType();
        System.out.println("T[] kind: " + kind(values));
        System.out.println("T[] component kind: " + kind(
                ((GenericArrayType) values).getGenericComponentType()));
        System.out.println("List<String>[] kind: "
                + kind(field("genericArray").getGenericType()));
        System.out.println("String[] kind: "
                + kind(field("ordinaryArray").getGenericType()));
        System.out.println("raw List kind: "
                + kind(field("rawList").getGenericType()));

        AnnotatedType annotated = field("list").getAnnotatedType();
        Mark outer = annotated.getAnnotation(Mark.class);
        AnnotatedType argument = ((AnnotatedParameterizedType) annotated)
                .getAnnotatedActualTypeArguments()[0];
        Mark element = argument.getAnnotation(Mark.class);
        System.out.println("outer annotation: " + outer.value());
        System.out.println("argument annotation: " + element.value());

        Type base = LongHolder.class.getGenericSuperclass();
        Type supplied = ((ParameterizedType) base)
                .getActualTypeArguments()[0];
        System.out.println("subclass binds T to: "
                + supplied.getTypeName());
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac GenericTypeLookupDemo.java
java GenericTypeLookupDemo
~~~

Result:

~~~text
list kind: ParameterizedType
list raw: java.util.List
list argument: java.lang.String
variable: T
variable bounds: 2
first bound: java.lang.Number
upper bound: java.lang.Number
lower bound: java.lang.Integer
T[] kind: GenericArrayType
T[] component kind: TypeVariable
List<String>[] kind: GenericArrayType
String[] kind: Class
raw List kind: Class
outer annotation: outer
argument annotation: element
subclass binds T to: java.lang.Long
~~~

Lessons from the output:

- `field.getGenericType()` keeps `List<String>` as a `ParameterizedType`; the first type argument is `Class<String>`.
- `T` of `Holder<T extends Number & Comparable<T>>` is a `TypeVariable` with **two bounds**; one of them is `Comparable<T>`, which is itself a `ParameterizedType`.
- Wildcards retrieve bounds via `WildcardType`, not via `TypeVariable`.
- `T[]` and `List<String>[]` are `GenericArrayType`, whereas `String[]` is `Class`.
- The raw-type `List` field is `Class`, not `ParameterizedType`.
- The field's `AnnotatedType` holds `@Mark("outer")`; the annotation on the type argument is retrieved at the `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` level.
- `LongHolder.class.getGenericSuperclass()` describes `Holder<Long>`; from that, you can retrieve `Long` bound to type parameter `T` in this inheritance relationship.

This example **discovers metadata from declarations**, rather than inferring the type argument of `new ArrayList<String>()` at runtime.

## 8. Extended `AnnotatedType` API Table

Subtypes of `AnnotatedType` reflect the shape of the type at each position. A few points to verify carefully when implementing:

### 8.1. `AnnotatedParameterizedType`

For `List<@Mark String>`, call `getAnnotatedActualTypeArguments()` to retrieve each type argument along with its corresponding annotation. If a type argument is in turn `Map<@Mark String, @Mark Integer>`, the inner elements can continue to be `AnnotatedParameterizedType`. Do not inspect only the outermost annotation and drop nested annotations.

### 8.2. `AnnotatedTypeVariable`

When a type-use position is the variable `T`, the annotated type shape can be `AnnotatedTypeVariable`. The `getAnnotatedBounds()` API lets you read annotations attached to the variable's bounds. Keep in mind that a type-use annotation at the **use site** of `T` and an annotation at the **bound declaration** are two distinct positions.

### 8.3. `AnnotatedWildcardType`

With `List<? extends @Mark Number>`, the annotation on `Number` is read from `getAnnotatedUpperBounds()` of the `AnnotatedWildcardType` inside the annotated parameterized type. Similarly, `? super @Mark Integer` uses `getAnnotatedLowerBounds()`.

Distinction to note: `WildcardType.getUpperBounds()` only returns `Type[]`; if you want annotations on the bound type itself, you need the `AnnotatedWildcardType` branch.

### 8.4. `AnnotatedArrayType`

Java allows type-use annotations at **each array level**; for example, the syntax `String @Mark []` attaches an annotation to one array position. `AnnotatedArrayType.getAnnotatedGenericComponentType()` steps into the next element level, which may be another `AnnotatedArrayType` or an `AnnotatedType` representing the base component. For multidimensional arrays, do not equate an annotation on the outer `[]` with an annotation on the final element type.

### 8.5. `getAnnotatedOwnerType()`

When a type has an owner (such as an inner type inside an enclosing type), `AnnotatedType.getAnnotatedOwnerType()` (Java 9+) can reveal the annotated owner type or `null` if not applicable. Do not assume every `ParameterizedType` has an owner, or that the owner is always `Class<?>`.

## 9. Distinguishing Generic Metadata, Runtime Erasure, and Reifiability

`Type` helps read what remains stored in the **generic signature** of a field, method, constructor, or superclass. However, Java generics are still subject to **type erasure** in many runtime operations.

Example:

~~~java
List<String> strings = new java.util.ArrayList<>();
List<Integer> numbers = new java.util.ArrayList<>();

boolean sameRuntimeClass =
        strings.getClass() == numbers.getClass(); // true
~~~

*This fragment requires importing `java.util.List` and must be placed in a context allowing variable declarations.*

Both objects are instances of the same runtime class `ArrayList`; using `object.getClass()` alone cannot tell whether a source variable was declared as `List<String>` or `List<Integer>`.

Several notes:

- Generic type arguments are stored at the appropriate **declaration sites**; not all generic information survives compilation, and the compiler may omit information not emitted in a readable signature form.
- `List<String>.class` is invalid; `List.class` is valid.
- `instanceof List<String>` is invalid in regular Java because that form is non-reifiable; `instanceof List<?>` can be valid.
- `String[]` has its own runtime array class (`String[].class`), whereas `List<String>[]` is a generic array type declaration; `new List<String>[3]` cannot be created directly.
- `Type.getTypeName()` is convenient for logging, but **is not a global runtime identifier**. Two classes with the same binary name loaded by two different defining class loaders are still distinct types.

When an API can return `TypeVariable` or `ParameterizedType`, **do not blindly cast to `Class<?>`**. If an approximate runtime class is needed, define a clear rule for erasure/bounds and wildcard semantics; such simplification can lose information and is unsuitable for accurately reconstructing generic signatures.

## 10. Common Mistakes When Building a Lookup Utility

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Casting every `Field.getGenericType()` to `Class<?>` | A generic field can be `ParameterizedType`, `TypeVariable`, `GenericArrayType` | Branch with `instanceof` on `Type` |
| Using `Field.getType()` to read `List<String>` | `getType()` reflects the erased type `List.class` | Use `getGenericType()` |
| Using `getClass()` of an object to infer `List<String>` | Erasure removes type arguments from the object's runtime class | Read generic declaration/signature if available |
| Assuming `? super Integer` has upper bound `Integer` | `Integer` is the **lower bound** | Check `getLowerBounds()` and `getUpperBounds()` |
| Treating `T[]` as always being `Class` | Component `T` is non-reifiable | Handle `GenericArrayType` when Reflection returns that shape |
| Using `getDeclaredAnnotations()` to find all type-use annotations | Declaration annotations and annotations on the type-use tree live at different positions | Use `getAnnotatedType()` and traverse annotated arguments/bounds |
| Ignoring type-use annotations on type arguments | Annotations can sit inside generic nesting | Traverse `AnnotatedParameterizedType` |
| Traversing `T extends Comparable<T>` bounds infinitely | Loops back to the same type variable `T` | Track variables currently being traversed |
| Using `getSimpleName()` as a key for all types | Easy package collisions; local/anonymous types are hard to describe | Use a structured key with an appropriate namespace |
| Believing `SOURCE`/`CLASS` annotations are present at runtime | Retention is not `RUNTIME` | Only expect annotations retained for runtime Reflection reading |
| Ignoring generic signature errors | Bytecode metadata may have missing dependencies or invalid signatures | Handle `TypeNotPresentException`, `MalformedParameterizedTypeException`, `GenericSignatureFormatError` per context |

A framework should separate **type discovery**, **positional annotation reading**, **normalization/formatting**, **class name resolution**, and **error handling** into independent steps for easier testing.

## 11. Choosing an API by Practical Question

- **"I need to know what runtime class a field has?"** → `Field.getType()`.
- **"I need to know whether a field is declared `List<String>` or `List<T>`?"** → `Field.getGenericType()`, then branch on `Type`.
- **"I need annotations on the field's type and inside its type arguments?"** → `Field.getAnnotatedType()`; traverse `AnnotatedParameterizedType` or the corresponding subtype.
- **"I need the generic return type of a method?"** → `Method.getGenericReturnType()`.
- **"I need type-use annotations on the return value?"** → `Method.getAnnotatedReturnType()`.
- **"I need the bounds of generic parameter `T`?"** → `Class.getTypeParameters()` or `Method.getTypeParameters()`, then `TypeVariable.getBounds()` / `getAnnotatedBounds()`.
- **"I want to see how `T` in a superclass is bound to `Long`?"** → `Subclass.class.getGenericSuperclass()` and `ParameterizedType.getActualTypeArguments()`.
- **"I want to distinguish `? extends X` from `? super X`?"** → `WildcardType.getUpperBounds()` / `getLowerBounds()`.
- **"I need to handle `T[]`?"** → `GenericArrayType.getGenericComponentType()`.
- **"I need to inspect a reifiable array type `String[]`?"** → `Class.isArray()` / `Class.getComponentType()`.
- **"I want to preserve all nested annotations?"** → build a parallel traversal of `AnnotatedType` and `Type`, rather than relying on a single name string.

## 12. Suggestions for Testing a Type Traverser in a Project

For a generic analyzer to work reliably, include fixtures covering:

1. **Raw and parameterized:** `List`, `List<String>`, `Map<String, List<Integer>>`.
2. **Type variable:** `class Box<T>`, `<T extends Number & Comparable<T>>`.
3. **Wildcard:** `List<?>`, `List<? extends Number>`, `List<? super Integer>`.
4. **Array:** `String[]`, `T[]`, `List<String>[]`.
5. **Multi-level type-use annotations:** `@Mark List<@Mark String>`, annotations on wildcard bounds and array dimensions.
6. **Subclass substitution:** `class StringBox extends Box<String>`.
7. **Nesting and owner:** generic member types when your code supports them.
8. **Null/empty:** classes without a generic superclass, without type parameters, annotations without runtime retention.
9. **Malformed/missing types:** if the tool reads bytecode outside its control, handle reflection errors instead of crashing unexpectedly.
10. **Bound cycles:** `T extends Comparable<T>` does not cause infinite recursive traversal.

Assertions should rely on **`Type` shapes, names/bounds, and exact annotation positions** rather than incidental `toString()` strings, non-guaranteed member array ordering, or class loader identity hash codes.

## 13. Self-Check

1. Does `Class<?>` implement `Type`? **Yes.**
2. Is `AnnotatedType` a subtype of `Type`? **No; `getType()` returns the underlying `Type`.**
3. Which interface typically describes `List<String>` when calling `Field.getGenericType()`? **`ParameterizedType`.**
4. What type does `List<?>` hold in `getActualTypeArguments()[0]`? **`WildcardType`.**
5. What interface is `T` of `class Box<T>`? **`TypeVariable<?>`.**
6. Is `T[]` necessarily a `Class<?>`? **No; it is usually a `GenericArrayType`.**
7. What about `String[]`? **`Class<?>` with `isArray() == true`.**
8. In `List<@Mark String>`, which API retrieves the annotation on the type argument? **`AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[0].getAnnotation(Mark.class)`.**
9. What is the lower bound of `? super Integer`? **`Integer.class`; the default upper bound is usually `Object.class`.**
10. Does `new ArrayList<String>().getClass()` directly know `String`? **No; generic type arguments are erased from the object's runtime class.**
11. With `T extends Comparable<T>`, why can a naive traversal loop? **The bounds reference the same `TypeVariable T` again.**
12. Is `@Target(TYPE_USE)` enough for Reflection to read an annotation at runtime? **No; `RUNTIME` retention is required.**

## 14. Conclusion

Start from **the declaration source**: read `getGenericType` / `getGenericReturnType` / `getGenericSuperclass` when you need type structure, and read `getAnnotatedType` / `getAnnotatedReturnType` / `getAnnotatedSuperclass` when you need annotations by **type-use position**. Then branch properly by `Class`, `ParameterizedType`, `TypeVariable`, `WildcardType`, and `GenericArrayType`; traverse `AnnotatedType` subtypes in parallel so annotations on type arguments, wildcard bounds, or array dimensions are not lost. Reading generic signatures via Reflection reveals declarations, **without erasing the type erasure rules** of runtime objects.

### References

- [Java SE 21 — `Type`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Type.html)
- [Java SE 21 — `ParameterizedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/ParameterizedType.html)
- [Java SE 21 — `TypeVariable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/TypeVariable.html)
- [Java SE 21 — `WildcardType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/WildcardType.html)
- [Java SE 21 — `GenericArrayType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/GenericArrayType.html)
- [Java SE 21 — `AnnotatedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedType.html)
- [Java SE 21 — `AnnotatedParameterizedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html)
- [Java SE 21 — `AnnotatedTypeVariable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedTypeVariable.html)
- [Java SE 21 — `AnnotatedWildcardType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedWildcardType.html)
- [Java SE 21 — `AnnotatedArrayType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedArrayType.html)
