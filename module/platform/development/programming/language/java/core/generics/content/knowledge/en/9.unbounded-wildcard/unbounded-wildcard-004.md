# Restrictions on Adding and Replacing Elements Through `List<?>` in Java

## 1. The problem to understand

In Java, `List<?>` is a `List` with an **unknown element type**. The `?` symbol is an *unbounded wildcard*. It allows referencing lists with many different element types without losing generics type checking:

```java
List<String> words = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();

List<?> first = words;    // Valid
List<?> second = numbers; // Valid
```

However, being able to reference `List<String>` or `List<Integer>` does not mean you can add any value into the list through a `List<?>` variable.

Core principles:

- **Reading:** retrieved elements can be safely used as type `Object`.
- **Adding or replacing with a non-`null` value:** the compiler does not know whether the value matches the actual element type, so it disallows it.
- **Adding/replacing with `null`:** may **compile**, because `null` is compatible with every reference type; execution can still fail depending on the list.
- **Removing, clearing, or repositioning elements:** many operations can still compile because they do not introduce a new value of unknown type into the list.

`List<?>` **does not mean an immutable or read-only list**. Compile-time type restrictions and runtime mutability of the list object are two separate matters.

## 2. Why can't we `add` a concrete element?

Consider the example:

```java
List<String> strings = new ArrayList<>();
List<?> unknown = strings;

unknown.add("Java"); // COMPILE ERROR
unknown.add(10);     // COMPILE ERROR
unknown.add(new Object()); // COMPILE ERROR
```

The compiler knows `unknown` references a list with some element type, yet **cannot assume that type is `String`, `Integer`, or `Object`**. If `add(10)` were allowed through a `List<?>` pointing to `List<String>`, an `Integer` value would slip into a list promised to hold `String`.

Conceptually, the compiler creates an internal type often called a **wildcard capture**, such as `CAP#1`, to represent the unknown element type in a usage context of `List<?>`. `add(E)` requires an argument of the exact type `E`, while neither `String` nor `Integer` is guaranteed to be compatible with `CAP#1`.

This error has nothing to do with whether the list is currently empty:

```java
List<?> empty = new ArrayList<String>();
empty.add("hello"); // Still a compile error
```

The `new ArrayList<String>()` expression on the right-hand side does not make the `?` parameter of the **variable** `empty` become `String` in subsequent calls.

At the same time, `List<?>` **is not** `List<Object>`:

```java
List<String> strings = new ArrayList<>();
List<Object> objects = strings; // COMPILE ERROR
List<?> unknown = strings;     // Valid
```

`List<Object>` can accept any `Object` instance via `add`; `List<?>` does not allow that operation.

## 3. Type exception: `null` can be added

`null` is a special reference value compatible with every reference type, including the unknown element type represented by wildcard capture. Therefore:

```java
List<String> strings = new ArrayList<>();
List<?> unknown = strings;

unknown.add(null); // COMPILES; ArrayList allows null
System.out.println(strings); // [null]
```

Pay close attention to the difference between **being accepted by the compiler** and **succeeding at runtime**:

```java
List<?> unmodifiable = List.of("Java");
unmodifiable.add(null); // Compiles; throws UnsupportedOperationException
```

`List.of(...)` creates a list that does not support modification operations. Thus, although `null` is allowed at the type level, the `add` method still throws `UnsupportedOperationException`. A custom list implementation may also reject `null` according to its own contract.

**Do not** treat `add(null)` as a useful way to bypass wildcards. It does not let you add typed business data and can introduce unwanted `null` elements.

## 4. Limitations of `set(index, value)`

The `set(int index, E element)` method replaces the element at an existing position. It does not change the list's size, yet still places **a new value** into a position that must preserve the exact element type `E`. Therefore, the wildcard rule still applies.

```java
List<?> unknown = new ArrayList<String>(List.of("A", "B"));

unknown.set(0, "C"); // COMPILE ERROR
unknown.set(0, 99);  // COMPILE ERROR
unknown.set(0, null); // COMPILES
```

If the actual list supports `set` and allows `null`, the last replacement works:

```java
List<String> source = new ArrayList<>(List.of("A", "B"));
List<?> unknown = source;

Object previous = unknown.set(0, null);
System.out.println(previous); // A
System.out.println(source);   // [null, B]
```

`set` returns the old element. Through `List<?>`, we can receive that value as type `Object`, because every generic reference element type is a subtype of `Object`.

`set(index, null)` can still fail due to:

- **`IndexOutOfBoundsException`** if the index is out of valid range.
- **`UnsupportedOperationException`** if the list does not support `set` (for example, lists returned by `List.of`).
- **`NullPointerException` or other errors** if an implementation has a contract forbidding `null` or checks specific constraints.

You must not infer from a `List<?>` declaration that the list is definitely modifiable.

### 4.1. Why can `list.set(0, list.get(0))` also cause a compile error?

A surprising case:

```java
static void replaceWithItself(List<?> list) {
    list.set(0, list.get(0)); // COMPILE ERROR
}
```

The `get(0)` call reads an element. Yet in the expression above, Java does not guarantee the compiler uses **the same capture type** for the return value of `get` and the parameter type required by `set`; the result of `get` may be seen as a different capture type, so it cannot be assigned to `set`'s parameter. The programmer knowing both operations use the same list object is not enough for that syntax to be accepted.

If you need to read and write back an element with the same unknown type, use a **generic helper method** to capture that type once:

```java
static <T> void replaceWithItselfCaptured(List<T> list) {
    if (!list.isEmpty()) {
        list.set(0, list.get(0)); // Valid: both share T
    }
}

static void caller(List<?> values) {
    replaceWithItselfCaptured(values); // Wildcard capture at call site
}
```

This is an operation replacing an element with its own old value to illustrate the capture technique; it does not alter the data. The helper method can still throw `UnsupportedOperationException` if the actual list does not allow `set`.

## 5. Removing or swapping is a different group of operations from inserting new elements

`add(E)` and `set(int,E)` require **a value of element type E**. In contrast, `remove(int)`, `remove(Object)`, and `clear()` only remove existing data, so they do not require the caller to supply a new E. `Collections.swap(List<?>,i,j)` is also valid because the library uses a generic helper to preserve the same element type when swapping.

| Call via `List<?>` | Compiles? | Notes |
| --- | --- | --- |
| `get(0)`, `size()` | Yes | `get` requires a valid index. |
| `add("A")`, `set(0,"A")` | No | String is not guaranteed to be the wildcard's type. |
| `add(null)`, `set(0,null)` | Yes | Operation still depends on mutability/null contract. |
| `remove(0)`, `remove("A")` | Yes | One removes by index, the other by Object. |
| `clear()`, `Collections.reverse(list)` | Yes | Runtime list must support the required modification. |

```java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));
List<?> view = values;
Object removed = view.remove(1);
Collections.reverse(view);
System.out.println(removed + " / " + values); // B / [C, A]
```

These calls do not insert mistyped elements, yet they still mutate the data. The next section specifically distinguishes `ArrayList`, `Arrays.asList`, and `List.of` to explain why the same type-valid call can succeed or throw `UnsupportedOperationException`.

## 6. Distinguishing three common list types

| List | `add(null)` | `set(0, null)` | `remove(0)` |
| --- | --- | --- | --- |
| `new ArrayList<>(List.of("A"))` | Usually succeeds | Succeeds | Succeeds |
| `Arrays.asList("A")` | `UnsupportedOperationException` | Succeeds | `UnsupportedOperationException` |
| `List.of("A")` | `UnsupportedOperationException` | `UnsupportedOperationException` | `UnsupportedOperationException` |

All three cases can be assigned to a `List<?>` variable. They differ in the **modification contract of the concrete object**:

1. A regular `ArrayList` allows adding, replacing, removing, and accepts `null`.
2. `Arrays.asList` returns a **fixed-size** list backed by an underlying array: it allows `set` but forbids adding or removing elements that change the size.
3. `List.of` returns an **unmodifiable** list; it forbids `add`, `set`, `remove`, and disallows containing `null`.

Do not equate “invariance in generic type parameters” (*invariance*) with “unmodifiable data” (*unmodifiable/immutable collection*).

## 7. Complete Java 17+ example

Create the file `WildcardMutationDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class WildcardMutationDemo {
    // Helper keeps the same T while both reading and writing existing values.
    private static <T> void swap(List<T> items, int left, int right) {
        T first = items.get(left);
        items.set(left, items.get(right));
        items.set(right, first);
    }

    static void swapFirstTwo(List<?> items) {
        if (items.size() >= 2) {
            swap(items, 0, 1); // Java captures the type of '?' when calling helper.
        }
    }

    public static void main(String[] args) {
        List<String> words =
                new ArrayList<>(Arrays.asList("Java", "Generics", "List"));
        List<?> unknown = words;

        System.out.println("Read: " + unknown.get(0));

        Object old = unknown.set(1, null);
        System.out.println("Old: " + old);
        System.out.println("After set null: " + words);

        unknown.remove(1);
        System.out.println("After remove: " + words);

        swapFirstTwo(unknown);
        System.out.println("After swap: " + words);

        unknown.add(null);
        System.out.println("After add null: " + words);

        try {
            List<?> fixed = List.of("immutable");
            fixed.add(null);
        } catch (UnsupportedOperationException e) {
            System.out.println(
                    "Unmodifiable: " + e.getClass().getSimpleName());
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 WildcardMutationDemo.java
java WildcardMutationDemo
```

Result:

```text
Read: Java
Old: Generics
After set null: [Java, null, List]
After remove: [Java, List]
After swap: [List, Java]
After add null: [List, Java, null]
Unmodifiable: UnsupportedOperationException
```

Interpretation:

- `unknown.get(0)` reads `String` as `Object`; printing still displays the string's content.
- `set(1, null)` replaces `Generics` with `null`; the variable `old` retains the previous value.
- `remove(1)` removes the `null` element, leaving `[Java, List]`.
- The `swap` helper captures the element type as a single `T`, allowing two elements to be swapped without casting and without adding mistyped values.
- `add(null)` succeeds with `ArrayList`.
- `List.of` rejects `add` at runtime even though the `null` argument is valid for generics.

## 8. When you need to add or replace with a real value: choose a different API type

### 8.1. Exact element type is known: use `List<T>`

If a method must operate on strings, declare it explicitly:

```java
static void replaceFirst(List<String> list, String replacement) {
    if (!list.isEmpty()) {
        list.set(0, replacement);
    }
}
```

The method accepts only `List<String>` (and its implementations), so it can replace with `String`. The compiler checks the type of the new value.

### 8.2. Same unknown type: use a type parameter and wildcard capture

If a method must read an existing element and put it back into the list or swap two elements, use `<T>` to preserve the relationship between the value and the list:

```java
static <T> void rotateFirstTwo(List<T> list) {
    if (list.size() < 2) {
        return;
    }
    T first = list.get(0);
    list.set(0, list.get(1));
    list.set(1, first);
}
```

A `List<?>` variable can still be passed into this method because the compiler can capture the wildcard type for **the entire call**:

```java
List<?> list = new ArrayList<>(List.of(1, 2));
rotateFirstTwo(list); // Valid if the object supports set
```

Key point: `<T>` does not allow stuffing arbitrary types into the list; it forces **all positions using `T` to agree with each other**.

### 8.3. Want to add values of type `T`: use `? super T`

For a method that only accepts data for writing:

```java
static void appendText(List<? super String> destination) {
    destination.add("Java");
}
```

The method accepts `List<String>` and `List<Object>`, because both can hold a `String`. Conversely, `List<?>` does not guarantee this.

### 8.4. Want to read with an upper bound: use `? extends T`

```java
static double total(List<? extends Number> source) {
    double result = 0;
    for (Number number : source) {
        result += number.doubleValue();
    }
    return result;
}
```

`? extends Number` is useful for **reading** values as `Number`, yet still does not allow `source.add(1)` or `source.set(0, 1)`. An upper bound does not make the concrete element type known.

## 9. Common mistakes and how to handle them

| Misconception | Why it is wrong | How to handle it |
| --- | --- | --- |
| `List<?>` allows `add(Object)` | The actual element type may be narrower than `Object` | Use `List<Object>` when the object truly must hold any `Object`, or `? super T` to accept `T` |
| `List<?>` is always read-only | `remove`, `clear`, `set(..., null)`, and swapping can compile | Check the implementation's modification contract separately |
| `add(null)` always succeeds | `List.of` does not support modification; other implementations may reject `null` | Check the list contract; avoid inserting `null` unnecessarily |
| `set(index, x)` is allowed just because it does not change size | It still puts a new value `x` into a position with an unknown element type | Use `List<T>` or `List<? super T>` appropriately |
| `list.set(0, list.get(0))` is definitely valid on `List<?>` | Two wildcard uses can become incompatible captures | Move both read and write operations into a `<T>` helper |
| Casting `List<?>` to `List<String>` to add values | An unchecked cast does not prove the real list holds `String`; it can cause heap pollution | Design the API with the right type parameter from the start |
| `Collections.swap` works, so `list.add("x")` must also work | Swap only moves values already inside the same list; add inserts an external value | Distinguish rearranging existing elements from inserting new ones |

**Do not use raw types** (for example `List raw = unknown;`) as a way to bypass restrictions. Raw types bypass most generic checks at compile time, which can cause cast errors later when elements are read through a typed reference.

## 10. Self-check: compile or runtime error?

Predict the result of each **independent** snippet below, assuming `java.util.*` is already imported.

**A — Adding a concrete element**

```java
List<?> a = new ArrayList<String>();
a.add("X");
```

**B — Adding `null` to a modifiable list**

```java
List<?> b = new ArrayList<String>();
b.add(null);
System.out.println(b.size());
```

**C — Replacing with `null` on an unmodifiable list**

```java
List<?> c = List.of("X");
c.set(0, null);
```

**D — Swapping elements on a modifiable list**

```java
List<?> d = new ArrayList<>(List.of("X", "Y"));
Collections.swap(d, 0, 1);
System.out.println(d);
```

**E — Reading and passing directly to `set`**

```java
List<?> e = new ArrayList<>(List.of("X"));
e.set(0, e.get(0));
```

**Answers:**

- **A:** Does not compile; `String` is not guaranteed to be the element type of `List<?>`.
- **B:** Compiles and runs successfully with `ArrayList`; prints `1`.
- **C:** Compiles, but `List.of` throws `UnsupportedOperationException` when calling `set`.
- **D:** Compiles and runs successfully; prints `[Y, X]`.
- **E:** Does not compile because the wildcard capture in the `get` call does not unify with the parameter type required by `set`. A `<T>` helper can be used to ensure both positions share one type.

## 11. Summary

For `List<?>`, the compiler **does not accept inserting or replacing with a non-`null` value** because the element type is unknown. `add(null)` and `set(index, null)` are type-valid, yet are not guaranteed to succeed at runtime. Removing, clearing, and reordering elements can be type-valid; they still obey the actual mutability of the list object.

When you need to write real data, describe the type relationship explicitly with `List<T>`, `List<? super T>`, or a generic helper `<T>`. The wildcard `?` lets an API accept many list types while keeping Java's type-safety guarantees intact.