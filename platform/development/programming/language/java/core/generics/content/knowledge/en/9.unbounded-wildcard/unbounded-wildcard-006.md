# Each Wildcard `?` Can Represent a Different Type in Java Generics

In Java Generics, the question mark `?` denotes **an unspecified type parameter**. When declaring `List<?>`, we know it is a list belonging to **some concrete element type**, yet we do not know whether that type is `String`, `Integer`, or another reference type.

Key point: **two wildcard positions do not implicitly represent the same type**. Each wildcard can be treated by the compiler as a separate hidden type. Those two hidden types *might coincide in reality*, yet if the program cannot express the relationship between them, the compiler **is not allowed to assume they are equal**.

This lesson falls under the topic of *unbounded wildcards* and focuses on reading data, why transferring elements between two `List<?>` lists is rejected, the **wildcard capture** mechanism, and how to use generic methods to preserve type safety.

## 1. What does `List<?>` actually say?

Consider:

```java
List<String> names = List.of("An", "Binh");
List<Integer> ages = List.of(20, 25);

List<?> first = names;
List<?> second = ages;
```

Both assignments are valid. Unlike `List<Object>`, `List<?>` does not assert that the list holds `Object`; it only states that **the type argument is currently unknown**.

- For `first`, the actual element type of the referenced list is `String`.
- For `second`, the actual element type is `Integer`.
- Looking only at the `List<?>` signature, the compiler does not know each of those hidden types.
- Two `?` signs **are not two variables with the same name** binding them together. They can represent two independent types.

Any list can be read through `List<?>` as `Object`:

```java
Object name = first.get(0);
Object age = second.get(0);
```

This is safe because every Java object of a reference type can be used as `Object`. However, assigning directly `String text = first.get(0)` will not compile, even though the programmer knows `first` was just assigned from `names`: the expression `first.get(0)` is checked against the **declared type of `first`, which is `List<?>`**.

> Understand `?` as “there is an element type, yet the user of this reference does not know that type”; do not understand it as “elements can have any type and be freely added”.

`List<?>` is equivalent in type-bound meaning to `List<? extends Object>`. It is a wildcard **without an explicit bound**, having a default upper bound of `Object`.

## 2. Two independent wildcards: same symbol, not necessarily the same type

The following method accepts **any two lists**:

```java
static void showFirstPair(List<?> left, List<?> right) {
    Object a = left.get(0);
    Object b = right.get(0);
    System.out.println(a + " | " + b);
}
```

The signature has two distinct `?` signs:

```text
showFirstPair(List<?>, List<?>)
                   ^        ^
                type X    type Y
```

This is an illustrative diagram of **two unknown types**; `X` and `Y` are not real type names in the declaration. `X` and `Y` *may be equal or different*, yet the signature does not require them to be equal.

For example, both calls are valid (assuming the method and lists are already declared):

```java
showFirstPair(List.of(10, 20), List.of("An", "Binh"));
showFirstPair(List.of("Java"), List.of("Generics"));
```

In the first call, the lists carry elements of two different types. In the second call, both lists have `String` elements. **The `List<?>` signature accepts both cases**, because it does not constrain the two type arguments to match.

Even more importantly: even when two references actually point to **the same list object**, that relationship is not inferred as a shared type constraint between two uses of `?`.

```java
List<Integer> original = new ArrayList<>(List.of(1, 2));
List<?> a = original;
List<?> b = original;

Object x = a.get(0); // Valid.
Object y = b.get(0); // Valid.
a.set(0, b.get(0));  // COMPILE ERROR.
```

The `set` line intentionally illustrates an error, not standalone runnable code. In this situation, a human sees `a` and `b` both pointing to `original`, yet the static type `List<?>` provides no proof that the capture type used for `a`'s write parameter equals the element type read from `b`.

## 3. Why can't elements be transferred between two `List<?>`?

Try writing the method:

```java
static void moveFirst(List<?> destination, List<?> source) {
    destination.add(source.get(0)); // COMPILE ERROR.
}
```

Suppose two `?` signs were always treated as the same type; then the `add` statement would look valid. Yet this method could also be called with:

```java
List<Integer> destination = new ArrayList<>(List.of(1));
List<String> source = List.of("Java");

// moveFirst(destination, source);
// If the wrong method above were accepted, it could
// insert a String into a list meant only for Integer.
```

The `List<Integer>` contract requires the added element to be compatible with `Integer`. `source.get(0)` from `List<String>` returns `String`. Therefore Java forbids the write right at compile time.

We can summarize the principle as follows:

| Operation with two `List<?>` | Valid? | Why |
| --- | --- | --- |
| `Object a = left.get(0)` | Yes | Any element type can be read as `Object` |
| `Object b = right.get(0)` | Yes | Same for the second wildcard |
| `left.add(right.get(0))` | No | Unknown whether `right`'s type fits `left` |
| `left.set(0, right.get(0))` | No | Replacing an element must also satisfy `left`'s element type |
| `left.add(null)` | Type-valid | `null` is compatible with every reference type; collection may still reject at runtime |
| `left.clear()` | Type-valid | Removing elements introduces no new type; collection may still not support it |
| `left.contains(right.get(0))` | Type-valid | `contains(Object)` takes `Object` to check, does not add elements |

Do not use `?` as a way to circumvent type-safety rules. The `?` sign allows **general data observation**, while restricting operations that require knowing the element type.

## 4. Wildcard capture: the compiler binds a hidden type to `?`

When processing `List<?>`, the compiler can perform **capture conversion**: temporarily treating the wildcard as an unknown yet consistent type within an appropriate scope. Error messages from `javac` sometimes mention `capture#1 of ?`, `capture#2 of ?`.

Illustrative example, not Java code to declare:

```text
List<?> left  → List<CAP#1>
List<?> right → List<CAP#2>

CAP#1 and CAP#2:
- Both have upper bounds compatible with Object.
- No constraint that CAP#1 = CAP#2.
- May coincide on a concrete type at runtime; the compiler still cannot assume so.
```

The names `CAP#1` and `CAP#2` only describe how to understand errors, **not Java types you can write in source code**. The numbering and exact error wording are decided by the compiler, not part of the API.

One especially confusing example:

```java
static <T> void requireSameType(List<T> one, List<T> two) {
    // Signature requires the same T for both parameters.
}

static void demo(List<?> items) {
    requireSameType(items, items); // COMPILE ERROR.
}
```

Even when repeating **the exact same variable** `items` twice, the two argument expressions can be captured independently. The compiler cannot infer a single shared `T` satisfying both equality constraints.

This does not contradict passing **one** `List<?>` to a generic method with **one** `List<T>` parameter: in that case Java only needs to capture one hidden type and use it consistently inside the method.

## 5. Why doesn't reading as `Object` prove the right to write?

Each `List<?>` has a hidden element type. The value from `get(0)` can be used as `Object`, yet `Object` is too broad to automatically become the element type of the destination list:

```java
static void inspect(List<?> left, List<?> right) {
    Object first = left.get(0);
    Object second = right.get(0);
    System.out.println(first + " / " + second);
    // left.add(second); // Does not compile: two independent captures.
}
```

Even `left.add(first)` is not automatically statically safe, because the variable `first` is `Object`. The special exception `add(null)` only speaks to `null`'s assignability, not guaranteeing the list is mutable or accepts null. **The specific problem here:** we need a provable type relationship between different wildcard positions. A generic helper can only safely capture **one list argument** and keep the same `T` internally; to transfer elements between two lists, the relationship between the two types must be declared directly in the API.

## 6. Capturing the same type with a generic helper

There are **safe** modifications on a list of unknown type, provided we only **move elements within that very list** without introducing elements from an unrelated list.

For example, swapping two positions in a `List<?>`. Writing it directly easily causes a capture error:

```java
static void swapWrong(List<?> items, int a, int b) {
    // items.set(a, items.get(b)); // COMPILE ERROR.
}
```

The common solution is an outer method accepting the wildcard and an inner **generic helper** naming the hidden type:

```java
static void swap(List<?> items, int a, int b) {
    swapCaptured(items, a, b);
}

private static <T> void swapCaptured(List<T> items, int a, int b) {
    T oldA = items.get(a);
    items.set(a, items.get(b));
    items.set(b, oldA);
}
```

How it works:

1. `swap` takes `List<?>`, so callers can pass `List<String>`, `List<Integer>`, or lists of other types.
2. When calling `swapCaptured(items, ...)`, Java captures the wildcard and infers a matching `T` **for a single `items` argument**.
3. Inside `swapCaptured`, every `get` and `set` works with **one `List<T>`**; taking a `T` from one position and putting it back in another is valid.
4. The method does not need to know whether `T` is specifically `String` or `Integer`; it only ensures internal operations do not break `T`'s contract.

This is a solution for **one wildcard of one list**, not turning two independent `List<?>` lists into the same type. It is the *wildcard capture helper* technique commonly used when an API must accept `List<?>` yet an internal operation must stay linked to the exact hidden element type.

Beyond generic checks, you still need to ensure indices `a`, `b` are valid and the list is modifiable. Otherwise, the runtime can throw `IndexOutOfBoundsException` or `UnsupportedOperationException`.

## 7. If two lists must have a type relationship, express it with `T`

When you want to **transfer elements from one list to another**, you must describe the source–destination relationship precisely.

### 7.1. Requiring the same type argument

```java
static <T> void appendFirstSameType(List<T> destination, List<T> source) {
    destination.add(source.get(0));
}
```

`T` in both positions **is the same type variable**. If the caller has `List<String>` and `List<String>`, the call fits. If the caller has `List<String>` and `List<Integer>`, Java cannot pick a `T` satisfying both `List<T>` parameters because generic collections are invariant.

Comparison:

```java
List<String> source = List.of("Java");
List<String> destination = new ArrayList<>();
appendFirstSameType(destination, source); // Valid.

// List<Integer> integers = new ArrayList<>();
// appendFirstSameType(destination, integers); // COMPILE ERROR.
```

This is how you express a **same-type requirement** in the API. It differs from two unconstrained `?` signs.

### 7.2. Source is a subtype, destination accepts a supertype

Sometimes the source is `List<Integer>` and the destination is `List<Number>`. The two list types **differ**, yet elements can still be transferred safely because every `Integer` is also a `Number`.

```java
static <T> void appendFirst(
        List<? extends T> source,
        List<? super T> destination) {
    destination.add(source.get(0));
}
```

- `List<? extends T>` allows **reading** elements as `T` from the source.
- `List<? super T>` allows **writing** `T` elements into the destination.
- **The same `T`** connects both parameters, with appropriate bounded wildcards.

This is an application of the **PECS** principle: *Producer Extends, Consumer Super*. Here `source` is the producer of elements; `destination` is the receiver of elements. This case cannot be fully expressed with two independent `List<?>` parameters, because they provide no information about the element-type relationship.

Do not cast `(List<Number>)(List<?>) integers` to “fix” the error. Unsafe casts do not create a real type relationship and can corrupt the list's contract.

## 8. Complete Java 17+ example

The program below demonstrates simultaneously:

- Two independent `List<?>` parameters can accept two different list types.
- A generic helper can swap elements **within the same list**.
- A generic method with `extends/super` bounds can transfer elements from `List<Integer>` to `List<Number>`.

Save as **`WildcardDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class WildcardDemo {
    static void showFirstPair(List<?> left, List<?> right) {
        Object a = left.get(0);
        Object b = right.get(0);
        System.out.println(a + " | " + b);
    }

    static void swap(List<?> items, int a, int b) {
        swapCaptured(items, a, b);
    }

    private static <T> void swapCaptured(List<T> items, int a, int b) {
        T oldA = items.get(a);
        items.set(a, items.get(b));
        items.set(b, oldA);
    }

    static <T> void appendFirst(
            List<? extends T> source,
            List<? super T> destination) {
        destination.add(source.get(0));
    }

    public static void main(String[] args) {
        List<Integer> ints = new ArrayList<>(List.of(10, 20, 30));
        List<String> names = new ArrayList<>(List.of("An", "Binh"));

        List<?> first = ints;
        List<?> second = names;
        showFirstPair(first, second);

        swap(ints, 0, 2);
        swap(names, 0, 1);
        System.out.println(ints);
        System.out.println(names);

        List<Number> numbers = new ArrayList<>();
        appendFirst(ints, numbers);
        System.out.println(numbers);

        showFirstPair(ints, names);
    }
}
```

Compile and run:

```bash
javac WildcardDemo.java
java WildcardDemo
```

Stdout:

```text
10 | An
[30, 20, 10]
[Binh, An]
[30]
30 | Binh
```

**Result explanation:** `first` references `List<Integer>` and `second` references `List<String>`, so `showFirstPair` reads `10` and `An` as `Object`. `swap` swaps element positions inside each list with their actual types preserved. After swapping, the first number of `ints` is `30`, which is validly added to `numbers` of type `List<Number>`. Two lists with different element types are still handled uniformly when only reading is required.

## 9. You cannot “use one `T`” to force two independent captures to become the same type

You might try solving the problem by passing both `List<?>` into a generic helper:

```java
static <T> void copySameType(List<T> to, List<T> from) {
    to.add(from.get(0));
}

static void copyUnknown(List<?> to, List<?> from) {
    copySameType(to, from); // COMPILE ERROR.
}
```

`copySameType` by itself is valid because it requires two `List<T>` with **exact one `T`**. Yet calling `copySameType(to, from)` cannot prove that the two independent captures of `to` and `from` correspond to the same type. A helper cannot invent type information that the two outer parameters do not provide.

Even the following case can still fail:

```java
static void copyUnknown(List<?> items) {
    copySameType(items, items); // COMPILE ERROR: two independent captures.
}
```

Important difference:

- `swapCaptured(items)` takes only **one `List<T>`**; after capture, every read/write in the helper uses the same `T`.
- `copySameType(items, items)` has **two argument positions** that must both match one `T`; from a `List<?>` expression, the capture of each position is not implicitly the same type.
- `copySameType(typed, typed)` with `typed` declared as `List<Integer>` is valid because the `Integer` type is already expressed in the type system.

When a task genuinely requires a relationship between two parameters, place that relationship in the **outer API signature** using `<T>` and the necessary bounds. When only operating internally on one list of unknown type, use a capture helper with **one list**.

## 10. `Map<?, ?>`: two wildcards in the same generic type

A similar situation appears when a generic type has **multiple type arguments**:

```java
Map<?, ?> data = Map.of("language", 17);
Object key = data.keySet().iterator().next();
Object value = data.values().iterator().next();
```

The first `?` describes the unknown key type; the second `?` describes the unknown value type. There is no default condition that **the key type must equal the value type**. For example, both `Map<String, Integer>` and `Map<Long, Long>` can be referenced by `Map<?, ?>`.

In most write operations, you cannot insert an arbitrary non-null key or value into `Map<?, ?>`, because their hidden types are unknown. This same reasoning applies to `BiFunction<?, ?, ?>` and other generic types with multiple `?` signs: **each wildcard position must be considered under its own constraint**.

## 11. Common misconceptions

### “Using the same `?` symbol means the same type”

**False.** `?` is not a reusable named variable like `T`. Two different wildcards do not automatically generate an equality constraint. At runtime they might relate to the same element kind, yet the compiler needs static evidence expressed through types.

### “Both lists are `List<?>`, so you can add from one to the other”

**False.** Both are compatible with the `List<?>` interface type for **reading**, which does not mean their element types are compatible for **writing**. For example, `List<Integer>` and `List<String>` are both assignable to `List<?>`, yet elements cannot be transferred arbitrarily between them.

### “A list declared as `List<?>` can hold all kinds of objects”

**False regarding write capability.** `List<?>` references a list with an unknown concrete element type; that does not grant permission to add every kind of object. If you want a list whose elements have different types and need to add arbitrary objects, you can use `List<Object>` when the problem design truly calls for it.

### “A generic helper will automatically unify two hidden types”

**False.** A helper only helps Java **name a capture** and apply it consistently inside the method body. If given two lists with no type relationship, you cannot assert a shared `T` by blindly calling a helper.

### “`List<?>` is immutable”

**False.** Wildcard type and collection mutability are two independent matters. An `ArrayList<String>` through `List<?>` can call `clear()`, whereas `List.of(1, 2)` can reject modification even when the reference is declared with a concrete `List<Integer>`.

### “Type erasure makes wildcards no different”

**False.** Type erasure affects how generics are represented at runtime; assignments, captures, and type constraints are still enforced by the **Java compiler** before execution. You cannot use the fact that multiple `List<T>` have their generic arguments erased to infer that elements can be exchanged between two `List<?>`.

## 12. Self-check

With the following declarations, examine **compilability**, assuming methods are called on non-empty lists when reading:

```java
List<Integer> ints = new ArrayList<>(List.of(1, 2));
List<String> texts = new ArrayList<>(List.of("A", "B"));
List<?> a = ints;
List<?> b = texts;
```

| Expression | Result | Explanation |
| --- | --- | --- |
| `Object x = a.get(0);` | Valid | Reads `List<?>` as `Object` |
| `String s = b.get(0);` | Compile error | `b.get(0)` only guarantees an unknown type, safely used as `Object` |
| `a.add(b.get(0));` | Compile error | Cannot prove the two wildcards have compatible types |
| `a.set(0, a.get(0));` | Compile error | Two captures can be independent; needs a generic helper |
| `a.add(null);` | Type-valid | `null` is accepted type-wise; runtime depends on collection |
| `showFirstPair(a, b);` | Valid | Method only reads the two lists as `Object` |
| `swap(ints, 0, 1);` | Valid | Generic helper handles one `Integer` list |
| `appendFirst(ints, new ArrayList<Number>());` | Valid | `Integer` can be added to a destination accepting `Number` |

Note: “type-valid” does not guarantee runtime always succeeds; for example `get(0)` on an empty list still throws `IndexOutOfBoundsException`, or `add(null)` on an unmodifiable collection can still throw an exception.

## Key takeaways

1. `?` is **an unknown type parameter**, not a shared variable named `?`.
2. **Each wildcard/capture can correspond to a different type**; they may also coincide, yet the compiler does not assume an equality relationship automatically.
3. `List<?>` allows **reading out `Object`**; it does not guarantee being able to write non-null elements of a concrete type.
4. When you need to operate inside **one list** while preserving the element type, use a generic helper to capture it as `List<T>`.
5. When you need to operate between **two lists with a type relationship**, describe the relationship using `<T>`, `? extends T`, and `? super T`, instead of merely reducing both to `List<?>`.

Understanding the independence of each `?` helps explain `capture of ?` errors in Java and choose the right generic signatures for APIs—flexible when reading data while preserving type safety when writing.