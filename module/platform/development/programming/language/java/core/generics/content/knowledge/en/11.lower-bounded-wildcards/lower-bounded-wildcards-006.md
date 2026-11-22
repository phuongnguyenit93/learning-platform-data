# Relationship between `? super Integer` and `? super Number` in Java Generics

The two types `List<? super Integer>` and `List<? super Number>` look very similar, but they are **not equivalent**. Because `Integer` is a subtype of `Number`, the compatibility relationship between these two lower-bounded wildcards goes in this direction:

```text
Integer <: Number

List<? super Number>  <:  List<? super Integer>
          |                         |
          +----- assignable to ---->+
```

You can assign a value of type `List<? super Number>` to a variable of type `List<? super Integer>`. **The reverse direction is invalid.** This is a consequence of the *type argument containment* rule for lower-bounded wildcards (`super`), often intuitively described as *contravariant* behavior at the wildcard position.

This statement must be understood accurately: ordinary `List<T>` remains **invariant**. There is no rule making `List<Number>` a subtype of `List<Integer>`. The flexibility here arises because both sides use lower-bounded wildcards, not because Java turns all generics contravariant.

This lesson clarifies three things: which type arguments can stand behind each `? super`, in which direction the two wildcard types convert, and why their add/read permissions differ.

## 1. What does `? super T` mean?

In Java, the declaration:

```java
List<? super Integer> integerSink;
```

states that the variable references a `List<X>` with an unknown type argument `X`, where `X` is **`Integer` or a supertype of `Integer`**. Examples of compatible type arguments include `Integer`, `Number`, `Object`, and superinterfaces implemented by `Integer`, such as `Comparable<Integer>` or `java.io.Serializable`.

Conversely:

```java
List<? super Number> numberSink;
```

requires `X` to be **`Number` or a supertype of `Number`**, such as `Number`, `Object`, or `java.io.Serializable`.

Important point: “supertype” in Java's subtype relationship does not mean only classes inherited via `extends`, but also interfaces implemented via `implements`. A `List<Serializable>` also accepts `Number` because `Number implements Serializable`.

Illustrative example (variables placed inside a method body, with imports from `java.util` and `java.io.Serializable`):

```java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();
List<Serializable> serializables = new ArrayList<>();
List<Comparable<Integer>> comparables = new ArrayList<>();

List<? super Integer> a = integers;
List<? super Integer> b = numbers;
List<? super Integer> c = objects;
List<? super Integer> d = serializables;
List<? super Integer> e = comparables;

List<? super Number> f = numbers;
List<? super Number> g = objects;
List<? super Number> h = serializables;

// List<? super Number> invalid = integers;   // Does not compile.
// List<? super Number> invalid2 = comparables; // Does not compile.
```

`List<Integer>` is not compatible with `List<? super Number>`: `Integer` is a **subtype**, not a supertype of `Number`. `Comparable<Integer>` is also not a supertype of `Number`, even though it is an interface that `Integer` implements.

In real-world APIs, this kind of parameter is typically used as a **data sink** (consumer): `? super T` allows passing `T` values into a collection with a broader declared element type.

## 2. The set of valid type arguments explains the direction of the relationship

Each lower-bounded wildcard can be viewed as a condition placed on the actual type argument:

- For `? super Integer`: the argument must be `Integer` **or a supertype of `Integer`**.
- For `? super Number`: the argument must be `Number` **or a supertype of `Number`**.

Because every supertype of `Number` is also a supertype of `Integer` (since `Integer extends Number`), the set of type arguments satisfying `? super Number` **lies inside** the set satisfying `? super Integer`.

```text
Example type arguments accepted by ? super Integer:
    Integer, Number, Object, Serializable, Comparable<Integer>, ...

Example type arguments accepted by ? super Number:
             Number, Object, Serializable, ...

The set (? super Number) is a subset of (? super Integer)
```

This is an intuitive way to understand why a `List<? super Number>` can be viewed through a `List<? super Integer>` reference: if a collection is guaranteed to accept `Number`, then of course it also accepts any `Integer`.

However, the set diagram above only illustrates the condition on type arguments, not a formal definition that a wildcard is a runtime collection or that two lists are “converted” into each other. Compatibility checking happens at **compile time**, based on type-argument *containment* rules and Java's assignment rules.

## 3. Assigning a `List<? super Number>` to a `List<? super Integer>`

Minimal example:

```java
List<? super Number> numberSink = new ArrayList<Number>();
List<? super Integer> integerSink = numberSink; // Valid.
```

Contract-based explanation:

1. `numberSink` accepts any `Number` object, including `Integer`, `Double`, and `Long`.
2. `integerSink` only requires a place capable of accepting `Integer` objects.
3. A list that accepts `Number` satisfies the requirement of accepting `Integer`, so the assignment is safe.

Yet after the assignment, **allowed operations are determined by the static type of each variable**:

```java
numberSink.add(1);
numberSink.add(2.5); // Valid: Double is a Number.

integerSink.add(3);  // Valid: Integer.
// integerSink.add(4.5); // Does not compile: static type is ? super Integer.
```

Even though both variables point to the same list object, the compiler does not “remember” that `integerSink` was initialized from `numberSink`. Once a reference is declared as `List<? super Integer>`, it only exposes the narrower contract: **adding `Integer`**.

### Complete example

Save as `SuperAssignmentDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class SuperAssignmentDemo {
    public static void main(String[] args) {
        List<? super Number> numberSink = new ArrayList<Number>();
        numberSink.add(2.5);

        List<? super Integer> integerSink = numberSink;
        integerSink.add(10);
        integerSink.add(20);

        // integerSink.add(3.5); // Does not compile.

        System.out.println(numberSink);
        System.out.println(integerSink);

        Object item = integerSink.get(0);
        System.out.println(item);
    }
}
```

Compile and run with Java 17 or later:

```bash
javac SuperAssignmentDemo.java
java SuperAssignmentDemo
```

Output:

```text
[2.5, 10, 20]
[2.5, 10, 20]
2.5
```

Both variables print the same contents because they point to the same `ArrayList`. The value read from `integerSink.get(0)` only guarantees a static type usable as `Object`, so even though the first element is a `Double`, the call is completely safe.

## 4. Why isn't the reverse assignment allowed?

The assignment below is rejected:

```java
List<? super Integer> integerSink = new ArrayList<Integer>();
// List<? super Number> numberSink = integerSink; // COMPILE-TIME ERROR.
```

Imagine if the assignment were allowed:

```java
List<Integer> realList = new ArrayList<>();
List<? super Integer> integerSink = realList;

// FALSE ASSUMPTION — Java rejects the line below:
// List<? super Number> numberSink = integerSink;

// If the line above were allowed:
 // numberSink.add(3.14); // Double is a Number.
 // realList would contain a Double even though it must be a List<Integer>.
```

`List<? super Integer>` can point to `List<Integer>`. A `List<Integer>` **cannot** accept a `Double`. Yet `List<? super Number>` has a contract allowing `Double` to be added. Assigning in the reverse direction would let the compiler permit an operation capable of breaking the real list's type safety.

This is why the relationship is one-way only:

```text
List<? super Number>  --->  List<? super Integer>   VALID
List<? super Integer> --->  List<? super Number>    INVALID
```

You cannot mechanically infer the assignment direction from the type name right after `super`. You must ask: **which objects does the target reference type promise can be added, and does the source guarantee that capability in every case?**

## 5. Table of element addition and reading permissions

| Variable type | Some actual list types it can reference | Non-null values addable via the variable | Safe type when reading via `get` |
| --- | --- | --- | --- |
| `List<? super Integer>` | `List<Integer>`, `List<Number>`, `List<Object>`, `List<Serializable>`, ... | `Integer` | `Object` |
| `List<? super Number>` | `List<Number>`, `List<Object>`, `List<Serializable>`, ... | `Number` and subtypes (`Integer`, `Double`, ...) | `Object` |
| `List<Integer>` | `List<Integer>` | `Integer` | `Integer` |
| `List<Number>` | `List<Number>` | `Number` and subtypes | `Number` |
| `List<?>` | Any matching `List<T>` | Cannot arbitrarily add a non-null value | `Object` |

Both `? super` wildcards permit passing the **`null` literal** at the type-system level; whether the actual collection supports `add` and accepts `null` is a separate issue.

### 5.1. Write permission (`add`)

With `List<? super Number>`, the compiler can guarantee that every valid list accepts `Number` and its subtypes:

```java
static void addNumbers(List<? super Number> target) {
    target.add(1);    // Integer is a Number.
    target.add(2.5);  // Double is a Number.
    target.add(3L);   // Long is a Number.
}
```

With `List<? super Integer>`, the compiler only guarantees accepting `Integer`. `Integer` is a `final` class, so there are no subclasses to add to this option:

```java
static void addIntegers(List<? super Integer> target) {
    target.add(1);
    target.add(2);

    // target.add(2.5); // Does not compile.
}
```

Both snippets are illustrative methods and need to be placed inside a class with `import java.util.List;` if compiled separately.

Note: “compiles” is different from “guaranteed to succeed at runtime”. An unmodifiable `List.of(...)` can still match type-wise to be passed into the methods above, yet `add` will throw `UnsupportedOperationException`. Generic rules determine type compatibility, not the *mutability* of the collection.

### 5.2. Read permission (`get`)

`? super Number` does not mean `Number` can be read. A `List<? super Number>` can point to `List<Object>`, or `List<Serializable>` containing non-`Number` objects. Therefore:

```java
List<? super Number> numbers = new ArrayList<Object>();
Object first = numbers.isEmpty() ? null : numbers.get(0); // Valid.

// Number n = numbers.get(0); // Does not compile.
```

Similarly:

```java
List<? super Integer> integers = new ArrayList<Number>();
Object first = integers.isEmpty() ? null : integers.get(0);

// Integer i = integers.get(0); // Does not compile.
```

The lower bound provides a guarantee about **objects that can be put in**, not a guarantee stricter than `Object` for **objects taken out**. When you need to read numbers and call `doubleValue()`, use `List<? extends Number>` (producer) or `List<Number>` if appropriate, instead of relying on `? super Number`.

## 6. Complete example: using two consumer methods

Save as `LowerBoundConsumerDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class LowerBoundConsumerDemo {
    static void putIntegers(List<? super Integer> destination) {
        destination.add(10);
        destination.add(20);
    }

    static void putNumbers(List<? super Number> destination) {
        destination.add(30);
        destination.add(4.5);
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>();
        List<Number> numbers = new ArrayList<>();
        List<Object> objects = new ArrayList<>();

        putIntegers(integers);
        putIntegers(numbers);
        putIntegers(objects);

        putNumbers(numbers);
        putNumbers(objects);

        // putNumbers(integers); // COMPILE-TIME ERROR.

        System.out.println("integers=" + integers);
        System.out.println("numbers=" + numbers);
        System.out.println("objects=" + objects);
    }
}
```

```bash
javac LowerBoundConsumerDemo.java
java LowerBoundConsumerDemo
```

Output:

```text
integers=[10, 20]
numbers=[10, 20, 30, 4.5]
objects=[10, 20, 30, 4.5]
```

Because `putIntegers` only adds `Integer`, any `List<Integer>`, `List<Number>`, or `List<Object>` is capable of receiving them. `putNumbers` can also add `Double`, so `List<Integer>` does not satisfy the contract.

The same `List<Number>` object can be passed to both methods, because it is broad enough to accept any `Number`. That does not make `List<Integer>` and `List<Number>` subtypes of each other.

## 7. Assignment along the `super` direction is a type relationship, not data conversion

Consider:

```java
List<Number> source = new ArrayList<>();
List<? super Number> numberSink = source;
List<? super Integer> integerSink = numberSink;
```

All three variables point to **one single object**; no elements are converted to another type, no new list is created, and the collection is not iterated.

`numberSink` allows adding `Number`; `integerSink` only allows adding `Integer`. If data is added via `numberSink`, it can be observed through `integerSink` using `get`, but only as `Object`.

This is the nature of a **static type view**: the same runtime object can be referenced through generic declarations with different contracts. The compiler enforces each variable's contract at the point of use.

A short example:

```java
numberSink.add(1.5);
integerSink.add(2);
System.out.println(source); // [1.5, 2]
```

If declaring `integerSink` were allowed to “remember” that it is always `List<Number>` because it had been assigned from `numberSink`, the rule would depend on variable assignment history and become unsafe for other values coming from method parameters. Java checks according to the static type of the expression at the use site.

## 8. `? super Number` and `? super Integer` are not `List<Number>` or `List<Integer>`

Distinguish two groups:

**Exact parameterized types:**

```java
List<Number> exactNumbers = new ArrayList<>();
List<Integer> exactIntegers = new ArrayList<>();

// List<Number> invalid = exactIntegers; // Does not compile.
```

**Wildcard parameterized types:**

```java
List<? super Integer> anyIntegerDestination = exactIntegers;
List<? super Integer> anotherIntegerDestination = exactNumbers;

List<? super Number> anyNumberDestination = exactNumbers;
```

You also cannot assign a wildcard back to a concrete type argument:

```java
List<? super Number> wildcard = new ArrayList<Number>();

// List<Number> exact = wildcard; // Does not compile.
```

Reason: the `wildcard` variable could also hold a `List<Object>` or `List<Serializable>`, so the compiler cannot guarantee the real object has exact type `List<Number>`. Initializing it right in the example with `new ArrayList<Number>()` does not change the contract of the `wildcard` variable.

Similarly, `List<? super Integer>` is not `List<Integer>` and does not automatically become `List<Number>`.

## 9. Direct connection to the PECS principle

PECS stands for **Producer Extends, Consumer Super**:

- **Producer:** a parameter supplying objects to the program (mainly reading) → use `? extends T` when appropriate.
- **Consumer:** a parameter receiving objects put in by the program (mainly writing) → use `? super T` when appropriate.

Identify the specific kind of values the method needs to **write** before choosing the lower bound:

| Method requirement | Suitable parameter type | Reason |
| --- | --- | --- |
| Add `Integer` values | `List<? super Integer>` | Accepts `List<Integer>`, `List<Number>`, `List<Object>`, and other supertypes |
| Add multiple kinds of `Number` | `List<? super Number>` | Allows writing `Integer`, `Double`, `Long`, ... |
| Only read `Number` objects | `List<? extends Number>` | Values read are guaranteed usable as `Number` |
| Both read and write one exact type `T` | `List<T>` or generic method | Preserves the relationship between read element type and written element type |

For example, if a method actually only adds `Integer` yet declares parameter `List<? super Number>`, it inadvertently excludes `List<Integer>` from the set of valid callers. Switching to `List<? super Integer>` makes the API **broader in the list types it can accept**, while still keeping `add(Integer)` calls safe.

Conversely, if the method body needs to add `Double` and `Integer`, changing it from `List<? super Number>` to `List<? super Integer>` will cause the code inside to stop compiling. Choose the lower bound based on the **types of values to write**, not arbitrarily based on inheritance relationships between named types.

## 10. Can a method accept `? super Integer` and forward it to `? super Number`?

Suppose there are two APIs:

```java
static void acceptIntegers(List<? super Integer> target) {
    target.add(100);
}

static void acceptNumbers(List<? super Number> target) {
    target.add(1.25);
}
```

We can write:

```java
static void forwardNumbers(List<? super Number> target) {
    acceptIntegers(target); // Valid.
    acceptNumbers(target);  // Valid.
}
```

But the reverse direction is invalid:

```java
static void forwardIntegers(List<? super Integer> target) {
    acceptIntegers(target); // Valid.
    // acceptNumbers(target); // Does not compile.
}
```

Why? `forwardIntegers` might directly receive a `List<Integer>`. If it called `acceptNumbers`, that method could add a `Double` into a list that actually holds only `Integer`. The compiler forbids this dangerous forwarding.

This situation occurs frequently when wiring service or helper methods: an API using a lower bound **broader in the kinds of values it writes** requires a destination capable of accepting more types, and thus can only accept a **narrower** set of caller arguments.

## 11. Generic methods and `Collections.copy`: applying two data directions

A practical example of combining producer/consumer is copying elements from source to destination. A Java method can be written:

```java
static <T> void appendAll(
        List<? extends T> source,
        List<? super T> destination) {
    for (T item : source) {
        destination.add(item);
    }
}
```

If `source` is `List<Integer>`, `destination` can be `List<Integer>`, `List<Number>`, or `List<Object>`. If `source` is `List<Number>` containing `Double` as well, `destination` must be capable of accepting `Number` values.

Save as `AppendAllDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class AppendAllDemo {
    static <T> void appendAll(
            List<? extends T> source,
            List<? super T> destination) {
        for (T value : source) {
            destination.add(value);
        }
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(1, 2);
        List<Number> numbers = new ArrayList<>();
        List<Object> objects = new ArrayList<>();

        appendAll(integers, numbers);
        appendAll(numbers, objects);

        System.out.println(numbers);
        System.out.println(objects);
    }
}
```

```bash
javac AppendAllDemo.java
java AppendAllDemo
```

Output:

```text
[1, 2]
[1, 2]
```

This method illustrates the same rule as the signature `Collections.copy(List<? super T> dest, List<? extends T> src)`, though **their behavior differs**: `appendAll` uses `add` to append elements and grow the list, whereas `Collections.copy` replaces existing elements in the destination and requires the destination to be long enough. Do not mechanically substitute one for the other.

Just remember the relationship when choosing `T`: `destination` must have an element type that is `T` or a supertype of `T`. If `T` is `Number`, a `List<Integer>` cannot accept every `Number`; if `T` is `Integer`, `List<Number>` accepts them completely.

## 12. Trap caused by natural-language interpretation of “super”

A fairly common faulty inference:

> “`Number` is a supertype of `Integer`, so `List<? super Number>` must cover more list types than `List<? super Integer>`.”

In reality, the requirement `X super Number` is **stricter** than `X super Integer`. Only `X` broad enough to hold every `Number` satisfies `? super Number`, whereas `? super Integer` only needs `X` broad enough to hold every `Integer`.

Example:

```java
List<Integer> onlyIntegers = new ArrayList<>();

List<? super Integer> accepted = onlyIntegers; // Valid.
// List<? super Number> rejected = onlyIntegers; // Invalid.
```

`List<? super Integer>` **accepts more actual type arguments** (for example it can accept both `List<Integer>` and `List<Number>`), yet **allows adding fewer kinds of values** through the variable (`Integer` instead of any `Number`).

Conversely, `List<? super Number>` **accepts fewer actual list types**, yet **allows adding more kinds of values** (`Integer`, `Double`, `Long`, ...).

This is an important trade-off:

| Aspect | `? super Integer` | `? super Number` |
| --- | --- | --- |
| Lower bound | `Integer` | `Number` |
| Valid caller lists | Broader | Narrower |
| Non-null values writable | Only `Integer` | Any `Number` (and subtypes) |
| Safe read type | `Object` | `Object` |
| Assignable to the other variable type | Cannot directly convert to `? super Number` | Can convert to `? super Integer` |

## 13. Common compile errors and how to fix them

### Error 1: reversing the assignment direction

```java
List<? super Integer> ints = new ArrayList<Integer>();
// List<? super Number> nums = ints; // Invalid.
```

**Fix:** if the code needs to write `Number` values in general, require a destination of type `List<? super Number>` from the beginning. If the code only needs to write `Integer`, keep `List<? super Integer>`.

### Error 2: assuming `List<? super Integer>` is always `List<Number>`

```java
List<? super Integer> target = new ArrayList<Integer>();
// List<Number> exact = target; // Invalid.
```

**Fix:** if the program needs a real `List<Number>`, create or accept a list declared with exact type `List<Number>`. A wildcard does not tell you the concrete type argument of the underlying list.

### Error 3: reading from `? super Number` and immediately calling `Number` APIs

```java
List<? super Number> target = new ArrayList<Object>();
// Number value = target.get(0); // Invalid.
Object value = target.isEmpty() ? null : target.get(0); // Valid.
```

**Fix:** if the task is to read `Number` values for computation, consider `List<? extends Number>`; if the exact element type of the source is needed, use an appropriate generic method. Do not cast blindly.

### Error 4: inferring runtime mutability from the variable's type

```java
List<? super Number> target = List.of(1, 2);
// target.add(3.5); // Compiles if uncommented, but at runtime throws
                   // UnsupportedOperationException.
```

**Fix:** only call `add` when the data source contract guarantees the collection is mutable; you can use a new destination `ArrayList` when you need to own and update the list.

### Error 5: thinking `? super T` guarantees every existing element is `T`

```java
List<Object> rawContents = new ArrayList<>();
rawContents.add("not a number");

List<? super Number> numbers = rawContents;
numbers.add(42);

Object first = numbers.get(0); // "not a number", not a Number.
```

**Fix:** the lower-bound relationship only determines objects that **can be added**, not restrict objects already inside a supertype list. If every element must be a `Number`, a source declaration such as `List<? extends Number>` or `List<Number>` is appropriate.

### Error 6: casting to bypass the assignment relationship

For example, trying to cast `(List<? super Number>) (List<?>) integerList` discards type-safety proof and can produce an `unchecked` warning. If a `Double` is added into a real `List<Integer>`, an error may surface later when reading as `Integer`. Do not use raw types or unchecked casts to “fix” wildcard assignment errors.

## 14. Knowledge check

**Question 1.** `Integer extends Number`; which assignment is valid?

```java
List<? super Number> nums = new ArrayList<Number>();
List<? super Integer> ints = nums; // Valid.

// List<? super Number> other = ints; // Invalid.
```

The first assignment is valid because anywhere accepting `Number` also accepts `Integer`. The reverse assignment is invalid because `ints` might just be a `List<Integer>`.

**Question 2.** Can `List<? super Integer>` be passed to `void addNumbers(List<? super Number> x)`?

**No**, because the method could add a `Double`. However, `List<? super Number>` can be passed to `void addIntegers(List<? super Integer> x)`.

**Question 3.** Does `List<? super Number>` allow reading into a `Number` variable?

**No such guarantee.** The real list may be `List<Object>` containing non-`Number` objects. Reading is only guaranteed as `Object`.

**Question 4.** Is `List<Serializable>` compatible with `List<? super Number>`?

**Yes**, because the `Number` class implements `Serializable`. The lower bound considers interface relationships as well, not just the superclass chain.

**Question 5.** Is `List<? super Integer>` “stronger” or “weaker” than `List<? super Number>`?

No single word describes every operation. `? super Integer` accepts **more destination types** yet only guarantees writing `Integer`; `? super Number` accepts **fewer destination types** yet allows writing any `Number`. In terms of assignability, `List<? super Number>` is compatible with `List<? super Integer>`.

## 15. Rules to remember

1. If `A` is a subtype of `B`, then in the lower-bounded wildcard direction: `List<? super B>` is assignable to `List<? super A>`.
2. `List<? super Integer>` accepts lists whose element type is `Integer` or a supertype of `Integer`. It allows writing `Integer`.
3. `List<? super Number>` accepts lists whose element type is `Number` or a supertype of `Number`. It allows writing any `Number`.
4. Both types only guarantee reading elements as `Object`.
5. Exact generics like `List<Integer>` and `List<Number>` remain invariant, with no automatic inheritance relationship by type argument.
6. Choose the `super` bound according to the **kind of values the method needs to add**, while separately checking runtime mutability of the collection.

The fastest self-check before any assignment is to ask: “If the program only knows the variable type on the **left-hand side**, which objects is it allowed to add, and is the list on the **right-hand side** guaranteed to accept all of those objects?” Only if the answer is always yes is the assignment type-safe.