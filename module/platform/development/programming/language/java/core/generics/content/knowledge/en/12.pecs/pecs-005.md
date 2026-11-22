# When to Use a Wildcard and When to Name a Type Parameter in Java Generics

## 1. The Type Design Question: `?` or `<T>`?

In Java generics, a **wildcard** `?` represents an unknown type, whereas a **named type parameter** such as `T`, `E`, `K`, or `V` allows multiple positions in a method signature to **refer to a shared type relationship**. Both can make an API flexible, yet they express different information.

For example, a method that only needs to count elements:

~~~java
static int count(List<?> values) {
    return values.size();
}
~~~

Here `?` is sufficient: there is no reason to name the element type. A signature `static <T> int count(List<T> values)` could also be used, but `T` conveys no additional useful relationship.

Conversely, a method that takes the first element and **returns the exact element type supplied by the caller** needs `T`:

~~~java
static <T> T first(List<T> values) {
    return values.get(0);
}
~~~

With `List<String>`, the result has type `String`; with `List<Integer>`, the result has type `Integer`. Replacing `T` with `?` would lose the link between the **input element type** and the **return value type**.

The rest of this lesson helps you:

- Correctly choose `?`, `? extends T`, and `? super T` according to the data direction of the **PECS** (*Producer Extends, Consumer Super*) rule.
- Recognize when to declare `<T>` or `<T, R>` to express a relationship across multiple positions.
- Combine wildcards and type parameters in **the same signature**, rather than treating them as mutually exclusive choices.
- Understand why a public method accepting `List<?>` sometimes must call a `<T>` helper to preserve **wildcard capture**.
- Avoid signatures that are too strict, too broad, or force callers to resort to raw types or unchecked casts.

## 2. Type Mechanism: “No Need to Know the Name” vs. “Must Refer to the Same Name”

Consider three signatures:

~~~java
static void showAll(List<?> values) { /* ... */ }

static double sum(List<? extends Number> values) { /* ... */ }

static <T> T selectFirst(List<T> values) { return values.get(0); }
~~~

These snippets **illustrate signatures**; they must be placed in a class with `import java.util.List` if compiled standalone.

- `List<?>`: **an unknown element type**; every element can be read as `Object`. Useful when the algorithm does not need any element-specific API.
- `List<? extends Number>`: **an unknown subtype of `Number`**; every element can be read as `Number`, so `doubleValue()` can be called.
- `<T> T selectFirst(List<T>)`: names `T` in both input and output. A caller passing `List<String>` gets `String`, with no cast needed.

You can read `?` as “what the concrete type is does not matter to the API's promise.” You can read `T` as “the concrete type may differ between calls, but **all positions mentioning `T` within the same call must satisfy the constraints of `T`**.”

**Note on signatures:** `?` is a *type argument* inside `List<?>`, `Class<?>`, etc.; you **cannot** use a standalone `?` as a return type like `static ? first(...)`. To return a value whose type is tied to the input, you need a named type variable or a concrete type.

## 3. Use Wildcards When Type Identity Does Not Need to Be Preserved Across Positions

### 3.1. Only Observing Data Through `Object`'s API: `?`

~~~java
static void printItems(List<?> items) {
    for (Object item : items) {
        System.out.println(item);
    }
}
~~~

`printItems(List.of("A", "B"))` and `printItems(List.of(1, 2))` are both valid. The method does not care about `String` or `Integer`; every object can be printed via `println(Object)`.

The variant with a type parameter below adds no safety:

~~~java
static <T> void printItemsWithT(List<T> items) {
    for (T item : items) {
        System.out.println(item);
    }
}
~~~

If `T` does not appear in **any other meaningful position** and the method body does not require preserving type identity, a wildcard states the intent more clearly. This is a **design rule**; the compiler does not forbid declaring a single-use type parameter.

### 3.2. Only Reading Against an Upper Bound: `? extends T`

~~~java
static double average(List<? extends Number> numbers) {
    if (numbers.isEmpty()) {
        throw new IllegalArgumentException("empty list");
    }
    double sum = 0;
    for (Number number : numbers) {
        sum += number.doubleValue();
    }
    return sum / numbers.size();
}
~~~

For instance, it can accept `List<Integer>`, `List<Long>`, `List<Double>`, etc. Because the algorithm only needs methods on `Number` and **does not return values in the original subtype**, adding `<T extends Number>` is unnecessary.

Compare signatures:

~~~java
// Clear enough when only using Number for reading:
static double average(List<? extends Number> numbers) { /* ... */ }

// Valid, but T does not serve any relationship:
static <T extends Number> double averageWithT(List<T> numbers) { /* ... */ }
~~~

The two blocks above only compare **signatures** (the `/* ... */` bodies do not provide a complete implementation returning `double`). In real code, use the `average` implementation above.

**Mechanism:** with `List<? extends Number>`, the compiler only knows elements have a capture type `CAP <: Number`. `Number` can be read, but you cannot call `add(Integer)` or `add(Double)` arbitrarily because `CAP` could be a different subtype. The `extends` wildcard suits a position that **supplies data for the method to read**.

### 3.3. Only Writing to a Destination: `? super T`

~~~java
static void addDefaults(List<? super Integer> target) {
    target.add(10);
    target.add(20);
}
~~~

You can pass `List<Integer>`, `List<Number>`, or `List<Object>`. All three accept `Integer` values.

With `List<? super Integer>`, the compiler **only guarantees** the read type of `get(...)` is `Object`, because the actual list might be a `List<Object>` already containing other values. The contract here focuses on **writing data**. There is no need to declare `<T extends Integer>` just to add known `Integer` values.

### 3.4. Applying PECS by Parameter Role

| Role the method needs | Usually suitable signature | Reason |
| --- | --- | --- |
| Only counting, printing, or handling as `Object` | `List<?>` | No need to know element kind. |
| Reading `Number` values | `List<? extends Number>` | Every element is guaranteed to be a `Number`. |
| Adding `Integer` to a destination list | `List<? super Integer>` | Every supertype of `Integer` can accept `Integer`. |
| Reading and writing back elements under **the same hidden type** | `List<?>` + helper `<T>`, or `List<T>` | Must preserve the capture type inside the operation. |
| Returning the input's exact element type | `<T> T first(List<T>)` | Input/output relationship requires a shared name `T`. |
| Appending source to destination with linked types | `<T> void append(List<? extends T>, List<? super T>)` | `T` links both positions; wildcards express producer/consumer. |

PECS looks at **the element data flow relative to the method**: a parameter is a *producer* when it supplies elements to read, and a *consumer* when it receives elements to write. It does not mean `? extends` turns a collection immutable or `? super` forbids reading; other operations still depend on the specific API/implementation.

## 4. Naming `T` When Preserving a Relationship Between Parameter and Result

An API that gets the first element:

~~~java
static Object firstObject(List<?> values) {
    return values.get(0);
}
~~~

It accepts any kind of list, but the caller only gets `Object`. If the original kind must be returned, use:

~~~java
static <T> T firstTyped(List<T> values) {
    return values.get(0);
}

String s = firstTyped(List.of("Lan", "Minh"));
Integer n = firstTyped(List.of(2, 4, 6));
~~~

This example includes call lines placed inside **a valid Java method or block**; `List` must be imported. There is no unchecked cast. The compiler infers `T = String` or `T = Integer` from the argument and context.

So should you write:

~~~java
static <T> T firstFromExtends(List<? extends T> values) {
    return values.get(0);
}
~~~

That is also **valid**. This signature permits lists whose elements are subtypes of `T`; it also lets type inference choose a broader `T` based on context. The difference between `List<T>` and `List<? extends T>` must be weighed according to the contract, not out of a hunch that “extends is always better.”

Keep in mind the empty-list case: both `firstTyped` and `firstFromExtends` here throw `IndexOutOfBoundsException` if `get(0)` is called when there are no elements. Generics only control **types**, not that a list has at least one element.

### 4.1. When the Result Involves Multiple Related Types

If a method converts `T` to `R`, the two names carry independent meanings:

~~~java
static <T, R> List<R> mapAll(
        List<? extends T> source,
        java.util.function.Function<? super T, ? extends R> mapper) {
    List<R> output = new ArrayList<>();
    for (T value : source) {
        output.add(mapper.apply(value));
    }
    return output;
}
~~~

This snippet is an **illustrative method**, placed in a class with `import java.util.List` and `java.util.ArrayList` to compile. It shows:

- `T` is the type read from the source list.
- `R` is the resulting type produced.
- `? extends T` allows the source to supply a subtype of `T`.
- `Function<? super T, ? extends R>` accepts a `T` value and returns `R` or a subtype of `R`.
- `List<R>` expresses an output typed precisely as `R`.

Using wildcards **inside** the generic declaration `Function<...>` does not make `T` and `R` redundant; on the contrary, these names tie the data types together across source, mapper, and result.

## 5. Naming `T` When Expressing a Relationship Between Multiple Parameters

Suppose we want to copy elements **by appending them to the end of a destination list**. The source may contain `Integer`, while the destination is declared as `List<Number>`.

Use a method type parameter to state clearly that the source produces `T` and the destination accepts `T`:

~~~java
static <T> void appendAll(
        List<? extends T> source,
        List<? super T> target) {
    for (T item : source) {
        target.add(item);
    }
}
~~~

Valid example:

~~~java
List<Integer> source = List.of(1, 2, 3);
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

appendAll(source, numbers);
appendAll(source, objects);
~~~

**Why not just unnamed wildcards?**

~~~java
// DOES NOT compile: the two ? represent two independent unknown types.
static void badAppend(List<?> source, List<?> target) {
    for (Object element : source) {
        target.add(element); // Cannot verify element matches target's type.
    }
}
~~~

`List<?>` does not tell the compiler how the source and target types relate. Using `<T>` forms a **bridge** between the two parameters. The two wildcards `? extends T` and `? super T` make the signature both safe and not overly restrictive.

### 5.1. Why Is `List<T>` on Both Sides Often Too Strict?

~~~java
// May be too restrictive for producer -> consumer needs:
static <T> void appendStrict(List<T> source, List<T> target) {
    target.addAll(source);
}
~~~

With `List<Integer>` and `List<Number>`, the call `appendStrict(ints, numbers)` does not compile: generic `List<T>` is invariant, and one `T` cannot simultaneously equal both `Integer` and `Number` for those two parameterized types.

For an element-transfer operation, what must be proven is not that **both lists have the same type argument**, but that **every element from source is assignable to target**. `<T> List<? extends T>` and `List<? super T>` express that exact dependency.

### 5.2. Comparison with the Standard API

`java.util.Collections.copy` uses:

~~~java
public static <T> void copy(
        List<? super T> dest,
        List<? extends T> src);
~~~

This is an **API signature**, not a method definition with a body to compile on its own. `copy` **overwrites elements at corresponding positions** in the destination and requires the destination to have enough elements; it does not behave like `appendAll` adding at the end. Both still share the same producer/consumer contract pattern.

The standard method `Collection<E>.addAll(Collection<? extends E> c)` also illustrates the rule: `E` is already **named at the interface level** as the destination's element type; thus the source parameter only needs the wildcard `? extends E`, without declaring an extra single-use `<S extends E>`.

## 6. Special Case: Wildcard Capture Forces a `<T>` Helper

An API taking `List<?>` cannot always finish its work within the same method body. Some operations need to **take an element out and write it back into that very collection**.

For example, trying to swap the first and last elements:

~~~java
// DOES NOT compile:
static void badSwap(List<?> list) {
    list.set(0, list.get(list.size() - 1));
}
~~~

At first glance this looks safe because it reads from and writes to **the same list**. However, each expression involving an unnamed element type can be processed by the compiler with distinct capture variables, so the compiler cannot prove the value transfer as written above.

The right design is **a public API using a wildcard to accept any list**, paired with a private helper naming the capture type:

~~~java
static void swapEnds(List<?> values) {
    swapEndsCaptured(values);
}

private static <T> void swapEndsCaptured(List<T> values) {
    if (values.size() < 2) {
        return;
    }
    int lastIndex = values.size() - 1;
    T first = values.get(0);
    values.set(0, values.get(lastIndex));
    values.set(lastIndex, first);
}
~~~

At the call `swapEndsCaptured(values)`, type inference and capture conversion let Java temporarily name the single element type of **the same list** as `T` inside the helper. From there, `get`/`set` share `T` and need no cast.

This is the distinction between:

- **API surface:** the caller does not need to know the element type, so it uses `List<?>`.
- **Implementation:** when the algorithm must move values of the same element type across multiple expressions, a `<T>` helper helps the compiler represent that relationship.

If the caller passes an unmodifiable `List.of(...)`, `set` throws `UnsupportedOperationException` at runtime. A swap method must receive a mutable list (such as `ArrayList`). Type safety and mutability are two separate contracts.

## 7. Complete, Compilable, and Runnable Java 17+ Program

Create the file **WildcardOrTypeParameterDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class WildcardOrTypeParameterDemo {
    static double average(List<? extends Number> values) {
        if (values.isEmpty()) {
            throw new IllegalArgumentException("empty list");
        }
        double sum = 0.0;
        for (Number value : values) {
            sum += value.doubleValue();
        }
        return sum / values.size();
    }

    static String summary(List<?> values) {
        return "size=" + values.size();
    }

    static <T> T first(List<T> values) {
        return values.get(0);
    }

    static <T> void appendAll(List<? extends T> source, List<? super T> target) {
        for (T item : source) {
            target.add(item);
        }
    }

    static void swapEnds(List<?> values) {
        swapEndsCaptured(values);
    }

    private static <T> void swapEndsCaptured(List<T> values) {
        if (values.size() < 2) {
            return;
        }
        int lastIndex = values.size() - 1;
        T first = values.get(0);
        values.set(0, values.get(lastIndex));
        values.set(lastIndex, first);
    }

    public static void main(String[] args) {
        List<Integer> ids = List.of(2, 4, 6);
        System.out.println("average: " + average(ids));
        System.out.println("summary: " + summary(ids));

        String name = first(List.of("Lan", "Minh"));
        System.out.println("first: " + name);

        List<Number> destination = new ArrayList<>(List.of(1.5));
        appendAll(ids, destination);
        System.out.println("copied: " + destination);

        List<String> names = new ArrayList<>(List.of("A", "B", "C"));
        swapEnds(names);
        System.out.println("swapped: " + names);
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -Xlint:all WildcardOrTypeParameterDemo.java
java WildcardOrTypeParameterDemo
~~~

**Exact stdout**:

~~~text
average: 4.0
summary: size=3
first: Lan
copied: [1.5, 2, 4, 6]
swapped: [C, B, A]
~~~

This file compiled with `javac --release 17 -Xlint:all` and ran successfully with zero unchecked warnings.

Each section explains a design choice:

1. `average` only reads `Number`, so it uses `? extends Number`.
2. `summary` does not need the element type, so it uses `?`.
3. `first` returns the exact element type, so it needs type parameter `T`.
4. `appendAll` passes `T` from source to target, so it needs `T` to connect the two wildcards.
5. `swapEnds` accepts any `List<?>`, while the helper uses `T` to keep the relationship between two elements of the same list.

## 8. Situations to Check Carefully Before Choosing

### 8.1. When One Container Needs Both Reading and Writing Data of the Same Type

If an API needs to take `T` from a collection, transform or swap it, and write **back `T` values of the same type**, a named `List<T>` or capture helper is usually clearer than `List<? extends T>` / `List<? super T>`. The “producer extends, consumer super” rule is not meant to force wildcards on every operation where one variable is both producer and consumer.

Example:

~~~java
static <T> void replaceFirst(List<T> list, T value) {
    list.set(0, value);
}
~~~

`T` ensures `value` matches the element type of `list`. Note that `set` can throw `IndexOutOfBoundsException` if the list is empty or `UnsupportedOperationException` if unmodifiable.

### 8.2. A Single-Use Type Parameter Is Not Automatically Wrong

The guideline “if `T` is mentioned only once, use a wildcard” is a **signature design** heuristic, not a mandatory syntax rule. Exceptions exist: a type parameter used in another type parameter's bound, complex inference, interface contracts that must remain compatible, or an internal implementation needing a name for the capture type.

For instance, `<T extends Number> void observe(List<T>)` can be simplified to `void observe(List<? extends Number>)` when you only need to read as `Number`. However, do not alter public signatures arbitrarily if changing them affects binary/source compatibility in an existing system; evaluate callers, overloads, and overridden methods.

### 8.3. A Type Parameter Can Link Multiple Positions Indirectly Through Bounds

The letter `T` does not have to appear in literally two parameters. Example:

~~~java
static <T extends Comparable<? super T>> T chooseMax(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
~~~

`T` appears in the input, output, and the bound `Comparable<? super T>`. The `? super T` wildcard on `Comparable` states that comparison can accept `T` even if the implementation compares via a supertype of `T`. Here a named type parameter and a wildcard **complement each other**.

### 8.4. Return Positions Should Usually Provide the Most Useful Type

A method returning `List<?>` or `List<? extends Number>` may be valid, but the caller will have to work through a view with less type information. If the method knows the exact element type or can preserve `T` from an input parameter, returning `List<T>` is usually easier to use.

~~~java
static <T> List<T> mutableCopy(List<? extends T> source) {
    return new ArrayList<>(source);
}
~~~

A caller passing `List<String>` can receive `List<String>`. When an API intentionally advertises only “some kind of Number,” a wildcard return type can be appropriate, though you must be aware of the limitation on the caller.

### 8.5. A Named Type Parameter Does Not Mean Two Arguments Have the Same Runtime Class

The compiler verifies **assignability/type relationships by signature**, not whether two objects share the same `getClass()`. Even when type inference selects a single shared `T`, `T` can be an interface or superclass.

Example:

~~~java
static <T extends Number> void acceptPair(T a, T b) {
    System.out.println(a.doubleValue() + b.doubleValue());
}

acceptPair(10, 2.5); // Can infer T as a suitable supertype of Integer and Double.
~~~

Thus “same `T`” does not necessarily mean **same concrete class**. It means every `T` position obeys a shared system of type constraints inferred by the compiler.

## 9. How to Choose with a Consistent Process

When designing a new generic method, follow these steps in order:

1. **Trace the element path:** where does the method take data from, where does it send data, and does it return an element or a new collection?
2. **Isolate observation-only cases:** if you only need `size()`, `Object`, or element-type-independent handling, try `<?>`.
3. **Choose bounds for one-way operations:** only reading `Number` → `? extends Number`; only adding `Integer` → `? super Integer`.
4. **Find mandatory relationships:** if the return value must retain a parameter's type, or source and destination must satisfy a relationship, declare a name `<T>` or `<T,R>`.
5. **Replace type variables used solely for flexibility:** when an `S extends T` appears in only one parameterized argument and contributes to no other relationship, consider writing `? extends T` / `? super T`.
6. **Use a wildcard capture helper when needed:** the public API can take `<?>` while an internal helper uses `<T>` to operate between elements of the same capture.
7. **Compile actual call sites:** test important calls, compiler diagnostics, and `javac -Xlint:unchecked`; do not conclude from a single idealized example alone.

Quick decision table:

| Situation | Choice | Why |
| --- | --- | --- |
| `print(List<...>)` does not care about kind | `List<?>` | No type name needed. |
| `sum(List<...>)` only reads numbers | `List<? extends Number>` | Sufficient guarantee of `Number`. |
| `fill(List<...>)` only adds Integer | `List<? super Integer>` | Consumer accepts `Integer` values. |
| `first(...)` returns input element kind | `<T> T first(List<T>)` | Connects input and return. |
| `append(source,target)` | `<T> void append(List<? extends T>,List<? super T>)` | Connects source and target. |
| `swap(List<?>)` avoids exposing type | `List<?>` API + `<T>` helper | Captures same type for `get`/`set`. |
| `map(source,mapper)` returns new result type | `<T,R>` + wildcards on source/mapper | Connects source, transform, and result. |

## 10. Common Errors, Symptoms, and Fixes

### Error 1 — Using `<T>` Meaninglessly

~~~java
static <T> int size(List<T> values) {
    return values.size();
}
~~~

You can write `static int size(List<?> values)`. `T` here merely lengthens the code without preserving any useful relationship.

### Error 2 — Using `<?>` and Expecting to Return a Concrete `T`

~~~java
static Object firstUnknown(List<?> values) {
    return values.get(0);
}

// String name = firstUnknown(List.of("Lan")); // DOES NOT compile.
~~~

If the exact type must be returned, write `<T> T first(List<T>)`. **Downcasting** after receiving `Object` is no substitute for the static proof provided by a generic method.

### Error 3 — Using `extends` at a Write Destination

~~~java
static void brokenAdd(List<? extends Number> target) {
    target.add(10); // DOES NOT compile.
}
~~~

Switch to `List<? super Integer>` if only adding `Integer`, or use `List<Number>` if the contract genuinely requires a list of `Number` elements.

### Error 4 — Using `super` at a Source That Needs to Read Number

~~~java
static double brokenSum(List<? super Number> values) {
    double result = 0;
    for (Number n : values) { // DOES NOT compile: elements read out are only guaranteed as Object.
        result += n.doubleValue();
    }
    return result;
}
~~~

Switch to `List<? extends Number>` if elements are used as `Number`.

### Error 5 — Merging Every Wildcard into a Single `T`

If two parameters are **unrelated**, do not force them to share `T`:

~~~java
static void printPairSizes(List<?> left, List<?> right) {
    System.out.println(left.size() + ":" + right.size());
}
~~~

The function can accept `List<String>` together with `List<Integer>`. There is no need to force them into a single shared type argument.

### Error 6 — Fixing Type Errors with Raw `List` or Unchecked Casts

~~~java
// Warning/risk: raw type hides type information.
List raw = new ArrayList<String>();
List<Integer> ints = raw; // Unchecked conversion.
~~~

This does not establish a valid subtype relationship and can lead to `ClassCastException` when reading. Redesign the signature with appropriate wildcards and type parameters, or validate data at the boundary of legacy APIs.

### Error 7 — Confusing Type Parameter Information with Runtime Bounds

Because of **type erasure**, `List<String>` and `List<Integer>` do not retain concrete type arguments that can be checked with `instanceof List<String>`. A named `T` helps **the compiler** verify type relationships; it is not an automatic “runtime proof.” If runtime validation is needed, inspect actual elements or use a `Class<T>` token where appropriate.

## 11. Review

1. To print `size()` of any list, should you choose `<T> void f(List<T>)` or `void f(List<?>)`? **`List<?>`** is simple and loses no needed relationship.
2. To sum both `List<Integer>` and `List<Double>` using only `Number.doubleValue()`? **`List<? extends Number>`**.
3. To write `Integer` into `List<Integer>`, `List<Number>`, or `List<Object>`? **`List<? super Integer>`**.
4. Why does `<T> T first(List<T>)` need `T`? **So that the result's type is tied to the input element type at the same call site.**
5. Why is `appendAll(List<?>, List<?>)` not enough to insert elements? **The two wildcard types are not proven to have a producer/consumer relationship; a shared type parameter is needed to connect both positions.**
6. Why might a `swapEnds(List<?>)` API still need a `<T>` helper? **To capture an unknown element type and use the same name `T` across both read and write operations.**
7. Does `<T>` guarantee every argument at runtime has the same class? **No.** Type inference can pick a common supertype.
8. Is the rule “if `T` is used once, change it to `?`” always true? **Not strictly.** Check whether `T` contributes to bounds, return types, other relationships, or constraints of an existing API.

## 12. References

- [JLS Java SE 17 §4.5.1 — Type Arguments of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.1): explains wildcards, type-argument containment, and examples where a single-use type parameter should be replaced by a wildcard.
- [JLS Java SE 17 §5.1.10 — Capture Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.10): the basis for converting a wildcard's unknown type into a temporary type variable.
- [Oracle Java Tutorials — Guidelines for Wildcard Use](https://docs.oracle.com/javase/tutorial/java/generics/wildcardGuidelines.html): choosing `extends`/`super` by producer/consumer and notes on method return types.
- [Oracle Java Tutorials — Wildcard Capture and Helper Methods](https://docs.oracle.com/javase/tutorial/java/generics/capture.html): why a generic helper is used to capture a wildcard.
- [Java SE 17 API — Collections.copy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#copy(java.util.List,java.util.List)): standard signature combining `<T>`, `? super T`, and `? extends T`.
- [Java SE 17 API — Collection.addAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#addAll(java.util.Collection)): `Collection<? extends E>` inside an interface that already names `E`.
