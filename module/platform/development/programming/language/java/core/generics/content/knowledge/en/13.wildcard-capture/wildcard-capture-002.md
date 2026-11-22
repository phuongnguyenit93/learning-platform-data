# Reading CAP#1 and "capture of ?" Messages in Java Generics

## 1. Why Does javac Mention CAP#1?

In Java Generics, a variable of type `List<?>` states that the list has **some type argument**, but the code using the variable does not know whether it is `String`, `Integer`, or another type. When checking a generic call, the Java compiler (`javac`) can create a **temporary internal type** to represent the unknown type argument. That process is called **wildcard capture** or **capture conversion**.

When reporting an error, `javac` sometimes displays a compiler-generated name such as:

- `CAP#1`: a temporary symbol assigned by the compiler to a captured type.
- `capture of ?`: indicates the hidden type comes from an unbounded wildcard `?`.
- `capture of ? extends Number`: indicates the hidden type comes from a wildcard with upper bound `Number`.
- `capture of ? super Integer`: indicates the hidden type comes from a wildcard with lower bound `Integer`.

**`CAP#1` is not a Java class, a variable, a type parameter name you can declare yourself, or something that exists independently at runtime.** It is a diagnostic device to help readers distinguish hidden types during compile-time type checking. The numbers `#1`, `#2`,... are only internal labels; you must not infer execution order or a stable identifier across JDK versions.

Example:

```java
List<String> names = new ArrayList<>();
List<?> unknown = names;
```

The compiler knows `unknown` **has static type `List<?>`**. When processing a call that takes an element of `E` such as `add(E)`, it can treat `E` as some hidden type `CAP#1`. However, there is no basis to assert that an arbitrary `String` is assignable to that hidden type.

```java
unknown.add("An"); // Compile error: cannot prove String is CAP#1
```

Seeing `CAP#1` means something very practical: **you are trying to pass a value to, or relate two values with, a type that the compiler does not currently know exactly**.

## 2. Distinguishing the Actual Type, Static Type, and Captured Type

Suppose:

```java
List<String> names = new ArrayList<>(List.of("An", "Binh"));
List<?> view = names;
```

There are three levels to keep separate:

1. **The actual object/list**: `names` and `view` both point to an `ArrayList` storing strings; `names` is declared as `List<String>`.
2. **The static type of the expression `view`**: `List<?>`. Code written against `view` may only rely on the wildcard contract and cannot automatically deduce `String`.
3. **The internal captured type**: when checking a call, `javac` may give a temporary name like `CAP#1` to the hidden type argument. This is a type-checking helper detail; this name is not a source type you can write in Java.

Java Generics use **type erasure**: type arguments such as `String` are not retained as a runtime property of the `ArrayList` object itself to automatically verify every element. Wildcard capture does not read a “real generic type” from the heap; it is a compiler type transformation used to verify safety constraints.

Therefore, you cannot fix the error by looking for a class named `CAP#1`, declaring `CAP#1 value`, or trying to “erase” that name with an arbitrary cast.

## 3. Reading the Structure of a javac Error Message

The following example **intentionally does not compile**. Place it in `BrokenCapture.java` to observe the compiler:

```java
import java.util.List;

public class BrokenCapture {
    static void appendText(List<?> values) {
        values.add("new");
    }
}
```

Run:

```bash
javac -Xdiags:verbose BrokenCapture.java
```

This command fails at the compilation step. **There is no program stdout**, because no runnable program was produced. The content and formatting of stderr can vary by JDK version, compiler options, and context; do not memorize the exact wording or `CAP` numbers.

The message typically contains points equivalent to:

```text
no suitable method found for add(String)
required: CAP#1
found:    String
reason:  String cannot be converted to CAP#1
where CAP#1 is a fresh type-variable from capture of ?
```

This is an **illustrative message format**, not a guarantee of the exact full stderr of every `javac` version. The actual output may also list the `add(int,E)` overload or phrase the error as `incompatible types`.

Read it in order:

1. **Error location**: the call `values.add("new")`, especially the passed argument.
2. **`found` / `actual`**: the compiler knows the argument you supplied is `String`.
3. **`required` / `formal`**: the generic method `List<E>.add(E)` expects a value of the hidden element type, which may be labeled `CAP#1`.
4. **`capture of ?`**: the required type comes from `?` in `List<?>`.
5. **Conclusion**: there is no proof that `String` is the list's element type. The problem lies in the type contract, not string syntax or a JVM bug.

When encountering a long error, locate the variable with a wildcard, trace back to the parameter type of the method being called, and ask: “Am I **reading** a value from the hidden type or trying to **write** a value of a specific type into the hidden type?”

Depending on the message, `javac` may say `CAP#1 extends Object` or use the phrase “fresh type-variable”. These parts describe the bounds of the hidden type; they are not a suggestion to replace `CAP#1` with `Object`.

## 4. Why Does `List<?>.add` Fail While `get` Can Read?

`List<E>` has two characteristic operations:

```java
E get(int index);
boolean add(E element);
```

These are **abbreviated signatures** illustrating two methods, not a standalone runnable program.

For `List<?>`, `get` provides a value of the hidden type; every generic type argument is a reference type, so that value can be used under type `Object`:

```java
List<String> names = List.of("An");
List<?> values = names;

Object first = values.get(0); // Valid
// String text = values.get(0); // Unsafe under static type List<?>
```

However, `add` requires a value of the **exact hidden type**. The compiler does not know that type:

```java
List<?> values = new ArrayList<String>();

// values.add("An"); // Error because ? does not mean String
// values.add(42);   // Error because ? does not mean Integer
values.add(null);    // Type-valid
```

Only `null` is allowed at the type-checking level because `null` is assignable to every reference type. Nevertheless, `List.of(...)` and unmodifiable lists can still throw `UnsupportedOperationException` on modification; some implementations have their own rules regarding null.

**Do not fix CAP errors with raw `List`**. Casting to a raw type to call `add` bypasses generic parameter checking and can cause *heap pollution*, leading code that reads the list under its declared type to hit a `ClassCastException` later.

## 5. `CAP#1 extends Number`: Can Read `Number` but Cannot Write `Number`

With an upper-bounded wildcard:

```java
List<Integer> integers = new ArrayList<>(List.of(1, 2));
List<? extends Number> source = integers;

Number first = source.get(0); // Valid
// source.add(3);              // Does not compile
// source.add(3.5);            // Does not compile
// source.add((Number) 3);     // Also does not compile
```

The compiler can describe the element type as a `CAP#1` with **upper bound `Number`**. What it knows is “`CAP#1` is `Number` or a subtype of `Number`”. Therefore:

- **Reading** a `CAP#1` and assigning it to `Number` is safe.
- **Writing** a new `Number` or `Integer` into `CAP#1` is not guaranteed to be safe: the list could be `List<Double>`, `List<Integer>`, or `List<Number>`.

Error illustration:

```java
static void brokenAdd(List<? extends Number> numbers) {
    // numbers.add(Integer.valueOf(10)); // Cannot assign Integer to CAP#1 extends Number
}
```

When a message mentions `capture of ? extends Number`, read it as **“a hidden type beneath Number”**, not **“the hidden type is Number itself”**. This is why an upper bound allows a producer to supply values for reading, without granting permission to add arbitrary new values.

## 6. `CAP#1 super Integer`: Can Write `Integer` but Reading Only Guarantees `Object`

With a lower-bounded wildcard:

```java
List<Number> numbers = new ArrayList<>(List.of(1, 2));
List<? super Integer> destination = numbers;

destination.add(3); // Valid: every matching type accepts Integer
Object first = destination.get(0); // Valid

// Integer exact = destination.get(0); // Does not compile
// Number number = destination.get(0);  // Does not compile
```

A `List<? super Integer>` can be `List<Integer>`, `List<Number>`, or `List<Object>`. A `List<Object>` can already contain non-`Integer` objects, so `get` only guarantees type `Object`.

The compiler may label the type argument `CAP#1` with information about **lower bound `Integer`** and general upper bound `Object`. Failing when trying to assign the result of `get` to `Integer` does not mean `CAP#1` is a subtype of `Integer`; the `super` wildcard constrains the opposite direction.

Two readings to remember:

| Wildcard | What does the compiler know about the hidden type? | Guaranteed retrieved value | Guaranteed accepted value |
|---|---|---|---|
| `?` | Unknown type parameter | `Object` | Only `null` type-wise |
| `? extends Number` | Hidden type is `Number` or a subtype | `Number` | Only `null` type-wise |
| `? super Integer` | Hidden type is `Integer` or a supertype | `Object` | `Integer`, its subtypes, and `null` |
| `Integer` | Element type is exactly `Integer` | `Integer` | `Integer` and `null` |

The “accepted value” column refers to what the compiler permits, not a guarantee that the actual list supports mutation or accepts null. With generics, the PECS rule remains useful: **Producer Extends, Consumer Super**.

## 7. A Subtle Capture Error: Taking an Element Out and Putting That Same Element Back

Sometimes you do not want to insert a foreign element at all: you only want to put an existing element back into the same list. Even so, the following snippet typically causes a capture error in `javac`:

```java
static void putFirstBack(List<?> values) {
    // values.set(0, values.get(0)); // Wildcard capture error
}
```

Conceptually, putting back the element just retrieved is safe if the list is mutable. But at the generic expression level, the compiler does not necessarily preserve **proof that the two wildcard positions in the call refer to the same captured type**. In the message, `CAP#1` and `CAP#2` or `Object` and `CAP#1` may appear. That does not mean the list holds two different element classes; they are two compiler labels needed to protect type constraints in this checking context.

To express the relationship “read `T` out and write back that exact `T`” explicitly, use a **wildcard capture helper**:

```java
static void putFirstBack(List<?> values) {
    putFirstBackCaptured(values);
}

private static <T> void putFirstBackCaptured(List<T> values) {
    if (!values.isEmpty()) {
        T first = values.get(0);
        values.set(0, first);
    }
}
```

These are illustrative methods you can place in a Java class. `putFirstBackCaptured` has **one consistent type parameter named `T`**: the result of `get` is `T`, and `set` accepts `T`. Calling the helper lets the compiler infer `T` from the hidden wildcard of the passed-in list.

You do not need to know whether the actual type name is `String` or `Integer`. No raw types, no `(List<T>)` cast, and no disabling compile-time checks.

However, the helper only ensures **type safety**; if the list does not permit modification, `set` can still throw `UnsupportedOperationException`. If the list is empty, the snippet above does not perform `set`.

## 8. Complete Java 17 Example: Preserving the Same Hidden Type with a Helper

Create `WildcardCaptureDiagnosticsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class WildcardCaptureDiagnosticsDemo {
    static void repeatFirst(List<?> values) {
        repeatCaptured(values);
    }

    private static <T> void repeatCaptured(List<T> values) {
        if (!values.isEmpty()) {
            T first = values.get(0);
            values.add(first);
        }
    }

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

    static <T> void copyAll(
            List<? extends T> source,
            List<? super T> destination) {
        for (T element : source) {
            destination.add(element);
        }
    }

    public static void main(String[] args) {
        List<String> words = new ArrayList<>(List.of("red", "blue"));
        List<?> unknown = words;

        Object first = unknown.get(0);
        System.out.println("First: " + first);

        repeatFirst(unknown);
        System.out.println("Repeated: " + words);

        swapFirstTwo(unknown);
        System.out.println("Swapped: " + words);

        Collections.swap(unknown, 0, 1);
        System.out.println("Library swap: " + words);

        List<Integer> numbers = List.of(2, 4);
        List<Number> collected = new ArrayList<>();
        copyAll(numbers, collected);
        System.out.println("Collected: " + collected);
    }
}
```

Compile and run:

```bash
javac WildcardCaptureDiagnosticsDemo.java
java WildcardCaptureDiagnosticsDemo
```

**Exact stdout:**

```text
First: red
Repeated: [red, blue, red]
Swapped: [blue, red, red]
Library swap: [red, blue, red]
Collected: [2, 4]
```

Explanation:

1. `unknown` has static type `List<?>`, so `get(0)` can be used as `Object`. The referenced object is `ArrayList<String>`.
2. `repeatFirst` accepts a `List<?>` and calls helper `repeatCaptured`. Inside the helper, `T first = values.get(0)` and `values.add(first)` both use `T`. Because `ArrayList` is mutable, the result is `[red, blue, red]`.
3. `swapFirstTwo` uses the same mechanism to swap the first two elements without needing to construct a new value of type `T`. The result is `[blue, red, red]`.
4. `Collections.swap` is a library API accepting `List<?>`; it swaps elements by index when the list supports `set`. The result is `[red, blue, red]`.
5. `copyAll` illustrates how to link types between **two lists with different roles**: source `List<? extends T>` supplies `T`, and destination `List<? super T>` receives `T`. `List<Integer>` and `List<Number>` are compatible according to the PECS rule.

Every method in the file has complete declarations/imports, uses no raw types, and contains no unchecked casts. If you replace `words` with a list returned by `List.of(...)`, `repeatFirst` and `swapFirstTwo` may throw `UnsupportedOperationException` when attempting to modify it.

## 9. Why Do CAP#1 and CAP#2 Sometimes Appear in the Same Error?

The symbols `CAP#1`, `CAP#2`,... are internal hidden types named by the compiler when capturing wildcards in different contexts. **You cannot assume two independent wildcards share the same element type** merely because both are written `?`.

Example:

```java
static void moveOne(List<?> from, List<?> to) {
    // to.add(from.get(0)); // Does not compile
}
```

The caller can easily pass:

```java
List<String> strings = new ArrayList<>(List.of("red"));
List<Integer> integers = new ArrayList<>(List.of(1));

// moveOne(strings, integers); // If the method body writes an element, type safety breaks!
```

`from` can be `List<String>`, while `to` is `List<Integer>`. A helper that merely assigns the same name `T` to both lists **cannot turn two different actual types into the same type**.

If you want to copy between lists with a valid type relationship, design the contract right in the signature:

```java
static <T> void moveAll(
        List<? extends T> from,
        List<? super T> to) {
    for (T item : from) {
        to.add(item);
    }
}
```

With `List<String>` as source and `List<Object>` as destination, the compiler can infer a suitable `T`; with `List<String>` as source and `List<Integer>` as destination, there is no valid type relationship to transfer values under the contract above.

**Lesson when seeing multiple CAPs:** distinguish “multiple uses of **one list** that must preserve the same type” from “**two different lists** whose element types are not guaranteed to be related”. The first group is usually solved by a capture helper; the second group requires modeling a real type relationship or changing the design.

## 10. When Can a Capture Helper Solve the Error?

A generic helper is appropriate when you **need to express a relationship about the same hidden type** that the compiler cannot prove when written directly via a wildcard.

General pattern:

```java
static void operation(List<?> values) {
    operationCaptured(values);
}

private static <E> void operationCaptured(List<E> values) {
    // Here read and write operations with the same type E are checked consistently.
}
```

This is a **method declaration pattern**, not a standalone program. The name `E` is chosen by the author (you can use `T`, `X`...) and is completely different from `CAP#1` generated by the compiler.

A helper **does not** legitimize writing a value of the wrong type:

```java
private static <T> void unsafeAttempt(List<T> values) {
    // values.add("new"); // Still an error: T is not guaranteed to be String
}
```

The helper only gives a consistent name to the hidden type; it does not prove that an arbitrary `String` is assignable to any `T`.

When a task only needs a built-in library operation like `Collections.swap(List<?>, ...)`, using the existing API can be clearer than writing a helper. When a task only wants to **read** values as `Object`, no helper is needed because `List<?>` already suffices.

If you need to **write `T` from outside into a destination**, consider `List<? super T>`. If you need to **read `T` from a source**, consider `List<? extends T>`. If one object must both read and write one exact element type, `List<T>` may be a better contract than a wildcard.

## 11. Wrong Fixes to Avoid

### Wrong: using a raw type to bypass CAP

```java
static void unsafe(List<?> values) {
    List raw = values;   // Raw type, loses type argument checking
    raw.add("new");      // May produce an unchecked warning
}
```

This example intentionally illustrates **unsafe** code. If `values` is a `List<Integer>`, the last line can insert a `String` into a list that other places trust to contain only `Integer`s. Code reading it as `Integer` later can hit `ClassCastException`. An `unchecked` warning is not equivalent to a capture error; suppressing the warning does not make the write safe.

### Wrong: casting to `List<String>` without proving the elements

```java
static void unsafeCast(List<?> values) {
    // Do not use casts as a way to fix CAP errors when the data is unknown.
    // List<String> strings = (List<String>) values;
}
```

A generic cast does not verify individual elements due to type erasure. When receiving untrusted data, inspect each element and copy into a new `List<T>` if you need to guarantee the contents are of type `T`.

### Wrong: merely changing `CAP#1` to `Object`

If a method demands an element of `List<?>`, changing the input data to `Object` does not tell the compiler the hidden type:

```java
static void broken(List<?> values, Object candidate) {
    // values.add(candidate); // Still invalid
}
```

A `List<String>` cannot accept an arbitrary `Object`. `Object` is the **common supertype of reference types**, not another name for the hidden type parameter.

### Wrong: thinking CAP messages are about runtime

The `CAP#1` and `capture of ?` errors discussed here are detected **at compile time**. They differ from `ClassCastException` occurring at runtime. `-Xdiags:verbose` helps read more detailed diagnostics, whereas `@SuppressWarnings("unchecked")` does not resolve a **compile error** about incompatible type arguments.

## 12. Quick Translation Table from Compiler Messages to Questions to Answer

| Common phrase | How to read it | Question to resolve |
|---|---|---|
| `CAP#1` | Temporary name of a captured hidden type | Where does this wildcard-derived type come from? |
| `capture of ?` | Unknown arbitrary type argument | Am I trying to write a value into `List<?>`? |
| `capture of ? extends T` | Hidden type is `T` or a subtype | Am I trying to add `T` to a source only guaranteed to be readable as `T`? |
| `capture of ? super T` | Hidden type is `T` or a supertype | Am I demanding to read `T` when only `Object` is guaranteed? |
| `required CAP#1, found String` | Method needs the hidden type, but `String` was passed | What proves `String` equals the hidden type? |
| `CAP#1, CAP#2` | Compiler is tracking different hidden types | Do the two positions genuinely share one element type? |
| `incompatible types` | Assignment/argument passing violates constraints | Can the contract be changed with an appropriate wildcard or `<T>` helper? |

CAP numbering can vary by context; do not write logic relying on the label order. A “capture of ...” message **does not automatically mean you must cast**, nor does it prove the data inside the list is corrupted.

## 13. Step-by-Step Investigation of a Real Error

When facing a large message involving capture:

1. **Read the call line causing the error**, do not start by searching the project for the name `CAP#1`. Identify `add`, `set`, `get`, or a generic method call.
2. **Find the declared type of the receiver**: `List<?>`, `List<? extends Number>`, `List<? super Integer>`, or a nested type such as `List<List<?>>`.
3. **Find the type parameter the method requires**. For example `add(E)` requires the list's own `E`, `set(int,E)` requires an `E`, and `get(int)` returns `E`.
4. **Note the data direction**: are elements flowing **out of the list** or **into the list**? That direction determines `extends`/`super` if the signature can be changed.
5. **Check relationships across multiple hidden types**: the same list can use a `<T>` helper; independent lists require genuine constraints in the signature.
6. **Choose the smallest change that stays type-safe**: use `Object` for general reading only, use a capture helper to preserve one hidden type, use PECS for source/destination, or use `List<T>` if one concrete type is needed.
7. **Recompile** with `javac -Xdiags:verbose` if details are needed; once compilation succeeds, also verify runtime behavior such as empty or unmodifiable lists.

The key is to **fix the program's real type relationship**, not turn a helpful compile-time error into a runtime error via a raw cast.

## 14. Self-Check Exercises

Given:

```java
List<Integer> ints = new ArrayList<>(List.of(1, 2));
List<?> a = ints;
List<? extends Number> b = ints;
List<? super Integer> c = ints;
```

Predict:

1. Does `a.add(3)` compile? If it reports `CAP#1`, where does the hidden type come from?
2. Is `Number x = b.get(0)` valid? What about `b.add(3)`?
3. Is `c.add(3)` valid? What about `Integer y = c.get(0)`?
4. Can `a.set(0, a.get(0))` cause a capture error? What safer helper approach exists?
5. Can two variables `List<?> from` and `List<?> to` be assumed to have the same element type just because both use `?`?
6. Is `CAP#1` a runtime class or only a compiler symbol?

**Answers:**

1. No. `CAP#1` represents the hidden element type captured from `List<?>`; the compiler does not know whether `Integer` is suitable.
2. `get` safely reads as `Number` because of the upper bound; `add(3)` does not compile because the hidden type could be another subtype of `Number`.
3. `add(3)` is valid because every `? super Integer` type accepts `Integer`. `get` only guarantees `Object`, so it cannot be assigned directly to `Integer`.
4. Yes; use `static <T> void helper(List<T> values)` and put both `get`/`set` inside the helper so the same type `T` is checked consistently.
5. No. Two wildcards can represent two different element types; if copying is needed, design the type relationship using `<T>`, `? extends T`, and `? super T`.
6. `CAP#1` is an internal name in compiler diagnostics, not a runtime class. You cannot instantiate objects or declare variables with the type name `CAP#1` in Java.

## 15. Takeaways

When you see **`CAP#1` / `capture of ?`**, read it as: **“the compiler is tracking an existing generic type whose exact identity is unknown; is my operation assuming too much about that type?”**. If the message says `? extends T`, you usually know enough to **read as `T`**; if it says `? super T`, you usually know enough to **write values of `T`**; if it says `?`, you can primarily only read safely as `Object`.

If you need to keep **one hidden type** consistent across multiple operations on the same list, a helper with type parameter `<T>` lets the compiler express that relationship. If sources/destinations genuinely have different types, describe the relationship with suitably bounded wildcards. This approach resolves the root cause of capture errors while preserving Java Generics type-safety checks.