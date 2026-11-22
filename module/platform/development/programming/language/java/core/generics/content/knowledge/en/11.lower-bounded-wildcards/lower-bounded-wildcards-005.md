# Distinguishing lower-bounded wildcards from type parameter bounds in Java Generics

## 1. The problem: two non-equivalent ways of saying “type bound”

When reading Java generics signatures, we often encounter two constructs:

```java
List<? super Integer> destination;
<T extends Number> void process(T value) { /* ... */ }
```

Both use the word “bound”, yet they apply to **two different grammatical entities**:

- `? super Integer` is a **lower-bounded wildcard** at a **type argument position**; it expresses an unknown element type that is `Integer` or a **supertype of `Integer`**.
- `<T extends Number>` is an **upper-bounded type parameter** declaration; it names a type `T` that the compiler must know is `Number` or a **subtype of `Number`** within the declaration's scope.

Crucial point: Java **does not support declaring a lower-bounded type parameter** such as `<T super Integer>`. The `super` keyword appears validly in the lower bound of a **wildcard**, whereas type parameters declared with `<T extends ...>` use an upper bound.

This lesson focuses on distinguishing their meanings, syntax, type inference behavior, and effects when reading/writing data; it does not equate a type parameter `T` with a wildcard `?`.

## 2. Formal distinction: type parameter vs. wildcard

### 2.1. A type parameter is a reusable type name

In the following method, `T` is a declared **type parameter** and can appear in multiple positions:

```java
static <T extends Number> T identity(T value) {
    return value;
}
```

- `<T extends Number>` **declares** `T`, while constraining `T` to be a type compatible with `Number`.
- `T value` and the return type `T` both refer to **a single named type parameter**.
- Inside the method body, operations guaranteed by the upper bound can be called, such as `value.doubleValue()`.
- At each call site, the compiler infers or checks an appropriate type argument (for example `Integer`, `Double`).

`extends` in a type parameter bound covers both **class inheritance** and **interface implementation**:

```java
static <T extends CharSequence> int sizeOf(T text) {
    return text.length();
}
```

`CharSequence` is an interface, yet the keyword is still `extends`, not `implements`.

A bound can also be an *intersection* of multiple requirements:

```java
static <T extends Number & Comparable<T>> int compare(T a, T b) {
    return a.compareTo(b);
}
```

If there is a class in the bound list, the class must appear before the interfaces. This is still an **upper bound** on `T`.

### 2.2. A wildcard represents an unknown type at the use site

Unlike declaring `T`, a wildcard does not introduce a type name for independent reuse:

```java
List<? super Integer> receiver = new ArrayList<Number>();
```

Here, `?` is the **type argument** of `List<...>`. The actual list may be declared with `Integer` or a compatible supertype of `Integer`; code using `receiver` **does not know** the exact type parameter of the list.

`? super Integer` differs from `? extends Integer`:

- `? super Integer`: the unknown element type is **`Integer` or a supertype of `Integer`**; safe for **writing `Integer`**.
- `? extends Integer`: the unknown element type is **`Integer` or a subtype of `Integer`**; safe for **reading as `Integer`**. `Integer` is `final`, so examples with it show less subtype variety, yet the rule still applies.

When calling a method on `List<? super Integer>`, the compiler can create an internal capture type for the wildcard. That capture has `Integer` as its lower bound and is guaranteed to have `Object` as its upper bound. You cannot turn the wildcard `?` into a type name `T` and reuse it arbitrarily in other declarations.

### 2.3. Comparison table

| Property | `List<? super Integer>` | `<T extends Number>` |
| --- | --- | --- |
| Constrained entity | Wildcard serving as **type argument** of `List` | **Declared type parameter** named `T` |
| Bound direction | **Lower**: unknown element type is a supertype of or equal to `Integer` | **Upper**: `T` is a subtype of or equal to `Number` |
| Where it appears | Inside a parameterized type, e.g. `List<? super Integer>` | In a generic class, interface, method, or constructor declaration |
| Has a name to link multiple positions? | No direct name; a helper can be used to capture | Yes: the same `T` can repeat in parameters, variables, and return type |
| Values that can be put into a list | Through a `List<? super Integer>` variable, `Integer` (and corresponding subtypes) can be added | The bound `T extends Number` alone **does not state** there is any list to add to |
| Values retrieved | With `List<? super Integer>`, only `Object` is guaranteed | With a `T` value, it can at least be used as `Number` |
| Opposite syntax | `? extends Integer` is an upper-bounded wildcard | `<T super Integer>` is **invalid** in Java |

The label “supertype” here includes any valid **supertype** in Java's type system, including interfaces. For example, `List<Number>`, `List<Object>`, and `List` types parameterized with an appropriate supertype of `Integer` can all be used in a `List<? super Integer>` position. Do not assume there are only the exact three choices `Integer`, `Number`, `Object`.

## 3. How does `? super T` create a lower bound?

Consider:

```java
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

List<? super Integer> targetA = numbers; // Valid
List<? super Integer> targetB = objects; // Valid
```

In the case of `targetA`, the actual list accepts `Number`. In `targetB`, the actual list accepts `Object`. Both kinds **accept an `Integer`**, because every `Integer` is simultaneously a `Number` and an `Object`.

Type-valid operations:

```java
targetA.add(Integer.valueOf(10));
targetB.add(20); // int is boxed to Integer
targetA.set(0, Integer.valueOf(30)); // Requires a valid index and a List supporting set
```

Conversely:

```java
targetA.add(3.14);                 // COMPILE-TIME ERROR: Double is not guaranteed compatible
targetB.add(new Object());        // COMPILE-TIME ERROR: Object is not guaranteed to be Integer
Integer n = targetA.get(0);       // COMPILE-TIME ERROR: only Object is guaranteed
Object value = targetA.get(0);    // Valid if the list is non-empty
```

**Why is reading only safe as `Object`?** Because the actual element type may be `Object`, and a `List<Object>` can also contain `String`, `Double`, or any other object alongside the added `Integer` values. The lower bound guarantees the condition for **putting `Integer` in**, not that every element read out is an `Integer`.

Note on `set`: besides type safety, the index must exist and the `List` instance must support replacement. `? super Integer` does not turn an unmodifiable list into a modifiable one.

## 4. `<T extends Number>` constrains a named type

Consider a method operating only on a single `T`:

```java
static <T extends Number> double twice(T value) {
    return value.doubleValue() * 2;
}
```

`T` is bounded by `Number`, so `doubleValue()` can be called. The method accepts `Integer`, `Long`, `Double`, and other compatible types. However, it does **not** create a special relationship between `List<Integer>` and `List<Number>`:

```java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = integers; // COMPILE-TIME ERROR: generics are still invariant
```

More importantly: even with `T extends Number`, adding an element still requires the exact `T`:

```java
static <T extends Number> void put(List<T> list, T value) {
    list.add(value); // Valid: the list's type parameter and value are both T
}
```

You cannot simply know `T extends Number` and arbitrarily add a `Double`:

```java
static <T extends Number> void wrong(List<T> list) {
    list.add(3.14); // COMPILE-TIME ERROR: T could be Integer
}
```

The same name `T` maintains a consistent relationship across multiple positions. The `put` method can accept `List<Integer>` with `Integer`, or `List<Double>` with `Double`. An upper bound does not mean every `Number` value can be inserted into an arbitrary `List<T>`.

## 5. Why is there no `<T super Integer>` syntax?

The following declarations are **invalid Java syntax**:

```java
// DOES NOT compile:
class InvalidBox<T super Integer> { }
static <T super Number> void invalid(T value) { }
```

Java only has upper-bound syntax in **type parameter declarations**, for example:

```java
class NumberBox<T extends Number> {
    private final T value;

    NumberBox(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

If an API needs to accept a list whose type parameter is `Integer` or a supertype of `Integer`, write the lower bound **at the type use site**:

```java
static void appendInteger(List<? super Integer> target) {
    target.add(42);
}
```

Or both name a type `T` and use a lower-bounded wildcard:

```java
static <T> void append(List<? super T> target, T value) {
    target.add(value);
}
```

These are two different layers of constraints: `T` is tied to the type of `value`; `? super T` guarantees that the **destination** accepts values of type `T`.

**Distinction from type inference:** during *type inference*, the compiler may use “lower” or “upper” type constraint relationships to solve inference equations. That does not create a new declaration syntax `<T super X>` in Java source code.

## 6. Using both an upper bound on T and a lower-bounded wildcard in the same API

This is a very common scenario:

```java
static <T extends Number> void copyNumbers(
        List<? super T> destination,
        List<? extends T> source) {
    for (T number : source) {
        destination.add(number);
    }
}
```

Part-by-part breakdown:

1. `<T extends Number>`: `T` is a valid numeric type; operations provided by `Number` can be used.
2. `List<? extends T> source`: **read source** whose element type is `T` or a subtype of `T`; each read element can be handled as `T`.
3. `List<? super T> destination`: **write destination** whose element type is `T` or a supertype of `T`; each `T` value can be safely added.
4. `for (T number : source)`: elements from the source are safe to read as `T`, and can then be passed to `destination.add(number)`.

Example:

```java
List<Integer> integers = List.of(1, 2);
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

copyNumbers(numbers, integers); // Valid
copyNumbers(objects, integers); // Valid
```

An invalid call:

```java
List<Double> doubles = new ArrayList<>();
copyNumbers(doubles, integers); // COMPILE-TIME ERROR
```

`List<Double>` is not a suitable destination to receive `Integer` elements from this source. The compiler cannot find a `T` that simultaneously satisfies the type relationships required by both parameters.

You can write `<T>` without the `extends Number` bound if the method only needs to copy arbitrary objects:

```java
static <T> void copyAll(
        List<? super T> destination,
        List<? extends T> source) {
    for (T element : source) {
        destination.add(element);
    }
}
```

Here, the `Number` upper bound is unnecessary. Only declare the constraints that the method body or API contract genuinely requires.

### PECS as a mnemonic for usage direction

**PECS: Producer Extends, Consumer Super.**

- `? extends T` fits a source supplying elements to be **read as T**.
- `? super T` fits a destination consuming elements to **write T**.

PECS is a generic signature design guideline, not a rule claiming every `extends` source is unmodifiable or every `super` destination is guaranteed mutable at runtime.

## 7. Type scope diagrams

Assume:

```text
Object
  ↑
Number
  ↑
Integer
```

Arrows point from subtype to supertype.

For a variable of type `List<? super Integer>`:

```text
Actual lists that can be accepted:
    List<Integer>
    List<Number>
    List<Object>
    ... or List<other compatible supertype of Integer>

Values safe to add: Integer (or values of a subtype of Integer)
Guaranteed type when reading: Object
```

For example, `Integer` is a `final` class so it has no actual subclasses; the phrasing “or subtype” is the general rule when `T` is not `final`.

For the declaration `<T extends Number>`:

```text
Chosen type T:
    Number
    Integer
    Double
    Long
    ... other compatible subtypes of Number

A T value can be used as Number.
A List<T> only accepts values proven compatible with T.
```

The two sets of relationships go in **opposite directions** relative to the bound. One describes the hidden element type of a **data-receiving position**; the other describes the concrete types permitted for a **named type parameter**.

## 8. Standalone Java 17+ example that compiles and runs

Create the file `LowerBoundDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class LowerBoundDemo {
    // T is upper-bounded by Number.
    // The destination wildcard is lower-bounded by T.
    static <T extends Number> void copyNumbers(
            List<? super T> destination,
            List<? extends T> source) {
        for (T number : source) {
            destination.add(number);
        }
    }

    public static void main(String[] args) {
        List<Integer> ids = List.of(4, 8);
        List<Number> numbers = new ArrayList<>();
        List<Object> objects = new ArrayList<>();

        copyNumbers(numbers, ids);
        copyNumbers(objects, ids);
        System.out.println("Numbers: " + numbers);
        System.out.println("Objects: " + objects);

        List<? super Integer> sink = numbers;
        sink.add(12);
        System.out.println("After add: " + numbers);

        Object first = sink.get(0);
        System.out.println("Read as Object: " + first);

        List<? super Number> broadSink = objects;
        broadSink.add(3.5);
        System.out.println("Objects after double: " + objects);
    }
}
```

Compile and run in the directory containing the file:

```bash
javac -encoding UTF-8 LowerBoundDemo.java
java LowerBoundDemo
```

Exact output:

```text
Numbers: [4, 8]
Objects: [4, 8]
After add: [4, 8, 12]
Read as Object: 4
Objects after double: [4, 8, 3.5]
```

Explanation:

- `copyNumbers(numbers, ids)` and `copyNumbers(objects, ids)` are both valid: the destination list has a type parameter broad enough to accept the source elements.
- `List<? super Integer> sink = numbers` allows adding `12` because `12` is boxed to `Integer`.
- `sink.get(0)` only has `Object` as its guaranteed type; the actual list happens to hold `4`, yet the compiler does not infer element types backwards from runtime contents.
- `List<? super Number> broadSink = objects` allows adding `Double` because `Double` is a `Number` and the destination can hold `Number`.

The program contains no unchecked casts or raw types.

## 9. Examples of common mistakes

### 9.1. Using `? super T` as an upper bound of T

```java
// Invalid: a wildcard cannot stand directly in the bound position of T.
static <T extends ? super Number> void broken(T x) {}
```

A type parameter is declared with **a valid upper-bound type**, not with a wildcard like this. If you need “a destination accepting numbers”, put `? super Number` in the list's type argument position:

```java
static void addNumber(List<? super Number> list, Number value) {
    list.add(value);
}
```

### 9.2. Mistaking `List<? super Integer>` for `List<Integer>`

```java
List<? super Integer> values = new ArrayList<Object>();
values.add(1);          // Valid
Integer n = values.get(0); // COMPILE-TIME ERROR
```

The actual list may be `List<Object>` containing many objects that are not `Integer`. You cannot extract `Integer` solely from the lower bound.

### 9.3. Mistaking an upper bound on T for permission to write Number

```java
static <T extends Number> void wrong(List<T> values) {
    values.add(3.5); // COMPILE-TIME ERROR: T could be Integer
}
```

When needing to add a specific `Double`, accept `List<? super Double>` or `List<Double>`. When needing to preserve the same type `T`, accept an additional parameter of type `T value`.

### 9.4. Thinking `super` makes generics “covariant”

```java
List<Integer> ids = new ArrayList<>();
List<Number> numbers = ids; // COMPILE-TIME ERROR
List<? super Integer> target = ids; // Valid
```

`List<Integer>` and `List<Number>` remain **invariant** in their type parameters. A wildcard only creates a **flexible reference-receiving type** with appropriate read/write guarantees.

### 9.5. Renaming T without linking the positions

```java
static <A, B> void unsafe(
        List<? super A> destination, B value) {
    // destination.add(value); // Cannot compile: A and B have no relationship.
}
```

Different type parameter names do not automatically establish a relationship. If the goal is to add `value`, use the same `T`:

```java
static <T> void safe(List<? super T> destination, T value) {
    destination.add(value);
}
```

### 9.6. Equating type safety with mutability

```java
List<? super Integer> target = List.of(1, 2);
target.add(3); // Compiles, but throws UnsupportedOperationException
```

The lower-bounded wildcard proves the element type is **compatible for insertion**. It does not guarantee that the list object allows modification.

## 10. Self-check

Assume `import java.util.*;`. For each standalone snippet, state **whether it compiles**, and if so, what type is guaranteed when reading.

**A — `super` wildcard accepting a broad destination**

```java
List<? super Integer> a = new ArrayList<Number>();
a.add(10);
Object x = a.get(0);
```

**B — Reading as Integer**

```java
List<? super Integer> b = new ArrayList<Object>();
Integer x = b.get(0);
```

**C — Lower-bounded type parameter**

```java
class Box<T super Integer> {}
```

**D — Upper-bounded type parameter**

```java
static <T extends Number> double toDouble(T x) {
    return x.doubleValue();
}
```

**E — Writing Number into List<? super Integer>**

```java
List<? super Integer> e = new ArrayList<Number>();
Number n = 3.5;
e.add(n);
```

**F — Writing Integer into List<? super Number>**

```java
List<? super Number> f = new ArrayList<Object>();
f.add(3);
```

**G — Combining a type parameter and a wildcard**

```java
static <T extends Number> void store(
        List<? super T> target, T value) {
    target.add(value);
}
List<Object> objects = new ArrayList<>();
store(objects, Integer.valueOf(9));
```

In examples D and G, the `static` methods must be declared inside an appropriate class or context; these are illustrative code fragments, not standalone runnable Java files.

**Answers:**

- **A:** Valid; adds `Integer` into a list accepting `Integer`, and reading is safe as `Object`.
- **B:** Does not compile: `get` returns a type only guaranteed to be `Object`.
- **C:** Does not compile: Java has no `<T super ...>` syntax.
- **D:** Valid when placed in an appropriate class declaration; `T` is upper-bounded by `Number`, allowing `doubleValue()` to be called.
- **E:** Does not compile: an arbitrary `Number` could be `Double`, whereas `List<? super Integer>` might point to `List<Integer>`.
- **F:** Valid: `Integer` is a `Number` and every `List<? super Number>` accepts `Number`.
- **G:** Valid: `T` can be inferred as `Integer` (or a compatible type), and `List<Object>` is a destination capable of holding that value.

## 11. Key takeaways

**`? super T` is a wildcard lower bound at a type argument position**: it represents an unknown element type broad enough to accept `T` values; reading only guarantees `Object`. **`<T extends U>` is an upper bound on a named type parameter**: it constrains `T` to the `U` family and allows linking multiple positions within the same declaration.

Java does not support `<T super U>` in type parameter declarations. When both mechanisms are needed, use a combined signature such as `<T extends Number> void copy(List<? super T> dest, List<? extends T> src)` to accurately describe the values read from the source and accepted by the destination.