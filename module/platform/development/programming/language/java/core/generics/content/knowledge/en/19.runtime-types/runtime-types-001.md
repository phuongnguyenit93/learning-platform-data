# What is a reifiable type in Java?

In Java, a **reifiable type** is a type whose type information is fully available at runtime so that the JVM can perform type checks appropriate for that type. Conversely, many generic-related types, such as `List<String>` or a type variable `T`, are **non-reifiable**: after *type erasure*, the JVM does not have enough information about concrete type arguments to directly check the full generic type the way the compiler checked it in source code.

For example, an `ArrayList<String>` object and an `ArrayList<Integer>` object both have the runtime class `ArrayList`. The JVM can check whether they are a `List`, but it cannot simply use `instanceof` on an `Object` reference to confirm that the first list truly conforms to `List<String>`.

This concept is important when studying `instanceof`, class literals, generic arrays, raw types, wildcards, and reflection.

> Common point of confusion: **`List<?>` is reifiable**, but that **does not mean the JVM knows the element type of the list**. `List<?>` only requires checking that it is a `List`, without requiring identification of a concrete type argument.

## 1. "Fully available at runtime" — sufficient for which checks?

In source code, `List<String>` lets `javac` know that an `add` call must accept `String` and the result of `get` is treated as `String`. However, the JVM operates using runtime classes and type-erased descriptors. The `String` argument of a `List<String>` variable is normally not stored as a separate class named `List<String>`.

Consider this illustration:

```java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();

boolean sameClass = names.getClass() == numbers.getClass(); // true
```

This is a snippet placed inside a valid Java method. Both objects are created with `ArrayList`; the difference in generic arguments belongs to source-level type information and does not create two separate runtime classes.

Therefore, **reifiable** does not mean "stores every type detail appearing in source code," but rather that a type has enough runtime structure required by the language definition. `List<?>` only describes a parameterized type whose type argument is unbounded; at runtime, there is no need to distinguish `String`, `Integer`, or any other concrete element type to check whether an object is a `List<?>`.

In contrast, for **`List<String>`**, a true check would have to verify the `String` parameter as well. That kind of check is not guaranteed by a normal runtime check on an erased list object.

## 2. Quick identification of reifiable groups

According to **JLS §4.7**, common reifiable groups are primitives, non-generic classes/interfaces, raw types, parameterized types where **all arguments** are the unbounded wildcard `?`, and arrays whose component type is reifiable. Nested types also need their enclosing type name components evaluated under JLS rules.

| Example type | Reifiable? | Explanation |
| --- | --- | --- |
| `int`, `String`, `Runnable`, `String[]` | Yes | Primitive, non-generic type, or array with an appropriate runtime component |
| Raw `List`, `Map` | Yes | Has a runtime class/interface, though raw operations may emit unchecked warnings |
| `List<?>`, `Map<?, ?>`, `List<?>[]` | Yes | Unbounded wildcard and reifiable component type |
| `List<String>`, `Map<String,Integer>` | No | Concrete type arguments are not checked by an instance's runtime class |
| `List<? extends Number>`, `List<? super Integer>` | No | Bounded wildcard, different from unbounded `?` |
| `T`, `T[]`, `List<String>[]` | No | Type variable or non-reifiable component type |

Three important traps: `List<? extends Object>` does not belong to the unbounded wildcard group like `List<?>`; `List<List<?>>` is not reifiable because the outer type argument is `List<?>` rather than a `?`; and a bound `<T extends Number>` **does not turn T into a reifiable type**.

This table is only for conceptual identification. The next type-classification lesson expands in detail on raw/wildcard/array cases along with runtime array components, Reflection, and API impact.


## 3. Comparing reifiable and non-reifiable types via `instanceof`

Suppose data only has static type `Object`:

```java
Object value = java.util.List.of("Java", "Generics");

boolean a = value instanceof java.util.List<?>; // Valid
boolean b = value instanceof java.util.List;    // Valid, uses raw type
// boolean c = value instanceof java.util.List<String>; // Compile-time error
```

Calling `instanceof List<?>` asks **is the object a `List`?** Not "are all elements `String`?". `instanceof List` can also check the erased class/interface, but `List<?>` should be preferred to preserve generic-appropriate phrasing.

An important counterexample:

```java
Object value = java.util.List.of(10, 20, 30);

System.out.println(value instanceof java.util.List<?>); // true
```

The result is `true` even though the elements here are `Integer`, not `String` at all. `List<?>` does not assert any specific element type.

A common checking form in Java 17+ code is pattern matching:

```java
if (value instanceof java.util.List<?> items) {
    System.out.println("So phan tu: " + items.size());
}
```

`items` has type `List<?>`; reading an element gives a value usable as `Object`, and you cannot arbitrarily add a `String` or `Integer` through this variable.

**Note on checking generic types:** stating that "every occurrence of `instanceof List<String>` is an error in any context" is an oversimplification; modern Java also considers *cast compatibility* and the static type of the expression. The case to remember when checking an object of unknown type, such as `Object value` above, is that **you cannot verify a concrete generic argument using `instanceof`**. Do not use a case where the compiler already knows the static type to infer that the runtime can read `String` inside a `List`.

## 4. Why is `List<?>` reifiable while `List<String>` is not?

Both types use the `List` interface at runtime, yet their checking requirements differ:

```text
Object value = ...

value instanceof List<?>
  -> Checks whether the object implements List
  -> Does not require identifying the element type

value instanceof List<String>
  -> Wants to check the String argument as well
  -> The runtime class List does not store a separate String argument per instance
  -> No corresponding direct runtime check exists
```

The difference lies in **how much the type asserts**. `List<?>` makes a weaker requirement: "is a list of some unknown element type." The JVM can check the raw `List` part and satisfy the check. By contrast, `List<String>` requires a specific constraint that is not fully preserved in the runtime class.

This also explains why `Map<?, ?>` is reifiable: both the key type and value type are unconstrained, so the runtime check only needs to confirm that it is a `Map`.

Do not interpret `?` as "accepts writing any kind of element." In `List<?>`, the compiler treats the element type as an unknown type; you can read values as `Object` but **cannot add arbitrary objects** (normally only `null` can be added via the `add` method). This is a fundamental difference from raw `List`, where write operations can produce **unchecked warnings** and heap pollution.

## 5. Arrays are the clearest example of runtime type checks

Java arrays carry **component type** information at runtime. Therefore, a `String[]` array can be checked as `String[]`, even when held in a variable of type `Object` or `Object[]`.

```java
Object value = new String[] { "An", "Binh" };

System.out.println(value instanceof String[]); // true
System.out.println(value instanceof Object[]); // true
```

Arrays are **covariant**, so a `String[]` can be referenced through `Object[]`. Yet the runtime still knows the actual array has component type `String` and can reject a wrongly typed write operation:

```java
Object[] slots = new String[1];

try {
    slots[0] = 42;
} catch (ArrayStoreException exception) {
    System.out.println("ArrayStoreException");
}
```

The result is `ArrayStoreException`: an `Integer` cannot be stored in a runtime `String[]` array.

Contrast this with generic collections:

```java
java.util.List<String> values = new java.util.ArrayList<>();
// values.add(42); // Rejected by the compiler immediately when proper generic information is present
```

Arrays check their component type at runtime; generic collections rely primarily on source-level type checking. When a program uses raw types or unchecked conversions to bypass generics, errors may only surface as a `ClassCastException` when reading an element, rather than an `ArrayStoreException` when writing.

## 6. Why is `new List<?>[2]` allowed while `new List<String>[2]` is not?

This is an important practical consequence of reifiability.

```java
// Valid:
java.util.List<?>[] groups = new java.util.List<?>[2];
groups[0] = java.util.List.of("Java");
groups[1] = java.util.List.of(17);

// Does not compile:
// java.util.List<String>[] strings = new java.util.List<String>[2];
```

The element of `List<?>[]` has type `List<?>`, which belongs to the reifiable group. At runtime, that array has component class **`List`**, so any object implementing `List` matches the array's element type.

By contrast, `List<String>` is non-reifiable. If direct creation of a `List<String>[]` array were allowed, array element assignment checks could not verify the `String` argument of each list. Java rejects **generic array creation** with such a component type to avoid creating a false sense of type safety.

Notably, `List<?>[]` allows storing both `List<String>` and `List<Integer>`, because it does not constrain the element type inside each list. It does not turn the elements into `List<Object>`, nor does it allow arbitrarily writing an `Integer` into a `List<String>` through a `List<?>` reference.

Furthermore, **not being able to create `new List<String>[2]` does not mean a variable declared as `List<String>[]` can never exist**. Legacy code or unchecked casts can produce variables of that type; they require careful heap-pollution control. The rule to remember here is that Java **forbids directly creating an array with a non-reifiable component type**.

## 7. Is the type variable `T` reifiable?

No. Even with an upper bound, a type variable still does not hold a single concrete type at runtime to be used as a component type or class literal:

```java
// Snippet: the three error-commented lines cannot be uncommented to compile.
class Container<T extends Number> {
    void inspect(Object value) {
        // if (value instanceof T) { } // Invalid
        // Class<?> type = T.class;      // Invalid
        // T[] elements = new T[10];     // Invalid generic array creation
    }
}
```

At the erasure level, `T extends Number` is erased to `Number`. However, that **does not turn `T` into `Number` in terms of the parameterized type's meaning in source code**: a `Container<Integer>` still wants `T = Integer`, whereas a `Container<Double>` uses `T = Double`.

If the actual requirement is only asking "is `value` a `Number`?", you can write `value instanceof Number`; but that answer does not prove `value` is **the concrete type `T`**.

A common way to check a concrete class type supplied by the caller is to pass a **type token**:

```java
static <T> boolean matches(Class<T> token, Object value) {
    return token.isInstance(value);
}

// matches(String.class, "Java") -> true
// matches(Integer.class, "Java") -> false
```

`Class<T>` helps an API preserve type information of a **concrete class** when the caller passes `String.class` or `Integer.class`. However, you cannot use a class literal `List<String>.class` to obtain a token fully representing `List<String>`; `List.class` only represents the raw runtime interface `List`.

When you need to construct `T`, instead of `new T()`, you can require a `Supplier<T>` or a factory; this solves the problem of **not knowing the concrete constructor/type**, rather than making all generic types naturally reifiable.

## 8. A Java 17+ program to observe reifiable types directly

Save the following code into **`ReifiableTypeDemo.java`**:

```java
import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class ReifiableTypeDemo {
    static final class Fields {
        List<String> named;
        List<?> unknown;
    }

    public static void main(String[] args) throws NoSuchFieldException {
        Object names = new ArrayList<String>(List.of("An", "Binh"));
        Object numbers = new ArrayList<Integer>(List.of(1, 2));
        Object map = Map.of("a", 1);

        System.out.println("List<?> runtime check: "
                + (names instanceof List<?>));
        System.out.println("Map<?, ?> runtime check: "
                + (map instanceof Map<?, ?>));
        System.out.println("Same ArrayList class: "
                + (names.getClass() == numbers.getClass()));

        List<?>[] groups = new List<?>[2];
        groups[0] = List.of("Java");
        groups[1] = List.of(17);

        System.out.println("List<?>[] runtime check: "
                + (groups instanceof List<?>[]));
        System.out.println("Array component: "
                + groups.getClass().getComponentType().getTypeName());

        Object[] slots = new String[1];
        try {
            slots[0] = 42;
        } catch (ArrayStoreException exception) {
            System.out.println("Array store: ArrayStoreException");
        }

        Class<?> token = String.class;
        System.out.println("Class token checks String: "
                + token.isInstance("ok"));

        Field field = Fields.class.getDeclaredField("named");
        System.out.println("Field erased type: "
                + field.getType().getTypeName());
        System.out.println("Field generic metadata: "
                + field.getGenericType().getTypeName());

        Object mixed = List.of("Java", 42);
        System.out.println("Mixed list matches List<?>: "
                + (mixed instanceof List<?>));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ReifiableTypeDemo.java
java ReifiableTypeDemo
```

Expected output:

```text
List<?> runtime check: true
Map<?, ?> runtime check: true
Same ArrayList class: true
List<?>[] runtime check: true
Array component: java.util.List
Array store: ArrayStoreException
Class token checks String: true
Field erased type: java.util.List
Field generic metadata: java.util.List<java.lang.String>
Mixed list matches List<?>: true
```

Explanation in order:

1. `List<?>` and `Map<?, ?>` allow runtime interface checks without requiring identification of type arguments.
2. `ArrayList<String>` and `ArrayList<Integer>` are both `ArrayList`, so `getClass()` is equal. Generic type arguments do not cause the JVM to generate two runtime classes.
3. `new List<?>[2]` is valid; the runtime array has component type `java.util.List`.
4. `Object[] slots = new String[1]` retains the runtime array type `String[]`; writing an integer is rejected with `ArrayStoreException`.
5. `String.class` is a class token carrying actual `String` information; `Class.isInstance("ok")` succeeds.
6. `Field.getType()` returns the erased type `List`, while `Field.getGenericType()` can read the field declaration metadata `List<String>`.
7. A list mixing `String` and `Integer` still satisfies `instanceof List<?>`; this illustrates that **reifiable does not mean validating element kinds**.

The program intentionally uses `List.of("Java", 42)` in the final example to prove that the `List<?>` check accepts a list containing elements of multiple types. It does not claim this is a `List<String>`.

## 9. Reflection still sees generics: does that contradict non-reifiable types?

No. Java distinguishes **generic declaration metadata** from the **runtime type identity of an object**.

In this example:

```java
class Example {
    java.util.List<String> names;
}
```

If the class is compiled with the corresponding `Signature` metadata, reflection via `Field.getGenericType()` can read `List<String>`. However, `Field.getType()` only returns the runtime class `List`.

The metadata indicates that **the declared field** has type argument `String`. It does not automatically guarantee that an object placed into the field via unsafe code always contains only `String`. Similarly, the fact that a subclass explicitly declared `extends Parent<String>` can be reflected via `getGenericSuperclass()` does not mean every instance of `Parent<T>` carries a separate runtime class per `T`.

For an ordinary object:

```java
Object value = new java.util.ArrayList<String>();
Class<?> runtime = value.getClass(); // java.util.ArrayList
```

You cannot deduce `String` solely from `runtime` through the standard `getClass()` mechanism. An `ArrayList<Integer>` also returns that same class.

**Therefore:** a non-reifiable parameterized type can appear in **declaration metadata**, yet still not be enough for the JVM to directly perform a `List<String>` type check on an `Object` variable.

## 10. How do reifiable type, raw type, wildcard, and erasure differ?

These four concepts often appear together, yet they answer four different questions:

| Concept | Question it answers | Example |
| --- | --- | --- |
| **Type erasure** | How does the compiler turn generic types into descriptors/erased types? | `List<String>` → `List`, `T` → `Object` or bound |
| **Reifiable type** | Does the JVM have enough runtime representation to check this type? | `String[]`, `List<?>`, `Map<?, ?>` |
| **Raw type** | Is a generic class/interface being used without specifying type arguments? | `List`, `Map` |
| **Unbounded wildcard** | Does the parameterized type accept an unknown type argument? | `List<?>`, `Map<?, ?>` |

Raw `List` is reifiable, yet raw types can cause **unchecked warnings** when manipulating generic data. `List<?>` is also reifiable while still preserving generic rules that prevent adding elements of unknown type.

Key point to remember: **reifiable is not synonymous with "safer in every operation."** A raw `List` is reifiable yet can still allow `raw.add(42)` into an object that other code actually treats as `List<String>`. Conversely, `List<String>` is non-reifiable yet has strong type checking in normal Java source code.

## 11. Is `Class<String>` a reifiable type?

This is an interesting case: `String.class` is a valid class literal expression, and **the static type of the expression** is normally represented by the compiler as `Class<String>`. Yet the parameterized type `Class<String>` itself is **not** a parameterized type whose arguments are all unbounded wildcards, so it does not belong to the reifiable generic type group.

There is no contradiction here: the class literal `String.class` produces/references the `Class` object describing **the runtime class `String`**, not a separate runtime class named `Class<String>`. Saying `Class<String>` is non-reifiable refers to checking the entire generic type `Class<String>` on an object of unknown type; it does not take away the ability to use `String.class` as a token.

Example:

```java
Class<String> stringType = String.class;
System.out.println(stringType.isInstance("text")); // true

Class<?> unknownClass = stringType; // Valid
```

There is no corresponding `List<String>.class` class literal syntax for the JVM to fully represent a `List` with elements of type `String`. If a serialization library needs to preserve `List<String>`, it typically requires `java.lang.reflect.Type`, `ParameterizedType`, or a custom *type token* structure that can hold declaration-level metadata; checking/converting individual elements still depends on the library's contract.

## 12. Practical limitations caused by non-reifiable types

### 12.1. `instanceof` does not replace element checks

```java
Object value = java.util.List.of(1, 2);

// Valid:
if (value instanceof java.util.List<?> list) {
    for (Object element : list) {
        System.out.println(element);
    }
}

// Invalid if value has static type Object:
// if (value instanceof java.util.List<String>) { ... }
```

If you must validate that a list contains only `String`, you need to actually check the elements or use an object already guaranteed by a trustworthy API. Simply knowing `instanceof List<?>` is not enough.

### 12.2. Cannot create generic arrays with non-reifiable component types

```java
// Invalid:
// java.util.List<String>[] array = new java.util.List<String>[3];

// Valid:
java.util.List<?>[] array = new java.util.List<?>[3];
```

If an algorithm must hold multiple lists of `String`, it is usually easier to maintain type safety with **`List<List<String>>`** rather than trying to create `List<String>[]`.

### 12.3. Cannot use a type variable as a concrete runtime class

```java
// Inside a generic class:
class Sample<T> {
    // Class<?> cls = T.class;      // Invalid
    // T value = new T();           // Invalid
    // T[] values = new T[4];       // Invalid
}
```

For cases requiring object creation, pass a `Supplier<T>` or factory. For cases requiring a runtime class check, pass `Class<T>` if `T` is represented by a concrete class, or a `Type` mechanism carrying broader information for complex generic data.

### 12.4. Do not infer generic safety from an unchecked cast

```java
Object input = java.util.List.of(42);

// Only illustrates unsafe behavior with an unchecked cast:
java.util.List<String> strings = (java.util.List<String>) input;
// String s = strings.get(0); // May throw ClassCastException
```

The cast can succeed because the runtime only checks `List`, not the `String` type argument. When a `String` is needed from a collection containing `Integer`, the read operation fails.

That is why the compiler warns **unchecked**: there is a part of the generic promise that the runtime cannot prove.

## 13. Common misconceptions

**"Reifiable means the runtime stores all generic type arguments."** False. `List<?>` is reifiable yet does not store and validate a specific element type.

**"`List<String>` being non-reifiable means the compiler cannot check type safety."** False. `List<String>` is still strictly checked by the compiler; the limitation lies in the runtime representation and checking of the full parameterized type.

**"Only non-generic classes are reifiable."** False. Raw types, primitive types, arrays with reifiable element types, and types like `List<?>` or `Map<?, ?>` can all be reifiable.

**"`List<? extends Number>` is reifiable because `List` can still be checked."** False by definition: the wildcard argument is bounded, not unbounded `?`; the full parameterized type itself does not belong to the reifiable group.

**"All arrays with generics are forbidden."** False. `new List<?>[2]` is valid; what is forbidden is directly creating an array with a non-reifiable component type such as `List<String>`.

**"Reflection can read `List<String>`, so every instance knows it is a `List<String>`."** False. Reflection can read **declaration** metadata even though an `ArrayList`'s runtime class does not contain a separate type argument per instance.

**"`List<?>` is equivalent to raw `List`."** False. Both are reifiable, yet generic checking when **writing data** is very different: `List<?>` preserves capture-type rules, while a raw type drops part of those guarantees.

**"Just having `Class<T>` allows checking `List<String>` as a separate runtime class."** False. `Class<T>` fits a concrete class like `String`; a nested generic type with type arguments must be described and validated by another mechanism if needed.

## 14. Self-check exercises

**Question 1.** Is `String[]` reifiable? Why?

Yes. `String` has a clear runtime class and the array carries the runtime component type `String`.

**Question 2.** Is `Map<?, ?>` reifiable?

Yes. Both type arguments are unbounded wildcards.

**Question 3.** Is `List<? extends Number>` reifiable?

No. This is not `List<?>`; the wildcard has a concrete upper bound.

**Question 4.** Can `List<?>[]` be created with `new List<?>[3]`?

Yes. The component type `List<?>` is reifiable, so creating this array form is valid.

**Question 5.** Why cannot `List<String>[]` be created directly with `new List<String>[3]`?

Because the component type `List<String>` is non-reifiable. The runtime array cannot fully check the `String` type argument when storing elements.

**Question 6.** A field declared as `List<String>` is reported by reflection as `ParameterizedType`. Does that make `List<String>` reifiable?

No. Metadata about a declaration differs from the runtime's ability to fully check the type of an arbitrary object.

**Question 7.** What is the result of `Object x = List.of(42); x instanceof List<?>;`?

`true`, because `x` is a `List`. The check does not require the elements to be `String` or any concrete type argument.

## 15. How to remember and apply

Ask yourself two questions before using a generic type in a runtime expression:

1. **What does the runtime need to check?** Just whether the object is a `List`, belongs to class `String`, or also needs to prove each specific type argument?
2. **Does that information reside on the runtime object/class or only on the generic declaration?** `String[]` has a runtime component class; an ordinary `List<String>` does not have a separate runtime class carrying the `String` parameter.

When you only need to ask whether an object is a collection, use `instanceof List<?>`. When you need to confirm that every element has the right type, check each element or keep the data inside an API with a safe generic contract. When you need to create an array, choose a reifiable element type or consider using a collection instead. When you need reflection, distinguish between runtime `Class` and `Type` metadata describing the generic declaration.

**Conclusion:** a **reifiable type** has sufficient representation at runtime to perform its corresponding type checks. In Java, primitive types, non-generic types, raw types, types parameterized solely with unbounded wildcards, and arrays of reifiable types are the key groups. Types such as `List<String>`, `List<? extends Number>`, and the type variable `T` are non-reifiable. Understanding the distinction accurately explains the rules for `instanceof`, generic array creation, type erasure, unchecked casts, and reflection.