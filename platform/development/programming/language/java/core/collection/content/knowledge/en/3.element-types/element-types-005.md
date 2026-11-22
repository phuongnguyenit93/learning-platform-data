# Lower-Bounded Wildcards When Writing Data and the PECS Rule

A method that wants to add integers to a list does not necessarily need to require an exact `List<Integer>`. A `List<Number>` can also receive an `Integer`, and so can a `List<Object>`. If the signature only accepts `List<Integer>`, it excludes those completely safe targets.

A lower-bounded wildcard, written as `? super T`, solves this problem: it accepts a target capable of **receiving values of type T** while keeping Java's type checking intact.

This article focuses on the data-writing direction and how it coordinates with the reading direction in the PECS rule. The examples use Java 17 or later.

## 1. The problem to solve: accepting the right kind of write target

Suppose you need to add sample IDs of type `Integer`:

```java
static void addSampleIds(List<Integer> target) {
    target.add(10);
    target.add(20);
}
```

The method accepts a `List<Integer>`, but does not accept a `List<Number>` or `List<Object>` variable. Generics are invariant: `List<Integer>` does not become a subtype of `List<Number>` just because `Integer` is a subtype of `Number`.

In this case, the method does not need to know the exact element type of the target. It only needs to ensure that the target accepts `Integer`.

A more suitable signature:

```java
static void addSampleIds(List<? super Integer> target) {
    target.add(10);
    target.add(20);
}
```

These are illustrative methods that need to be placed in a class that imports `java.util.List`.

Thanks to the lower bound, the same method can be called with different targets:

```java
List<Integer> ids = new ArrayList<>();
List<Number> measurements = new ArrayList<>();
List<Object> values = new ArrayList<>();

addSampleIds(ids);
addSampleIds(measurements);
addSampleIds(values);
```

`ArrayList` also needs to be imported. The element types of all the target lists allow receiving `Integer`. [Oracle: Lower Bounded Wildcards](https://docs.oracle.com/javase/tutorial/java/generics/lowerBounded.html)

## 2. Reading the exact meaning of ? super Integer

`List<? super Integer>` does not mean "a list containing only supertypes of Integer".

It represents a list with an **unknown concrete type argument**, where that argument is `Integer` or an appropriate supertype of `Integer`.

You can visualize the unknown type as `S` with the relationship:

```text
Integer is a subtype of S.
```

When passing an `Integer` into a target expecting `S`, the write operation is safe. However, we do not know exactly what `S` is from the wildcard reference alone.

The following examples are valid:

| Typed object | Assignable to `List<? super Integer>`? | Reason |
| --- | --- | --- |
| `List<Integer>` | Yes | Accepts exact `Integer` |
| `List<Number>` | Yes | `Integer` is a `Number` |
| `List<Object>` | Yes | `Integer` is an `Object` |
| `List<Double>` | No | `Double` is not a supertype of `Integer` |
| `List<String>` | No | No valid relationship for accepting `Integer` |

The first three valid rows are familiar examples, not a claim that only three exact types are accepted. The supertype relationship can also include interfaces that `Integer` implements.

A lower-bounded wildcard is used at the generic use site. It does not declare a new generic class and does not copy data.

```java
List<Object> original = new ArrayList<>();
List<? super Integer> target = original;

target.add(10);
System.out.println(original); // [10]
```

Both variables still point to the same list object; modifications through `target` are visible through `original`. [Java Language Specification 17: Type Arguments of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.1)

## 3. Which values can be written?

### 3.1. Writing values of the lower bound

Through `List<? super Integer>`, you can add `Integer`:

```java
List<? super Integer> target = new ArrayList<Number>();
target.add(Integer.valueOf(7));
target.add(8);
```

On the last line, the `int` value is boxed into an `Integer`.

With a general lower bound `? super Dog`, you can also add an instance of a subclass of `Dog`, because it can still be used wherever a `Dog` is accepted. In the integer example, `Integer` is a final class, so it has no user-defined subclasses.

### 3.2. Not every Number can be added

The following snippet **does not compile**:

```java
List<? super Integer> target = new ArrayList<Integer>();
target.add(2.5); // Double is not guaranteed to be accepted.
```

`2.5` becomes a `Double`. However, the actual list might be a `List<Integer>`, so adding a `Double` would break its type guarantee.

Nor can you add a variable whose static type is only `Number`:

```java
Number value = Integer.valueOf(7);
List<? super Integer> target = new ArrayList<Number>();

// Does not compile:
target.add(value);
```

Even though the current object held by `value` is an `Integer`, the expression `value` is checked under the type `Number`. A lower bound does not allow bypassing the type contract of an expression.

If the data is meant to be `Integer`, preserve that type information in the design. Do not add a cast just to bypass an error without a valid basis.

### 3.3. Replacing elements follows the same type rule

With a non-empty list that supports `set`:

```java
List<Number> values = new ArrayList<>(List.<Number>of(2.5));
List<? super Integer> target = values;

Object old = target.set(0, 10);
```

Writing an `Integer` is safe, but the old value is only guaranteed to be `Object`: it could be a `Double`, as in the example.

A lower-bounded wildcard governs what kind of data is safe to write, not just the `add` method specifically.

## 4. Why does reading only guarantee Object?

A list that accepts `Integer` does not necessarily contain only `Integer`:

```java
List<Object> values = new ArrayList<>();
values.add("header");

List<? super Integer> target = values;
target.add(10);

Object first = target.get(0);
System.out.println(first); // header
```

If `get(0)` were treated as `Integer`, the example above would be unsafe. Because the target could be a `List<Object>` containing arbitrary pre-existing data, the common read type is only `Object`.

The following lines **do not compile**:

```java
Integer firstInteger = target.get(0);
Number firstNumber = target.get(0);
```

The word "consumer" in PECS does not mean the object cannot be read. It means we use this type to guarantee the value-receiving direction; the type information of data read back out is weaker.

Do not describe `? super Integer` as "write-only". We can still read elements as `Object`, query the size, iterate, remove elements, or perform other operations supported by the object.

A cast when reading is only safe if there is independent proof that the element matches. The presence of the wildcard does not provide that proof.

## 5. PECS: viewing data flow from the method's perspective

PECS is a mnemonic for:

```text
Producer Extends
Consumer Super
```

Translated by role:

- Where a parameter **produces T for the method to read**: use `? extends T`.
- Where a parameter **consumes T that the method writes**: use `? super T`.

Consider a method that transfers elements from a source to a target:

```java
static <T> void appendAll(
        Iterable<? extends T> source,
        Collection<? super T> target) {

    for (T value : source) {
        target.add(value);
    }
}
```

The method requires importing `java.util.Collection`; `Iterable` belongs to `java.lang`.

- `source` provides values usable as `T`, so it uses `extends`.
- `target` receives those `T` values, so it uses `super`.
- The type parameter `T` links both sides within the same call.

This is a method that **appends elements to the target via the add operation**, not a data-move transaction. It does not clear the source and does not roll back if an error occurs midway. Ordering and duplicate retention depend on the target collection type; for example, a set does not retain repeated equal elements.

The point of view is the method being designed. A collection might produce data in one method and consume data in another; the role is not permanently attached to a class name or variable name. [Oracle: Guidelines for Wildcard Use](https://docs.oracle.com/javase/tutorial/java/generics/wildcardGuidelines.html)

### Common source–target pairs

| Source type | Target type | Can transfer safely using the method above? |
| --- | --- | --- |
| `List<Integer>` | `List<Integer>` | Yes |
| `List<Integer>` | `List<Number>` | Yes |
| `List<Integer>` | `List<Object>` | Yes |
| `List<Double>` | `List<Number>` | Yes |
| `List<Number>` | `List<Integer>` | No |
| `List<String>` | `List<Number>` | No |

The row from `List<Number>` to `List<Integer>` is rejected even if the source currently happens to contain only integers. The source type permits other `Number` subtypes; the signature has no proof that every element is an `Integer`.

When using the illustrative method, the source must not be structurally modified in an invalid way while being iterated. In particular, do not assume it is safe when the source and target are actually the same collection or views sharing underlying data.

## 6. Comparing easily confused types

| Reference type | What is known about elements | Write arbitrary `Integer`? | Guaranteed read type |
| --- | --- | --- | --- |
| `List<Integer>` | Exact element type is `Integer` | Yes | `Integer` |
| `List<? extends Number>` | An unknown type in the `Number` hierarchy | No | `Number` |
| `List<? super Integer>` | An unknown type that accepts `Integer` | Yes | `Object` |
| `List<?>` | An unknown element type | No | `Object` |
| `List<Object>` | Element type is `Object` | Yes | `Object` |

The "write" column refers to type checking. A list might still be unmodifiable or have value restrictions at runtime.

`List<? extends Number>` does not guarantee read-only behavior in the sense of immutability: for instance, `clear()` can be valid and mutate the underlying source. `List<? super Integer>` does not guarantee write-only behavior either. Wildcards restrict operations that depend on knowing the element type; they do not create a runtime modification permission mechanism. [Oracle: Wildcards and Subtyping](https://docs.oracle.com/javase/tutorial/java/generics/subtyping.html)

## 7. PECS also appears in callbacks

### 7.1. Consumer receives elements

`Iterable.forEach` accepts an object of the form:

```java
Consumer<? super T>
```

If a list has `Integer` elements, a `Consumer<Number>` is completely capable of receiving them:

```java
List<Integer> ids = List.of(1, 2, 3);

Consumer<Number> printer =
        value -> System.out.println(value.doubleValue());

ids.forEach(printer);
```

This snippet requires importing `List` and `java.util.function.Consumer`.

A consumer capable of handling `Number` can also handle `Integer`. It does not force the caller to rewrite it as `Consumer<Integer>` when existing capability is already sufficient.

In this case, the callback object is the party consuming `T`. Do not just look at the method name `forEach` and guess the wildcard direction. [Java 17: Iterable.forEach](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Iterable.html#forEach(java.util.function.Consumer)), [Consumer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Consumer.html)

### 7.2. Comparator consumes two values to compare them

`List<E>.sort` accepts `Comparator<? super E>`. A comparator that can compare `Number` values can be used to sort a list of `Integer`:

```java
Comparator<Number> byNumber =
        Comparator.comparingDouble(Number::doubleValue);

List<Integer> ids = new ArrayList<>(List.of(3, 1, 2));
ids.sort(byNumber);

System.out.println(ids); // [1, 2, 3]
```

This illustration requires importing the types used. The comparator accepts two elements; the `int` return value of the comparison does not turn `T` into output data.

A comparator using `doubleValue` is only appropriate for illustrative purposes and this specific data domain. It does not accurately preserve ordering for all high-precision `Number` types; a matching generic type does not automatically guarantee correct domain comparison rules. [Java 17: List.sort](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator))

## 8. Reading the Collections.copy signature using PECS

A classic API:

```java
static <T> void copy(
        List<? super T> dest,
        List<? extends T> src)
```

The destination receives `T` values; the source provides values usable as `T`. This follows the exact same reasoning, even though the parameter order puts the destination first and the source second.

However, PECS only addresses type relationships. The runtime contract of `Collections.copy` also specifies that the destination must have a **size at least equal to the source**. It replaces existing positions rather than automatically appending slots like the `appendAll` method above.

```java
List<Number> dest =
        new ArrayList<>(List.<Number>of(9.0, 9.0, 9.0));

Collections.copy(dest, List.of(1, 2));
System.out.println(dest); // [1, 2, 9.0]
```

If you only write:

```java
List<Number> dest = new ArrayList<>(10);
Collections.copy(dest, List.of(1, 2)); // IndexOutOfBoundsException.
```

A capacity of 10 does not create 10 elements; the destination size is still 0.

Read the wildcards to understand which side is read and which side is written, then continue reading the requirements on size, mutability, and exceptions. A proper generic signature does not replace the full API contract. [Java 17: Collections.copy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#copy(java.util.List,java.util.List))

## 9. When should you not rely solely on wildcards?

### 9.1. Needing to maintain an exact type across multiple positions

If a method both reads a value of a specific type and returns it, or links it with another parameter, a named type parameter is usually more expressive.

For example:

```java
static <T> T addAndReturn(List<T> target, T value) {
    target.add(value);
    return value;
}
```

This is an illustrative method. `T` links the received value, the list, and the result.

Do not turn every `List<T>` into `List<? super T>` out of habit. Consider the desired contract, type inference behavior, and the result type the caller needs.

### 9.2. Returning a wildcard forces the caller to keep carrying that restriction

If a method creates a new `List<Integer>`, returning `List<? super Integer>` typically strips the caller of the ability to read `Integer` directly without any commensurate benefit.

Wildcards are a tool for relaxing input acceptance rules based on role, not a default that must appear everywhere. Only include a wildcard in a return type when that restriction is genuinely intended by the API.

### 9.3. Lower bounds do not share the same syntax as type parameters

In Java, you do not write:

```java
// Invalid:
<T super Integer>
```

`super` in this article belongs to the wildcard syntax `? super Integer`. Named type parameters use different declaration rules, such as `<T extends Number>` for an upper bound.

A single wildcard cannot simultaneously specify both `extends` and `super` to form an arbitrary range. Do not overgeneralize the syntax from how its meaning is phrased in natural language.

## 10. Type bounds do not guarantee mutability or atomicity

### 10.1. An object might not support add

A method taking `List<? super Integer>` accepts a `List<Integer>` variable as far as types are concerned, but the underlying object might have been created with `List.of`:

```java
List<Integer> target = List.of(1, 2);
addSampleIds(target); // UnsupportedOperationException.
```

If a method needs to write data, its documentation should state that the target must support that operation. If the method owns the creation of the result, it can proactively choose a mutable structure.

Similarly, `null` may be valid from a type perspective but rejected by the collection according to its own policy. Wildcards do not fully express data nullability.

### 10.2. Multiple writes do not automatically form a transaction

If the first `add` succeeds but the next one fails, the already-added elements are not automatically rolled back by the wildcard contract.

`List<? super T>` does not imply thread safety either. A target `ArrayList` shared across multiple threads still requires proper synchronization; generic types do not introduce locks.

### 10.3. Do not use raw types or casts to bypass type errors

If the source has type `List<Number>` and the target is `List<Integer>`, the compiler error may reflect a genuinely unsafe design. Determine whether you need to validate each value, convert the data, or choose a broader target type.

Casting through a raw `List` or suppressing unchecked warnings does not turn a `Double` into an `Integer`. It merely disables part of the check, causing the failure to surface later at a read site.

## 11. Complete Java 17 Program

Save to `LowerBoundPecsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.function.Consumer;

public class LowerBoundPecsDemo {
    private static void addSampleIds(List<? super Integer> target) {
        target.add(10);
        target.add(20);
    }

    private static <T> void appendAll(
            Iterable<? extends T> source,
            Collection<? super T> target) {
        for (T value : source) {
            target.add(value);
        }
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>();
        List<Number> numbers = new ArrayList<>(List.<Number>of(2.5));
        List<Object> objects = new ArrayList<>(List.of("header"));

        addSampleIds(integers);
        addSampleIds(numbers);
        addSampleIds(objects);
        System.out.println("integers = " + integers);
        System.out.println("numbers = " + numbers);
        System.out.println("objects = " + objects);

        List<? super Integer> sink = objects;
        Object existing = sink.get(0);
        System.out.println("existing sink value = " + existing);

        List<Integer> source = List.of(3, 1, 2);
        List<Number> destination = new ArrayList<>();
        appendAll(source, destination);
        System.out.println("appended numbers = " + destination);
        System.out.println("source unchanged = " + source);

        Comparator<Number> byNumber =
                Comparator.comparingDouble(Number::doubleValue);
        integers = new ArrayList<>(source);
        integers.sort(byNumber);
        System.out.println("sorted integers = " + integers);

        Consumer<Number> printer =
                value -> System.out.println("consume = " + value);
        integers.forEach(printer);

        List<Number> slots = new ArrayList<>(
                List.<Number>of(9.0, 9.0, 9.0));
        Collections.copy(slots, List.of(1, 2));
        System.out.println("copied into existing slots = " + slots);

        List<Number> capacityOnly = new ArrayList<>(10);
        try {
            Collections.copy(capacityOnly, List.of(1, 2));
        } catch (IndexOutOfBoundsException expected) {
            System.out.println("capacity alone is not enough for Collections.copy");
        }

        List<Integer> unmodifiable = List.of(1, 2);
        try {
            addSampleIds(unmodifiable);
        } catch (UnsupportedOperationException expected) {
            System.out.println("compatible type does not promise mutability");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 LowerBoundPecsDemo.java
java LowerBoundPecsDemo
```

Stdout:

```text
integers = [10, 20]
numbers = [2.5, 10, 20]
objects = [header, 10, 20]
existing sink value = header
appended numbers = [3, 1, 2]
source unchanged = [3, 1, 2]
sorted integers = [1, 2, 3]
consume = 1
consume = 2
consume = 3
copied into existing slots = [1, 2, 9.0]
capacity alone is not enough for Collections.copy
compatible type does not promise mutability
```

How to read the output:

1. The same lower-bounded method writes `Integer` values into three different kinds of targets.
2. The `List<Object>` target retains its pre-existing `"header"` element; reading through the lower bound can only rely on `Object`.
3. The `appendAll` function coordinates an `extends` source and a `super` target, adding elements to the target without clearing the source.
4. `Comparator<Number>` accepts `Integer` elements for comparison.
5. `Consumer<Number>` accepts each `Integer` from `forEach`.
6. `Collections.copy` replaces existing target positions and leaves extra positions untouched.
7. Reserving capacity alone is not enough to satisfy the size requirement of `Collections.copy`.
8. A compatible generic type does not make an unmodifiable list mutable.

The example uses separate source and target collections for `appendAll`, avoiding adding elements to the same collection currently being iterated.

## 12. Intentionally Non-Compiling Case

Save in a separate file `LowerBoundMustFail.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class LowerBoundMustFail {
    public static void main(String[] args) {
        List<? super Integer> target = new ArrayList<Integer>();
        target.add(2.5);
    }
}
```

Run:

```shell
javac --release 17 -encoding UTF-8 LowerBoundMustFail.java
```

**Expectation:** the compiler rejects `target.add(2.5)`.

The reason is that `target` may point to a `List<Integer>`, so it cannot guarantee accepting a `Double`. The error message may mention an unknown capture type; that is how the compiler represents the specific element type hidden behind the wildcard.

Do not place intentionally failing files into a source set that needs to build cleanly. This is a type-rule verification test, not a runnable program example.

## 13. Procedure for Choosing a Bound for a Parameter

For each generic method parameter, proceed step by step:

1. Choose the value type `T` that the method actually needs to process.
2. Determine whether the method takes `T` out of the parameter or puts `T` into it.
3. If taking values out as `T`, start by considering `? extends T`.
4. If putting `T` values in, start by considering `? super T`.
5. If an exact type relationship must be preserved across multiple places, consider a named type parameter.
6. Check mutability, `null` handling, size, and concurrency conditions outside the generic type system.
7. Test both calls that should be accepted and calls that must be rejected.

For example, with a list receiving `Integer`, verify that `List<Integer>`, `List<Number>`, and `List<Object>` all work, whereas `List<Double>` is rejected. This is how you evaluate flexibility without sacrificing type safety.

## 14. Common Mistakes

| Misconception | Correct understanding |
| --- | --- |
| `super Integer` means you can add any supertype of Integer | It guarantees the target accepts `Integer`; it does not guarantee accepting every `Number` or `Object` |
| A lower-bounded target contains only Integer | It could be a `List<Object>` with pre-existing data of other types |
| Reading from `List<? super Integer>` yields `Number` | Only `Object` is guaranteed |
| PECS is based on source/target variable names | You must look at the direction of data flow from the method's perspective |
| A consumer is always a target collection | A callback receiving elements is also a consumer of that type |
| Wildcards make a collection mutable | Mutability is still determined by the underlying object and API |
| Having capacity means `Collections.copy` will work | The destination must already have enough existing elements |
| Using `super` for both source and target is more flexible | The source would then not allow reading values as the required type `T` |
| Using `extends` for both sides still allows writing T | The target has an unknown element type and therefore cannot accept an arbitrary T |
| Suppressing warnings is a way to solve bound errors | It does not prove the data is type-safe |

## 15. Self-Practice

1. A method adds `Long` values to a collection. If you want it to accept `Collection<Long>`, `Collection<Number>`, and `Collection<Object>`, which signature should you start with?  
   **Answer:** `Collection<? super Long>`, along with the requirement that the target supports adding elements.

2. Why does `List<? super Integer>` not allow adding `Double`?  
   **Answer:** the actual list might have the element type `Integer`.

3. Why does reading from a lower-bounded target not guarantee returning an `Integer`?  
   **Answer:** the target could be a list of a broader type that already contains other values.

4. How should a function transferring integer data into a list of numbers set the wildcards on both sides?  
   **Hint:** the source produces a type usable as `T` using `extends`; the target consumes `T` using `super`.

5. Can a `Comparator<Object>` be used with `List<String>.sort` from a type perspective?  
   **Answer:** yes, because it can accept `String`. However, the comparison logic must still be genuinely valid for the elements and satisfy the comparator contract.

Lower bounds help write flexible data targets without losing type guarantees. PECS becomes easy to apply when you always clearly identify which values come out of the source, which values go into the target, and which requirements lie outside generic type checking.
