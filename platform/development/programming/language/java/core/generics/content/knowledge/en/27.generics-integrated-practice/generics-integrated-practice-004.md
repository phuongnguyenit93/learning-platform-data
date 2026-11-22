# Fixing Wildcard Errors with Capture Helpers in Java Generics

## Learning Objectives

When working with a `List<?>`, Java allows reading elements but typically rejects putting an element just read back into the list via a direct `set` or `add` call. A common error message is `incompatible types: Object cannot be converted to CAP#1`. This is the classic practice scenario for **wildcard capture**: the compiler knows `?` stands for some specific type, yet an ordinary expression cannot arbitrarily assign a value back into a slot requiring that exact unknown type.

This lesson focuses on writing a **generic helper method** to capture that same type within a single call, perform the operation safely, and keep the public interface simple.

After this lesson, you will be able to:

- Read and explain `CAP#1`, `capture of ?`, and the limits of write operations on `List<?>`.
- Write a helper of the form `private static <T> void helper(List<T> list)` and call it from a method taking `List<?>`.
- Perform swaps, rotations, and element copies **within the same collection** without raw types or unchecked casts.
- Distinguish **a single captured wildcard** from **two independent wildcards** that lack proof of having the same type.
- Decide when to use a capture helper, `? extends T`, `? super T`, a generic method with a named T, or library APIs such as `Collections.swap`.

## 1. The Problem: Why Does `List<?>` Reject Writing Elements Back?

Consider a list with an unknown element type:

```java
static void rotateWrong(java.util.List<?> values) {
    values.set(0, values.get(1)); // Does not compile.
}
```

This is **intentionally erroneous code**. If the list holds `String`s, visually taking an element from the same list and writing it to another position looks safe. The problem lies in how the compiler type-checks each expression.

- `List<?>` does not mean `List<Object>`. The `?` denotes a specific **unknown** element type.
- Reading via `values.get(1)` can be typed as `Object`, because every valid reference type is a subtype of Object.
- Writing via `values.set(0, ...)` requires a value of **that exact unknown element type**, not merely an Object.
- The outer method cannot name the capture type to preserve the link between the read value and the written value.

Therefore the compiler cannot prove that the expression passed to `set` belongs to the exact capture type `set` demands. With `javac --release 17`, the error message looks like:

```text
error: incompatible types: Object cannot be converted to CAP#1
where CAP#1 is a fresh type-variable:
  CAP#1 extends Object from capture of ?
```

`CAP#1` is an **internal compiler diagnostic name** for the unknown type created during *capture conversion*. It is not a runtime class name, not a type you can declare in Java, and the number `#1` carries no fixed design meaning.

### Wildcard does not mean every element is Object

Example:

```java
java.util.List<String> words = new java.util.ArrayList<>();
java.util.List<?> view = words;

// view.add("A");  // Does not compile: element type unknown.
// view.add(42);   // Does not compile.
// view.add(null); // Type-system valid, if the list supports mutation and null.
Object value = view.isEmpty() ? null : view.get(0);
```

Both references point to the same object, yet `view` intentionally hides the element type. The compiler blocks adding arbitrary values to protect a list that might actually be `List<String>`, `List<Integer>`, or `List<MyType>`.

One point to keep separate: **type checking and collection mutability are two distinct concerns**. Even when an operation is well-typed, an unmodifiable `List.of(...)` can still throw `UnsupportedOperationException` on `set`/`add`.

## 2. What Does Capture Conversion Do?

When a method declares a parameter `List<?>`, the compiler can temporarily interpret `?` as a **single capture type** for an expression, such as `CAP#1 extends Object`. That is how the compiler tracks a hidden type during generic inference and checking.

Suppose we have:

```java
static void consume(java.util.List<?> values) {
    // At the use site, values can be viewed as List<CAP#1>.
}
```

The comment is a conceptual illustration; `CAP#1` is not valid Java syntax. From a List with element type CAP#1, the compiler allows widening the read result to `Object`. But given only an expression of type `Object`, the compiler cannot treat it as `CAP#1`.

A generic method with a **named type parameter** preserves this relationship:

```java
private static <T> void replaceFirstWithSecond(java.util.List<T> values) {
    if (values.size() >= 2) {
        T second = values.get(1);
        values.set(0, second);
    }
}
```

Here:

- `List<T>.get(1)` returns exact `T`.
- `List<T>.set(0, T)` accepts exact `T` back.
- Type inference binds `T` to a capture of the wildcard when calling the helper.
- No unsafe casts, no raw types.

From outside you can write:

```java
static void replaceFirstWithSecond(java.util.List<?> values) {
    replaceFirstWithSecondCaptured(values);
}

private static <T> void replaceFirstWithSecondCaptured(
        java.util.List<T> values) {
    if (values.size() >= 2) {
        T second = values.get(1);
        values.set(0, second);
    }
}
```

These methods are **declaration patterns placed in the same class**, with the helper name deliberately differing from the public name for clarity. The compiler infers `T` as the capture type of the passed list. The helper body only operates on elements taken from **that same list**, so the type relationship holds.

There is no need to declare `CAP#1` yourself, no need to cast, and no need to know ahead of time whether the list holds `String` or `Integer`.

## 3. Step-by-Step Fix Process

Suppose you start with the requirement "swap the first and last elements of any list":

**Step 1 — Write the public signature as needed.**

```java
static void swapEnds(java.util.List<?> values) {
    // Accepts List<String>, List<Integer>, List<MyType>, ...
}
```

`List<?>` makes sense because the caller does not need to pass in or receive back a value of a specific type T.

**Step 2 — Do not try to write hard-to-infer mutations directly.**

```java
// WRONG, for illustration only:
// Object first = values.get(0);
// values.set(0, values.get(values.size() - 1));
// values.set(values.size() - 1, first);
```

The `Object first` variable has lost its link to the unknown element type. Both `set` calls run into capture issues.

**Step 3 — Delegate the operation to a generic helper.**

```java
static void swapEnds(java.util.List<?> values) {
    if (values.size() < 2) {
        return;
    }
    swapCaptured(values, 0, values.size() - 1);
}

private static <T> void swapCaptured(
        java.util.List<T> values, int left, int right) {
    T first = values.get(left);
    values.set(left, values.get(right));
    values.set(right, first);
}
```

These two methods can be placed in a class and compiled. Passing `List<?>` to `swapCaptured` triggers capture conversion, inferring a unified `T` for all operations inside the helper.

**Step 4 — Keep the helper narrow in visibility.** Make the helper `private` if it only serves the public method. The API surface remains clean: callers only see `swapEnds(List<?>)`.

**Step 5 — Check runtime conditions.** Empty lists or lists with fewer than two elements should be skipped; unmodifiable lists will throw `UnsupportedOperationException`; bad indices can throw `IndexOutOfBoundsException`. A capture helper **only solves generic typing**, not runtime preconditions.

## 4. Complete Java 17 Example: Swap, Rotate, Duplicate, and PECS

The following program illustrates three operations mutating data **within the same `List<?>`** via capture helpers, then compares them with copying from one list to another using `extends`/`super`.

**File `WildcardCaptureLab.java`:**

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class WildcardCaptureLab {
    static void swapEnds(List<?> values) {
        if (values.size() < 2) return;
        swapCaptured(values, 0, values.size() - 1);
    }

    private static <T> void swapCaptured(List<T> values, int left, int right) {
        T previous = values.get(left);
        values.set(left, values.get(right));
        values.set(right, previous);
    }

    static void rotateRight(List<?> values) {
        rotateRightCaptured(values);
    }

    private static <T> void rotateRightCaptured(List<T> values) {
        if (values.size() < 2) return;
        T last = values.get(values.size() - 1);
        for (int i = values.size() - 1; i > 0; i--) {
            values.set(i, values.get(i - 1));
        }
        values.set(0, last);
    }

    static void duplicateFirst(List<?> values) {
        duplicateFirstCaptured(values);
    }

    private static <T> void duplicateFirstCaptured(List<T> values) {
        if (!values.isEmpty()) values.add(values.get(0));
    }

    static <T> void appendAll(
            List<? super T> destination,
            List<? extends T> source) {
        destination.addAll(source);
    }

    public static void main(String[] args) {
        List<String> words = new ArrayList<>(List.of("A", "B", "C"));
        List<?> view = words;
        swapEnds(view);
        System.out.println("swap=" + words);
        rotateRight(view);
        System.out.println("rotate=" + words);
        duplicateFirst(view);
        System.out.println("duplicate=" + words);

        List<Integer> integers = new ArrayList<>(List.of(1, 2));
        List<Number> numbers = new ArrayList<>(List.of(0.5));
        appendAll(numbers, integers);
        System.out.println("append=" + numbers);

        List<?> fixed = List.of("x", "y");
        try {
            swapEnds(fixed);
        } catch (UnsupportedOperationException exception) {
            System.out.println("immutable=" + exception.getClass().getSimpleName());
        }

        Collections.swap(words, 0, 1);
        System.out.println("library=" + words);
    }
}
```

Run with JDK 17 or later:

```bash
javac --release 17 -Xlint:all WildcardCaptureLab.java
java WildcardCaptureLab
```

**Verified exact stdout:**

```text
swap=[C, B, A]
rotate=[A, C, B]
duplicate=[A, C, B, A]
append=[0.5, 1, 2]
immutable=UnsupportedOperationException
library=[C, A, B, A]
```

The program compiles under `javac --release 17 -Xlint:all` without warnings in the tested example. The generic helpers execute operations with clear type relationships.

### 4.1. `swapEnds` preserves exact element types

With `List<String>`, after calling `swapEnds(view)`, the first and last elements swap places: `[A, B, C]` becomes `[C, B, A]`.

The same holds for `List<Integer>`: the helper can accept a different capture and infer the corresponding `T` in a **different call**. The helper does not store a "global T" fixed to String after the first call.

### 4.2. `rotateRight` must retain multiple reads/writes of the same T

In `rotateRightCaptured`:

- `T last = values.get(size - 1)` holds the last element under exact type `T`.
- The loop sequentially moves the element at `i - 1` to `i`.
- `values.set(0, last)` places the last element at the front.

After swapping gave `[C, B, A]`, rotating right yields `[A, C, B]`. If the list has fewer than two elements, the method preserves its contents and avoids out-of-bounds index access.

The key mechanism is not the rotation algorithm itself, but that every internal read and write uses **one consistent T**.

### 4.3. `duplicateFirst` can add an element read from the same list

With `List<?>`, `view.add(view.get(0))` does not compile. Inside the helper, however:

```java
private static <T> void duplicateFirstCaptured(List<T> values) {
    if (!values.isEmpty()) {
        values.add(values.get(0));
    }
}
```

the type `T` of the element read is the exact type required by `add(T)`. Thus we can duplicate the first element: `[A, C, B]` becomes `[A, C, B, A]`.

This **does not permit adding an arbitrary Object**; the value must be T, here taken directly from the captured list.

### 4.4. `appendAll` uses PECS between two type-related lists

In `appendAll`, the source has type `List<? extends T>` so we can **read T** from the source list. The destination has type `List<? super T>` so we can **write T** into the destination list.

Since `Integer extends Number`, we can pass `List<Integer>` as source and `List<Number>` as destination. Then `1` and `2` are appended after `0.5`, producing `[0.5, 1, 2]`.

The difference from capturing a single `List<?>` is the **relationship between two containers**: the API must guarantee elements from source can be safely added to destination. `extends`/`super` expresses that relationship directly, whereas two independent `?` wildcards cannot.

### 4.5. Capture does not make an immutable collection mutable

`List.of("x", "y")` is an unmodifiable list. `swapEnds(fixed)` still succeeds in inferring T at compile time; at runtime, however, `set` fails and throws `UnsupportedOperationException`.

This is not a capture bug. Generic type safety and mutability are separate concerns. A method can require callers to supply a mutable list by contract, or make a copy:

```java
List<String> copy = new ArrayList<>(List.of("x", "y"));
swapEnds(copy);
```

This short snippet assumes `List`/`ArrayList` are imported and `swapEnds` is in scope.

### 4.6. Standard library methods can replace custom helpers

`Collections.swap(List<?> list, int i, int j)` already supports wildcards for swapping. If the problem is simply swapping, call this API instead of maintaining a custom helper.

Similarly, `Collections.reverse(List<?>)` reverses a list without requiring callers to know the element type. Before building a complex capture helper, check whether the standard library already provides a method for that exact operation.

## 5. Error Example: The `CAP#1` Error and How to Read It

**File `InvalidCapture.java` — intentionally fails to compile:**

```java
import java.util.List;

class InvalidCapture {
    static void rotate(List<?> values) {
        values.set(0, values.get(1));
    }

    static void move(List<?> source, List<?> target) {
        target.add(source.get(0));
    }
}
```

Test command:

```bash
javac --release 17 InvalidCapture.java
```

`javac` rejects both statements. Core diagnostic output (verified):

```text
error: incompatible types: Object cannot be converted to CAP#1
where CAP#1 is a fresh type-variable:
  CAP#1 extends Object from capture of ?
```

Similar messages appear in both places, yet **their meanings require different analysis**:

- `values.set(0, values.get(1))`: the element comes from **the exact same list**; fundamentally it can be safe. This is a good candidate for a capture helper with one T.
- `target.add(source.get(0))`: an element from **source** is placed into an **independent target**, both typed only as `List<?>`. There is no proof they hold the same element type. Writing a single-T helper cannot validate this transfer.

Therefore, do not assume every `CAP#1` error can be fixed the same way without changing the contract. Ask: **Do the read and write locations truly belong to the same type?** If yes, a capture helper lets the compiler express that. If not, supply explicit type relationships or runtime checks.

## 6. Two Independent Wildcards Are Two Distinct Captures

Consider this illustration:

```java
static void move(List<?> source, List<?> destination) {
    moveCaptured(source, destination);
}

private static <T> void moveCaptured(
        List<T> source, List<T> destination) {
    if (!source.isEmpty()) {
        destination.add(source.get(0));
    }
}
```

This **does not compile** when calling `moveCaptured` with two independent `List<?>` parameters. With `javac --release 17`, the inference error reads:

```text
required: List<T>,List<T>
found:    List<CAP#1>,List<CAP#2>
reason: inference variable T has incompatible equality constraints CAP#2,CAP#1
```

Explanation:

- `source` has one unknown element type, denoted `CAP#1`.
- `destination` has a separate unknown element type, denoted `CAP#2`.
- Writing `List<?>` for both does not prove `CAP#1` equals `CAP#2`.
- The helper requires **the same T**, so the call is rejected.

At runtime, for example, `source` could easily be `List<String>` and `destination` `List<Integer>`. If the compiler permitted arbitrary copying, the destination's data would become corrupted with wrong types.

Subtle point: even if you *know* two references happen to point to the same kind of list in a specific scenario, the signature `move(List<?>, List<?>)` does not express any relationship between them. Java verifies contracts provable at compile time, not guesses based on sample data.

### Three proper design options for two collections

**Option 1 — Caller knows the shared T:**

```java
static <T> void moveSameType(List<T> source, List<T> target) {
    if (!source.isEmpty()) {
        target.add(source.get(0));
    }
}
```

The method belongs inside a class importing `java.util.List`. Callers pass two lists that genuinely share type T.

**Option 2 — Subtype/supertype relationship (PECS):**

```java
static <T> void copyInto(
        List<? extends T> source,
        List<? super T> target) {
    target.addAll(source);
}
```

This pattern allows transferring elements from `List<Integer>` to `List<Number>`, or from `List<String>` to `List<Object>`. The API specifies the needed type relationship.

**Option 3 — Untyped data from an external source:** Accept `List<?>` and a `Class<T>` token to validate each element before adding to `List<T>`.

```java
static <T> void appendValidated(
        List<?> source, List<T> target, Class<T> type) {
    for (Object value : source) {
        target.add(type.cast(value));
    }
}
```

This method can partially modify target if invalid data appears midway. If **all-or-nothing** is needed, validate and copy into a temporary typed list first, then call `target.addAll(validated)`. A Class token only checks runtime-reifiable types like `String.class`; nested generic elements need deeper validation.

## 7. Choosing a Wildcard or a Type Variable for an API

A useful rule of thumb: **use a wildcard when the concrete type is irrelevant to the public contract**, and **use a named type variable when you need to express a relationship across multiple positions**.

Comparison:

| Intent | Appropriate signature | Why |
| --- | --- | --- |
| Only check element count | `int size(List<?> values)` | No need for a named T. |
| Iterate and print any elements | `void print(List<?> values)` | Reading as Object suffices. |
| Swap element positions within the same list | `void swap(List<?> values, ...)` with `<T>` helper | Simple public API; helper preserves read/write link. |
| Return the first element typed for the caller | `<T> T first(List<T> values)` | T links element type to return type. |
| Copy source into a wider-typed destination | `<T> void copy(List<? extends T>, List<? super T>)` | Two collections have an explicit type relationship. |
| Add Integer into a sink that may hold Number/Object | `void addInt(List<? super Integer> sink)` | Destination accepts Integer; no capture helper needed. |
| Read Number from a list of Number subtypes | `void consume(List<? extends Number> source)` | Safely reads Number; cannot write arbitrary Number. |

If you have:

```java
static <T> void printAny(List<T> values) {
    for (T element : values) {
        System.out.println(element);
    }
}
```

where T appears only once in the signature and no other link is needed, it can usually be simplified to `printAny(List<?> values)`. However, **appearing once does not always mean T is redundant**: check the full method body, overload resolution, and return types. When T is needed to retain data across multiple operations, a generic helper remains valuable.

## 8. Wildcards with `extends` and `super` Bounds

Capture helpers are not limited to unbounded wildcards.

### 8.1. `? extends Number`

If a method accepts `List<? extends Number>`, elements can be read as Number:

```java
static double sum(List<? extends Number> values) {
    double total = 0;
    for (Number value : values) {
        total += value.doubleValue();
    }
    return total;
}
```

This is an illustrative method inside a class, importing `List`. Because no writing is needed, **no helper is required**.

If the task is taking an element from the list and adding it back to **that same list**, you can write:

```java
static void duplicateNumber(List<? extends Number> values) {
    duplicateNumberCaptured(values);
}

private static <T extends Number> void duplicateNumberCaptured(
        List<T> values) {
    if (!values.isEmpty()) {
        values.add(values.get(0));
    }
}
```

The helper signature keeps T bounded by Number; the compiler can capture the actual element type from the `extends Number` wildcard. Adding an arbitrary `Number` into a List of unknown elements (which might be Integer) remains forbidden.

### 8.2. `? super Integer`

A `List<? super Integer>` is a **consumer** capable of accepting Integer:

```java
static void addInteger(List<? super Integer> destination) {
    destination.add(10);
}
```

This signature fits when callers pass `List<Integer>`, `List<Number>`, or `List<Object>`. Reading from a `List<? super Integer>` cannot automatically yield Integer; the safely readable type is generally Object.

You do not need a capture helper to add Integer because the `super Integer` bound already guarantees the write operation.

### 8.3. Capture helpers do not replace PECS

**Producer Extends, Consumer Super** is the right mindset when an API has one side producing/reading elements and another side consuming/writing elements. Capture helpers solve a different situation: **a single container whose type is unknown yet requires consistent internal operations**.

Do not force every API to `List<?>` and build complicated helpers. If you know the element type being written from outside, express it directly with `List<T>` or `List<? super T>`.

## 9. Deciding Between Collections API and Writing a Custom Capture Helper

Before writing a `<T>` helper, ask **whether the desired operation already exists in the standard library**. The methods below accept a list of any element type and reposition *existing* values without requiring callers to guess the element type:

| Intent | Built-in API | Risks to consider |
|---|---|---|
| Swap two elements | `Collections.swap(List<?>, i, j)` | Valid indices, list supports `set` |
| Reverse order | `Collections.reverse(List<?>)` | Whether list allows mutation |
| Rotate by distance | `Collections.rotate(List<?>, distance)` | May shift all positions |
| Shuffle | `Collections.shuffle(List<?>)` | Random result, no fixed stdout |

Example inside a method with `import java.util.*`:

```java
List<?> letters = new ArrayList<>(List.of("A", "B", "C"));
Collections.rotate(letters, 1);
System.out.println(letters); // [C, A, B]
```

`List<?>` does not allow adding an arbitrary `String` through the `letters` reference, yet it **does not forbid valid APIs from rearranging elements within the same list**. Type relationships remain intact because the operation only repositions values that already belong to that list.

If an algorithm needs to hold onto an element across multiple `get`/`set` calls and is not in the standard library, a `List<?>` wrapper paired with a `<T> void operation(List<T>)` helper is a clean choice. If data must move **between two collections with different element types**, define a PECS relationship instead of assuming two independent `?` captures are compatible.

Note: `Collections.sort` also requires appropriate comparability, so it is **not** applicable to every `List<?>` the way `reverse` is. Mutating list operations can still throw `UnsupportedOperationException` if callers pass `List.of(...)`; capture conversion does not override mutability contracts.

## 10. Common Mistakes When Fixing `capture of ?`

| Wrong or incomplete fix | Problem | Better fix |
| --- | --- | --- |
| Changing `List<?>` to raw `List` | Loses generic checks; can insert wrong types into the list. | Use a `<T>` helper or adjust the contract with PECS. |
| Casting `(List<Object>) values` | Generic cast does not prove element type; can be unchecked and corrupt data. | Preserve the capture using `List<T>` inside a helper. |
| Using `Object` to temporarily hold an element then `set` | `Object` can be wider than the required capture type. | Local variable `T first` inside a generic helper. |
| Calling a helper with two arbitrary `List<?>` arguments | Two wildcards create two distinct captures, proving no shared T. | Put `<T>` on the caller signature or use `extends/super`. |
| Assuming capture helpers make `List.of` mutable | Generic typing does not change object mutability. | Pass a mutable list or create a copy. |
| Assuming `?` always means Object | Wildcard represents an unknown type; Object is only a common safe read type. | Keep the distinction between reading Object and writing the capture. |
| Thinking `CAP#1` is a real class | It is an internal compiler name for inference diagnostics. | Read the capture constraints and identify involved positions. |
| Suppressing warnings instead of changing signatures | Hides type-safety risks without establishing type relationships. | Redesign the API and verify via compilation. |
| Exposing helpers overly publicly | API surface leaks unnecessary implementation details. | Keep helpers private if used only internally. |

### Warning about casting

Do not fix this with a raw cast such as:

```java
// DO NOT USE:
@SuppressWarnings({"unchecked", "rawtypes"})
static void unsafeRotate(List<?> values) {
    List raw = values;
    raw.set(0, raw.get(1));
}
```

This may compile, but it uses raw types to bypass type checking. Even though this specific operation reads and writes within the same list, the API loses compile-time enforcement preventing incompatible writes in future edits. A generic helper makes the invariant explicit: both internal inputs and outputs share T.

## 11. Practicing with Compile Errors and Verification

When encountering the message:

```text
incompatible types: Object cannot be converted to CAP#1
```

follow this sequence:

1. **Check what statement is writing:** `List<?>.add`, `List<?>.set`, or another method taking a capture parameter.
2. **Identify where the object came from:** the same list, another list, or an arbitrary data source.
3. **If from the same list**, try moving the operation into a helper `<T> void helper(List<T> values)`; place both the read and write logic inside the same helper.
4. **If from a different list**, do not force a single T just to silence the compiler. Add a type relationship: `List<T>` on both sides, or `<? extends T>`/`<? super T>`.
5. **Run `javac` before** adding any cast. If the helper is right, it usually needs no `@SuppressWarnings("unchecked")`.
6. **Test with multiple element types** and with unmodifiable collections to separate compile-time type safety from runtime mutability.
7. **Check empty lists and indices** to prevent `IndexOutOfBoundsException`, and clarify semantics of insertion, reordering, and aliasing.

A manual test worth running:

```java
// Place inside main of a class that has defined swapEnds.
List<Integer> ints = new ArrayList<>(List.of(10, 20, 30));
swapEnds(ints);
System.out.println(ints); // [30, 20, 10]
```

To compile this standalone, you need a class containing `swapEnds` along with imports for `List`/`ArrayList`. If you already ran the program in section 4, you can add this snippet to `main` and check the updated output.

### When is a helper unnecessary?

If the requirement is read-only:

```java
static void printAll(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

then no capture helper is needed. If you are only adding a known Integer to a consumer:

```java
static void addTen(List<? super Integer> destination) {
    destination.add(10);
}
```

it is also unnecessary. Create a helper only when it resolves **a type relationship obscured by a wildcard that the compiler cannot otherwise track across expressions**.

## 12. Self-Check Exercises

**Exercise 1.** Why does `List<?> list` allow `list.get(0)` but reject `list.set(0, list.get(1))`?

**Answer:** On read, the element can be viewed as Object; on write, `set` requires the unknown capture type. A read expression used as Object is not guaranteed to match the capture in direct signature checking. A generic helper with a named T expresses that same-type relationship.

**Exercise 2.** Write a helper signature that moves the last element to the front in any list.

**Answer:**

```java
static void rotateRight(List<?> values) {
    rotateRightCaptured(values);
}

private static <T> void rotateRightCaptured(List<T> values) {
    if (values.size() < 2) return;
    T last = values.get(values.size() - 1);
    for (int i = values.size() - 1; i > 0; i--) {
        values.set(i, values.get(i - 1));
    }
    values.set(0, last);
}
```

These two methods are snippets placed inside a class importing `List`.

**Exercise 3.** Why can't you write `copy(List<?> from, List<?> to) { to.add(from.get(0)); }`?

**Answer:** The element types of from and to are unknown and may differ. There is no proof that a value from from matches the element type accepted by to.

**Exercise 4.** If you want to copy from `List<Integer>` into `List<Number>`, which signature fits?

**Answer:** `<T> void appendAll(List<? super T> destination, List<? extends T> source)`; the compiler can choose a suitable T allowing reads from source and writes to destination.

**Exercise 5.** Does a generic helper resolve `UnsupportedOperationException` when calling `set` on `List.of`?

**Answer:** No. The helper only aids generic type checking. Unmodifiable lists still reject `set` or `add`.

**Exercise 6.** Why does replacing `List<?>` with raw `List` eliminate the compiler error yet remain a poor choice?

**Answer:** Raw List drops element constraints, allowing incompatible objects to be written. It proves no type relationship and easily leads to heap pollution and `ClassCastException` later.

**Exercise 7.** Suppose a helper `<T> void change(List<T> values)` is called once with a `List<?>` holding Strings. Will T always be String in all future calls?

**Answer:** No. T is inferred independently per call. On another call, the helper can accept a list holding Integer, Number, or a custom class.

**Exercise 8.** Should you write a custom helper solely to wrap `Collections.swap`?

**Answer:** Usually no; `Collections.swap` already accepts `List<?>` and performs the swap directly. Use a custom helper when an algorithm needs multiple linked reads/writes or when the library lacks a method meeting your requirements.

## 13. Key Takeaways

- `List<?>` holds an **unknown** element type, not `List<Object>`.
- The compiler may assign a temporary name like `CAP#1` to a capture type; this name exists solely for inference and diagnostics.
- If an operation **reads from and writes to the same list**, a helper method `<T> void helper(List<T> list)` preserves safe relationships among the list's elements.
- If an operation transfers elements **between two independent lists**, two `?` wildcards do not guarantee matching types. Use a generic signature expressing the relationship or PECS.
- Capture helpers do not change whether a list is mutable, do not change runtime erasure, and are never a reason to add unchecked casts.
- Prefer concise public APIs and standard library utilities; keep capture logic in private helpers when it is purely an implementation detail.

When reading a `capture of ?` error, the right question is not "how do I force the compiler to accept Object?", but **can the value being written be proven to belong to the same unknown type required by the container?** If the answer is yes because it came from the same container, a generic helper with a named T expresses that relationship cleanly, safely, and maintainably.