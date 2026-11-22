# Heap Pollution and Parameterized-Type Variables

## Objectives

In Java Generics, a `List<String>` variable promises the compiler that when reading an element, the program can treat that element as a `String`. However, if another call path uses a **raw type**, an **unchecked conversion/cast**, or unsafe operations on **generic varargs**, the underlying data structure may no longer fulfill that promise. That situation is called **heap pollution**.

This lesson belongs to the **Generic Varargs** topic in Java Core — Generics. After studying it, you will be able to:

- Explain heap pollution in terms of the relationship between a parameterized type in source code and the actual object on the heap.
- Distinguish **heap pollution**, **unchecked warnings**, and **`ClassCastException`**; they are related but not synonymous.
- Demonstrate two sources of pollution: raw `List` and **varargs arrays** `List<String>...`.
- Explain why the assignment `Object[] alias = groups; alias[0] = List.of(99);` can pass the runtime array store check while reading a `String` fails.
- Use `-Xlint:rawtypes`, `-Xlint:unchecked`, and `-Xlint:varargs` to read useful warnings.
- Apply `@SafeVarargs` responsibly; understand the annotation's limitations and choose non-varargs collections or generic methods when appropriate.
- Wrap untrusted data with an adapter that **checks each element** instead of performing an unchecked cast on the entire collection.

All complete programs run on **Java 17 or later**. Snippets with comments indicating compile errors are for analysis only; do not copy them as standalone programs with the comments removed.

## 1. What Exactly Is Heap Pollution?

A standard phrasing: **heap pollution occurs when a variable of a parameterized type refers to an object that is not compatible with that parameterized type**. This is not a syntax error or a dedicated exception named `HeapPollutionException`: it is a **type-unsafe state** that may not fail immediately when created.

Example:

```java
import java.util.ArrayList;
import java.util.List;

class Illustration {
    static void demonstrate() {
        List<String> names = new ArrayList<>();
        names.add("Java");

        List raw = names;   // Both variables point to the same ArrayList.
        raw.add(42);       // Unchecked call.

        // names is declared as List<String>, but contains Integer.
        // String second = names.get(1); // ClassCastException at runtime.
    }
}
```

The snippet above is an illustrative class without `main`; a complete program with verified output is in section 4.

Why doesn't the compiler reject `raw.add(42)` immediately? The source type of `raw` is **raw `List`**, which omits the type argument `String`. The `add` method is therefore invoked without the compile-time guarantee for `List<String>`; the compiler emits an unchecked warning, but does not know that `raw` is violating a generic contract of another variable.

The `raw.add(42)` operation does not necessarily throw an exception, because the runtime class `ArrayList` does not have a dedicated version for `ArrayList<String>`. The error may be detected at a subsequent **read/cast** site: when the compiler expects `String` but the actual value is `Integer`.

### Three Concepts Not to Equate

| Concept | Refers to | Example |
| --- | --- | --- |
| **Heap pollution** | An object trusted by a generic reference no longer matches its type parameter | `List<String>` containing an `Integer` |
| **Unchecked warning** | The compiler cannot verify full type soundness of a call/conversion | `raw.add(42)`, unsafe generic varargs |
| **`ClassCastException`** | A specific runtime cast fails | Reading an `Integer` from `List<String>` and using it as `String` |

An unchecked warning **only indicates risk**; it does not prove that heap pollution has definitely occurred. Conversely, if code intentionally bypasses type checks, heap pollution can exist before any exception is thrown. Never use "runs without error" as proof that a data path is safe.

## 2. Generics Type Checking and Type Erasure

`List<E>` is defined with type parameter `E`; in `List<String>`, the compiler uses `String` to type-check calls. Example:

```java
List<String> messages = new ArrayList<>();
messages.add("Hello");
// messages.add(3); // Compile-time error if called through a typed reference.
String first = messages.get(0);
```

This snippet assumes `import java.util.List;` and `import java.util.ArrayList;`.

The type argument `String` **does not create a separate runtime class `List<String>`**. Java generics perform **type erasure**; a call like `List.get(int)` uses a descriptor returning `Object`, while the compiler can insert a `checkcast String` at the site where the result is read as `String`.

Do not misunderstand type erasure as turning a `String` object into a different `Object`. The actual object still has runtime class `String`; only the information about the **container's type argument** is not represented by the JVM as a specialized runtime class.

The consequence related to heap pollution: at runtime, `ArrayList` cannot automatically enforce a "store check for `String`" on every `add` call. If data enters through a raw/unchecked path, an invalid element can slip in, and failure occurs later when typed code reads it out.

## 3. Generic Varargs: Where Arrays Meet Type Erasure

In Java, the declaration:

```java
static void show(List<String>... groups) {
    // ...
}
```

uses **varargs**: at runtime, varargs arguments are passed via an **array**. However, the element type `List<String>` is **non-reifiable**: the JVM has no dedicated runtime class for `List<String>`, and `new List<String>[n]` cannot be created directly in Java source code.

Key points:

- `List<String>...` is valid in a varargs signature, though the compiler may emit a warning about **possible heap pollution**.
- The runtime array holds `List` elements and cannot verify the `String` type argument of each list.
- The varargs array can be viewed through a broader `Object[]` reference due to array covariance.
- Writing a `List<Integer>` into an array slot through `Object[]` may **not** throw `ArrayStoreException`, because the runtime component type is still `List`.
- Reading an element while expecting `String` can throw `ClassCastException`.

Compare two cases:

```java
String[] texts = {"A"};
Object[] textAlias = texts;
// textAlias[0] = 99; // Compiles, but throws ArrayStoreException at runtime.
```

and:

```java
// Inside a method receiving List<String>... groups:
Object[] groupsAlias = groups;
groupsAlias[0] = List.of(99); // The JVM still sees this as a List.
```

The second snippet **pollutes an array whose source type is `List<String>[]`**. The runtime store check only verifies whether the inserted object is a `List`; it cannot check every element inside against the `String` type argument. Thus, the assignment is not blocked the way `String[]` blocks `Integer`.

That is why Java restricts **generic array creation**, warns on **non-reifiable varargs**, and provides `@SafeVarargs` for declarations that can be proven safe.

## 4. Program A — Seeing Heap Pollution via Raw Types and Generic Varargs

Create the file **`HeapPollutionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class HeapPollutionDemo {
    static List<String>[] pollute(List<String>... groups) {
        Object[] alias = groups;
        alias[0] = List.of(99);
        return groups;
    }

    public static void main(String[] args) {
        List<String> words = new ArrayList<>(List.of("Java"));
        List raw = words;
        raw.add(42);
        System.out.println("raw contents: " + words);

        try {
            String item = words.get(1);
            System.out.println(item);
        } catch (ClassCastException ex) {
            System.out.println("raw read failure: "
                    + ex.getClass().getSimpleName());
        }

        List<String> original = new ArrayList<>(List.of("safe"));
        List<String>[] groups = pollute(original);
        System.out.println("varargs component: "
                + groups.getClass().getComponentType().getName());
        System.out.println("original unaffected: " + original);

        try {
            String item = groups[0].get(0);
            System.out.println(item);
        } catch (ClassCastException ex) {
            System.out.println("varargs read failure: "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Compile and run from the directory containing the file:

```bash
javac -Xlint:all HeapPollutionDemo.java
java HeapPollutionDemo
```

**Verified stdout:**

```text
raw contents: [Java, 42]
raw read failure: ClassCastException
varargs component: java.util.List
original unaffected: [safe]
varargs read failure: ClassCastException
```

With Java 17 and `-Xlint:all`, the compiler also emits **four warnings** in the tested example:

- `[unchecked] Possible heap pollution from parameterized vararg type List<String>` on the declaration of `pollute`.
- `[rawtypes]` on `List raw`.
- `[unchecked]` on `raw.add(42)`.
- `[unchecked] unchecked generic array creation for varargs parameter of type List<String>[]` at the call `pollute(original)`.

The exact wording, locations, and number of warnings depend on the compiler version and lint flags; they are **`javac` diagnostics**, not program stdout.

### Part A1 — Raw Type Breaks `List<String>`'s Contract

The two variables `words` and `raw` are **two references to the same `ArrayList`**. Because `raw` omits the type argument, calling `add(42)` can insert an `Integer` into the list that `words` still trusts as `List<String>`.

```text
           List<String> words ---+
                                  +---> ArrayList containing ["Java", 42]
                 List raw -------+
```

When `String item = words.get(1)` executes, typed code expects a `String`, so the compiler emits the corresponding cast, yet the actual object is an `Integer`. It is the read line that throws `ClassCastException`, not `raw.add(42)`.

### Part A2 — Generic Varargs Pollutes the Array Without Modifying the Original List

The method:

```java
static List<String>[] pollute(List<String>... groups) {
    Object[] alias = groups;
    alias[0] = List.of(99);
    return groups;
}
```

performs four dangerous steps:

1. `groups` is a runtime array with **component type `List`**, even though the compiler represents it as `List<String>[]` in source code.
2. `Object[] alias = groups` allows manipulation through an array view holding `Object`.
3. `alias[0] = List.of(99)` replaces **the first slot of `groups`** with a list containing an `Integer`. The array accepts it because that object is a `List`.
4. Returning `groups` leaks a reference to the **polluted array** to callers expecting `List<String>[]`.

The line:

```text
original unaffected: [safe]
```

is crucial: the method **does not add `99` to `original`**. It replaces an **element of the varargs array** — that is, it replaces the reference to the list. In a normal varargs call `pollute(original)`, the compiler creates the argument-passing array, and `original` still keeps `"safe"`.

When code reads:

```java
String item = groups[0].get(0);
```

it relies on `List<String>[]`, but the list at index 0 now holds an `Integer`; the cast to `String` fails. That is heap pollution via **generic varargs**, distinct from the raw `List` path earlier.

### Why Is `ArrayStoreException` Not Thrown?

The actual array `groups` has component type `java.util.List`. Both `List<String>` and `List<Integer>` are runtime objects implementing `List`. The array's runtime store check has no knowledge of the erased type argument. Conversely, if you tried to store a `String` directly into an array slot whose component class is `List`, the runtime array store check would reject it because `String` is not a `List`.

## 5. Where Errors Are Caught and How the Three Mechanisms Differ

A sequence of events to remember:

```text
Compile time:
    List<String> x
        |
        +-- x.add(42)                     -> compile-time error
        |
        +-- raw.add(42)                   -> unchecked warning

Runtime:
    raw.add(42)                           -> write may succeed
        |
        v
    polluted List<String>
        |
        v
    String s = x.get(i)                    -> ClassCastException

Generic varargs:
    List<String>... groups
        |
        v
    Object[] alias = groups
        |
        v
    alias[0] = List.of(99)                 -> array only checks the List component
        |
        v
    String s = groups[0].get(0)            -> ClassCastException
```

Not every `ClassCastException` stems from heap pollution: an ordinary invalid cast on `Object` can also cause it. Conversely, heap pollution may not throw an exception if code never reads or casts the wrong element; that is why tests covering only the happy path are insufficient to prove generic safety.

**Differences in where checks happen:**

| Scenario | Compiler | Runtime | Outcome |
| --- | --- | --- | --- |
| `List<String>.add(42)` | Rejects | Does not run | Compile-time error |
| `List raw = words; raw.add(42)` | Unchecked warning | `ArrayList` does not check type argument `String` | May cause heap pollution |
| `Object[]` pointing to `String[]`, writing `Integer` | Allows due to `Object[]` variable type | Checks `String` component | `ArrayStoreException` |
| `Object[]` pointing to varargs `List<String>[]`, writing `List<Integer>` | May miss error via alias | Only checks `List` component | May cause heap pollution |
| Reading `Integer` as `String` | Trusts source type `List<String>` | `checkcast String` fails | `ClassCastException` |

This table assumes the exact runtime objects described and no custom validation logic inside the container.

## 6. Why Can't `List<String>[]` Be Created Directly?

In Java, the following is a compile-time error:

```java
// List<String>[] groups = new List<String>[2]; // Generic array creation.
```

However:

```java
List<?>[] groups = new List<?>[2]; // Valid.
```

Java arrays store their runtime component class and verify elements written into the array. `List<String>` is **non-reifiable**: the inner `String` type is not represented as a separate runtime class for `List<String>`. Allowing `new List<String>[2]` would promise a runtime check that the JVM cannot enforce.

`List<?>` uses an **unbounded wildcard** and is a reifiable type in this context. A `List<?>[]` array can still hold lists of different element types, because its contract only states that each slot is a `List` with an unknown type argument; when reading through `List<?>`, elements are seen as `Object`, not assumed to be `String`.

Generic varargs `List<String>...` raises a related issue: in source code, the parameter looks like an array with generic components; in bytecode, the array parameter is represented by its erased component type `List`. The compiler allows varargs declarations because they are a useful language feature, while warning whenever it cannot guarantee safety due to non-reifiable elements.

## 7. Distinguishing Risks at the Method, Call Site, and Data Level

In the lab, the compiler can warn **at the method declaration**:

```java
static List<String>[] pollute(List<String>... groups)
```

and **at the call site**:

```java
List<String>[] groups = pollute(original);
```

These two warning locations help you spot different risks:

- **Declaration warning:** the method accepts a generic varargs array that could cause heap pollution. The signature itself does not guarantee bad data, yet the compiler cannot prove from the signature that the body is safe.
- **Invocation warning:** when the compiler must synthesize a varargs array with a non-reifiable component type, the call creates a typed structure that cannot be fully checked at runtime.
- **Unchecked call/conversion warning:** code may have gone through a raw type or an unverified cast, such as `raw.add(42)`.

Do not simply silence warnings at whichever place is most convenient. If you own the method, audit **the entire method body** and any aliases of the varargs array first. If the method comes from a library, read its contract and avoid unsafe call patterns.

Once a `List<String>[]` has been polluted, returning the array from the method makes bugs harder to trace because callers may read the bad element many steps later. It is especially dangerous to store a varargs array in a shared field, return it across an API, or hand it off for other code to mutate.

## 8. Writing Intentionally Safe Generic Varargs

A method that only iterates over the groups and builds a new collection can avoid pollution. Example:

```java
@SafeVarargs
static <T> List<T> merge(List<? extends T>... parts) {
    List<T> result = new ArrayList<>();
    for (List<? extends T> part : parts) {
        result.addAll(part);
    }
    return List.copyOf(result);
}
```

This pattern **does not write** into the `parts` array, does not cast or swap lists inside it, and does not expose the varargs array for external mutation. Elements are added to `result` under the `T` contract verified by the compiler. The return value is a new list, not the varargs array itself.

### When Can `@SafeVarargs` Be Used?

`@SafeVarargs` is an **author's assertion** that the implementation over non-reifiable varargs is safe. Java allows it on constructors, static methods, final instance methods, and (since Java 9) private instance methods. It cannot be placed on non-final overridable instance methods, because an overriding subclass could violate the guarantee made by the annotation.

The annotation:

- Suppresses certain unchecked warnings related to the varargs declaration/invocation that the author has proven safe.
- **Does not make the JVM retain generic type arguments** for the array.
- **Does not magically make a dangerous method safe**.
- Does not guarantee the suppression of other warnings caused by genuinely unchecked operations inside the body.

In particular, never put `@SafeVarargs` on the `pollute` method from section 4 just to clean up compiler output. That method deliberately stores a `List<Integer>` into an array that callers believe is `List<String>[]`; the annotation would make a **false** guarantee.

## 9. Program B — Using `@SafeVarargs` Properly

Create the file **`SafeVarargsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class SafeVarargsDemo {
    @SafeVarargs
    static <T> List<T> merge(List<? extends T>... parts) {
        List<T> result = new ArrayList<>();

        for (List<? extends T> part : parts) {
            result.addAll(part);
        }
        return List.copyOf(result);
    }

    static void showAny(List<?> items) {
        for (Object value : items) {
            System.out.println("seen: " + value);
        }
    }

    public static void main(String[] args) {
        List<String> merged = merge(List.of("An"), List.of("Binh"));
        System.out.println("merged: " + merged);
        showAny(merged);

        List<Number> nums = merge(List.of(1, 2), List.of(3.5));
        System.out.println("numbers: " + nums);
    }
}
```

Run:

```bash
javac -Xlint:all SafeVarargsDemo.java
java SafeVarargsDemo
```

**Verified stdout:**

```text
merged: [An, Binh]
seen: An
seen: Binh
numbers: [1, 2, 3.5]
```

**Why is it safe in this example?**

1. `parts` is only **read**; its array slots are never modified.
2. Every `part` is a `List<? extends T>`: elements read out can be used as `T`.
3. `result` is a brand-new `ArrayList<T>` that holds no alias to the varargs array.
4. The `parts` array is neither returned, stored in a field, nor passed to untrusted code.
5. `List.copyOf(result)` returns a list that does not support standard mutating operations. In this example the elements are immutable `String` and `Number` instances; `copyOf` does not automatically provide deep immutability if elements themselves are mutable.

When calling `merge(List.of(1, 2), List.of(3.5))` in an assignment context targeting `List<Number>`, the compiler can infer `T = Number`. Both `Integer` and `Double` elements can be treated as `Number`, so the output is valid.

**Avoid overgeneralizing:** `@SafeVarargs` does not declare that any arbitrary generic varargs method is always safe. It applies only when **the body truly contains no operations that break the generic contract**.

## 10. Better Alternatives When Varargs Are Not Needed

If an API routinely receives collections from callers, a non-varargs signature can express intent more clearly:

```java
static <T> List<T> copyOfItems(
        java.util.Collection<? extends T> source) {
    return List.copyOf(source);
}
```

This is an illustrative method snippet and needs to be placed inside a class that imports `java.util.List`. It does not force the compiler to create a generic varargs array at the call site.

Or, if multiple groups are needed, accept a collection of groups:

```java
static <T> List<T> flatten(
        List<? extends List<? extends T>> groups) {
    List<T> out = new ArrayList<>();
    for (List<? extends T> group : groups) {
        out.addAll(group);
    }
    return List.copyOf(out);
}
```

Use `List<List<String>>` or a compatible typed expression as required in practice. This approach has no hidden varargs array and avoids aliasing risks of generic arrays, though you must still respect contracts regarding `null`, collection mutability, and concurrency.

**Rule of thumb:** varargs makes sense when an API is conveniently called with several separate arguments and the method only reads or consumes them safely; collection parameters are usually better when callers already hold dynamic lists or need clear ownership contracts.

## 11. Data Boundaries from Raw APIs: Validate Elements Before Producing `List<String>`

In legacy code, you cannot always change an API that returns a raw `List`. Instead of:

```java
// Do not declare data safe merely by casting:
// @SuppressWarnings("unchecked")
// List<String> strings = (List<String>) legacyList;
```

accept `List<?>`, validate each element, and construct a new typed result. This surfaces errors at the **data boundary** rather than letting them appear later in business logic.

Create the file **`HeapPollutionBoundaryDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class HeapPollutionBoundaryDemo {
    static List<String> checkedStrings(List<?> input) {
        List<String> copy = new ArrayList<>();

        for (int i = 0; i < input.size(); i++) {
            Object value = input.get(i);
            if (!(value instanceof String s)) {
                throw new IllegalArgumentException(
                        "invalid element at index " + i);
            }
            copy.add(s);
        }
        return List.copyOf(copy);
    }

    public static void main(String[] args) {
        List<?> good = List.of("A", "B");
        System.out.println("validated: " + checkedStrings(good));

        List<?> bad = List.of("A", 5);
        try {
            checkedStrings(bad);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }
    }
}
```

Run:

```bash
javac -Xlint:all HeapPollutionBoundaryDemo.java
java HeapPollutionBoundaryDemo
```

**Verified stdout:**

```text
validated: [A, B]
rejected: invalid element at index 1
```

The `checkedStrings` method confirms that **every element** is a `String` before returning `List<String>`. It uses no unchecked cast, rejects `null` (because `null instanceof String` evaluates to `false`), and returns a new list that cannot be modified directly via standard list operations.

If a legacy list may hold objects of multiple types, you should agree explicitly whether invalid elements should be **rejected**, **converted**, or **skipped with reporting**. The `checkedStrings` approach is a fail-fast policy, not the only sensible policy.

When multiple threads can modify the input collection concurrently during validation, stronger guarantees require consistent synchronization or snapshotting; element-by-element copying in this example does not automatically provide an atomic snapshot if the source is mutated concurrently.

## 12. Warning Mechanisms: Enabling the Right Tools When Hunting Heap Pollution

Useful compiler options:

```bash
javac -Xlint:rawtypes -Xlint:unchecked -Xlint:varargs HeapPollutionDemo.java
```

| Category | Example detected | What to inspect |
| --- | --- | --- |
| `rawtypes` | `List raw` | Why is the type argument omitted, and can it be replaced with generics or a wildcard? |
| `unchecked` | `raw.add(42)`, unsafe generic varargs, unchecked casts | Is the data guaranteed to have the right type? |
| `varargs` | Potentially unsafe operations inside a varargs method body, especially when annotated | Does the body leak, write to, or alias the varargs array? |

On the program we ran, `javac -Xlint:all` catches raw types, unchecked calls, generic varargs declarations, and generic varargs invocations. You can enable `-Xlint:all` during audits and narrow down the tracked categories for your build pipeline once you understand the root causes.

In real codebases, compiler warnings may appear at different locations depending on the JDK. Do not turn the exact message text or line numbers in these examples into rigid rules; what matters is **the nature of the data flow and the compiler's ability to prove type safety**.

Priority order for fixes:

1. Do not let raw types leak past legacy boundaries.
2. Replace unchecked casts with structured data validation whenever possible.
3. Audit every generic varargs method for array writes or array exposure.
4. Consider removing varargs if it is not genuinely needed.
5. Use `@SuppressWarnings("unchecked")` only in narrow scopes with an explanatory proof.
6. Apply `@SafeVarargs` only after verifying that the method body is safe.

## 13. Observing Type Erasure with `javap`

After compiling `HeapPollutionDemo.java`, run:

```bash
javap -s -p HeapPollutionDemo
```

**Verified excerpt:**

```text
static java.util.List<java.lang.String>[] pollute(
    java.util.List<java.lang.String>...);
  descriptor: ([Ljava/util/List;)[Ljava/util/List;
```

How to read it: the `[` prefix before a type descriptor denotes an **array**; `Ljava/util/List;` denotes a `List` object. The descriptor `([Ljava/util/List;)[Ljava/util/List;` shows that at the JVM level the method accepts a `List[]` array and returns a `List[]` array. The `String` type argument does not appear in the descriptor — it can only be recorded in generic `Signature` metadata.

This is clear evidence of why the runtime component type of the varargs array in our example is `java.util.List`. The JVM can check whether an object placed into the array is compatible with `List`, but **cannot verify the `String` type argument separately**.

If you also want to inspect the cast bytecode at read sites:

```bash
javap -c -p HeapPollutionDemo
```

In `main`, there are reads whose source type expects `String`; the compiler can emit `checkcast java/lang/String`. Exact bytecode indices and offsets depend on the compiler build, so focus on **method descriptors and opcodes** rather than memorizing bytecode line numbers.

## 14. Common Mistakes to Avoid

**Mistake 1 — Thinking heap pollution is a dedicated exception.** Heap pollution is a violated type-safety state, not a named exception. `ClassCastException` is a possible consequence when a cast occurs.

**Mistake 2 — Ignoring warnings because the program still runs.** An unchecked path can pass many tests simply because bad data has not appeared yet; the risk remains. Add test cases with incompatible elements and typed reads.

**Mistake 3 — Thinking `@SafeVarargs` makes a method safe by itself.** The annotation introduces no new runtime checks. If the body executes `alias[0] = List.of(99)`, it remains dangerous even if the compiler no longer warns at call sites.

**Mistake 4 — Confusing `List<?>[]` with `List<String>[]`.** `List<?>[]` does not promise that every element is a `List<String>`; never cast arbitrarily and then rely on reading strings.

**Mistake 5 — Assuming `ArrayStoreException` will protect generic varargs arrays.** Runtime array store checks only know the `List` component type, not the type arguments of each list.

**Mistake 6 — Failing to distinguish modifying the array from modifying the collection.** In the `pollute` example, `alias[0]` is replaced with a different list; `original` does not have `99` inserted into it. When debugging, inspect the identity/aliasing of the **array** and the **list elements** separately.

**Mistake 7 — Treating `List<Object>` as a universal substitute for `List<String>`.** Java generics are invariant; `List<String>` is not a subtype of `List<Object>`. Use `List<?>` to read elements of unknown type, or `List<T>` matching the domain.

**Mistake 8 — Using an unchecked cast on a whole list instead of validating.** `(List<String>) raw` does not iterate and check every element. It can attach an invalid generic promise to real data.

**Mistake 9 — Assuming only generic varargs causes heap pollution.** Raw types, unchecked conversions, reflection/unsafe operations, or legacy APIs can also produce data that violates a generic contract.

**Mistake 10 — Letting a varargs array escape its scope without consideration.** If the array is saved in a field or returned, other code can mutate slots through aliases, breaking generic promises trusted by downstream readers.

## 15. Practice Exercises with Answers

### Exercise 1 — Identifying Heap Pollution

```java
List<String> names = new ArrayList<>();
List raw = names;
raw.add(100);
```

**Question:** When can heap pollution occur? Is `raw.add(100)` guaranteed to throw an exception?

**Answer:** once an `Integer` enters the list that `names` declares as `List<String>`, the generic promise has been violated. `raw.add(100)` can succeed with an unchecked warning; the failure may only surface when code reads an element as `String`.

### Exercise 2 — Relationship Between Varargs and Array Covariance

A method receives `List<String>... groups` and runs `Object[] x = groups; x[0] = List.of(7)`. Why isn't `ArrayStoreException` necessarily thrown at the assignment?

**Answer:** the array's runtime component class is `List`; `List.of(7)` produces an object implementing `List`. The JVM has no runtime information stating that the slot must hold `List<String>`.

### Exercise 3 — Two Different Failures

An `Object[]` pointing to a `String[]` has an `Integer` written into it; a `List<String>` has an `Integer` written into it via a raw type and is then read as `String`. What are the two typical exceptions?

**Answer:** the `String[]` array throws `ArrayStoreException` at the write site; reading from the polluted `List<String>` typically throws `ClassCastException`.

### Exercise 4 — When `@SafeVarargs` Is and Isn't Appropriate

A method only iterates over `List<? extends T>... items` to copy elements into an `ArrayList<T>`; it neither writes to nor returns the varargs array. Can `@SafeVarargs` be placed on that static method?

**Answer:** yes, provided the author verifies that the body neither creates heap pollution nor exposes the array. Never apply the annotation to a method that writes incompatible data into the varargs array.

### Exercise 5 — Two Warning Categories

How do `-Xlint:rawtypes` and `-Xlint:unchecked` differ?

**Answer:** `rawtypes` detects generic types used without type arguments (`List raw`), whereas `unchecked` detects generic operations that cannot be fully verified (`raw.add(42)`, casts, or generic varargs).

### Exercise 6 — Why Can `List<?>[]` Be Created?

`new List<?>[2]` is valid while `new List<String>[2]` is invalid. Why?

**Answer:** `List<?>` with an unbounded wildcard is reifiable for array creation and makes no claim about specific element types. `List<String>` is non-reifiable and therefore cannot be the component type of an array created directly with that syntax.

### Exercise 7 — Building an Adapter Around a Raw API

A legacy `List` might contain `String`, `Integer`, and `null`; you need an API returning `List<String>`. Should you use `(List<String>) raw` with `@SuppressWarnings`?

**Answer:** a cast cannot serve as validation. Accept `List<?>`, inspect each element, decide how to handle wrong types or `null`, and construct a new typed list like `checkedStrings`.

### Exercise 8 — Verifying with `javap`

For `static List<String>[] pollute(List<String>... groups)`, does the descriptor contain `String` or only `List[]`?

**Answer:** the descriptor uses `List[]` for both parameter and return type: `([Ljava/util/List;)[Ljava/util/List;`. The generic `String` can appear in Signature metadata, not in the runtime descriptor.

## 16. Self-Assessment Checklist

You should be able to explain:

1. What heap pollution is and why it is not synonymous with an unchecked warning or an exception.
2. How a raw `List` can corrupt data still referenced by a `List<String>` variable.
3. How generic varargs are passed via a runtime array whose component type is erased to `List`.
4. How an `Object[]` alias can write `List<Integer>` into a varargs array without the runtime checking `String`.
5. Why `ClassCastException` can appear later at typed reads, whereas `ArrayStoreException` belongs to actual array element checks.
6. Why `@SafeVarargs` is a guarantee that must be proven, not a switch that fixes type safety.
7. How `List<?>[]` differs from `List<String>[]` in terms of type guarantees and array creation.
8. How a safe upgrade path removes unnecessary raw types, validates data at boundaries, limits unchecked casts, and avoids unsafe operations on varargs arrays.
9. How `javap -s` and `-c` provide evidence of type erasure and generated casts in bytecode.

## Conclusion

**Heap pollution** occurs when a parameterized type's promise no longer reflects the referenced object. With generic varargs, a notable cause is that **the runtime array only knows the erased component type**, allowing a list with the wrong type argument to pass the store check via `Object[]`. Casting on a subsequent read expecting `String` then throws `ClassCastException`.

Use typed generics instead of raw types, avoid exposing or mutating varargs arrays, apply `@SafeVarargs` only after proving the body safe, and validate elements from untrusted sources before publishing a `List<String>`. That way Java generics continue enforcing type safety at compile time rather than deferring failures to runtime.
