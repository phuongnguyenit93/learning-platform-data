# Meaning of `? super T` in Java Generics

## 1. What does `? super T` represent?

In Java Generics, **`? super T` is a lower-bounded wildcard**, meaning a wildcard with a **lower bound**. This syntax represents a type argument that is **not known exactly**, but must be **`T` or a supertype of `T`**. A supertype here is understood according to Java's subtype relationship, and can be a superclass or an interface that `T` implements.

Example:

```java
List<? super Integer> destination;
```

The actual element type of the list can be `Integer`, `Number`, `Object`, or another valid supertype of `Integer`. What Java guarantees is: **a value of type `Integer` can be inserted into this list in a type-safe manner**.

The two parts of the syntax serve different roles:

- `?`: a hidden type argument; the source code at this position **does not know exactly** which type `E` the list was declared with.
- `super T`: constrains `T` to be a subtype of or identical to that hidden type; therefore, a `T` value can be assigned to the actual element type.

`List<? super Integer>` can be read as: “A `List` with some element type broad enough to **accept an `Integer` value**”.

```java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

List<? super Integer> a = integers; // Valid
List<? super Integer> b = numbers;  // Valid
List<? super Integer> c = objects;  // Valid
```

These assignments only create **new references to existing lists**, without copying or converting elements. If `a` points to `integers`, modifying elements through `a` is also visible through `integers`.

What **cannot** be inferred from `? super Integer` is that “the type argument is definitely `Number`” or “the list is definitely `List<Object>`”. In each individual case, the actual type may differ; the compiler not knowing it leads to specific limitations when reading.

## 2. Which lists are compatible with `? super T`?

Consider the type hierarchy:

```text
Object
  └── Number
       ├── Integer
       ├── Double
       └── Long
```

With the lower bound `Integer`, the type parameters `Integer`, `Number`, and `Object` all accept `Integer`. Conversely, `Double` is a “sibling” type to `Integer`, not a supertype of `Integer`.

```java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();
List<Double> doubles = new ArrayList<>();

List<? super Integer> sink;

sink = integers; // Valid
sink = numbers;  // Valid
sink = objects;  // Valid
// sink = doubles; // Compile-time error
```

| Passed-in list | Accepted by `List<? super Integer>`? | Why? |
|---|---|---|
| `List<Integer>` | Yes | `Integer` is the lower bound itself |
| `List<Number>` | Yes | `Number` is a supertype of `Integer` |
| `List<Object>` | Yes | `Object` is a supertype of `Integer` |
| `List<Double>` | No | `Double` is not a supertype of `Integer` |
| `List<String>` | No | `String` is not a supertype of `Integer` |
| `List<? extends Number>` | Not guaranteed | The hidden type could be `Double`, which cannot accept `Integer` |
| `List<?>` | Not guaranteed | Unknown whether the hidden type can accept `Integer` |

The last column of the two wildcard rows refers to the fact that **you cannot rely on that static type to assign directly** to a `List<? super Integer>` variable. An object behind the variable might happen to have a compatible type, but the compiler is not allowed to rely on such a guess.

For a general `T`, the rule is identical: if `T` is `Dog`, then the type parameters `Dog`, `Animal`, and `Object` can serve as destinations accepting `Dog`, assuming `Dog extends Animal`. The keyword `super` in the wildcard indicates the **direction toward supertypes**.

## 3. Why can `T` and subtypes of `T` be added?

A `List<? super Integer>` can be a `List<Integer>`, `List<Number>`, or `List<Object>`. **All three can hold an `Integer`**, so the compiler allows:

```java
List<Number> numbers = new ArrayList<>();
List<? super Integer> destination = numbers;

destination.add(10);
destination.add(Integer.valueOf(20));
destination.set(0, 15);

System.out.println(numbers); // [15, 20]
```

The `add` and `set` operations above are safe regarding **element type**. If a type `T` has a subclass `S`, a value of `S` can also be added to `List<? super T>` thanks to the assignment relationship `S` → `T` → unknown supertype. For example, `? super Number` accepts `Integer` and `Double` values, because both are subtypes of `Number`.

```java
List<Object> objects = new ArrayList<>();
List<? super Number> sink = objects;

sink.add(Integer.valueOf(7));
sink.add(Double.valueOf(2.5));
sink.add((Number) Long.valueOf(9L));

System.out.println(objects); // [7, 2.5, 9]
```

However:

```java
List<? super Integer> sink = new ArrayList<Number>();

// sink.add(2.5);        // Does not compile: Double is not Integer
// sink.add(new Object()); // Does not compile: Object is not guaranteed to be compatible
sink.add(42);             // Valid
sink.add(null);           // Valid for type checking
```

Because the actual list might be `List<Integer>`, adding a `Double` or an arbitrary `Object` would not be safe. A variable of type `List<? super Integer>` **does not gain the right to add anything just because in one specific case it points to `List<Object>`**. The compiler evaluates based on the static type contract.

`null` is a special exception in type checking, because it can be assigned to any reference type. Whether adding `null` succeeds at runtime depends on the implementation (list mutability and null-allowance policy).

## 4. Why does reading only guarantee `Object`?

With `List<? super Integer>`, we **do not know** whether `E` is actually `Integer`, `Number`, or `Object`. Suppose the list is `List<Object>`: it may already contain both strings and numbers before being passed into the method. The lower-bound constraint does not guarantee that existing values are all `Integer`.

```java
List<Object> mixed = new ArrayList<>();
mixed.add("existing text");
mixed.add(100);

List<? super Integer> sink = mixed;
sink.add(42);

Object first = sink.get(0);  // Valid
Object third = sink.get(2);  // Valid

// Integer number = sink.get(2); // Error: get(2) only guarantees Object
// Number value = sink.get(2);   // Also an error: it could be an Object other than Number
```

Even though the element at index 2 is actually an `Integer`, the compiler does not rely on the index or existing data to change the return type of `get`.

Example working at runtime:

```java
Object value = sink.get(2);
if (value instanceof Integer number) {
    System.out.println(number + 1); // 43
}
```

`instanceof` checks **only the retrieved value itself**. It does not turn the entire `sink` variable into `List<Integer>` and makes no commitment that the other elements are `Integer`.

This read/write asymmetry is the core point:

- **Writing:** an `Integer` can be supplied because every type `E` matching `? super Integer` can accept `Integer`.
- **Reading:** it can only be safely assigned to `Object` because it is unknown whether the original value in `List<E>` is an `Integer`.

Do not misunderstand `? super T` as “every existing element is a supertype of `T`”. The wildcard constrains **the type argument of the structure**, not individual runtime values in some “larger” direction.

## 5. Complete Java 17 example: an API accepting multiple destination list types

Create the file `SuperWildcardDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class SuperWildcardDemo {
    static void addDefaults(List<? super Integer> destination) {
        destination.add(10);
        destination.add(20);
    }

    static <T> void appendAll(
            List<? extends T> source,
            List<? super T> destination) {
        for (T element : source) {
            destination.add(element);
        }
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>();
        List<Number> numbers = new ArrayList<>();
        List<Object> objects = new ArrayList<>();

        addDefaults(integers);
        addDefaults(numbers);
        addDefaults(objects);

        System.out.println("Integers: " + integers);
        System.out.println("Numbers: " + numbers);
        System.out.println("Objects: " + objects);

        List<? super Integer> receiver = numbers;
        receiver.set(0, 99);
        Object first = receiver.get(0);
        System.out.println("First as Object: " + first);

        List<Integer> more = List.of(3, 4);
        appendAll(more, numbers);
        System.out.println("After appendAll: " + numbers);

        List<? super Number> numberReceiver = objects;
        numberReceiver.add(1.5);
        System.out.println("Objects with double: " + objects);
    }
}
```

Compile and run with Java 17 or later:

```bash
javac SuperWildcardDemo.java
java SuperWildcardDemo
```

**Exact stdout:**

```text
Integers: [10, 20]
Numbers: [10, 20]
Objects: [10, 20]
First as Object: 99
After appendAll: [99, 20, 3, 4]
Objects with double: [10, 20, 1.5]
```

Why does the example compile and run?

1. `addDefaults` accepts `List<Integer>`, `List<Number>`, and `List<Object>`, because all three lists can accept `Integer`.
2. `receiver.set(0, 99)` is valid: `set` writes an `Integer` into a list whose hidden type is `Integer` or a supertype of it. `receiver.get(0)` only has `Object` as its safe static type.
3. `appendAll` uses a type parameter `T` connecting the source and destination. In the call `appendAll(more, numbers)`, `T` can be inferred such that both the source `List<Integer>` and the destination `List<Number>` are compatible.
4. `numberReceiver` has the lower bound `Number`, so adding a `Double` is type-safe even when the variable is referencing `List<Object>`.

All lists are created with mutable `ArrayList` instances, so `add` and `set` succeed. Printing the lists relies on `toString()` of `ArrayList` and the integer/`Double` elements, so the stdout matches the output above.

## 6. PECS: “Consumer Super”

The **PECS** rule stands for “**Producer Extends, Consumer Super**”. This is a mnemonic for designing APIs with wildcards:

- A **producer** produces/supplies values to the algorithm, so use `? extends T` to allow **reading** values as type `T`.
- A **consumer** receives values from the algorithm, so use `? super T` to allow **writing** values of type `T` into the destination.

General example:

```java
static <T> void appendAll(
        List<? extends T> source,
        List<? super T> destination) {
    for (T element : source) {
        destination.add(element);
    }
}
```

In the loop, `source` produces values assignable to `T`; `destination` receives those `T` values. The method allows calls such as:

```java
List<Integer> ints = List.of(1, 2);
List<Number> nums = new ArrayList<>();
List<Object> objs = new ArrayList<>();

appendAll(ints, nums); // Valid
appendAll(ints, objs); // Valid
appendAll(nums, objs); // Valid
```

There are no unchecked casts and no need to use a raw `List`. If the destination parameter were replaced with `List<T>`, the API would be unnecessarily restrictive for many calls where the destination's element type is a supertype of `T`.

**PECS describes the role of a parameter in the algorithm**, which does not mean `? super T` is strictly “write-only”: you can still read as `Object`, count elements, or remove elements when the implementation supports it. Likewise, `? extends T` does not mean the structure is immutable; it only restricts arbitrarily adding values of a specific type into an unknown type.

## 7. When should you use `List<? super T>` instead of `List<T>`?

Compare the two signatures:

```java
static void addCountStrict(List<Integer> values) {
    values.add(1);
}

static void addCountFlexible(List<? super Integer> values) {
    values.add(1);
}
```

`addCountStrict` only accepts `List<Integer>`. `addCountFlexible` also accepts `List<Number>` and `List<Object>`. If inside the method you only need to **put an `Integer` into the list**, the second signature accurately describes the required capability and is more flexible.

However, if the algorithm needs to **read results from the list itself as `Integer`**, `List<? super Integer>` does not guarantee that:

```java
static Integer getFirstStrict(List<Integer> values) {
    return values.get(0);
}

static Object getFirstFlexible(List<? super Integer> values) {
    return values.get(0);
}
```

The snippet above assumes the list is non-empty; if it is empty, `get(0)` throws `IndexOutOfBoundsException` regardless of the generic parameter.

The question to ask when designing a signature is **“Does the method need to know the exact type of the elements being read, or does it only need to put `T` values into the list?”**. When the main operation is writing `T`, `super` is usually the right choice.

## 8. Using `? super T` with interfaces or subclasses

`super` does not require the lower bound to be a class with a direct `extends` relationship. It also supports type relationships involving interfaces.

Suppose we have custom declarations:

```java
interface Event {
    String label();
}

record LoginEvent(String user) implements Event {
    public String label() {
        return "Login " + user;
    }
}
```

This is an **illustrative declaration snippet**, not a standalone program. A `List<? super LoginEvent>` can reference `List<LoginEvent>`, `List<Event>`, or `List<Object>`; into it you can add `LoginEvent` objects:

```java
List<Event> log = new ArrayList<>();
List<? super LoginEvent> sink = log;

sink.add(new LoginEvent("Lan")); // Valid
Object entry = sink.get(0);      // Safe to read as Object
```

Even though the `sink` variable points to `List<Event>` in the example, the compiler still only allows `get` to return the general safe type `Object` on a variable with a lower-bounded wildcard type.

When the lower bound is a type that has subclasses, you can also add objects of those subtypes. For example, `List<? super Number>` allows adding `Integer` and `Double` because both are `Number`.

## 9. Does a lower-bounded wildcard change list mutability?

No. Generics control **value types**, while the concrete list controls **mutability** and other runtime restrictions.

```java
List<Number> mutable = new ArrayList<>();
List<? super Integer> a = mutable;
a.add(1);       // Accepted by the compiler and allowed by ArrayList
a.add(null);    // Accepted by the compiler; ArrayList allows null
```

On the contrary:

```java
List<Integer> immutable = List.of(1, 2);
List<? super Integer> b = immutable;

// b.add(3); // Type-safe, but throws UnsupportedOperationException at runtime
```

Here `List.of(...)` returns an unmodifiable list. If `b.add(3)` is uncommented, the program compiles but throws `UnsupportedOperationException` at runtime.

`List<? super Integer>` also allows calling methods that do not depend on adding a specific element, such as `clear()`, `remove(Object)`, `remove(int)`, `size()`, and `contains(Object)`. `remove(0)` selects the overload taking an **`int` index**, not the overload removing an `Integer.valueOf(0)` object. Removal and modification operations remain subject to the runtime rules of the implementation.

Therefore, do not use `? super T` as a mechanism to protect data from modification; if an unmodifiable contract is needed, provide an unmodifiable structure or an appropriate copy.

## 10. Relationship among `? super T`, `? extends T`, `?`, and a concrete type

The following table uses `T = Number`:

| Declared type | Accepted list type parameters | Safe type read from `get` | Add an arbitrary `Number`? |
|---|---|---|---|
| `List<Number>` | Exactly `Number` | `Number` | Yes |
| `List<? super Number>` | `Number` or supertypes such as `Object` | `Object` | Yes |
| `List<? extends Number>` | `Number` or subtypes such as `Integer`, `Double` | `Number` | No |
| `List<?>` | Any element type | `Object` | No |
| Raw `List` | Discards type argument info | `Object` | Possible, but unsafe; produces unchecked warning |

In the `List<?>` and `List<? extends Number>` rows, `add(null)` remains a type-valid exception. In the rows where values can be added, you still must check whether the implementation allows modifying the list.

Points to distinguish:

- `List<Number>` is **not** a supertype of `List<Integer>` even though `Number` is a supertype of `Integer`; Java Generics are *invariant*.
- `List<? super Integer>` **accepts** `List<Number>`; that is the flexibility of a lower-bounded wildcard, not inheritance between `List<Integer>` and `List<Number>`.
- `? super Number` differs from `? extends Number`: the first represents the ability to **accept `Number` values**, while the second represents the ability to **supply values readable as `Number`**.

## 11. Example outside `List`: `Comparator<? super T>`

The principle of “passing a `T` value to a consumer of a supertype” also appears in Java library APIs.

`List<E>.sort` accepts `Comparator<? super E>`. A comparator that knows how to compare `Number` can be used to sort a list of `Integer`, because that comparator **accepts** `Integer` values as `Number`:

```java
List<Integer> values = new ArrayList<>(List.of(30, 2, 11));
Comparator<Number> byNumericValue =
        Comparator.comparingDouble(Number::doubleValue);

values.sort(byNumericValue);
System.out.println(values); // [2, 11, 30]
```

When placing this snippet into a Java class, you need to import `java.util.ArrayList`, `java.util.List`, and `java.util.Comparator`. This is an illustrative snippet, not a standalone `main`.

If `sort` required an exact `Comparator<Integer>`, a general comparator accepting `Number` could not be used directly. The lower bound `? super E` lets the API use a consumer accepting a supertype, in line with PECS.

## 12. Note on `Collections.copy` and “writing to a destination”

Another library API clearly demonstrates the source/destination roles:

```java
static <T> void copy(
        List<? super T> dest,
        List<? extends T> src)
```

This is a **simplified signature** of `java.util.Collections.copy`, not a custom method to place alongside that name in a program. `src` is an upper-bounded source because we read `T` from it; `dest` is lower-bounded because we write `T` into it.

Unlike `appendAll` in the previous section, `Collections.copy` **replaces** the corresponding elements in the destination. The destination list must have a size **at least equal to** the source list; it does not automatically grow the destination by calling `add`.

Java 17 example:

```java
List<Integer> source = List.of(7, 8);
List<Number> destination =
        new ArrayList<>(List.of(0, 0, 0));

Collections.copy(destination, source);
System.out.println(destination); // [7, 8, 0]
```

You need to import `java.util.Collections`, `java.util.List`, and `java.util.ArrayList`. If `destination` is empty, `Collections.copy(destination, source)` throws `IndexOutOfBoundsException`; if the destination is unmodifiable, `UnsupportedOperationException` may occur. These are behavioral constraints of the API, independent of whether the generic types already match.

## 13. Not every declaration with `super` is valid syntax

`super` in the syntax being studied is a **lower bound for a wildcard** at a type argument position:

```java
List<? super Integer> sink;
Consumer<? super Integer> handler;
Comparator<? super Integer> comparator;
```

However, Java **does not** allow declaring a named type parameter using the syntax `<T super Integer>`:

```java
// class Box<T super Integer> { } // Java syntax error
// static <T super Number> void f() { } // Java syntax error
// List<super Integer> list; // Error: missing ? of the wildcard
```

A named type parameter such as `<T extends Number>` uses an upper-bound constraint. When you want to express a **consumer** of `T` at a type argument position, you write `? super T` inside a generic type, such as `List<? super T>`.

In addition, `? super T` is not syntax used in object creation expressions:

```java
// List<? super Integer> bad = new ArrayList<? super Integer>(); // Error
List<? super Integer> good = new ArrayList<Number>();          // Valid
```

The object creation side uses a concrete type argument (`Number`) or the diamond operator `<>` for compiler inference. The wildcard on the declaration side describes the view and allowed operations through the variable `good`.

## 14. Common mistakes when learning `? super T`

**Mistake 1: “`? super Integer` means every element read out is `Integer` or a supertype.”** False. The constraint applies to the list's type argument. If the actual type argument is `Object`, the list may already contain a `String`. When reading, only `Object` is guaranteed.

**Mistake 2: “A `List<? super Integer>` destination accepts `Double` because both `Double` and `Integer` are `Number`.”** False. `List<? super Integer>` might actually be `List<Integer>`; it is only guaranteed to accept `Integer` and subtypes of `Integer` (if any exist).

**Mistake 3: “`List<Integer>` can be passed to `List<Number>` because `Integer extends Number`.”** False. Generics are invariant. To design a method taking a list to add `Integer`, you can use `List<? super Integer>`.

**Mistake 4: “The `super` keyword means the list must have the exact element type of the superclass `Number`.”** False. The element type can be `Integer` itself, a superclass, or a compatible superinterface; the wildcard does not specify that exact type.

**Mistake 5: “If `get` only returns `Object`, then `? super T` shouldn't be used.”** False when the API is a consumer. A consumer signature prioritizes the ability to safely write `T`; if reading `T` is needed, revisit the contract or use an appropriately named generic type parameter.

**Mistake 6: “`? super T` guarantees every `add` call succeeds.”** False. `add(T)` is type-valid, but can still throw `UnsupportedOperationException` or other errors depending on the list instance.

**Mistake 7: “`Collections.copy` works like an `add` loop.”** False. `Collections.copy` replaces existing elements and requires a sufficiently large destination; an `add` loop appends elements to the end (when supported by the implementation).

**Mistake 8: “Using raw `List` is a way to avoid wildcard limitations.”** Using raw types disables generic checks and can cause *heap pollution*, leading to `ClassCastException` elsewhere in the code. Choose the right wildcard contract rather than disabling type safety.

## 15. Self-check exercise

Given the code snippet:

```java
List<Integer> integers = new ArrayList<>(List.of(1, 2));
List<Number> numbers = new ArrayList<>(List.of(5, 6));
List<Object> objects = new ArrayList<>(List.of("before"));
List<? super Integer> target = numbers;
```

Answer before checking the solutions:

1. Can you assign `target = integers` and `target = objects`? What about `target = new ArrayList<Double>()`?
2. Do `target.add(7)` and `target.add(null)` compile?
3. Does `target.add(7.5)` compile, even though `target` initially points to `List<Number>`?
4. Can you write `Integer x = target.get(0)` or `Number y = target.get(0)` without a cast?
5. Does `target.set(0, 99)` compile? Where does it modify the element?
6. Does `List<? super Number> numberSink = objects;` compile? Can you call `numberSink.add(3.14)`?
7. If `target` references `List.of(1, 2)` via a type-valid variable, is `target.add(3)` accepted at runtime?

**Answers:**

1. Both `List<Integer>` and `List<Object>` are valid. `List<Double>` is not compatible because `Double` is not a supertype of `Integer`.
2. Both calls compile validly. The actual object must support adding elements and may have its own null policy.
3. No. `Double` is not `Integer`. The compiler relies on the static type `List<? super Integer>` rather than the actual type happening to be `List<Number>`.
4. No. For `get(0)`, the safest static type is `Object`. Assigning to `Number` or `Integer` requires appropriate additional checks/evidence.
5. Yes. `set` is allowed to take `Integer`, and it will replace the element at index 0 of the list object that `target` currently references; in the initial setup, that is `numbers`.
6. Yes. `List<Object>` accepts `Number` and its subtypes; `3.14` is boxed into `Double`, which is a `Number`.
7. No. The call is type-valid, but the list created by `List.of` is unmodifiable, so it throws `UnsupportedOperationException`.

## 16. Rule to remember

**`? super T` = “an unknown type broad enough to accept `T`”.** This is a constraint on the type argument, allowing an API to accept a destination of type `T` or a supertype of `T` while still checking written values at compile time. Reading elements from the destination only guarantees `Object` because existing data may belong to a type broader than `T`.

When a parameter acts as a **receiver of `T` values**, consider `? super T`. When it acts as a **source supplying `T` values**, consider `? extends T`. When multiple positions need to relate to the same type `T`, combine wildcards with a named type parameter following the PECS principle.