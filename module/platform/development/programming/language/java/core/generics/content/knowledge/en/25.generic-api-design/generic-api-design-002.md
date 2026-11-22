# Naming and Documenting Type Relationships in Java Generics

When designing Java APIs using Generics, a signature that is **syntactically valid** is not necessarily **easy to understand in terms of its contract**. The names `T`, `E`, `K`, `V`, `R`; `extends` bounds; `? extends`/`? super` wildcards; and the details written in Javadoc work together to answer:

- Which type is the **input**, and which type is the **result**?
- Must two parameters be the **same type**, or do they only have a subtype/supertype relationship?
- Is a parameter a **source producing data** or a **destination consuming data**?
- Does the type constraint live on the **class**, the **method**, or a wildcard at the **parameter site**?
- What is enforced by the compiler, and what belongs to the **runtime contract** such as `null`, mutation, ownership, and exceptions?

For example, consider the same goal of "transforming each element from a source into a new result form":

```java
// Valid signature, but hard to understand without role-based names:
static <T, U> java.util.List<U> transform(
        Iterable<? extends T> x,
        java.util.function.Function<? super T, ? extends U> y);

// Can be named by role for better readability:
static <S, R> java.util.List<R> map(
        Iterable<? extends S> source,
        java.util.function.Function<? super S, ? extends R> mapper);
```

Both express the same **type relationship** in the example: input of type `S`, result of type `R`; source providing `S`; mapper accepting a suitable supertype of `S` and returning a suitable subtype of `R`. However, the latter reveals its intent through the method name, the variables `source`/`mapper`, and the symbols `S`/`R` even before reading the Javadoc.

**Core principle:** **names describe roles, signatures express compiler-enforced constraints, and Javadoc explains semantics and behavior that cannot be inferred from types alone**. Do not use comments to compensate for a signature that conveys the wrong type relationship.

## 1. Type parameter naming conventions in Java

Java typically uses **short uppercase names**, especially when roles are well-established conventions:

| Name | Common role | Context |
| --- | --- | --- |
| `T` | General Type | `Box<T>`, `List<T>`, simple generic methods |
| `E` | Element | `Collection<E>`, `List<E>`, `Set<E>` |
| `K` | Key | `Map<K, V>` |
| `V` | Value | `Map<K, V>`, whereas `Optional<T>` uses `T` |
| `R` | Result/Return | `Function<T, R>`, map/convert APIs |
| `U`, `S` | Second type / Source | Methods relating two independent types |
| `T1`, `T2` | Types with the same role distinguished by position | Some multi-argument abstractions |

These are **conventions**, not names with special meaning to the compiler. `class Box<T>` and `class Box<V>` are equally valid if all corresponding references are updated consistently.

For an interface/map:

```java
interface Lookup<K, V> {
    V get(K key);
}
```

The names `K` and `V` make it immediately clear that `get` takes a **key** and returns a **value**. An API using `<T,U>` for the same roles would compile, but forces the reader to guess more.

### When to use longer names?

If an API has many type parameters with complex relationships, descriptive names like `<SOURCE, RESULT>`, `<INPUT, OUTPUT>`, or `<KEY, VALUE>` can be chosen when codebase conventions permit. Java allows such identifiers, though short names `T`, `U`, `R`, `K`, `V` are more common in the standard Java library.

Long names **do not fix a broken design**. For instance, `<INPUT, OUTPUT>` does not establish type safety if the method still performs unproven unchecked casts. Keep type parameter names short and consistent when roles are obvious; use semantically rich names when the contrast genuinely helps readability of a difficult signature.

### Variable and method names also matter

Compare:

```java
static <T> void f(java.util.List<? extends T> a,
                  java.util.List<? super T> b);

// Easier to understand:
static <T> void copy(
        java.util.List<? extends T> source,
        java.util.List<? super T> destination);
```

The first signature has the right type relationship but does not state its purpose; the second highlights the **direction of data**. In implementation code, names like `source`, `destination`, `mapper`, `predicate`, `comparator`, `factory`, `fallback`, and `result` are often just as important as the name `T`.

## 2. Identify the type relationship before choosing names

A generic design usually revolves around four kinds of relationships:

1. **Same type:** multiple positions use the same type variable `T`, such as `T choose(T left, T right)`.
2. **Two independent types with a transformation:** `<S,R> R convert(S source, Function<? super S,? extends R> mapper)`.
3. **Subtype constraint:** `<T extends Number>` or `<T extends Comparable<? super T>>`.
4. **Use-site variance relationship:** `Collection<? extends T>` as source, `Collection<? super T>` as destination.

A simple example:

```java
static <T> T first(java.util.List<T> items) {
    return items.get(0);
}
```

The name `T` appears in `List<T>` and the return type `T`. This is a **compiler-checked relationship**: `List<String>` yields `String` at the call site, `List<Integer>` yields `Integer` (according to inference rules and the static type of the call).

If the return type is changed to `Object`, the method can still run but **loses the type relationship** in its signature:

```java
static Object firstUnclear(java.util.List<?> items) {
    return items.get(0);
}
```

That can be a reasonable API when the intent is simply to read a value of unknown type, but it cannot replace the `<T> T first(List<T>)` contract if callers need to receive the result without casting.

**Design question:** is there a real type relationship worth expressing with the **same type variable**? If so, do not weaken the signature to `Object` and write in Javadoc "caller casts the result".

## 3. Type parameter scope: class-level or method-level?

A type parameter has a **declaration site**. `T` at the class level and `T` on an individual method are not automatically the same type variable.

```java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value; // T of class Box
    }

    static <U> Box<U> of(U value) {
        return new Box<>(value); // U of static method of
    }
}
```

`Box<String>` holds a `String` from the compiler's perspective. `Box<Integer>` holds an `Integer`. The `of` method is a **static generic method** declaring its own `U`; it does not directly reference the class's `T` in a static context.

An easy-to-make API mistake:

```java
class Store<T> {
    // The method's T below is a NEW T, not Store's T:
    <T> void accept(T value) { }
}
```

This snippet compiles, but the method-level `T` **shadows** the class's `T`. If the goal is only to accept the `T` that the store carries, write:

```java
class Store<T> {
    void accept(T value) { }
}
```

If the goal is an independent second type, write `<U>` and document the relationship between `U` and `T`.

**Do not reuse the same type parameter name in nested scopes merely because the compiler allows it.** Readers struggle to distinguish the class-level type contract from the method-level type contract, especially in APIs with many overloads.

## 4. Do not declare a type parameter when it creates no useful relationship

Consider a utility that only prints a collection:

```java
static <T> void printAll(java.util.Collection<T> items) {
    for (T item : items) {
        System.out.println(item);
    }
}
```

This code is valid, but if `T` appears only once in the declaration and the method needs no special relationship, a wildcard can be simpler:

```java
static void printAll(java.util.Collection<?> items) {
    for (Object item : items) {
        System.out.println(item);
    }
}
```

The `?` expresses that the method **does not need to know or name** the element type. This suits APIs that only observe, count, log, or measure size.

However, **appearing only once does not always require a wildcard**. A generic method still needs `T` when relating the type to a return type, callback, bound, a related exception declaration, or when the API needs contextual type inference. Practical rules:

- **Need to name the type to bind multiple positions?** Use a type parameter `<T>`.
- **Only need to accept a container of unknown type?** Use `?` if no meaning is lost.
- **Only one fixed business type?** Use the concrete type, such as `Collection<String>`, and do not over-generalize unnecessarily.

Good design reduces the number of type variables users have to infer.

## 5. Source–destination relationship: encode it directly in the signature with PECS

In Generics, **PECS** is the familiar principle: *Producer Extends, Consumer Super*.

- The source **produces** values read as `T`: `Iterable<? extends T>`.
- The destination **consumes** values of `T`: `Collection<? super T>`.

A copying API:

```java
static <T> int copyInto(
        Iterable<? extends T> source,
        java.util.Collection<? super T> destination) {
    int accepted = 0;
    for (T item : source) {
        if (destination.add(item)) {
            accepted++;
        }
    }
    return accepted;
}
```

With `List<Integer>` as source and `List<Number>` as destination:

```java
java.util.List<Integer> integers = java.util.List.of(2, 4, 6);
java.util.List<Number> numbers = new java.util.ArrayList<>();

int accepted = copyInto(integers, numbers); // 3
```

Writing `copyInto(List<T>, List<T>)` would make the API more restrictive than necessary because `List<Integer>` is **not a subtype** of `List<Number>`: Java generics are **invariant**.

### What PECS allows, and what it does not promise

- `? extends T` allows reading elements as `T`; it does not mean an arbitrary `T` can be added to the source through that wildcard reference.
- `? super T` allows adding `T` to the destination; reading from the destination can in general only be safely used as `Object` if the destination's exact type is unknown.
- PECS is a **type compatibility** rule; it does not prove that the destination is mutable, forbids nulls, or that `add` always returns `true`. These points must be documented per the specific collection contract.

For a destination `Set` that already contains duplicate elements, `add` can return `false`. Hence the `copyInto` example returns **the number of times `destination.add(item)` reported `true`**, without claiming the number of source elements visited or the final element count for every kind of collection.

If the API intends to return the number of *processed* elements, name it `processedCount` and increment the counter on each iteration. **The result name, Javadoc, and logic must match.**

## 6. Transformation relationship: name `S` and `R` for clear input/output

A `map` operation typically relates a **source type** `S` to a **result type** `R`:

```java
static <S, R> java.util.List<R> map(
        Iterable<? extends S> source,
        java.util.function.Function<? super S, ? extends R> mapper) {
    java.util.List<R> result = new java.util.ArrayList<>();
    for (S item : source) {
        result.add(mapper.apply(item));
    }
    return result;
}
```

Signature breakdown:

- `<S, R>`: two independent type parameters; `S` is not required to be a subtype of `R`.
- `Iterable<? extends S>`: the source may supply subtypes of `S`.
- `Function<? super S, ? extends R>`: callback accepting a type suitable for handling `S` and returning a result suitable to be viewed as `R`.
- `List<R>`: result list with element type `R`.

Call:

```java
java.util.List<Integer> ids = java.util.List.of(2, 4);
java.util.List<String> labels = map(ids, id -> "id-" + id);
```

The compiler infers the relationship between `Integer` and `String` from the lambda expression, target type, and `map` signature. No `(List<String>)` cast or `Object` in the public API is needed.

### Why not just use `Function<S,R>`?

`Function<S,R>` is also valid, but is often **narrower** than `Function<? super S, ? extends R>` in APIs that need to accept callbacks with a wider input type or narrower output type. However, do not sprinkle wildcards out of habit: wildcards lengthen signatures and sometimes complicate type inference/diagnostics. Use wildcards where the API genuinely needs type flexibility.

For an interface already designed with appropriate type parameters, the shorter form can be chosen to prioritize usability. **Generality must serve the use case**, not be a goal in itself.

## 7. Upper bounds: names and Javadoc must clarify constraints

A generic method that needs to compare elements can use a bound:

```java
static <T extends Comparable<? super T>> java.util.Optional<T>
greatest(Iterable<? extends T> source) {
    T best = null;
    boolean found = false;
    for (T item : source) {
        java.util.Objects.requireNonNull(item, "element");
        if (!found || item.compareTo(best) > 0) {
            best = item;
            found = true;
        }
    }
    return found ? java.util.Optional.of(best)
                 : java.util.Optional.empty();
}
```

`T extends Comparable<? super T>` states that `T` can be compared with `T` itself or with an appropriate supertype. This form is more useful than `Comparable<T>` in some inheritance models, because a subtype can inherit comparability declared on a supertype.

**Reading it accurately:** `extends` in a type parameter declaration `<T extends ...>` expresses an **upper bound**, even when the bound is an interface; `? super T` is a **use-site lower-bounded wildcard**, not type variable declaration syntax.

The Javadoc for `greatest` should also explain decisions beyond the signature:

- For an empty source, returns `Optional.empty()` instead of `null`.
- For a `null` element, throws `NullPointerException`, because the example forbids nulls.
- Relies on the **natural ordering** of each `T` value.
- Finds the greatest element in the provided data; does not sort or modify the source collection.
- Does not provide thread-safety/snapshot guarantees for a mutable source modified concurrently.

The bound only proves the compiler can invoke a matching `compareTo`. It **does not decide on its own** how empty inputs or nulls are handled.

## 8. Standard Javadoc: `@param <T>` differs from `@param value`

Javadoc has dedicated syntax to document a **type parameter**:

```java
/**
 * Creates a box containing one value.
 *
 * @param <T> type of the boxed value
 * @param value value to store; must be non-null
 * @return a box containing {@code value}
 * @throws NullPointerException if {@code value} is null
 */
static <T> Box<T> of(T value) { /* ... */ }
```

Distinction:

- `@param <T>`: describes the **type parameter T** of the method/class.
- `@param value`: describes the **value parameter `value`** of the method.
- `@return`: describes the result and important conditions on the result.
- `@throws` or `@exception`: describes errors intentionally thrown by the API under its contract.

The `<T>` angle brackets inside the `@param` tag are **special Javadoc syntax** for type parameters. They are not equivalent to `@param T` (which describes a formal parameter named `T`, if one exists).

Javadoc supports `{@code ...}` for code snippets and `{@link ...}` to link related APIs; use them to clarify terminology without overusing markup.

### Javadoc for a class-level type parameter

```java
/**
 * Stores exactly one value.
 *
 * @param <T> type of the stored value
 */
public final class Box<T> {
    private final T value;

    private Box(T value) {
        this.value = java.util.Objects.requireNonNull(value);
    }

    public T get() {
        return value;
    }
}
```

If a class has `<K,V>`, document **both**:

```java
/**
 * Associates keys with values.
 *
 * @param <K> type of keys used to locate values
 * @param <V> type of values stored in the association
 */
interface Registry<K, V> { /* ... */ }
```

Do not just write `@param <K> key` when the contract also needs to specify key equality/hashing or whether null keys are allowed. Java's generic convention `K`/**`V`** does not automatically carry those semantics; the API author must describe them in the corresponding documentation.

## 9. Javadoc for the `S` → `R` relationship

For `map`, Javadoc should explain the relationships rather than merely repeating the signature verbatim:

```java
/**
 * Applies a mapper to each source element, in iteration order.
 *
 * @param <S> source element type
 * @param <R> resulting element type
 * @param source elements to transform; may contain null elements
 * @param mapper transformation applied once to each visited element
 * @return a new mutable list of mapped values, preserving source order
 * @throws NullPointerException if source or mapper is null
 */
static <S, R> java.util.List<R> map(
        Iterable<? extends S> source,
        java.util.function.Function<? super S, ? extends R> mapper) {
    java.util.Objects.requireNonNull(source, "source");
    java.util.Objects.requireNonNull(mapper, "mapper");
    java.util.List<R> result = new java.util.ArrayList<>();
    for (S value : source) {
        result.add(mapper.apply(value));
    }
    return result;
}
```

In this example, `map` does not forbid `null` in the source and does not reject a mapper returning `null`, because `ArrayList` allows nulls. Therefore accurate documentation can explicitly state **result may contain null elements** if that matters to the public API.

If an unmodifiable list is desired, `List.copyOf(result)` can be chosen when the contract forbids nulls, but **both code and Javadoc** must be updated, since `List.copyOf` rejects `null` and has structural snapshot semantics. Do not describe an "immutable result" in Javadoc and then actually return a mutable `ArrayList`.

### Javadoc is not a substitute for explaining wildcards mechanically

There is no need to explain every `? extends` and `? super` mechanically on every method if module-level documentation already covers it. Instead, describe the **roles**: readable source, processing callback, newly created result, receiving destination. Yet for a non-obvious API, an `@apiNote` or a call example `List<Integer>` → `Collection<Number>` can help users understand why the wildcard exists.

## 10. Complete Java 17+ example: clear type relationships and names

Save to **`GenericApiNamingDemo.java`**:

```java
import java.util.*;
import java.util.function.*;

public class GenericApiNamingDemo {
    /** A pair whose first and second components may differ in type. */
    record Pair<A, B>(A first, B second) {}

    /** A container carrying one value of type T. */
    static final class Box<T> {
        private final T value;

        private Box(T value) {
            this.value = Objects.requireNonNull(value, "value");
        }

        /**
         * Builds a box from an input value.
         *
         * @param <U> type of the input and stored value
         * @param value a non-null value
         * @return a box containing the value
         * @throws NullPointerException if value is null
         */
        static <U> Box<U> of(U value) {
            return new Box<>(value);
        }

        T get() {
            return value;
        }
    }

    /**
     * Sends each element from a source into a destination.
     *
     * @param <T> type accepted from the source
     * @param source elements to read, in iteration order
     * @param destination collection receiving source elements
     * @return number of destination add calls that returned true
     * @throws NullPointerException if source or destination is null
     * @throws UnsupportedOperationException if destination rejects adds
     */
    static <T> int copyInto(
            Iterable<? extends T> source,
            Collection<? super T> destination) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(destination, "destination");
        int accepted = 0;
        for (T item : source) {
            if (destination.add(item)) {
                accepted++;
            }
        }
        return accepted;
    }

    /**
     * Transforms source elements into a new mutable list.
     *
     * @param <S> source element type
     * @param <R> resulting element type
     * @param source values to transform, in iteration order
     * @param mapper function mapping each S into a compatible R
     * @return new mutable list of mapped values in source order
     * @throws NullPointerException if source or mapper is null
     */
    static <S, R> List<R> map(
            Iterable<? extends S> source,
            Function<? super S, ? extends R> mapper) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(mapper, "mapper");
        List<R> result = new ArrayList<>();
        for (S value : source) {
            result.add(mapper.apply(value));
        }
        return result;
    }

    /**
     * Finds the greatest value under its natural ordering.
     *
     * @param <T> comparable element type
     * @param source non-null iterable containing no null elements
     * @return greatest element, or Optional.empty() if source is empty
     * @throws NullPointerException if source or any element is null
     */
    static <T extends Comparable<? super T>> Optional<T> greatest(
            Iterable<? extends T> source) {
        Objects.requireNonNull(source, "source");
        T best = null;
        boolean seen = false;
        for (T value : source) {
            Objects.requireNonNull(value, "element");
            if (!seen || value.compareTo(best) > 0) {
                best = value;
                seen = true;
            }
        }
        return seen ? Optional.of(best) : Optional.empty();
    }

    public static void main(String[] args) {
        List<Integer> ids = List.of(2, 4, 6);
        List<Number> numbers = new ArrayList<>();

        System.out.println("Copied: " + copyInto(ids, numbers));
        System.out.println("Numbers: " + numbers);

        List<String> labels = map(ids, x -> "id-" + x);
        System.out.println("Mapped: " + labels);

        System.out.println("Greatest: "
                + greatest(ids).orElseThrow());
        System.out.println("Empty maximum: "
                + greatest(List.<Integer>of()));

        Pair<String, Integer> pair = new Pair<>("age", 20);
        System.out.println("Pair: " + pair.first()
                + "=" + pair.second());

        Box<String> box = Box.of("Java");
        System.out.println("Box: " + box.get());
    }
}
```

Compile and run with Java 17 or later:

```bash
javac -encoding UTF-8 -Xlint:all GenericApiNamingDemo.java
java GenericApiNamingDemo
```

Standard output:

```text
Copied: 3
Numbers: [2, 4, 6]
Mapped: [id-2, id-4, id-6]
Greatest: 6
Empty maximum: Optional.empty
Pair: age=20
Box: Java
```

Interpretation focusing on **relationships between types**, not just computed values:

1. `copyInto` accepts a `List<Integer>` source and a `Collection<Number>` destination, because `Integer` is compatible with `Number`. The compiler applies PECS without needing raw types.
2. `map` receives `Integer` values, the callback produces `String`, and it returns `List<String>`. The two type parameters `S` and `R` have different roles.
3. `greatest` uses `Comparable<? super T>` and returns `Optional<T>`, so the output data type remains tightly linked to the input. An empty source yields `Optional.empty()`.
4. `Pair<A,B>` indicates that the two components **may have different types**, without forcing them into the same `T`.
5. `Box<T>` preserves the instance type relationship; the static factory `Box.of` declares its own `U`, creating a box with an inferred type argument.

For `copyInto`, the contract does not promise the operation is **atomic**: if the destination collection throws an exception during iteration, earlier elements may already have been added. For aliased source/destination or concurrent modification, a separate usage policy is needed; the example does not promise safe copying across every collection kind in such situations.

## 11. Distinguishing the same `T` from two differently related types

Consider two APIs:

```java
static <T> T choose(T first, T second) {
    return first;
}

static <A, B> Pair<A, B> pair(A first, B second) {
    return new Pair<>(first, second);
}
```

In `choose`, the same type variable `T` allows the compiler to find a type `T` compatible with both arguments via type inference. **This does not necessarily force both objects to have the same runtime class.** For example, when passing `String` and `Integer`, the compiler can infer a suitable common supertype in a given context. If the API truly requires "both elements must have the exact same runtime class", a signature `<T> T choose(T,T)` **does not guarantee that on its own**.

In `pair`, `A` and `B` are kept independent, making clear that first and second can have different types.

Be careful with names like `T1`, `T2`: they distinguish type variables, **not force two types to be different**. Callers can still use the same `String` for both `T1` and `T2`. Document the roles "first component" and "second component"; do not falsely write "must be distinct Java types" if the signature cannot enforce that condition.

### When to use the names `A`, `B`?

For an independent pair structure `Pair<A,B>`, two simple, neutral symbols are usually appropriate. For a key/value pair, `Entry<K,V>` is usually clearer. Choose based on **semantics**, not merely the number of type parameters.

## 12. Distinguishing upper bounds, wildcards, and business contracts

Three signatures serve different roles:

```java
static <T extends Number> void acceptNumber(T value) { }

static void readNumbers(List<? extends Number> numbers) { }

static <T> void append(T value, Collection<? super T> target) { }
```

- `<T extends Number>`: declares a **named type variable** with an upper bound; `T` can be reused in multiple positions in the signature.
- `List<? extends Number>`: a **use-site wildcard**; the parameter can be a list of a `Number` subtype, while elements can only be read safely as `Number`.
- `Collection<? super T>`: wildcard for a consumer; `T` can be added to it.

Do not write Javadoc such as "`? extends Number` means every item must have runtime class Number". Subtypes like `Integer` and `Double` are compatible at compile time, while runtime data still needs to respect generic invariants.

An upper bound also does not imply the API always "accepts every subclass" if the method has additional runtime conditions. Similarly, a wildcard does not determine the null policy: `List<? extends Number>` can contain nulls if the backing collection allows them; the type system does not forbid nulls by default.

## 13. Relationships with callbacks: input `super`, output `extends`

A typical callback type:

```java
Function<? super T, ? extends R>
```

It combines two roles:

- The function's **input parameter** consumes a value of type `T`: use `? super T` to accept a function declared to take a suitable supertype.
- The function's **result** supplies a value of type `R`: use `? extends R` to accept a function returning a suitable subtype.

Example:

```java
java.util.function.Function<Number, String> describe =
        number -> "n=" + number;

java.util.List<Integer> input = java.util.List.of(1, 2);
java.util.List<CharSequence> output = map(input, describe);
```

In a suitable target-typing context, `S` can be `Integer` and `R` can be `CharSequence`: `Function<Number,String>` accepts `Integer` as a `Number` and returns `String`, which is a subtype of `CharSequence`. This expresses flexibility that an exact `Function<S,R>` might not permit.

**However, check usability:** Java generics have complex inference when multiple wildcards are nested. If users frequently have to add casts or type witnesses to call an everyday API, consider overloads or changing the signature. The theoretically broadest API is not necessarily the easiest API to use.

## 14. Compile-time guarantees and runtime contracts: document them separately

A signature like:

```java
static <T> void addAll(
        Collection<? extends T> source,
        Collection<? super T> destination)
```

tells the compiler the **type relationship between source and destination elements**. However, it does not say:

- Is `destination` **mutable** and does it support `add`?
- Is `null` accepted?
- Can the input be empty?
- If an error occurs midway, can `destination` be partially modified?
- Is the source's iteration order preserved in `destination`? A `Set` may reorder or deduplicate depending on implementation.
- May `source` and `destination` share the same object/alias?
- Is the operation thread-safe? Does it copy a snapshot?

These belong to the **semantic contract** and should be written in the Javadoc of public APIs. For example:

> *Adds each source element to destination in iteration order. This operation may modify destination before throwing. The destination must support additions; null elements must be accepted by its contract.*

In this README, this sentence is an **example of explanatory text**, not a claim that every `Collection` accepts nulls or preserves order. State the specific conditions and behavior of the method being designed.

### Nullness and generic type arguments

`List<String>` **does not mean non-null list elements** in the standard Java type system. If an API forbids nulls, state this clearly in the documentation and check at the boundary (`Objects.requireNonNull`), or use a nullness annotation system established by the codebase. Do not rely on the word `String` to imply something the compiler does not guarantee.

### Ownership and mutability

`List<R>` in the `map` signature does not say whether the result is mutable or unmodifiable. If the function returns `new ArrayList<>()`, the Javadoc can state "new mutable list"; if it returns `List.copyOf`, it must state the null policy, the unmodifiability of the container, and its shallow-copy nature. Update the Javadoc at the same time whenever an implementation change affects the public contract.

## 15. Expressing errors and choices when there is no data

A `max` method can choose between:

```java
static <T extends Comparable<? super T>> T maxNonEmpty(
        Collection<? extends T> elements) { /* ... */ }

static <T extends Comparable<? super T>> Optional<T> maxOptional(
        Collection<? extends T> elements) { /* ... */ }
```

Both signatures describe the same bound on `T`, but differ in their **empty-data contract**.

- `maxNonEmpty` can require non-empty input and throw `NoSuchElementException` or `IllegalArgumentException` by design.
- `maxOptional` can return `Optional.empty()` if the input is empty.

A good README or Javadoc must state the implementation's exact choice, rather than simply saying "returns the largest T".

Also, do not use `Optional<T>` to avoid stating a null policy: `Optional` is not designed as a wrapper holding `null`; the behavior when a source element is `null` must be decided.

## 16. Overloading, type inference, and readable names

An "overly generic" API can make compiler errors hard for callers to read:

```java
static <A, B, C, D> D route(A a, B b,
        java.util.function.BiFunction<? super A, ? super B, ? extends C> f,
        java.util.function.Function<? super C, ? extends D> g) {
    return g.apply(f.apply(a, b));
}
```

Although valid, users have to resolve four type parameters and multiple wildcards. Only introduce that level of generality if there is a worthwhile use case. If the business flow is always "parse → validate → save", clear domain class names and operations are usually better than an abstract four-type `route` function.

When a generic method returns a value via target typing, it is sometimes helpful to use a result variable with an explicit type:

```java
List<String> names = map(List.of(1, 2), x -> "item-" + x);
```

If type inference still struggles in a complex call, you can choose a lambda with explicit parameter types or supply an appropriate type witness like `SomeClass.<Integer,String>map(...)`. However, **do not use unchecked casts as a default workaround**; that may only defer failures to runtime.

### Avoid overloads differing only in type parameter names

```java
// CANNOT be declared together in the same class if erased signatures collide:
static <T> void process(List<T> values) {}
static <U> void process(List<U> values) {}
```

Renaming `T` to `U` does not create a distinct overload; both have the same erased signature. A public API must distinguish overloads by **genuinely different parameter type information**, not by the letters of type parameters.

## 17. Writing Javadoc examples to demonstrate wildcard usefulness

For a public API transferring data from source to destination, a short example is worth more than repeatedly explaining PECS in the abstract:

```java
List<Integer> ids = List.of(1, 2);
List<Number> numbers = new ArrayList<>();

int accepted = copyInto(ids, numbers);
```

It shows users:

- A `List<Integer>` source is accepted even though the destination is `List<Number>`.
- `List<Object>` does not need to be used as the default destination type when unnecessary.
- `copyInto` writes into `destination`, rather than creating a new output list.
- The return value expresses the number of times `destination` accepted an element according to the method's contract.

Good Javadoc should include **at least one example with subtype-related types** if wildcard flexibility is a primary feature. Testing only `List<String>` → `List<String>` fails to demonstrate the real benefit of `extends` and `super`.

## 18. Common naming and documentation mistakes

**Mistake 1 — "Using `T` everywhere means the exact same type."** No. Type parameter scopes differ, and type inference can select a common supertype for multiple arguments.

**Mistake 2 — "`E`, `K`, `V` are mandatory keywords."** No. They are conventions for expressing element/key/value.

**Mistake 3 — "When input and output differ, just use the same `T`."** No. If the two roles can differ in type, use `<S,R>` or appropriate names to keep the contract accurate.

**Mistake 4 — "Add `<T>` even when unnecessary because it looks more generic."** No. For an API that only observes a collection without relating types, `Collection<?>` can be clearer than `<T> Collection<T>`.

**Mistake 5 — "`List<T>` and `List<? extends T>` are equivalent."** No. The wildcard gives the source subtype flexibility that the invariant form does not have.

**Mistake 6 — "`? super T` on a source lets you read exact `T`."** No. It is generally suited for a **consumer**; when reading via a `super` wildcard, the safe value type may only be `Object`.

**Mistake 7 — "`@param T` in Javadoc is enough for a type parameter."** No. Type parameters use `@param <T>` syntax.

**Mistake 8 — "`@param <T>` replaces explaining nullability/mutability."** No. The tag describes the type role; the semantic contract must be documented separately.

**Mistake 9 — "Returning `List<R>` automatically means the result is unmodifiable."** No. The interface and generic type argument do not determine mutability.

**Mistake 10 — "`T extends Number` means only exact runtime `Number` is accepted."** No. Subtypes such as `Integer` also match under upper-bound rules.

**Mistake 11 — "A `Pair<A,B>` forces `A` and `B` to be different."** No. Two independent type parameters can both be bound to the same type.

**Mistake 12 — "Javadoc can promise an unchecked cast is safe even if the code checks nothing."** No. Javadoc does not make a cast check an erased type argument; the contract must be designed and proven by the API.

**Mistake 13 — "The names `source`/`destination` do not matter because the compiler checks types."** No. The compiler checks type validity, whereas users need to know the **direction of side effects and ownership** to use the API correctly.

## 19. Self-check exercises

**Question 1.** If an API takes a value of type `T` and returns the exact same kind of type `T`, should you use `<T>` or `<S,R>`?

Usually use `<T>` to express the same type-variable relationship, provided it matches the actual contract.

**Question 2.** Does `Map<K,V>` force key and value to be two distinct runtime classes?

No. `K` and `V` are two independent type parameters; the same type argument can be bound to both.

**Question 3.** Why does `copyInto(Iterable<? extends T>, Collection<? super T>)` accept `List<Integer>` and `Collection<Number>`?

The source produces `Integer`, which matches `T`, while the destination can consume `T` via the lower-bounded wildcard; `Integer` is a subtype of `Number`.

**Question 4.** What does `static <S,R> List<R> map(..., Function<? super S, ? extends R>)` need to explain in Javadoc?

The roles of the source/result types, how the mapper is applied, iteration order, mutability/copying of the result, null policy, and exceptions.

**Question 5.** Why is `@param <T>` different from `@param value`?

One tag describes a **type parameter**, while the other describes a **formal value parameter**.

**Question 6.** If a method only needs a `Collection` to log each element, should `<T>` be used?

If `T` does not need to be linked to the result or other parameters, `Collection<?>` is usually shorter and more accurate.

**Question 7.** When an API returns `Optional<T>`, does the type itself state why it might be empty?

No. Javadoc must explain whether empty means no elements, not found, or filtered out by some rule.

**Question 8.** What does `<T extends Comparable<? super T>>` guarantee?

It guarantees comparability compatible with `T` at the type level, allowing `compareTo` to be called under the contract. It does not decide null policy or empty-list behavior on its own.

**Question 9.** If a method returns `new ArrayList<R>()`, is it right for Javadoc to say "unmodifiable list"?

No. `ArrayList` is mutable; the documentation must match the implementation, or the implementation must change.

**Question 10.** Can two overloads be distinguished solely by `<T>` and `<U>` when parameter types differ only in the type variable name?

No, if the erased signatures are equivalent. Renaming type variables does not create distinct overloads.

## 20. Checklist when reviewing a generic API

Before publishing or editing a public generic API, check:

1. **Type parameter names:** are `E/K/V/T/R/S/U` used consistently; are longer names needed to avoid role confusion?
2. **Declaration site:** is the type variable on the class or method? Is a name shadowed by a nested `<T>`?
3. **Same-type relationships:** is `T` preserved between parameters and results, or accidentally lost as `Object`?
4. **Source–destination:** do `extends`/`super` wildcards reflect the read/write direction?
5. **Bounds:** are `extends Number`, `Comparable<? super T>`, or a specific interface genuinely needed?
6. **Type inference:** are common call use cases natural and easy to diagnose on error?
7. **Javadoc type parameters:** are `@param <T>`, `@param <R>` present for every public type parameter needing documentation?
8. **Javadoc value parameters:** are parameters named `source`, `destination`, `mapper`, `comparator` described with their proper roles?
9. **Return/exception contracts:** does documentation clearly cover empty cases, nulls, mutability, ownership, partial failures, aliases, and side effects when relevant?
10. **Examples:** is there a call example showing real type relationships (e.g., `Integer` → `Number`, `Integer` → `String`)?
11. **Doc-to-code sync:** if `ArrayList` was replaced with `List.copyOf`, or the null policy or counter changed, was Javadoc updated?
12. **Safety from casts/raw types:** has `@SuppressWarnings("unchecked")` been avoided as a way to hide an invalid type relationship?

**Conclusion:** Naming type parameters in Java is part of **contract design**, not merely a matter of style. Choose `T` for a consistently related type, `E` for element, `K/V` for key/value, and `S/R` for source/result when helpful; use `? extends` and `? super` to clearly describe producers and consumers; declare bounds sufficient for the compiler to protect the operations actually needed. Then use Javadoc `@param <T>`, `@param`, `@return`, and `@throws` to document what the signature alone cannot say: nulls, empty data, mutation, ownership, side effects, partial failures, and the meaning of the result. A good generic API lets readers see **the type relationships right in the signature**, while the documentation clarifies **the actual runtime behavior**.