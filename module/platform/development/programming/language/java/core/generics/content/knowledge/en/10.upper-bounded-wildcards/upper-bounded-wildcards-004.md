# Why Can't You Add an Arbitrary Value `T` to `List<? extends T>`?

## 1. Goal and Scenario

Suppose we need to write a method that takes a list of numbers for calculation:

```java
static double sum(List<? extends Number> values) {
    double result = 0.0;
    for (Number value : values) {
        result += value.doubleValue();
    }
    return result;
}
```

The method above can accept `List<Integer>`, `List<Double>`, `List<BigDecimal>`, or `List<Number>`. Yet inside the method itself, the following operation does not compile:

```java
values.add(42); // COMPILE ERROR
```

Since `Integer` is a `Number`, the value `42` is an `Integer`, and the wildcard declares `extends Number`, why does Java still reject it?

**Core answer:** `List<? extends T>` holds elements of **an unknown concrete type that is a subtype of or equal to `T`**. To add an element, it must be proven that the new element is compatible with **that concrete type**, not merely compatible with the upper bound `T`. Java cannot prove this for an arbitrary value of type `T`.

This lesson explains the typing rule, proves the safety rationale, shows what reads/writes are actually permitted, covers the case of `null`, and explains how to design APIs when adding data is needed.

## 2. What Does `? extends T` Actually Mean?

A reference of type `List<? extends Number>` can accept `List<Integer>`, `List<Double>`, or `List<Number>`, but **does not expose the exact element type** at the usage site:

```java
List<Integer> ints = new ArrayList<>();
List<? extends Number> numbers = ints;
Number value = numbers.isEmpty() ? 0 : numbers.get(0);
```

`Number` is an upper bound allowing **reading**, not a license to **insert any `Number`**. In this lesson, we will prove specifically why the compiler must forbid writing so as not to break the contract of `List<Integer>` or `List<Double>`, even when the caller knows which runtime object it actually is.

## 3. Proof by Counterexample: Adding `T` Breaks Type Safety

Suppose the compiler allowed adding a `Number` through a `List<? extends Number>` variable:

```java
List<Integer> integers = new ArrayList<>();
List<? extends Number> view = integers;

// Hypothetical if Java allowed it, though in reality this line DOES NOT compile:
view.add(3.14);
```

`3.14` is boxed into `Double`, which is a subtype of `Number`. Still, it is **not an `Integer`**. If the addition were accepted, `integers` would end up holding a `Double` while other code continues to trust that the list contains only `Integer`:

```java
// Simulating the hypothetical consequence; not a valid Java program.
Integer first = integers.get(0); // Actual data is a Double!
```

The problem does not only arise when adding `Double`. Even `view.add(42)` must be prohibited, because the variable `view` could be pointing to a `List<Double>`. The compiler cannot guess based on a particular value that happens to look "reasonable" in one case.

Therefore, given:

```java
static void cannotAdd(List<? extends Number> values) {
    values.add(Integer.valueOf(42)); // COMPILE ERROR
    values.add(Double.valueOf(3.14)); // COMPILE ERROR
    values.add((Number) Integer.valueOf(1)); // STILL AN ERROR
}
```

All three lines are invalid. Casting the value to `Number` does not help, because `Number` is the upper bound, not the list's known concrete element type.

## 4. Why Can You Read as `T` Yet Not Write `T`?

Suppose a list has an actual element type `U` with `U extends T`.

**When reading:** every value of type `U` is a value of type `T`, so it can be read and used as `T`.

**When writing:** an arbitrary value of type `T` is not necessarily a `U`. It could be a different subtype of `T`, so it cannot be placed into a list that only accepts `U`.

```java
List<? extends Number> values = List.of(10, 20);

Number number = values.get(0); // VALID: element is guaranteed to be Number
Object object = values.get(0); // VALID: Number is also an Object
Integer integer = values.get(0); // INVALID: element could be Double
values.add(number);             // INVALID: Number is not guaranteed to match the element type
```

This is an intentional one-way flow of information: **the upper bound guarantees the ability to read**, not the ability to write new values.

An example with a custom hierarchy:

```java
class Animal {}
class Dog extends Animal {}
class Cat extends Animal {}

List<Dog> dogs = new ArrayList<>();
List<? extends Animal> animals = dogs;

Animal a = animals.get(0); // Type-valid; will fail with an index error if the list is empty
animals.add(new Dog());    // COMPILE ERROR
animals.add(new Cat());    // COMPILE ERROR
animals.add(new Animal()); // COMPILE ERROR
```

Even `new Dog()` is rejected through `animals`, because the static type of the variable is `List<? extends Animal>`, not `List<Dog>`. When you know the exact type of the list, write through a variable with the explicit type:

```java
dogs.add(new Dog()); // VALID
```

## 5. Wildcard Capture: What Is the Compiler Checking?

When the compiler uses `List<? extends Number>`, it may represent `?` with a temporary type, often referred to in error messages as **`CAP#1`** (*capture of ? extends Number*). You can picture it as:

```text
CAP#1 is the unknown element type
CAP#1 <: Number

get(int)  : CAP#1
add(CAP#1): boolean
```

This is a type-explanation diagram, not Java syntax. Because `CAP#1` is an unknown subtype of `Number`, the compiler has **no** rule allowing an arbitrary `Number` or `Integer` to be passed where `CAP#1` is required.

A compiler error message might mention:

```text
incompatible types: Integer cannot be converted to CAP#1
where CAP#1 is a fresh type-variable:
  CAP#1 extends Number from capture of ? extends Number
```

The exact formatting of the error depends on the JDK version and source expression; the meaning remains that the value being inserted has not been proven compatible with the captured element type.

Note carefully: the type parameter `T` in `List<? extends T>` is **not** the type `CAP#1`. `T` is the **upper bound**; `CAP#1` is the concrete yet unknown element type lying underneath that bound.

### 5.1. Writing a Generic Method With `T` Still Does Not Allow Adding `T`

```java
static <T> void tryAdd(List<? extends T> target, T value) {
    target.add(value); // COMPILE ERROR
}
```

You could pass `List<Integer>` along with a `Number` value as arguments so that `T` is inferred as `Number`, yet the list might only accept `Integer`. Giving a name `T` to the upper bound does not make the concrete type underneath `?` known.

Similarly:

```java
static <T extends Number> void tryAddNumber(
        List<? extends T> list, T value) {
    list.add(value); // STILL AN ERROR
}
```

Declaring `<T extends Number>` only restricts `T` itself within the `Number` family; it does not eliminate the wildcard from `List<? extends T>`.

### 5.2. Knowing the Actual Object Is Still Not Enough If the Variable Is Declared With a Wildcard

```java
List<? extends Number> view = new ArrayList<Number>();
view.add(1); // COMPILE ERROR
```

Even though `new ArrayList<Number>()` can accept `Integer`, the declared type of `view` is still `List<? extends Number>`. The compiler checks the call based on the **static type of the receiver expression** and capture rules.

If you want to write, keep a properly typed reference:

```java
List<Number> numbers = new ArrayList<>();
List<? extends Number> readable = numbers;

numbers.add(1);    // VALID
// readable.add(1); // INVALID
```

Both references point to the same list; the difference lies in the capabilities that each **declared type** permits the source code to use.

## 6. Is It Really Impossible to Add Anything at All?

**Important exception: `null`.** In Java, `null` is convertible to any reference type, including an unknown capture type:

```java
List<Integer> integers = new ArrayList<>();
List<? extends Number> view = integers;

view.add(null); // COMPILES
```

If the list object supports adding elements and allows `null`, the operation succeeds. However, this is not a way to add a useful `T` value:

- `null` does not carry a `Number` object or a concrete numeric value.
- `List.of(...)` and unmodifiable lists will throw `UnsupportedOperationException` when calling `add(null)`.
- Certain collection implementations or contracts may reject `null` with their own exceptions.

Therefore, the accurate phrasing is: **you cannot add an arbitrary non-`null` value of type `T` through `List<? extends T>`**; `add(null)` is valid at the type-system level, without necessarily succeeding at runtime.

`set(index, value)` has the same type restriction on the new argument:

```java
List<? extends Number> view = new ArrayList<Integer>(List.of(1, 2));

view.set(0, 5);    // COMPILE ERROR
view.set(0, null); // COMPILES when considering this line alone
```

`set(0, null)` only succeeds if the index exists and the actual list supports replacement and accepts `null`. An invalid index can throw `IndexOutOfBoundsException`.

## 7. `? extends T` Does Not Mean an Immutable List

Forbidding arbitrary writes of a new `T` does **not** mean the source object is immutable:

```java
List<Integer> ints = new ArrayList<>(List.of(1, 2, 3));
List<? extends Number> view = ints;
view.remove(1); // Compiles; removes element if the list supports it.
view.clear();   // Compiles; does not require a value of the capture type.
```

These operations can throw `UnsupportedOperationException` on lists that disallow modification. `Collections.swap` and generic capture helpers can also move elements that **already belong to the same list**. That is a different operation from inserting a new `Number`. A dedicated lesson on **wildcards do not make objects immutable** analyzes aliases, unmodifiable views, and snapshots.

## 8. Why Can a Generic Helper Add Back an Element It Just Read?

The following snippet may be surprising:

```java
static void cannotDuplicate(List<? extends Number> values) {
    values.add(values.get(0)); // COMPILE ERROR
}
```

Even though `get(0)` and `add(...)` are both called on `values`, Java may capture uses of the wildcard at different type positions. The compiler does not guarantee that the value read in this expression is treated as the exact parameter type required by `add`.

A helper method parameterized by `<E>` can hold **the same element type `E`** throughout the entire method body:

```java
static <E> void duplicateFirst(List<E> values) {
    if (!values.isEmpty()) {
        E first = values.get(0);
        values.add(first); // VALID: same E
    }
}

static void caller(List<? extends Number> source) {
    duplicateFirst(source); // VALID: captures wildcard as E at the call site
}
```

This is safe because the added value **comes from the list itself and keeps the exact type `E`**. `duplicateFirst` does not invent an arbitrary `Number`. If the source is `List<Integer>`, the helper receives an `E` corresponding to that element type; if it is `List<Double>`, it preserves `Double`.

The helper only satisfies type checking; if the list does not support `add`, the call will still throw `UnsupportedOperationException`.

Do not use raw `List` or unchecked casts to "trick" the compiler. Those approaches can allow wrong-typed elements to slip into the list and cause `ClassCastException` when reading later.

## 9. When You Actually Need to Write `T`, How Should You Design the API?

### 9.1. Use `List<T>` When the Exact Same Type Is Needed

If a method must guarantee that the new value has the exact element type:

```java
static <T> void append(List<T> target, T value) {
    target.add(value);
}
```

Example:

```java
List<Integer> integers = new ArrayList<>();
append(integers, 10); // Valid: T is Integer
```

The type `T` in `List<T>` is the same type parameter as that of `value`; the list has no unknown wildcard in the method signature. This method still depends on whether the list supports `add` at runtime.

### 9.2. Use `List<? super T>` When the List Is a Destination Receiving `T` Values

If a method is designed to write `T` elements to a destination, a **lower-bounded** wildcard is appropriate:

```java
static <T> void appendTo(List<? super T> target, T value) {
    target.add(value); // Type-valid
}
```

When `T` is `Integer`, the destination can be `List<Integer>`, `List<Number>`, or `List<Object>`: all of them accept an `Integer`. This is the opposite of `List<? extends T>`, which might point to a list of a narrower subtype into which `T` is not allowed to be inserted.

Example:

```java
List<Number> numbers = new ArrayList<>();
appendTo(numbers, Integer.valueOf(7));
appendTo(numbers, Double.valueOf(2.5));
```

### 9.3. Use `extends` for the Read Source and `super` for the Write Destination

A common signature when transferring elements:

```java
static <T> void transfer(
        List<? extends T> source,
        List<? super T> destination) {
    for (T value : source) {
        destination.add(value);
    }
}
```

For example, calling with `List<Integer>` and `List<Number>` is valid. `source` only needs to guarantee that every element read is a `T`; `destination` guarantees it can accept `T`.

This is the **PECS (Producer Extends, Consumer Super)** rule:

- **Producer `? extends T`**: supplies values readable as `T`.
- **Consumer `? super T`**: receives values of type `T` to write.

PECS guides API signature selection based on how data is used. It does not mean an `extends` list has immutable contents or a `super` list always supports modification.

## 10. Complete Java 17+ Program

Save a file `ExtendsWriteDemo.java` with the following contents:

```java
import java.util.ArrayList;
import java.util.List;

public class ExtendsWriteDemo {
    // Keep a single type E for both the read element and the added element.
    static <E> void duplicateFirst(List<E> list) {
        if (!list.isEmpty()) {
            E first = list.get(0);
            list.add(first);
        }
    }

    // Type T is guaranteed to be compatible with the destination list.
    static <T> void appendTo(List<? super T> target, T value) {
        target.add(value);
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>(List.of(10, 20));
        List<? extends Number> source = integers;

        Number read = source.get(0);
        System.out.println("Read: " + read);

        // source.add(30); // Compile error if uncommented.
        duplicateFirst(source);
        System.out.println("Same list: " + integers);

        List<Number> destination = new ArrayList<>();
        appendTo(destination, 3.5);
        System.out.println("Destination: " + destination);

        try {
            List<? extends Number> unmodifiable = List.of(1, 2);
            unmodifiable.add(null); // Type-valid, but List.of cannot be modified.
        } catch (UnsupportedOperationException e) {
            System.out.println(
                    "Unmodifiable: " + e.getClass().getSimpleName());
        }
    }
}
```

In the directory containing the file, compile and run:

```bash
javac -encoding UTF-8 ExtendsWriteDemo.java
java ExtendsWriteDemo
```

Output:

```text
Read: 10
Same list: [10, 20, 10]
Destination: [3.5]
Unmodifiable: UnsupportedOperationException
```

Analysis:

1. `source.get(0)` returns a value readable as `Number`.
2. `source.add(30)` is commented out because it cannot compile with `List<? extends Number>`.
3. `duplicateFirst(source)` is valid because the helper captures the single type `E` and takes the element from the list itself. It modifies the `integers` object, because `source` and `integers` reference the same object.
4. `appendTo` has destination `List<? super T>`, so it can add an actual value.
5. `List.of` rejects modification at runtime. This is independent of `add(null)` being type-valid.

## 11. Common Mistakes

| Statement or snippet | Verdict | Reason |
| --- | --- | --- |
| "`? extends Number` means any `Number` can be added" | False | The actual element type could be only `Integer` or `Double` |
| `list.add((Number) 1)` via `List<? extends Number>` | Does not compile | Casting to `Number` does not prove compatibility with the capture type |
| "The actual list is `ArrayList<Number>`, so the wildcard variable can add" | False | Compile-time checking relies on the static type `List<? extends Number>` |
| `list.add(null)` | Compiles | `null` is compatible with the unknown reference type; runtime may still reject |
| "An `extends` wildcard implies immutable" | False | Some removal/reordering operations can be valid and execute |
| `list.add(list.get(0))` with a wildcard variable | May not compile | The capture types at the two positions are not forced to be identical |
| Helper `<E>` accepting `List<E>` and adding back an element just read | Valid | The same `E` governs both reading and writing |
| Writing `T` into `List<? super T>` | Type-valid | The destination can accept any `T` value |
| Using raw `List` to add ill-typed values | Unsafe | Bypasses type checking and risks errors when reading |

### Tip for Reading Compile Errors

When you encounter an error mentioning `CAP#1` or "capture of `? extends ...`", ask yourself: "Am I passing an **external** value into a place expecting a specific unknown subtype?" If so, check whether your API needs `List<T>`, `List<? super T>`, or simply a helper to manipulate **existing elements**.

## 12. Self-Check Exercises

Examine each of the following snippets separately with `import java.util.*;`. Determine whether it compiles, and if so, whether it is guaranteed to succeed at runtime.

**A — Reading from a source**

```java
List<? extends Number> a = List.of(1, 2, 3);
Number value = a.get(0);
```

**B — Adding a subtype**

```java
List<? extends Number> b = new ArrayList<Integer>();
b.add(4);
```

**C — Adding the upper bound itself**

```java
List<? extends Number> c = new ArrayList<Number>();
c.add((Number) 4);
```

**D — Adding null**

```java
List<? extends Number> d = new ArrayList<Integer>();
d.add(null);
System.out.println(d.size());
```

**E — Writing through a lower bound**

```java
List<? super Integer> e = new ArrayList<Number>();
e.add(4);
```

**F — Using a capture helper**

```java
static <E> void copyFirst(List<E> values) {
    if (!values.isEmpty()) {
        values.add(values.get(0));
    }
}
List<? extends Number> f = new ArrayList<>(List.of(1, 2));
copyFirst(f);
```

Snippet F consists of two declarations placed inside a class or valid method declaration context; a `static` method cannot be declared freely among statements inside `main`.

**Answers:**

- **A:** Compiles; reading `Number` is safe.
- **B:** Does not compile; `Integer` is not proven to be `b`'s captured element type.
- **C:** Does not compile; even though the actual object is `ArrayList<Number>`, variable `c` has a wildcard type.
- **D:** Compiles and runs with `ArrayList`; prints `1`. One cannot infer that every other `List` implementation also permits `add(null)`.
- **E:** Compiles; `List<? super Integer>` accepts an `Integer` value. The `ArrayList<Number>` instance supports adding, so the operation succeeds.
- **F:** Compiles; the helper uses the same parameter `E` for `get` and `add`. The source `ArrayList` instance supports modification, so the operation succeeds.

## 13. Key Takeaways

`List<? extends T>` is a list of **an unknown subtype of `T`**. Reading out a `T` is safe because every element is a `T`; adding an arbitrary `T` is unsafe because that value may not belong to the actual element type. `null` is a type-valid exception, though runtime may still reject the operation.

When designing APIs: use `? extends T` for read sources, `? super T` for write destinations, and `List<T>` or a generic helper when you need to link the exact element type being read with the element type being written.