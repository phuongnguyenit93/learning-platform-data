# Meaning of `? extends T` in Java Generics

## 1. What Does `? extends T` Represent?

In Java Generics, `? extends T` is an **upper-bounded wildcard**. This syntax states that the actual type argument of a generic type is **an unknown type, but that type must be `T` or a subtype of `T`**.

```java
List<? extends Number> values;
```

In the declaration above, `values` can reference `List<Number>`, `List<Integer>`, `List<Double>`, `List<Long>`, and any other `List<S>` where `S` is a subtype of `Number`. However, at the usage site of the variable `values`, the compiler does not know the exact type `S`.

There are two parts to read separately:

- **`?`**: represents an unknown type argument; it is not `Object` and does not mean arbitrary values can be written.
- **`extends T`**: constrains the unknown type argument to belong to the set of `T` and subtypes of `T`; `T` is called the *upper bound*.

The word `extends` in a wildcard is a **type bound**. It works both when the upper bound is a class (`Number`) and when the upper bound is an interface (`CharSequence`, `Comparable<?>`, etc.). The upper bound `T` does not need to be a direct superclass; indirect subtype relationships are also valid.

```java
List<Integer> integers = new ArrayList<>();
List<Double> doubles = new ArrayList<>();
List<Number> numbers = new ArrayList<>();

List<? extends Number> a = integers;
List<? extends Number> b = doubles;
List<? extends Number> c = numbers;
```

All three assignments are valid. These are **reference assignments**; they do not create a new list and do not convert all elements to `Number` in memory.

**Key point:** `? extends Number` states that *the element type of the list lies under the bound `Number`*, rather than stating that *each addition can choose any subtype of `Number`*.

## 2. The Unknown Type Model: Why Knowing the Upper Bound Still Leaves the Exact Type Unknown?

Imagine a method that accepts `List<? extends Number>`. One caller may pass a list containing only `Integer`, while another passes a list containing only `Double`. Inside the method body, we do not know which call will occur.

```java
static void inspect(List<? extends Number> source) {
    Number value = source.get(0); // Valid when the list is not empty
}
```

The compiler has enough information to conclude that **every element read out can be treated as `Number`**. However, it does not have enough information to conclude that a new `Integer` can be written into a list that might actually be a `List<Double>`.

We can visualize the relationship as follows:

```text
                   Number
               /      |      \
          Integer   Double   Long
               \      |      /
          ? extends Number
          (an unknown type in the group above)
```

The diagram only illustrates the possibilities under the upper bound; the `?` **does not change the actual type** of each referenced list.

In practice, the compiler may use an internal *capture type* (for example, a placeholder name representing the unknown type such as `CAP#1`) to remember the constraint. We do not write that internal type name in source code. What matters is that operations on `List<? extends Number>` must remain safe for **every** type that could possibly substitute for the wildcard.

## 3. Invariance of Generics and the Role of `extends`

Even though `Integer extends Number`, Java Generics are **invariant** (invariant with respect to type arguments): `List<Integer>` is not a subtype of `List<Number>`.

Here is a snippet demonstrating the compile error:

```java
List<Integer> integers = new ArrayList<>(List.of(1, 2));

// List<Number> numbers = integers; // Does not compile
```

If that assignment were allowed, users of `numbers` could add a `Double` into a list promised to contain only `Integer`. Java prevents this through compile-time checking.

When an API only **needs to retrieve values as `Number`**, we can relax the input contract to:

```java
static double sum(List<? extends Number> source) {
    double total = 0;
    for (Number number : source) {
        total += number.doubleValue();
    }
    return total;
}
```

Now both `List<Integer>` and `List<Double>` are valid arguments. The API still guarantees that elements read out can be used as `Number`.

| Argument type passed | `List<Number>` | `List<? extends Number>` |
|---|---|---|
| `List<Number>` | Allowed | Allowed |
| `List<Integer>` | No | Allowed |
| `List<Double>` | No | Allowed |
| `List<java.math.BigDecimal>` | No | Allowed |
| `List<Object>` | No | No |
| `List<String>` | No | No |

`Object` is a supertype of `Number`, so `List<Object>` does not satisfy `? extends Number`. `String` does not extend `Number`. Remember that accepting a list argument depends on its **declared type parameter**, not merely on inspecting a few elements that happen to be inside it.

## 4. Read Access: What Does the Upper Bound Guarantee to the Compiler?

With `List<? extends Number>`, every element read out can be safely assigned to `Number` or `Object`:

```java
List<Integer> integers = List.of(10, 20, 30);
List<? extends Number> source = integers;

Number first = source.get(0);  // Allowed
Object same = source.get(0);   // Allowed
int size = source.size();      // Allowed
double value = first.doubleValue();

// Integer exact = source.get(0); // Not allowed: ? could be Double
```

Methods defined on `Number`, such as `intValue()`, `longValue()`, and `doubleValue()`, can be called. A method belonging only to `Integer` cannot be called directly on a value with static type `Number` without appropriate checking or casting.

For example:

```java
static void printAsDouble(List<? extends Number> source) {
    for (Number item : source) {
        System.out.println(item.doubleValue());
    }
}
```

This method is determined to be valid by the **upper bound** of the wildcard. If the upper bound is `CharSequence`, elements read out can be used as `CharSequence` and `length()` can be called; they cannot be assumed to be `String`.

Note: `source.get(0)` is only valid at runtime if the list has elements. `extends` does not guarantee that the list is non-empty, does not prevent `null` values, does not guarantee that the list is mutable, and does not guarantee that numeric values fit business requirements. For instance, `doubleValue()` can lose precision with very large integers or `BigDecimal`; type bounds and numeric precision are two separate concerns.

## 5. Write Access: Why Can't We Add `Integer`, `Double`, or `Number`?

Given the declaration:

```java
List<? extends Number> source = new ArrayList<Integer>();
```

Behind `source` may be a `List<Integer>`. If the compiler allowed adding a `Double`, the contract of the original list would be broken. Yet even `source.add(123)` is disallowed, because at another call site `source` could just as easily reference a `List<Double>`.

```java
List<? extends Number> source =
        new ArrayList<Integer>(List.of(1, 2, 3));

// source.add(42);            // Compile error
// source.add(2.5);           // Compile error
// source.add((Number) 42);   // Still a compile error
// source.set(0, 42);         // Compile error
```

Even if the argument is written as a `Number`, we only know the unknown type `S extends Number`. From "`Integer` is a `Number`" it does not follow that "`Integer` is assignable to every `S` among the subtypes of `Number`".

One exception in type checking is `null`:

```java
List<Integer> integers = new ArrayList<>(List.of(1, 2));
List<? extends Number> view = integers;

view.add(null); // Compiles because null can be assigned to any reference type
```

The `ArrayList` in this example allows `null`, and `null` is actually added to the list. However, **not every `List` implementation allows modification or adding `null`**. For example, `List.of(...)` creates an unmodifiable list; calling `add` will throw `UnsupportedOperationException`. Clearly distinguish between **an operation being accepted by the type system** and **an operation succeeding at runtime**.

## 6. The `extends` Wildcard Does Not Make a List Immutable

`List<? extends Number>` restricts the **types of values allowed to be inserted through that reference**, rather than making the source object immutable. If the underlying source is an `ArrayList<Integer>`, another `List<Integer>` alias can still modify its elements, and operations that do not require supplying a new element, such as `clear()` or `remove(int)`, still compile through the wildcard.

```java
List<Integer> original = new ArrayList<>(List.of(4, 5, 6));
List<? extends Number> source = original;
source.remove(0);
System.out.println(original); // [5, 6]
```

With an unmodifiable list, a removal operation may throw `UnsupportedOperationException`. To protect contents, alias management, unmodifiable wrappers, or snapshots are needed; the dedicated lesson on **wildcards and immutability** will analyze those options in detail.

## 7. Complete Java 17 Example: Reading, Transferring Data, and Preserving Type Safety

Create the file `ExtendsWildcardDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class ExtendsWildcardDemo {
    static double sum(List<? extends Number> source) {
        double result = 0;
        for (Number n : source) {
            result += n.doubleValue();
        }
        return result;
    }

    static void transfer(
            List<? extends Number> source,
            List<? super Number> destination) {
        for (Number n : source) {
            destination.add(n);
        }
    }

    static void swapFirstTwo(List<? extends Number> source) {
        swapCaptured(source);
    }

    private static <E extends Number> void swapCaptured(List<E> values) {
        if (values.size() < 2) {
            return;
        }
        E first = values.get(0);
        values.set(0, values.get(1));
        values.set(1, first);
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>(List.of(10, 20, 30));
        List<Double> doubles = List.of(1.5, 2.5);

        System.out.println("Integer sum: " + sum(integers));
        System.out.println("Double sum: " + sum(doubles));

        List<Number> combined = new ArrayList<>();
        transfer(integers, combined);
        transfer(doubles, combined);
        System.out.println("Combined: " + combined);

        List<? extends Number> view = integers;
        Number first = view.get(0);
        System.out.println("First: " + first);

        swapFirstTwo(view);
        System.out.println("After swap: " + integers);

        view.add(null);
        System.out.println("After null: " + integers);
    }
}
```

Compile and run:

```bash
javac ExtendsWildcardDemo.java
java ExtendsWildcardDemo
```

Stdout:

```text
Integer sum: 60.0
Double sum: 4.0
Combined: [10, 20, 30, 1.5, 2.5]
First: 10
After swap: [20, 10, 30]
After null: [20, 10, 30, null]
```

Program analysis:

1. `sum` accepts a source whose type argument is `Number` or any of its subtypes. The method body only needs to read each element as `Number` and invoke `doubleValue()`.
2. `transfer` uses the `List<? extends Number>` source to read numbers safely. The `List<? super Number>` destination is a list whose element type is `Number` or one of its supertypes (`Object`), so it allows adding `Number` values. `combined` is a new `List<Number>`, not an alias of `integers` or `doubles`.
3. `view` references the same list as `integers`. `get(0)` returns a value that can be safely read as `Number`.
4. `swapFirstTwo` does not create a new `Integer` or `Double` to add to the list. It swaps two existing elements through a helper that preserves the same unknown element type. Section 8 explains this mechanism.
5. `view.add(null)` is valid at compile time. Because the actual object is an `ArrayList<Integer>`, adding `null` succeeds and the result appears in `integers`. If `sum(integers)` were called again after this step, the loop calling `n.doubleValue()` on `null` would cause a `NullPointerException`; the example deliberately computes the sums before adding `null`.

The numeric results in the example are all exact in `double` representation, so stdout is deterministic. In applications requiring monetary calculation or decimal precision, adding via `doubleValue()` should not be used in place of an appropriate numeric model.

## 8. Wildcard Capture: How Can Elements Be Swapped?

Each `? extends Number` is an **unknown but consistent element type**. When we need to write back the exact elements retrieved from the same list, a generic helper can *capture* that unknown type:

```java
static void swapFirstTwo(List<? extends Number> source) {
    swapCaptured(source);
}
private static <E extends Number> void swapCaptured(List<E> xs) {
    if (xs.size() < 2) return;
    E first = xs.get(0);
    xs.set(0, xs.get(1));
    xs.set(1, first);
}
```

The compiler allows writing back an `E` retrieved from `xs` itself, while **not** allowing an arbitrary `Number` to be added into `List<? extends Number>`. If the list does not support `set`, the call can still fail at runtime. The complete program in Section 7 demonstrated swapping; the lesson on **additional bounds on `T`** further illustrates wildcard capture.

## 9. The PECS Rule: Why Does `extends` Fit Data Sources?

**PECS — Producer Extends, Consumer Super**: if a parameter supplies elements that the algorithm **reads**, use `? extends T`; if a parameter is where the algorithm **writes** elements of type `T`, use `? super T`.

```java
static <T> void copy(
        List<? extends T> source,
        List<? super T> destination) {
    for (T value : source) destination.add(value);
}
```

This signature connects a producer containing `T` or a subtype with a consumer able to accept `T`. For example, a `List<Integer>` source and a `List<Number>` destination are valid. This is an **API parameter selection rule**, not a promise that the source is immutable or the destination is mutable. The section on designing data-supplying input APIs at the end of the chapter explains how to choose among `Iterable`/`Collection`/`List` according to the operations needed.

## 10. `extends` Works with Interfaces

In wildcard syntax, `extends` is also used with interfaces, even though a class uses the `implements` keyword to implement that interface.

```java
static void showLengths(List<? extends CharSequence> texts) {
    for (CharSequence text : texts) {
        System.out.println(text.length());
    }
}
```

This method accepts `List<String>` or `List<StringBuilder>` because both `String` and `StringBuilder` implement `CharSequence`.

```java
List<String> names = List.of("An", "Binh");
List<StringBuilder> builders =
        List.of(new StringBuilder("Java"));

showLengths(names);
showLengths(builders);
```

Note that you cannot write `texts.add("new")` inside the method. Even though `String` is a `CharSequence`, the actual list may be a `List<StringBuilder>`. There is only a **read guarantee** that elements can be used as `CharSequence`.

When multiple interface bounds are needed, Java allows declaring a type parameter with multiple bounds, such as `<T extends Number & Comparable<T>>`; that is a named type parameter syntax and a different problem from a simple `? extends T` wildcard. Each `? extends ...` wildcard typically expresses a single upper bound in standard type syntax.

## 11. Comparing `? extends T`, `T`, `?`, and `? super T`

| Declaration with `Number` | Which list types are accepted? | Safe read type | Add an arbitrary `Integer`? |
|---|---|---|---|
| `List<Number>` | `List<Number>` | `Number` | Yes |
| `List<? extends Number>` | `List<Number>` and `List` of subtypes of `Number` | `Number` | No |
| `List<?>` | `List` with any type argument | `Object` | No |
| `List<? super Number>` | `List<Number>`, `List<Object>` | `Object` | Yes |

In this table, "Add" only means **permitted by the compiler**; the actual object may still not support modification.

`List<?>` and `List<? extends Object>` have very similar meanings: every reference type argument lies below `Object`, so an `Object` bound does not raise the read guarantee above `Object`. By contrast, `List<? extends Number>` provides useful information that the elements belong to the `Number` family.

With `List<? super Number>`, retrieved values are only guaranteed to have type `Object` because the list may be declared with element type `Object`. In return, we can add `Number` and its subtypes, such as `Integer`. This is the symmetry of **reading via the upper bound, writing via the lower bound**.

## 12. Common Reasoning Mistakes

**Mistake 1 — "`extends` means any subtype can be added."** No. A `List<? extends Number>` may actually be a `List<Double>`; adding an `Integer` is unsafe. Knowing only the upper bound does not tell you the exact type to write.

**Mistake 2 — "`List<Integer>` is a `List<Number>`."** No. Java Generics are invariant; use `List<? extends Number>` when the goal is to accept multiple sources to read as `Number`.

**Mistake 3 — "If you can read `Number`, you can write `Number`."** No. Information sufficient for **reading up to a supertype** is not sufficient for writing a supertype where a specific subtype might be required.

**Mistake 4 — "`extends` makes a list immutable."** No. `clear()` or `remove(...)` are still type-valid. Mutability is a contract of the implementation and how the object is provided.

**Mistake 5 — "`? extends Number` must be `Integer` if all elements currently visible are integers."** No. The compiler relies on **static types and upper bounds**, not on inferring generic types from elements that happen to be observed. A `List<Number>` can easily contain a bunch of `Integer` values and still not be a `List<Integer>`.

**Mistake 6 — "Casting `(List<Integer>)` turns a `List<? extends Number>` into a safe list of integers."** Casting does not verify elements because of type erasure; it can produce an unchecked warning and leave a deferred runtime error. Prefer designing APIs with sufficient type constraints or validating data when forced to handle untrusted sources.

**Mistake 7 — "`? extends T` is an object creation syntax."** No. Wildcards are type-argument syntax at use sites; you cannot write `new ArrayList<? extends Number>()`. You can create `new ArrayList<Integer>()` and assign the reference to a `List<? extends Number>` variable.

## 13. Self-Check Exercises

Given the code:

```java
List<Integer> ints = new ArrayList<>(List.of(2, 4, 6));
List<Double> doubles = new ArrayList<>(List.of(1.5, 2.5));
List<? extends Number> source = ints;
```

Predict:

1. Can `source.get(0)` be assigned to `Number` or `Integer` without casting?
2. Does `source.add(7)` compile? Does `source.add(null)` compile?
3. Does `source.clear()` compile, and how does it affect `ints`?
4. Does `List<Number> numbers = ints;` compile?
5. Does `source = doubles;` compile? After the assignment, at what static type is `source.get(0)` safe?
6. Is `List<? extends Number> data = new ArrayList<Object>();` valid?

**Answers and explanations:**

1. Assigning to `Number` (or `Object`) is safe; the compiler does not know that the exact unknown type is `Integer`.
2. `add(7)` does not compile because the unknown type might not be `Integer`. `add(null)` compiles because `null` is compatible with any reference type; runtime behavior depends on the implementation.
3. `clear()` compiles. Here `source` and `ints` point to the same mutable `ArrayList`, so `ints` will be empty after clearing.
4. No. `List<Integer>` is not `List<Number>`.
5. Yes. `List<Double>` also satisfies `? extends Number`; after the assignment, reading is still only guaranteed as `Number`.
6. No. `Object` is a supertype, not `Number` or a subtype of `Number`.

## 14. Guiding Principle

Choose **`? extends T`** when an API needs to **retrieve values from a source whose elements are `T` or subtypes of `T`**, and does not need to arbitrarily add new `T` values into that same source. The upper bound allows reading results as `T` while still accepting multiple `List<S>` types safely at compile time. Even so, `?` still denotes an unknown type: write access is restricted to protect the original list, and actual mutability is determined by the `List` instance.

If the code needs to write `T` into the list, consider `? super T`; if you need to preserve an exact type relationship between input and output or across multiple parameters, consider a named type parameter such as `<T>`.