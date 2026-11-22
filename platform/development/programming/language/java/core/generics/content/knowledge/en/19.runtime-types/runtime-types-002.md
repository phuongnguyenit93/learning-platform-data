# Classifying ordinary types, raw types, unbounded wildcards, and array types at runtime

## 1. Why do we need to classify types when working with Java Generics?

Java Generics enforces type relationships very strictly at **compile time**, but much of the information about type parameters is removed (*type erasure*) when source code is compiled into bytecode. Therefore, the question "Does Java know this type at runtime?" must be answered accurately **for each category of type**.

For example:

```java
List<String> names = List.of("Lan", "Minh");
Object object = names;
```

In source code, `names` has type `List<String>`. At runtime, the `List` object still has its concrete class, yet there is no separate class for `List<String>` alongside `List<Integer>` simply because they use different type arguments.

By contrast, a `String[]` array retains a runtime component of `String`, so the JVM can prevent writing an `Integer` into that array through an `Object[]` alias.

The central concept of this lesson is **reifiable type** — a type whose runtime representation remains sufficient for operations that require a type determinable at runtime, according to the rules of the Java Language Specification (JLS). This lesson focuses on the four groups in the title:

1. **Ordinary types**: primitive types and non-generic classes/interfaces such as `int`, `String`, `Runnable`.
2. **Raw types**: a generic name used without type arguments, such as raw `List` or `Map`.
3. **Parameterized types with only unbounded wildcards**: for example, `List<?>`, `Map<?, ?>`.
4. **Array types**: `String[]`, `int[]`, `List<?>[]`, `List<String>[]`, `T[]`, and the impact of the component type.

After this lesson, you will know how to classify types as **reifiable** or **non-reifiable**, understand the differences among `instanceof`, `Class`, Reflection `Type`, and array element checks, and be able to explain `generic array creation` errors and unchecked casts.

## 2. Three levels of type information must be distinguished

A Java variable can involve three distinct layers of information:

| Level | Example | What it expresses |
| --- | --- | --- |
| **Source type (compile time)** | `List<String>` | The compiler checks `add`, `get`, assignments, and generic relationships based on `String`. |
| **Runtime type/class** | Object belonging to an implementation of `List` | The JVM determines the actual class of the object, used for dispatch, `instanceof`, reflection, and casts; the `String` type argument does not automatically become a class specialization. |
| **Generic declaration metadata** | Field declared `List<String>` or `T[]` | The class file may retain a Signature attribute; Reflection reads this *declaration* back via `getGenericType()`, not per-instance specialization. |

These three levels do not contradict each other:

```java
List<String> a = new ArrayList<>();
List<Integer> b = new ArrayList<>();
```

`a` and `b` have different types in source code, yet `a.getClass() == b.getClass()` is `true`: both objects are created from the ordinary `ArrayList` class. Generic information of the **declaration** may still be present on a field/method/class via metadata, yet that does not prove the runtime knows what element type each individual `ArrayList` holds.

### 2.1. Reifiable does not mean "does not use generics"

`List<?>` is a generic type with a wildcard, yet it is **reifiable**. Conversely, `List<String>` is a parameterized type with a concrete type argument, yet it is **non-reifiable**.

Reifiability is about **what kind of runtime information Java allows to be checked**, not "whether this code has generics," "what elements the collection currently contains," or "whether any object can be added."

### 2.2. Reifiable is also not synonymous with checking all internal data

An expression `object instanceof List<?>` can verify that the object is a runtime `List`. It **does not** iterate over every element to verify they share the same type, and it does not guarantee that the collection contains no `null`.

Even though `List<?>` is reifiable, Java still does not know whether `?` stands for `String`, `Integer`, or another reference type in a specific instance. Therefore, reifiability is a condition on **the type being checked**; ensuring input data integrity still requires contracts and element-by-element checks.

## 3. List of reifiable types in Java

The basic reifiable groups in the JLS include:

- **Non-generic** class or interface types, e.g. `String`, `Number`, `Runnable`.
- Parameterized types where **every** type argument is the unbounded wildcard `?`, e.g. `List<?>`, `Map<?, ?>`.
- **Raw types** of generic classes/interfaces, e.g. `List`, `Map`.
- **Primitive types**, e.g. `int`, `boolean`, `double`.
- **Array types** whose component type is reifiable, e.g. `String[]`, `int[]`, `List<?>[]`, `List[][]`.
- Nested type forms that satisfy the reifiability condition for each part of the type name under JLS rules.

In addition, `Object`, `String[]`, or `List<?>` can be reifiable; the type variable `T`, `List<String>`, and `List<? extends Number>` do **not** belong to this group.

### 3.1. Detailed classification table

| Type written in Java | Reifiable? | Brief explanation |
| --- | --- | --- |
| `int` | Yes | Primitive with a definite runtime type. |
| `boolean`, `double` | Yes | Primitive. |
| `String`, `Integer`, `Object` | Yes | Ordinary class, no type parameters on this type itself. |
| `Runnable` | Yes | Non-generic interface. |
| `String[]`, `int[]` | Yes | Reifiable component; the JVM knows the component type. |
| `List` | Yes | Raw type of `List<E>`; valid in terms of runtime determinability, though not as safe as parameterized `List<T>`. |
| `Map` | Yes | Raw type. |
| `List<?>` | Yes | Every type argument is an **unbounded** wildcard. |
| `Map<?, ?>` | Yes | Both type arguments are `?`. |
| `List<?>[]`, `Map<?, ?>[]` | Yes | Component is a reifiable type. |
| `List[]` | Yes | Array of raw type `List`; may produce a `rawtypes` warning. |
| `List<String>` | No | The `String` argument is erased and does not create a separate runtime specialization. |
| `Map<String, Integer>` | No | Concrete type arguments are non-reifiable. |
| `List<? extends Number>` | No | **Bounded** wildcard, not in the "all arguments are unbounded wildcards" group. |
| `List<? super Integer>` | No | Lower-bounded wildcard. |
| `T` in `<T>` | No | A type variable is not a reifiable type. |
| `T[]` | No | Component type `T` is non-reifiable, even though its erasure may be `Object`. |
| `List<String>[]` | No | Component `List<String>` is non-reifiable. |
| `List<?>[][]` | Yes | Every array dimension has a reifiable component. |
| `List<String>[][]` | No | Final component `List<String>` is non-reifiable. |

With `T extends Number`, `T` and `T[]` are **still non-reifiable**; the erasure of `T` may become `Number` and the erasure of `T[]` may become `Number[]`, yet erasure does not turn a type variable into a type you can use directly with `new T[5]`.

### 3.2. A bounded wildcard changes the conclusion

Compare:

```java
List<?> a;                      // Reifiable
List<? extends Number> b;       // Non-reifiable
List<? super Integer> c;        // Non-reifiable
Map<?, ?> d;                    // Reifiable
Map<String, ?> e;               // Non-reifiable
```

`? extends Number` means "an unknown subtype of `Number`"; this is a compile-time constraint whose meaning differs from unbounded `?`. The fact that the JVM can see `List` or `Map` after erasure is not enough to preserve full bounded type-argument information on each object.

## 4. Group A — Ordinary classes, interfaces, and primitives

Types such as:

```java
String text = "Java";
int count = 10;
Runnable action = () -> {};
```

have corresponding runtime representations. For example:

```java
Object x = "Java";

System.out.println(x instanceof String);  // true
System.out.println(String.class.getName()); // java.lang.String
```

A `String` is indeed an instance of class `String`, and the `instanceof` operator checks the matching runtime type.

For primitives, you cannot write `x instanceof int`; `instanceof` works with **reference types** in valid forms of the operator, and primitives are not objects to be checked that way. However, `int.class` is a valid class literal, returning a `Class` object representing the primitive `int`.

```java
System.out.println(int.class.isPrimitive()); // true
```

Distinguish `int` from the wrapper `Integer`: `Integer` is a reference class that can be checked via `instanceof Integer`, whereas `int` is a primitive. Boxing/unboxing can convert between the two forms in contexts permitted by Java, yet they are not a single type.

### 4.1. Ordinary types can still implement generic APIs

`String` has no type parameter of its own, yet it implements interfaces such as `Comparable<String>`. That does not make `String` a non-reifiable generic class.

A **non-generic** class/interface can use generics in methods or implement a generic interface. Classifying reifiability requires looking at **the type being asked about**, rather than inferring that "anything touching Generics makes the entire class non-reifiable."

## 5. Group B — Raw types

A raw type occurs when all type arguments of a generic declaration are omitted:

```java
List rawList;
Map rawMap;
```

Both raw `List` and raw `Map` are reifiable. This explains why runtime-related operations can use the raw form:

```java
Object value = List.of("Java");

boolean isList = value instanceof List;    // Valid
Class<?> type = List.class;                 // Valid
```

However, **reifiable does not prove type safety** when using generic APIs. Raw types can trigger `[rawtypes]` warnings on declaration and `[unchecked]` warnings when invoking members with arguments the compiler cannot verify.

```java
List raw = new ArrayList();
raw.add("Java");
raw.add(99); // Unchecked call may occur
```

When you need to accept an arbitrary list only to read data, `List<?>` is usually better:

```java
static int count(List<?> values) {
    return values.size();
}
```

`List<?>` preserves generic constraints, avoiding the arbitrary write access that raw types inadvertently allow.

### 5.1. A raw type is not `List<Object>`

`List<Object>` is a parameterized type with concrete argument `Object`, which is **non-reifiable**. `List<?>` and raw `List` are reifiable, yet they have different compile-time rules.

```java
List<String> names = List.of("Lan");
List<?> unknown = names;             // Valid
// List<Object> objects = names;      // Invalid: generics are invariant
```

When designing an API, choose `List<?>` when you want to read elements of an unknown type; choose `List<Object>` when you genuinely need a list capable of holding `Object` with corresponding write access; avoid raw `List` in new code except for justified legacy compatibility.

### 5.2. Runtime class does not distinguish raw and parameterized instances

```java
List<String> texts = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();

boolean sameClass = texts.getClass() == numbers.getClass(); // true
```

An `ArrayList` does not carry separate runtime classes for `String` and `Integer`; generic type arguments are not specialized into two different implementation classes.

`List<?>` can be checked at runtime as a `List`, yet that does not determine the source-level type argument. Reflection on a **declaration** `List<?> field` can record the `?`, which differs from an object storing "I am List<?>" on itself.

## 6. Group C — Unbounded wildcard `?`

`List<?>` is a parameterized type with an unbounded wildcard argument. It is one of the most important examples because it is both reifiable and preserves many generic checking rules.

```java
Object value = List.of("A", 17);

if (value instanceof List<?> items) {
    System.out.println(items.size());
}
```

`instanceof List<?>` is valid; the pattern variable `items` is treated as a `List<?>`. You can:

- Call `size`, `isEmpty`, and iterate over elements as `Object`.
- Read an element: `Object element = items.get(0)`.
- You cannot call `items.add("text")` or `items.add(17)`, because the compiler does not know the concrete captured element type of the list.
- You can add `null` under type rules in a mutable list; however, the actual list might not support adding or might reject null. For example, `List.of(...)` is unmodifiable.

### 6.1. Unbounded wildcards and `instanceof`

How to check from an `Object`:

```java
Object incoming = List.of("a", "b");

if (incoming instanceof List<?> list) {
    for (Object item : list) {
        System.out.println(item);
    }
}
```

You cannot use `incoming instanceof List<String>` in this context to verify that all elements are `String`. With an `Object` variable and Java 17, the compiler rejects that parameterized type check because the runtime cannot verify the `String` argument.

```java
// For a variable of type Object: compile-time error on Java 17.
// if (incoming instanceof List<String>) { ... }
```

Syntax details for `instanceof` with certain parameterized types have been adjusted across Java language versions, especially when a type relationship is already provable at compile time. This **does not make the JVM start checking the type argument of a `List` at runtime**. When validating data received from untrusted sources, use `instanceof List<?>` and then verify each element.

Example of a function accepting only a list of strings:

```java
static List<String> checkStrings(Object incoming) {
    if (!(incoming instanceof List<?> rawValues)) {
        throw new IllegalArgumentException("Expected a List");
    }

    List<String> result = new ArrayList<>();
    for (Object value : rawValues) {
        if (!(value instanceof String text)) {
            throw new IllegalArgumentException("Non-String element: " + value);
        }
        result.add(text);
    }
    return List.copyOf(result);
}
```

This is an **illustrative method snippet** that must be placed inside a class with `java.util.List` and `java.util.ArrayList` imported. The function produces a copy after checking every element; `List.copyOf` rejects null and returns an unmodifiable list. If the contract permits null or requires mutability, an appropriate copy strategy must be chosen.

### 6.2. `Class<?>` is also a reifiable type

```java
Class<?> runtimeClass = incoming.getClass();
```

`Class<?>` contains an unbounded wildcard, so the type `Class<?>` itself is reifiable. However, a `Class<?>` only tells you the runtime class of the object — for example, a `List` implementation — without automatically deducing the `String` type argument of an erased source variable.

A `Class<String>` has a concrete type argument, so it is not a reifiable type under the general rule for parameterized types. Although you can write `String.class` and assign it to `Class<String>` thanks to the API signature of class literals, do not conclude that this creates a separate runtime class representing *the parameterization of `Class`*.

## 7. Group D — Arrays: component type exists at runtime

Java arrays are objects, and the JVM maintains a definite **runtime component type**. For example:

```java
String[] names = new String[2];

System.out.println(names.getClass().isArray());               // true
System.out.println(names.getClass().getComponentType());      // class java.lang.String
System.out.println(names instanceof String[]);                // true
```

Arrays also have **covariance**:

```java
String[] strings = new String[1];
Object[] objects = strings;     // Valid
```

Even though the `objects` reference has static type `Object[]`, the actual object is still `String[]`. If you write the wrong type:

```java
objects[0] = 42; // ArrayStoreException at runtime
```

The JVM has enough runtime information to prevent an `Integer` from being written into an array with component type `String`.

### 7.1. Arrays of reifiable types

| Creation expression | Valid? | Runtime component type |
| --- | --- | --- |
| `new int[3]` | Yes | `int` |
| `new String[3]` | Yes | `String` |
| `new Object[3]` | Yes | `Object` |
| `new List[3]` | Yes, raw-type warning may appear | `List` |
| `new List<?>[3]` | Yes | `List` |
| `new Map<?, ?>[3]` | Yes | `Map` |
| `new List<String>[3]` | No | Component `List<String>` is non-reifiable. |
| `new List<? extends Number>[3]` | No | Component is non-reifiable due to bounded wildcard. |
| `new T[3]` in method `<T>` | No | `T` is a non-reifiable type variable. |

From a runtime perspective, an array created with `new List<?>[3]` is still an array whose component class is `List`. This explains why a `List<?>[]` can hold a `List<String>` and a `List<Integer>` in two different slots without a separate wildcard argument check at runtime.

### 7.2. Wildcard array and raw array share the same runtime class

```java
List<?>[] wildcardArray = new List<?>[2];
List[] rawArray = new List[2];

boolean sameRuntimeClass =
        wildcardArray.getClass() == rawArray.getClass(); // true
```

In source code, `List<?>[]` retains more generic constraints than raw `List[]`. Yet the runtime element type of both is `List`, so they share the same array class. You can verify this with:

```java
wildcardArray.getClass().getComponentType() == List.class
```

Each slot of `wildcardArray` is only checked by the JVM to ensure the stored object is a valid `List`. It has no way to verify the type argument of the list element such as `String` or `Integer`.

### 7.3. Why is `new List<String>[2]` forbidden?

Suppose Java allowed such an array:

```java
// This is an invalid assumption in Java:
List<String>[] strings = new List<String>[2];
Object[] objects = strings;
objects[0] = List.of(42);
String first = strings[0].get(0);
```

Because the generic argument `String` is not checked at runtime, writing a `List<Integer>` into an array class whose component is only raw `List` would not be blocked by the array store check for the generic argument. Later, reading `String` could throw `ClassCastException`.

Therefore, Java **forbids directly allocating** an array whose component is `List<String>` (a non-reifiable type). Forbidding creation does not mean declaring the type is completely forbidden:

```java
List<String>[] reference; // Variable declaration is allowed
```

However, `new List<String>[2]` remains a `generic array creation` error. Unchecked casts can cause values of this type to appear through legacy APIs, and you should avoid assuming they are safe.

### 7.4. `T[]` with a type variable remains a special case

Inside a generic class:

```java
class Buffer<T> {
    T[] data;

    // T[] create(int size) {
    //     return new T[size]; // Error: generic array creation
    // }
}
```

When `T` is unbounded, its erasure is `Object`; with `<T extends Number>`, its erasure is `Number`. Yet the class does not know the concrete runtime component class the caller wants, so the compiler does not allow allocating `new T[size]`.

One way to obtain a properly typed array is a **factory**:

```java
static <T> T[] create(int size, java.util.function.IntFunction<T[]> factory) {
    return factory.apply(size);
}

// String[] names = create(3, String[]::new);
```

The snippet above is an illustrative method that must be placed inside a class. The caller supplies an array with real component `String`. Another approach uses `Array.newInstance` with a `Class<T>` type token, though casting to `T[]` must be carefully encapsulated and may produce an unchecked warning.

### 7.5. Reifiable arrays can still cause ArrayStoreException

Reifiability lets the runtime array know its component class; it **does not prove that every write through an alias is safe**. The syntax `Object[] alias = new String[1]` permits a broader alias, yet the runtime performs a store check.

Likewise, a reifiable `List<?>[]` does not prevent you from creating an alias and storing a **List with a different element type**: all of them are `List` according to the runtime component. If a design truly needs a safe collection of `List<String>`, consider `List<List<String>>` or check elements/nested elements when building the data.

## 8. Reflection: erased types and generic declarations

`java.lang.reflect.Field` has two easily confused APIs:

```java
field.getType()        // Class<?> of the field's runtime type, after erasure
field.getGenericType() // java.lang.reflect.Type from the generic declaration, if present
```

If a field is declared `List<String>`, `getType()` reports raw `List`, while `getGenericType()` can return a `ParameterizedType` representing `List<String>` from Signature metadata. This describes **the declared type of the field**; it does not verify that the elements of an object assigned to the field match that type.

### 8.1. Field comparison example

```java
static final class Examples<T> {
    String plain;
    List raw;
    List<?> unknown;
    List<String> names;
    String[] plainArray;
    List<?>[] wildcardArray;
    List<String>[] parameterizedArray;
    T element;
    T[] variableArray;
}
```

This is a nested class included in the complete program below. When inspecting each field with `getType()` and `getGenericType()`:

| Field declaration | `getType()` represents | `getGenericType()` represents |
| --- | --- | --- |
| `String plain` | `String` | `String` |
| `List raw` | `List` | `List` |
| `List<?> unknown` | `List` | `List<?>` |
| `List<String> names` | `List` | `List<String>` |
| `String[] plainArray` | `String[]` | `String[]` |
| `List<?>[] wildcardArray` | `List[]` | `List<?>[]` |
| `List<String>[] parameterizedArray` | `List[]` | `List<String>[]` |
| `T element` | `Object` if `T` is unbounded | `T` |
| `T[] variableArray` | `Object[]` if `T` is unbounded | `T[]` |

For a generic method, there are similarly `getParameterTypes()`/`getGenericParameterTypes()` and `getReturnType()`/`getGenericReturnType()`. That is useful information for frameworks analyzing APIs, yet it does not replace runtime data validation.

### 8.2. `Type` has several forms

A `Type` from `getGenericType()` can be:

- `Class<?>` for ordinary types or appropriate raw/array classes.
- `ParameterizedType` for declarations such as `List<String>` or `List<?>`.
- `TypeVariable<?>` for `T`.
- `GenericArrayType` for arrays containing generic components that cannot be directly represented as a corresponding `Class`, such as `T[]` or `List<String>[]`.
- `WildcardType` when inspecting the wildcard type argument of a `ParameterizedType`.

Do not cast `(Class<?>) field.getGenericType()` blindly for every field: it can throw `ClassCastException` when the actual instance is `ParameterizedType` or `GenericArrayType`. When building frameworks, check `instanceof` for each branch of `Type` and inspect bounds/type arguments with the corresponding API.

### 8.3. Metadata does not turn into runtime validation

Suppose a field is declared `List<String> names`; Reflection returns a `ParameterizedType` with argument `String`, yet a raw alias could pollute the assigned list with elements of the wrong type. Even then, the metadata still accurately states that **the field was declared** as `List<String>` — it does not check every existing element.

If you need to ingest data from JSON, JDBC, or legacy APIs, you must use a parser, schema, or per-element checks matching the expected generic structure. Simply reading `getGenericType()` does not make data automatically type-safe.

## 9. Complete Java 17 program for hands-on classification

The following file **`ReifiableTypesDemo.java`** combines `instanceof List<?>`, wildcard/raw arrays, runtime component checks, and Reflection. It intentionally contains two raw-type usages for comparison, so enabling `-Xlint:rawtypes` will emit warnings; those warnings are part of the demonstration.

```java
import java.lang.reflect.Field;
import java.util.List;

public class ReifiableTypesDemo {
    static final class Examples<T> {
        String plain;
        List raw;
        List<?> unknown;
        List<String> names;
        String[] plainArray;
        List<?>[] wildcardArray;
        List<String>[] parameterizedArray;
        T element;
        T[] variableArray;
    }

    public static void main(String[] args) throws Exception {
        Object mixed = List.of("Java", 17);
        System.out.println("instanceof-List<?>=" + (mixed instanceof List<?>));

        List<?>[] wildcardArray = new List<?>[2];
        wildcardArray[0] = List.of("Java");
        wildcardArray[1] = List.of(17);
        List[] rawArray = new List[2];
        System.out.println("same-array-class="
                + (wildcardArray.getClass() == rawArray.getClass()));
        System.out.println("array-component="
                + wildcardArray.getClass().getComponentType().getTypeName());
        System.out.println("elements="
                + wildcardArray[0].get(0) + "," + wildcardArray[1].get(0));

        Object[] alias = new String[1];
        try {
            alias[0] = 99;
        } catch (ArrayStoreException e) {
            System.out.println("store-check=" + e.getClass().getSimpleName());
        }

        String[] fields = {"plain", "raw", "unknown", "names", "plainArray",
                "wildcardArray", "parameterizedArray", "element", "variableArray"};
        for (String name : fields) {
            Field field = Examples.class.getDeclaredField(name);
            System.out.println(name + ": raw=" + field.getType().getTypeName()
                    + "; generic=" + field.getGenericType().getTypeName());
        }
    }
}
```

Compile with Java 17 or a JDK supporting `--release 17`:

```bash
javac --release 17 -Xlint:rawtypes ReifiableTypesDemo.java
java ReifiableTypesDemo
```

The compiler emits **3 `rawtypes` warnings** for the source above: one on field `List raw`, and two on `List[] rawArray = new List[2]` (at both the declaration and the array creation expression). These are warnings, not compile-time errors.

Exact stdout of the program:

```text
instanceof-List<?>=true
same-array-class=true
array-component=java.util.List
elements=Java,17
store-check=ArrayStoreException
plain: raw=java.lang.String; generic=java.lang.String
raw: raw=java.util.List; generic=java.util.List
unknown: raw=java.util.List; generic=java.util.List<?>
names: raw=java.util.List; generic=java.util.List<java.lang.String>
plainArray: raw=java.lang.String[]; generic=java.lang.String[]
wildcardArray: raw=java.util.List[]; generic=java.util.List<?>[]
parameterizedArray: raw=java.util.List[]; generic=java.util.List<java.lang.String>[]
element: raw=java.lang.Object; generic=T
variableArray: raw=java.lang.Object[]; generic=T[]
```

Reading the three groups of results:

- `instanceof-List<?>=true` only confirms `mixed` is a `List`; it does not check element type uniformity.
- `same-array-class=true`, `array-component=java.util.List` show that both the raw array and the wildcard array have runtime component `List`.
- `getType()` for generic fields returns erased types (`List`, `Object`, `Object[]`), whereas `getGenericType()` displays declarations with `?`, `String`, and `T` from metadata.

The line `store-check=ArrayStoreException` proves that a `String[]` has runtime component `String` even when its alias is `Object[]`: the JVM checks the element being stored.

## 10. Expected compile-time errors when using non-reifiable types

This is an **intentionally invalid code snippet**, used solely to observe compiler diagnostics. Do not place it together with the working program above.

File **`InvalidReifiable.java`**:

```java
import java.util.List;

class InvalidReifiable {
    static <T> void run(Object x) {
        List<String>[] a = new List<String>[2];
        T[] b = new T[2];
        if (x instanceof List<String>) {
            System.out.println(x);
        }
    }
}
```

Compile:

```bash
javac --release 17 InvalidReifiable.java
```

The compiler rejects three places:

```text
error: generic array creation
    List<String>[] a = new List<String>[2];

error: generic array creation
    T[] b = new T[2];

error: Object cannot be safely cast to List<String>
    if (x instanceof List<String>) {
```

Explanation:

1. `List<String>` is non-reifiable, so it cannot serve as the component for the expression `new List<String>[2]`.
2. `T` is a non-reifiable type variable, so `new T[2]` cannot be allocated.
3. Given a value of static type `Object`, the JVM has no way to fully check the `String` type argument of a `List` via `instanceof List<String>`.

Do not "fix" this into an unchecked cast `List<String>[] a = (List<String>[]) new List<?>[2]` without a proven invariant. That cast does not make the JVM aware of `String` in the component type and can lead to heap pollution.

## 11. How to use reifiable types across APIs

### 11.1. With `instanceof`

Use checks for types that can be determined at runtime:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}

if (value instanceof List<?> elements) {
    System.out.println(elements.size());
}
```

With arrays:

```java
if (value instanceof String[] words) {
    System.out.println(words.length);
}
```

These examples are **code fragments to place inside a method**, with `value` having an appropriate reference type and `java.util.List` imported. If you want finer classification than `List<?>`, you must inspect elements or use metadata/protocols from the data source.

### 11.2. With `Class` objects and reflection

A `Class<?>` can describe `String.class`, `List.class`, or `String[].class`. However, there is no class literal `List<String>.class` representing a runtime specialization of a list.

```java
Class<?> stringClass = String.class;
Class<?> listClass = List.class;
Class<?> arrayClass = String[].class;
```

If a framework needs to preserve **an entire type tree** like `List<String>` or `Map<String,List<Integer>>`, it needs a `Type`, `ParameterizedType`, or a *type token* mechanism based on generic declarations. That serves to describe/decode types; the `Class` object of an already created `ArrayList` still does not remember the source variable's type parameters.

### 11.3. With arrays and generic varargs

Varargs in bytecode are array-based. A method such as:

```java
static <T> void examine(List<T>... lists) {
    // ...
}
```

has a non-reifiable generic component, so warnings about heap pollution or unchecked array creation can appear. You should not attach `@SafeVarargs` merely to silence the compiler: the annotation is a promise about how the method uses the array, not something that makes `List<T>` reifiable.

When you simply need to hold multiple lists of the same kind, consider nested collections:

```java
List<List<String>> groups = new ArrayList<>();
groups.add(List.of("a", "b"));
```

This eliminates the need to create a `List<String>[]` directly. However, a `List<List<String>>` is still not a reifiable type when considering all type arguments; its safety comes from compile-time generic checking and data discipline, not from having a separate `List<List<String>>` class at runtime.

## 12. Common misconceptions and mistakes

### 12.1. "Raw types are reifiable, which means raw types are good for type safety"

False. Raw `List` is reifiable in terms of **runtime shape**, yet it removes type arguments from compile-time checking, permitting unchecked operations. Choose `List<?>` when you need to accept a list of unknown element type without needing to add arbitrary elements.

### 12.2. "`List<?>` is reifiable, which means element types are known"

False. `?` is literally an unknown type. The JVM recognizes `List` yet does not infer a concrete type argument. If you need `List<String>`, inspect each element and construct a list with a clear contract.

### 12.3. "`List<String>` is non-reifiable, which means variables of this type cannot be declared"

False. `List<String>` is the foundation of compile-time generic type safety. You can certainly declare `List<String>` or methods returning `List<String>`; you simply cannot use certain runtime operations requiring a reifiable type such as `new List<String>[n]` and certain forms of runtime type checks.

### 12.4. "Arrays are just old lists, so the JVM does not know element types"

False. Arrays have a runtime component class. `String[]` guards against mistaken writes via `ArrayStoreException`. However, an array with component `List` does not know the type argument of **each individual list inside**.

### 12.5. "`T extends Number` makes `T` reifiable"

False. The bound tells the compiler which operations are permitted on `T` and determines erasure; it does not create a new runtime `Class<T>` for the type variable. `new T[n]` remains invalid. Use a factory or class token when allocation is needed.

### 12.6. "Reflection reads `List<String>`, so the JVM checks element types at runtime"

False. `Field.getGenericType()` reads the generic declaration from class metadata. If data is written wrongly via a raw alias or loaded from an unchecked external source, that metadata still exists while elements can have the wrong type.

### 12.7. "`List<?>[]` and `List[]` have the same class, so you might as well use the raw type"

False. Both types can share the same runtime array class, yet they have **different source-level checking rules**. Using `List<?>[]` expresses that elements are Lists with unknown generic arguments; raw `List[]` drops many checks and can trigger warnings.

### 12.8. "Erasure turns runtime `String[]` into `Object[]`"

False. Erasure applies to **generic representations of signatures**, not to automatically changing the runtime component of an already created array object. With `<T> T[] echo(T[] array)`, the descriptor may use `Object[]`, yet if the caller passes `String[]`, the object remains a genuine `String[]`.

## 13. Classification checklist when reading code or fixing bugs

For any questionable type, proceed in order:

1. **Inspect the type structure:** primitive, non-generic class/interface, raw type, parameterized type, type variable, or array?
2. If it is a parameterized type, **are all arguments strictly unbounded `?`?** If yes, that is a reifiable case; if there is `String`, `? extends Number`, or `? super Integer`, no.
3. If it is an array, **classify the component type** first and repeat the rule across each dimension; `List<?>[]` is reifiable, `List<String>[]` is not.
4. If it is `T`, **do not confuse erasure with reifiability**. A bound only tells the replacement type of `T` under erasure; it does not turn `T` into a concrete runtime class.
5. If `instanceof` or array allocation is needed, check the language rules for that expression before writing code.
6. If inspecting Reflection, **separate runtime `Class<?>` from `Type`/Signature metadata**.
7. If converting generic data from external sources, **validate each element** or use an explicit parser/schema when a stricter contract is needed.
8. If encountering unchecked casts, raw aliases, or generic array creation, prioritize fixing the API design and preserving type information from source to destination.

Quick lookup table:

| Need | Type/API to consider | Note |
| --- | --- | --- |
| Only need to know if an object is a `List` | `instanceof List<?>` | Does not prove elements are `String`. |
| Accept any list for reading | `List<?>` | Avoid raw types when write capability is unnecessary. |
| Store a list of strings with compile-time checks | `List<String>` | Being non-reifiable does not diminish type safety value. |
| True string array at runtime | `String[]` | Store check can throw `ArrayStoreException` on invalid writes. |
| Array of lists with unknown type arguments | `List<?>[]` | Runtime only checks that elements are `List`. |
| Need to create a `T[]` array | `IntFunction<T[]>`, array factory | Caller creates the array with the desired runtime component. |
| Need to read a field's generic declaration | `Field.getGenericType()` | Declaration metadata; does not validate instance data. |
| Need to read actual class or array component | `getClass()`, `getComponentType()` | Reveals generic erasure and runtime component class. |

## 14. Self-check questions

**Question 1.** Among the four types `List`, `List<?>`, `List<String>`, and `List<? extends Number>`, which ones are reifiable?

<details>
<summary>Answer</summary>

Raw `List` and `List<?>` are reifiable. `List<String>` is non-reifiable because it has a concrete argument; `List<? extends Number>` is non-reifiable because its wildcard is bounded.

</details>

**Question 2.** How do `new List<?>[2]` and `new List<String>[2]` differ?

<details>
<summary>Answer</summary>

`List<?>` is reifiable, so it can serve as the component of array creation; the JVM uses the runtime component `List`. `List<String>` is non-reifiable, so the expression `new List<String>[2]` is rejected with a `generic array creation` error.

</details>

**Question 3.** Why can `String[]` throw `ArrayStoreException` when referenced as `Object[]`?

<details>
<summary>Answer</summary>

Arrays are covariant; `Object[]` can point to a `String[]`. The JVM retains the runtime component `String`, and therefore rejects writing an `Integer` into the array even though the alias's static type is `Object[]`.

</details>

**Question 4.** `Field.getGenericType()` returns `java.util.List<java.lang.String>`. Does that confirm the current list contains only `String`?

<details>
<summary>Answer</summary>

No. It describes the declared type of the field via generic Signature metadata. The actual contents can still suffer from heap pollution if code uses raw types, unchecked casts, or unvalidated data sources.

</details>

**Question 5.** With `<T extends Number>`, why cannot `new T[5]` be created directly inside a generic method even though `T` erases to `Number`?

<details>
<summary>Answer</summary>

`T` remains a non-reifiable type variable. Erasure to `Number` does not indicate whether the caller expects `Integer[]`, `Double[]`, or another subtype array. Use `IntFunction<T[]>` or an allocation mechanism with a concrete runtime component type when an array is needed.

</details>

**Question 6.** Can `List<?>[]` and `List[]` have the same runtime class? If so, which type should be used in new code?

<details>
<summary>Answer</summary>

Yes: the runtime array of both has component `List`. In new code, `List<?>[]` usually provides a clearer compile-time contract when elements are Lists with unknown type arguments; raw `List[]` can trigger `rawtypes`/`unchecked` warnings.

</details>

## 15. Key takeaways

A **reifiable** type is a type with a runtime representation suitable for operations that require determining a type at runtime. The main groups are primitives, non-generic classes/interfaces, raw types, parameterized types containing only **unbounded** wildcards, and arrays with reifiable components.

`List<String>` has great value at compile time despite being non-reifiable; `List<?>` is reifiable yet does not reveal the concrete type argument; raw `List` is reifiable yet can forfeit generic checks; `String[]` is reifiable and checked by the JVM on component writes, while `List<String>[]` cannot be directly allocated.

When debugging, always separate **the declared source type**, **the actual runtime class/array component**, and **the generic metadata readable by Reflection**. This distinction helps you choose `instanceof` properly, avoid invalid generic arrays, and design type-safe data validation boundaries.