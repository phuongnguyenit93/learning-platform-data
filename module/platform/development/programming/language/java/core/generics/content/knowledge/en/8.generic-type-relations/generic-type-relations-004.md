# Generic Invariance and Array Covariance in Java

## 1. Objective and Context

In Java, `Integer` extends `Number`, yet the following two declarations do **not** follow the same assignment rules:

- `Integer[]` can be assigned to a variable of type `Number[]`: **arrays are covariant** with respect to reference element types.
- `List<Integer>` cannot be assigned to a variable of type `List<Number>`: **generics are invariant by default** with respect to type parameters.

Distinguishing these two rules helps prevent compile errors when designing APIs with `List<T>`, understand `ArrayStoreException`, and use `? extends` / `? super` for their intended purposes. This lesson examines **type relationships**; the `extends` keyword in a wildcard does not itself turn `List<Integer>` into `List<Number>`.

## 2. Background: Subtyping Relationships

Suppose `Integer` is a subtype of `Number`, denoted `Integer <: Number`. Then:

```java
Number n = Integer.valueOf(42); // Valid: Integer is a Number
Object o = n;                   // Valid: Number is an Object
```

However, the relationship between **element types** does not automatically determine the relationship between the types that contain them:

| Type expression | Valid subtyping relationship? | Reason |
| --- | --- | --- |
| `Integer <: Number` | Yes | Class inheritance |
| `Integer[] <: Number[]` | Yes | Covariance of reference arrays |
| `List<Integer> <: List<Number>` | No | Invariance of generic type parameters |
| `List<Integer> <: List<? extends Number>` | Yes | Upper-bounded wildcard accepts numeric lists |
| `List<Number> <: List<? super Integer>` | Yes | Lower-bounded wildcard accepts types that hold Integer |

The `<:` symbol in the table is notation used to explain subtyping relationships, not Java syntax.

## 3. Generic Invariance

For the same generic type, such as `List<T>`, Java does **not** treat `List<Integer>` as a subtype of `List<Number>`, nor does it treat the reverse direction as valid, even though `Integer` is a subtype of `Number`.

```java
import java.util.List;

List<Integer> integers = List.of(1, 2, 3);
List<Number> numbers = integers; // COMPILE ERROR: incompatible types
```

This is an intentional error from the type system. Suppose the assignment above were allowed:

```java
// HYPOTHETICAL (does not compile in Java):
List<Integer> integers = new ArrayList<>();
List<Number> numbers = integers;
numbers.add(3.14);                 // Double is also a Number
Integer value = integers.get(0);  // Cannot be safe if the element is Double
```

`List<Number>` allows adding `Double`, `Long`, or `Integer`. Conversely, a `List<Integer>` must keep only elements of type `Integer`. If the same object were viewed through both types above, writing through the `List<Number>` variable would break the contract of the `List<Integer>` variable. **Invariance prevents this risk at compile time.**

Two situations must be distinguished:

```java
List<Integer> a = new ArrayList<Integer>(); // Valid
List<Integer> b = new ArrayList<>();        // Valid: type inference
List<Number>  c = new ArrayList<Integer>(); // Invalid: different type arguments
```

`ArrayList<Integer>` is a `List<Integer>` because `ArrayList<T>` implements `List<T>` with the **same** `T`; that does not make `List<Integer>` become `List<Number>`.

To obtain an independent `List<Number>` from `Integer` elements, create a destination list and copy the values:

```java
List<Integer> integers = List.of(1, 2);
List<Number> numbers = new ArrayList<>(integers); // Valid: creates a different list
numbers.add(3.14);                                // Valid: destination list holds Number
```

This is **copying element references into a new container structure**, not casting between `List<Integer>` and `List<Number>`.

## 4. Array Covariance

For **reference** element types, if `Integer <: Number` then `Integer[] <: Number[]`. Therefore:

```java
Integer[] integers = {1, 2};
Number[] numbers = integers; // Valid at compile time
numbers[0] = 3;              // Valid: Integer stored in Integer[]
numbers[1] = 3.14;           // Compiles, but throws ArrayStoreException
```

The `numbers` variable has declared type `Number[]`, yet the actual array object created is `Integer[]`. The JVM still knows the **actual element type** of the array. When an element assignment occurs, the JVM checks whether the value is compatible with the actual element type. `Double` cannot reside in `Integer[]`, so the last statement throws `ArrayStoreException` at the moment of writing; earlier elements are not turned into `Double`.

Therefore, array covariance **does not guarantee that every write operation is statically safe**. Java accepts the array type assignment, while performing a runtime check to preserve type safety. Arrays existed before generics were added to Java; the covariance rule was kept for compatibility with existing language and API design.

Note the distinctions among array types:

- `String[]` can be viewed as `Object[]` because `String` is a reference subtype of `Object`.
- `int[]` is **not** a `Number[]` or `Object[]` because `int` is a primitive type. However, the `int[]` object itself can still be assigned to a variable of type `Object`.
- Assigning the wrong element into a reference array can cause `ArrayStoreException`; casting an array reference to the wrong array type can cause `ClassCastException`. These are two different operations and two different errors.

## 5. Why Do Generics and Arrays Behave Differently?

There are two core characteristics:

1. **Arrays carry element type information at runtime (reified)**. An object `new Integer[2]` knows its slots require `Integer`. The JVM checks on write.
2. **Most generic type argument information is erased during compilation (type erasure)**. At runtime, an `ArrayList<String>` object and an `ArrayList<Integer>` object generally use the same `ArrayList` class; the JVM does not have a per-element concrete type check on each add call analogous to an array store check.

With generics, the compiler proactively blocks assignments that could corrupt types early on. With reference arrays, the compiler allows the covariant relationship and the JVM can block an unsafe write at runtime.

You should not infer that **all** generic checks disappear. The compiler still inserts appropriate casts at use sites and the JVM still checks those inserted casts. Type erasure also does not mean that all uses of raw types or unchecked casts are safe.

## 6. Using Wildcards to Describe APIs with Multiple Element Types

Wildcards make type expressions more flexible without breaking the invariance rule of `List<T>`.

### 6.1. `? extends Number`: Accepting a Source for Reading

```java
List<Integer> integers = List.of(1, 2);
List<Double> doubles = List.of(1.5, 2.5);

List<? extends Number> first = integers; // Valid
List<? extends Number> second = doubles; // Valid

Number x = first.get(0); // Valid: read as Number
first.add(10);           // COMPILE ERROR
```

`List<? extends Number>` means a list whose element type is **an unknown type** within the `Number` family, such as `Integer` or `Double`. Reading elements as `Number` is safe; adding an `Integer` into a list that might actually be a `List<Double>` is not safe. Therefore, `add` does not accept ordinary element values; `add(null)` is a type-valid exception, though usually of no business value.

Example of a method that reads a sum:

```java
static double sum(List<? extends Number> values) {
    double result = 0;
    for (Number value : values) {
        result += value.doubleValue();
    }
    return result;
}
```

The method accepts `List<Integer>`, `List<Double>`, or `List<Number>` without requiring the caller to copy data. Because the result is `double`, you still need to be aware of `double` precision limits when handling currency or very large integers.

### 6.2. `? super Integer`: Accepting a Destination for Writing

```java
List<Number> numbers = new ArrayList<>();
List<? super Integer> destination = numbers;

destination.add(10);     // Valid: adds Integer
destination.add(20);     // Valid
Object item = destination.get(0); // Only guaranteed to be Object
```

The actual element type of `List<? super Integer>` may be `Integer`, `Number`, or `Object`. Any such list accepts an `Integer` value, whereas a value read from it cannot automatically be treated as `Integer` or `Number` because it could be a `List<Object>` holding other objects.

### 6.3. The PECS Rule and Copy Methods

**PECS = Producer Extends, Consumer Super**: a source producing elements to read uses `extends`; a destination receiving elements to write uses `super`.

```java
static <T> void appendAll(
        List<? super T> destination,
        List<? extends T> source) {
    for (T value : source) {
        destination.add(value);
    }
}
```

For example, `appendAll(List<Number>, List<Integer>)` is valid. This method **appends** to the end of the destination. Do not confuse it with `Collections.copy(destination, source)`: the library method **overwrites by index** and requires the destination list to already contain enough elements.

If an API **both reads and writes the same concrete type** (for instance, replacing or swapping values), using `List<T>` or a helper with an explicit type parameter is usually more appropriate than wildcards.

## 7. Complete, Runnable Java 17+ Example

Create the file `QuanHeKieuDemo.java` with the contents:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class QuanHeKieuDemo {
    static <T> void appendAll(
            List<? super T> destination,
            List<? extends T> source) {
        for (T value : source) {
            destination.add(value);
        }
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(10, 20);
        List<? extends Number> readable = integers;
        System.out.println("Extends read: " + readable.get(0));

        List<Number> numbers = new ArrayList<>();
        List<? super Integer> writable = numbers;
        writable.add(30);
        System.out.println("Super read: " + writable.get(0));

        appendAll(numbers, integers);
        System.out.println("Destination: " + numbers);

        Integer[] actual = {1, 2};
        Number[] view = actual; // Covariant array
        System.out.println("Array read: " + view[0]);

        try {
            view[0] = 3.5; // Double cannot be stored in Integer[]
        } catch (ArrayStoreException exception) {
            System.out.println(
                    "Array store blocked: " + exception.getClass().getSimpleName());
        }
        System.out.println("Array after: " + Arrays.toString(actual));

        List<?>[] genericViews = new List<?>[1];
        genericViews[0] = List.of("x");
        System.out.println("Unbounded wildcard: " + genericViews[0].get(0));
    }
}
```

Compile and run in the directory containing the file above:

```bash
javac -encoding UTF-8 QuanHeKieuDemo.java
java QuanHeKieuDemo
```

Exact output:

```text
Extends read: 10
Super read: 30
Destination: [30, 10, 20]
Array read: 1
Array store blocked: ArrayStoreException
Array after: [1, 2]
Unbounded wildcard: x
```

Step-by-step analysis: `readable` reads `Integer` as `Number`; `writable` adds `Integer` into a `List<Number>`; `appendAll` appends 10 and 20. The actual array is `Integer[]`, so writing `3.5` is blocked while `[1, 2]` remains intact. The final part illustrates an array holding lists with an unbounded wildcard.

## 8. Why Can't We Create Arrays of Concrete Generic Types?

The following declaration **does not compile**:

```java
List<String>[] words = new List<String>[2]; // generic array creation: invalid
```

Suppose creating it were valid. Due to erasure, the runtime element type cannot distinguish `List<String>` from `List<Integer>`. If the array reference were passed via `Object[]`, the element-store check would see the same raw type `List` and fail to detect the mismatch in the `String` type argument. That would break the type guarantee of `List<String>[]`. Therefore, Java forbids directly creating arrays with non-reifiable parameterized element types.

Conversely, the following case is **valid**:

```java
List<?>[] lists = new List<?>[2];
lists[0] = List.of("a");
lists[1] = List.of(1, 2);
Object first = lists[0].get(0);
```

`List<?>` is a type with an unbounded wildcard, which is among the **reifiable** types permitted as the element type of an array creation expression. However, when reading from a list via `List<?>`, the element type is only guaranteed to be `Object`; you cannot assert that the entire list holds `String` or `Integer`.

In applications, when needing a collection of lists, prefer `List<List<String>>` or an equivalent generic structure instead of generic arrays. Bypassing with raw types, unchecked casts, or `@SuppressWarnings("unchecked")` does not by itself make the data types safe.

## 9. Common Mistakes and How to Fix Them

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| Assigning `List<Integer>` to `List<Number>` | Compile error | If only reading, use `List<? extends Number>`; if needing an independent list, create `new ArrayList<Number>(integers)` |
| Assuming `List<? extends Number>` allows `add(1)` | Compile error | Use `List<? super Integer>` when the goal is to accept `Integer` |
| Reading `List<? super Integer>` directly as `Integer` | Compile error | Read as `Object`, or use a more precise type structure |
| Assuming `Number[] a = new Integer[2]` allows writing `Double` | `ArrayStoreException` at runtime | Create an actual `new Number[2]` array if needing to hold multiple kinds of `Number` |
| Creating `new List<String>[2]` | Compile error | Use `List<List<String>>`, or `List<?>[]` when such an array is truly needed |
| Using raw `List` to bypass invariance | Unchecked warning, risk of later `ClassCastException` | Keep type parameters and wildcards explicit |

In particular, `Arrays.asList(1, 2)` creates a fixed-size `List<Integer>`; changing the reference variable to a wildcard does not turn it into a `List<Number>` or into a list that allows adding elements. **Type relationships** and **structural mutability** of each list implementation are two independent concerns.

## 10. Self-Check

For each snippet, predict **whether it compiles**, and if it compiles, whether there is a runtime error:

```java
// A
List<? extends Number> a = List.of(1, 2);
Number n = a.get(0);

// B
List<Number> b = List.of(1, 2);

// C
Number[] c = new Integer[1];
c[0] = 1.5;

// D
List<? super Integer> d = new ArrayList<Object>();
d.add(7);
Object o = d.get(0);

// E
Object[] e = new int[2];
```

**Explanation and answers:**

- **A:** Valid, reads element as `Number`. `List.of(1, 2)` infers `List<Integer>`, which is accepted in the `? extends Number` position.
- **B:** Valid: the `List.of` call is inferred with type `Number` via **target typing** from the left-hand side; this differs from taking a variable that already has type `List<Integer>` and assigning it to `List<Number>`. The returned list is immutable in the sense of being **unmodifiable**, a concept distinct from the **invariance** of generic types.
- **C:** Compiles; writing a `Double` into an `Integer[]` object throws `ArrayStoreException`.
- **D:** Valid; `List<Object>` is a destination capable of accepting `Integer`, and reading through `? super Integer` only infers `Object`.
- **E:** Does not compile: `int[]` is not `Object[]`. You can write `Object e = new int[2];` if you need a reference to the array object itself.

### Takeaway

`List<S>` and `List<T>` remain invariant even when `S <: T`. Reference arrays `S[]` are covariant with `T[]`, yet writing the wrong element can be rejected by the JVM at runtime. When designing generic APIs, use `? extends T` to read from a source and `? super T` to write to a destination; use a fixed type parameter `T` when strict type relationships must be maintained in both directions.