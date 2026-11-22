# Why Can Two Identically Written Wildcards Still Be Two Different Types?

## 1. The Problem: Both Written `?`, Yet Not Guaranteed to Be the Same Type

In Java Generics, the `?` (*wildcard*) symbol represents **an unknown type**. When two positions both write `List<?>`, we only know each list has **some kind of element**; there is no promise that the two element kinds must match.

~~~java
List<String> words = List.of("A", "B");
List<Integer> numbers = List.of(1, 2);

List<?> first = words;
List<?> second = numbers;

Object a = first.get(0);
Object b = second.get(0);
~~~

The two variables `first` and `second` have the same **declared type** `List<?>`. Yet one list contains `String` and the other contains `Integer`. Hence there is no basis to transfer an element retrieved from `first` into `second`:

~~~java
// Does NOT compile:
second.add(first.get(0));
~~~

That is the most important scenario when learning **wildcard capture**. When the compiler needs to check a method call on a generic type containing a wildcard, it can **capture** the unknown type into a fresh type variable for inference. Two captures can be represented by the compiler as `CAP#1` and `CAP#2`, each with its own constraints. The same `?` syntax **does not automatically create an equality relationship** between captures.

In this lesson, we will distinguish the declared type from the captured type, also explain the case where two positions use **the very same `List<?>` variable**, verify real compile errors, and then fix the design with a generic helper `<T>` or an appropriate PECS relationship.

## 2. Identical Declared Types Differ from Captured Type Identity

### 2.1. `List<?>` Is a Valid Type; `CAP#1` Is Not a Name Written by Programmers

The following three declarations are all valid:

~~~java
List<?> unknownA = List.of("Java");
List<?> unknownB = List.of(42);
List<?> unknownC = List.of(3.5);
~~~

The variables share the same *declared type* `List<?>` and all allow reading elements as `Object`. This is a safe relationship with no unchecked conversion.

However, in a call like `unknownB.add(...)`, the `E` parameter of `List<E>` must be known well enough for the compiler to decide whether the value can be added. Java applies **capture conversion** to temporarily represent the wildcard as a hidden type, for example:

~~~text
List<?>                -> List<CAP#1>
CAP#1 extends Object
~~~

This is a **modeling diagram**, not Java syntax. `CAP#1` is a compiler-generated diagnostic name, not a class, a runtime type token, or a type parameter a programmer can write directly.

Another capture can produce:

~~~text
List<?>                -> List<CAP#2>
CAP#2 extends Object
~~~

The two constraints `CAP#1 extends Object` and `CAP#2 extends Object` **do not imply** `CAP#1 == CAP#2`, `CAP#1 <: CAP#2`, or `CAP#2 <: CAP#1`. Which order the compiler uses for `CAP#1`, `CAP#2` is an error-message detail; what matters is that **no compatibility proof exists between the two unknown types**.

### 2.2. Capture Is a Compile-Time Operation and Does Not Modify the List

When assigning `List<String>` to `List<?>`, Java does not convert elements to a new type and creates no copy. Both references can point to the same list object. **Capture conversion only helps the type system analyze an expression**.

It is not stored at runtime as types `CAP#1`/`CAP#2`. Generic type arguments largely undergo *type erasure* in the runtime representation. Java must decide whether calls to `add`, `set`, or `get` are valid **before running**.

### 2.3. “Not Equal” Does Not Mean Everything Is Forbidden

~~~java
List<?> x = List.of("A");
List<?> y = List.of(10);

Object left = x.get(0);  // Valid.
Object right = y.get(0); // Valid.

boolean same = left.equals(right); // Valid: equals accepts Object.
boolean hasIt = y.contains(left);  // Valid: contains accepts Object.
~~~

`contains(Object)` does not require an argument matching the list's type parameter `E`. Meanwhile `add(E)` and `set(int,E)` require a value compatible with `E`. The **method signature itself** determines whether a relationship between captured types needs to be proven.

## 3. Two `List<?>` Variables: Readable, but Elements Cannot Be Transferred Arbitrarily

Consider a method purely illustrating the error:

~~~java
static void brokenTransfer(List<?> source, List<?> target) {
    target.add(source.get(0)); // Does NOT compile.
}
~~~

Conceptual analysis:

1. `source.get(0)` returns a value of an unknown captured type, say `CAP#1`.
2. `target.add(...)` only accepts `target`'s element type, say `CAP#2`.
3. There is no guarantee that `CAP#1` is a subtype of `CAP#2`.
4. The compiler rejects the element transfer.

Concrete counterexample:

~~~java
List<String> source = List.of("text");
List<Integer> target = new ArrayList<>();
// If both could be passed as List<?> and then target.add(source.get(0)),
// a String would be added into a list declared as List<Integer>.
~~~

Even if on some call the caller passes two `List<String>` instances, the signature `brokenTransfer(List<?>, List<?>)` must guarantee type safety for **every valid pair**, including `List<String>` and `List<Integer>`.

**Do not fix this with raw/unchecked casts.** Casting `List<?>` to `List<String>` without proof of the element type merely shifts the risk to runtime and can cause heap pollution.

## 4. Even the Same `List<?>` Variable Can Produce Two Different Captures

The most surprising point: even a **single reference** does not guarantee that the compiler recognizes two capture results across separate expressions as one mutually assignable type.

~~~java
static void brokenSelfAssign(List<?> list) {
    list.set(0, list.get(0)); // Does NOT compile.
}
~~~

From a human perspective, `get(0)` retrieves an element from the exact list that `set(0, ...)` writes back to, so this operation can be safe if the list is mutable. Yet the compiler analyzes generic expressions containing wildcards via capture conversion. When checking the `set` call, it can see a type `CAP#1` for the parameter `E` to write and a type `CAP#2` for the result of `get`. Having both expressions use **the same source variable** does not automatically generate the constraint `CAP#1 == CAP#2` in that call.

Compiling with Java 17 using `javac -Xdiags:verbose` produces an error equivalent to:

~~~text
required: int,CAP#1
found:    int,CAP#2
...
CAP#1 extends Object from capture of ?
CAP#2 extends Object from capture of ?
~~~

CAP ordering/numbering can vary by compiler and version. The line `set(0, list.get(0))` **does not compile** even though both expressions refer to the same object.

**Key takeaway to remember:** Do not think of each `List<?>` variable as having a “fixed CAP ID” throughout a method. CAP names are the result of analyzing expressions/captures; resolve them using explicitly expressed type relationships rather than relying on variable names or runtime object identity.

### 4.1. Aliasing Also Does Not Automatically Prove Capture Equality

~~~java
List<String> actual = new ArrayList<>(List.of("A", "B"));
List<?> a = actual;
List<?> b = actual;
~~~

The two references `a` and `b` both point to `actual` at runtime. However, a method with signature `f(List<?> a, List<?> b)` cannot assume the two variables always point to the same object, or have the same element type on every call. When exchanging values by type parameter, you must state that relationship in the signature or capture via a helper for **a single list**.

## 5. Identical `extends` Wildcards Are Also Not Guaranteed to Be the Same Subtype

This situation is not limited to `List<?>`. Two variables both declared `List<? extends Number>` can refer to:

~~~java
List<? extends Number> ints = List.of(2, 4);
List<? extends Number> doubles = List.of(1.5, 2.5);

Number a = ints.get(0);    // Valid.
Number b = doubles.get(0); // Valid.
~~~

Yet you cannot directly transfer a value read from one list into the other:

~~~java
static void brokenUpperBound(
        List<? extends Number> source,
        List<? extends Number> target) {
    target.add(source.get(0)); // Does NOT compile.
}
~~~

We can model the two independent captures:

~~~text
CAP#1 <: Number
CAP#2 <: Number
~~~

Both are subtypes of `Number`; that **does not prove `CAP#1` is a subtype of `CAP#2`**. If `source` is actually `List<Integer>` and `target` is `List<Double>`, writing an `Integer` into a `Double` list would be wrong.

This is why `? extends Number` fits a **read source**: it guarantees a common type on the reading side, without permitting arbitrary `Number` insertions.

## 6. `super` Wildcards: Known Values Can Be Written, but Read Results Cannot Be Assumed to Share a Type

With `List<? super Integer>`, each list has an unknown element type, yet **each such type accepts `Integer`**:

~~~java
List<? super Integer> x = new ArrayList<Number>();
List<? super Integer> y = new ArrayList<Object>();

x.add(10); // Valid.
y.add(20); // Valid.
~~~

Even so, **transferring an element read from `x` into `y`** is still not guaranteed:

~~~java
static void brokenLowerBound(
        List<? super Integer> source,
        List<? super Integer> target) {
    target.add(source.get(0)); // Does NOT compile.
}
~~~

The reason: `source` could be a `List<Object>` holding a `String`, while `target` could be a `List<Integer>`. An element read from `List<? super Integer>` is only guaranteed as `Object`, not `Integer`.

It is safe to **add an existing `Integer` variable**, not every element incidentally read from a list that accepts `Integer`:

~~~java
Integer n = 10;
x.add(n);
y.add(n);
~~~

General conclusion for `?`, `? extends T`, and `? super T`: **two wildcards with the same bound syntax do not mean they represent the same type argument**.

## 7. Fixing the Single-List Case: Wildcard Capture Helper with `<T>`

The `brokenSelfAssign(List<?>)` case can be solved using a **generic helper method**. The public API still allows any `List<?>`; inside the helper, we **name the element type** so it is used consistently across `get` and `set`.

~~~java
static void swapEnds(List<?> values) {
    swapEndsCaptured(values);
}

private static <T> void swapEndsCaptured(List<T> values) {
    if (values.size() < 2) {
        return;
    }
    int last = values.size() - 1;
    T temporary = values.get(0);
    values.set(0, values.get(last));
    values.set(last, temporary);
}
~~~

**Mechanism:**

1. Calling `swapEndsCaptured(values)` lets the compiler infer a `T` corresponding to the captured type of the source list.
2. Inside the helper, both the return value of `get(...)` and the argument to `set(..., value)` refer to the same **named type parameter `T`**.
3. `T temporary = values.get(0)` creates a variable of static type `T`. Both `set` calls also expect `T`, so type checking succeeds without any cast.
4. The caller does not need to know whether the list holds `String`, `Integer`, or any specific type.

This method is safe regarding **element type**. It still requires a mutable collection; `List.of(...)` does not support `set` and can throw `UnsupportedOperationException` if passed directly to `swapEnds`. Checking `size() < 2` protects empty and single-element lists from index errors.

### 7.1. Why Does the Helper Succeed While the Direct Nested Expression Fails?

In the helper `List<T>`, **one letter `T` is declared** and used at every relevant position. In `List<?>`, each check of a wildcard-involving expression can require a separate capture. Having the compiler accept the helper method **does not prove that wildcards from unrelated parameters are identical**: the helper is operating on a single list object under one unified `T`.

With two independent variables `List<?> source` and `List<?> target`, you cannot arbitrarily give them the same `T` just by calling a `<T>` helper; the caller must supply a **genuine type relationship** for the compiler to verify.

## 8. Two Independent Lists: Expressing the Relationship in the Method Signature

If two lists genuinely share the same element type, a method using the type parameter in both positions makes sense:

~~~java
static <T> void swapFirst(List<T> left, List<T> right) {
    T temporary = left.get(0);
    left.set(0, right.get(0));
    right.set(0, temporary);
}
~~~

The method above accepts **two `List<String>`** instances or **two `List<Integer>`** instances; it ensures both type arguments match the same `T`. Assumptions: both lists have at least one element and allow `set`.

~~~java
List<String> left = new ArrayList<>(List.of("A"));
List<String> right = new ArrayList<>(List.of("B"));
swapFirst(left, right); // Valid.
~~~

However, a pair of `List<String>` and `List<Integer>` cannot be passed to `swapFirst` under a shared `List<T>`; this **matches the contract** of the element-exchange algorithm. Do not use raw types to force the call past that boundary.

### 8.1. The Producer/Consumer Case: `<T>` Combined with Two Differently Directed Wildcards

Sometimes source and target do not have the same type argument yet can still **transfer elements safely**. For example, `List<Integer>` supplies `Integer`s to `List<Number>`.

~~~java
static <T> void appendAll(
        List<? extends T> source,
        List<? super T> destination) {
    for (T element : source) {
        destination.add(element);
    }
}
~~~

`T` serves as the bridge between the read site and the write site; the wildcards express the roles:

- `source: List<? extends T>` guarantees **reading `T`**.
- `destination: List<? super T>` guarantees **ability to write `T`**.
- There is no need to force the two actual type arguments to be identical: one side can be `Integer`, the other `Number`.

Example:

~~~java
List<Integer> ints = List.of(2, 4);
List<Number> numbers = new ArrayList<>(List.of(1.5));
appendAll(ints, numbers);
System.out.println(numbers); // [1.5, 2, 4]
~~~

This applies **PECS** (*Producer Extends, Consumer Super*) to a relationship that Java can verify. It **differs** from assuming two wildcards with the same syntax are the same capture.

The standard API `Collections.copy(List<? super T> dest, List<? extends T> src)` expresses the same type-relationship model, though its behavior **replaces elements by position**, requiring the destination list to have sufficient size rather than appending as above.

## 9. Runnable Java 17+ Program to Observe the Difference

Create **WildcardCaptureIdentityDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class WildcardCaptureIdentityDemo {
    static void rotateEnds(List<?> values) {
        rotateEndsCaptured(values);
    }

    private static <T> void rotateEndsCaptured(List<T> values) {
        if (values.size() < 2) {
            return;
        }
        int last = values.size() - 1;
        T temporary = values.get(0);
        values.set(0, values.get(last));
        values.set(last, temporary);
    }

    static <T> void swapFirst(List<T> left, List<T> right) {
        T temporary = left.get(0);
        left.set(0, right.get(0));
        right.set(0, temporary);
    }

    static <T> void appendAll(List<? extends T> source, List<? super T> destination) {
        for (T element : source) {
            destination.add(element);
        }
    }

    public static void main(String[] args) {
        List<String> left = new ArrayList<>(List.of("A", "B", "C"));
        List<String> right = new ArrayList<>(List.of("X", "Y"));

        rotateEnds(left);
        System.out.println("rotated: " + left);

        swapFirst(left, right);
        System.out.println("left: " + left);
        System.out.println("right: " + right);

        List<?> view1 = left;
        List<?> view2 = right;
        Object first = view1.get(0);
        Object second = view2.get(0);
        System.out.println("read: " + first + " / " + second);

        List<Integer> integers = List.of(2, 4);
        List<Number> destination = new ArrayList<>(List.of(1.5));
        appendAll(integers, destination);
        System.out.println("numbers: " + destination);

        List<? extends Number> n1 = List.of(5);
        List<? extends Number> n2 = List.of(8.5);
        Number a = n1.get(0);
        Number b = n2.get(0);
        System.out.println("numeric views: " + a + " / " + b);
    }
}
~~~

Compile and run with Java 17 or newer:

~~~bash
javac --release 17 -Xlint:all WildcardCaptureIdentityDemo.java
java WildcardCaptureIdentityDemo
~~~

**Exact stdout**:

~~~text
rotated: [C, B, A]
left: [X, B, A]
right: [C, Y]
read: X / C
numbers: [1.5, 2, 4]
numeric views: 5 / 8.5
~~~

The program has been verified with `javac --release 17 -Xlint:all`: compiles cleanly with no unchecked warnings.

Walkthrough:

1. `rotateEnds` accepts a wildcard, and the `<T>` helper maintains one captured type throughout the swap; result `[C, B, A]`.
2. `swapFirst` accepts two `List<String>` instances sharing a type argument, so swapping the first elements succeeds.
3. Both `List<?>` views read safely as `Object`. Identical syntax reveals nothing about the actual values or grants permission to transfer arbitrarily between them.
4. `appendAll` lets source `List<Integer>` transfer elements into destination `List<Number>` using one shared `T` and two oppositely directed wildcards.
5. Both `List<? extends Number>` views read safely as `Number` yet can hold two different actual subtypes, such as `Integer` and `Double`.

## 10. Verifying Cases That Do NOT Compile

Separately create **InvalidCaptures.java** below to test intentional errors. **This file intentionally does not compile** and is not part of the runnable program in section 9.

~~~java
import java.util.List;

class InvalidCaptures {
    static void sameVariable(List<?> list) {
        list.set(0, list.get(0)); // Two captures are not inferred to be the same.
    }

    static void twoVariables(List<?> source, List<?> target) {
        target.add(source.get(0)); // No relationship between the two wildcards.
    }

    static void twoUpperBounds(List<? extends Number> source,
                               List<? extends Number> target) {
        target.add(source.get(0)); // The same upper bound is still insufficient.
    }
}
~~~

Test command:

~~~bash
javac --release 17 -Xdiags:verbose InvalidCaptures.java
~~~

**Expected:** `javac` exits **non-zero**, reporting three compile errors. Typical diagnostic excerpts verified with Java supporting `--release 17`:

~~~text
required: int,CAP#1
found:    int,CAP#2
...
no suitable method found for add(CAP#1)
...
CAP#1 extends Number from capture of ? extends Number
CAP#2 extends Number from capture of ? extends Number
3 errors
~~~

These are **typical abbreviated excerpts**, not verbatim full stderr; `CAP#` numbers, file positions, and formatting can change across compilers. All three errors point to one root cause: the signatures fail to provide evidence that a value of the captured type at the read site is compatible with the captured type at the write site.

Do not fix with `@SuppressWarnings("unchecked")`: the three cases above are **type incompatibility errors**, not merely unchecked warnings that an annotation could suppress. The solution is to **change the signature/type contract** or use a capture helper when working with a single collection.

## 11. What Happens If Two Wildcards Are Created from the Same Source?

Look at:

~~~java
List<String> strings = new ArrayList<>(List.of("A", "B"));
List<?> one = strings;
List<?> two = strings;
~~~

Knowing that `one` and `two` currently point to the same object **is not a typing condition expressed by `List<?>`**. Aliasing is a runtime fact at that moment; a method declaring two `List<?>` parameters still accepts two completely different lists.

On the other hand, you can retain the `List<String>` type at the call site and pass it to a `<T>` method requiring two `List<T>` parameters. Then both parameters are checked under an explicit type relationship. If the public API only accepts **two independent `List<?>` parameters**, there is no completely type-safe generic way to assume they share the same element type just by comparing references or looking at wildcard syntax.

Comparison:

| Case | What proof does the compiler have? | Transfer elements between the two lists? |
| --- | --- | --- |
| `List<String> a`, `List<String> b` | Same type argument `String` | Valid if destination supports modification. |
| `List<?> a`, `List<?> b` | Two unknown kinds, possibly different | Not guaranteed. |
| `List<? extends Number> a` and `b` of the same declared type | Each is some subtype of `Number` | Cannot do `b.add(a.get(0))`. |
| `List<? super Integer> a` and `b` of the same declared type | Each accepts `Integer` | Can add a known `Integer` to both; cannot transfer arbitrary `a.get(...)` elements to `b`. |
| `<T> swap(List<T> a,List<T> b)` | Both lists share one `T` in the call | Valid when the caller satisfies the signature. |
| `<T> append(List<? extends T>,List<? super T>)` | Source reads `T`, destination accepts `T` | Valid even if actual type arguments differ. |

## 12. Limitations and Common Pitfalls

### 12.1. Misreading “same `?`” as “same subtype”

A wildcard is a constraint, **not a named variable**. Two positions both having `? extends Number` only share the upper bound `Number`, not implicitly the same `Integer` or `Double`.

### 12.2. Believing `CAP#1` Is a Runtime Class

Labels `CAP#1`, `CAP#2` are how the compiler represents hidden types during type checking. They do not appear as new classes. You cannot use `instanceof CAP#1`, write `new CAP#1()`, or name a type variable with this syntax.

### 12.3. Using the Same Alias and Expecting the Compiler to Track Object Identity

Java does not rely on two references pointing to the same list to automatically allow writes through generic wildcards. When an algorithm requires a relationship, express it with a type parameter or a capture helper.

### 12.4. Treating `? extends Number` as `List<Number>`

`List<Integer>` is not a subtype of `List<Number>` because generics are invariant. `List<? extends Number>` is an upper-bounded read view; it does not permit adding arbitrary `Number`s and does not unify captured types across two lists.

### 12.5. Using `? super Integer` and Assuming Read Values Are Integer

`List<? super Integer>` can point to `List<Number>` or `List<Object>` with elements broader than `Integer`. The safe read type of `List<E>` is `Object`. An `Integer` explicitly supplied by the caller can still be added to any `List<? super Integer>`.

### 12.6. Thinking Any `<T>` Helper Forces Two Independent Wildcards to Match

A helper can **preserve one list's capture** across operations. For **two independent lists**, the relationship must be proven by the method signature and the arguments passed by the caller. A generic type parameter does not automatically allow mixing the types of `List<String>` and `List<Integer>`.

### 12.7. Ignoring Mutability and Index Errors

Generic typing only permits or forbids operations **type-wise**. `get(0)` and `set(0, value)` can still throw `IndexOutOfBoundsException` if the list is empty; `List.of(...)` is unmodifiable and can throw `UnsupportedOperationException` when `add` or `set` is called.

## 13. Workflow for Diagnosing Wildcard Capture Errors

1. **Read the exact `CAP#n` error line:** two different labels usually indicate the compiler has not proven the two captured types have a compatible relationship.
2. **Check the signature of the called method:** `get` returns `E`; `add` expects `E`; `set` both takes and returns `E`; `contains` takes `Object`.
3. **Check how many wildcard sources are involved:** one list needing internal operations, or two genuinely independent lists?
4. **For one list:** consider a public `List<?>` method delegating to a private helper `<T> ... (List<T>)` to capture one consistent type.
5. **For two lists:** require the relationship the algorithm actually needs via `List<T>`/`List<T>` or `List<? extends T>`/`List<? super T>`.
6. **Do not fix with raw types or unchecked casts** when there is no proof of contents. Re-test call sites with `javac -Xlint:unchecked`.
7. **Distinguish static errors from runtime risks:** a compile-time capture error differs from `ClassCastException`/heap pollution caused by deliberately bypassing the type system.

## 14. Review Questions

1. Are two variables both typed `List<?>` guaranteed to have the same type argument? **No.** One may be `List<String>`, the other `List<Integer>`.
2. Do `CAP#1` and `CAP#2` both extending `Object` mean the two types are equal? **No.** Sharing an upper bound does not prove equality.
3. Why does `list.set(0,list.get(0))` fail to compile inside a method accepting `List<?>`? **Because the two expressions can be captured separately; the compiler does not link them to the same type variable.**
4. Why can helper `<T> void swap(List<T>)` operate safely? **Because `T` is used consistently for both the inputs and outputs of the operations.**
5. Can two `List<? extends Number>` lists transfer elements directly between each other? **Not guaranteed**, because they could be `List<Integer>` and `List<Double>`.
6. Can two `List<? super Integer>` lists both accept `Integer n`? **Yes, type-wise**, because every valid supertype accepts `Integer`. However, that does not imply arbitrary `source.get(...)` elements can be transferred to the destination.
7. When source is `List<Integer>` and target is `List<Number>`, which signature describes safe element copying? **`<T> void append(List<? extends T>,List<? super T>)`**.
8. Is `CAP#1` a class that exists at runtime? **No**, it is a type variable used by the compiler during type checking.
9. If two wildcard variables reference the same object, does that replace the generic contract? **No**; the type relationship must be expressed in the signature or handled by a properly scoped helper.
10. Can `@SuppressWarnings("unchecked")` turn a capture incompatibility error into valid code? **No.** It is a type-checking error, not merely an unchecked warning.

## 15. References

- [JLS Java SE 17 §5.1.10 — Capture Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.10): rules for creating fresh capture variables from wildcards and non-equivalence between captures.
- [JLS Java SE 17 §4.5.1 — Type Arguments of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.1): upper/lower bounded wildcards, type argument bounds, and containment relationships.
- [JLS Java SE 17 §4.10.2 — Subtyping Among Class and Interface Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.10.2): subtyping of parameterized types, and why `List<Integer>` is not a subtype of `List<Number>`.
- [Oracle Java Tutorials — Wildcard Capture and Helper Methods](https://docs.oracle.com/javase/tutorial/java/generics/capture.html): `CAP#` errors and generic helper examples used to capture wildcards.
- [Oracle Java Tutorials — Guidelines for Wildcard Use](https://docs.oracle.com/javase/tutorial/java/generics/wildcardGuidelines.html): PECS and how to choose wildcards for sources and destinations.
- [Java SE 17 API — List<E>](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): contracts of `get`, `set`, `add` and distinguishing type safety from list mutability.