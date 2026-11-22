# Using Exact Types When Preserving Read–Write Relationships in Java Generics

## 1. The design problem: a list that both provides and receives back the same data type

A familiar piece of advice when writing generic APIs is **PECS — Producer Extends, Consumer Super**:

- If a collection only **provides** values of type T, a `? extends T` signature is usually flexible.
- If a collection only **receives** values of type T, a `? super T` signature is usually flexible.
- However, when **the same parameter is both read from and written back to** and the program needs to preserve **an exact bidirectional type relationship**, a good choice may be **a single consistent type parameter T**, such as `List<T>`.

Example:

~~~java
static <T> T replaceFirst(List<T> values, T replacement) {
    return values.set(0, replacement);
}
~~~

This function does three things under **the same T**:

1. Accepts a `List<T>`.
2. Writes the `replacement` value of type T into the list.
3. Returns the previous T value provided by `List.set`.

If the caller uses `List<String>`, then T is String; if the caller uses `List<Integer>`, then T is Integer. No casting is needed, no external wildcard capture is needed, and the compiler verifies that the replacement value is compatible with the exact list passed in.

~~~java
List<String> words = new ArrayList<>(List.of("old", "other"));

String previous = replaceFirst(words, "new"); // "old"
~~~

If you try to write an integer into a list of strings:

~~~java
// replaceFirst(words, 99);
// Does not compile: no consistent T between List<String> and Integer.
~~~

This is the core example of **"using exact types when preserving read–write relationships"**. Not every wildcard is bad; rather, wildcards are a tool for expressing **one-way flexibility** or **an unknown type**, and cannot replace every constraint between reads and writes.

## 2. Defining "exact type" in a generic API

In this lesson, **exact type** means the signature keeps the same named type argument at the positions that need to be linked, such as `List<T>`, `T`, `UnaryOperator<T>`, or `Map<K,V>`. It does **not** mean a runtime object may only contain one exact class with no subclasses.

Example:

~~~java
List<Number> numbers = new ArrayList<>();
numbers.add(Integer.valueOf(1));
numbers.add(Double.valueOf(2.5));
~~~

This is still a valid `List<Number>`; Number is a reference type that both Integer and Double can be used for wherever Number is expected.

Be careful to distinguish:

- `List<String>`: the type argument is already fixed to String.
- `List<T>` in a generic method: the type argument is determined by the caller and compiler at the call site; **positions sharing the same T must be consistent**.
- `List<?>`: a list with an **unknown** type argument, which cannot automatically be treated as String or Number.
- `List<? extends Number>`: the type argument is **an unknown subtype** of Number.
- `List<? super Integer>`: the type argument is **an unknown supertype** of Integer.

**Invariance** of Java generics is crucial:

~~~java
List<Integer> ints = new ArrayList<>();

// List<Number> invalid = ints; // Does not compile.
List<? extends Number> readable = ints; // Valid.
~~~

Even though Integer extends Number, `List<Integer>` is not automatically a subtype of `List<Number>`. If that were allowed, code could write a Double into a list originally promised to hold Integers.

## 3. Three signature kinds and read–write capabilities

| Parameter kind | Safe to read as | Safe to write | Use when |
| --- | --- | --- | --- |
| `List<T>` | T | A T-compatible value | The same T is needed in both directions. |
| `List<? extends T>` | T | Cannot add an arbitrary T | Only reading values from a producer is needed. |
| `List<? super T>` | Object (not guaranteed to read as T) | T and compatible subtypes | Only supplying T values to a consumer is needed. |
| `List<?>` | Object | Cannot add an arbitrary non-null value | Type argument is unknown; generic reading/processing is needed. |
| `List<Object>` | Object | Any Object | The list is genuinely declared to hold Object. |

Clarifying "cannot write" in the table: the compiler prevents writing **an arbitrary T value** into a collection with an unknown captured type argument. There are still valid operations such as `add(null)` statically, or using a **wildcard capture helper** to move values already read from that same collection. So this should not be understood as "no mutating operation can exist at all."

Beyond static types, the collection must **support modification**: `List.of(...)`, `List.copyOf(...)`, and lists from `Stream.toList()` do not allow standard mutating operations. A `List<T>` signature does not guarantee `set`, `add`, or `replaceAll` will succeed at runtime if the list implementation does not support them.

## 4. Read-only: why ? extends T is a good choice

Suppose you need to sum a list of numbers:

~~~java
static double sum(List<? extends Number> values) {
    double total = 0;
    for (Number value : values) {
        total += value.doubleValue();
    }
    return total;
}
~~~

You can call:

~~~java
double a = sum(List.of(1, 2, 3));       // Integer elements.
double b = sum(List.of(1.5, 2.5));      // Double elements.
~~~

`? extends Number` allows the list to have type argument Number, Integer, Double, or a compatible subtype. When reading, each element **can at least be viewed as Number**.

However, you cannot do:

~~~java
static void invalid(List<? extends Number> values) {
    // values.add(Integer.valueOf(5)); // Does not compile.
    // values.add(Double.valueOf(5));  // Does not compile.
}
~~~

Because the compiler does not know whether the collection's actual type argument is Integer, Double, or another subtype. The fact that "Integer is a Number" is not enough to prove Integer can be added to every `List<? extends Number>`.

**Rule:** if truly read-only, accept `List<? extends Number>` so callers do not have to copy List<Integer> into List<Number>. But if the method intends to **modify the numbers themselves** and return the same type argument, a different design is needed.

## 5. Write-only: why ? super T is a good choice

Suppose you want to insert new Integers into a destination:

~~~java
static void appendIds(List<? super Integer> target) {
    target.add(10);
    target.add(20);
}
~~~

You can call it with:

~~~java
List<Integer> integerTarget = new ArrayList<>();
List<Number> numberTarget = new ArrayList<>();
List<Object> objectTarget = new ArrayList<>();

appendIds(integerTarget);
appendIds(numberTarget);
appendIds(objectTarget);
~~~

All destinations can accept an Integer. However, **reading from `List<? super Integer>` only guarantees Object**:

~~~java
List<? super Integer> target = new ArrayList<Number>();
target.add(42);

Object value = target.get(0); // Valid.
// Integer invalid = target.get(0); // Does not compile.
~~~

Reason: the actual type argument could be Integer, Number, or Object. The compiler cannot promise that a value read from List<Object> is always an Integer.

Do not cast arbitrarily to Integer if data might be added from other sources. If you need to read back as Integer or preserve the exact element type, a signature with a type variable T or a verified invariant is more appropriate.

## 6. When the same List both receives T and returns T: choose List<T>

An update API may return **the value before modification**:

~~~java
static <T> T replaceFirst(List<T> values, T replacement) {
    return values.set(0, replacement);
}
~~~

Try three design variants:

~~~java
// Read-only variant:
static Number first(List<? extends Number> values) {
    return values.get(0);
}

// Write-only variant:
static void append(List<? super Integer> values, Integer x) {
    values.add(x);
}

// Variant needing same-type read–write:
static <T> T replaceFirst(List<T> values, T replacement) {
    return values.set(0, replacement);
}
~~~

`first` uses an upper bounded wildcard because retrieving a Number suffices. `append` uses a lower bounded wildcard because it only pushes an Integer in. `replaceFirst` needs a consistent T for the list, the new element, and the return value.

In generic code, a **named type parameter** is not merely a longer way to write a wildcard. It lets you model **equality relationships between type positions** in the same call.

### 6.1. Why not use List<? extends T> for updates?

Suppose:

~~~java
static <T> void invalid(
        List<? extends T> values, T replacement) {
    // values.set(0, replacement); // Does not compile.
}
~~~

Even though replacement has type T, the *captured* type argument of `values` could be a narrower subtype of T. Thus the compiler cannot allow writing a general T into that list.

### 6.2. Why not use List<? super T> for output as well?

~~~java
static <T> T invalidRead(List<? super T> values) {
    // return values.get(0); // Does not compile.
    throw new UnsupportedOperationException();
}
~~~

The snippet above only illustrates typing. Calling `get` on this kind of list can only be read as Object. Throwing UnsupportedOperationException in the example is a placeholder for testing the signature and **not a recommended implementation** for a real API.

Fix the design with `List<T>` if both reading and writing the same T are needed:

~~~java
static <T> T takeAndReplace(List<T> list, T replacement) {
    return list.set(0, replacement);
}
~~~

Another case is separating the read and write paths into **two parameters** (producer/consumer) if the problem actually only transfers in one direction.

## 7. An API modifying multiple elements: UnaryOperator<T>

Suppose you want to transform each element of a list **in place**, ensuring the mapper returns the same T:

~~~java
static <T> void editAll(
        List<T> values, UnaryOperator<T> editor) {
    values.replaceAll(editor);
}
~~~

`UnaryOperator<T>` is a specialization of `Function<T,T>`. It takes T and returns T, fitting the **read → transform → write same type** pattern well.

Usage:

~~~java
List<String> words = new ArrayList<>(List.of("hello", "world"));

editAll(words, String::toUpperCase);
System.out.println(words); // [HELLO, WORLD]
~~~

Java's `List.replaceAll` signature defines a `UnaryOperator<E>` matching the list's element type E. The compiler ensures the mapper does not suddenly turn a List<String> into a list of Integers.

### 7.1. Why can't Function<T,R> replace UnaryOperator<T> in this situation?

A `Function<String,Integer>` turns String into Integer. If you want to **replace elements inside the List<String> itself**, the Integer result cannot be stored back while still keeping `List<String>`.

~~~java
Function<String, Integer> length = String::length;

// List<String> words = ...
// words.replaceAll(length); // Does not compile.
~~~

If the business logic wants to produce a new list type, create a **new List<R>** via `Stream.map` or a non-mutating transformation method. Do not use unchecked casts to turn a List<String> into a List<Integer> on the same object.

## 8. Swapping between two lists: the T relationship must be consistent

When exchanging elements between **two Lists**, both inputs both provide and receive back elements of type T:

~~~java
static <T> void swapFirst(List<T> left, List<T> right) {
    T oldLeft = left.get(0);
    left.set(0, right.get(0));
    right.set(0, oldLeft);
}
~~~

Valid call:

~~~java
List<String> left = new ArrayList<>(List.of("A"));
List<String> right = new ArrayList<>(List.of("B"));

swapFirst(left, right); // left holds B, right holds A.
~~~

However:

~~~java
List<String> words = new ArrayList<>(List.of("A"));
List<Integer> codes = new ArrayList<>(List.of(1));

// swapFirst(words, codes); // Does not compile.
~~~

The compiler cannot find **one unified T** for both `List<String>` and `List<Integer>`. If allowed, the method could write an Integer into List<String> and a String into List<Integer>, breaking the type promise.

This is an example where two `List<? extends Object>` parameters would be **too weak**: both lists would be accepted for reading Object, yet there is no guarantee the two captured element types can be written across to each other.

### 8.1. "Same T" is stricter than "both are subtypes of Number"

~~~java
List<Integer> ints = new ArrayList<>(List.of(1));
List<Double> doubles = new ArrayList<>(List.of(2.5));

// swapFirst(ints, doubles); // Does not compile.
~~~

Even though Integer and Double both extend Number, there is no safe swap between those two lists under their declared type arguments.

If the business logic truly needs a mixed Number list, the caller can proactively create two `List<Number>` from the start. But you should not alter the view type of List<Integer> with an unchecked cast just to make the call accepted.

## 9. One-way copy is completely different from two-way swap

For **one-way data transfer**, do not force both lists to have the exact same type argument if that needlessly restricts callers.

A flexible signature:

~~~java
static <T> void copyForward(
        List<? extends T> source,
        List<? super T> target) {

    for (T value : source) {
        target.add(value);
    }
}
~~~

Explanation:
- Source **produces** T → `? extends T`.
- Target **receives** T → `? super T`.
- The method does not read target as T to write back into source, so the two element types do not need to be equal.

Example:

~~~java
List<Integer> source = List.of(7, 8);
List<Number> destination = new ArrayList<>();

copyForward(source, destination);

System.out.println(destination); // [7, 8]
~~~

`List<Integer>` can serve as producer for T = Number, and `List<Number>` receives Number. For a one-way transfer method, a PECS signature is usually semantically sound and more reusable than `<T> void copy(List<T>,List<T>)`.

### 9.1. Comparison with Collections.copy

The standard library also has the signature:

~~~java
public static <T> void copy(
        List<? super T> dest,
        List<? extends T> src);
~~~

In `Collections.copy`, the destination comes **before** the source; the meaning of the type bounds remains as above.

**Very important behavioral note:** `Collections.copy` replaces elements by index and does not automatically grow the list. Destination must have size **at least equal to source**, otherwise it throws IndexOutOfBoundsException. Meanwhile, `copyForward` in the example above uses `add` to append data to the end of a mutable list.

Thus two methods with similar PECS signatures do not necessarily share the same behavior regarding size and storage positions.

## 10. Wildcard capture: modifying inside a List<?> without knowing T

When you only have:

~~~java
List<?> values;
~~~

you cannot arbitrarily add a String/Integer because the actual element type is unknown. Yet sometimes the task **does not need to know that type**, only to move element positions **within the same list**.

Example swapping two elements:

~~~java
static void swapUnknown(List<?> values) {
    swapCaptured(values);
}

private static <T> void swapCaptured(List<T> values) {
    T first = values.get(0);
    values.set(0, values.get(1));
    values.set(1, first);
}
~~~

**This is the wildcard capture helper pattern**:
1. The public method takes List<?> so callers do not need to know the element type.
2. The compiler can capture the wildcard into a temporary type variable for **the same object** when calling the helper.
3. Inside the helper, all reads/writes use **the same T**, so swapping values already read from the list remains type-safe.
4. No arbitrary new external T value is introduced into the list.
5. The list must be mutable and have enough elements, otherwise UnsupportedOperationException/IndexOutOfBoundsException may be thrown.

Usage:

~~~java
List<Integer> codes = new ArrayList<>(List.of(1, 2));
swapUnknown(codes);
System.out.println(codes); // [2, 1]
~~~

This shows that saying "a wildcard list can never be written to" is an oversimplification. **With a helper that has captured the same unknown type**, an internal operation that does not alter the element type can still be safe.

### 10.1. Why doesn't capture solve swapping between two wildcard lists?

Suppose:

~~~java
static void invalid(List<?> first, List<?> second) {
    // Cannot simply read an element from first and set it into second
    // because the two wildcards may be two different captured types.
}
~~~

`first` could be List<String>, and `second` could be List<Integer>. The fact that both use `?` does not prove they share the same element type.

A helper with **one** T applied to the same list enables internal swapping. But to safely swap **between two lists**, a stronger type relationship is needed in the public API, such as `<T> void swapFirst(List<T>, List<T>)`.

## 11. Complete, verified Java 17+ example

Save the following content as **ExactTypeDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.UnaryOperator;

public class ExactTypeDemo {
    static <T> T replaceFirst(
            List<T> values, T replacement) {
        return values.set(0, replacement);
    }

    static <T> void editAll(
            List<T> values, UnaryOperator<T> editor) {
        values.replaceAll(editor);
    }

    static <T> void swapFirst(
            List<T> left, List<T> right) {
        T oldLeft = left.get(0);
        left.set(0, right.get(0));
        right.set(0, oldLeft);
    }

    static <T> void copyForward(
            List<? extends T> source, List<? super T> target) {
        for (T value : source) {
            target.add(value);
        }
    }

    static void swapUnknown(List<?> values) {
        swapCaptured(values);
    }

    private static <T> void swapCaptured(List<T> values) {
        T first = values.get(0);
        values.set(0, values.get(1));
        values.set(1, first);
    }

    public static void main(String[] args) {
        List<String> words =
                new ArrayList<>(List.of("old", "middle"));

        System.out.println(
                "previous=" + replaceFirst(words, "new")
        );

        editAll(words, String::toUpperCase);
        System.out.println("edited=" + words);

        List<String> left =
                new ArrayList<>(List.of("A"));
        List<String> right =
                new ArrayList<>(List.of("B"));

        swapFirst(left, right);
        System.out.println(
                "swapped=" + left + "/" + right
        );

        List<Integer> codes =
                new ArrayList<>(List.of(1, 2));

        swapUnknown(codes);
        System.out.println("capture=" + codes);

        List<Integer> source = List.of(7, 8);
        List<Number> target = new ArrayList<>();

        copyForward(source, target);
        target.add(3.5);
        System.out.println("copied=" + target);

        List<? extends Number> producer = source;
        Number n = producer.get(0);
        System.out.println("read=" + n);

        List<? super Integer> consumer = target;
        consumer.add(9);

        Object item = consumer.get(0);
        System.out.println("written=" + target);
        System.out.println(
                "readBackType=" +
                item.getClass().getSimpleName()
        );
    }
}
~~~

Compile with a JDK supporting Java 17:

~~~bash
javac --release 17 -Xlint:all ExactTypeDemo.java
java ExactTypeDemo
~~~

**Exact stdout:**

~~~text
previous=old
edited=[NEW, MIDDLE]
swapped=[B]/[A]
capture=[2, 1]
copied=[7, 8, 3.5]
read=7
written=[7, 8, 3.5, 9]
readBackType=Integer
~~~

### 11.1. Explanation of each result

**`previous=old`**: `replaceFirst` both takes a new String and returns the old String from the same List<String>. The generic method preserves the T relationship across the list, the new value, and the return type.

**`edited=[NEW, MIDDLE]`**: `UnaryOperator<String>` reads String and returns String; List.replaceAll can write the result back into the exact same list.

**`swapped=[B]/[A]`**: two List<String> instances share the same T and can therefore exchange values in both directions.

**`capture=[2, 1]`**: the public method takes List<?> and the helper captures the type argument internally to swap two values of the same type already read from that same list.

**`copied=[7, 8, 3.5]`**: List<Integer> supplies Integers to List<Number> via producer extends / consumer super. Afterward, the destination can add a Double because its actual type argument is Number.

**`read=7`**: `List<? extends Number>` allows safely reading a Number from List<Integer>.

**`written=[7, 8, 3.5, 9]`**: `List<? super Integer>` allows writing an Integer into a List<Number>.

**`readBackType=Integer`**: the variable read from the consumer wildcard has static type Object; at runtime the specific object at index 0 is Integer, but that **does not change the read contract** of `List<? super Integer>` into Integer.

### 11.2. Runtime conditions of the example

All write operations use a mutable `ArrayList`. If `List.of(...)` is passed as the target of `set`, `replaceAll`, or `add`, the method may throw UnsupportedOperationException even though **it compiles completely validly**.

`replaceFirst`, `swapFirst`, and `swapCaptured` also assume the list has elements at the accessed indices. If the list is empty or has only one element during a two-position swap, IndexOutOfBoundsException may be thrown. These are **data conditions**, not generic type argument issues.

Unchecked casts should not be used to bypass those conditions: a cast cannot turn an immutable list into a mutable one or conjure nonexistent elements.

## 12. Code snippets that intentionally fail to compile

The following examples are written to **test type rules**; do not merge them into the runnable class above if you want to run the complete program.

### 12.1. Replacing with an Integer in List<String>

~~~java
List<String> words = new ArrayList<>(List.of("A"));

// replaceFirst(words, 42);
// Error: no consistent T between List<String> and Integer.
~~~

### 12.2. Swapping List<String> and List<Integer>

~~~java
List<String> names = new ArrayList<>(List.of("A"));
List<Integer> ids = new ArrayList<>(List.of(1));

// swapFirst(names, ids);
// Inference error: T has incompatible equality constraints.
~~~

### 12.3. Writing through extends

~~~java
List<? extends Number> source = List.of(1, 2);

// source.add(3);
// Cannot add an arbitrary Number/Integer into a captured subtype.
~~~

### 12.4. Reading as T from super

~~~java
List<? super Integer> sink = new ArrayList<Number>();

// Integer value = sink.get(0);
// Does not compile: the result only has safe type Object.
~~~

Careful: `sink.get(0)` could also throw IndexOutOfBoundsException if the destination has no elements yet; the compile error here happens **before runtime is reached** due to a type mismatch.

### 12.5. Writing a mapper returning a different type into the original List

~~~java
List<String> names = new ArrayList<>(List.of("A"));
Function<String, Integer> toLength = String::length;

// names.replaceAll(toLength);
// Invalid: requires UnaryOperator<String>, not Function<String,Integer>.
~~~

These examples demonstrate the compiler preventing **loss of type relationships** without needing to run the program. Do not fix them by casting to raw List and writing the wrong element type.

## 13. Using exact types for Map<K,V> when reading and updating values

Similarly to `List<T>`, a `Map<K,V>` has a relationship among:
- Key type `K`.
- Value type `V` read from the map.
- Value type `V` written back into the map.

Example:

~~~java
static <K, V> V replaceValue(
        Map<K, V> map, K key, V replacement) {
    return map.put(key, replacement);
}
~~~

If the caller has a `Map<String,Integer>`, the method only accepts Integer-compatible values; `Map<String,Number>` can accept Integer or Double under the Number contract.

For updating a value based on its previous value:

~~~java
static <K, V> void editValue(
        Map<K, V> map, K key, UnaryOperator<V> change) {

    if (!map.containsKey(key)) {
        return;
    }

    V oldValue = map.get(key);
    map.put(key, change.apply(oldValue));
}
~~~

This snippet is written as a **standalone method fragment** and requires `import java.util.Map` and `import java.util.function.UnaryOperator`. It updates the value with the same V. If the map currently holds a key mapped to a null value, `oldValue` is null and `change` must handle null itself; if the map is immutable, `put` may be unsupported.

### 13.1. Why not overuse Map<? extends K, ? extends V>?

A map viewed through producer wildcards:

~~~java
Map<? extends String, ? extends Number> view = someMap;
~~~

can allow reading data as String/Number in appropriate positions, yet does not permit updating with an arbitrary Number value because the actual value type might be Integer, Double, or another Number subtype.

With lower bounds, you might write a compatible V, yet reading back is not guaranteed to yield V. If an API **genuinely updates the exact V value of Map<K,V> and returns the old V**, named type parameters usually express the relationship better.

If the task is a **one-way copy of entries** from one source map to another destination map, wildcards can be designed accordingly; there is no need to make every method invariant when no bidirectional read–write relationship needs to be preserved.

## 14. Exact comparison: List<T>, List<? extends T>, List<? super T>

Three signatures share the same letter T yet do not share the same semantics.

~~~java
static <T> void exact(List<T> list, T value) {
    list.add(value);
}

static <T> T produce(List<? extends T> list) {
    return list.get(0);
}

static <T> void consume(List<? super T> list, T value) {
    list.add(value);
}
~~~

In `exact`:
- One T is inferred from all constraints of the call.
- The list and value are bound to the same type argument T.
- Code can read from the list as T when needed.

In `produce`:
- The list has an unknown subtype of T.
- The method only uses values read out as T.
- An arbitrary T value cannot be added back.

In `consume`:
- The list has an unknown supertype of T.
- The method can write a T value.
- When reading, only Object is guaranteed.

Key point: **PECS determines wildcard placement based on role**, whereas **named T determines shared constraints across type positions**. They complement rather than exclude each other.

## 15. When is a wildcard signature more flexible, and when is it too weak?

### 15.1. Wildcard is more flexible: only one-way transfer is needed

~~~java
static <T> void appendAll(
        Collection<? extends T> source,
        Collection<? super T> target) {
    for (T element : source) {
        target.add(element);
    }
}
~~~

`Collection<Integer>` can transfer into `Collection<Number>`. If both parameters used `Collection<T>`, callers would have to satisfy a stricter equality constraint and might be rejected even though one-way data movement is completely safe.

### 15.2. Wildcard is too weak: bidirectional exchange is needed

~~~java
static <T> void exchange(List<T> a, List<T> b) {
    T first = a.get(0);
    a.set(0, b.get(0));
    b.set(0, first);
}
~~~

You cannot carelessly replace both parameters with `List<? extends T>` and keep the logic, because the two lists could hold different captured subtypes.

### 15.3. No type parameter needed if only one position

If you only need to accept a list of unknown type and print its element count:

~~~java
static int sizeOf(List<?> list) {
    return list.size();
}
~~~

There is no relationship across type positions to name, so `<?>` is usually cleaner and clearer:

~~~java
static <T> int sizeOfOverGeneric(List<T> list) {
    return list.size();
}
~~~

The second method is still valid, yet the type parameter T adds no type-relationship value if neither the implementation nor the API uses T anywhere else. **Do not add a type parameter just to avoid a wildcard**; use it when positions genuinely need to be connected.

## 16. Notes on method references and read–write Function types

An API accepting a mapper to **modify List<T> in place** typically wants:

~~~java
static <T> void modify(
        List<T> values, UnaryOperator<T> mapper) {
    values.replaceAll(mapper);
}
~~~

An API creating a new result list may want:

~~~java
static <T, R> List<R> transform(
        List<? extends T> input,
        Function<? super T, ? extends R> mapper) {

    List<R> output = new ArrayList<>();
    for (T item : input) {
        output.add(mapper.apply(item));
    }
    return output;
}
~~~

In the second function:
- Input is **read-only** → `List<? extends T>`.
- Mapper accepts T and returns R (or a compatible subtype).
- Output is a **new List<R>**, without forcing it back into List<T>.
- Two type parameters T and R clearly express that **input and output may differ in type**.

Usage:

~~~java
List<Integer> lengths = transform(
        List.of("Java", "Go"),
        String::length
); // [4, 2]
~~~

If the original list and original element type must be preserved, use an invariant API with UnaryOperator<T>; if genuinely converting to a new result type, use a generic Function<T,R> and create a separate R container.

## 17. Invariance does not mean subtype objects are forbidden

A misconception:

> "List<T> is an exact type, meaning it only accepts elements whose runtime class matches T identically."

False. With `T = Number`:

~~~java
List<Number> values = new ArrayList<>();
values.add(Integer.valueOf(4));
values.add(Double.valueOf(1.5));
~~~

The two objects have different runtime classes, yet both are compatible with **Number at compile time**.

What is disallowed is **replacing the collection's type argument** with a subtype and then using it as a collection holding the supertype:

~~~java
List<Integer> integers = new ArrayList<>();
// List<Number> asNumbers = integers; // Does not compile.
~~~

The meaning of invariance is that a subtype relationship between **List<Integer> and List<Number>** is not automatically inherited from Integer <: Number. It does not stop `List<Number>` from holding instances of subclasses of Number.

## 18. Avoid bypassing typing with raw casts or unchecked casts

An obvious mistake:

~~~java
List<Integer> integers = new ArrayList<>(List.of(1, 2));

// Do not do this:
List raw = integers;
raw.add("text");
~~~

If the `integers` alias reads the element "text" as Integer, it may throw ClassCastException. The purpose of a generic method with the same T is **to leave no path for inserting the wrong type argument into a data structure**.

Do not use:

~~~java
// List<Number> forged = (List<Number>) (List<?>) integers;
~~~

to bypass invariance when implementing a two-way swap/copy. Even if an unchecked cast is permitted by the compiler at a warning-suppressed site, it does not turn the collection into a different runtime kind, and does not guarantee data stays well-typed under write operations.

If the current API demands invariance while the business case only needs a one-way copy, **change the signature to PECS**. If two-way read/write is genuinely needed, **change the data structure** so both share the same type argument from creation, or define a clear conversion rule that creates a new object.

## 19. Implementation exceptions and data policies

A valid generic signature does not mean every operation succeeds at runtime.

### 19.1. Unmodifiable lists

~~~java
List<String> fixed = List.of("A");

// replaceFirst(fixed, "B");
// Runtime UnsupportedOperationException when calling set.
~~~

To modify, create a mutable copy:

~~~java
List<String> mutable = new ArrayList<>(fixed);
replaceFirst(mutable, "B");
~~~

### 19.2. Invalid indices

~~~java
List<String> empty = new ArrayList<>();

// replaceFirst(empty, "A");
// Runtime IndexOutOfBoundsException.
~~~

Production code should check `isEmpty()`, specify errors clearly, or choose an API not tied to a fixed index.

### 19.3. Null policy

Java generics do not forbid nulls by themselves. Some List implementations accept null, while factory methods such as `List.of` and `List.copyOf` reject null by contract. If an API wants to forbid nulls, it can require `Objects.requireNonNull` and document that policy clearly.

### 19.4. Side effects and thread safety

`List<T>` does not make a list thread-safe on its own. If multiple threads call `swapFirst`, `editAll`, or `replaceFirst` on the same mutable lists without synchronization, race conditions or inconsistent state may occur. In concurrent processing, use proper synchronization, concurrency-friendly data structures, or immutable/functional designs.

## 20. API signature selection table

| Practical goal | Suggested signature | Reason |
| --- | --- | --- |
| Only count elements | `size(List<?>)` | No need to know T. |
| Only read numbers | `sum(List<? extends Number>)` | Accepts List<Integer>, List<Double>, List<Number>. |
| Only append Integers | `append(List<? super Integer>)` | Accepts List<Integer>, Number, Object targets. |
| Replace an element and return old element | `<T> T replace(List<T>, T)` | Read and write the same T. |
| Edit all elements in place | `<T> void edit(List<T>, UnaryOperator<T>)` | T→T and writes back into List<T>. |
| Swap two lists with the same type argument | `<T> void swap(List<T>, List<T>)` | Guarantees the same T in both directions. |
| Swap inside one list of unknown T | `swap(List<?>)` + capture helper | Only swaps positions of values with the same captured T. |
| Copy from producer to consumer | `<T> copy(List<? extends T>, List<? super T>)` | Does not force both type arguments to be identical. |
| Turn T into R and create new result | `<T,R> List<R> map(List<? extends T>, Function<? super T,? extends R>)` | Allows changing data types. |
| Update map and return old V value | `<K,V> V replace(Map<K,V>,K,V)` | Preserves key/value relationship for both reading and writing. |

These are **role-based signature suggestions**, not a claim that every method in the world has exactly one shape. Choose according to data invariants, mutation needs, and how much flexibility callers require.

## 21. Generics API review checklist

1. **Clarify data flow direction**: does the collection only produce values, only consume values, or both?
2. **If read-only**, consider `? extends T` to accept subtype producers.
3. **If write-only**, consider `? super T` to accept supertype consumers.
4. **If same-type read–write is needed**, use a consistent **named type parameter T** across the collection, input values, mapper, and output.
5. **If two collections interact**, determine whether it is copy or exchange; one-way may use PECS, two-way may need the same T.
6. **If T is only used in one position**, check whether `<?>` can replace a pointless type parameter T.
7. **Do not treat List<Object> and List<?> as identical**: List<Object> accepts Object on writes; List<?> holds an unknown element type.
8. **When a wildcard needs internal manipulation**, consider a capture helper and ensure two different unknown captures are not mixed.
9. **Avoid unchecked casts and raw types** to break invariance or fool the compiler.
10. **Check mutability/indices/nulls**, because type safety does not guarantee the List operation is actually supported.
11. **Avoid unsynchronized shared mutable state**, especially in methods modifying multiple collections.
12. **Use UnaryOperator<T> for in-place transforms**, Function<T,R> for transforms that may change types and return a new container.
13. **Do not overuse type parameters to create artificial complexity**: exact when preserving a relationship is required; wildcard when only one-way flexibility is needed.
14. **Compile with the target Java release** and test both valid and invalid cases to verify the compile-time contract.

## 22. Self-check questions

**1.** Why does `List<? extends Number>` allow reading Number but forbid adding an arbitrary Integer?

**Answer:** The actual element type could be an unknown Number subtype (such as Double), so a new Integer is not guaranteed safe for all possibilities.

**2.** Why does `List<? super Integer>` accept Integer, yet `get` can only be used as Object?

**Answer:** The actual type argument could be Integer, Number, or Object; the compiler does not know that every element read is an Integer.

**3.** Why is `<T> T replaceFirst(List<T>,T)` better than two wildcards for an update task?

**Answer:** The same T links the list type, the replacement, and the return value; the method needs to both write and read the exact declared type.

**4.** Can `List<Integer>` be assigned to `List<Number>`?

**Answer:** No. Java generic types are generally invariant; if assignment were allowed, a Double could be added to a list meant for Integers.

**5.** Can two List<String> instances be used with `<T> void swapFirst(List<T>,List<T>)`?

**Answer:** Yes. The compiler chooses T as String and every swapped value preserves its type.

**6.** Can List<String> and List<Integer> be swapped using that method?

**Answer:** No. The compiler cannot find a single consistent T because the two parameterized list types are invariant.

**7.** Why can `copyForward(List<? extends T>,List<? super T>)` accept List<Integer> and List<Number>?

**Answer:** One-way data flow: source produces Integer used as Number, target receives Number; there is no requirement to write Number back into List<Integer>.

**8.** Can `List<?>` swap two elements inside itself?

**Answer:** Yes, if the list is mutable, via a generic helper to capture the unknown element type and read/write values taken from that same list. An external value of arbitrary type cannot be added directly.

**9.** Why can't two different `List<?>` instances automatically swap elements?

**Answer:** The two wildcards may be two different captured types, such as String and Integer; there is no bidirectional guarantee.

**10.** Why is `UnaryOperator<T>` appropriate when using `List.replaceAll`?

**Answer:** UnaryOperator takes T and returns T, matching taking an element T and writing it back into the same List<T>.

**11.** When turning String into Integer and returning a new list, how should the API be designed?

**Answer:** Use `Function<? super T,? extends R>` to produce R and a new `List<R>`; do not turn the original List<String> into List<Integer> with an unchecked cast.

**12.** Does `List<T>` guarantee that `set` can be called?

**Answer:** No. List.of and immutable/unmodifiable implementations can throw UnsupportedOperationException at runtime; type parameters do not describe mutability.

**13.** In Map<K,V>, if you read a value V, apply UnaryOperator<V>, and put it back, what type should be used?

**Answer:** `Map<K,V>` with the same type variable V at both read and write sites; it keeps the value type consistent.

**14.** If a method only returns `list.size()`, is `<T>` needed?

**Answer:** Usually not. `List<?>` is enough because there is no T relationship across multiple positions to express.

**15.** If the compiler blocks a write into `List<? extends T>`, should you fix it with a raw cast?

**Answer:** No. Check whether the method needs a named T for a read–write relationship, or needs a new structure/PECS to express the right data direction. Unchecked casts can cause heap pollution.

## 23. Remember

**Place wildcards according to data direction; place named type parameters according to relationships that must be preserved.**

~~~text
One-way read:     List<? extends T> ────→ T
One-way write:    T ────→ List<? super T>

Read then write back the same type:
                  List<T> ────→ T ──transform──→ T ────→ List<T>

Two-way swap:
                  List<T> ⇄ List<T>
                  (same T)

One list of unknown elements:
                  List<?> ──capture T──→ internal read/write with same T
~~~

Choose **`List<T>`** or **`Map<K,V>`** when a method needs to retrieve an element/entry of a declared type and then write back a value **compatible with the same type parameter**. Choose **`? extends T`** when you want to accept flexible producers, **`? super T`** when you want to accept flexible consumers, and **`<?>`** when there is no need to name the element type.

Do not force raw/unchecked casts to bypass the type system because of a warning or inference error. Instead, re-examine **the relationship between inputs, values read, and values written**. A good generic signature must accurately describe that relationship—flexible enough for callers without opening a path to break data safety.