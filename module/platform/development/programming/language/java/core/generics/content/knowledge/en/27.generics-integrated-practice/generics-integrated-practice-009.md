# Building a Decision Table for `T`, `?`, `? extends`, `? super` and Self-Assessing Scenarios

## 1. Goal: Choosing Generics Syntax from Data Requirements

When writing a Java API, the key question is not "where can I sprinkle more wildcards?", but **which type relationship must the method contract express**. Four common choices are:

- **`T`**: a *named type variable*, declared on a class or method and usable in multiple positions to **link types together**.
- **`?`**: an *unbounded wildcard*, typically appropriate when code operates independently of element type.
- **`? extends T`**: an unknown type that is a compatible subtype of `T`, typically used when **reading data as `T`**.
- **`? super T`**: an unknown type that is `T` or a compatible supertype, typically used when **putting values of type `T` in**.

Short examples:

```java
static void inspect(List<?> items) { ... }

static double total(List<? extends Number> items) { ... }

static void append(List<? super Integer> items) { ... }

static <T> T first(List<T> items) { ... }
```

These are **illustrative signature templates**, not a complete Java file. Import `java.util.List`, define method bodies, and place them inside a class.

For this integrated practice, focus on answering three questions before choosing syntax:

1. **Does the method need to write elements into the structure, or only read?**
2. **Must the type on this parameter be linked to another parameter or the return type?**
3. **Which concrete parameterizations must callers be able to pass into the API?**

Choosing wrong often does not fail immediately at runtime: often the compiler rejects useful calls, or the API becomes too loose and forces unsafe casts. Choosing right preserves **type safety** while keeping callers flexible.

## 2. Quick Decision Table

| API boundary requirement | Typically appropriate choice | What it guarantees |
|---|---|---|
| Only read, count, print, or clear everything, ignoring element type | `List<?>` | Accepts `List<String>`, `List<Integer>`, ... |
| Read numbers and call `doubleValue()` | `List<? extends Number>` | Each element read can be used as `Number` |
| Add `Integer` values into a caller-supplied list | `List<? super Integer>` | Accepts `List<Integer>`, `List<Number>`, `List<Object>` |
| Input and output must share the same type parameter | `<T> T first(List<T>)` | Returns type `T` inferred from input |
| Transfer elements from source to destination | `<T> void copy(List<? extends T>, List<? super T>)` | Source supplies T, destination accepts T |
| Return a `List` with an explicit element type to caller | `List<T>` or `List<String>` | Caller knows exact type per contract |
| Compare `T` objects using a comparator for T or a supertype | `Comparator<? super T>` | Comparator consumes T |
| Transform `T` values to `R` values with a function | `Function<? super T, ? extends R>` | Function consumes T, produces R |
| Constrain a declared type variable to the numeric hierarchy | `<T extends Number>` | Bound on type parameter |
| Read-only nested lists of numbers | `List<? extends List<? extends Number>>` | Each level has its own read direction and bound |

**Mnemonic:** *Producer Extends, Consumer Super* — commonly abbreviated **PECS**. This is a rule of thumb for choosing **wildcards at generic type use sites**, not a substitute for analyzing data flow.

When a parameter must both receive and return a specific `T`, a type variable `<T>` or invariant `List<T>` may be necessary. Do not force wildcards everywhere.

## 3. Exact Read/Write Table with `List`

Assuming lists are **mutable** and have no other business constraints:

| Reference type | Safely read elements as | Which types can be `add`ed? | Can point to |
|---|---|---|---|
| `List<String>` | `String` | `String` | A list with static element type `String` |
| `List<Number>` | `Number` | `Number` and compatible subtypes | `List<Number>` |
| `List<Object>` | `Object` | Any reference value | `List<Object>` |
| `List<?>` | `Object` | Only `null` depending on mutability; cannot add arbitrary non-null values | `List<String>`, `List<Integer>`, ... |
| `List<? extends Number>` | `Number` | Only `null` depending on mutability; cannot add an arbitrary `Number` | `List<Integer>`, `List<Double>`, `List<Number>`, ... |
| `List<? super Integer>` | `Object` | `Integer` and valid subtypes of `Integer` (since `Integer` is final, `Integer` itself) | `List<Integer>`, `List<Number>`, `List<Object>` |
| `List<? super Number>` | `Object` | `Number` and subtypes of `Number`, such as `Integer`, `Double` | `List<Number>`, `List<Object>` |

Distinguish **"the compiler permits the `add` call"** from **"the underlying list object is mutable at runtime."** `List.of(...)` is unmodifiable: even `List<String>` cannot add elements at runtime. The table above describes **static type checking**, not a guarantee that every list is mutable.

`List<?>` and `List<? extends Number>` still allow many operations that do not require supplying a new value of the element type: `size`, `get`, `clear`, `remove` by index, or `add(null)` if the implementation allows it. Thus calling them "read-only lists" is an imprecise shorthand; they primarily **disallow adding non-null values of an arbitrary chosen type**.

## 4. Why Is `List<Integer>` Not a `List<Number>`?

In Java, generic types like `List<T>` are **invariant** by default:

```java
List<Integer> integers = new ArrayList<>();
// INTENTIONALLY DOES NOT COMPILE:
// List<Number> numbers = integers;
```

If that forbidden assignment were allowed, code could call `numbers.add(3.14)` and pollute a list expected to contain only `Integer`s.

Subtyping of elements **does not automatically propagate** to subtyping between two generic instantiations:

```text
Integer <: Number <: Object

List<Integer> is NOT a subtype of List<Number>
List<Integer> is a valid subtype of List<? extends Number>
List<Number> is a valid subtype of List<? super Integer>
```

The `extends` and `super` keywords in **wildcards** define a family of parameterized types a method can accept. They do not alter the actual class hierarchy.

Use `List<? extends Number>` when you need to **read as Number** from various list types. Use `List<? super Integer>` when you need to **write Integer** into various list types.

## 5. Runnable Example: `?`, `extends`, `super` in One Program

Create file **`WildcardChoiceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class WildcardChoiceDemo {

    static int count(List<?> values) {
        return values.size();
    }

    static double sum(List<? extends Number> values) {
        double result = 0;
        for (Number number : values) {
            result += number.doubleValue();
        }
        return result;
    }

    static void appendIntegers(List<? super Integer> target) {
        target.add(10);
        target.add(20);
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(1, 2, 3);
        List<Double> decimals = List.of(1.5, 2.5);
        List<Number> target = new ArrayList<>();

        appendIntegers(target);

        System.out.println(count(integers));
        System.out.println(sum(integers));
        System.out.println(sum(decimals));
        System.out.println(target);
        System.out.println(target.get(0) instanceof Number);
    }
}
```

JDK 17+ commands:

```bash
javac WildcardChoiceDemo.java
java WildcardChoiceDemo
```

Stdout:

```text
3
6.0
4.0
[10, 20]
true
```

Explanation:

- `count(List<?>)` needs no knowledge of element type, only calling `size`.
- `sum(List<? extends Number>)` reads every element as `Number`, accepting both `List<Integer>` and `List<Double>`.
- `appendIntegers(List<? super Integer>)` is allowed to add `Integer` into `List<Number>`.
- The method does not need to return a specific element type from `target`; calling `get` through `List<? super Integer>` only guarantees type `Object`.

If `target` were an unmodifiable `List.of(...)`, `appendIntegers` would throw `UnsupportedOperationException` even though static types match. Here `target` uses `ArrayList`.

## 6. When Do You Need a Type Variable `<T>` Instead of `?`?

A named type variable **links two or more type positions together**.

Example:

```java
static <T> T first(List<T> values) {
    return values.get(0);
}
```

Caller:

```java
List<String> words = List.of("A", "B");
String firstWord = first(words);
```

Here the compiler infers `T = String` from `List<String>` and yields return type `String`. If replaced with:

```java
static Object first(List<?> values) {
    return values.get(0);
}
```

the method still reads the right object, yet callers only see return type `Object`. The input/output type link has disappeared from the signature.

**Pragmatic rule:** If a type appears in **only one position and needs no name for linking**, a wildcard usually keeps the API shorter. If a type appears across multiple mutually constrained positions, `<T>` is usually valuable.

Subtle note: `<T>` can be inferred as a **common supertype** of the actual arguments in a call. It does not guarantee two runtime objects share the exact same concrete class. `<T>` is a static type constraint, not a runtime class-equality check.

## 7. Example: `<T>` Preserving Return Types and Copying Data

File **`TypeVariableDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class TypeVariableDemo {

    static <T> T first(List<T> values) {
        return values.get(0);
    }

    static <T> List<T> duplicate(List<? extends T> source) {
        return new ArrayList<>(source);
    }

    public static void main(String[] args) {
        List<String> words = List.of("An", "Binh");
        List<Integer> numbers = List.of(4, 5);

        String word = first(words);
        Integer number = first(numbers);
        List<String> copy = duplicate(words);

        System.out.println(word);
        System.out.println(number);
        System.out.println(copy);
    }
}
```

Run:

```bash
javac TypeVariableDemo.java
java TypeVariableDemo
```

Stdout:

```text
An
4
[An, Binh]
```

Analysis:

- `first` uses `T` in both the **list parameter** and the **return type**.
- `duplicate` uses `T` for the **return list**, while input `? extends T` accepts a producer of any compatible subtype.
- `new ArrayList<>(source)` creates a new mutable list; this is a **shallow copy**, without cloning elements.
- If you only need to print all elements as `Object`, there is no compelling reason to declare `<T>`: `List<?>` is simpler.

## 8. `<T extends Bound>` Is Not `? extends Bound`

This is the single most common confusion:

```java
static <T extends Number> T identity(T value) {
    return value;
}
```

`<T extends Number>` **declares type variable T** and constrains T to `Number` or a valid subtype.

By contrast:

```java
static double total(List<? extends Number> values) {
    // ...
    return 0;
}
```

`? extends Number` **does not declare a type variable**. It is a wildcard type argument at the `List` use site.

Comparison:

| Syntax | Where does it appear? | Meaning |
|---|---|---|
| `<T>` | Type parameter declaration | Names a type variable |
| `<T extends Number>` | Generic class/method declaration | Upper bound on a type variable |
| `List<T>` | Type use site, T already declared | Binds element type to T |
| `List<? extends Number>` | Type use site | An unknown element type at or below Number |
| `List<? super Integer>` | Type use site | An unknown element type that is Integer or a supertype |
| `<T super Number>` | Illegal in Java | No lower-bound syntax exists for type parameters |
| `List<? extends T>` | Type use site, T in scope | Producer of T or subtype |
| `List<? super T>` | Type use site, T in scope | Consumer of T or supertype |

Java does not allow `<T super Number>`. `super` belongs in **wildcard type arguments**, not as a lower bound on type parameter declarations.

A type variable can also declare multiple upper bounds:

```java
<T extends Number & Comparable<T>>
```

whereas a wildcard `? extends Number & Comparable<...>` is not an equivalent way to write intersection bounds in ordinary Java type arguments.

## 9. Combining `T`, `extends`, and `super`: Moving Source to Destination

A classic PECS problem is copying elements from one collection to another. The API should be flexible enough for:

- `List<Integer>` → `List<Number>`: valid.
- `List<Integer>` → `List<Object>`: valid.
- `List<Double>` → `List<Number>`: valid.
- `List<Number>` → `List<Integer>`: **unsafe**: source could contain Double.

Signature:

```java
static <T> void transfer(
        List<? extends T> source,
        List<? super T> target) {
    for (T value : source) {
        target.add(value);
    }
}
```

This is an illustrative method; place inside a class and import `List`.

Meaning:

- `T` links source and destination.
- Source is a **producer**, hence `? extends T`.
- Target is a **consumer**, hence `? super T`.

The compiler solves for a suitable `T` from the call's constraints. This structure does not require source and target to have identical element types.

## 10. Hands-On Check: Moving One Element with PECS

Unlike appending the entire source, the next method **removes the first element from source** and puts it into destination. This is a revealing test because having the right generic types is not enough: source must actually support `remove`, and destination must support `add`.

File **`PecsMoveDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class PecsMoveDemo {
    static <T> void moveFirst(
            List<? extends T> source,
            List<? super T> destination) {
        if (!source.isEmpty()) {
            T element = source.remove(0);
            destination.add(element);
        }
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>(List.of(1, 2, 3));
        List<Number> numbers = new ArrayList<>(List.of(0.5));
        moveFirst(integers, numbers);

        System.out.println(integers);
        System.out.println(numbers);
    }
}
```

Run:

```bash
javac --release 17 PecsMoveDemo.java
java PecsMoveDemo
```

Stdout:

```text
[2, 3]
[0.5, 1]
```

**Why does it compile?** `source` allows reading an element compatible with `T`; `destination` accepts `T`. The two collections need not share the same type argument: an `Integer` is read and added into `List<Number>`.

**Why is that not enough for runtime safety?** If you replace `integers` with `List.of(1, 2, 3)`, `remove(0)` throws `UnsupportedOperationException`; generic signatures do not guarantee mutability. If `destination.add` fails after removing from source, the operation does not roll back automatically: that is a **partial failure** a production transfer API must handle.

Try modifying the code to pass `List<Number>` as source and `List<Integer>` as destination. The compiler must reject this reversed direction; do not force it through with a raw cast.

## 11. Producer/Consumer Compatibility Matrix

| Actual source or target | API `List<? extends Number>` | API `List<? super Integer>` | Explanation |
|---|---|---|---|
| `List<Integer>` | Accepted | Accepted | Integer is a subtype of Number and is Integer itself |
| `List<Double>` | Accepted | Rejected | Double is not a supertype of Integer |
| `List<Number>` | Accepted | Accepted | Number matches the upper bound and is a supertype of Integer |
| `List<Object>` | Rejected | Accepted | Object is not a subtype of Number, but is a supertype of Integer |
| `List<String>` | Rejected | Rejected | String belongs to neither bound relationship |

This table covers **type compatibility of list arguments**, not whether a method using the corresponding wildcard can perform arbitrary operations on the list.

For instance, an API taking `List<? extends Number>` accepts `List<Integer>`, yet **cannot** arbitrarily call `add(3.14)`, because the underlying list may only accept Integer.

For `List<? super Integer>`, `get` only guarantees `Object`: the backing list might be `List<Object>`, so never assume every element in it is an Integer.

## 12. `? extends` Does Not Mean "The List Is Read-Only"

Saying "producer extends" helps choose type arguments, not define full list mutability.

Example:

```java
static void removeEverything(List<? extends Number> values) {
    values.clear();
}
```

This is a valid method inside a class (assuming `List` is imported). `clear()` requires passing no element of the unknown type, so the compiler permits it. At runtime, if the implementation is a mutable `ArrayList`, it clears all elements; if it is `List.of`, it throws `UnsupportedOperationException`.

Operations like `size`, `isEmpty`, `contains`, `get`, and `clear` do not supply a new value of the unknown element type. By contrast:

```java
// INTENTIONALLY DOES NOT COMPILE:
void bad(List<? extends Number> values) {
    values.add(42);
}
```

An arbitrary `Number` is not guaranteed to match the concrete captured element type, such as when `values` actually refers to a `List<Double>`.

`null` is a special case that can pass generic compile-time checking on `add`, though the implementation may forbid mutation or null. Never design a producer API around calling `add(null)` unless business contracts explicitly require it.

## 13. `? super` Does Not Mean "Everything Can Be Added"

Consider:

```java
List<? super Integer> target = new ArrayList<Number>();
```

Operations:

```java
target.add(1);                // Valid: Integer
target.add(Integer.valueOf(2)); // Valid
Object item = target.get(0); // Valid
```

However:

```java
// INTENTIONALLY DOES NOT COMPILE:
target.add(3.5);              // Double is not an Integer
Integer x = target.get(0);   // get only guarantees Object
```

Why does the compiler disallow reading as Integer? `target` could refer to a `List<Object>` that already contains non-Integer objects. Even though **the values this method itself just added** are Integers, other elements in the list are not constrained by the wildcard contract to be Integer.

If you truly need to read back the exact values you just inserted as Integer, keep references to those objects or redesign the API; never cast the entire `List<? super Integer>` to `List<Integer>`.

## 14. Example: Mixed Read/Write Tasks and Wildcard Effects

File **`ConsumerReadBackDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ConsumerReadBackDemo {

    static void append(List<? super Integer> target) {
        target.add(7);
        target.add(8);
    }

    public static void main(String[] args) {
        List<Object> objects = new ArrayList<>();
        objects.add("old");

        append(objects);

        Object first = objects.get(0);

        System.out.println(first);
        System.out.println(objects);
        System.out.println(objects.get(1) instanceof Integer);
    }
}
```

Compile and run:

```bash
javac ConsumerReadBackDemo.java
java ConsumerReadBackDemo
```

Stdout:

```text
old
[old, 7, 8]
true
```

The actual list is `List<Object>`, and it already held a String before Integers were added. Thus the consumer method should treat `get` results only as `Object`.

If the implementation must inspect mixed data, use `instanceof` or separate validation logic — never assume `? super Integer` makes all pre-existing elements Integers.

## 15. When Only Printing or Counting: `?` Beats an Unnecessary Type Variable

Compare:

```java
static <T> void printAll(List<T> values) {
    values.forEach(System.out::println);
}
```

with:

```java
static void printAll(List<?> values) {
    values.forEach(System.out::println);
}
```

Both are illustrative methods requiring `List` to be imported.

If `T` does not appear in the return type, does not relate to another parameter, and is not used in logic requiring a concrete link, **the wildcard is shorter and expresses intent better**.

Using `?` lets callers pass `List<String>`, `List<Integer>`, or `List<LocalDate>` without the method declaring a `<T>` just to look generic.

Do not mechanically replace `List<T>` with `List<?>` if an internal helper needs to pass a `T` element to another API constrained by `T`. Whenever **a type relationship must be preserved**, a named type variable remains essential.

## 16. Wildcard Capture: Testing Keeping the Same Type Across Two Accesses

A `List<?>` has **an unknown element type**, not by default `List<Object>`. If you read an element and write it back into **that same list**, a generic helper can preserve the type relationship without casts.

Instead of repeating a swap algorithm, try a new requirement: **replace the last element with the first element**, keeping list size unchanged.

File **`CaptureLastDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class CaptureLastDemo {
    static void copyFirstToLast(List<?> values) {
        copyCaptured(values);
    }

    private static <T> void copyCaptured(List<T> values) {
        if (values.size() >= 2) {
            T first = values.get(0);
            values.set(values.size() - 1, first);
        }
    }

    public static void main(String[] args) {
        List<String> words = new ArrayList<>(List.of("A", "B", "C"));
        List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3));

        copyFirstToLast(words);
        copyFirstToLast(numbers);

        System.out.println(words);
        System.out.println(numbers);
    }
}
```

Run:

```bash
javac --release 17 CaptureLastDemo.java
java CaptureLastDemo
```

Stdout:

```text
[A, B, A]
[1, 2, 1]
```

At the public boundary, `List<?>` lets callers pass a list of any element type. Inside the helper, the compiler **captures the exact wildcard of one list object per call**, infers `T`, and permits `get` and `set` under the same type. Never hardcode `T` as `String` by guessing; `List<Integer>` must run safely too.

Self-check exercise: (1) Why is `Object first = values.get(0); values.set(0, first);` invalid directly inside a method accepting `List<?>`? (2) If writing elements from a different list, what condition must be added? **Answer:** (1) `Object` does not guarantee the captured element type; (2) you need a type variable/wildcard linking source and destination as in PECS, rather than pairing two independent `?` wildcards.

`List.of(...)` is unmodifiable; the method calls `set`, so the example uses `ArrayList`. Generic capture protects **type relationships**, not mutability or index bounds.

## 17. Choosing `Collections.copy` vs. `addAll`: Two Different Contracts

Both can transfer `Integer`s into `List<Number>` type-safely, yet **how they modify the list** differs:

| Intent | Choice | Conditions/effects |
|---|---|---|
| **Append** elements from source | `destination.addAll(source)` | Destination must support addition; size usually increases |
| **Overwrite** existing slots | `Collections.copy(destination, source)` | Destination must have **size ≥ source.size()** and support `set` |
| Reserve capacity only, with no elements yet | `new ArrayList<>(capacity)` | `size() == 0`; cannot satisfy `Collections.copy` for non-empty source |

Java 17 example inside a method importing `java.util.*`:

```java
List<Integer> source = List.of(7, 8);
List<Number> overwrite = new ArrayList<>(List.of(0, 0, 99));
List<Number> append = new ArrayList<>(List.of(99));

Collections.copy(overwrite, source);
append.addAll(source);

System.out.println(overwrite); // [7, 8, 99]
System.out.println(append);    // [99, 7, 8]
```

If you write `List<Number> empty = new ArrayList<>(source.size());` and call `Collections.copy(empty, source)`, generic types still match, yet runtime throws `IndexOutOfBoundsException` because **capacity is not size**. That is an **API contract** bug, not a PECS bug.

To remember parameter order, `Collections.copy(destination, source)` takes **destination first, source second**. The right choice requires both checks: *can the types transfer safely?* and *does the runtime operation need append or overwrite, with sufficient elements and mutability?*

## 18. The `sort` Method: Why Does Comparator Use `? super T`?

Signature of `List.sort`:

```java
void sort(Comparator<? super E> c)
```

where `E` is the List's element type.

A Comparator is an object that **consumes two `E` instances** to compare them, so a comparator written for a compatible supertype can compare `E` instances too.

File **`ComparatorWildcardDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class ComparatorWildcardDemo {
    record Person(String name, int age) {
    }

    static <T> void sortWith(
            List<T> values, Comparator<? super T> comparator) {
        values.sort(comparator);
    }

    public static void main(String[] args) {
        List<Person> people = new ArrayList<>(List.of(
                new Person("Binh", 21),
                new Person("An", 20)
        ));

        Comparator<Person> byName =
                Comparator.comparing(Person::name);

        sortWith(people, byName);

        System.out.println(
                people.stream().map(Person::name).toList());
    }
}
```

Run:

```bash
javac ComparatorWildcardDemo.java
java ComparatorWildcardDemo
```

Stdout:

```text
[An, Binh]
```

A `Comparator<Object>` may be type-compatible with `Comparator<? super Person>`, yet **generic type validity does not guarantee the comparator implements a meaningful domain ordering**.

Do not change it to `Comparator<? extends T>`: a comparator must **accept** T for `compare`, not produce T.

## 19. `Function<? super T, ? extends R>`: Two Directions in One Signature

`Function<T, R>` **accepts T** and **returns R**. A flexible helper can accept:

```java
Function<? super T, ? extends R>
```

Because:

- Function input is a consumer of T → `? super T`.
- Function output is a producer of R → `? extends R`.

File **`FunctionVarianceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;

public class FunctionVarianceDemo {

    static <T, R> List<R> transform(
            List<? extends T> source,
            Function<? super T, ? extends R> mapper) {

        List<R> result = new ArrayList<>();

        for (T element : source) {
            result.add(mapper.apply(element));
        }

        return result;
    }

    public static void main(String[] args) {
        List<Integer> source = List.of(2, 3);

        Function<Number, String> description =
                n -> "value=" + n.intValue();

        List<String> output = transform(source, description);

        System.out.println(output);
    }
}
```

Compile and run:

```bash
javac FunctionVarianceDemo.java
java FunctionVarianceDemo
```

Stdout:

```text
[value=2, value=3]
```

`List<Integer>` produces elements compatible with `T = Number`; `Function<Number,String>` consumes them; the resulting list has `R = String`.

This contract illustrates that **PECS applies to generic functional interfaces too** — not only collections.

## 20. Nested Generics: Each Level Must Be Analyzed

Given two generic layers:

```java
List<List<Integer>>
```

This cannot automatically be treated as `List<List<Number>>`, because generic invariance applies at **every level**.

However, if the API only reads groups of numbers, you can use:

```java
List<? extends List<? extends Number>>
```

The outer `? extends` says "elements are a compatible kind of List"; the inner `? extends Number` says "elements of each list can be read as Number."

File **`NestedWildcardDemo.java`**:

```java
import java.util.List;

public class NestedWildcardDemo {

    static double sumAll(
            List<? extends List<? extends Number>> groups) {

        double sum = 0;

        for (List<? extends Number> group : groups) {
            for (Number value : group) {
                sum += value.doubleValue();
            }
        }

        return sum;
    }

    public static void main(String[] args) {
        List<List<Integer>> batches =
                List.of(List.of(1, 2), List.of(3));

        System.out.println(sumAll(batches));
    }
}
```

Run:

```bash
javac NestedWildcardDemo.java
java NestedWildcardDemo
```

Stdout:

```text
6.0
```

`List<List<Integer>>` is not a subtype of `List<List<Number>>`, yet it matches the multi-level wildcard structure for a **read-only** problem.

Be careful if you want to add a new list into the outer collection: the outer wildcard also has an unknown captured element type, so the compiler forbids inserting an arbitrary `List<Number>`.

## 21. Return Types: Why Avoid `List<?>` When Callers Need Typed Data?

An API might return:

```java
List<?> load();
```

If there genuinely is no schema element type, this return type is honest: callers only know they receive a list of unknown elements.

But if the producer knows the list contains Strings, the signature:

```java
List<String> loadNames();
```

conveys more information; callers can read elements as `String` without casts.

With a generic factory:

```java
static <T> List<T> empty() {
    return new ArrayList<>();
}
```

callers can write:

```java
List<String> names = empty();
```

The compiler uses the target type to infer T.

A `List<? extends Number>` return type can fit if an API deliberately hides a subtype while allowing reads as Number. However, it makes life harder for callers who want to add Number values. Never use wildcard return types merely to make code look "more generic" when a concrete result type or named type variable is clearer.

## 22. When Must `T` Be Used Across Multiple Inputs?

Consider two variables sharing an element type:

```java
static <T> void moveOne(List<T> source, List<T> target) {
    target.add(source.remove(0));
}
```

This method works inside a class importing `List`. It requires both lists to be viewed under the same `T` for reading and writing; yet that can be **too strict** if source is `List<Integer>` and target is `List<Number>`.

More flexible:

```java
static <T> void moveOne(
        List<? extends T> source,
        List<? super T> target) {
    target.add(source.remove(0));
}
```

This change allows valid subtype relationships without losing safety. Because the intent is "remove one element and transfer it," source must be mutable; generic type checking does not guarantee `remove` succeeds on `List.of`.

**Lesson:** Use T to **link**, and consider wildcards around T to express variance along the data flow.

## 23. `?` and `Object` Are Not Equivalent

Example:

```java
List<String> strings = List.of("a", "b");

List<?> unknown = strings; // Valid.

// INTENTIONALLY DOES NOT COMPILE:
// List<Object> objects = strings;
```

`List<?>` accepts a list of any type argument. `List<Object>` is a list whose exact element type is `Object`; it cannot directly accept `List<String>`.

A method accepting `List<Object>` could add an `Integer`; if the compiler permitted passing `List<String>` there, the `List<String>` contract would break. That is why Java disallows the conversion.

If you only iterate and print, `List<?>` is a better choice than `List<Object>`. If you genuinely want a heterogeneous container where code may add `String`, `Integer`, and so on, `List<Object>` expresses that contract accurately.

## 24. Do Not Use Raw Types to Be "More Flexible"

A raw type:

```java
List raw = new ArrayList();
```

discards type arguments instead of expressing flexible type relationships. It generates `rawtypes` warnings and makes certain method invocations unchecked.

A proper design:

```java
static void show(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

retains compiler checking while accepting lists of varied element types.

Do not replace `List<? extends Number>` with raw `List` and manually cast each element to Number to avoid writing wildcards. When reading numbers, the bounded wildcard expresses the constraint at compile time with far better diagnostics.

Enable:

```bash
javac -Xlint:rawtypes,unchecked YourClass.java
```

to find raw/unchecked boundaries in real code. `@SuppressWarnings` is not a fix for wrong type relationships.

## 25. `extends`/`super` Do Not Dictate `null` or Mutability

A `List<? super Integer>` might be a mutable `ArrayList<Object>` or a collection forbidding additions. A `List<? extends Number>` might contain null elements if its implementation permits them.

Generic types constrain only the **element type**, leaving unspecified:

- Is `null` permitted?
- Are add/remove/set operations permitted?
- Can multiple threads mutate concurrently?
- Can data be mutated through another reference?
- Are there ordering or uniqueness constraints?

For example, `List.of(1,2)` forbids `add` because it is unmodifiable, regardless of whether viewed as `List<Integer>` or `List<? extends Number>`.

When writing production APIs, document mutability, ownership, and nullability conditions **separately** alongside the generic signature, and test each operational path.

## 26. Selection Table for Common Java APIs

| API or scenario | Key signature/pattern | Why |
|---|---|---|
| `Collections.copy` | `<T> copy(List<? super T> dest, List<? extends T> src)` | Source producer, destination consumer |
| `List.sort` | `sort(Comparator<? super E>)` | Comparator accepts E to compare |
| `Collection.addAll` | `addAll(Collection<? extends E>)` | Source collection produces E values |
| `Stream.map` | `Function<? super T, ? extends R>` | Function consumes T, produces R |
| `Collections.max` (with comparator) | `<T> T max(Collection<? extends T>, Comparator<? super T>)` | Source reads T, comparator consumes T, returns T |
| Iterate without needing type linkage | `void inspect(Collection<?>)` | No need to name T |
| Extract an element preserving element type | `<T> T first(List<T>)` | Input linked to return type |
| Transfer `List<Integer>` to `List<Number>` | `<T> transfer(List<? extends T>, List<? super T>)` | Fits subtype–supertype relationship |
| Accept a list truly storing Objects and adding mixed types | `List<Object>` | Concrete element type Object |

The signatures in this table are **condensed study patterns**. When calling real APIs, check the exact overload's Javadoc; beyond Generics, there are preconditions like capacity/size, mutability, `null`, and comparator contracts.

## 27. Choosing Syntax Using 5 Questions

When designing a method, walk through this sequence:

**Question 1: Do you need to call operations relying on a specific element type?**

- If only `size`, `isEmpty`, generic logging: consider `<?>`.
- If reading as `Number` to call `doubleValue`: consider `<? extends Number>`.

**Question 2: Do you need to insert objects of type X into a caller-supplied collection?**

- If adding `Integer`: `<? super Integer>` fits better than `<? extends Integer>`.
- If only adding the exact declared element type: `List<T>` may fit.

**Question 3: Must types at two positions be linked to each other?**

- Input and return share a type: declare `<T>`.
- Source and sink are linked: `<T>` combined with `? extends T`/`? super T`.

**Question 4: Do callers need to pass subtypes/supertypes?**

- Overly strict `List<T>` everywhere blocks safe calls like `List<Integer>` → `List<Number>`.
- Apply appropriate variance where data flow permits.

**Question 5: What lies outside generic type checking?**

- Null, mutability, indices, concurrency, type erasure, nested content.
- Add explicit contracts and tests accordingly.

Choose the **simplest signature that accurately expresses the required relationships**, not the one with the most wildcards.

## 28. Self-Assessment — Part A: Choose One of the Four Forms

For each requirement, choose from **`T` / `?` / `? extends` / `? super`** before checking the answers.

| ID | Scenario | API template to fill in |
|---|---|---|
| A1 | Accept any list to print element count | `void count(List<...> list)` |
| A2 | Sum any `Number` from specialized lists | `sum(List<...> list)` |
| A3 | Allow callers to pass `List<Object>` to add `Integer` | `append(List<...> dest)` |
| A4 | Return the exact element type of the passed list | `static <...> ... first(List<...>)` |
| A5 | Transfer `List<Double>` to `List<Number>` | `transfer(List<...> src, List<...> dst)` |
| A6 | Read any list solely as `Object` | `inspect(List<...>)` |
| A7 | Sort `List<Person>` using a compatible `Comparator<Object>` | `sort(List<T>, Comparator<...>)` |
| A8 | Function taking T and producing R, allowing supertype input/subtype output | `Function<..., ...>` |
| A9 | Type variable accepting only `Number` and subtypes | `static <...> ...` |
| A10 | Swap two elements inside a `List<?>` | Helper using a captured type variable |

### Answers for Part A

| ID | Choice | Brief reason |
|---|---|---|
| A1 | `List<?>` | Independent of element type |
| A2 | `List<? extends Number>` | Reads elements as Number |
| A3 | `List<? super Integer>` | Destination accepts Integer |
| A4 | `<T> T first(List<T>)` | T links input and output |
| A5 | `<T> transfer(List<? extends T>, List<? super T>)` | Two-sided PECS |
| A6 | `List<?>` | Unknown element type, read-only as Object |
| A7 | `Comparator<? super T>` | Comparator consumes T |
| A8 | `Function<? super T, ? extends R>` | Function consumes T, returns R |
| A9 | `<T extends Number>` | Upper bound on type variable declaration |
| A10 | `<T>` on helper taking `List<T>` | Captures wildcard so `set` writes the same element type |

Self-scoring: **2 points** for each correct choice with a data-flow explanation, **1 point** if correct without explanation, **0 points** if wrong. Maximum **20 points** for Part A.

This is a self-study rubric, not output from an automated grader.

## 29. Self-Assessment — Part B: Does It Compile?

Evaluate each snippet with proper imports, inside a method, assuming variables are declared right before use. Mark **valid** or **invalid**, then state why.

**B1**

```java
List<Integer> xs = new ArrayList<>();
List<? extends Number> ys = xs;
```

**B2**

```java
List<Integer> xs = new ArrayList<>();
List<Number> ys = xs;
```

**B3**

```java
List<Object> objects = new ArrayList<>();
List<? super Integer> sink = objects;
sink.add(10);
```

**B4**

```java
List<? super Integer> sink = new ArrayList<Number>();
Integer n = sink.get(0);
```

**B5**

```java
List<? extends Number> source = List.of(1, 2);
Number n = source.get(0);
```

**B6**

```java
List<? extends Number> source = new ArrayList<Integer>();
source.add(10);
```

**B7**

```java
List<?> any = new ArrayList<String>();
any.add(null);
```

**B8**

```java
List<?> any = new ArrayList<String>();
any.add("new");
```

**B9**

```java
List<? super Number> sink = new ArrayList<Object>();
sink.add(1.5);
```

**B10**

```java
List<? super Number> sink = new ArrayList<Integer>();
```

**B11**

```java
List<List<Integer>> batches = List.of(List.of(1));
List<? extends List<? extends Number>> readOnly = batches;
```

**B12**

```java
List<String> names = new ArrayList<>();
names.sort(Comparator.naturalOrder());
```

### Answers and Reasons for Part B

| ID | Result | Reason |
|---|---|---|
| B1 | Valid | `Integer` is under `Number`; upper-bounded wildcard accepts it |
| B2 | Invalid | Generic invariance |
| B3 | Valid | `Object` is a supertype of `Integer`; adding Integer is safe |
| B4 | Type-invalid | `get` only guarantees `Object`; cannot assign directly to `Integer`. Even if changed to `Object`, `get(0)` would throw `IndexOutOfBoundsException` because the new list is empty |
| B5 | Valid | Reading Number from an upper-bounded wildcard |
| B6 | Invalid | Cannot add an arbitrary Integer to `? extends Number` |
| B7 | Type-valid | `null` can be passed to `add` on an unknown wildcard; the backing `ArrayList` here is mutable |
| B8 | Invalid | Cannot add non-null String when captured element type is unknown |
| B9 | Valid | `Number` is the lower bound; can add `Double`, which is a subtype of Number |
| B10 | Invalid | `Integer` is not a supertype of `Number` |
| B11 | Valid | Upper-bounded wildcards at both levels allow reading nested lists |
| B12 | Valid | `String` has a natural order, and the comparator matches `sort`'s parameter type |

Question B4 is especially instructive: distinguish the **compile-time error** of assigning `Object` to Integer from the **runtime error** of reading index 0 on an empty list if the variable type is changed.

Score **1 point** per correct answer, up to **12 points**.

## 30. Self-Assessment — Part C: Fix Wrong or Overly Strict APIs

### C1. Read-only yet signature is too rigid

Original:

```java
static void printAll(List<Object> items) {
    for (Object item : items) {
        System.out.println(item);
    }
}
```

Problem: callers cannot pass `List<String>` directly even though the method only reads.

**Answer:** Change to `List<?>`.

### C2. Summing using raw List

Original:

```java
static double sum(List numbers) {
    double result = 0;
    for (Object n : numbers) {
        result += ((Number) n).doubleValue();
    }
    return result;
}
```

**Preferred answer:** `static double sum(List<? extends Number> numbers)`. Then iterate with `for (Number n : numbers)` so the compiler enforces the contract.

### C3. Only adding Integers yet destination parameter is too narrow

Original:

```java
static void addDefaults(List<Integer> dest) {
    dest.add(1);
}
```

If it should also accept `List<Number>` and `List<Object>`:

**Answer:** Change to `List<? super Integer>`.

### C4. Need to return the exact element type

Original:

```java
static Object first(List<?> items) {
    return items.get(0);
}
```

If callers expect `String` when passing `List<String>`:

**Answer:** `static <T> T first(List<T> items)`.

### C5. Copying Integer source into Number destination

Original:

```java
static <T> void copy(List<T> src, List<T> dst) {
    dst.addAll(src);
}
```

To support safe subtype relationships:

**Answer:** `static <T> void copy(List<? extends T> src, List<? super T> dst)`.

### C6. Comparator given `extends`

Original:

```java
static <T> void sort(
        List<T> values, Comparator<? extends T> cmp) {
    // Cannot be used directly for values.sort(cmp).
}
```

**Answer:** A comparator consumes T, so use `Comparator<? super T>`.

### C7. Mapper with reversed variance

Original:

```java
Function<? extends T, ? super R> mapper
```

This is generally wrong when the method **passes T into the function and reads R out**.

**Answer:** `Function<? super T, ? extends R>`.

### C8. Read-only nested list

Original:

```java
static double sumGroups(List<List<Number>> groups) {
    // ...
    return 0;
}
```

To accept `List<List<Integer>>`:

**Answer:** Use `List<? extends List<? extends Number>>` if both levels are only read.

Part C does not require rewriting full classes; the goal is explaining **public API signatures**. Score 0–2 points per scenario (choice + explanation), up to **16 points**.

## 31. Three Bonus Challenges That Should Not Be Solved with Casts

### Challenge 1 — Copy then sort

Must accept `Collection<? extends T>`, create a `List<T>`, and sort with `Comparator<? super T>`.

Hint:

```java
static <T> List<T> sortedCopy(
        Collection<? extends T> source,
        Comparator<? super T> order) {
    List<T> result = new ArrayList<>(source);
    result.sort(order);
    return result;
}
```

Place inside a class and import `java.util.Collection`, `List`, `ArrayList`, `Comparator`.

Do not cast `Collection<? extends T>` to `Collection<T>`: the constructor accepts the producer directly without a cast.

### Challenge 2 — Swap inside `List<?>`

Requirement: public method accepts `List<?>` without raw types or unchecked casts.

**Answer:** Delegate to a helper `<T> void swapCaptured(List<T>, int, int)` from wrapper `swapAny(List<?>, int, int)` as in section 16. This is wildcard capture.

### Challenge 3 — Store mixed unrelated values in one structure

Do not use `List<? super Integer>` if the goal is storing both Strings and Integers where the intended element type really is Object.

**Answer:** `List<Object>` is right when code needs to add varied reference types and read them as Object. PECS is not the answer to every collection problem.

## 32. Combined Self-Assessment Rubric

Maximum points across the three quiz and API-fixing parts:

| Part | Items | Max points |
|---|---:|---:|
| A. Syntax direction choices | 10 | 20 |
| B. Does it compile? | 12 | 12 |
| C. Fixing API signatures | 8 | 16 |
| **Total** | **30** | **48** |

Suggested self-interpretation (study rubric only):

- **0–20 points:** review invariance and the difference between reading and writing.
- **21–32 points:** basic syntax understood; practice type inference and multi-parameter signatures.
- **33–41 points:** right choice in most scenarios; focus on nested generics, capture, and mutability.
- **42–48 points:** solid foundation; try designing APIs from real requirements and reviewing edge cases.

Scores carry no certification meaning; what matters more is that **every choice has a data-flow explanation** and avoids unchecked casts.

To verify, place snippets marked **invalid** into a separate test file, run `javac`, and read the diagnostics directly. Do not put intentionally broken lines into runnable demo files with verified stdout.

## 33. Common Thinking Errors

**Error 1 — "Using extends makes the list read-only."** Inaccurate; operations taking no element-type values like `clear()` still compile, subject to runtime mutability.

**Error 2 — "Using super lets you read T."** No; reading from `List<? super T>` only guarantees safe typing as `Object`.

**Error 3 — "`List<Integer>` is a `List<Number>`."** False due to invariance. Use `List<? extends Number>` if you only need a producer.

**Error 4 — "`List<?>` is the same as `List<Object>`."** No; an unknown wildcard differs from a concrete Object element type.

**Error 5 — "`?` always makes an API better than `<T>`."** No; type variables link inputs, outputs, and multiple parameters.

**Error 6 — "`<T extends Number>` and `? extends Number` are identical."** No; one declares a type variable, the other is a wildcard type argument at a use site.

**Error 7 — "You can declare `<T super Integer>`."** Illegal in Java.

**Error 8 — "`List<? super Number>` accepts `List<Integer>`."** No; Integer is not a supertype of Number.

**Error 9 — "A method adding Integer to `List<? super Integer>` guarantees all elements are Integers."** No; the list may already hold other objects.

**Error 10 — "Use `Comparator<? extends T>` because the comparator relates to T."** Wrong direction: a comparator **consumes** T, so it needs `? super T`.

**Error 11 — "Function input should be extends, output should be super."** Backwards for standard data flow; the flexible form is `Function<? super T, ? extends R>`.

**Error 12 — "One level of wildcard handles all nested generics."** No; variance must be analyzed at each layer of `List<List<T>>`.

**Error 13 — "Use raw List and cast to silence compile errors."** Drops safety and introduces unchecked warnings and heap pollution.

**Error 14 — "`List<T>` forces identical runtime concrete classes everywhere."** No. The compiler can infer T as a common supertype; Java generic type variables are not runtime equality assertions.

**Error 15 — "A generic signature indicates the list is mutable."** No; `List.of` remains unmodifiable.

**Error 16 — "`Collections.copy` automatically grows the destination."** No; the destination must already hold enough elements to replace.

**Error 17 — "Wildcard capture requires an unchecked cast."** No; a generic helper captures wildcards safely.

**Error 18 — "Wildcard return types are always most flexible."** No; callers often need explicit type arguments to operate cleanly without casts.

**Error 19 — "`? extends T` allows adding any subtype of T."** No; the actual captured subtype may be narrower than the value being added.

**Error 20 — "PECS guarantees thread safety or null safety."** No; those are type contracts, not concurrency or data policies.

## 34. Pre-Finalization Generic API Checklist

1. State clearly whether each parameter is **read**, **written**, or **both**.
2. Ask whether the element type must appear in the return type or another parameter.
3. If no type linkage is needed, consider wildcard `?`.
4. If reading under an upper bound, consider `? extends Bound`.
5. If writing `T` values into a consumer, consider `? super T`.
6. If linking input and output, declare `<T>` or `<T, R>` explicitly.
7. When combining source and sink, test the PECS signature against concrete subtypes and supertypes.
8. Try compiling with `List<Integer>`, `List<Number>`, and `List<Object>` to catch inverted bounds.
9. Never substitute `List<Object>` for `List<?>` when an API only reads any list.
10. Never use raw types to bypass generic inference errors.
11. For nested types, analyze each wildcard level separately.
12. When hitting capture errors, consider a `<T>` helper instead of unchecked casts.
13. When using a comparator, confirm the **consumer** direction of `Comparator<? super T>`.
14. When using a function, confirm `super` input and `extends` output.
15. Check null, mutability, ownership, and index preconditions outside the type signature.
16. Choose return types that give callers adequate information, avoiding wildcards where unnecessary.
17. Write compile-time tests for both accepted and rejected calls.
18. Compare against standard Java APIs using the same patterns.
19. Enable `javac -Xlint:unchecked,rawtypes` when working with legacy code.
20. Document why each wildcard was chosen rather than merely writing "uses PECS."

## 35. Summary and Standard References

A quick cheat sheet:

```text
Element type does not matter           → ?
Read values as Bound                   → ? extends Bound
Add T values into destination          → ? super T
Link input/output or multiple positions → <T>
```

Do not pick by syntax appearance. **Trace the data flow**: where are values produced, where are values consumed, and which type relationships must hold between parameters and results.

In Java, **`T` is a named type variable; `?` is an unknown wildcard; `? extends` creates a producer view, `? super` creates a consumer view**. Generic invariance explains why wildcards are needed to permit subtypes/supertypes where safe.

This integrated practice is complete when you can write and explain these signatures yourself:

```java
static void inspect(List<?> values)

static double sum(List<? extends Number> values)

static void append(List<? super Integer> destination)

static <T> T first(List<T> values)

static <T> void copy(
        List<? extends T> source,
        List<? super T> destination)

static <T, R> List<R> map(
        List<? extends T> source,
        Function<? super T, ? extends R> mapper)
```

These are **illustrative signature templates**; do not copy them as bodyless declarations expecting them to compile. Practice using the complete runnable programs in the earlier sections.

Java 17 standard references:

- [JLS §4.5 — Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5): type arguments and wildcards.
- [JLS §4.4 — Type Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.4): T and upper bounds.
- [JLS §4.10 — Subtyping](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.10): generic subtyping rules.
- [JLS §5.1.10 — Capture Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.10): wildcard capture.
- [JLS §18 — Type Inference](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html): inference for generic methods.
- [Java SE 17 `java.util.Collections`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html): `copy`, `max`, `sort`.
- [Java SE 17 `java.util.List`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): `addAll`, `sort`, `get`, `set`.
- [Java SE 17 `java.util.function.Function`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html): functional interface taking T and returning R.
- [Java SE 17 `java.util.Comparator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html): generic comparator and `? super T`.