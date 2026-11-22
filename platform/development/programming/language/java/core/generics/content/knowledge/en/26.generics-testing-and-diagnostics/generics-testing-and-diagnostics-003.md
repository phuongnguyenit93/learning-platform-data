# Reading `incompatible types`, `capture`, and `incompatible bounds` Errors in Java Generics

## 1. Learning Objectives

`javac` Generics error messages often contain phrases like `incompatible types`, `capture of ?`, `CAP#1`, `inference variable T has incompatible bounds`, `equality constraints`, `upper bounds`, or `lower bounds`. They look intimidating, yet most express one very concrete question:

> Does the compiler have enough proof that the value being passed, assigned, or returned satisfies **every type constraint** at the call or usage site?

To fix them properly, you need to determine whether the error comes from an **invalid subtype relationship**, an **unknown wildcard being captured**, or a **generic inference system unable to find a single type satisfying all conditions simultaneously**. These three situations are related, but they do not share the same remedy.

This lesson helps you:

- Break down a `javac` diagnostic into error location, `required`, `found`, reason, and the `where` section.
- Recognize that Java Generics are **invariant**: `List<Integer>` is not `List<Number>`.
- Understand that `CAP#1`/`CAP#2` are unknown types created by *capture conversion*, not a runtime class named CAP.
- Know why `List<? extends Number>` reads `Number` safely yet cannot accept arbitrary `Integer` additions.
- Use a `<T>` helper method when you need to preserve the same unknown element type inside **one** `List`.
- Use `? extends T` and `? super T` when transferring data between two collections with a clear type relationship.
- Read `equality`, `upper`, and `lower` constraints when the compiler reports `incompatible bounds`.
- Distinguish compile-time generic errors from `ClassCastException`/`ArrayStoreException` thrown at runtime.
- Verify valid and invalid examples on Java 17+, without guessing outputs or compiler messages.

## 2. Map of the Three Error Categories

| Category | Common Diagnostic Signs | Nature |
| --- | --- | --- |
| Type incompatibility | `incompatible types: X cannot be converted to Y` | Type X cannot be assigned to a position expecting Y under Java's allowed conversions. |
| Wildcard capture | `CAP#1`, `CAP#2`, `capture of ?`, `capture of ? extends Number` | The compiler represents a real yet unknown type behind a wildcard. |
| Conflicting inference constraints | `inference variable T has incompatible bounds` or `inferred type does not conform to upper bound(s)` | No type argument T can be found that simultaneously satisfies the constraints from target, arguments, and bounds. |

A single diagnostic can appear in multiple layers of messages. For example, a call `accepts(xs, 10)` may start with "method cannot be applied to given types", while the underlying reason is "inference variable T has incompatible bounds" and also mentions `CAP#1`. Therefore, do not read only the first line or look only for the word `error`.

### General Approach

Read errors in order:

1. **Pointed line:** which assignment, call, return expression, or `add/set` operation failed?
2. **Target type:** what does the compiler expect (`required`, target type, variable type)?
3. **Source type:** what does the compiler have (`found`, actual argument, expression type)?
4. **Relationship to prove:** subtype, invariant generic, wildcard bound, or type-variable constraint?
5. **Additional details:** `where`, `equality constraints`, `upper bounds`, `lower bounds`, `CAP#n`.
6. **Business intent:** do you want to read, write, convert types, or link two inputs? Choose a signature fix that matches the goal instead of casting blindly.

To make `javac` emit more evidence, use `-Xdiags:verbose`. The error samples below were run using:

```bash
javac --release 17 -Xdiags:verbose FileName.java
```

Exact message wording can vary across JDK releases; read the **type relationship** expressed by the diagnostic, rather than relying on CAP numbering or line wrapping.

## 3. `incompatible types`: Starting from Assignment Relationships

### 3.1. Invariance: List of Integer Is Not List of Number

**File `IncompatibleInvariant.java` — intentionally fails to compile:**

```java
import java.util.ArrayList;
import java.util.List;

class IncompatibleInvariant {
    List<Number> values = new ArrayList<Integer>();
}
```

`javac --release 17 -Xdiags:verbose IncompatibleInvariant.java` returned the main message:

```text
error: incompatible types:
ArrayList<Integer> cannot be converted to List<Number>
```

**Why?** `Integer` is a subtype of `Number`, but generic types are **invariant**: `List<Integer>` is not automatically a subtype of `List<Number>`.

If the assignment above were allowed, a `List<Number>` variable could add a `Double` to what is actually an `ArrayList<Integer>`, breaking the `Integer` element contract:

```java
// Suppose the forbidden assignment above were allowed:
List<Number> wider = new ArrayList<Integer>();
wider.add(3.14);  // Would corrupt the Integer list.
```

This is *intentionally invalid* illustrative code, not a runnable program.

### 3.2. Fixing According to Your Goal

**Goal A — want a list that can hold any `Number`:**

```java
List<Number> numbers = new ArrayList<>();
numbers.add(10);
numbers.add(3.14);
```

Here the created object is `ArrayList<Number>` via target typing, so adding both `Integer` and `Double` is valid.

**Goal B — only need to read `Number`s from a `List` of `Integer`:**

```java
List<Integer> integers = List.of(1, 2);
List<? extends Number> source = integers;
Number first = source.get(0);
```

The wildcard allows reading `Number` without **promising** that the caller can add an arbitrary `Number` into the source list.

**Goal C — need a copy capable of adding other `Number`s:**

```java
List<Integer> integers = List.of(1, 2);
List<Number> copy = new ArrayList<>(integers);
copy.add(3.14);
```

You created a new list with element type `Number`. This is not casting `List<Integer>` to `List<Number>`; the data is copied into a container with a different contract.

### 3.3. Why Can `List<Number> x = List.of(1, 2)` Be Valid?

Distinguish between:

```java
List<Number> a = List.of(1, 2);             // Valid.
List<Number> b = new ArrayList<>(List.of(1, 2)); // Valid.
// List<Number> c = new ArrayList<Integer>();   // Invalid.
```

In the first two lines, the compiler can use the **target type** to infer generic arguments for `List.of` or diamond so that the result has a type compatible with `List<Number>`. In the last line, the concrete parameterized type `ArrayList<Integer>` is written explicitly, so it cannot be converted to `List<Number>`.

A common debugging mistake is seeing two lines both "containing Integers" and concluding that the compiler behaves inconsistently. In fact, one is **generic method/constructor inference** and the other is **invariance of an already-fixed type**.

## 4. Return Types Can Also Produce `incompatible bounds`

**File `IncompatibleReturn.java` — intentionally fails to compile:**

```java
import java.util.List;

class IncompatibleReturn {
    static List<String> values() {
        return List.of(1, 2);
    }
}
```

When running `javac --release 17 -Xdiags:verbose`, the primary message observed was:

```text
error: incompatible types: inference variable E has incompatible bounds
    equality constraints: String
    lower bounds: Integer
```

Why didn't it simply say "Integer cannot be converted to String"?

`List.of(E,E)` is a **generic method**. The compiler must find `E` satisfying two sources of constraints:

- The expected return type is `List<String>`; this forces the `List<E>` structure to match the target type, yielding a condition requiring `E=String` in this context.
- The two arguments `1`, `2` have type `Integer` after boxing; `E` must be able to accept `Integer`.

No `E` simultaneously satisfies the `String` equality requirement and holds `Integer`. The compiler presents the problem as a set of **incompatible bounds** constraints.

The fix is to change the **data**, the **return type**, or perform an **intentional conversion**:

```java
static List<String> strings() {
    return List.of("1", "2");
}

static List<Integer> integers() {
    return List.of(1, 2);
}

static List<String> convertNumbers() {
    return List.of(1, 2).stream().map(String::valueOf).toList();
}
```

Do not use an unchecked cast to turn a `List` of `Integer` into a `List` of `String`. If the business logic requires `String`, create actual `String`s.

## 5. Capture Conversion: `CAP#1` Is Not a Runtime Class

### 5.1. A Wildcard Represents an Unknown Type

The declaration:

```java
List<? extends Number> numbers;
```

means: a `List` whose elements belong to **some specific subtype of `Number` unknown to the user of this reference**. It might actually be `List<Integer>`, `List<Double>`, or another `Number` subtype.

The compiler performs *capture conversion*, assigning an internal name to that unknown type, such as `CAP#1`. This name only appears in compiler diagnostics; it does not exist as a Java class that you can `new CAP#1()` or `instanceof CAP#1`.

With `List<? extends Number>`, the compiler knows **CAP is a subtype of `Number`**. It **does not know that CAP is specifically `Integer`**, even if the code just read an `Integer` through another path.

### 5.2. Reading `Number` Works, Writing `Integer` Is Not Proven Safe

**File `CaptureAdd.java` — intentionally fails to compile:**

```java
import java.util.List;

class CaptureAdd {
    static void add(List<? extends Number> numbers) {
        numbers.add(42);
    }
}
```

Run:

```bash
javac --release 17 -Xdiags:verbose CaptureAdd.java
```

Verified diagnostic:

```text
error: no suitable method found for add(int)
method List.add(CAP#1) is not applicable
(argument mismatch; int cannot be converted to CAP#1)
CAP#1 extends Number from capture of ? extends Number
```

This makes sense. The caller could pass in a `List<Double>`; if the method were allowed to add `Integer` `42`, the `Double` contract would be broken.

Reading still works:

```java
static Number firstNumber(List<? extends Number> list) {
    return list.get(0);
}
```

Because `CAP` is a subtype of `Number`, the retrieved value can be used as `Number`.

**Exception to remember:** Java allows passing `null` into many `add` operations with wildcard capture, because `null` is compatible with every reference type. However, that does **not** mean an arbitrary non-null value can be added to `List<? extends Number>`. For a read-only API, do not rely on adding `null` to mutate data.

## 6. Why Can `List<?>.set(index, list.get(...))` Still Fail?

A seemingly absurd situation: taking an element out of the same list and setting it into another slot—why does the compiler report CAP?

**File `CaptureSet.java` — intentionally fails to compile:**

```java
import java.util.List;

class CaptureSet {
    static void move(List<?> values) {
        values.set(1, values.get(0));
    }
}
```

With `-Xdiags:verbose`, the compiler reported:

```text
method set in interface List<E> cannot be applied to given types
required: int,CAP#1
found:    int,CAP#2
reason: argument mismatch; Object cannot be converted to CAP#1
CAP#1 extends Object from capture of ?
CAP#2 extends Object from capture of ?
```

**Core reason:** Two uses of a wildcard expression can be captured separately, so the compiler has no proof that `CAP#1` and `CAP#2` are identical for the `set` operation. Even though a human sees the same variable `values`, the type system cannot rely on two independent captures to automatically permit writing.

### 6.1. The Right Fix: Generic Capture Helper

Pass the wildcard input **once** into a method with a single type variable `T`:

```java
static void replaceSecondUnknown(List<?> values) {
    replaceSecondWithFirst(values);
}

private static <T> void replaceSecondWithFirst(List<T> values) {
    values.set(1, values.get(0));
}
```

Inside the helper:

- `T` represents the **unknown yet consistent element type of a specific `List`**.
- `get(0)` returns `T`.
- `set(1, T)` accepts that exact `T`.
- The compiler has sufficient proof to allow the assignment.

The caller does not need to know what `T` is. When invoking the helper, capture conversion and generic inference use a single `T` to express consistency.

**Precondition:** The list must have at least two elements and support `set`. For instance, `List.of("A","B")` does not permit modification and will throw `UnsupportedOperationException` at runtime; the helper only solves the **type issue**, not mutability or index validity.

A valid test:

```java
List<String> words = new ArrayList<>(List.of("A", "B"));
replaceSecondUnknown(words);
System.out.println(words); // [A, A]
```

The complete Java 17 program in Section 11 contains this exact helper and test.

### 6.2. When Is a Helper Needed, and When Not?

Use a helper when:

- A public method has a legitimate reason to accept `List<?>`.
- Internally it needs to perform a type-safe operation where multiple positions must use the **same unknown element type**.
- Passing the whole list to a private generic method allows capturing it once as `List<T>`.

No helper is needed just to read elements as `Object` or check `size()`:

```java
static void printSize(List<?> list) {
    System.out.println(list.size());
}
```

Do not treat a helper as a cast trick to "solve every CAP error": use it only when a genuine `T` relationship can be proven.

## 7. Two Wildcard Lists Are Two Unknown Types

**File `CaptureAcross.java` — intentionally fails to compile:**

```java
import java.util.List;

class CaptureAcross {
    static void copy(List<?> source, List<?> destination) {
        destination.add(source.get(0));
    }
}
```

The compiler reported a form like:

```text
no suitable method found for add(CAP#1)
method List.add(CAP#2) is not applicable
Object cannot be converted to CAP#2
```

`source` could be `List<String>`, while `destination` is `List<Integer>`. Two `?` wildcards **do not mean the same type**. There is no language rule permitting unconditional transfer of an element from source to destination list.

Do not "fix" this with a raw cast:

```java
// Unsafe anti-pattern:
((List) destination).add(source.get(0));
```

A raw cast bypasses compiler checks, yet can create *heap pollution* and cause `ClassCastException` when other code reads according to the generic contract.

### 7.1. PECS: Expressing Source and Destination Relationships

If the goal is to copy from a subtype of `T` into a container accepting `T` or a supertype of `T`, write:

```java
static <T> void transferFirst(
        List<? extends T> source,
        List<? super T> target) {
    target.add(source.get(0));
}
```

This is the **Producer Extends, Consumer Super** rule:

- `source` produces `T` values ⇒ `? extends T`.
- `target` consumes `T` values ⇒ `? super T`.
- `T` is declared at the method level to **link the two parameters**.

Caller:

```java
List<Integer> source = List.of(4, 7);
List<Number> target = new ArrayList<>(List.of(1.5));

transferFirst(source, target);
System.out.println(target); // [1.5, 4]
```

This is a safe copy: `Integer` is a `Number` and `List<Number>` can accept `Integer`. Note that `target` must be mutable; if `List.of(...)` is used as the destination, a runtime mutability error can still occur.

### 7.2. Do Not Blindly Assign the Same `T` to Both Containers

Another way to write it:

```java
static <T> void transferExact(List<T> source, List<T> target) {
    target.add(source.get(0));
}
```

This method shares a single `T`, but it is more restrictive for taking from `List<Integer>` and writing into `List<Number>` because generics are invariant. PECS expresses a broader relationship while remaining type-checked.

**Rule:** A capture helper solves the problem of *one wildcard list needing to reuse a single element type*. PECS solves *two containers having a clear subtype/supertype relationship*. Do not mix the two problems.

## 8. `incompatible bounds`: The Compiler Is Solving a Constraint System

A generic method can generate multiple requirements on a type variable `T`. The compiler must find type arguments that satisfy all of them simultaneously.

Intuitively, the three constraint groups can be read as:

| Diagnostic | Intuitive Reading | Example |
| --- | --- | --- |
| `equality constraints: String` | In that context, `T` is forced to equal `String` for parameterized type compatibility. | Target type `List<String>` with generic return `List<E>`. |
| `upper bounds: Number` | `T` is constrained to be a subtype of `Number` (or satisfy a corresponding upper bound). | `<T extends Number>`. |
| `lower bounds: Integer` | `T` must be a supertype of `Integer` to accept an `Integer` value as `T`. | Generic call receiving an `Integer`. |

This is a helpful reading guide when debugging; the full JLS inference algorithm also handles compatibility constraints, wildcard bounds, capture, intersection types, and many more complex cases. Do not treat this table as a complete simulator of every inference rule.

### 8.1. Conflict Between Method Bound and Argument

**File `BoundedWrong.java` — intentionally fails to compile:**

```java
import java.util.List;

class BoundedWrong {
    static <T extends Number> void use(List<T> numbers) {}

    static void demo() {
        use(List.of("A"));
    }
}
```

Run:

```bash
javac --release 17 -Xdiags:verbose BoundedWrong.java
```

The compiler printed the core message:

```text
required: List<T>
found:    List<String>
reason: inference variable E has incompatible bounds
upper bounds: Number,Object
lower bounds: String
```

The method requires `T extends Number`, yet the caller passes `List<String>`. `String` is not a subtype of `Number`. Even though the compiler infers `E` from `List.of`, no valid inference can turn `String` into `Number`.

Fix properly according to the problem:

```java
use(List.of(1, 2));           // T is compatible with Integer.
use(List.<Number>of(1, 2));   // Explicitly specify Number if needed.
```

Or if the method truly needs to process `String`, change the method's bound/algorithm. Do not force `(List<Number>)(List<?>) List.of("A")`; that cast does not turn a `String` into a `Number`.

### 8.2. Constraints from Target Type and Multiple Arguments

**File `IncompatibleBounds.java` — intentionally fails to compile:**

```java
class IncompatibleBounds {
    static <T> T first(T a, T b) {
        return a;
    }

    static void demo() {
        String value = first("A", 42);
    }
}
```

In verified Java 17 output, the diagnostic begins:

```text
incompatible types: inferred type does not conform to upper bound(s)
inferred: INT#1
upper bound(s): String,Object
```

This is followed by details about *intersection types* `INT#1` and `INT#2`. The key takeaway is that the compiler can infer a common supertype for the two arguments `String` and `Integer`, yet the result expression is required to be `String`. There is no proof that the result of that generic method must be `String` when mixed types are passed.

Ways to fix:

```java
String a = first("A", "B"); // Two String arguments.
Object b = first("A", 42);  // Result used as Object.
```

Do not change `String value` to raw `Object` and then cast to `String` later if the business logic actually requires `String`; clarify the desired input and output contracts.

**Important nuance:** `<T> T first(T a,T b)` does not force both arguments to have the exact same runtime class. The compiler can infer a common supertype. Thus using `Object` in the valid fix example is not "Java turning off generic checks", but a different inference matching the target type.

## 9. `CAP#1` and `incompatible bounds` Can Appear Together

**File `MethodCaptureWrong.java` — intentionally fails to compile:**

```java
import java.util.List;

class MethodCaptureWrong {
    static <T> void accepts(List<T> values, T item) {}

    static void demo(List<? extends Number> xs) {
        accepts(xs, 10);
    }
}
```

This program creates a case with **both capture and generic inference**. The Java 17 diagnostic includes:

```text
required: List<T>,T
found:    List<CAP#1>,int
reason: inference variable T has incompatible bounds
equality constraints: CAP#1
lower bounds: Integer
CAP#1 extends Number from capture of ? extends Number
```

Explanation:

1. The first parameter `List<T>` is matched against `List<? extends Number>`, tying inference variable `T` to the captured element type, called `CAP#1`.
2. The second parameter `T item` receives `Integer` (boxed from `10`).
3. The compiler cannot prove that `Integer` is `CAP#1` itself. `CAP#1` could be `Double` or another `Number` subtype.

Do not just look at "incompatible bounds" and arbitrarily remove `extends Number`. The issue is that **an unknown type is bound to the list while you insist on inserting an `Integer` with no proof that it has the same type**.

### How to Fix?

If the method only needs to **read** the list, change the contract:

```java
static void inspect(List<? extends Number> xs, Number other) {
    Number first = xs.get(0);
    System.out.println(first + "," + other);
}
```

If you need to add an `Integer` to a list, you need a **consumer**:

```java
static void addInteger(List<? super Integer> destination) {
    destination.add(10);
}
```

If the method truly must accept `List<T>` together with a `T` value, the caller must supply a list with a real identical type relationship, for example:

```java
static <T> void accepts(List<T> values, T item) {
    values.add(item);
}

List<Integer> values = new ArrayList<>();
accepts(values, 10);
```

Each design corresponds to a different business requirement. There is no "single cast that cures all incompatible bounds".

## 10. Understanding `extends` and `super` Correctly

| Parameter | Safe Read | Safe Write | Purpose |
| --- | --- | --- | --- |
| `List<T>` | `T` | `T` | A specific type `T` named in the method/class. |
| `List<? extends T>` | `T` | Mostly cannot add arbitrary non-null `T` | Producer: supplies subtypes of `T`. |
| `List<? super T>` | `Object` | `T` and subtypes of `T` | Consumer: accepts `T` values. |
| `List<?>` | `Object` | Cannot add arbitrary non-null values | Element type unknown; suitable for general inspection. |

Example:

```java
List<? extends Number> input = List.of(1, 2);
Number n = input.get(0);       // Valid.
// input.add(3);               // Does not compile.

List<? super Integer> sink = new ArrayList<Number>();
sink.add(3);                   // Valid.
Object obj = sink.get(0);      // Read as Object.
```

Do not say `List<? extends Number>` "is a List of Number" in the sense of being able to add any `Number`: it could have been created from a `List<Integer>` that does not permit `Double`.

Do not say `List<? super Integer>` always reads out an `Integer`: the underlying container could actually be `List<Object>`, and the compiler only guarantees the read result as `Object`.

## 11. Complete Java 17 Program

**File `GenericDiagnosticsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class GenericDiagnosticsDemo {
    static class Animal {}
    static class Dog extends Animal {}
    static class Cat extends Animal {}

    static <T> void replaceSecondWithFirst(List<T> list) {
        list.set(1, list.get(0));
    }

    static void replaceSecondUnknown(List<?> list) {
        replaceSecondWithFirst(list);
    }

    static <T> void transferFirst(
            List<? extends T> source, List<? super T> target) {
        target.add(source.get(0));
    }

    static <T extends Number & Comparable<T>> T max(T left, T right) {
        return left.compareTo(right) >= 0 ? left : right;
    }

    static <T> T first(T a, T b) {
        return a;
    }

    static void showBounds(List<? extends Number> list) {
        Number value = list.get(0);
        System.out.println("readNumber=" + value);
    }

    public static void main(String[] args) {
        List<Dog> dogs = new ArrayList<>(List.of(new Dog()));
        List<? extends Animal> animals = dogs;
        System.out.println("extendsReadable=" + (animals.get(0) instanceof Dog));

        List<? super Dog> dogSink = new ArrayList<Animal>();
        dogSink.add(new Dog());
        System.out.println("superSize=" + dogSink.size());

        List<String> words = new ArrayList<>(List.of("A", "B"));
        replaceSecondUnknown(words);
        System.out.println("captureHelper=" + words);

        List<Integer> source = List.of(4, 7);
        List<Number> target = new ArrayList<>(List.of(1.5));
        transferFirst(source, target);
        System.out.println("transfer=" + target);

        showBounds(List.of(42));
        System.out.println("boundedMax=" + max(3, 8));
        System.out.println("targetTyped=" + first("A", "B"));
        System.out.println("wildcardCount="
                + Collections.frequency(List.of(1, 1, 2), 1));
    }
}
```

Compile and run commands:

```bash
javac --release 17 -Xlint:all GenericDiagnosticsDemo.java
java GenericDiagnosticsDemo
```

**Verified stdout:**

```text
extendsReadable=true
superSize=1
captureHelper=[A, A]
transfer=[1.5, 4]
readNumber=42
boundedMax=8
targetTyped=A
wildcardCount=2
```

This program compiled with `javac --release 17 -Xlint:all` with zero warnings in verification.

### 11.1. Producer/Consumer with Inheritance

`List<Dog>` can be used as `List<? extends Animal>`; `Animal` can be read, but an arbitrary `Cat` cannot be added. `List<? super Dog>` accepts `Dog` safely, whereas reading back only guarantees `Object`.

### 11.2. Capture Helper Works Because There Is Only One `T`

`replaceSecondUnknown` calls `replaceSecondWithFirst`. Inside the helper, both the value obtained from `get(0)` and the parameter to `set(1,...)` share the same `T`, so `[A,A]` is valid.

### 11.3. PECS Transfers `Integer` to `Number`

`transferFirst` reads `Integer` from the source and adds it to a `List<Number>`. No casts, no heap pollution.

### 11.4. Bounds on `T` in `max`

`<T extends Number & Comparable<T>>` requires both `Number` behavior and self-comparability via `Comparable<T>`. Calling `max(3,8)` returns `8`; not every pair of different `Number` subtypes satisfies a single `T`. When type arguments differ, a different algorithm/Comparator may be needed.

### 11.5. Generic Method with a Valid Target Type

`first("A","B")` returns a `String` under a `String` target; there is no inference conflict. Contrast this with `String s = first("A",42)` in Section 8, where the compiler lacks the same guarantee.

## 12. Table of Intentionally Failing Files for Reading Practice

Each of the following examples is a **separate file**; do not combine them with `GenericDiagnosticsDemo.java` and expect the build to still succeed.

| File Name | Error-Causing Line | Central Diagnostic |
| --- | --- | --- |
| `IncompatibleInvariant.java` | `List<Number> x = new ArrayList<Integer>();` | `incompatible types ... cannot be converted` |
| `IncompatibleReturn.java` | `return List.of(1,2)` when returning `List<String>` | `inference variable E has incompatible bounds`; equality `String`, lower `Integer` |
| `CaptureAdd.java` | `List<? extends Number>.add(42)` | `int cannot be converted to CAP#1` |
| `CaptureSet.java` | `List<?>.set(1,list.get(0))` | `required CAP#1, found CAP#2` |
| `CaptureAcross.java` | `destination.add(source.get(0))` with two `List<?>` | Two independent captures do not prove compatibility |
| `IncompatibleBounds.java` | `String s = first("A",42)` | `inferred type does not conform to upper bound(s)` |
| `BoundedWrong.java` | `use(List.of("A"))` with `T extends Number` | Upper `Number` conflicts with lower `String` |
| `MethodCaptureWrong.java` | `accepts(xs,10)` with `xs:List<? extends Number>` | Equality `CAP#1` conflicts with lower `Integer` |

A negative compilation test should verify that `javac` **returns a non-zero exit code** and that the message is of the expected kind, rather than merely checking that the program "prints nothing". The diagnostics above were reproduced with Java 17 and verbose mode.

## 13. Compiler Commands That Aid Better Analysis

### 13.1. Enabling Detailed Diagnostics

```bash
javac --release 17 -Xdiags:verbose IncompatibleBounds.java
```

Verbose mode typically shows `required/found`, capture variables, and more constraint details.

### 13.2. Enabling Generics Warnings

```bash
javac --release 17 -Xlint:unchecked,rawtypes GenericDiagnosticsDemo.java
```

If source code contains raw types or unchecked casts, warnings help locate where generic relationships were lost. In the complete program in Section 11, the illustrative errors were fixed without needing unchecked casts.

### 13.3. Distinguishing Errors from Warnings

- `incompatible types`, `generic array creation`, `name clash`, and certain `capture` errors at compile time **block the build**.
- `unchecked cast`/`rawtypes` are usually **warnings** in contexts permitted by Java.
- `ClassCastException` and `ArrayStoreException` are **runtime exceptions**, often following a raw alias/unchecked operation or an invalid write into a covariant array.

Do not use `@SuppressWarnings("unchecked")` as a "fix" for an invalid `add` call. The annotation does not turn `CAP#1` into `Integer`, create a missing subtype relationship, or change the data.

### 13.4. Using Negative Tests Properly

A systematic way to study:

1. Save each failing snippet in a file matching the class name in the table.
2. Compile one file separately.
3. Note `required`, `found`, and `where` or constraints.
4. Change **only one contract factor** at a time: target type, type bound, wildcard, or generic helper.
5. Recompile to confirm.
6. Add a runtime test for the fixed case, especially with collection mutation.

Do not put multiple independent errors into one file and draw conclusions from the first error; the first error can cause the compiler to skip or infer subsequent lines differently.

## 14. When Should You Fix the Method Signature vs. the Caller?

### 14.1. Error at the Caller

If the API requires `List<Number>` because internally it must add both `Integer` and `Double`, the caller should pass an actual `List<Number>`:

```java
List<Number> values = new ArrayList<>();
values.add(10);
values.add(3.5);
```

Do not relax the API to `List<? extends Number>` if the method genuinely **needs to write `Number`** into the list. The `extends` wildcard forbids that operation.

### 14.2. Error at the API

If the API only sums `Number` elements yet requires `List<Number>`, the signature may be overly strict:

```java
static double sum(List<? extends Number> values) {
    double total = 0;
    for (Number x : values) {
        total += x.doubleValue();
    }
    return total;
}
```

This method accepts `List<Integer>`, `List<Double>`, and `List<Number>`. It does not write, so the `extends` wildcard expresses the intent accurately.

### 14.3. Error Due to an Ambiguous Contract

If a method tries to insert an `Integer` object into `List<? extends Number>`, you need to decide:

- Read-only? Do not call `add`.
- Write `Integer`? Accept `List<? super Integer>`.
- Write a `T` matching the list? Use `List<T>` and a related `T` parameter, requiring the caller to provide a properly typed list.
- Copy elements between two containers? Use `List<? extends T>` and `List<? super T>`.

Fixing a generic error is not merely silencing the compiler; it is **defining the API's read/write permissions and data guarantees**.

## 15. Messages That Look Similar but Have Different Causes

### "Found List<String>, required List<T>"

Could be:

- `T` is bounded by `extends Number`.
- `T` is constrained by another argument.
- `T` is inferred from a target return type.
- `CAP` of a wildcard requires a consistent unknown type.

Read `where` and the constraints before adding a cast.

### "Required CAP#1, found CAP#2"

Could be two independent wildcards or two captures of wildcard expressions that the compiler cannot prove are the same type. If operating on only **one list**, a generic capture helper can create a unified `T`. If transferring data between **two lists**, the source/destination relationship must be expressed in the signature, and sometimes there is no safe way to perform the operation the caller requested.

### "Inference variable T has incompatible bounds"

Constraints are conflicting. This does not necessarily mean "Java's compiler is too weak" or "generics are too complex so ignore it". Sketch the three constraint sources:

```text
Target / return context
        |
        v
Inference variable T <---- actual arguments
        ^
        |
Declared bounds / wildcards

T must satisfy all constraint arrows.
```

If they cannot all be true together, either one requirement must change or the data must change — for example, you cannot demand `List<String>` from `List.of(1,2)` without converting `Integer` to `String`.

## 16. Common Supertypes and *Intersection Types*

In `String s = first("A",42)`, `javac` may print `INT#1`, `INT#2` along with interfaces such as `Serializable` and `Comparable`. This is a description of an **intersection type produced by inference** to represent a complex common type of the arguments. It does not mean the runtime creates a class named `INT#1`.

Do not try to memorize the list of interfaces the compiler prints in each JDK. The important part is:

- The generic method tries to find a single `T` for both `String` and `Integer`.
- The target requires the result to be used as `String`.
- The inferred common supertype is not necessarily a subtype of `String`.
- Therefore, the assignment is blocked.

A readable and honest solution is to change the target to `Object` if business logic permits, or make the input types uniform. A `String` cast can only be a risky runtime decision and cannot replace compile-time proof.

## 17. Capture Conversion Is Not Arbitrary Wildcard Covariance

Wildcards permit certain assignment relationships:

```java
List<Integer> a = List.of(1, 2);
List<? extends Number> b = a;
Number n = b.get(0);
```

Once `b` is used, however, the compiler needs to remember "some specific type extending `Number`" rather than assuming it is `Number`. Capture conversion formalizes this.

Similarly:

```java
List<Number> sink = new ArrayList<>();
List<? super Integer> consumer = sink;
consumer.add(5);
Object readBack = consumer.get(0);
```

`? super Integer` allows writing `Integer`, while the general read type is `Object` because the actual container might be `List<Object>`.

Do not confuse wildcards with array covariance: `Number[]` can reference an `Integer[]`, yet the JVM checks array stores and can throw `ArrayStoreException`; generics primarily protect through the compiler, and the subtype relationship between `List<Integer>` and `List<Number>` does not work like array covariance.

## 18. Common Misconceptions

| Claim | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| "`Integer` extends `Number` so `List<Integer>` extends `List<Number>`." | Generic invariance. | Read through `List<? extends Number>` or copy into `List<Number>`. |
| "`? extends Number` means any `Number` can be added." | The element type might be an unknown specific `Integer`/`Double`. | Only read `Number`, or change the API to a consumer. |
| "`CAP#1` is a class you can cast to." | `CAP` is an internal capture-conversion variable. | Express the relationship with a `<T>` helper or bounds. |
| "Two `List<?>` share the same `?` so they have the same type." | Each wildcard can denote a different element type. | Do not copy arbitrarily; use PECS if a subtype relation exists. |
| "`List<?>.set(i,list.get(j))` definitely compiles." | Captures can differ across the two expressions. | Use a capture helper taking `List<T>` once. |
| "A generic helper solves every CAP error." | It cannot prove two independent wildcard lists have the same type. | Use properly typed source/destination or adjust requirements. |
| "`lower bounds: Integer` means `T` must be `Integer`." | It usually requires `T` to accept `Integer`, not necessarily equal `Integer`. | Inspect equality and upper bounds too. |
| "Adding an unchecked cast is the solution." | Casting drops checks; it does not change the underlying data's type. | Fix the API/target or actually convert values. |
| "`Incompatible bounds` is always caused by a wrong `extends` in the declaration." | Constraints also come from return target, arguments, and wildcards. | Read the entire diagnostic. |
| "If the build runs, generic values are always right at runtime." | Raw types/unchecked operations can cause heap pollution. | Keep warnings enabled and validate boundaries. |
| "Every list can be added to once generics compile." | Immutable lists can throw `UnsupportedOperationException`. | Separate type safety from mutability contracts. |

## 19. Practical Debugging Workflow

1. **Isolate the file and expression** causing the compiler error. Do not edit all generic parameters at once.
2. **Run `javac --release 17 -Xdiags:verbose`** to view the full constraint sections.
3. **Identify the static types** of all arguments, the target variable, and the method return type.
4. **Check invariance:** Are you trying to place `List<Subclass>` into `List<Superclass>`?
5. **Look for wildcards:** If `? extends`, `? super`, or `?` is present, determine whether the method is reading or writing.
6. **Read CAPs:** Do the CAPs come from the same `List` needing a capture helper, or two `List`s without a proven relationship?
7. **Read constraints:** What equality, upper, and lower bounds are imposed on `T` from each position?
8. **Find the real conflict:** `String` does not extend `Number`; `Integer` cannot be guaranteed to match a `CAP` that might be `Double`.
9. **Choose a business-aligned fix:** Change the target, change the data, convert elements, use a wildcard, generic helper, PECS, or a class token when runtime checking is genuinely performed.
10. **Recompile both valid and invalid cases.** Make sure the error disappeared for the right reason, not because an unchecked warning masked it.
11. **Run mutability and logic tests.** A method that compiles validly can still hit `IndexOutOfBoundsException` or `UnsupportedOperationException`.
12. **Review the public API:** Keep generic contracts clear and simple; do not force callers to use raw types.

## 20. Exercises and Answers

### Exercise 1: Why Can't This Be Assigned Directly?

```java
List<Number> values = new ArrayList<Integer>();
```

**Answer:** Generic invariance. `ArrayList<Integer>` is not a subtype of `List<Number>`; if allowed, the caller could add a `Double` to a list of `Integer`.

### Exercise 2: When Is `List<? extends Number>` Appropriate?

**Answer:** When the method only needs to **read** values usable as `Number` and does not add arbitrary `Number`s into the source.

### Exercise 3: What Does `CAP#1` Mean?

**Answer:** A fresh type variable generated by the compiler when capturing a wildcard; for example, an unknown subtype of `Number`. It is not a runtime class.

### Exercise 4: `List<?>` Fails When Getting an Element and Setting It Back at Another Slot—What Should You Do?

**Answer:** Pass `List<?>` into a `<T>` helper accepting `List<T>`; inside the helper, `get` and `set` both use `T`. Ensure the list is mutable and indices are valid.

### Exercise 5: Can You Copy from `List<?>` into Another `List<?>`?

**Answer:** Not in general. The two wildcards may represent two different types. You need a `? extends T` source and `? super T` destination, or another typed contract.

### Exercise 6: Does `lower bounds: Integer` Mean `T` Equals `Integer`?

**Answer:** Not necessarily. It usually requires `T` to be a supertype broad enough to accept an `Integer`; you must also check equality and upper constraints.

### Exercise 7: Does `<T extends Number> void use(List<T>)` Accept a `List` of `String`?

**Answer:** No. `String` is not a subtype of `Number`, so the compiler can report incompatible bounds.

### Exercise 8: Why Is `String s = first("A",42)` Hard to Infer?

**Answer:** Two inputs of different types can lead the compiler to a common supertype not guaranteed to be `String`, while the target requires `String`.

### Exercise 9: What Needs Fixing in `List<String> values() { return List.of(1,2); }`?

**Answer:** Return a `List` of `Integer` if that matches the data, return `String` literals, or actually convert the `Integer`s to `String`s. Do not use an unchecked cast.

### Exercise 10: When Do You Use `List<? super Integer>`?

**Answer:** When the API needs to **write `Integer`** into a collection that could be `List<Integer>`, `List<Number>`, or `List<Object>`. Reading from it generally only guarantees `Object`.

### Exercise 11: Does a Generic Helper Solve `accepts(xs,10)` When `xs` Is `List<? extends Number>`?

**Answer:** Not automatically. The element type of `xs` might be `Double`; there is no proof that `Integer` belongs to that exact captured type. Change the contract or pick a compatible list/value.

### Exercise 12: Why Do You Need Runtime Tests After Fixing Compile Errors?

**Answer:** Type safety does not guarantee that the list supports modification, has enough elements, or that input data satisfies business contracts. `List.of` can still throw `UnsupportedOperationException` on `set/add`.

## 21. Summary

All three major message groups stem from one principle: **the compiler permits an operation only when it can prove the required type relationships.**

- `incompatible types`: invalid assignment/return relationship, such as `List<Integer>` not being usable as `List<Number>`.
- `capture of ?` and `CAP#n`: an element type exists yet is unknown; do not assume all wildcards represent the same type.
- `incompatible bounds`: generic inference must satisfy target, arguments, and bounds simultaneously; when constraints conflict, no valid type argument exists.

Choose fixes based on **read/write permissions and actual data relationships**: `extends` wildcards for producers, `super` for consumers, a generic helper for one unified capture, PECS to transfer between two collections with a subtype relationship, and real data conversion when changing element types. Do not make unchecked casts your default fallback.

**Remember:** When you see `CAP#1` or "incompatible bounds", ask *which type relationship does the compiler lack proof of?* — and fix that exact relationship in the API design.