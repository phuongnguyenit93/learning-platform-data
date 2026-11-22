# What Is a Raw Type and Its Role in Pre-Generics Java Code

## Objectives

A **raw type** is the use of a generic type **without providing type arguments**, for example writing `List` instead of `List<String>` or `List<?>`. Understanding raw types helps you read and integrate libraries, classes, and methods written before Java supported generics, while also recognizing places where the compiler cannot fully verify type safety.

After this lesson, you can:

- Distinguish between generic types, parameterized types, and raw types using practical Java examples.
- Explain why pre-Java 5 code commonly used `List`, `Object`, and casts, and why Java still supports that style.
- Understand the role of **type erasure**, **backward compatibility**, and **migration compatibility** in the existence of raw types.
- Correctly read `[rawtypes]` and `[unchecked]` warnings, and identify when heap pollution and `ClassCastException` can occur.
- Choose among `List<?>`, `List<Object>`, `List<T>`, or an element-checking adapter instead of a raw type.
- Know how to isolate exposure to legacy APIs and gradually migrate old code to generics without creating a false sense of safety.

## 1. Recognizing Raw Types in Source Code

With the `List<E>` interface and the `ArrayList<E>` class in `java.util`:

```java
List<String> names = new ArrayList<>(); // Parameterized type.
List<?> unknown = names;                // Parameterized type with wildcard.
List raw = names;                       // Raw type.
```

The snippets above illustrate declarations in a context with `java.util.List` and `java.util.ArrayList` imported. The differences are:

| Syntax | Meaning at compile time | Is it a raw type? |
| --- | --- | --- |
| `List<String>` | List declared to have elements of type `String` | No |
| `List<Integer>` | List declared to have elements of type `Integer` | No |
| `List<Object>` | List declared to have elements of type `Object` | No |
| `List<?>` | List with an unknown specific element type | No |
| `List<E>` inside a generic declaration | Has type parameter `E` | No |
| `List` | Use of a generic type omitting type arguments | **Yes** |
| `ArrayList` | Use of a generic class omitting type arguments | **Yes** |

A raw type appears when a generic class/interface name is used **without the type parameter section**. For example:

```java
class Box<T> {
    private T value;
    Box(T value) { this.value = value; }
    T get() { return value; }
}
```

With the class above, `Box<String>` is a parameterized type; writing only `Box` as a variable or parameter type is using **raw `Box`**.

One common point of confusion: `Object` itself is **not** a raw type. It is an ordinary type that declares no generic parameters. `List<Object>` is also **not a raw type** because the type argument `Object` is explicitly specified.

## 2. Why Do Raw Types Exist in Java's History?

Java had `java.util.List` and collections before the language had generics. Before **Java 5 (2004)**, code typically looked like this:

```java
import java.util.ArrayList;
import java.util.List;

class OldStyleExample {
    public static void main(String[] args) {
        List names = new ArrayList();
        names.add("Lan");
        names.add("Minh");

        String first = (String) names.get(0);
        System.out.println(first); // Lan
    }
}
```

Today this program still compiles with modern JDKs; when `-Xlint:rawtypes` and `-Xlint:unchecked` are enabled, the compiler warns about uses of raw generics or unchecked operations. This is **historical-style code**, not a case where pre-Java 5 programmers already had generic `List<E>` and intentionally omitted the type arguments.

Because generics did not exist yet, `List` stored references as `Object`. `get(int)` returned `Object`, and the caller had to cast manually to use it as a `String`:

```java
String first = (String) names.get(0);
```

Problems with the old style:

- There was no language-level guarantee that the list contained only `String` values.
- An `Integer` could be added to a list of strings without the compiler rejecting it, because the specific element type was not described in the type.
- An invalid cast was only detected at runtime and could throw `ClassCastException`.
- Every read site had to cast proactively; API changes and maintenance were more complicated.

Since Java 5, generics allow specifying `List<String>` so the compiler can check element additions and retrievals:

```java
List<String> names = new ArrayList<>();
names.add("Lan");
// names.add(123); // Does not compile.
String first = names.get(0); // No need to write a cast manually in source.
```

Several changes create this improvement: the compiler knows that calls through `List<String>` have element type `String`, supports type inference, and reports warnings/errors at compile time. The compiler may still insert casts into bytecode under the type erasure mechanism.

Raw types continue to exist because Java needed **compatibility with legacy code and libraries** written before generics, allowing old code to continue using collection classes that were later generalized.

## 3. How Do Raw Types Relate to Type Erasure?

Java generics mainly check types at **compile time**. During compilation, type parameters are erased from JVM descriptors in the appropriate places. For an unbounded type parameter:

```java
class Box<T> {
    private T value;
    void set(T value) { this.value = value; }
    T get() { return value; }
}
```

`T` has erasure `Object`. Typical descriptors are:

| Source member | JVM descriptor |
| --- | --- |
| Field `T value` | `Ljava/lang/Object;` |
| `void set(T value)` | `(Ljava/lang/Object;)V` |
| `T get()` | `()Ljava/lang/Object;` |
| `List<E>.add(E)` with unbounded `E` | `(Ljava/lang/Object;)Z` |
| `List<E>.get(int)` | `(I)Ljava/lang/Object;` |

This allows code using pre-generics API versions to continue linking against compatible bytecode. For example, when the collections library added generic metadata `List<E>` in source code, underlying descriptors like `get(int):Object` did not suddenly turn into `get(int):String` per call site. There are no separate runtime classes `ArrayList<String>` and `ArrayList<Integer>` for each generic argument.

**However, raw types and erasure are not the same concept.**

- **Type erasure** is how the compiler represents and translates generics into bytecode.
- **A raw type** is how a programmer **writes a reference to a generic type without type arguments** in source code.
- A generic method used properly with `List<String>` also undergoes erasure; erasure does not mean the code uses a raw type.
- Raw types drop type-checking information in source code, so they can lead to unchecked warnings.

Compiling generics via erasure enables runtime compatibility with old code; raw types are the syntactic bridge for interacting with legacy-style source code and APIs.

## 4. Full Example: Raw Types Can Corrupt Typed Data

Create file **`RawTypeDemo.java`**, Java 17 or later:

```java
import java.util.ArrayList;
import java.util.List;

public class RawTypeDemo {
    static class Box<T> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        void set(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    // Pre-Java 5 style API: List without a type argument.
    static void legacyAppend(List list, Object value) {
        list.add(value);
    }

    public static void main(String[] args) {
        List<String> words = new ArrayList<>();
        words.add("Java");
        legacyAppend(words, 42);
        System.out.println("list data: " + words);

        try {
            String second = words.get(1);
            System.out.println(second);
        } catch (ClassCastException ex) {
            System.out.println("list read: " + ex.getClass().getSimpleName());
        }

        Box<String> box = new Box<>("safe");
        Box rawBox = box;
        rawBox.set(123);
        try {
            String value = box.get();
            System.out.println(value);
        } catch (ClassCastException ex) {
            System.out.println("box read: " + ex.getClass().getSimpleName());
        }
    }
}
```

Run from the directory containing the file:

```bash
javac -Xlint:rawtypes -Xlint:unchecked RawTypeDemo.java
java RawTypeDemo
```

Program stdout **verified with JDK**:

```text
list data: [Java, 42]
list read: ClassCastException
box read: ClassCastException
```

The compiler also emits warnings such as `[rawtypes] found raw type: List` and `[unchecked] unchecked call to add(E)` or `set(T)`. The exact wording of warnings depends on the compiler version and line numbers; this is not the stdout of `java RawTypeDemo`.

### Exact Sequence of Events

1. `words` is declared as `List<String>`, so normal calls like `words.add(42)` **do not compile**.
2. `legacyAppend` takes raw `List`; when `words` is passed in, the method receives the same list object. `list.add(42)` is not checked as a `List<String>` operation, and the compiler emits an unchecked warning in the method body.
3. The actual contents of the list are now `[Java, 42]`, even though the `words` variable is still declared as `List<String>`. This state where data no longer matches its generic promise is called **heap pollution**.
4. At `String second = words.get(1)`, the compiler relies on `List<String>` and may emit `checkcast String`. The actual value is an `Integer`, causing `ClassCastException`.
5. With `Box<String>`, assigning `Box rawBox = box` does not create a second box: both variables reference the same instance. Calling `rawBox.set(123)` pollutes the data in the box. Reading `String value = box.get()` fails on the cast.

**Key takeaway:** raw types still run and are binary-compatible, but they lose part of compile-time type-checking guarantees. Failures can appear **late at the read site**, far from where the wrong-typed data was inserted.

## 5. Reading the Two Compiler Warning Types Correctly

Enable both warning categories when inspecting legacy code:

```bash
javac -Xlint:rawtypes -Xlint:unchecked RawTypeDemo.java
```

### `[rawtypes]`: using a generic name without a type argument

Example:

```java
List list = new ArrayList();
Box box = new Box("X");
```

These two lines use raw `List`, raw `ArrayList`, and raw `Box`. With `-Xlint:rawtypes`, the compiler warns about missing type parameters. The `rawtypes` warning helps pinpoint places where the API can be improved to express data more clearly.

### `[unchecked]`: an operation or conversion that the compiler cannot fully verify

Example:

```java
List raw = new ArrayList();
raw.add("A"); // Unchecked call to add(E) via raw List.

List<String> words = raw; // Unchecked conversion from raw List.
```

At the assignment site, the compiler cannot verify that all elements in the raw list are actually `String`. The assignment compiles with an unchecked warning, creating conditions that can lead to `ClassCastException` when the data is retrieved.

Comparison table:

| Warning | What does it indicate? | Example |
| --- | --- | --- |
| `rawtypes` | A generic type name is used as a raw type | `List list` |
| `unchecked` | A generic-related call/assignment/cast is not fully checked | `raw.add(1)`, `List<String> x = raw` |
| Compile error | The compiler proves a typed call is incompatible | `List<String> x; x.add(1)` |
| Runtime error | Actual data does not match the cast/assumption | `ClassCastException` on read |

Both warnings can appear together in different places; they are **not synonymous**. A raw declaration does not necessarily cause an immediate runtime error, and an unchecked cast can appear even without a raw declaration nearby. Suppressing warnings does not make the program safer.

`@SuppressWarnings({"rawtypes", "unchecked"})` is sometimes necessary in a manually verified legacy adapter, but you should not scatter that annotation throughout code just to silence warnings without proving data correctness.

## 6. Comparing Raw `List`, `List<?>`, `List<Object>`, and `List<String>`

The important difference is not just syntax:

| Variable type | Can be read as | Can add `String`? | Can add `Integer`? |
| --- | --- | --- | --- |
| `List<String>` | `String` | Yes | No |
| `List<Object>` | `Object` | Yes | Yes |
| `List<?>` | `Object` | No, except `null` | No, except `null` |
| Raw `List` | `Object` | Yes, with unchecked warning | Yes, with unchecked warning |

The table assumes a modifiable list; with `List.of(...)` or unmodifiable lists, any mutation call can throw `UnsupportedOperationException` at runtime even if allowed by the Java type.

### Why is `List<?>` better than raw `List` when you only need to read?

```java
static void printElements(List<?> items) {
    for (Object item : items) {
        System.out.println(item);
    }
}
```

This is a usable method when placed inside a class with `java.util.List` imported. It accepts `List<String>`, `List<Integer>`, and many other list types, while **preventing arbitrary objects from being inserted into the list when the element type is unknown**.

In contrast, `static void printElements(List items)` introduces a raw type into the API and opens the door to write calls with unchecked warnings. If you only need to observe elements, `List<?>` expresses the intent more safely and accurately.

### Why not always replace raw `List` with `List<Object>`?

Because `List<String>` **is not a subtype of** `List<Object>`. Java generics are invariant; consider the assignment:

```java
List<String> names = new ArrayList<>();
// List<Object> all = names; // Compile error.
List<?> any = names;         // Valid.
```

If `List<String>` were treated as `List<Object>`, other code could add an `Integer` through the `all` variable, breaking the promise of `names`. For read-only APIs, `List<?>` is usually a much more compatible replacement for raw types than `List<Object>`.

If the **actual business requirement** is a list that can hold multiple kinds of values, `List<Object>` has its own purpose; it is not an arbitrary drop-in replacement for every `List<String>`.

## 7. The Legitimate Role of Raw Types When Interfacing with Legacy APIs

Raw types do not exist merely because programmers forget syntax. They are also part of the transition strategy between the **pre-generics** and **post-generics** Java worlds.

Common situations:

1. **Legacy source code** declares `List`, `Map`, `Class`, or custom containers like `Box` without type arguments.
2. **Legacy APIs** accept/return collections without element type information, because their API contracts were written before generics existed.
3. **Legacy binary libraries** still need to link with new programs. Type erasure keeps descriptors compatible in cases designed for this purpose.
4. **Incremental upgrades**: you can replace raw types one site at a time with generic forms, using adapters at boundaries instead of rewriting the entire application all at once.

However, raw types should be viewed as **controlled contact points**, not as a way to design new generic APIs. When a library already provides a generic form, prefer parameterizing the type according to the actual data.

An upgrade rule of thumb: do not hastily declare that a raw `List` contains `String` just because current test data happens to look like strings. Check the return contract of the library or validate each element before exposing a trusted `List<String>`.

## 8. Creating a Checked Read Boundary for Legacy APIs

If legacy code returns a raw `List` and modern code wants to ensure all elements are strings, **do not cast the whole list to `List<String>`**. Pass the source into an API accepting `List<?>` and check each element:

```java
static java.util.List<String> validatedNames(java.util.List<?> source) {
    java.util.List<String> result = new java.util.ArrayList<>();
    for (Object item : source) {
        result.add(String.class.cast(item));
    }
    return java.util.List.copyOf(result);
}
```

This is an **illustrative method** to place inside a class; the lesson already has a standalone program `RawTypeDemo.java` in section 4 to observe raw writes and late failures. In this helper, `String.class.cast` verifies the runtime class of each element; `List.copyOf` rejects `null` and creates a list that cannot be modified via ordinary APIs. If you want to allow `null`, you must define that contract and use a different result container.

This verification boundary is useful when **a legacy interface cannot yet be changed**, yet the modern side does not want unchecked casts spreading outward. A production adapter also needs to clarify index reporting on invalid data, ownership/mutability of the source list, and whether copying is truly sufficient. This lesson only introduces the strategy; multi-layer migration plans, legacy caller handling, and binary compatibility must be designed at the system level.

## 9. How Raw Types Differ from Wildcards in Compile-Time Checks

This part is often confused:

```java
List<String> strings = new ArrayList<>();
List raw = strings;       // Raw type.
List<?> unknown = strings;
```

When writing:

```java
raw.add(100);
```

The compiler may allow the call but emit an **unchecked** warning: the raw type drops the link to the `String` type argument on that reference.

When writing:

```java
// unknown.add(100); // Does not compile.
// unknown.add("X"); // Does not compile.
```

The compiler **does not know** what concrete type the wildcard represents, so it prohibits writing any non-`null` object. This lets `List<?>` preserve type safety when code only needs to read.

Both `raw` and `unknown` reference **the exact same `strings` list**, without creating a copy. The difference lies in the **compile-time contract** of the two reference types.

Another example to avoid:

```java
// if (obj instanceof List<String>) { } // Invalid because the type argument is not reifiable.
if (obj instanceof List<?>) {
    // Knows obj is a List, cannot conclude the elements inside are String.
}
```

This check assumes `Object obj` is already in scope. `List<?>` is a case that can be checked with `instanceof`, whereas `List<String>` is not a specialized runtime class that can be checked directly.

## 10. A Raw Type Does Not Erase All Type Bounds

There is an important exception to reason about accurately: if a type parameter **has an upper bound**, erasure typically uses that upper bound, not always `Object`.

Illustrative example:

```java
class NumberHolder<T extends Number> {
    void accept(T number) {
        System.out.println(number);
    }
}
```

After erasure, `accept(T)` has a descriptor taking `Number`. If you use:

```java
NumberHolder rawHolder = new NumberHolder();
rawHolder.accept(Integer.valueOf(7)); // Valid.
// rawHolder.accept("text");           // Still a compile error.
```

This snippet needs to be placed inside an appropriate class/method to run; it focuses on explaining the signature. Even though `rawHolder` is a raw type, the method takes `Number` after erasure, so a `String` cannot be passed directly. You cannot conclude that a raw type allows **any value type** in **every method**.

If code uses `Box<T extends Number>`, what a raw type can do must be analyzed based on the bound and the actual erased signature. Raw types reduce generic information, but constraints still represented in the erased signature remain in effect.

## 11. Migration Guidance When Encountering Raw APIs

In a long-lived codebase, a raw type may appear in a declaration, in a method signature, or be passed to other callers. Start from **intended usage** rather than replacing every `List` with `List<Object>`:

| Context | Preferred action | Why |
| --- | --- | --- |
| You own the data and know for sure it holds only `String` | Update creation sites, write sites, and signatures to `List<String>` | Compiler protects the invariant from the source |
| Element type is unknown and you only need to observe | Accept `List<?>` | Prevents observing code from adding arbitrary non-null values |
| Legacy API returns raw `List`, application needs `List<String>` | Use a helper that checks each element and copies | Avoids turning an unchecked cast into a false promise |
| Element type cannot yet be proven | Keep `List<?>` and handle elements as `Object` | Honest with the information currently available |

Enable `javac -Xlint:rawtypes,unchecked` to locate raw declarations and unchecked operations. Compiling cleanly with warnings does not prove data is safe. If a raw boundary must remain, isolate it and write tests with wrong-typed data before exposing a typed API.

**Connection point:** Distinguishing conversion directions between raw and parameterized types, how type erasure affects members, and caller/callee migration plans are the next steps; the foundational definition of a raw type alone does not determine the full migration strategy.

## 12. Common Pitfalls

### Confusing raw `List` with `List<Object>`

`List<Object>` has an explicit type argument, can hold many kinds of objects, and cannot directly receive a `List<String>` reference due to invariance. Raw `List` drops generic parameter checks and can trigger warnings.

### Assuming "compiles" means "safe"

An unchecked warning means the compiler **cannot prove** the operation is safe. Passing with sample test data does not guarantee safety when inputs change.

### Reading `List<String>` after a raw source added a wrong value

The compiler still treats `words.get(i)` as having source type `String`; when the compiler-inserted cast checks an actual `Integer` value, a failure can occur. That is why the exception is usually thrown at the **read/cast site**, not necessarily where the wrong data was added.

### Treating `List<?>` as raw because it does not name a concrete type

`List<?>` is still a **parameterized type**, carrying a wildcard constraint and restricting write operations to maintain safety. It is the right choice when an API only needs to inspect the contents of a list of unknown type.

### Casting `Object` or `Class` without verification

`Object` and raw `Class` do not automatically provide information about all generic arguments. To restore data types at a boundary, you need a reliable contract, metadata, or verification operation.

### Using `@SuppressWarnings` to silence all warnings across a project

Broad suppression can hide new unchecked calls, making bugs harder to trace. Keep raw types inside boundary modules when unavoidable, and strive to keep most code using parameterized types.

### Forgetting that a raw collection can still be unmodifiable

`List raw = List.of("A")` is a raw reference to a list that does not support modification. Even if the compiler allows `raw.add("B")` with an unchecked warning, the call can still throw `UnsupportedOperationException`. Raw types do not change the mutability restrictions of the underlying object.

## 13. Self-Check Exercises

**Exercise 1 — Type classification.** Among `List`, `List<?>`, `List<Object>`, and `List<String>`, which one is a raw type?

**Answer:** only `List` without type arguments.

**Exercise 2 — Predicting warnings.** With `List raw = new ArrayList(); raw.add(1);`, what do `-Xlint:rawtypes` and `-Xlint:unchecked` mean?

**Answer:** `rawtypes` detects places where generic arguments are omitted; `unchecked` warns that calling `add(E)` through a raw reference is not checked like a typed call.

**Exercise 3 — Analyzing late failure.**

```java
List<String> words = new ArrayList<>();
List raw = words;
raw.add(99);
String s = words.get(0);
```

This snippet must be placed in a method with collection imports. Why does the error happen on the last line even though `add` already ran?

**Answer:** raw `List` allows an `Integer` value to enter the list object with a warning; at `words.get(0)`, the typed code expects a `String` and the cast fails.

**Exercise 4 — Choosing a signature.** A method only iterates and prints every element of a list regardless of type; should it accept `List`, `List<Object>`, or `List<?>`?

**Answer:** `List<?>`, because it accepts different typed lists and does not allow arbitrary element additions.

**Exercise 5 — Distinguishing erasure.** Why does `List<String>` still undergo erasure even though it is not a raw type?

**Answer:** erasure is the general compilation mechanism for generics; a raw type is specifically a reference syntax in Java source that omits generic arguments.

**Exercise 6 — Upgrading a legacy API.** A legacy library returns a `List` that may contain both `String` and `Integer`. You need an API returning `List<String>`. Should you cast the whole list to `List<String>`?

**Answer:** you cannot treat that unchecked cast as proof of safety. You need to verify each element, reject invalid elements, build a new typed collection, or expose the actual data type accurately if safety cannot be guaranteed.

**Exercise 7 — Do raw types still have bounds?** With `NumberHolder<T extends Number>`, is calling `rawHolder.accept("hello")` valid?

**Answer:** no. The erasure of `T` is `Number`, so `String` still does not match a signature accepting `Number`.

## Practical Conclusion

**A raw type is the name of a generic class or interface used without providing type arguments**, such as `List` or `Box`. It exists mainly so legacy Java APIs and programs can continue coexisting with generics added in Java 5. **Type erasure** supports binary compatibility, but using raw types in source code weakens compile-time type safety checks and can open the door to **unchecked calls, heap pollution, and `ClassCastException`**.

When writing modern Java, declare concrete types like `List<String>` when the data is known; use `List<?>` when you only need to read a list of unknown type; use `List<Object>` when you genuinely need to store multiple kinds of objects; and confine raw types to integration boundaries with legacy code. **Keeping compiler warnings useful, validating data at boundaries, and avoiding arbitrary unchecked casts** is how you leverage legacy compatibility while preserving your application's type safety.
