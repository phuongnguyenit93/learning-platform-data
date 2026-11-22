# Accepting `List<T>` and Lists of Subtypes Using `? extends T`

A method that needs to process values of type `T` often also wants to accept lists containing **subtypes of `T`**. In Java Generics, the signature `List<T>` when `T` is fixed **does not automatically accept** `List<Subtype>` simply because `Subtype extends T`. The way to express a *data source whose elements are `T` or a subtype of `T`* is **`List<? extends T>`**.

For example, `Integer` and `Double` are both subtypes of `Number`:

~~~java
List<Integer> integers = List.of(1, 2, 3);
List<Double> doubles = List.of(1.5, 2.5);

// List<Number> a = integers; // COMPILE ERROR.
List<? extends Number> b = integers; // Valid.
List<? extends Number> c = doubles;  // Valid.
~~~

This is an **illustrative snippet that needs to be placed inside a class and import `java.util.List`**. The direct assignment line to `List<Number>` is commented out because it is intentionally mistyped. The two lines using wildcards are valid without unchecked casts and without copying the list.

Key takeaway: **`? extends T` lets you accept multiple list types; in return, the compiler restricts writing new elements through that reference.** You need to understand both sides to build correct APIs.

## 1. Why Doesn't `List<T>` Automatically Accept `List<Subtype>` When `T` Is Fixed?

With ordinary variables, subtype relationships work as expected:

~~~java
Integer number = 10;
Number wider = number; // Valid: Integer extends Number.
~~~

However, Java generics are **invariant** with respect to type arguments:

~~~java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = integers; // COMPILE ERROR.
~~~

This is an **intentionally non-compiling snippet** and requires importing `java.util.List` and `java.util.ArrayList`. If that assignment were allowed, code using `numbers` could add a `Double`:

~~~java
numbers.add(3.14); // Hypothetical only, if the invalid assignment above were accepted.
~~~

Then, the original list declared as `List<Integer>` would end up containing a `Double`, risking a `ClassCastException` when another part of the code reads an element as `Integer`. The compiler blocks that risk right at the assignment.

Stated in terms of type relationships:

- `Integer` is a subtype of `Number`.
- `List<Integer>` is **not** a subtype of `List<Number>`.
- `List<Integer>` can be used as `List<? extends Number>`.
- `List<Number>` can also be used as `List<? extends Number>`.

The fact that `List<Integer>` is not `List<Number>` is the rule of **invariance**; the fact that an upper-bounded wildcard allows `List<Integer>` to be used where `List<? extends Number>` is required is a type relationship **proven safe by Java**.

## 2. How to Read the Signature `List<? extends T>`

In the signature:

~~~java
static void process(List<? extends Number> source) {
    // Each element can be read as Number.
}
~~~

`?` is a **wildcard** denoting a type argument that is not precisely known. `extends Number` constrains that unknown type to be `Number` or an eligible subtype of `Number`.

As a result, the signature can accept:

~~~java
List<Number> numbers = new ArrayList<>();
List<Integer> integers = new ArrayList<>();
List<Double> doubles = new ArrayList<>();

process(numbers);  // Yes.
process(integers); // Yes.
process(doubles);  // Yes.
~~~

The two snippets above are **illustrative method/call code** that must be placed inside a class and import `java.util.*`. They show a method accepting multiple argument types while maintaining a safe contract.

However, **not just any subtype of `Object` is accepted**: `List<String>` does not match `List<? extends Number>` because `String` is not a subtype of `Number`.

The condition can be read as follows:

> Every element that the list provides must be usable under the contract of `T`.

This condition matters when the method calls APIs of `T`. With `Number`, we can call `doubleValue()`, `intValue()`, etc. on each element regardless of whether the actual list holds `Integer` or `Double`.

## 3. Complete Java 17+ Example: One Method Accepting Both Integers and Floating-Point Numbers

Create the file **`ExtendsNumbersDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ExtendsNumbersDemo {
    private static void printNumbers(List<? extends Number> values) {
        System.out.print("values:");
        for (Number value : values) {
            System.out.print(" " + value);
        }
        System.out.println();
    }

    private static double sum(List<? extends Number> values) {
        double total = 0.0;
        for (Number value : values) {
            total += value.doubleValue();
        }
        return total;
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>(List.of(2, 4, 6));
        List<Double> doubles = new ArrayList<>(List.of(1.5, 2.5));
        List<Number> mixed = new ArrayList<>(List.of(10, 20.5));

        printNumbers(integers);
        printNumbers(doubles);
        printNumbers(mixed);

        System.out.println("sum integers = " + sum(integers));
        System.out.println("sum doubles = " + sum(doubles));
        System.out.println("sum mixed = " + sum(mixed));
    }
}
~~~

Compile and run:

~~~bash
javac ExtendsNumbersDemo.java
java ExtendsNumbersDemo
~~~

Exact stdout:

~~~text
values: 2 4 6
values: 1.5 2.5
values: 10 20.5
sum integers = 12.0
sum doubles = 4.0
sum mixed = 30.5
~~~

The methods `printNumbers` and `sum` only depend on behaviors guaranteed by `Number`, so they do not need to know the concrete subtype of the elements. `doubleValue()` is an API declared in `Number`; at runtime, the corresponding implementation on `Integer` or `Double` is invoked.

The benefit is that **changes on the caller side do not force changes to the method signature**: the same method can work with `List<Integer>`, `List<Double>`, `List<Number>`, and lists of other `Number` subclasses.

## 4. Readable as `T`, Yet Cannot Arbitrarily Write `T`

With an argument of type `List<? extends Number>`, each element read out can be safely used as `Number`, whether the actual list holds `Integer` or `Double`:

~~~java
List<Integer> integers = new ArrayList<>(List.of(1, 2));
List<? extends Number> input = integers;
Number first = input.get(0);
// input.add(3); // Does not compile: the unknown element type could be Double.
~~~

Precisely because of this, the signature accepts lists of **multiple subtypes** without losing type checking. If `List<Number>` were used, the compiler would not allow passing a `List<Integer>` variable directly. In particular, viewing the source through a wildcard **does not create a new list** and does not convert element types at runtime.

Calling `add(null)` can pass type checking, but runtime success still depends on the collection's null/mutability policy; `remove` or `clear` can also be type-valid and mutate the underlying data. Subsequent lessons separate the three issues of **reading via the upper bound**, **prohibiting arbitrary value writes**, and **`null`** so they are not conflated.

## 5. Interpreting `List<? extends T>` When `T` Is a Generic Type Parameter

So far, we have used `Number` as a concrete upper bound. In a generic method, `T` can also be a type parameter:

~~~java
static <T> T first(List<? extends T> source) {
    if (source.isEmpty()) {
        throw new IllegalArgumentException("source must not be empty");
    }
    return source.get(0);
}
~~~

This is **a method that needs to be placed inside a class and import `java.util.List`**. `T` is the type the caller wants to receive, while `? extends T` allows source elements to be `T` or a subtype of `T`.

Example usage with `T` explicitly specified:

~~~java
List<Integer> integers = List.of(10, 20);
List<Double> doubles = List.of(1.5, 2.5);

Number a = MyUtils.<Number>first(integers); // Valid.
Number b = MyUtils.<Number>first(doubles);  // Valid.
~~~

This call snippet only illustrates the signature; assume `first` is `static` inside a `MyUtils` class. The `<Number>` notation is an **explicit type argument** choosing `T = Number`. Then `List<? extends T>` becomes `List<? extends Number>`, so it accepts both `Integer` and `Double` lists.

An equivalent way to write this in a real program is to place `first` and the call in the same class and call `ClassName.<Number>first(...)`.

### A Common Confusion: A Generic Method Accepting `List<T>` Can Also Be Used for Many Types

It is important to distinguish between **`T` being fixed** and **`T` being inferred independently on each call**:

~~~java
static <T> void show(List<T> values) {
    System.out.println(values.size());
}
~~~

The method above can be called in turn with `List<Integer>`, `List<String>`, and `List<Double>`, because the compiler picks an appropriate `T` for **each individual call**:

~~~java
show(List.of(1, 2));     // T can be Integer.
show(List.of("a", "b")); // T can be String.
~~~

These snippets are **illustrative method/call code that must be placed inside a class**. Therefore, the statement "`List<T>` never accepts a list of subtypes" would be an **incorrect** generalization without specifying how `T` is being determined.

The real difference appears when we **need to maintain a known upper bound**, such as a fixed `Number` type, or need to preserve a type relationship across multiple parameters of the same method. When `T` is already `Number`, `List<T>` means `List<Number>`, whereas `List<? extends T>` still accepts `List<Integer>`, `List<Double>`, and `List<Number>`.

## 6. When a Method Needs to Read From a Source and Write to a Destination: Pairing `extends` with `super`

A method that copies elements of type `T` has two opposite roles:

- **Source (producer)** supplies elements usable as `T`: `List<? extends T>`.
- **Destination (consumer)** must be able to receive any element of type `T`: `List<? super T>`.

Appropriate signature:

~~~java
static <T> void copyTo(List<? extends T> source,
                       List<? super T> destination) {
    for (T element : source) {
        destination.add(element);
    }
}
~~~

This is **a method that needs to be placed inside a class and import `java.util.List`**. It is guaranteed safe when the caller supplies compatible types. The easy-to-remember rule is **PECS — Producer Extends, Consumer Super**.

Create the complete program **`GenericCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class GenericCopyDemo {
    static <T> void copyTo(List<? extends T> source,
                           List<? super T> destination) {
        for (T element : source) {
            destination.add(element);
        }
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(1, 2);
        List<Double> doubles = List.of(3.5, 4.5);
        List<Number> numbers = new ArrayList<>();

        copyTo(integers, numbers);
        copyTo(doubles, numbers);

        List<Object> objects = new ArrayList<>();
        copyTo(numbers, objects);

        System.out.println("numbers = " + numbers);
        System.out.println("objects = " + objects);
        System.out.println("integers = " + integers);
    }
}
~~~

Compile and run on Java 17+:

~~~bash
javac GenericCopyDemo.java
java GenericCopyDemo
~~~

Exact stdout:

~~~text
numbers = [1, 2, 3.5, 4.5]
objects = [1, 2, 3.5, 4.5]
integers = [1, 2]
~~~

Type explanation:

1. `integers` is `List<Integer>`. It is a valid source when the destination is `List<Number>`, because `Integer` can be accepted as `Number`.
2. `doubles` is `List<Double>`. It likewise supplies valid `Number` values for the destination.
3. `numbers` is a `List<Number>`, continuing as a valid source for `List<Object>`.
4. There is no invalid assignment from `List<Integer>` to `List<Number>`; the method **iterates over the elements** and adds each value into the other list.
5. `integers` remains unchanged, because the source is not modified.

If you truly only need to "add all elements" to a destination collection, the standard library already provides `Collection.addAll(Collection<? extends E>)`. Similarly, `Collections.copy` has the signature `<T> void copy(List<? super T> dest, List<? extends T> src)`, but its behavior is to **overwrite existing positions** and requires the destination to be at least as long. Do not confuse `Collections.copy` with appending at the end like `addAll`.

## 7. Keeping the Original List While Creating a Wider `List<T>`

Sometimes a downstream method truly requires `List<Number>` because it needs to add `Number` values of different types. In that case, **do not cast** `List<Integer>` to `List<Number>`; create a copy instead:

~~~java
List<Integer> integers = List.of(10, 20);

// List<Number> wrong = integers; // Does not compile.
List<Number> right = new ArrayList<>(integers);
right.add(2.5);

System.out.println(integers); // [10, 20]
System.out.println(right);    // [10, 20, 2.5]
~~~

This is **a code snippet that needs to be placed inside a class and import `java.util.*`**. The constructor `ArrayList(Collection<? extends E>)` accepts a collection whose elements are subtypes of `E`. The target type helps infer `E = Number`. The copy holds references to the elements, while the list structure is independent: adding to `right` does not mutate `integers`.

Clearly distinguish the two needs:

- **Only need to inspect or process elements as `T`**: accept `List<? extends T>`, without forcing the caller to copy.
- **Need to own a collection capable of holding multiple subtypes of `T` and frequently adding values**: create/accept a `List<T>` of the exact type and copy the source when needed.

Wildcards do not change the declared type of the underlying collection.

## 8. When the Upper Bound Is an Interface or a Custom Class

`extends` in a wildcard is syntax that applies to **both classes and interfaces**, not just classes. For example:

~~~java
static int totalLength(List<? extends CharSequence> texts) {
    int total = 0;
    for (CharSequence text : texts) {
        total += text.length();
    }
    return total;
}
~~~

This is **an illustrative method that needs to be placed inside a class** and import `java.util.List`. Both `String` and `StringBuilder` implement `CharSequence`, so their corresponding lists are valid inputs:

~~~java
int x = totalLength(List.of("Hi", "Java"));
int y = totalLength(List.of(new StringBuilder("AB"),
                            new StringBuilder("C")));
~~~

`x` equals `6` and `y` equals `3`. The elements have different runtime classes, yet all provide the `length()` method declared by `CharSequence`.

Here, `List<? extends CharSequence>` does **not** promise that the list contains the exact type `CharSequence`. It promises that the list contains some specific type conforming to `CharSequence`. Thus the method is allowed to call `length()`, but is not allowed to add a new string through the wildcard parameter.

Wildcards can be used with custom classes:

~~~java
class Animal {
    String name() { return "animal"; }
}
class Dog extends Animal {
    @Override String name() { return "dog"; }
}

static void printAnimals(List<? extends Animal> animals) {
    for (Animal animal : animals) {
        System.out.println(animal.name());
    }
}
~~~

These are **illustrative declarations**. `printAnimals` accepts `List<Animal>`, `List<Dog>`, or a list of another subclass of `Animal`. If you need to call a method that only exists on `Dog`, you must narrow the type safely, because the general contract only knows `Animal`.

## 9. Wildcard Capture: Why Can You Sometimes Write Back the Same Type?

With `List<? extends T>`, you cannot insert an arbitrary `T` element into the list because the actual subtype is unknown. However, if the element is retrieved from **that very same list**, a generic method can capture the unknown type (wildcard capture) and reuse it.

Create the file **`CaptureSwapDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CaptureSwapDemo {
    static void swapFirstTwo(List<? extends Number> values) {
        if (values.size() >= 2) {
            swapCaptured(values, 0, 1);
        }
    }

    private static <E> void swapCaptured(List<E> list, int i, int j) {
        E previous = list.get(i);
        list.set(i, list.get(j));
        list.set(j, previous);
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>(List.of(1, 2, 3));
        List<Double> doubles = new ArrayList<>(List.of(1.5, 2.5));

        swapFirstTwo(integers);
        swapFirstTwo(doubles);

        System.out.println(integers);
        System.out.println(doubles);
    }
}
~~~

~~~bash
javac CaptureSwapDemo.java
java CaptureSwapDemo
~~~

Exact stdout:

~~~text
[2, 1, 3]
[2.5, 1.5]
~~~

At the call site `swapCaptured(values, 0, 1)`, the compiler captures the wildcard's unknown subtype into a consistent type parameter `E`. Two elements are swapped **between positions within the same list**, so no element of a different class is added.

This shows that `extends` does not mean "forbid all modifications." It forbids operations that **cannot be proven type-safe**; a generic helper can prove that writing back the very elements of the same type is permitted.

## 10. Distinguishing `List<T>`, `List<? extends T>`, and `List<? super T>`

When `T` is fixed (for example `T = Number`), we have:

| Signature | Can accept | Static read type | Can add `T`? | Common role |
| --- | --- | --- | --- | --- |
| `List<T>` | List with exact type argument `T` | `T` | Yes | Both read and write exact `T` |
| `List<? extends T>` | List of `T` or subtype of `T` | `T` | No (except `null`) | Data source |
| `List<? super T>` | List of `T` or supertype of `T` | `Object` | Yes | Data destination |
| `List<?>` | List of any type | `Object` | No (except `null`) | Read/observe without needing to know the type |

For example, `List<? extends Number>` does not accept `List<Object>` because `Object` is **not a subtype** of `Number`. Conversely, `List<? super Number>` accepts `List<Object>` but **does not accept `List<Integer>`**, because `Integer` is not a supertype of `Number`.

These are two opposite directions of using the subtype relation. You should choose the wildcard strictly according to the role of the data in the API.

## 11. Common Mistakes When Writing APIs That Accept Lists of Subtypes

### Mistake 1 — Using `List<Number>` for a method that only reads all kinds of numbers

~~~java
static double total(List<Number> values) {
    return values.stream().mapToDouble(Number::doubleValue).sum();
}

// total(List.of(1, 2)); // Can fail when the input already has type List<Integer>.
~~~

This snippet is **illustrative method and example code**, not a standalone program. With a fixed variable `List<Integer> integers`, `total(integers)` definitely fails to compile. When the input is the expression `List.of(1, 2)` without a fixed target type, **target typing** may cause the compiler to infer `Number`, so that expression alone should not be used to demonstrate the error. A clear way to verify is:

~~~java
List<Integer> integers = List.of(1, 2);
// total(integers); // COMPILE ERROR.
~~~

If `total` only reads, the appropriate signature is usually `List<? extends Number>`.

### Mistake 2 — Assuming `? extends T` allows adding an arbitrary subtype

~~~java
static void addPi(List<? extends Number> numbers) {
    // numbers.add(3.14); // COMPILE ERROR.
}
~~~

A passed-in list could be `List<Integer>`, so adding a `Double` is not guaranteed safe.

### Mistake 3 — Assuming a wildcard turns element types into `T` at runtime

`List<? extends Number>` can still point to a `List<Integer>`. Wildcards do not copy, do not change the object, and do not cast each element. They change **which operations the compiler allows through the reference**.

### Mistake 4 — Unchecked casts to "make the assignment work"

~~~java
List<Integer> integers = new ArrayList<>();
@SuppressWarnings("unchecked")
List<Number> forged = (List<Number>) (List<?>) integers;
forged.add(3.14); // Risk of heap pollution.
~~~

This is **code illustrating a hazard**, not a conversion technique. `@SuppressWarnings("unchecked")` merely hides the warning; it does not verify that the list can hold a `Double`. Another place reading elements as `Integer` may encounter a `ClassCastException`.

### Mistake 5 — Forgetting to distinguish generic constraints from collection mutability

`ArrayList<Integer>` is a mutable collection yet can still be viewed under the type `List<? extends Number>`. Conversely, `List.of(1, 2)` is unmodifiable whether the reference is declared as `List<Integer>` or `List<? extends Number>`. The write restriction imposed by a wildcard and whether a collection supports modification are **two independent rules**.

### Mistake 6 — Using a wildcard when the API needs to return the caller's exact subtype

If you need to return an exact element of the same type as the input list, a generic method can be clearer:

~~~java
static <E> E firstExact(List<E> values) {
    return values.get(0);
}
~~~

This is **an illustrative method that needs to be placed inside a class**. When the input has type `List<Dog>`, the compiler can infer `E = Dog` and the return type is `Dog`. For a method that only needs to compute via the `Animal` API, `List<? extends Animal>` can be sufficient and simpler.

## 12. Self-Check Exercises

Suppose the following lines have been declared inside a method with `import java.util.*`:

~~~java
List<Integer> ints = new ArrayList<>(List.of(1, 2));
List<Double> doubles = new ArrayList<>(List.of(2.5, 3.5));
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();
List<? extends Number> input = ints;
~~~

Determine whether each statement compiles or not:

| Statement | Compiles? | Why? |
| --- | --- | --- |
| `List<Number> x = ints;` | No | Generic invariance |
| `List<? extends Number> x = ints;` | Yes | `Integer` is a subtype of `Number` |
| `List<? extends Number> x = doubles;` | Yes | `Double` is a subtype of `Number` |
| `List<? extends Number> x = objects;` | No | `Object` is not a subtype of `Number` |
| `Number value = input.get(0);` | Yes | Element is guaranteed to be `Number` |
| `Integer value = input.get(0);` | No | Subtype is not guaranteed to be `Integer` |
| `input.add(3);` | No | Unknown element type |
| `input.add(null);` | Yes | `null` is compatible with any reference type; runtime may reject |
| `input.remove(0);` | Yes | Does not require supplying an element of unknown type |
| `numbers.addAll(ints);` | Yes | `addAll` accepts `Collection<? extends Number>` |
| `objects.addAll(numbers);` | Yes | Every `Number` is also an `Object` |

The examples in the table are treated as **independent statements**; those marked "No" are intentionally mistyped and must not be copied into a program intended to compile cleanly.

## 13. Guiding Rule

When accepting a list whose element type is `T` or subtypes of `T`, determine what the method will **do with the elements**. If it primarily **reads** them as `T` and uses the API of `T`, choose `List<? extends T>`. If it needs to **write** `T` elements into a collection supplied by the caller, use `List<? super T>` for the destination. If it needs both reading and writing of a single exact type or needs to return a concrete subtype, consider a generic method with `<T>`. If you need to mix different subtypes in a new list, create an appropriate `List<T>` and copy the elements.

**`List<? extends T>` solves the problem of accepting `List<T>` and lists of subtypes without sacrificing type safety.** The method trades the ability to add new values through the wildcard view for flexible reading, thereby preserving the contract of the original list.