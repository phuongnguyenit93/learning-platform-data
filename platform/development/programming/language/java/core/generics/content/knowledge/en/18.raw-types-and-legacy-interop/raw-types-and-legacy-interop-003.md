# Converting from a Parameterized Type to a Raw Type in Java Generics

A **parameterized type** supplies type argument information, such as `List<String>`, `Map<String, Integer>`, or `Box<Customer>`. A **raw type** is the use of a generic class or interface name without writing the corresponding type arguments: `List`, `Map`, or `Box`.

When you write `List raw = typed;` where `typed` has type `List<String>`, Java permits this assignment to interoperate with legacy code. However, from the point where the `raw` variable is used, the compiler **no longer enforces the `String` element contract when calling operations through the raw variable**. That conversion is especially dangerous if other code inserts incompatible elements into the same collection.

The most important takeaway: **converting from a parameterized type to a raw type does not create a new list, does not remove elements, and does not check or change the type of stored data**. It changes **the type information the compiler uses for the reference**, while both variables may still point to the same runtime object.

## 1. Definition and Syntax

Example with the collections library:

```java
import java.util.ArrayList;
import java.util.List;

// Illustrative code; place inside a valid Java method or program.
List<String> names = new ArrayList<>();
names.add("An");

List raw = names; // Convert from List<String> to raw List
```

Here:

- `List<String>`: knows that generic methods of `List<E>` are being used with `E = String`.
- `List`: the raw type of interface `List<E>`; method calls are subject to erasure and raw type rules.
- `raw = names`: assigns the exact same **reference** to a variable whose static type carries less information; it never copies the collection.
- `new ArrayList<>()`: creates an `ArrayList` object as usual; the diamond `<>` syntax lets the compiler infer type arguments at source level and does not create a new runtime class `ArrayList<String>`.

Raw types are retained by Java mainly to support **migration compatibility** with legacy APIs and source code predating generics. In modern code, declare parameterized types or wildcards whenever possible.

### Distinguishing raw types from similar-looking types

```java
// Each line is a different way of declaring a reference:
List<String> exact;     // String elements
List<?> unknown;        // List of an unknown element type
List<Object> objects;   // List with E = Object
List raw;               // Raw List, drops generic checks at the raw usage site
```

`List<?>` is **not** a raw type; it is a parameterized type with a wildcard, still safety-checked by the compiler according to what can be proved. `List<Object>` is also not equivalent to `List<String>`: Java generics are invariant, so you cannot assign `List<String>` directly to `List<Object>`.

## 2. Conversion Direction `List<String>` → `List`: Valid, but Loses Guarantees on the Receiving Side

Consider this example:

```java
List<String> names = new ArrayList<>();
names.add("An");

List raw = names;  // Valid
Object item = raw.get(0);
raw.add(42);       // Syntactically valid, with unchecked warning
```

With static type `List<String>`, `names.add(42)` **does not compile** because `42` is boxed into an `Integer`, not a `String`. Yet `raw.add(42)` still compiles: using raw `List` causes the parameter of `add(E)` to be checked against the erased type `Object`.

Thus, the dangerous operation is **using the raw reference to write elements**, whereas `List raw = names;` itself has not yet corrupted the data.

With `javac -Xlint:rawtypes -Xlint:unchecked`, you should check two kinds of diagnostics:

- **`rawtypes`**: where a generic type is used without type arguments, such as the declaration `List raw`.
- **`unchecked`**: an operation whose generic safety is not guaranteed by the compiler, such as `raw.add(42)`.

Warning text formatting can differ across JDKs and compiler options. Do not equate the fact that assigning to raw is allowed with all subsequent operations through raw being safe.

### No copy is created and no separate "raw class" exists

With the same object:

```java
// Illustrative snippet in the same method:
List<String> typed = new ArrayList<>();
List raw = typed;
System.out.println(typed == raw); // true
```

Both variables reference **one** collection. Standard Java generics use type erasure, so `List<String>` and raw `List` are two views through the source-level type system; they do not represent two copies of the data.

If `raw.add(123)` runs, `typed` can see the `Integer` element through the same collection. When reading as `String`, the compiler may insert a runtime cast and throw `ClassCastException`.

## 3. Looking Ahead at the Reverse Direction: Raw → Parameterized Does Not Validate Data

The direction studied here is **`List<String>` → raw `List`**: valid, though code using the raw variable loses the `String` element constraint. The reverse direction **raw `List` → `List<String>`** is also commonly permitted by the compiler for legacy compatibility, but it emits an **unchecked conversion warning**:

```java
List<String> typed = new ArrayList<>();
List raw = typed;              // Convert to raw
raw.add(42);                   // Unchecked call, may corrupt data
List<String> recovered = raw; // Unchecked conversion, does NOT validate String
```

This is a snippet inside a method and requires importing `java.util.List` and `java.util.ArrayList`. There is no copying or element-by-element scanning in these assignments; `recovered` can observe the `Integer` element.

| Direction | Compiler proof that is missing |
| --- | --- |
| Typed → raw | Calls through the raw receiver are no longer checked against the previous argument |
| Raw → typed | Cannot prove the actual data matches the new type argument |

If you only need to iterate without knowing the element type, use `List<?>`. If you need to return a trustworthy `List<String>`, check each element and manage aliases; an **unchecked cast/conversion** alone does not solve it. The main focus of this lesson remains the impact of **typed → raw** on subsequent operations.

## 4. Heap Pollution: Code Compiles, Yet Data Violates the Declared Type

```java
// Snippet intentionally creating wrong-typed data:
List<String> names = new ArrayList<>();
names.add("An");

List raw = names;
raw.add(42);                // Mixes Integer into List<String>
String first = names.get(1); // May throw ClassCastException
```

The situation where a parameterized-type variable points to data that no longer satisfies the type contract it claims is called **heap pollution**. In the example, heap pollution occurs after adding an `Integer` through raw `List`.

Why does the failure usually appear **on read**, rather than immediately when adding?

1. `raw.add(42)` is checked against the erasure of `List.add(E)`, whose corresponding parameter is `Object`, so the runtime collection allows adding `Integer`.
2. The `names` variable is still viewed by the compiler as `List<String>`. When `names.get(1)` must produce a `String` result, bytecode can contain `checkcast java/lang/String`.
3. `Integer` cannot be cast to `String`, so `ClassCastException` occurs.

Not every read fails. For example, `Object x = names.get(1)` can receive the `Integer` as an `Object`; failure depends on operations requiring a concrete runtime type check.

That is why an unchecked warning deserves attention even when a program runs "fine" on a few test inputs.

## 5. How Does Type Erasure Relate to Converting to Raw?

Java generics use **type erasure**: an unbounded type parameter is erased to `Object`, while a bounded type parameter is erased to its first bound. For example, with `List<E>`, `E` erases to `Object`, so generic operations viewed through a raw receiver can accept/return `Object`.

However, **not every raw generic method returns `Object`**. Consider:

```java
// Snippet illustrating signatures, not a standalone program.
class NumericBox<N extends Number> {
    private N value;

    NumericBox(N value) {
        this.value = value;
    }

    N get() {
        return value;
    }

    void set(N value) {
        this.value = value;
    }
}
```

When using raw `NumericBox`, `N` erases to `Number`. Thus `rawBox.get()` has return type `Number` when observed via the erased type; `rawBox.set(1.5)` can be called with a `Double` because the method accepts `Number`, even though it is no longer bound to a concrete type argument.

```java
// Snippet continuing the NumericBox example:
NumericBox<Integer> integers = new NumericBox<>(10);
NumericBox rawBox = integers;
Number current = rawBox.get(); // Valid; not Object by default
rawBox.set(1.5);               // Unchecked call; may cause heap pollution
// Integer later = integers.get(); // May throw ClassCastException
```

Therefore, **a raw type is using a generic declaration while omitting type arguments in source code**; **erasure is the compilation mechanism** explaining why those generic signatures can be used in erased form. The two concepts are related, not completely synonymous.

## 6. Complete Runnable Java 17+ Program

Save file **`RawTypeConversionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class RawTypeConversionDemo {
    static List<String> checkedCopy(List<?> values) {
        List<String> result = new ArrayList<>();

        for (Object value : values) {
            if (!(value instanceof String text)) {
                throw new IllegalArgumentException(
                        "Phan tu khong phai String");
            }
            result.add(text);
        }
        return result;
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("An", "Binh"));

        // Convert from parameterized type to raw type:
        List raw = names;
        System.out.println("Cung doi tuong: " + (raw == names));
        System.out.println("Doc qua raw: " + raw.get(0));

        // Wrong-typed operation via raw receiver (unchecked):
        raw.add(42);
        System.out.println("Sau raw.add: " + names);

        try {
            String third = names.get(2);
            System.out.println(third);
        } catch (ClassCastException exception) {
            System.out.println("Doc sai kieu: ClassCastException");
        }

        // Convert back from raw to parameterized type (unchecked):
        List<String> uncheckedBack = raw;
        System.out.println("Gan raw ve List<String> cung doi tuong: "
                + (uncheckedBack == names));

        // Read via wildcard without verifying elements are String:
        List<?> readOnlyView = names;
        System.out.println("Qua List<?>: " + readOnlyView.get(0));

        try {
            checkedCopy(readOnlyView);
        } catch (IllegalArgumentException exception) {
            System.out.println("Kiem tra du lieu: tu choi Integer");
        }

        List<String> clean = checkedCopy(List.of("Lan", "Mai"));
        System.out.println("Ban sao an toan: " + clean);
    }
}
```

Use JDK 17 or later:

```bash
javac -encoding UTF-8 -Xlint:rawtypes -Xlint:unchecked RawTypeConversionDemo.java
java RawTypeConversionDemo
```

Program **standard output** (excluding warnings printed by the compiler during compilation):

```text
Cung doi tuong: true
Doc qua raw: An
Sau raw.add: [An, Binh, 42]
Doc sai kieu: ClassCastException
Gan raw ve List<String> cung doi tuong: true
Qua List<?>: An
Kiem tra du lieu: tu choi Integer
Ban sao an toan: [Lan, Mai]
```

Meaning of each group:

- `Cung doi tuong: true`: converting to raw only changes the **static type of the variable**, without cloning the list.
- `raw.add(42)`: an intentional example causing heap pollution so you can observe the consequence; do not use in business code.
- `ClassCastException`: occurs when a value retrieved from the list must be treated as `String` while the actual value is `Integer`.
- `List<String> uncheckedBack = raw`: the compiler can warn even though at runtime it is still the same list. Not throwing immediately at assignment **does not guarantee** all elements have the right type.
- `List<?> readOnlyView`: restricts adding incompatible elements through this view. It does not filter or repair already-polluted data.
- `checkedCopy`: checks each actual element before building a new `ArrayList<String>`; thus the result is guaranteed according to the check in the function. The example leaves the source list intact.

Running with `-Xlint:rawtypes` and `-Xlint:unchecked` also reveals raw type usage, the unsafe `add` operation, and the raw → `List<String>` conversion. Warnings are output from the **compilation command**, not the standard output listed above.

## 7. Comparing Raw Types with `List<?>`: Why Is Wildcard Better When the Element Type Is Unknown?

When an API only needs to inspect elements without needing to know their concrete type, use:

```java
static void printAll(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

Calls to `printAll(List<String>)` or `printAll(List<Integer>)` are both valid. The type `List<?>` explicitly states "this is a list with an unknown element type" and **preserves generic rules**, thereby disallowing arbitrary additions of `String`, `Integer`, or `Object` via the `List<?>` reference. Normally only `null` can be added via `add`, since `null` is compatible with every reference type.

Contrast:

```java
// Illustrative snippet; the error-commented line does not compile.
List<String> source = new ArrayList<>();
List<?> wildcard = source;
List raw = source;

// wildcard.add("A"); // Compile error: unknown capture type
raw.add("A");         // Compiles, but with unchecked warning
Object value = wildcard.get(0); // Valid if an element exists
```

That the last line requires the list to have an element before calling `get(0)` is only about index bounds; `List<?>` does not prevent `IndexOutOfBoundsException` by itself.

For a collection that receives or supplies values of a specific type, you can use bounded wildcards:

- `List<? extends Number>`: suitable when you need to read elements as `Number`.
- `List<? super Integer>`: suitable when you need to add `Integer` into a consumer, though reading back can only assume `Object`.

This is the **PECS (Producer Extends, Consumer Super)** idea. Using wildcards purposefully still enables flexible interop without needing raw types.

## 8. A Method Accepting a Raw Type Can Break the Caller's Contract

Suppose a legacy API declares:

```java
// Code illustrating a legacy API; not a standalone program.
static void legacyAppend(List values) {
    values.add(100);
}
```

A modern caller passes `List<String>`:

```java
List<String> names = new ArrayList<>(List.of("An"));
legacyAppend(names); // Valid, but the raw API may add an Integer
```

The caller's compiler cannot prove whether the body of `legacyAppend` preserves `String` elements. If the method actually adds an `Integer`, the caller's list becomes type-polluted and an error may only surface when reading out as `String`.

For code you control, use a generic method with a proper contract:

```java
static <T> void append(List<T> values, T value) {
    values.add(value);
}

// append(names, "Binh"); // Valid
// append(names, 100);    // Rejected when no valid type inference exists
```

With the generic signature above, if `names` is `List<String>`, passing an `Integer` value cannot be accepted simply by "inferring T as Object", because `List<T>` is invariant. This is a helpful constraint that keeps data properly typed.

### How to handle a legacy API that cannot be modified?

You can choose one of the following approaches depending on the contract:

1. **Do not let the legacy API directly mutate critical data:** pass a copy or an unmodifiable view when the API only needs to read; keep in mind that if the legacy API actually tries `add`, it will fail.
2. **Validate and copy data on return:** use `List<?>` to read elements as `Object`, check with `instanceof` or `Class<T>.cast`, then build a new parameterized collection.
3. **Write an adapter at the system boundary:** isolate raw types and unchecked conversions in one small place, document safety preconditions, and avoid letting raw types spread across the application.
4. **Generify signatures when you can edit the source:** add appropriate type parameters or wildcards, then update callers and run compiler checks.

Whether `Collections.unmodifiableList` or `List.copyOf` is appropriate also depends on whether the API needs to modify the list, whether it accepts `null`, and whether you want a view or a copy. There is no automatic conversion solution that guarantees turning an untrusted raw `List` into `List<String>` with a single cast.

## 9. Is Casting `(List<String>) raw` Safer Than Assignment?

No. Consider:

```java
// Snippet illustrating an unchecked cast:
List raw = new ArrayList();
raw.add(42);
List<String> converted = (List<String>) raw;
```

Casting from raw `List` to `List<String>` cannot verify at runtime that `String` is the element type of each value. Because Java generics undergo type erasure, a cast to such a parameterized type generally checks only the raw type structure supported at runtime, and cannot iterate and verify every element.

If an element has the wrong type, `String s = converted.get(0)` is what can throw `ClassCastException`. Hence, **adding an explicit cast is not a data validation solution**. Use a checked conversion procedure, such as `checkedCopy(List<?>)` in the complete example.

If you must keep an unchecked cast due to a proven external library contract, place it in a dedicated adapter with minimal `@SuppressWarnings("unchecked")` scope. Even then, you need a strong invariant guaranteeing the data source conforms and tests covering data paths—never treat the annotation as a fix for runtime errors.

## 10. Impact of Raw Types on Method Invocation

Using a raw receiver can change the observed parameter and return types of generic members according to erasure:

```java
// Illustrative snippet only, not standalone.
class Store<T> {
    private T item;

    void set(T value) {
        item = value;
    }

    T get() {
        return item;
    }
}

Store<String> typed = new Store<>();
Store rawStore = typed;    // Raw Store
rawStore.set(123);        // Unchecked call
Object value = rawStore.get();
// String text = typed.get(); // Possible ClassCastException
```

Here, type parameter `T` is unbounded, so `Store<T>.set` and `Store<T>.get` are seen via the erased type `Object` when called on a raw receiver. But if the type parameter has a bound, the erased type can be `Number`, `CharSequence`, or the appropriate first bound.

When a generic class has **its own generic methods**, using a raw receiver can also affect how instance member signatures are viewed under raw type rules. You should not assume every method called through a raw receiver retains full generic inference as it does with a parameterized reference. The reliable approach is to give variables/callers proper parameterized or wildcard types and let the compiler check calls.

**Static members** of a generic class do not depend on an instance attached to a specific type argument; you do not write `Store<String>.someStaticMethod()` to create a separate static method per type `T`.

## 11. What Raw Types Do Not Do

- **Do not create a new object.** `List raw = typed;` keeps the exact same reference.
- **Do not turn `String` elements into `Object` in the sense of changing runtime class.** A `String` remains a `String` object; only how the compiler views the value changes.
- **Are not synonymous with `List<Object>`.** A raw `List` accepts `List<String>`, whereas `List<Object>` cannot directly accept `List<String>`.
- **Do not make the runtime automatically check all contents.** Converting back or casting to `List<String>` does not scan and validate elements.
- **Do not disable all Java type checks.** Raw `List` is still a `List`, and non-generic constraints, ordinary cast checks, access restrictions, and Java syntax rules still apply.
- **Do not make `List<String>` and `List<Integer>` directly assignable to each other.** Generic invariance is still enforced in source code that specifies type arguments.
- **Do not mean every error occurs at `raw.add`.** Wrong-typed data often surfaces only when parameterized code tries to read it as a concrete type.

## 12. When Does Using a Raw Type Still Make Sense?

Raw types mainly appear when interacting with legacy code or APIs designed before generics, or at unavoidable integration boundaries. In those situations:

1. Confine raw types to a small adapter with a clear functional name.
2. Use compiler warnings `-Xlint:rawtypes` and `-Xlint:unchecked` as signals to find paths risking heap pollution.
3. Evaluate whether the API is **allowed to write** to the collection; only use an unmodifiable view when the contract permits it.
4. When data arrives from an untrusted source, validate each element and copy to the right type; do not merely cast.
5. Avoid suppressing warnings with `@SuppressWarnings` across an entire class or project.

In new Java code, if the element type is unknown, **prefer `List<?>` over raw `List`**. If you know the type to read or write, use the appropriate parameterized type or bounded wildcard.

## 13. Self-Check Exercises

**Question 1.** Does `List<String> strings = new ArrayList<>(); List raw = strings;` create a new list?

No. `strings == raw` is `true` because they are two references to the same object.

**Question 2.** Why does `raw.add(42)` compile when `strings.add(42)` does not?

Through a raw receiver, the `String` type argument constraint is not applied to `add(E)`; the erased signature can accept `Object`. The compiler normally emits an unchecked warning.

**Question 3.** Does `List<String> casted = (List<String>) raw;` check that all elements are `String`?

No. Casting to a parameterized collection is limited by type erasure; to validate contents you must check each element manually or rely on a source with a guaranteed contract.

**Question 4.** Is `List<?> unknown = strings;` safer than `List raw = strings;`?

Yes, if you need to accept a list of unknown element type while still wanting the compiler to prevent arbitrary additions. However, `List<?>` does not fix heap pollution that has already occurred earlier.

**Question 5.** Why does `List<String> back = raw;` produce an unchecked warning?

Because the compiler has no proof that every element currently stored in the raw list satisfies `String`; the assignment does not scan contents to verify.

**Question 6.** Can `List<Object> objects = strings;` be used instead of a raw type?

No. `List<String>` is not a subtype of `List<Object>` because Java generics are invariant. If you need to view all elements at the `Object` level, consider `List<?>` or an appropriate wildcard.

## 14. Rules to Remember

```text
List<String> typed = ...;
List raw = typed;          // Allowed; same object, generic info lost on raw variable
raw.add(42);              // Unchecked; may cause heap pollution
List<String> back = raw;  // Unchecked conversion; does NOT re-validate elements
List<?> view = typed;     // Safer parameterized view when the type argument is unknown
```

**Conclusion:** converting from a **parameterized type to a raw type** is a valid conversion for maintaining interoperability with legacy Java code, yet it loses part of generic type checking for operations through the raw reference. The biggest risk is raw code mutating a shared collection with wrong-typed data, causing errors to surface only when parameterized code reads it back. For new code, keep parameterized types or wildcards, isolate legacy APIs, and validate actual data before converting back to a concrete type.