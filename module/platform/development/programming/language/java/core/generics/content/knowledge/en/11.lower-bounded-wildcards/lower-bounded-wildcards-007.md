# Applying `? super T` for data-receiving outputs in Java Generics

When a method **puts values of type `T` into a target object** (destination/consumer), the destination parameter should usually be declared with the **lower-bounded wildcard `? super T`**. This allows the method to write `T` into a collection whose type argument is exactly `T` **or a supertype of `T`**, while still being type-checked by Java at compile time.

For example, a method dedicated to adding `Integer` does not have to require `List<Integer>`: it can also add `Integer` into `List<Number>` and `List<Object>`. The signature `List<? super Integer>` expresses that requirement precisely.

This is the **Consumer Super** part of the **PECS — Producer Extends, Consumer Super** principle. “Data-receiving output” in this lesson refers to **a destination parameter into which the method writes elements**, not necessarily the method's `return` value.

## 1. What is a data-receiving output?

A parameter is a **consumer** in an operation when it **receives objects supplied by the method**, such as:

- A destination list receiving newly added `Integer` values.
- A destination collection receiving elements read from a source collection.
- A queue receiving tasks of type `T`.
- A handler function (for example `Consumer<? super T>`) receiving a `T` value to perform an action.
- `Comparator<? super T>` receiving `T` elements to compare them, even though it does not store them.

Producer/consumer roles are determined **by the direction of data flow in the API**. An `ArrayList<Number>` can act as a *consumer* when receiving numbers from a source, and become a *producer* when another method iterates over existing numbers.

Example of a write-only method:

```java
static void addDefaults(List<? super Integer> destination) {
    destination.add(10);
    destination.add(20);
}
```

Type-valid calls:

```java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

addDefaults(integers);
addDefaults(numbers);
addDefaults(objects);
```

`destination` only needs the ability to accept `Integer`. There is no reason to force callers to build an exact `List<Integer>` when a broader destination list can still store `Integer` safely.

## 2. Why shouldn't a consumer parameter be fixed to `List<Integer>`?

An API that only needs to send an `Integer` into a destination can work with `List<Integer>`, `List<Number>`, or `List<Object>`. Java Generics are invariant, so `List<Number>` cannot be directly assigned to `List<Integer>`; if a narrow signature is used, callers must needlessly create a new list or resort to casting.

~~~java
static void sendTen(List<? super Integer> destination) {
    destination.add(10);
}
~~~

This signature **expands the destination choices without relaxing the element type being written**. The destination itself may already contain elements of a broader type; the method above does not need to know or read them. This is the clearest consumer case before considering callbacks, comparators, and source/destination combinations.

## 3. Choose the lower bound according to the values the output must accept

Do not read `? super Integer` as “allows sending any `Number` into the list”. A `List<? super Integer>` might actually be a `List<Integer>`, so `destination.add(2.5)` is unsafe. If you need to send both `Integer` and `Double`, choose `List<? super Number>` so the receiver is guaranteed to hold `Number` values.

~~~java
List<Number> numbers = new ArrayList<>();
List<? super Integer> integerOnly = numbers;
integerOnly.add(7);
// integerOnly.add(2.5); // Does not compile.

numbers.add(2.5);       // Valid, thanks to reference type List<Number>.
~~~

Both references share the same object, yet **each variable has permissions according to its own static type**. Choose the bound `T` based on the kind of data the method intends to write, not based on the runtime class of a list object that happens to be passed in.

## 4. An output can accept `T`, but is not guaranteed to produce `T`

The wildcard's lower bound only proves **the destination accepts `T` values**. If `List<? super Integer>` points to a `List<Object>` holding an old `String`, `get(i)` cannot be treated by the compiler as `Integer` or `Number`:

~~~java
List<Object> actual = new ArrayList<>();
actual.add("old");
List<? super Integer> destination = actual;
destination.add(42);

Object item = destination.get(0); // "old"
// Integer wrong = destination.get(0); // Compile-time error.
~~~

`set(i, 99)` is allowed type-wise, but requires a valid index and a modifiable list; `add(null)` is accepted by the compiler, yet the implementation may forbid null. If strongly typed read results are needed, use a suitable source parameter or verify **each value individually** with `instanceof`. `? super T` is not a promise about existing contents or mutability.

## 5. Why does `super` favor data-receiving outputs?

An API taking a destination to add `T` needs to know **the destination accepts `T`**. It does not necessarily need to know **all existing elements of the destination are `T`**.

Those are two opposite directions:

- **Writing:** needs to guarantee `T` can be placed into the collection → `Collection<? super T>`.
- **Reading:** needs to guarantee retrieved elements can be used as `T` → `Collection<? extends T>`.

This asymmetry is the reason for the PECS rule:

> **Producer Extends, Consumer Super.**

PECS is a guideline based on how a parameter is used. It does not mean every object named “output” must use `super`, or that calling `add` always requires a `super` wildcard. If the algorithm needs to **both read and write exact `T`**, `List<T>` may be clearer.

Example:

```java
static void increment(List<Integer> values) {
    for (int i = 0; i < values.size(); i++) {
        values.set(i, values.get(i) + 1);
    }
}
```

The method needs to read `Integer` to add 1, then write `Integer` back, so `List<Integer>` makes sense. If changed to `List<? super Integer>`, the result of `get(i)` is only guaranteed to be `Object` and addition cannot be applied directly.

## 6. Pairing a producing source and a data-receiving output

A pipeline commonly reads from one iterable and writes into another collection. A signature that both follows PECS and uses minimal abstractions:

~~~java
static <T> void transfer(
        Iterable<? extends T> source,
        Collection<? super T> destination) {
    for (T value : source) {
        destination.add(value);
    }
}
~~~

`Iterable<? extends T>` **produces** elements readable as `T`; `Collection<? super T>` **consumes** `T`. Thus `List<Integer>` can be transferred into `Collection<Number>` or `Collection<Object>` without unchecked casts.

This method **appends**, rather than overwriting existing positions. If `source` and `destination` are the same `ArrayList`, calling `add` during a for-each loop can throw `ConcurrentModificationException`; to support self-copying, take an appropriate snapshot before mutating. If `destination.add` throws an exception, earlier elements may already have been added: PECS does not make copy operations atomic transactions.

## 7. Standard library example: `Collections.copy`

The Java Collections Framework uses the same consumer idea for the destination. The conceptual signature of the method:

```java
public static <T> void copy(
        List<? super T> dest,
        List<? extends T> src)
```

Where:

- `src` supplies elements, so it uses `? extends T`.
- `dest` receives or replaces elements, so it uses `? super T`.

Small standalone example:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class CopyExample {
    public static void main(String[] args) {
        List<Integer> source = List.of(4, 5);
        List<Number> target = new ArrayList<>(List.of(0, 0));

        Collections.copy(target, source);
        System.out.println(target);
    }
}
```

Save `CopyExample.java` and run:

```bash
javac CopyExample.java
java CopyExample
```

Stdout:

```text
[4, 5]
```

**Important:** `Collections.copy` **replaces** elements at existing positions in the destination, rather than appending to the end like `appendAll`. The destination list must have a `size()` **at least equal to** the source size; otherwise, the method throws `IndexOutOfBoundsException`. The destination must also support replacing elements, or the operation may throw `UnsupportedOperationException`.

In the example above, `target` is created with two `0` elements, providing enough slots to replace both positions with `4` and `5`. `new ArrayList<>(source)` is an alternative when you genuinely want to create a new list rather than write into an existing destination.

## 8. `? super T` is not limited to collections

A “consumer” can be a function or object that **receives a value of type `T`**, even if it does not store elements.

### 8.1. `Consumer<? super T>`

The `Iterable.forEach` method has a signature accepting a `Consumer<? super T>`. Thanks to this, a `Consumer<Number>` can process elements of a `List<Integer>`:

```java
import java.util.List;
import java.util.function.Consumer;

public class ConsumerExample {
    public static void main(String[] args) {
        List<Integer> integers = List.of(1, 2, 3);
        Consumer<Number> printNumber =
                number -> System.out.println(number.intValue());

        integers.forEach(printNumber);
    }
}
```

Run:

```bash
javac ConsumerExample.java
java ConsumerExample
```

Stdout:

```text
1
2
3
```

`Consumer<Number>` knows how to accept any `Number`, so it can accept `Integer` values. Conversely, a `Consumer<Integer>` cannot be treated as a general consumer of all `Number` values, because it is not guaranteed to handle `Double`.

### 8.2. `Comparator<? super T>`

`List.sort` accepts `Comparator<? super E>`, where `E` is the list's element type. A `Comparator<Number>` is capable of comparing `Integer` values because every `Integer` is also a `Number`.

```java
List<Integer> values = new ArrayList<>(List.of(10, 3, 20));
Comparator<Number> byValue =
        Comparator.comparingDouble(Number::doubleValue);
values.sort(byValue);
System.out.println(values); // [3, 10, 20]
```

This is **a snippet used in a context where `java.util.List`, `java.util.ArrayList`, and `java.util.Comparator` are already imported**. `Comparator` is a consumer in the sense of **receiving elements for comparison**, not meaning that a comparator writes into the list.

The common thread is that **an API needs to pass `T` values to a receiving object**; the lower bound allows the receiver to be designed to handle supertypes of `T` as well.

## 9. Complete Java 17+ program

The following program brings together the main scenarios: multiple destination types accepting `Integer`, typed source–destination relationships, reading via `? super Integer`, and a comparator consuming `Number`.

Save as **`SuperConsumerDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.List;

public class SuperConsumerDemo {
    static void seed(Collection<? super Integer> target) {
        target.add(10);
        target.add(20);
    }

    static <T> void appendAll(
            List<? extends T> source,
            List<? super T> target) {
        for (T element : source) {
            target.add(element);
        }
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>();
        List<Number> numbers = new ArrayList<>();
        List<Object> objects = new ArrayList<>();

        seed(integers);
        seed(numbers);
        seed(objects);

        List<Integer> source = List.of(3, 5);
        appendAll(source, numbers);
        appendAll(source, objects);

        System.out.println("integers = " + integers);
        System.out.println("numbers = " + numbers);
        System.out.println("objects = " + objects);

        List<? super Integer> target = numbers;
        Object first = target.get(0);
        System.out.println("first = " + first);

        numbers.add(2.5);
        System.out.println("numbers after Double = " + numbers);

        List<Integer> sorted = new ArrayList<>(List.of(10, 3, 20));
        Comparator<Number> byValue =
                Comparator.comparingDouble(Number::doubleValue);
        sorted.sort(byValue);
        System.out.println("sorted = " + sorted);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac SuperConsumerDemo.java
java SuperConsumerDemo
```

Stdout:

```text
integers = [10, 20]
numbers = [10, 20, 3, 5]
objects = [10, 20, 3, 5]
first = 10
numbers after Double = [10, 20, 3, 5, 2.5]
sorted = [3, 10, 20]
```

Explanation of results:

1. The same `seed` method adds `Integer` to three destination collection types, because all three accept `Integer`.
2. `appendAll` transfers values from `List<Integer>` to `List<Number>` and `List<Object>` without casting.
3. Through the `target` reference of type `List<? super Integer>`, read results are safely guaranteed as `Object`.
4. The `numbers` list is inherently a `List<Number>`, so through the `numbers` reference it can still have `2.5` added after the consumer method has run.
5. `Comparator<Number>` can compare `Integer` elements when `sorted.sort(byValue)` is called.

The code does not convert a `List<Number>` into a `List<Integer>`; the wildcard only adjusts **which parameter relationships are allowed in the type system**, without changing the element type of the actual list.

## 10. Choosing the right signature for the need

| API requirement | Suggested signature | Readable as | Writable |
| --- | --- | --- | --- |
| Only add `Integer` to destination | `Collection<? super Integer>` | `Object` when retrieving elements | `Integer` |
| Read any kind of number from source | `Collection<? extends Number>` | `Number` | No specific non-null value guaranteed |
| Read and add any `Number` to a fixed destination list | `List<Number>` | `Number` | `Number` and subtypes |
| Read and write exact `Integer` | `List<Integer>` | `Integer` | `Integer` |
| Transfer values from source to destination | `<T>` + `Iterable<? extends T>` and `Collection<? super T>` | `T` from source | `T` into destination |
| Process `Integer` elements with a callback accepting `Number` | `Consumer<? super Integer>` | Not applicable to this callback | Callback receives `Integer` |

“Writable” in the table means **type-valid**, not a guarantee that a specific collection is mutable. Signature choice must follow the method contract, not merely variable names.

Some APIs only need to call `destination.add(...)` and can therefore accept `Collection<? super T>`. If positional access or element replacement via `set(index, value)` is needed, choose `List<? super T>`.

## 11. Common mistakes

### 11.1. Assuming `? super Integer` allows writing any `Number`

`List<? super Integer>` accepts **guaranteed `Integer`**, not guaranteed `Double`. If the real destination is `List<Integer>`, adding a `Double` is invalid. To add arbitrary `Number` values, use `List<? super Number>` (for destinations typed as `Number` or a supertype), or `List<Number>` when the exact list type is known.

### 11.2. Reading `Integer` directly from a wildcard destination

```java
List<Object> objects = new ArrayList<>();
objects.add("other");
List<? super Integer> destination = objects;

// Integer value = destination.get(0); // COMPILE-TIME ERROR.
Object value = destination.get(0);      // Valid.
```

This example shows why reading as `Integer` is unsafe: the current element is actually a `String`. A lower-bounded wildcard reference does not promise that every element of the destination has type `Integer`.

### 11.3. Thinking `super` produces a modifiable collection

```java
List<Integer> immutable = List.of(1, 2);
List<? super Integer> target = immutable;
// target.add(3); // Compiles, but if run will throw
// UnsupportedOperationException because List.of does not support adding.
```

The `super` keyword only implies **type checking for written elements**, not structural mutability. If an API is responsible for writing, its contract should explicitly state that the destination collection must support the corresponding operation.

### 11.4. Confusing `super` with “supertype of the list”

`List<? super Integer>` is not `List<Number>` and does not mean it inherits from `List<Integer>`. It is **a parameterized type with a lower-bounded wildcard**, used to accept multiple compatible type arguments. Assignments and read/write permissions are checked by the compiler based on that bound.

### 11.5. Using raw types or unchecked casts to force data

Do not write `List raw = ...` and add objects without type constraints, or cast `List<?>` to `List<Integer>` just to call `add`. Those shortcuts can put data incompatible with the original type parameter into the list and cause `ClassCastException` when elements are read under the declared type.

Use `? super T` when needing to **add `T` to a broader destination** and `? extends T` when needing to **retrieve `T` from a narrower source**.

### 11.6. Forgetting destination size or writability

Some operations use `add` to grow the destination; operations like `Collections.copy` use `set` to replace existing positions. Both can leverage `? super T`, yet their runtime preconditions differ. Read the API contract: is the collection mutable, is the destination large enough, does it accept `null`, and may source and destination overlap?

## 12. Knowledge self-check

Given variables with explicit declared types:

```java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();
List<Double> doubles = new ArrayList<>();

List<? super Integer> destination = numbers;
```

Evaluate each statement:

1. `destination.add(1)` — **Valid**. `1` is boxed into `Integer`.
2. `destination.add(Double.valueOf(2.5))` — **Compile-time error**. The destination might be `List<Integer>`.
3. `Number n = destination.get(0)` — **Compile-time error**. Reading through the wildcard only guarantees `Object`.
4. `Object o = destination.get(0)` — **Type-valid**; if the list is empty, runtime throws `IndexOutOfBoundsException`.
5. `destination = integers` — **Valid**. `List<Integer>` can serve as a consumer of `Integer`.
6. `destination = objects` — **Valid**. `List<Object>` accepts `Integer`.
7. `destination = doubles` — **Compile-time error**. `Double` is not a supertype of `Integer`.
8. `List<? super Number> target = numbers` — **Valid**. `Number` satisfies the lower bound.
9. `List<? super Number> target = integers` — **Compile-time error**. `Integer` is not a supertype of `Number`.
10. `appendAll(integers, objects)` — **Valid**, with the signature `<T> void appendAll(List<? extends T>, List<? super T>)` in the complete program above.

The items involving `get(0)` only evaluate **expression types**; to run successfully, the list must contain an element and not violate runtime contracts.

## Key takeaways

- A **consumer** is a parameter that **receives values of type `T`** from a method; when needing to write `T` into multiple destination types, use `? super T`.
- `List<? super Integer>` accepts references to `List<Integer>`, `List<Number>`, and `List<Object>`; it does not accept `List<Double>`.
- With `List<? super T>`, **`T` or a subtype of `T`** can be written, whereas general safe reading only yields `Object`.
- **PECS:** use `? extends T` for supplying sources, `? super T` for consuming destinations.
- When needing to both read and write one specific type, `List<T>` or `List<Integer>` is usually more suitable.
- Being writable **generically** does not prove a collection is mutable. Runtime preconditions of `add`, `set`, and `Collections.copy` must still be respected.
- Java Generics are invariant; lower-bounded wildcards provide the ability to accept broader destinations **without unsafe casts**.

Choosing `? super T` for the right data-receiving role makes Java APIs more reusable, allows passing elements up into supertype destination collections, and preserves generic contract correctness right at compile time.