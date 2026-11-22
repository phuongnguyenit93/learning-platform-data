# Naming an Unknown Type with a Generic Helper Method (Wildcard Capture)

## 1. What Problem Does Wildcard Capture Solve?

In Java Generics, the `?` symbol indicates a **specific but unknown** type argument at the use site, such as `List<?>`, `List<? extends Number>`, or `List<? super Integer>`. You can still read data according to the guarantees of the type bounds, but many write operations are rejected because the compiler cannot prove the written value matches the hidden element type.

Example:

```java
import java.util.List;

static void replaceWithSameValue(List<?> values) {
    values.set(0, values.get(0)); // COMPILE ERROR
}
```

A programmer sees the same list being read and written, but at the type-checking level, the expression `get(0)` is not guaranteed to have the exact type required by the `set(0, ...)` call when the wildcard is captured across different usage contexts. Therefore Java rejects this code.

To express the relationship “the retrieved value and the target write position belong to the **same element type**,” we use a **generic helper method** with a named type parameter:

```java
static <E> void replaceHelper(List<E> values) {
    if (!values.isEmpty()) {
        E current = values.get(0);
        values.set(0, current); // Valid: get and set use the same E
    }
}

static void replace(List<?> values) {
    replaceHelper(values); // The compiler captures the wildcard into E
}
```

In the call `replaceHelper(values)`, Java performs **capture conversion** to treat the unknown wildcard argument as an appropriate temporary type parameter when inferring type `E`. Inside the helper, the same name `E` is used consistently for `List<E>`, `get`, and `set`.

This is the technique of **naming an unknown type with a generic helper method**. The name `E` exists only within the scope of the helper; the wildcard is never permanently converted to `Object` or to a type guessed by the programmer.

## 2. How Do a Wildcard `?` and a Type Parameter `<E>` Differ?

Consider two signatures:

```java
static void inspect(List<?> list) { /* ... */ }

static <E> void transform(List<E> list) { /* ... */ }
```

Both can accept `List<String>`, `List<Integer>`, and many other list types. The difference lies in the type information usable **inside the method body**.

| Feature | `List<?>` | `<E> ... (List<E>)` |
| --- | --- | --- |
| Element type | An unknown type | A named type `E` |
| Reading via `get` | Safely received as `Object` | Safely received as `E` |
| Adding a concrete external value | Not arbitrarily permitted | Only permitted if the value is proven to be `E` |
| Reading and writing back the same value | Direct expression with wildcard can hit capture error | Value can be held in an `E` variable and written back |
| Relating type positions | Cannot name `?` directly | One `E` can be used across multiple positions |
| Runtime modification guarantee | No | No; depends on the list implementation |

`<E>` **declares a new type parameter** for the method. It does not force the caller to write `E` explicitly: the compiler usually infers it from the argument and applies capture conversion.

For example, `List<?> unknown = new ArrayList<String>();` can call `transform(unknown)` if the body of `transform` only performs safe operations on the same `E`. The compiler **does not conclude `E = String` based on the runtime object**; it treats `E` as the call's appropriate hidden type.

## 3. Capture Conversion Model: An Unknown Type Has an Identity Within a Scope

The compiler often describes a wildcard via an internal type notation like `CAP#1`. Given:

```java
List<?> items = new ArrayList<String>();
```

you can picture `items` as a list holding an unknown type `CAP#1` with upper bound `Object`. This is an explanatory notation, **not** Java syntax you can write directly in source code.

```text
Declared type at caller:
    List<?>

Capture conversion at an appropriate call:
    ?  -> CAP#1 (unknown type with internal identity)

Type parameter inference of the helper:
    E  = CAP#1

Inside the helper:
    E value = list.get(0)
    list.set(0, value)
    // Both the read site and the write site use E.
```

You should not interpret `?` as “`Object`” or as “each element can have any arbitrary type.” The real object still maintains its `List<String>`, `List<Integer>`, or corresponding contract. `Object` is simply the safe common type when reading from `List<?>` without knowing more about the elements.

Compiler error messages may mention `capture of ?` or `CAP#1`, `CAP#2`. These numbered labels are purely internal names used to report type mismatches where the compiler detects an error; do not use them to declare Java variables.

### Why Is a Helper Needed?

A helper is where the programmer **declares the same `E` appearing in both related positions**. The compiler can prove that all operations in the helper do not insert an element of the wrong type into the list. When the caller has `List<?>`, type inference on the call safely captures the wildcard.

A helper does not make unsafe casts valid; it simply expresses accurately the relationship that already exists among the elements of a generic object.

## 4. Designing the Public API Boundary and Internal Generic Helper

A helper is not only for swapping. For example, **copying the first element into the last position of the same list**:

```java
static void copyFirstToLast(List<?> values) {
    copyCaptured(values);
}

private static <E> void copyCaptured(List<E> values) {
    if (values.size() >= 2) {
        E first = values.get(0);
        values.set(values.size() - 1, first);
    }
}
```

These are illustrative methods placed inside a class importing `java.util.List`. If the initial data is `[A, B, C]` in an `ArrayList<String>`, the result is `[A, B, A]`. If it is `[1, 2, 3]` in an `ArrayList<Integer>`, the result is `[1, 2, 1]`.

**At the API boundary**, `List<?>` lets the caller pass a list of any element type. **Inside the helper**, `List<E>` connects `get` and `set` with the same `E`; the compiler does not need to know whether `E` is `String` or `Integer`. You cannot replace `first` with an arbitrary `Object` taken from outside the list.

Another example of this technique is swapping two positions; Java already provides `Collections.swap(List<?>,i,j)`. When you only need a swap, prefer the standard API; when you need a custom algorithm like the one above, a generic helper expresses the type invariant more clearly. If the list does not support `set`, runtime can still throw `UnsupportedOperationException`.

## 5. Re-adding an Existing Element: An Operation That Can Be Valid in a Helper

The following direct code has a type error:

```java
static void duplicateWrong(List<?> values) {
    values.add(values.get(0)); // COMPILE ERROR
}
```

You can keep the element type as a single `E` using a helper:

```java
static <E> void duplicateCaptured(List<E> values) {
    if (!values.isEmpty()) {
        E first = values.get(0);
        values.add(first); // Valid at the generic level
    }
}

static void duplicateFirst(List<?> values) {
    duplicateCaptured(values);
}
```

Here `first` **is retrieved from the list itself**, not an arbitrary `Object` or `String` coming from outside. If `values` is actually a `List<Integer>`, the helper only duplicates an existing `Integer` element. If it is a `List<String>`, the helper duplicates a `String`.

Two things must be clearly distinguished:

- The helper is **type-valid** because it uses the same `E`.
- `add` can still fail at **runtime** if the list is fixed-size or unmodifiable (`Arrays.asList`, `List.of`).

And if the list is empty, the code above intentionally does nothing to avoid `IndexOutOfBoundsException`.

### Capture Does Not Grant Permission to Add an Arbitrary External Value

You cannot write:

```java
static void addString(List<?> unknown) {
    addCaptured(unknown, "Java"); // Not guaranteed to compile
}

static <E> void addCaptured(List<E> list, E value) {
    list.add(value);
}
```

Because `unknown` cannot be proven to be `List<String>`. At the call `addCaptured(unknown, "Java")`, the type constraints of `List<E>` and `E value` have no valid assignment based solely on `List<?>`; `E` is constrained by the hidden element type and cannot arbitrarily be treated as `String`.

To actually add a `String` to a destination capable of accepting it, change the API contract:

```java
static void addText(List<? super String> destination, String text) {
    destination.add(text);
}
```

The destination can be `List<String>`, `List<CharSequence>`, or `List<Object>`, and all of those types accept `String`. No wildcard capture helper is needed when the relationship between the written value and the destination is fully stated by a lower bound.

## 6. Helpers with Upper-Bounded Wildcards `? extends T`

The mechanism is similar when the argument is not a bare `?` but a bounded wildcard:

```java
static void repeatLastNumber(List<? extends Number> values) {
    repeatNumberCaptured(values);
}

private static <E extends Number> void repeatNumberCaptured(List<E> values) {
    if (!values.isEmpty()) {
        E last = values.get(values.size() - 1);
        values.add(last);
    }
}
```

The call `repeatNumberCaptured(values)` lets the compiler capture the hidden element type beneath the bound `Number`; `E` is simultaneously upper-bounded by `Number`.

Inside the helper, you can write:

```java
E number = values.get(0);
double d = number.doubleValue(); // Valid: E extends Number
```

But you cannot add an arbitrary `Integer`:

```java
static <E extends Number> void invalid(List<E> values) {
    values.add(Integer.valueOf(10)); // COMPILE ERROR
}
```

Because `E` could be `Double`, `BigDecimal`, or another subtype of `Number`. Capture resolves the identity of an **existing** hidden type; it does not allow assuming that type is a specific subtype.

If you only need to operate on elements as `Number`, using `<E extends Number>` in the helper is appropriate. If you only need to move elements between positions in the same list, an unbounded helper `<E>` suffices; do not add a bound without a reason.

## 7. The Lower-Bounded Case `? super T`: Capture Does Not Turn Read Elements into T

Given:

```java
List<? super Integer> sink = new ArrayList<Number>();
sink.add(7); // Integer can be added
Object result = sink.get(0); // Only guaranteed to be Object
```

The wildcard of `sink` has lower bound `Integer`. The actual element type could be `Integer`, `Number`, `Object`, or another suitable supertype. Hence you cannot read `Integer` directly from `sink`.

A generic helper accepting `List<E>` is also not allowed to assume `E` is strictly `Integer`:

```java
static <E> void inspectCaptured(List<E> list) {
    E element = list.get(0); // Valid
    // Integer n = element; // ERROR: E is not known to be Integer
}
```

Being able to pass `List<? super Integer>` into a helper and preserve type `E` does not turn a lower bound into an upper bound `Integer`. The **guaranteed output type** through a lower-bounded wildcard remains `Object`, unless the API provides independent type evidence.

On the other hand, if the helper only wants to put an **existing element** back into the same list, it can still use a consistent `E`; that is the safety of an internal operation, not the ability to read an `Integer` outside the helper.

## 8. Capture in Generic Methods and Type Inference

Example:

```java
static <E> E first(List<E> list) {
    return list.get(0);
}

static Object readUnknown(List<?> values) {
    return first(values);
}
```

The compiler can capture the wildcard in `values` into an unknown type to infer `E` at the call `first(values)`. The return value is the captured type itself, but the call site can only safely assign it to `Object` when originating from `List<?>`.

Upper-bounded case:

```java
static Number readNumber(List<? extends Number> values) {
    return first(values);
}
```

This is a valid return because the captured type has upper bound `Number`.

Notably: a generic helper **does not force the caller to know the actual type name**. In practice, Java generic methods rely heavily on type inference and capture conversion, even when you never see the compiler report `CAP#1`.

### Independent Wildcard Parameters Do Not Automatically Become the Same E

Consider:

```java
static void moveBad(List<?> source, List<?> destination) {
    destination.add(source.get(0)); // COMPILE ERROR
}
```

The two wildcards in `source` and `destination` can represent **two different element types**. They are not automatically captured into **the same `E`**.

Even if both variables happen to point to the same `List<String>` at runtime, the signature `List<?>, List<?>` does not express that relationship. A `<E>` helper cannot “force” two independent captures to be the same type if the caller has not provided a safe type relationship.

If the goal is to transfer elements from a source to a wider destination, **express the exact relationship** using PECS:

```java
static <E> void copyTo(
        List<? extends E> source,
        List<? super E> destination) {
    for (E value : source) {
        destination.add(value);
    }
}
```

Then `List<Integer>` can be read and transferred into `List<Number>` or `List<Object>`; however, two independent `List<?>` parameters are insufficient to prove the required relationship.

Do not use raw types, unchecked casts, or `@SuppressWarnings("unchecked")` to pretend two lists share the same type. Those approaches can break the element contract and cause delayed cast errors.

## 9. When Should You Use a Helper and When Should You Not?

Use a generic helper when:

1. The public API accepts a `List<?>` or `List<? extends T>` that is sufficiently flexible.
2. A group of operations **needs to preserve the same hidden element type** across multiple places in the method body.
3. The written-back value comes from the list itself or from a transformation constrained as `E -> E`.
4. The operation can be performed without guessing a concrete type and without unchecked casts.

No helper is needed if:

- The API only reads elements via `List<? extends T>` without writing back.
- The API only writes values of type `T` into `List<? super T>`.
- The API already uses `<T> void process(List<T> list, ...)` and the positions already share the same `T`.
- A standard API already expresses the exact operation, such as `Collections.swap` or `Collections.reverse`.

Quick selection table:

| Need | Suggested signature |
| --- | --- |
| Only observe a list of unknown type | `void inspect(List<?> list)` |
| Swap elements of a list of unknown type | `void swap(List<?> list)` calling `<E>` helper, or `Collections.swap` |
| Read and write back the exact hidden element type | `void update(List<?> list)` calling `<E>` helper |
| Read and process as `Number` | `void inspect(List<? extends Number> list)` |
| Transform elements of the same type `E` | `<E> void update(List<E> list, UnaryOperator<E> f)` |
| Add `String` to a list that can hold `String` | `void write(List<? super String> sink)` |
| Copy from source to compatible destination | `<E> void copy(List<? extends E> src, List<? super E> dst)` |

If the helper implementation calls `add` or `set`, the list must support that mutation at runtime. `List.of` generally forbids modification; `Arrays.asList` permits `set` but not size-changing `add`. Type bounds are a **compile-time** concern, whereas structural and content mutability belong to the **object contract**.

## 10. Complete Java 17+ Program

Create **`CaptureExample.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class CaptureExample {
    // Public API accepts a list of an unknown type.
    static void reorder(List<?> items) {
        if (items.size() > 1) {
            swap(items, 0, 1);
        }
    }

    // Helper names E for the captured type.
    private static <E> void swap(
            List<E> items, int left, int right) {
        E old = items.get(left);
        items.set(left, items.get(right));
        items.set(right, old);
    }

    static void duplicateUnknown(List<?> items) {
        duplicate(items);
    }

    private static <E> void duplicate(List<E> items) {
        if (!items.isEmpty()) {
            E first = items.get(0);
            items.add(first);
        }
    }

    // Upper-bounded wildcard is captured inside the helper.
    static void repeatNumber(List<? extends Number> items) {
        repeatLast(items);
    }

    private static <E extends Number> void repeatLast(List<E> items) {
        if (!items.isEmpty()) {
            E last = items.get(items.size() - 1);
            items.add(last);
        }
    }

    public static void main(String[] args) {
        List<String> words =
                new ArrayList<>(List.of("red", "green", "blue"));
        List<?> unknown = words;

        reorder(unknown);
        System.out.println("Swapped: " + words);

        duplicateUnknown(unknown);
        System.out.println("Duplicated: " + words);

        List<Integer> integers = new ArrayList<>(List.of(2, 4));
        List<? extends Number> numbers = integers;

        repeatNumber(numbers);
        System.out.println("Numbers: " + integers);
    }
}
```

Compile and run in the directory containing the file:

```bash
javac -encoding UTF-8 CaptureExample.java
java CaptureExample
```

Output:

```text
Swapped: [green, red, blue]
Duplicated: [green, red, blue, green]
Numbers: [2, 4, 4]
```

Explanation:

- `unknown` has type `List<?>`, so from outside it is not known that the elements are `String`. The call `reorder(unknown)` still works: `swap` preserves the same `E` when reading and writing via `set`.
- `duplicateUnknown` captures the hidden type once in the call `duplicate(items)`; the new element is an existing element, already of type `E`.
- `repeatNumber` takes `List<? extends Number>` and uses the `<E extends Number>` helper to duplicate the last element. The actual element type remains `Integer`, so `[2, 4]` becomes `[2, 4, 4]`.
- All modified lists in the example are `ArrayList` instances, which support `set` and `add`. The wildcard variables are merely views with a broader static type onto the same objects.

The helper methods above are safe **without raw types, unchecked casts, or suppressed warnings**.

## 11. Common Mistakes and Fixes

| Error or misconception | Explanation | Fix |
| --- | --- | --- |
| Assuming `list.set(0, list.get(0))` on `List<?>` always compiles | Wildcard positions in the expression are not bound to the same `E` | Move both `get` and `set` into `<E> helper(List<E>)` |
| Seeing `List<?>` and assuming the element type equals `Object` | The actual type can be `String`, `Integer`, etc. | Understand `?` as an unknown type; only **read** safely as `Object` |
| Using a `<E>` helper to add an arbitrary `String` into `List<?>` | No evidence that type `E` accepts `String` | Use `List<? super String>` when writing `String` is needed |
| Assuming two different `List<?>` parameters share the same capture | Two independent wildcards do not necessarily share a type | Declare the relationship via `List<E>` or PECS pair `? extends E` / `? super E` |
| Thinking a helper permits every mutation | The compiler only checks types; the runtime list may not support `add/set` | Check the implementation contract and exception cases |
| Using an unchecked cast instead of a helper | Casts do not prove the real element type and risk heap pollution | Use a generic method preserving the same `E` |
| Creating a helper just to call `get` and return `Object` | No need to relate multiple `E` positions | Use `List<?>` and `Object` directly |
| Thinking `<E extends Number>` allows adding any `Number` | `E` could still be `Integer` or `Double` | Only write values proven to be `E` |

## 12. Self-Check Exercises

Evaluate the following snippets **individually**. Assume `java.util.*` is imported. Where `static` is declared, place the method inside a Java class body; these snippets are not standalone Java files.

**A — Reassigning a value retrieved from a wildcard**

```java
static void a(List<?> list) {
    list.set(0, list.get(0));
}
```

**B — Moving the operation into a helper**

```java
static <E> void bHelper(List<E> list) {
    if (!list.isEmpty()) {
        list.set(0, list.get(0));
    }
}
static void b(List<?> list) {
    bHelper(list);
}
```

**C — Helper adding a concrete value to a wildcard**

```java
static <E> void addHelper(List<E> list, E x) {
    list.add(x);
}
static void c(List<?> list) {
    addHelper(list, "hello");
}
```

**D — Capturing an upper-bounded list of numbers**

```java
static <E extends Number> void doubleLast(List<E> list) {
    if (!list.isEmpty()) {
        list.add(list.get(list.size() - 1));
    }
}
static void d(List<? extends Number> list) {
    doubleLast(list);
}
```

**E — Two independent wildcards**

```java
static void e(List<?> left, List<?> right) {
    right.add(left.get(0));
}
```

**F — Using PECS with two distinct roles**

```java
static <E> void f(
        List<? extends E> source,
        List<? super E> destination) {
    for (E value : source) {
        destination.add(value);
    }
}
```

**G — Helper present, but the list is unmodifiable**

```java
static <E> void gHelper(List<E> list) {
    if (!list.isEmpty()) {
        list.add(list.get(0));
    }
}
static void g() {
    gHelper(List.of(1, 2));
}
```

**Answers:**

- **A:** Does not compile; the return type of `get` is not accepted in the `set` position because the necessary capture relationship is not preserved.
- **B:** Compiles. `bHelper` uses the same `E` for both read and write operations; if the list does not support `set`, runtime can still reject it.
- **C:** Does not compile at the call `addHelper(list, "hello")`; the hidden element type cannot be proven to be `String`.
- **D:** Compiles. `E` captures the unknown numeric element type and preserves the exact type when duplicating the last element; runtime must support `add`.
- **E:** Does not compile; the element type of `left` has no proven relationship to the element type of `right`.
- **F:** Compiles; the source supplies `E` and the destination accepts `E`. At call sites, the compiler still checks that the argument pair has a compatible type relationship.
- **G:** Compiles, but `List.of` does not support adding elements; at runtime it throws `UnsupportedOperationException`.

## 13. Takeaways

**Wildcard capture** is the compiler mechanism used to represent an unknown wildcard type as a temporary type with an identity and suitable bounds. A **generic helper `<E>`** lets source code name that type and tie `get`, `set`, and `add` positions to the same type parameter.

Common pattern:

```java
static void publicOperation(List<?> values) {
    helper(values);
}

private static <E> void helper(List<E> values) {
    // Read and write values proven to have the same type E.
}
```

This technique does not turn `List<?>` into `List<Object>`, does not permit inserting an arbitrary external value, and does not prove that two independent wildcards share the same type. It preserves type safety when an algorithm needs to **read and write back elements of the same actual type**. When designing APIs with distinct sources and destinations, express the relationship with `? extends E` and `? super E`; when only a standard operation is needed, prefer existing library APIs.