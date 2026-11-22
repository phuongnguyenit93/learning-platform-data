# Why is reading from `List<? super T>` only guaranteed to be `Object`?

## 1. The problem to understand

In Java generics, the lower-bounded wildcard `? super T` denotes **an unknown type that is `T` or a supertype of `T`**. For example, `List<? super Integer>` can reference `List<Integer>`, `List<Number>`, `List<Object>`, or a list parameterized with another valid supertype of `Integer`.

We can safely **add `Integer`** to those lists, because every possible element type accepts `Integer`. However, when **reading** via `get(...)`, the compiler does not know whether the actual list holds `Integer`, `Number`, `Object`, or values of a broader type. For `java.util.List<E>`, the declared upper bound of `E` is `Object`, so the only guaranteed read type is **`Object`**.

~~~java
List<Number> numbers = new ArrayList<>();
List<? super Integer> destination = numbers;

destination.add(42);            // Valid: Integer matches any supertype of Integer.
Object item = destination.get(0); // Valid: the safe upper bound is Object.
// Integer exact = destination.get(0); // Compile-time error.
~~~

This is the key distinction between **the element type that can be written** and **the element type that can be inferred when reading**. This lesson explains the exact cause, common pitfalls, and usage in Java 17+ APIs.

## 2. Which lists can a `List<? super Integer>` variable point to?

Consider the following independent declarations:

~~~java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

List<? super Integer> a = integers;
List<? super Integer> b = numbers;
List<? super Integer> c = objects;
~~~

All three assignments are valid because `Integer` can be used wherever `Integer`, `Number`, or `Object` is expected. There may also be other supertypes, such as interfaces implemented by `Integer`. The wildcard does not pick one of those types at compile time; it **hides the concrete element type** from code using the `List<? super Integer>` variable.

Imagine the actual list is:

~~~java
List<Object> objects = new ArrayList<>();
objects.add("text");                // String is an Object.
objects.add(Integer.valueOf(99));   // Integer is also an Object.

List<? super Integer> view = objects;
Object first = view.get(0);         // Actual value is String.
~~~

If the compiler allowed `Integer first = view.get(0)`, the program would receive a `String` as an `Integer`, breaking the static guarantee of generics. Java does not allow that assignment. The ability to **add** `Integer` does not imply that **every existing element** is an `Integer`.

**Important point:** `List<? super Integer>` does not mean “a list containing only integers”. It is *a view* capable of writing integers into lists whose element type is a valid supertype of `Integer`.

## 3. Type reasoning: lower bound enables writing, upper bound determines reading

`List<E>` declares type parameter `E` without an explicit bound, so the default bound of `E` is `Object`.

When the compiler encounters `List<? super Integer>`, Java's **capture conversion** rules can model the wildcard using a hidden type, temporarily called `CAP#1`:

~~~text
Integer <: CAP#1 <: Object
~~~

This is a **type-relationship diagram**, not Java declaration syntax. The notation `A <: B` states that `A` is a subtype of `B`.

- **The lower bound `Integer`** guarantees that every `Integer` value is assignable to `CAP#1`. Therefore `destination.add(42)` compiles.
- **The upper bound `Object`** guarantees that every value of type `CAP#1` can be read as `Object`.
- No constraint guarantees `CAP#1 <: Number` or `CAP#1 <: Integer`. Therefore `Number n = destination.get(0)` and `Integer i = destination.get(0)` are not permitted.

Attach this reasoning to the signatures of `List<E>`:

~~~java
E get(int index);
boolean add(E element);
E set(int index, E element);
~~~

These are **simplified signatures** for explaining types, not three standalone methods to compile. After capture conversion:

- `get` returns `CAP#1`, which can be **widened to `Object`** without a cast.
- `add` expects a `CAP#1` value; the compiler permits passing `Integer` because `Integer <: CAP#1`.
- `set` accepts `Integer` safely, but the old value it returns can still only be used as `Object`.

For example:

~~~java
List<? super Integer> sink = new ArrayList<Number>();
sink.add(5);
Object old = sink.set(0, 7);
Object current = sink.get(0);

// Invalid: the exact CAP#1 type is unknown.
// Integer oldInt = sink.set(0, 9);
// Number currentNumber = sink.get(0);
~~~

**The reading rule actually depends on the *upper bound* of the type variable in the generic class, not solely on the `super` keyword.** For `List<E>`, that bound is `Object`. An example of a generic class with bound `E extends Number` will be examined separately in Section 8.

## 4. Comparing `extends`, `super`, and unbounded wildcards

| View type | Some matching source types | Safe type for `get(0)` | Can `add(new Integer(1))` type-wise? |
| --- | --- | --- | --- |
| `List<Integer>` | `List<Integer>` | `Integer` | Yes |
| `List<? extends Number>` | `List<Integer>`, `List<Double>`, `List<Number>` | `Number` | No |
| `List<? super Integer>` | `List<Integer>`, `List<Number>`, `List<Object>` | `Object` | Yes |
| `List<?>` | `List<String>`, `List<Integer>`, etc. | `Object` | No (except `null`) |
| `List<Object>` | `List<Object>` | `Object` | Yes |

In the table, “can add” only means **the compiler allows the operation type-wise**. If the implementation is an unmodifiable list like `List.of(...)`, `add` can still throw `UnsupportedOperationException` at runtime.

Compare three small examples:

~~~java
List<Integer> ints = new ArrayList<>();

List<? extends Number> producer = ints;
Number readNumber = producer.get(0); // Type-valid (though the list must have an element).
// producer.add(5);                  // Invalid.

List<? super Integer> consumer = ints;
consumer.add(5);                     // Valid.
Object readObject = consumer.get(0);  // Valid.
// Integer readInteger = consumer.get(0); // Invalid.

List<?> unknown = ints;
Object any = unknown.get(0);         // Valid.
// unknown.add(5);                   // Invalid.
~~~

Because `ints` starts as an empty list, **do not run `get(0)` before an element is added**; the block above illustrates the type system line by line, not a complete program executed sequentially. Standalone runnable code with valid elements is in Section 7.

PECS (*Producer Extends, Consumer Super*) summarizes two common use cases:

- When needing to **read values as a specific supertype**, choose `? extends T`.
- When needing to **write values of `T` or subtypes of `T`**, choose `? super T`.

PECS does not mean `? super T` is forbidden from reading; you can still read, though usually only as `Object` when the generic declaration does not specify a narrower bound.

## 5. Why doesn't “I just added an Integer” change the read type to Integer?

An intuitive example:

~~~java
List<Number> numbers = new ArrayList<>();
numbers.add(1.5);

List<? super Integer> sink = numbers;
sink.add(42);

Object first = sink.get(0);  // Actually Double.
Object second = sink.get(1); // Actually Integer.
~~~

The variable `sink` has **one single declared type**. The compiler does not establish a rule that positions after an `add(Integer)` call definitely always hold `Integer`:

- The list may **already have older elements** of a broader supertype.
- The list may be modified through **another reference** such as `numbers`, pointing to the same object.
- Element indices and list state can change through other operations; the compiler does not track the origin/runtime type of each position in a general collection.
- A list under a `List<? super Integer>` view can hold `Number` or `Object` instances depending on the actual generic argument.

If you still hold the exact `Integer` object that was added and want to use it, use the already-typed variable:

~~~java
Integer added = 42;
sink.add(added);
Integer retained = added; // No need to read back from view.
~~~

If you need to read elements as `Number` and you **know for certain the source list** has type `List<Number>`, use the reference that carries more precise type information:

~~~java
List<Number> typed = new ArrayList<>();
List<? super Integer> sink = typed;

sink.add(42);
Number n = typed.get(0); // Valid thanks to typed's declared type List<Number>.
Object o = sink.get(0);  // Only Object through the List<? super Integer> view.
~~~

Both variables point to the same list, but the **static type contract** at each expression differs. Reading via `sink` does not automatically inherit all knowledge from `typed`.

## 6. Safe reading: use `Object` and check when a subtype is needed

With `List<? super Integer>`, the general form is:

~~~java
List<? super Integer> values = new ArrayList<Object>();
values.add(10);
Object value = values.get(0);
System.out.println(value);
~~~

If the algorithm genuinely needs arithmetic operations, **check the read object at runtime**:

~~~java
Object value = values.get(0);
if (value instanceof Integer integer) {
    System.out.println(integer + 1);
} else if (value instanceof Number number) {
    System.out.println(number.doubleValue());
} else {
    System.out.println("Không phải số nguyên hoặc Number");
}
~~~

Pattern matching for `instanceof` in the example above has been supported since Java 16 and works reliably in Java 17. It proves the type **of the individual object being checked**, not that every element in the list is an `Integer`.

A checked cast can be used:

~~~java
Object value = values.get(0);
Integer integer = (Integer) value; // Only succeeds if the object is Integer or null.
~~~

If the actual value is `Double` or `String`, the cast throws `ClassCastException`; if it is `null`, the cast evaluates to `null`. Prefer `instanceof` when data may have multiple types. **Casting does not turn `List<? super Integer>` into `List<Integer>`.**

Do not write:

~~~java
List<? super Integer> values = new ArrayList<Object>();
// DOES NOT compile: the return type CAP#1 only guarantees Object.
Integer integer = values.get(0);

// DOES NOT compile because List<? super Integer> is not guaranteed to be List<Integer>.
List<Integer> exactList = values;
~~~

The compile-time error prevents callers from inferring a subtype solely from a lower bound.

## 7. Complete Java 17+ program: writing Integer and reading as Object

Save the file as **SuperReadDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SuperReadDemo {
    static final class NumberBox<T extends Number> {
        private T value;
        NumberBox(T value) { this.value = value; }
        T get() { return value; }
        void set(T value) { this.value = value; }
    }

    static void appendInteger(List<? super Integer> destination, Integer value) {
        destination.add(value);
    }

    public static void main(String[] args) {
        List<Number> numbers = new ArrayList<>();
        numbers.add(1.5);
        List<? super Integer> output = numbers;
        appendInteger(output, 10);
        Object first = output.get(0);
        Object last = output.get(1);
        System.out.println("first: " + first);
        System.out.println("last: " + last);
        System.out.println("numbers: " + numbers);

        List<Object> mixed = new ArrayList<>();
        mixed.add("text");
        List<? super Integer> sameTypeOfView = mixed;
        sameTypeOfView.add(7);
        Object item = sameTypeOfView.get(0);
        System.out.println("mixed first: " + item);
        if (sameTypeOfView.get(1) instanceof Integer value) {
            System.out.println("checked integer: " + value);
        }
        System.out.println("mixed: " + mixed);

        NumberBox<Number> numberBox = new NumberBox<>(3.5);
        NumberBox<? super Integer> boxView = numberBox;
        Number before = boxView.get();
        boxView.set(9);
        System.out.println("bounded read: " + before);
        System.out.println("bounded after: " + boxView.get());
    }
}
~~~

Compile and run (Java 17+):

~~~bash
javac --release 17 -Xlint:all SuperReadDemo.java
java SuperReadDemo
~~~

**Exact stdout**:

~~~text
first: 1.5
last: 10
numbers: [1.5, 10]
mixed first: text
checked integer: 7
mixed: [text, 7]
bounded read: 3.5
bounded after: 9
~~~

The program has been tested with `javac --release 17 -Xlint:all` and runs successfully **without any unchecked warnings**.

Explanation:

1. `output` has type `List<? super Integer>` and is assigned from `List<Number>`; `appendInteger` safely adds `10`.
2. Even after adding `Integer`, `output.get(0)` and `output.get(1)` are both read into `Object` variables. The first element is actually `Double 1.5` and the second is `Integer 10`.
3. `sameTypeOfView` has the **same static type** `List<? super Integer>` but points to `List<Object>` already containing `String "text"`. This is a direct counterexample to assuming that reading from `? super Integer` always yields `Integer`.
4. `instanceof Integer value` properly checks the second element before using it as `Integer`.
5. `NumberBox<? super Integer>` can be read as `Number` because the type parameter **of `NumberBox<T extends Number>` itself** has the upper bound `Number`, as explained in the next section.

## 8. Important exception: generic classes with an upper bound narrower than `Object`

Saying “`? super T` can always only be read as `Object`” is **too broad**. The exact rule is: the capture type takes its **upper bound from the type parameter of the generic declaration**; the minimum read result is based on that bound.

With `List<E>`, `E` has the default upper bound `Object`, so `List<? super Integer>.get()` has no guarantee stronger than `Object`.

However, with a custom class:

~~~java
static final class NumberBox<T extends Number> {
    private T value;

    NumberBox(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    void set(T value) {
        this.value = value;
    }
}
~~~

`NumberBox<? super Integer>` has capture type `CAP#2` satisfying:

~~~text
Integer <: CAP#2 <: Number
~~~

Because the **upper bound is `Number`**, it can be safely read as `Number`:

~~~java
NumberBox<Number> actual = new NumberBox<>(3.5);
NumberBox<? super Integer> view = actual;

view.set(42);             // Integer is a subtype of CAP#2.
Number n = view.get();    // Valid: CAP#2 is definitely a Number.
// Integer i = view.get(); // Invalid: CAP#2 could be Number.
~~~

The two blocks above are **illustrative snippets needing to be placed in the same class and appropriate import/type context**, whereas the program in Section 7 is a standalone runnable example.

JLS rules on capture conversion also consider bounds and constraints of other generic declarations; the `T extends Number` form is the easiest case to observe. Therefore, **reading `Object` is the right conclusion for `List<? super T>` and generic types whose parameter bound is `Object`**, while you must check the upper bound when using other generic classes.

## 9. Writing consumer-oriented APIs: when to choose `? super T`?

### 9.1. A method that pushes data into a destination list

~~~java
static void addDefaults(List<? super Integer> target) {
    target.add(10);
    target.add(20);
}
~~~

This method can be called with `List<Integer>`, `List<Number>`, or `List<Object>`, as long as the implementation allows modification. The method only needs to know that **`Integer` is an accepted type when writing**. It does not need to read from the list and perform `Integer` operations.

### 9.2. Contrasting an `extends` source and a `super` destination

~~~java
static <T> void copyValues(List<? extends T> source, List<? super T> target) {
    for (T element : source) {
        target.add(element);
    }
}
~~~

This is an illustrative method that can be placed in a Java class after importing `java.util.List`. Example:

~~~java
List<Integer> source = List.of(1, 2, 3);
List<Number> target = new ArrayList<>();
copyValues(source, target);
~~~

`source` **supplies** `T` values; `target` **receives** `T` values. The signature separates the two goals and does not require reading `Integer` from a `List<? super Integer>`. Before using this pattern in production, consider contracts regarding mutable lists, `null`, and handling cases where source/destination might be updated concurrently.

The standard API `Collections.copy(List<? super T> dest, List<? extends T> src)` uses this exact principle; it additionally requires the destination to be large enough (unlike appending in the `copyValues` example). Do not assume every “copy” means appending elements to the end.

### 9.3. Do not use `? super` when an exact subtype needs to be returned

If the goal is to retrieve `Integer` for computation, accept a suitably typed source:

~~~java
static int sumIntegers(List<Integer> values) {
    int total = 0;
    for (Integer value : values) {
        total += value;
    }
    return total;
}
~~~

Or if you want to handle other numeric types as well:

~~~java
static double sumNumbers(List<? extends Number> values) {
    double total = 0.0;
    for (Number value : values) {
        total += value.doubleValue();
    }
    return total;
}
~~~

Using `? super Integer` for a parameter meant only to **read integers** creates an overly broad input contract and an overly weak result type.

## 10. Other operations on `List<? super Integer>`

| Operation | Allowed by compiler? | Meaning |
| --- | --- | --- |
| `destination.add(3)` | Yes | `Integer` is assignable to the capture type. |
| `destination.add(Integer.valueOf(3))` | Yes | Adds an `Integer`. |
| `destination.add(3.5)` | No | `Double` is not guaranteed compatible with all destination list types. |
| `destination.add((Number) 3)` | No | A `Number` variable may hold a non-`Integer` type. |
| `destination.add(null)` | Yes type-wise | `null` can be passed to a reference type; concrete collections may reject null. |
| `Object x = destination.get(0)` | Yes | The upper bound of `List<E>` is `Object`. |
| `Integer x = destination.get(0)` | No | Capture is not guaranteed to be a subtype of `Integer`. |
| `Number x = destination.get(0)` | No | Capture could be `Object`. |
| `Object x = destination.set(0, 7)` | Yes type-wise | Writes `Integer`, reads the old element as `Object`. |
| `destination.remove(0)` | Yes type-wise | Removes by index; does not require supplying a specific element type. |
| `destination.clear()` | Yes type-wise | Clears all elements; implementation may forbid modification. |

Some methods return types unrelated to `E`, such as `size()` returning `int` and `contains(Object)` returning `boolean`. The phrase “reading is only guaranteed to be Object” specifically refers to **reading a value of type parameter `E`** via `get`, `iterator().next()`, `set` returning the old element, etc., not every method on `List`.

## 11. Common mistakes and how to fix them

**Mistake 1 — Equating `? super Integer` with `List<Integer>`.**

~~~java
List<? super Integer> target = new ArrayList<Number>();
// Integer n = target.get(0); // Does not compile.
~~~

Fix by accepting the value as `Object`, using `instanceof` if branching on actual type is needed, or changing the method contract if the algorithm requires `Integer`.

**Mistake 2 — Inferring the read type from a recently added value.** Java cannot track every element in a container by insertion order at the type level. Keep the original `Integer` reference, or use a more specific view when you have proof.

**Mistake 3 — Casting `(Integer) list.get(0)` without checking the data.** This cast can raise `ClassCastException` if the element is a `Double` or `String`. It also does not change the generic type of the list.

**Mistake 4 — Casting the entire collection:**

~~~java
List<? super Integer> view = new ArrayList<Object>();
// Do not try to turn the entire list into List<Integer>
// via a raw cast or unchecked cast to get a more specific element type.
~~~

Using raw types or unchecked casts only hides the risk and can cause heap pollution. If a `List<Integer>` collection is needed, check each value individually and build a new collection with a definite type argument.

**Mistake 5 — Thinking `? super Number` can read `Number`.** For `List<E>`:

~~~java
List<? super Number> list = new ArrayList<Object>();
list.add(3.5);          // Valid: Double is a Number.
Object value = list.get(0); // Read type is still only guaranteed to be Object.
// Number n = list.get(0);  // Does not compile.
~~~

The lower bound `Number` allows adding `Number` and subtypes; it does **not** raise the upper bound of `List<E>` above `Object`.

**Mistake 6 — Forgetting that a generic view does not determine list mutability.** `List<? super Integer> view = List.<Integer>of(1, 2);` is valid, but `view.add(3)` throws `UnsupportedOperationException` at runtime because `List.of` creates an unmodifiable list. This is a mutability contract issue, not a type-bound error.

## 12. Knowledge self-check

1. Can `List<? super Integer>` receive a reference to `List<Object>`? **Yes**, because `Object` is a supertype of `Integer`.
2. Why is `target.add(12)` valid? **Because `Integer` is a subtype of every element type compatible with `? super Integer`.**
3. Why is `Integer x = target.get(0)` invalid? **Because the actual element type may be `Number`, `Object`, or another supertype; the compiler only knows that the upper bound of `List<E>` is `Object`.**
4. Once an `Integer` has been added, can every element be read as `Integer`? **No.** The list may already contain values of a broader type and may be modified through another reference.
5. Can `instanceof Integer` be used on the retrieved value? **Yes.** That check guarantees the type only for the value being tested when the condition holds.
6. Is `? super T` always only readable as `Object` in every generic class? **No.** With `Box<E extends Number>` and `Box<? super Integer>`, it can be read as `Number`.
7. To accept a list for reading all elements as `Number`, should you choose `List<? extends Number>` or `List<? super Number>`? **`List<? extends Number>`**, because it guarantees each element can be read as `Number`.

## 13. References

- [JLS Java SE 17 §4.5.1 — Type Arguments of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.1): lower/upper-bounded wildcards and containment.
- [JLS Java SE 17 §5.1.10 — Capture Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.10): capture type of `? super T`, lower bound, and upper bound from generic declarations.
- [JLS Java SE 17 §4.10.2 — Subtyping Among Class and Interface Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.10.2): subtyping relationships with parameterized types.
- [Java SE 17 API — List<E>](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): signatures of `add(E)`, `get(int)`, `set(int,E)` and exceptions they may throw.
- [Java SE 17 API — Collections.copy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#copy(java.util.List,java.util.List)): practical example using `? super T` for the destination and `? extends T` for the source.