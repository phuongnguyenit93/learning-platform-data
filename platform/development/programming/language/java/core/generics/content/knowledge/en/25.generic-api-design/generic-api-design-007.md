# Isolating Unchecked Casts and Stating Safety Invariants in Java Generics

When designing a generic API, you sometimes have to integrate legacy code using **raw types**, store data in `Object[]`, accept an `Object` from an external source, or convert a reference lacking full type information into a parameterized form. Java may emit an **unchecked cast** warning: the compiler cannot fully prove the target type at runtime, especially when the target type contains generic type arguments removed by *type erasure*.

The proper response is **not** to slap `@SuppressWarnings("unchecked")` onto the entire class or perform a sweeping cast and hope for the best. Good design must address two things simultaneously:

1. **Isolate the cast** at a clear boundary, as small as possible: a local variable, an internal conversion method, or a dedicated adapter for legacy APIs.
2. **State and maintain the invariant** that proves the cast safe within its assumed scope: where data comes from, who is permitted to write, what types are allowed to be stored, whether references escape, when data is verified, and whether any path can break the contract.

Example:

```java
// Summary of the idea behind a generic class:
class Buffer<T> {
    private final Object[] data = new Object[8];

    void set(int index, T value) {
        data[index] = value;
    }

    T get(int index) {
        // Invariant to prove: the element at a valid index was
        // written as T through paths controlled by the class.
        @SuppressWarnings("unchecked")
        T value = (T) data[index];
        return value;
    }
}
```

This snippet **only illustrates cast placement**; it does not yet handle `size`, bounds, or uninitialized elements. The complete program in this lesson handles those points. If you cannot provide a proof for the invariant, you have no basis to call a cast safe merely because the warning disappeared.

## 1. Understanding "unchecked" accurately in Java Generics

Consider a value of unknown origin:

```java
Object input = java.util.List.of("An", 42);

// NO full runtime verification of List<String>:
@SuppressWarnings("unchecked")
java.util.List<String> names = (java.util.List<String>) input;
```

This cast can succeed because the actual object is a `List`; the JVM does not scan each element to verify the `String` type argument. When the second element is later read as `String`, an error may occur:

```java
// String second = names.get(1); // ClassCastException
```

Do not confuse these situations:

| Situation | What can the JVM/compiler verify? | Notes |
| --- | --- | --- |
| `(String) input` | Whether the runtime class is compatible with `String` | Regular checked cast |
| `(List<?>) input` | Whether the runtime object is a `List` | Does not check each element's type |
| `(List<String>) input` | Does not fully verify the `String` type argument | May produce an unchecked warning |
| `(T) item` in a generic method | Usually only up to `T`'s erasure/bound | Needs an invariant or runtime token |
| `(String[]) array` | The runtime component type of the array itself | Different from casting to generic `List<String>` |

**An unchecked warning does not mean every cast is wrong.** It says **the compiler cannot completely prove what you are asserting**. There are internal sites where the implementer maintains a strong enough invariant to justify the cast; there are also direct casts from untrusted data that no annotation can make safe.

### Erasure explains why the compiler must warn

In ordinary generics, `List<String>` and `List<Integer>` do not have two specialized runtime `List` classes. `List<String>.class` does not exist. Thus, checking the outer runtime type does not substitute for checking inner type arguments.

For the same reason, a `Class<T>` can verify **a concrete runtime class** such as `String.class`, yet is insufficient to validate a nested structure like `Map<String,List<Integer>>` using `Class.cast` alone.

## 2. What justifies a cast?

To evaluate an unchecked cast, write out a concrete proof statement:

> Every element read at a valid position in this storage was previously written through operations accepting `T`; the storage is not exposed as a mutable alias; there is no unchecked write path of a wider type than `T`; reads follow the documented synchronization contract.

From that statement, there are obligations to verify:

1. **Data source:** was the value created in typed code or obtained from `Object`/raw/JSON/legacy APIs? If untrusted, validate at the entry boundary.
2. **Write paths:** do all `add`, `set`, `replace`, deserialization, and reflection wrappers truly preserve the type condition?
3. **Read paths:** only read initialized elements within valid index bounds, never confusing `capacity` with `size`.
4. **Encapsulation:** is the internal `Object[]` or collection ever returned for callers to mutate directly?
5. **Aliasing:** is there any raw alias, unchecked alias, iterator/container view, or reference to a backing collection that could break the invariant?
6. **Null policy:** generic `T` can usually accept `null`; does the API allow null and enforce it consistently?
7. **Concurrent modification:** if multiple threads operate concurrently, is there synchronization to preserve atomicity/visibility for required state?
8. **Scope of commitment:** does the proof assume callers obey the normal type system, or must the API defend against untrusted legacy code?
9. **Verification timing:** after data is checked, can it still be mutated via another alias?
10. **Output:** does the return type promise something the runtime object lacks (e.g., `String[]` when the runtime object is `Object[]`)?

Only when you clearly know **the input preconditions**, **the mechanism preserving the invariant**, and **the paths that could break the invariant** can you judge whether an unchecked cast is acceptable.

## 3. Isolating `@SuppressWarnings("unchecked")` to where it is genuinely needed

Compare three scopes:

```java
// Avoid using an overly broad scope by default:
@SuppressWarnings("unchecked")
class BroadSuppression<T> {
    // New casts anywhere in the whole class would also lose warnings.
}
```

```java
// Smaller, yet may still hide other unchecked operations:
@SuppressWarnings("unchecked")
T get(int index) {
    return (T) elements[index];
}
```

```java
// Prefer this when backed by a verified invariant:
T get(int index) {
    java.util.Objects.checkIndex(index, size);

    @SuppressWarnings("unchecked")
    T value = (T) elements[index];

    return value;
}
```

Annotating the local variable makes the intent visible right next to the cast and allows warnings occurring elsewhere to **continue being reported by the compiler**.

**Review principle:** every use of `@SuppressWarnings("unchecked")` should have a **verifiable justification**, not merely "the compiler kept warning". If the cast can be replaced with standard generic APIs, wildcard `?`, or `Class<T>.cast` without altering the contract, it is usually best to eliminate the cast altogether.

### `rawtypes` differs from `unchecked`

```java
java.util.List raw = new java.util.ArrayList(); // raw type
raw.add("An");                                  // unchecked call
```

When enabling `-Xlint:rawtypes -Xlint:unchecked`, you may see warnings of two distinct categories:

- **`rawtypes`**: using raw `List` instead of a parameterized type when possible.
- **`unchecked`**: a call or conversion not fully verified by the compiler.

Do not place `unchecked` suppression on an entire class to hide raw-type warnings; **fix the API's input/output design first**, then tightly isolate what cannot be avoided.

## 4. Typical invariant for `Object[]` as backing storage

In a generic data structure, Java forbids `new T[n]` because `T` is non-reifiable. However, an internal `Object[]` is allowed:

```java
class SimpleStore<T> {
    private Object[] slots = new Object[4];
    private int size;

    void add(T value) {
        slots[size++] = value;
    }

    T get(int index) {
        @SuppressWarnings("unchecked")
        T item = (T) slots[index];
        return item;
    }
}
```

The snippet above is **incomplete**: it can overflow the array or read unused slots. To explain why the cast is safe, the invariant must include structural constraints:

- `0 <= size <= slots.length`.
- Positions `slots[0]` through `slots[size-1]` hold logical elements written via `Store<T>`'s type-safe API.
- `slots` is never leaked outside; no method accepts `Object` and writes without checking.
- `get(i)` only accepts `0 <= i < size`.
- Resize operations preserve the data, types, and order of logical positions.
- If `null` is forbidden, every write operation must check; if `null` is valid, read methods must clarify how a `null` element is distinguished from an unused slot.
- Calling code does not deliberately violate the generic contract with raw/unchecked operations.

These conditions can be controlled by **keeping storage private**, exposing only typed methods, checking indices, and preventing mutable aliases from escaping.

### Why is casting in `get` valid while casting the whole array is not?

When the invariant holds, an individual **element** in the array is in fact an object compatible with `T`. Yet an object array created with `new Object[n]` has runtime class **`Object[]`**, and does not turn into `String[]` when `T = String`.

```java
// Inside a generic class storing private Object[]:
@SuppressWarnings("unchecked")
T[] wrong() {
    return (T[]) slots; // Not a safe runtime T[] promise
}
```

If the caller expects `String[]` while `slots` is `Object[]`, runtime may throw `ClassCastException` at the receiving site. Casting each element and returning a **`T`** based on an invariant is completely different from attributing a **nonexistent runtime component class** to the array.

## 5. Limits of a typed API invariant: raw aliases can still break it

A `Buffer<String>` has an `add(T)` method checked by the compiler when callers use the parameterized type:

```java
Buffer<String> strings = new Buffer<>();
strings.add("Java");
// strings.add(42); // Does not compile
```

Yet if a caller deliberately uses a raw type:

```java
Buffer raw = strings;
raw.add(42); // Unchecked call warning
```

This operation can insert an `Integer` into `Buffer<String>`'s `Object[]` storage. When the caller later reads it as `String`, the compiler's inserted cast can throw `ClassCastException`.

What must be stated in the safety argument is: **the invariant is protected for normal typed usages**. It does not guarantee protection against code intentionally bypassing the type system via raw/unchecked aliases, privileged reflection, or unsafe native operations.

If the library must operate in an environment receiving data from untrusted plugins or legacy code, **runtime validation on entry** using a `Class<T>` token, validator, or specific format/schema may be needed rather than relying solely on compile-time generic `T`.

Do not write "because the field is private, heap pollution is completely impossible" when `add(T)` can still be invoked through a raw alias: `private` only protects **direct field access**, not calls through an API reference stripped of type arguments.

## 6. Untrusted data boundaries: validate, do not merely cast

Suppose an API receives `Object input` from reflection or a legacy system. The wrong approach:

```java
@SuppressWarnings("unchecked")
static <T> java.util.List<T> assume(Object input) {
    return (java.util.List<T>) input;
}
```

This method essentially promises to return `List<T>` without checking **a single element**. Even if the outer object is a `List`, one wrong element can fail in the caller later. It also fails to distinguish the error properly if `input` is not a list.

The recommended approach when you need a list whose elements belong to a concrete runtime class:

```java
static <T> java.util.List<T> checkedCopy(
        Object input, Class<T> elementType) {
    java.util.Objects.requireNonNull(elementType, "elementType");

    if (!(input instanceof java.util.List<?> source)) {
        throw new IllegalArgumentException("not a List");
    }

    java.util.List<T> result =
            new java.util.ArrayList<>(source.size());

    for (Object item : source) {
        result.add(elementType.cast(
                java.util.Objects.requireNonNull(item, "element")));
    }

    return java.util.List.copyOf(result);
}
```

Every step has a purpose:

1. **Check the outer structure**: `instanceof List<?>` confirms the object is a `List`, without confirming element types.
2. **Require a token**: `Class<T> elementType` specifies the expected runtime class, e.g., `String.class`.
3. **Check each element**: `elementType.cast(item)` verifies the object is compatible with the expected runtime class. Invalid values fail immediately at the boundary.
4. **Define null policy**: `requireNonNull(item)` explicitly rejects `null` data rather than relying on `List.copyOf` failing at the end of the method.
5. **Copy**: return a new structurally unmodifiable list so it no longer depends on the source's mutable structure after validation.
6. **No unchecked casts**: type safety comes from `Class<T>.cast` returning `T` for each checked item.

This is one **API contract choice**, not mandatory for every source. If `null` is permitted, choose a different policy and result construction, since `List.copyOf` rejects nulls.

### `Class<T>` is not enough for nested generics

`String.class` lets you check an element of type `String`; however, there is no `List<String>.class`. Thus, if you need to check `List<List<String>>` or `Map<String, List<Integer>>`, you must use a validator/schema that traverses each level; a raw-typed `Class<List>` only checks the outer structure.

**Do not pretend that `Type` or `ParameterizedType` validates data on its own.** Reflection metadata describes a declaration/type schema; a library wishing to verify data must execute validation against that schema.

## 7. Maintaining a safe contract with `List.copyOf` or immutable snapshots

If you receive a `List<?> source` that might still be mutated through another alias, "validate everything then cast the original reference to `List<T>`" still carries risk:

```java
// DO NOT do this to expose untrusted data:
boolean allStrings = source.stream().allMatch(String.class::isInstance);

// Immediately afterward, source could be mutated through another alias.
// @SuppressWarnings("unchecked")
// List<String> result = (List<String>) source;
```

Even if at one moment every element is a `String`, **that runtime fact does not automatically turn `List<?>` into `List<String>` at compile time**. Moreover, if the mutable list remains shared, the checked invariant can become false later.

Copying each element **after checking** into a new container of type `T` is a better approach. `List.copyOf` in `checkedCopy` decouples the result structure from the source, though note:

- `List.copyOf` returns a structurally unmodifiable list; it **does not deep-copy mutable element objects**.
- If the source list is modified **during iteration**, errors, inconsistent reads, or other implementation-dependent behavior may occur. Do not claim that merely calling `List.copyOf` creates an atomic snapshot against arbitrary concurrent modification.
- If concurrent multi-threaded data must be supported, specify a concurrency policy and take a consistent snapshot under proper synchronization.

A safe API must clearly state **when checks happen**, **who owns the result**, and **future constraints on the data**.

## 8. Where are wrappers like `Collections.checkedList` useful?

Java provides wrappers that check the runtime class of elements whenever writes go through the wrapper:

```java
java.util.List<String> backing = new java.util.ArrayList<>();
java.util.List<String> checked =
        java.util.Collections.checkedList(backing, String.class);

checked.add("ok");

java.util.List raw = checked;
// raw.add(42); // Emits unchecked warning; wrapper throws ClassCastException
```

Advantage: if legacy code calls `add` through **the checked wrapper itself**, an element runtime-incompatible with `String` is stopped near the write boundary.

However, the invariant must clearly note:

- The wrapper **does not fix** mistyped contents already present in the backing list before wrapping.
- Another **alias** pointing directly to `backing` can bypass the wrapper and cause heap pollution.
- The wrapper also does not turn Java generics into reified generics; `String.class` only checks one concrete runtime class.
- The wrapper does not automatically make the backing list thread-safe or immutable.

Therefore, `checkedList` is a **runtime guard on the operations it mediates**, not a substitute for controlling backing collection ownership or validating untrusted data sources.

## 9. Array factory: when casting elements differs from casting the entire array

If you need to return a true typed array to callers, do not write:

```java
// Wrong runtime target if slots is actually new Object[n]:
@SuppressWarnings("unchecked")
T[] expose() {
    return (T[]) slots;
}
```

Instead, ask the caller to supply an array factory:

```java
T[] toArray(java.util.function.IntFunction<T[]> factory) {
    java.util.Objects.requireNonNull(factory, "factory");

    T[] output = java.util.Objects.requireNonNull(
            factory.apply(size), "array");

    if (output.length != size) {
        throw new IllegalArgumentException("length");
    }

    System.arraycopy(slots, 0, output, 0, size);
    return output;
}
```

When `T = String`, the caller uses:

```java
String[] names = buffer.toArray(String[]::new);
```

The result is a **true `String[]`**, because `String[]::new` creates an array with runtime component type `String`. `System.arraycopy` will apply array store checks to the target array; it does not alter the runtime type of the backing `Object[]`.

However, an array factory also has a **contract**: it must allocate an appropriate `T[]` array of the requested size. In the code above, `null` and mismatched lengths are rejected. If a caller uses raw/unchecked code to pass a factory producing an incompatible array type, runtime can catch the mismatch; do not claim the method is immune to every untrusted factory.

## 10. Complete Java 17+ program: safety, check boundaries, and counterexamples

Save as **`UncheckedBoundaryDemo.java`**:

```java
import java.util.*;
import java.util.function.IntFunction;

public class UncheckedBoundaryDemo {
    static final class Buffer<T> {
        private Object[] slots = new Object[2];
        private int size;

        void add(T value) {
            if (size == slots.length) {
                slots = Arrays.copyOf(slots, slots.length * 2);
            }
            slots[size++] = value;
        }

        T get(int index) {
            Objects.checkIndex(index, size);

            // Invariant: slots[0..size) are written via add(T)
            // under parameterized use; storage does not escape.
            @SuppressWarnings("unchecked")
            T value = (T) slots[index];

            return value;
        }

        T[] toArray(IntFunction<T[]> arrayFactory) {
            Objects.requireNonNull(arrayFactory, "arrayFactory");

            T[] result = Objects.requireNonNull(
                    arrayFactory.apply(size), "array");

            if (result.length != size) {
                throw new IllegalArgumentException("length");
            }

            System.arraycopy(slots, 0, result, 0, size);
            return result;
        }
    }

    static <T> List<T> checkedCopy(
            Object candidate, Class<T> elementType) {
        Objects.requireNonNull(elementType, "elementType");

        if (!(candidate instanceof List<?> source)) {
            throw new IllegalArgumentException("not a List");
        }

        List<T> result = new ArrayList<>(source.size());

        for (Object value : source) {
            result.add(elementType.cast(
                    Objects.requireNonNull(value, "element")));
        }

        return List.copyOf(result);
    }

    // Intentionally wrong: this cast does not guarantee elements belong to T.
    static <T> List<T> assumedList(Object candidate) {
        if (!(candidate instanceof List<?>)) {
            throw new IllegalArgumentException("not a List");
        }

        @SuppressWarnings("unchecked")
        List<T> result = (List<T>) candidate;

        return result;
    }

    public static void main(String[] args) {
        Buffer<String> buffer = new Buffer<>();
        buffer.add("An");
        buffer.add("Binh");

        System.out.println("Buffer read: " + buffer.get(0));

        String[] copy = buffer.toArray(String[]::new);
        System.out.println("Typed array: " + Arrays.toString(copy));
        System.out.println("Array type: "
                + copy.getClass().getTypeName());

        List<String> safe =
                checkedCopy(List.of("A", "B"), String.class);
        System.out.println("Validated list: " + safe);

        List<?> mixed = List.of("A", 42);

        try {
            checkedCopy(mixed, String.class);
        } catch (ClassCastException ex) {
            System.out.println("Mixed input: ClassCastException");
        }

        try {
            checkedCopy(List.of("ok"), Integer.class);
        } catch (ClassCastException ex) {
            System.out.println("Wrong token: ClassCastException");
        }

        try {
            checkedCopy(List.of("A"), null);
        } catch (NullPointerException ex) {
            System.out.println("Missing token: NullPointerException");
        }

        List<String> wronglyAssumed =
                UncheckedBoundaryDemo.<String>assumedList(mixed);

        try {
            String value = wronglyAssumed.get(1);
            System.out.println(value);
        } catch (ClassCastException ex) {
            System.out.println(
                    "Unchecked assumption: ClassCastException");
        }

        // Intentionally breaking the invariant with a raw alias:
        Buffer<String> polluted = new Buffer<>();
        Buffer raw = polluted;
        raw.add(42);

        try {
            String value = polluted.get(0);
            System.out.println(value);
        } catch (ClassCastException ex) {
            System.out.println("Raw alias: ClassCastException");
        }

        List<String> backing = new ArrayList<>(List.of("ok"));
        List<String> checked =
                Collections.checkedList(backing, String.class);

        List rawChecked = checked;

        try {
            rawChecked.add(42);
        } catch (ClassCastException ex) {
            System.out.println("Checked wrapper: ClassCastException");
        }

        System.out.println("Backing after blocked add: " + backing);
    }
}
```

Compile and run on JDK 17 or later:

```bash
javac -encoding UTF-8 -Xlint:rawtypes -Xlint:unchecked UncheckedBoundaryDemo.java
java UncheckedBoundaryDemo
```

**Standard output** of the program (excluding compiler warnings):

```text
Buffer read: An
Typed array: [An, Binh]
Array type: java.lang.String[]
Validated list: [A, B]
Mixed input: ClassCastException
Wrong token: ClassCastException
Missing token: NullPointerException
Unchecked assumption: ClassCastException
Raw alias: ClassCastException
Checked wrapper: ClassCastException
Backing after blocked add: [ok]
```

**Interpreting results by trust boundaries:**

1. `Buffer<String>` initially accepts only strings through `add(T)`, does not expose `slots`, and `get` reads within `size`. The internal unchecked cast is backed by a concrete invariant.
2. `toArray(String[]::new)` creates a real typed array; the backing array remains `Object[]` and is never returned directly.
3. `checkedCopy` validates each element from the `Object` source against `String.class` or `Integer.class`; bad data fails **right at the conversion boundary**.
4. `assumedList` only confirms the outer object is a `List` and casts unchecked, **checking no elements**; failure occurs when the caller reads `Integer` as `String`.
5. Raw `Buffer` bypasses compile-time generic checking to write `Integer` into a buffer typed as `Buffer<String>`. The internal cast cannot rescue an already-broken invariant.
6. `Collections.checkedList` catches `Integer` when the raw alias tries to call `add` through the wrapper; the backing list stays `[ok]`.

The program contains two raw aliases **intentionally used to demonstrate failures**, so `-Xlint:rawtypes -Xlint:unchecked` is expected to warn on those lines. Explicitly marking where code is unsafe matters more than trying to silence every warning with broad suppression.

## 11. `Class<T>` is not a way to "reify" all generics

A `Class<T>` API is very useful when the desired type is a concrete runtime class:

```java
static <T> T verified(Object candidate, Class<T> type) {
    return type.cast(candidate);
}

String name = verified("Java", String.class);
```

If an `Integer` is passed for `String.class`, `ClassCastException` happens at `cast`. No unchecked cast is needed.

However, `List<String>.class` does not exist. For a generic list:

```java
Object input = List.of("A", 42);

boolean outer = input instanceof List<?>; // true
```

`outer` only proves the outer type. To restore a complex data contract, you need a validator capable of traversing nested levels and specifying the corresponding null/covariance/mutability policies.

If a system uses reflection `Type`/`ParameterizedType` or a type token to describe `List<String>`, that metadata helps specify **the schema** to check, yet still does not traverse and validate an object against the schema automatically. Keep **type specification** separate from **validation execution**.

## 12. For legacy APIs, where should the trust boundary be placed?

An application may have to call an old library returning a raw `List`:

```java
// Illustrative legacy signature:
static java.util.List loadLegacy() {
    return java.util.List.of("An", "Binh");
}
```

A common mistake is scattering `(List<String>) loadLegacy()` casts across multiple layers, then letting the whole project use `List<String>` as though the data had been validated.

One approach is creating a **single adapter**:

```java
static List<String> loadNames() {
    return checkedCopy(loadLegacy(), String.class);
}
```

This adapter is a clear boundary: once it returns, callers receive a typed snapshot created by the method and do not need to know the original legacy source was raw.

Document the adapter:

- The raw source might not be a list or might contain mistyped elements.
- Mistyped elements throw `ClassCastException` at the `Class.cast` step.
- Null elements throw `NullPointerException` per the chosen policy.
- The returned list is structurally unmodifiable, though mutable element objects are not automatically deep-copied.
- If source data is mutated concurrently during iteration, the adapter does not promise an atomic snapshot without a synchronization policy.

With a legacy source already trusted under a **separately proven** contract, there may be places using an internal unchecked cast; however, specifically document **who the producer is, what protects the data, and which conditions invalidate the assumption**.

## 13. Invariants that look right at first glance yet are insufficient in practice

### 13.1. "The list currently contains only Strings"

This invariant describes **a single point in time** and is insufficient if a raw alias or another thread can add an `Integer` right after checking.

You must add the condition that **no uncontrolled mutation path remains** or create a snapshot under proper synchronization.

### 13.2. "Every call to `add` takes `T`"

True for callers using typed `Buffer<String>`, yet a raw alias `Buffer raw` can still call `add(42)` with a warning. If the safety boundary must defend even against raw callers, use a runtime token to validate at write time.

### 13.3. "An array holding String elements is a String[]"

False. An array created with `new Object[n]` still has runtime component type `Object`, even when every element is a `String`. Casting the entire array to `String[]` can throw `ClassCastException`.

### 13.4. "Suppression is on just one line so the cast is definitely safe"

False. **A narrow scope aids auditing** and avoids hiding other warnings; it does not prove the data contents. Verify the invariant before suppressing.

### 13.5. "A checked wrapper protects the entire backing list"

Not if a direct alias to the backing list can still mutate it. `Collections.checkedList` checks operations **going through the wrapper**, without monitoring every other reference to the same object.

### 13.6. "Copying elements is enough for thread safety"

Copying element by element creates a structurally separate result, yet if the source is concurrently mutated during iteration, the snapshot may be inconsistent. Specify synchronization or appropriate immutable structures when multi-threading is required.

## 14. Generic arrays and varargs: suppression cases needing separate evaluation

A generic class is not allowed to write `new T[n]` because `T` is non-reifiable. Using an internal `Object[]` plus per-element casts is not equivalent to creating a real `T[]`.

A generic varargs method can also produce warnings:

```java
static <T> void visit(T... values) {
    for (T value : values) {
        System.out.println(value);
    }
}
```

Varargs are passed as an array. When the element type is non-reifiable, the compiler may warn about potential **heap pollution** and generic array creation.

If the implementation is genuinely safe and the declaration is eligible, `@SafeVarargs` may be placed on constructors or `static`, `final`, or `private` methods (subject to the Java version):

```java
@SafeVarargs
static <T> void printAll(T... values) {
    for (T value : values) {
        System.out.println(value);
    }
}
```

`@SafeVarargs` is **an author commitment**; it does not make `T` reifiable and cannot fix mistyped writes into the varargs array through an `Object[]` alias.

When auditing casts or generic arrays, evaluate separately:

- The actual runtime array type created (`Object[]`, `String[]`, or `List[]`).
- Whether the array escapes or retains an alias.
- Whether mistyped writes are possible through raw or `Object[]` references.
- Whether requirements to assert `@SafeVarargs` are truly met.

Do not add `@SafeVarargs` or `@SuppressWarnings` merely to silence warnings without analyzing the method body.

## 15. Bounded generics do not create a concrete runtime class for `T`

Example:

```java
static <T extends Number> T identity(T value) {
    return value;
}
```

The `Number` bound tells the compiler that operations declared on `Number` can be used, and `T`'s erasure is based on that bound. It does **not** turn `T` into a concrete runtime class such as `Integer` on every call.

If a generic adapter writes:

```java
@SuppressWarnings("unchecked")
static <T extends Number> T assumeNumber(Object value) {
    return (T) value;
}
```

the cast may only check that the object is compatible with `Number`. If the caller expects `Integer` while the real data is `Double`, failure may occur when the caller consumes the result.

Similarly, a type parameter `T extends Comparable<? super T>` permits calling `compareTo` per the compile-time generic relationship, yet does not verify that every untrusted object belongs to a container's exact type argument.

When a receiving boundary needs to check a concrete subtype, use `Class<T>` or a suitable validator instead of assuming a bound is enough.

## 16. Review checklist: is an unchecked cast ready to merge?

Check these questions before approving code:

1. **Why can't the compiler prove it automatically?** Because of erasure, a raw legacy boundary, a generic backing array, or something else?
2. **Can the cast be avoided?** Use `List<?>`, `Class<T>.cast`, typed copies, factories, PECS wildcards, or standard generic APIs.
3. **If unavoidable, where is the cast located?** Is a small local variable or adapter method the tightest appropriate spot?
4. **Is the stated invariant concrete?** E.g., "all `slots[0..size)` are written via `add(T)`, with no mutating alias escaping".
5. **Have all write paths been listed?** `set`, `addAll`, deserialization, listeners/callbacks, raw APIs?
6. **Is there risk of raw aliases/unchecked casts from callers?** Have trust preconditions been clearly bounded?
7. **How is `null` handled?** Rejected and reported immediately, or allowed consistently across all write paths?
8. **Does storage ever leak?** Returning `Object[]`, array views, backing collections, or mutable internal iterators?
9. **Are reads confined to the valid logical range?** Are `size` and index checks accurate?
10. **Is there a concurrency policy?** If the public API is intended to be thread-safe, the type-safety proof must align with the synchronization proof.
11. **At what scope is the cast suppressed?** Could it unintentionally hide other warnings?
12. **Do tests include mistyped cases?** Mixed data, nulls, raw aliases, runtime array mismatches, empty lists?
13. **Are API results tested?** Is the result a snapshot or a view; mutable or unmodifiable; clearly documented in Javadoc?
14. **Is runtime proof present when needed?** Does `Class<T>.cast` or a validator actually verify data at the boundary?
15. **Should linter flags be enabled in CI?** E.g., `javac -Xlint:unchecked -Xlint:rawtypes`, reviewing warnings at each site.

If you cannot answer the questions about write paths and invariants, an unchecked cast should not yet be considered proven safe.

## 17. Common mistakes

**Mistake 1 — "An unchecked cast means the code will definitely throw an exception."** No. The compiler warns because it cannot prove safety; the cast may succeed or fail depending on invariants and data.

**Mistake 2 — "Suppressing the warning makes the JVM check the generic type argument."** No. The annotation only affects compiler diagnostics.

**Mistake 3 — "A `List<String>` obtained by casting `Object` has been validated."** No. Only the outer `List` type may have been checked; individual elements remain unverified.

**Mistake 4 — "A `private Object[]` guarantees the invariant automatically."** No. A raw `add` call can still corrupt contents; a public getter leaking an alias also breaks encapsulation.

**Mistake 5 — "Casting `(T[]) new Object[n]` creates an array with the right runtime type."** No. When `T = String`, the object is still `Object[]`.

**Mistake 6 — "Once the whole list is validated, casting the original reference is safe forever."** Not if the list is mutable and another alias exists. A validated copy handles structural risks better, though consistent snapshots are still required under concurrent mutation.

**Mistake 7 — "All casts in a generic class should be suppressed at the class level."** No. That easily hides newly introduced unsafe operations.

**Mistake 8 — "`Class<T>` can validate `List<Map<K,V>>`."** No. A single class token does not represent nested type arguments.

**Mistake 9 — "`Collections.checkedList` checks writes through backing aliases too."** No. Only operations going through the wrapper are protected by the wrapper's checks.

**Mistake 10 — "The bound `T extends Number` proves an object is `Integer` when the caller expects `Integer`."** No. A bound describes a subtype relationship, without locking `T` to one concrete subtype at runtime.

**Mistake 11 — "If no `ClassCastException` happens at the cast site, the data is definitely safe."** No. Failure can surface much later during a subsequent read or access.

**Mistake 12 — "A JUnit test with one `List<String>` is enough to prove the cast."** No. Testing one happy example does not replace proving all write paths, aliases, lifetimes, and contracts.

## 18. Self-check exercises

**Question 1.** Why can `(List<String>) input` from an `Object` be an unchecked cast?

Because the JVM has no specialized runtime class carrying the `String` type argument for `List` to check in full; the cast can verify the outer type without verifying every element.

**Question 2.** Should `@SuppressWarnings("unchecked")` be placed on an entire class for a clean build?

Usually no. Isolate it to the exact local variable or method backed by a clear invariant so other warnings continue to be reported.

**Question 3.** What is the core condition justifying `(T) slots[i]` in `Buffer<T>`?

Elements within the valid range are written through typed paths preserving `T`; storage does not leak and there are no unchecked write paths under the usage assumptions; indices/size are checked.

**Question 4.** Why is `(T[]) slots` different from casting individual elements?

An array created with `new Object[n]` has runtime component type `Object`; casting does not change the array's class to `String[]` when `T = String`.

**Question 5.** What does `Class<String>.cast(42)` do?

It throws `ClassCastException` right at the check boundary because `Integer` is incompatible with runtime class `String`. This is a checked runtime cast of an object.

**Question 6.** Does `Collections.checkedList(backing, String.class)` fix pre-existing mistyped values?

No. The wrapper checks compatible operations going **through the wrapper itself**; it neither repairs the backing list nor stops external aliases from writing directly.

**Question 7.** If an API validates a list and then returns the original mutable list, what risk remains?

Another alias can mutate the list after validation, invalidating the type promise. Proper ownership and validation/snapshot policies are needed.

**Question 8.** What does enabling `-Xlint:rawtypes -Xlint:unchecked` accomplish?

It surfaces raw types and unchecked operations so reviewers know where to focus analysis; on its own, it does not prove code is free of or afflicted by heap pollution.

**Question 9.** Can `T extends Number` replace `Integer.class` when an exact runtime `Integer` check is needed?

No. `Number` is an upper bound of many subtypes; a token or validator matching the actual requirement is needed.

## 19. Conclusion: a small scope, a clear proof

An unchecked cast can be a reasonable choice **inside a tightly encapsulated generic API**, but only when you clearly state and maintain the invariant proving the contents are valid. Place the cast at **a visible trust boundary**; keep `@SuppressWarnings("unchecked")` at **the smallest scope**; keep raw types and backing arrays out of ordinary API surfaces; validate untrusted data with `Class<T>.cast` or a validator instead of slapping labels on via unchecked casts.

**Do not equate four distinct things:** compile-time type parameters, runtime object classes, generic reflection metadata, and actual data contents. Only when these relationships are accurately expressed in signatures/Javadoc and protected by concrete checks or invariants does a generic API deserve to be called type-safe, even if it contains an internal cast that the compiler cannot prove on its own.