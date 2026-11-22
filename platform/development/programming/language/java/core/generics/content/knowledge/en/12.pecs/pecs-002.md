# Determining the Read–Write Role of Each Parameter Under the PECS Rule

## 1. Why Determine Parameter Roles?

When designing a Java Generics API, two methods that both accept a `List<T>` may use the list in very different ways: one method only pulls elements out to compute with them, while the other only receives newly written elements. Writing the parameter as `List<T>` in every case can cause the API to reject lists that are completely suitable for the actual task.

**PECS** is the rule for choosing wildcards based on the role of each parameter:

- **Producer Extends**: a source **supplies values of type `T` to the algorithm** → consider `? extends T`.
- **Consumer Super**: a destination **receives values of type `T` from the algorithm** → consider `? super T`.

This is a rule about **the direction in which values move relative to the algorithm being written**, not simply whether a parameter appears first or last in the signature, or whether it is passed into the method.

Example:

```java
static <T> void copyValues(
        List<? extends T> source,
        List<? super T> destination) {
    for (T element : source) { // Read T from source
        destination.add(element); // Write T into destination
    }
}
```

In this example, `source` is a producer even though it is **passed into** the method; `destination` is a consumer even though it is also **passed into** the method. Reading and writing must be viewed from **inside the algorithm's operations**.

## 2. Step-by-Step Process to Determine Each Parameter's Role

For each generic parameter, go through these steps in order:

1. **Identify the type `T` of values being exchanged.** This could be `Number`, `String`, `Animal`, or a `<T>` type parameter declared on the method.
2. **Read the method body following the data flow.** Are `T` values **taken from** the parameter or **put into** the parameter?
3. **Separate secondary operations from primary operations.** `size()`, `isEmpty()`, and `contains(Object)` do not supply or accept a value of element type `T` in the sense PECS cares about.
4. **Assess the required permissions:** if you only take `T` out, choose `? extends T`; if you only supply `T` to a destination, choose `? super T`; if you need both reading and writing the exact `T`, consider `List<T>` and a named type parameter.
5. **Test calls with subtypes and supertypes.** Check whether a `List<Integer>` can serve as a source for reading `Number`; check whether a `List<Object>` can serve as a destination for receiving `Integer`.
6. **Do not overstate the wildcard's guarantees.** `extends` does not guarantee an immutable list; `super` does not guarantee that values read out are `T`; both still depend on the actual mutability of the implementation.

An initial decision table:

| How the parameter is used in the method | Role | Typical choice |
|---|---|---|
| Only reads elements as type `T` | Producer | `List<? extends T>` |
| Only puts `T` values into the list | Consumer | `List<? super T>` |
| Both reads elements as `T` and writes `T` elements | Both | `List<T>` or an appropriate `<T>` design |
| Only checks count, prints general info, does not need type `T` | Element-type independent | `List<?>` |
| Needs to preserve a type relationship across multiple parameters and the return type | Contract-dependent | Combine `<T>` with wildcards at each position |

This table is a design guide, **not a rule for mechanically rewriting signatures**. For instance, `List<? extends T>` can still call `clear()`, and `List<? super T>` can still read `Object`. The terms producer and consumer emphasize **supplying or receiving values of type `T`**.

## 3. Identifying a Producer from Read Operations

Suppose a method needs to compute the sum of a list of numbers:

```java
static double total(List<? extends Number> values) {
    double result = 0;
    for (Number value : values) {
        result += value.doubleValue();
    }
    return result;
}
```

Analysis:

- `values` supplies each element via `iterator()`/`get()`.
- The method treats each element as `Number` and calls `doubleValue()`; it does not create a new `Number` element to put into `values`.
- Therefore `values` plays the role of a **producer of `Number`**. `List<? extends Number>` accepts `List<Number>`, `List<Integer>`, `List<Double>`, and any `List<S>` with `S extends Number`.

If declared as `List<Number>`, the call `total(List<Integer>)` will **not** compile due to generic *invariance*, even though `Integer` is a subclass of `Number`.

```java
List<Integer> counts = List.of(2, 3);
List<Double> measurements = List.of(1.5, 2.5);

double a = total(counts);       // 5.0
double b = total(measurements); // 4.0
```

With `List<? extends Number>`, values read from the list can be used as `Number`; however, the compiler **does not allow adding an arbitrary `Integer` or `Double` to it**. The hidden element type could be any subtype of `Number`.

```java
static void inspect(List<? extends Number> values) {
    Number first = values.get(0); // Type-valid, requires a non-empty list
    // values.add(1);              // Does not compile
    // values.add(1.5);            // Does not compile
}
```

**Note:** If the algorithm only needs `size()` or prints every element as `Object`, `List<?>` may communicate the intent more accurately than `List<? extends Number>` because there is no need to constrain the data to numbers.

## 4. Identifying a Consumer from Write Operations

Consider a method that puts two integers into a caller-supplied list:

```java
static void addDefaults(List<? super Integer> destination) {
    destination.add(10);
    destination.add(20);
}
```

Analysis:

- The method body **produces** two `Integer` values.
- `destination` **receives** them via `add`.
- Therefore `destination` is a **consumer of `Integer`**, matching `List<? super Integer>`.

```java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

addDefaults(integers); // Valid
addDefaults(numbers);  // Valid
addDefaults(objects);  // Valid
```

All three arguments fit because `Integer` is assignable to `Integer`, `Number`, and `Object`. Conversely, `List<Double>` does not match `? super Integer` because `Double` **is not a supertype of `Integer`**.

The trade-off is that a value retrieved from a variable of type `List<? super Integer>` only guarantees the static type `Object`:

```java
static void demoReadingConsumer(List<? super Integer> values) {
    Object element = values.get(0); // Type-valid
    // Integer integer = values.get(0); // Does not compile
}
```

This makes sense: a `List<Object>` may already contain a `String` or a non-`Integer` object beforehand. The consumer signature only promises it is **broad enough to accept `Integer`**, not that every existing element is an `Integer`.

`null` can be added at the type-checking level for both `? extends T` and `? super T` because `null` is compatible with every reference type. Whether the operation succeeds at runtime, however, depends on whether the list allows mutation and `null`. Do not use the ability to add `null` to determine a PECS role.

## 5. When a Parameter Is Both Read and Written

Some operations that **replace or transform values of the same type** need to read `T` from a list and write a `T` value back into that very list. For example, incrementing each integer:

```java
static void increment(List<Integer> values) {
    for (int i = 0; i < values.size(); i++) {
        Integer oldValue = values.get(i); // Read Integer
        values.set(i, oldValue + 1);      // Write Integer
    }
}
```

Here, replacing `List<Integer>` with `List<? extends Integer>` allows reading as `Integer` but prevents writing a new `Integer`. Replacing it with `List<? super Integer>` allows writing `Integer`, but `get(i)` is only safe as `Object`. For the exact contract “**read and write back Integer**,” `List<Integer>` expresses the required permissions.

For a generic algorithm applying a same-type transformation function:

```java
static <T> void transformInPlace(
        List<T> values,
        java.util.function.UnaryOperator<T> transform) {
    for (int i = 0; i < values.size(); i++) {
        T current = values.get(i);
        values.set(i, transform.apply(current));
    }
}
```

`List<T>` is chosen because it must read and write **the same `T`**. The method does not force all lists to have type argument `Object`; `T` is inferred separately per call. For example, `List<String>` and `UnaryOperator<String>` fit seamlessly.

There is an instructive exception: **swapping or copying back the very elements already read** can be done safely using a *wildcard capture* helper:

```java
static void swapFirstTwo(List<?> values) {
    swapCaptured(values);
}

private static <T> void swapCaptured(List<T> values) {
    if (values.size() < 2) {
        return;
    }
    T first = values.get(0);
    values.set(0, values.get(1));
    values.set(1, first);
}
```

The helper preserves a single hidden type `T` for both reading and writing; it **does not fabricate a new `T` object of an arbitrary type**. This is a case for using a named type parameter to connect operations safely, rather than raw casting.

## 6. Determining Separate Roles for Each Parameter in the Same Method

A method can have multiple parameters, each serving a different role. Analyze **each position** according to its data operations, rather than applying the same wildcard to all of them.

```java
static <T> void copyValues(
        List<? extends T> source,
        List<? super T> destination) {
    for (T element : source) {
        destination.add(element);
    }
}
```

The data flow is:

```text
source: List<? extends T>
           │ read T
           ▼
        element: T
           │ write T
           ▼
destination: List<? super T>
```

- The `source` parameter is a **producer**. Each `T` can be taken from a list whose actual elements are `T` or a subtype.
- The `destination` parameter is a **consumer**. `T` can be added to a list whose element type is `T` or a supertype.
- The named type parameter `<T>` **links both ends** so the compiler checks the shared type relationship.

Example:

```java
List<Integer> integers = List.of(1, 2);
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

copyValues(integers, numbers); // Integer is accepted via Number
copyValues(integers, objects); // Integer is accepted via Object
copyValues(numbers, objects);  // Number is accepted via Object
```

Even though `Integer` is a subtype of `Number`, `List<Integer>` is not a subtype of `List<Number>`. It is the two wildcards in **the method signature** that allow these calls to be checked safely, not a change to Java's invariance rules.

A `List<? super T>` used as a destination may already contain values of various subtypes. Do not infer that every value read out of the destination is `T`.

## 7. Complete Java 17 Example: Three Roles in One API

Create the file `PecsParameterRolesDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.function.Predicate;

public class PecsParameterRolesDemo {
    static <T> void copyMatching(
            Iterable<? extends T> source,
            Collection<? super T> destination,
            Predicate<? super T> filter) {
        for (T element : source) {
            if (filter.test(element)) {
                destination.add(element);
            }
        }
    }

    static double sum(List<? extends Number> source) {
        double total = 0;
        for (Number element : source) {
            total += element.doubleValue();
        }
        return total;
    }

    static void addDefaults(List<? super Integer> destination) {
        destination.add(10);
        destination.add(20);
    }

    static <T> void replaceFirst(List<T> values, T replacement) {
        if (!values.isEmpty()) {
            values.set(0, replacement);
        }
    }

    static void showCount(List<?> values) {
        System.out.println("Input size: " + values.size());
    }

    public static void main(String[] args) {
        List<Integer> input = List.of(1, 2, 3, 4);
        List<Number> selected = new ArrayList<>();
        Predicate<Number> isEven =
                value -> value.intValue() % 2 == 0;

        copyMatching(input, selected, isEven);
        System.out.println("Selected: " + selected);
        System.out.println("Sum: " + sum(selected));

        List<Object> events = new ArrayList<>();
        addDefaults(events);
        System.out.println("Events: " + events);

        replaceFirst(selected, 99);
        System.out.println("After replace: " + selected);

        showCount(input);
    }
}
```

Run in the directory containing the file (JDK 17 or higher):

```bash
javac PecsParameterRolesDemo.java
java PecsParameterRolesDemo
```

**Stdout:**

```text
Selected: [2, 4]
Sum: 6.0
Events: [10, 20]
After replace: [99, 4]
Input size: 4
```

How each parameter is analyzed:

| Parameter | Direct operation | Role with `T` | Signature |
|---|---|---|---|
| `copyMatching.source` | Reads `T` in loop | Producer | `Iterable<? extends T>` |
| `copyMatching.destination` | `add(element)` | Consumer | `Collection<? super T>` |
| `copyMatching.filter` | `test(element)`: accepts `T` | Consumer | `Predicate<? super T>` |
| `sum.source` | Reads `Number` and computes `doubleValue()` | Producer | `List<? extends Number>` |
| `addDefaults.destination` | `add(Integer)` | Consumer | `List<? super Integer>` |
| `replaceFirst.values` | `get()` and `set()` with same `T` | Read and write | `List<T>` |
| `showCount.values` | `size()` | Does not need `T` | `List<?>` |

**Explanation of easily confused points:**

1. `filter` is also a **consumer**, even though `Predicate.test` does not write an element into a list: it **receives a value of type `T` as input** to test. Hence `Predicate<Number>` can act as a filter for `Integer` elements.
2. `source` is `Iterable<? extends T>` because the algorithm only needs the ability to iterate over elements; there is no need to force the source to provide `get(index)` or be a `List`. This is how you choose an interface just narrow enough for the contract.
3. `destination` uses `Collection<? super T>` because only `add` is needed, not indexed operations. The destination can be a `List<Number>` even when the source is a `List<Integer>`.
4. `replaceFirst` uses `List<T>` because it needs to read and write the exact same type `T`. `selected` is `List<Number>`, so writing `Integer 99` is valid via `Integer extends Number`.
5. `input` is created with `List.of(...)` (unmodifiable), yet it only acts as a source so the program never attempts to modify it. `selected` and `events` use `ArrayList` to permit `add` and `set`.

Distinguish **static type** checking from runtime behavior. If you pass an unmodifiable destination to `copyMatching`, the call may still compile, but `destination.add` can throw `UnsupportedOperationException`. PECS determines which types are **permitted to be accepted**, not whether the implementation supports mutation.

## 8. Seeing PECS in Callbacks and Functional Interfaces

PECS is not just for `List`. Given a type parameter `T`, check whether a function object **accepts `T`** or **supplies `T`**.

### `Predicate<? super T>`: A Consumer of `T`

`Predicate<T>.test(T value)` takes a value of type `T` and returns a boolean. If an algorithm has `Integer` elements, a `Predicate<Number>` can still test them as `Number`:

```java
static <T> long countMatching(
        List<? extends T> source,
        java.util.function.Predicate<? super T> condition) {
    long count = 0;
    for (T item : source) {
        if (condition.test(item)) {
            count++;
        }
    }
    return count;
}
```

This method snippet is a standalone signature example; to compile it, place it inside a class and import `java.util.List`. `source` supplies `T`, while `condition` receives `T`, so opposite wildcard directions apply.

### `Comparator<? super T>`: Taking Two `T` Values to Compare

`List<E>.sort` has a signature accepting `Comparator<? super E>`. A comparator does not produce `E`; it **accepts `E` values as arguments to `compare`**, so it is a consumer.

```java
List<Integer> values = new ArrayList<>(List.of(30, 2, 11));
java.util.Comparator<Number> byValue =
        java.util.Comparator.comparingDouble(Number::doubleValue);

values.sort(byValue);
System.out.println(values); // [2, 11, 30]
```

This is an illustrative snippet that can be placed inside `main` with imports `java.util.List` and `java.util.ArrayList`. Using `Comparator<Number>` to sort `List<Integer>` is valid because `Number` can accept any `Integer`.

### `Function<? super T, ? extends R>`: Having Both Input and Output

`Function<A,B>` **consumes** an `A` via `apply(A)` and **produces** a `B` as its result. Therefore, in an API transforming `T` into `R`, you can choose:

```java
static <T, R> List<R> map(
        List<? extends T> source,
        java.util.function.Function<? super T, ? extends R> mapper) {
    List<R> result = new ArrayList<>();
    for (T item : source) {
        result.add(mapper.apply(item));
    }
    return result;
}
```

For example, `source` supplies `Integer`; a `Function<Number,String>` accepts `Integer` and returns a matching `String`. In the callback, a lower bound is used for the **input** and an upper bound for the **output**; both follow from the data direction relative to the algorithm.

Note that the `Comparator` and `map` snippets illustrate APIs inside a suitable Java class, not standalone programs on their own. The complete program in section 7 already has a file and deterministic stdout.

## 9. Distinguishing `add`, `set`, `get` from Role-Neutral Operations

When reading a method, do not label a parameter “consumer” merely because there is a **mutating operation**. PECS cares about the flow of values of type `T`:

| Call | How does it relate to `T`? | Meaning when choosing a wildcard |
|---|---|---|
| `T x = list.get(i)` | Takes `T` out | Producer |
| `for (T x : list)` | Takes `T` out | Producer |
| `list.add(valueOfTypeT)` | Puts `T` in | Consumer |
| `list.set(i, valueOfTypeT)` | Puts `T` in at position | Consumer, and also check whether `T` is read |
| `list.size()` | Does not exchange `T` | Does not determine PECS |
| `list.isEmpty()` | Does not exchange `T` | Does not determine PECS |
| `list.contains(anyObject)` | Takes `Object`, does not require `T` | Insufficient to conclude consumer of `T` |
| `list.remove(anyObject)` | Takes `Object` to find/remove | Insufficient to conclude consumer of `T` |
| `list.remove(index)` | Removes by index, may return element `T` | If the result is used as `T`, has a producer aspect |
| `list.clear()` | Removes all, does not require supplying `T` | Does not make it a consumer of `T` |

For example, `List<? extends Number>` **can** call `remove` or `clear()` at the type-checking level, even though a concrete `Integer` cannot be added. When called on an unmodifiable list, those operations can fail at runtime. Hence producer is not synonymous with “immutable.”

Similarly, a `List<? super Integer>` can call `get`, but can only read safely as `Object`. Consumer does not mean “cannot read anything at all.”

### Watch Out for the `remove` Overload

`List` has both `remove(int index)` and `remove(Object o)`:

```java
List<Integer> values = new ArrayList<>(List.of(10, 20, 30));
values.remove(1);                  // Remove element at index 1
values.remove(Integer.valueOf(30)); // Remove object with value 30
```

If you read a method with `remove(1)`, that is an indexed removal operation, not “writing the `Integer` value 1 into the list.” Check the actual overload before analyzing the role.

## 10. When to Keep `List<T>` Instead of Wildcards?

PECS is a guideline for optimizing contracts at **read-only** or **write-only** positions. Do not force wildcards if doing so loses an important type relationship.

### Need to Read and Write the Same `T`

```java
static <T> void replaceAll(
        List<T> values,
        java.util.function.UnaryOperator<T> op) {
    values.replaceAll(op);
}
```

`List<T>` and `UnaryOperator<T>` express the same type for both the input and output of the transformation. Using `List<? extends T>` at the `values` position could make writing a `T` back invalid; `List<? super T>` loses the guarantee of reading as `T`.

### Need a Result That Preserves the Input Type

```java
static <T> T firstOrNull(List<T> values) {
    return values.isEmpty() ? null : values.get(0);
}
```

`firstOrNull(List<String>)` returns static type `String`. If `List<?>` were used and `Object` returned, the caller would lose this type relationship. However, some equivalent designs with `? extends T` can be used depending on inference and signature needs; the key thing to preserve is **the type parameter `T` linking input and output**.

### Only Need Element-Type-Independent Operations

```java
static boolean hasElements(List<?> values) {
    return !values.isEmpty();
}
```

Because it neither produces nor retrieves a result of a type `T` that needs naming, the unbounded wildcard `<?>` is a simpler contract than adding an unused `<T>`.

## 11. Reading Parameter Roles in `Collections.copy`

A notable example when analyzing **role by position** is the standard library signature:

```java
static <T> void copy(List<? super T> dest, List<? extends T> src)
```

In `Collections.copy(dest, src)`, **the first parameter `dest` is the consumer**, while the second parameter `src` is the producer. This is the reverse of the habit in many hand-written helpers of putting `source` first: position does not determine PECS; **operations on values of type `T` do**.

The method uses `set` to **overwrite existing elements**, not `add` to grow the size. For example, with destination `[0, 0, 0]` and source `[7, 8]`, the result is `[7, 8, 0]`; if the destination is shorter than the source, it throws `IndexOutOfBoundsException`. An unmodifiable destination list can throw `UnsupportedOperationException`. These conditions are not governed by wildcards.


## 12. A Wrong Example and How to Fix the Signature

Suppose we want to gather all `Number` values from a source into a destination list:

```java
static void collectWrong(
        List<Number> source,
        List<Number> target) {
    for (Number n : source) {
        target.add(n);
    }
}
```

The method above compiles, yet `List<Integer>` cannot be passed to `source` and `List<Object>` cannot be passed to `target`. The signature is more restrictive than the algorithm requires.

Observe the method body:

1. `source` is only read through the loop, needing only a guarantee that each value can be used as `Number`.
2. `target` only receives `Number` values taken from the source, with no need to read them back as `Number`.

Fix:

```java
static void collectNumbers(
        List<? extends Number> source,
        List<? super Number> target) {
    for (Number n : source) {
        target.add(n);
    }
}
```

With this signature:

```java
List<Integer> input = List.of(1, 2);
List<Object> output = new ArrayList<>();
collectNumbers(input, output);
System.out.println(output); // [1, 2]
```

The snippet needs `import java.util.List` and `java.util.ArrayList`, placed inside a class to compile. The rule for fixing is to **relax each parameter strictly according to its role** while keeping the `Number` bound for numeric reads/writes.

There is no need to switch to raw `List`: raw types bypass type-argument checking and can cause *heap pollution*. Wildcards preserve a contract that can be checked at compile time.

## 13. Pitfalls When Analyzing Read–Write Roles

**Pitfall 1 — “A passed-in parameter is input, so it must use `extends`.”** False. In Java, every parameter is passed into the method, yet a parameter can represent where the algorithm writes results. `destination` is usually a consumer `<? super T>`.

**Pitfall 2 — “A producer is an immutable list.”** False. Producer is the role of supplying data to the algorithm. `List<? extends T>` does not prevent `remove`, `clear`, or certain other operations; mutability is decided by the actual object.

**Pitfall 3 — “A consumer cannot be read.”** False. `List<? super T>` can still be read as `Object`, though it does not guarantee every element is `T`. If the algorithm needs to read out as `T`, reconsider the signature.

**Pitfall 4 — “Whenever there is `set`, it is only a consumer.”** Not necessarily. `set` supplies a value to the destination, but if the algorithm also needs to read a value of the same type `T` from that parameter, the parameter has both roles. For example, `transformInPlace` uses `List<T>`.

**Pitfall 5 — “`contains` and `remove(Object)` turn a parameter into a consumer of `T`.”** Not necessarily. Those methods accept `Object`; check whether the algorithm actually puts a value of type `T` into storage.

**Pitfall 6 — “Every functional interface is a producer because it returns a result.”** False. `Predicate<T>` and `Comparator<T>` accept values of type `T`, so they are consumers of `T`, even though they return `boolean` or `int`.

**Pitfall 7 — “A `Function` has the same role for both type parameters.”** False. `Function<A,B>` takes `A` and returns `B`; in a transformation context, that is typically `Function<? super A, ? extends B>`.

**Pitfall 8 — “PECS proves the program will run safely in every situation.”** No. It checks **type compatibility**. `IndexOutOfBoundsException`, `UnsupportedOperationException`, `NullPointerException`, invalid data, and business logic bugs can still occur.

## 14. Self-Test Exercise on Parameter Roles

For each signature below, identify whether each parameter is a producer, a consumer, or requires a shared type `T`:

```java
// A
static double average(List<? extends Number> data);

// B
static void collect(List<? super Integer> target, int value);

// C
static <T> void copy(
        List<? extends T> from,
        List<? super T> to);

// D
static <T> void update(
        List<T> values,
        java.util.function.UnaryOperator<T> change);

// E
static boolean exists(List<?> items);

// F
static <T> long count(
        Iterable<? extends T> input,
        java.util.function.Predicate<? super T> condition);
```

These are **exercise signatures**, not implemented methods with bodies and not a standalone compilable Java file.

**Answers:**

- **A:** `data` is a producer of `Number` because `average` reads values to compute; there is no need to write numbers into the source.
- **B:** `target` is a consumer of `Integer` because it receives an `int` value boxed into `Integer`. The parameter `value` is a numeric value, not a generic structure needing a wildcard.
- **C:** `from` is a producer of `T`, `to` is a consumer of `T`; the type parameter `<T>` links both roles.
- **D:** `values` both reads and writes `T`, so it uses `List<T>`. `change` takes `T` and returns `T`; `UnaryOperator<T>` reflects a same-type transformation.
- **E:** `items` is only used to ask “are there any elements?”, without needing the element type; `List<?>` suffices.
- **F:** `input` is a producer of `T`. `condition` takes each `T` via `test`, so it is a consumer of `T`, even though the `boolean` result is used for counting.

You can test yourself further by substituting `T = Number` or `T = Integer`, then trying to pass `List<Integer>` where reading happens and `List<Object>` where writing happens. If replacing `extends` with `super` breaks reading, or vice versa, that is a sign to re-examine the role.

## 15. Checklist When Designing a PECS Signature

Before publishing a generic method, answer:

1. **What types of values does the algorithm read?** If it receives values of type `T` from a parameter, that parameter is usually a producer.
2. **What types of values does the algorithm write?** If it passes `T` into a parameter, that parameter is usually a consumer.
3. **Which parameters need to preserve a same-type relationship?** If a read value must be written back or returned with that exact type, consider `<T>` and `List<T>`.
4. **Are any parameters only calling general operations?** If independent of element type, `<?>` avoids unnecessary constraints.
5. **Are the parameter interfaces narrow enough?** If you only iterate, `Iterable<? extends T>` may suffice; if you only add, `Collection<? super T>` is often enough; no need to default to `List`.
6. **Are subtypes and supertypes accepted as expected?** Test calls from `List<Integer>` → `List<Number>` or `List<Object>` without raw types.
7. **Are runtime requirements clear?** For write targets, the caller must pass a collection supporting mutation; for `Collections.copy`, the destination must have enough existing elements; for `null` data, a separate contract is needed.

A good signature expresses **the exact read–write permissions the method body needs**, neither granting write access to a source nor forcing a destination to have the exact element type when unnecessary.

## 16. Key Takeaway

PECS is a method for **looking at whether each generic parameter supplies or receives values of type `T`**. Use **`? extends T`** for parameters supplying `T`; use **`? super T`** for parameters receiving `T`. If both reading and writing use the same type, use a named type parameter to preserve the relationship; if the element type does not participate in the algorithm, `<?>` may be the clearest choice.

The goal of PECS is to make APIs flexible with the necessary subtypes and supertypes **while remaining type-safe at compile time**, not merely swapping a few keywords in a signature.
