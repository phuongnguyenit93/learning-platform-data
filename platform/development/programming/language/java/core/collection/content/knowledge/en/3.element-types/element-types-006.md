# Raw Types, Type Casting, and Heap Pollution in Collections

Generics allow a variable such as `List<String>` to express that its elements are used as strings. The compiler can reject many invalid operations right at compile time:

```java
List<String> names = new ArrayList<>();
names.add("An");
```

If you try to add an `Integer` through this variable, the compiler reports an error. However, when a collection passes through a raw type, an unchecked cast, or certain uses of generic arrays, that protection can be broken.

What makes this difficult to diagnose is that the place where the fault is introduced and the place where it is detected can be far apart: one piece of code inserts the wrong element, while another reads it under the promised type and only then encounters a `ClassCastException`.

This article uses Java 17 and explains raw types, type erasure, different kinds of casts, heap pollution, and how to handle data boundaries. The complete program deliberately retains certain warnings to observe the problem; snippets explicitly noted as compile errors are not usage recommendations.

## 1. What Does the Element Type Contract Protect?

With:

```java
List<String> names = new ArrayList<>();
```

the compiler knows:

- `add` requires an element compatible with `String`.
- `get` is used as a `String` value.
- Calls can be checked against the variable's type and method signatures.

This does not mean the `ArrayList` object itself maintains a dedicated `String` validator at every memory slot. Compile-time type information and runtime class checks are two different layers of mechanisms.

If every write path into the collection respects the same generic contract, the compiler helps maintain consistency. If any path bypasses that contract, a cleanly declared variable can still point to data whose type assumptions have been corrupted.

## 2. What Is a Raw Type and Why Does It Still Exist?

A **raw type** is the use of a generic type without its type arguments, such as using `List` instead of `List<String>`.

Illustrative snippet:

```java
List raw = new ArrayList();
raw.add("An");
raw.add(42);
```

Raw types exist primarily for compatibility with pre-generics code and legacy APIs. They should not be treated as a shorthand equivalent for `List<Object>` or `List<?>`.

When using a raw type, members involving type parameters are viewed through their erased types in the corresponding contexts. With `List`, element insertion calls are no longer checked like a `List<String>`.

The compiler may warn about:

- Using a raw type.
- Calling a method in a way that cannot verify the generic contract.
- Converting from a raw type to a parameterized type without verification.

The definition of raw types is specified in [JLS 17, Raw Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.8).

### 2.1. A Raw Declaration Does Not Corrupt Data by Itself

Having a raw reference does not automatically mean an error has already occurred. The risk arises when that reference permits an operation that consumers relying on the parameterized type cannot accept.

For example, holding a raw alias without writing the wrong type is not the same as using it to insert a number into a list that is treated elsewhere as a list of strings.

Separate two questions:

1. Has static verifiability been lost?
2. Have the data or type assumptions actually been violated?

Warnings usually point to the risk in the first question; you should not wait for an actual failure before addressing them.

## 3. Distinguishing List, `List<Object>`, `List<?>`, and `List<String>`

| Declared Type | Meaning | Reading Elements As | Adding Elements |
| --- | --- | --- | --- |
| `List<String>` | Elements are known by contract to be strings | `String` | Values compatible with `String` |
| `List<Object>` | Contract allows various object references | `Object` | Compatible object values |
| `List<?>` | Has some element type, but the specific type is unknown | `Object` | Cannot add an arbitrary non-null value under type checking |
| Raw `List` | Uses a generic type while omitting type arguments | Typically the erased type, here `Object` | Can write operations without generic type verification |

Mutation operations must also be supported by the underlying implementation class. The table describes capabilities from a type-checking perspective; it does not promise that any arbitrary list allows additions.

### 3.1. `List<Object>` Can Intentionally Hold Multiple Types

Illustrative snippet:

```java
List<Object> values = new ArrayList<>();
values.add("An");
values.add(42);
```

A list containing multiple types does not automatically imply heap pollution. The `List<Object>` contract inherently permits those values; readers receive `Object` and must decide how to handle them appropriately.

Heap pollution involves breaking a declared type assumption—you cannot conclude that heap pollution exists merely by seeing two different element classes.

### 3.2. `List<String>` Is Not a `List<Object>`

The snippet below does not compile:

```java
List<String> names = new ArrayList<>();
List<Object> objects = names;
```

If this assignment were allowed, code holding `objects` could add an `Integer`, causing code holding `names` to read the wrong type.

Generics are not covariant in that way. Use `List<?>` if you only need to accept a list with an unknown element type:

```java
List<?> unknown = names;
```

### 3.3. `List<?>` Is Not an Immutable List

You cannot call `unknown.add("text")` just because a string is an object: the actual element type might be `Integer`.

However, `List<?>` does not forbid all modifications. For instance, removing elements or calling `clear` can be type-safe and will succeed if supported by the implementation class.

`null` may be type-compatible with an unknown element reference, but the actual collection might forbid `null` or forbid additions altogether. Do not use a wildcard to infer mutability or `null` policy.

## 4. Heap Pollution in Collections

**Heap pollution** occurs when a variable of a parameterized type refers to an object that does not satisfy the assumed parameterized type. In collections, a common manifestation is a list being used as `List<String>` that actually contains a non-string element due to an unsafe write path.

Example:

```java
List<String> names = new ArrayList<>();
List raw = names;
raw.add(42);
```

Reference graph:

```text
names, viewed as List<String> ----+
                                  |
                                  v
                            same ArrayList
                                  |
raw, viewed as List --------------+
                                  |
                                  v
                           Integer element 42
```

There are not two lists. The assignment merely creates another reference to the same object, with different type-checking rules at the source level.

A call through the raw type can insert a number into the data storage that another part of the code trusts to be a list of strings. This concept is specified in [JLS 17, Heap Pollution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.2).

### 4.1. Failures Often Surface Late

The subsequent snippet:

```java
String first = names.get(0);
```

throws a `ClassCastException` when the actual element is an `Integer`.

The read site looks completely ordinary: the variable is declared as `List<String>`, so the programmer did not write any explicit cast. However, the compiler must perform an appropriate check when narrowing the type-erased result back to `String`.

Therefore, a stack trace pointing to `get` does not necessarily indicate the root cause of the bug. You must trace back the creation, return, aliasing, and write paths into the collection.

### 4.2. Not Every Operation Detects It Immediately

Operations such as `size()` do not need to treat elements as `String`. They can continue to work normally even after the list's type invariant has been violated.

Even reading an element through a reference that only requires `Object` does not necessarily force a string check.

Do not treat "it prints fine", "it counts fine", or "reading the first few elements worked" as proof that the entire collection satisfies the expected type.

## 5. What Does Type Erasure Explain?

Java implements generics primarily through **type erasure**.

At the level required for this article:

- Two `ArrayList` instances created with type arguments `String` and `Integer` do not become two separate specialized runtime classes merely because their generic type arguments differ.
- For `List<E>` without a more specific bound, the erased type associated with the element is `Object`.
- The compiler checks types in source code and inserts casts when needed to restore usage according to the declared type.

You can think of the read operation:

```java
String value = names.get(0);
```

at the mechanism level as roughly "read the object and check that it can be used as a `String`". This is a conceptual model for understanding, not a requirement that every compiler always generate identical bytecode.

### 5.1. Do Not Overstate That All Generic Information Disappears

Generic signatures of class or method declarations can remain in metadata and be inspected via reflection in appropriate contexts.

The key distinction is that the type arguments of a local variable like `List<String>` do not automatically turn into a deep element-by-element runtime check on every ordinary list instance.

Knowing that declaration metadata can be read does not mean you have verified that a list passed in from external code contains only strings.

### 5.2. Bounds and Erasure Are Not Always Object

A bounded type parameter is erased to its corresponding bound. This article uses `List<E>` for explanation because it is easy to observe, not to state a universal rule that "every generic always erases to Object" across all of Java.

See [JLS 17, Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6).

## 6. How Far Does Collection Casting Check?

### 6.1. Reference Casts Do Not Convert Elements

Suppose you have:

```java
Object candidate = List.of(1, 2, 3);
```

Casting `candidate` to `List<String>` does not convert the numbers into the strings `"1"`, `"2"`, `"3"`. It only asks to view the same reference under a different type, accompanied by whatever runtime checks the type system can perform.

If you want to convert values, you need an explicit transformation operation, such as mapping each number to its string representation. A cast does not substitute for data conversion.

### 6.2. Checked Cast on the Outer Type

A cast to a runtime-verifiable type checks the corresponding class or interface.

If the actual object is not a list, casting to `List` can throw a `ClassCastException` immediately.

If the object is a list containing numbers, the check "is it a List?" succeeds. However, that does not verify that the elements inside are strings.

### 6.3. Unchecked Cast

Deliberately unsafe illustrative snippet:

```java
Object candidate = List.of(1, 2, 3);
List<String> names = (List<String>) candidate;
```

The compiler warns because it cannot fully verify the generic type argument `String` in this cast. The outer type can be checked as `List`, but the generic component remains unproven.

Do not interpret "unchecked" as "no runtime check whatsoever". A cast may still verify the outer class while being insufficient to prove the full parameterized type.

Only when an element is subsequently read as a `String` might a failure occur at the read site.

### 6.4. Unchecked Conversion Does Not Require Cast Syntax

Example:

```java
List raw = legacyResult();
List<String> names = raw;
```

The second assignment can trigger an unchecked conversion warning. There are no cast parentheses, yet there is still an unverified promise about the element type.

The method `legacyResult` here is merely a placeholder representing a legacy API, not a method defined in the sample program.

### 6.5. Focus on the Source of Evidence

To trust a `List<String>`, you need one of the following valid bases:

- A data flow verified end-to-end by the compiler.
- An API with a trustworthy contract and a correct implementation.
- Element-by-element validation combined with control over subsequent write paths.
- Copying validated elements into a new, strongly typed structure.

A cast or an annotation that merely silences warnings does not supply this evidence on its own. Conversion categories are described in [JLS 17, Conversions and Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html).

## 7. Validating Untyped Data with Wildcards

### 7.1. Check the Outer Type First

When an input has type `Object`, you can check:

```java
if (candidate instanceof List<?> items) {
    for (Object item : items) {
        // Process according to the actual type of item.
    }
}
```

The block above is an illustrative skeleton without business logic.

For an untyped `Object`, you cannot use `instanceof List<String>` as a valid deep check to prove that every element is a string. The type `List<?>` is appropriate for verifying the outer shape without promising an unproven element type.

Do not overgeneralize this into "Java never allows parameterized types on the right-hand side of instanceof" in every context. The rule depends on verifiability and the known static type; this article specifically addresses an input object of completely unknown type.

### 7.2. Validate Each Element and Create a Copy

A method whose policy accepts only non-null strings:

```java
static List<String> copyStrings(Collection<?> source) {
    List<String> result = new ArrayList<>();
    for (Object value : source) {
        if (!(value instanceof String text)) {
            throw new IllegalArgumentException("Expected non-null String");
        }
        result.add(text);
    }
    return result;
}
```

The method above should be placed inside a class with the appropriate imports. The complete program below includes an enhanced version that reports the actual type encountered.

Mechanism:

1. Accept the input without making premature promises about a specific element type.
2. Read each element as `Object`.
3. Validate it using `instanceof String`.
4. Add only proven values into a new `List<String>`.
5. Return a result that does not share list structure with the input.

If validation fails partway through, the source collection is left unmodified by the method, and the partially built result is never returned.

The `null` policy is intentional: `instanceof String` evaluates to `false` for `null`, so the method rejects it. If an application accepts `null`, it must design the corresponding branch explicitly.

### 7.3. Why Validating and Casting the Same Object Can Still Be Risky

Even if you have just iterated through a list and confirmed that every element is a string, if another party still holds a raw alias to that exact list, they can insert a different value after your check completes.

Copying into a new list helps isolate both structure and write paths, though it does not solve every scenario automatically:

- A source modified concurrently during copying requires appropriate synchronization or concurrency mechanisms.
- Mutable elements remain shared if copied by reference.
- Validation rules must match business requirements, not just Java classes.

In the string example, the immutability of `String` elements makes the boundary much easier to manage.

### 7.4. Nested Generics Require Layer-by-Layer Validation

When `List<List<String>>` is required, knowing that each outer element is a `List` does not prove that the inner elements are `String`.

Similarly, `Map<String, List<Integer>>` requires checking the key type, the value collection type, and the element type inside each list.

A `Class<List>` or `List.class` token does not carry enough information to verify `List<String>`. You need structured validation or a data-mapping mechanism with an explicit contract.

## 8. Collections.checkedList: Detecting Certain Errors at the Write Site

Java provides dynamically type-checked views, for example:

```java
List<String> backing = new ArrayList<>();
List<String> checked = Collections.checkedList(backing, String.class);
```

If raw code attempts to insert an `Integer` **through the checked view**, it is rejected immediately with a `ClassCastException` at insertion time.

This moves the point of detection much closer to the cause of the error compared to waiting for another consumer to read the element as a string.

### 8.1. Not a Substitute for Fixing Raw Types

Using a wrapper is not an excuse to keep designing new APIs with raw types. It is a dynamic defense or diagnostic tool for appropriate boundaries.

Whenever you can fix declared types and method signatures, that is generally the better way to let the compiler verify data flow.

### 8.2. Does Not Validate Existing Elements When Creating the View

Creating a checked view should not be treated as a deep verification procedure or a sanitizer for elements already present in the backing list.

If the source already contains invalid types, you must validate the data or create a verified copy rather than merely wrapping it and assuming everything is fixed.

### 8.3. Direct References to the Backing List Can Still Bypass the Wrapper

If another component retains `backing` and uses a raw alias to write directly into it, those writes do not pass through `checked`'s validation.

The view and the backing list share underlying storage. All relevant write paths must be controlled for the wrapper to provide a meaningful boundary.

### 8.4. Only Checks the Provided Runtime Type

`String.class` is sufficient to verify whether an element is a string in this example. For nested generic types, supplying the outer class does not automatically check inner type arguments.

The wrapper is also not a deep copy, an immutability mechanism, or a thread-synchronization mechanism. See [Collections.checkedList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#checkedList(java.util.List,java.lang.Class)).

## 9. Copies and Views Do Not Automatically Restore Type Safety

### 9.1. Copying an Already Polluted Source

If the variable `names` has type `List<String>` but its underlying data is already polluted, writing:

```java
List<String> copy = new ArrayList<>(names);
```

is not an element-by-element verification that every item is a string. The compiler trusts the declared type of the source, and the copy constructor does not take `String.class` to perform such a check.

The new copy can continue carrying invalid elements, and the error will still only surface when an element is read as its specific type.

### 9.2. Unmodifiable Does Not Mean Type-Verified

Wrapping a source in an unmodifiable view only restricts mutation operations through that view. It does not turn an erroneously inserted `Integer` into a `String`.

`List.copyOf` is likewise not a deep generic verifier against whatever type argument the caller expects. Other API checks—such as `null` rejection—do not imply that all application element constraints have been verified.

### 9.3. Correct Java Class Is Not Enough for Domain Validity

A list consisting entirely of `String` instances can still contain empty codes, malformed email addresses, or values outside the acceptable domain.

Distinguish between:

- Correct Java type.
- Correct data structure.
- Correct domain constraints.

Do not use a generic cast as a substitute for all three validation layers.

## 10. Generic Varargs and Arrays: Another Path to Heap Pollution

Raw types are a common source of heap pollution, but not the only one. Arrays and varargs parameters with generic types can also break type contracts.

### 10.1. Why Are Arrays a Sensitive Point?

Arrays carry runtime component type information and are covariant in a way that generics are not. Meanwhile, `List<String>` is not represented at runtime as a specialized list class restricted to `String`.

Java does not allow direct creation of generic arrays:

```java
new List<String>[2]
```

This is a non-compiling example. Do not use a workaround cast through a raw array as a general technique for creating "safe" generic arrays.

### 10.2. Unsafe Varargs Example

Illustrative snippet to be placed inside a class:

```java
static String unsafeVarargs(List<String>... groups) {
    Object[] exposed = groups;
    exposed[0] = List.of(123);
    return groups[0].get(0);
}
```

What happens:

1. The varargs parameter is backed by an array whose runtime component type cannot enforce the `String` type argument of `List`.
2. That array is aliased as `Object[]`.
3. A `List<Integer>` is stored into a slot that source code views as `List<String>`.
4. Reading the first element as a `String` throws a `ClassCastException`.

There is no raw `List` anywhere in the method body, yet heap pollution still occurs through the array and aliasing.

### 10.3. @SafeVarargs Is an Author's Assertion

This annotation does not insert extra runtime type checks and does not automatically make a dangerous method body safe.

Do not attach `@SafeVarargs` to the example above just to silence warnings. The author must prove that the varargs usage does not cause heap pollution while also adhering to the declaration sites where the annotation is permitted.

A pattern can be safe when it only reads from the input lists and copies elements into a new result:

```java
@SafeVarargs
static <T> List<T> concatenate(List<? extends T>... groups) {
    List<T> result = new ArrayList<>();
    for (List<? extends T> group : groups) {
        result.addAll(group);
    }
    return result;
}
```

This method neither writes an incompatible list into the varargs array nor exposes the varargs array itself to external callers. The safety assertion still requires reviewing all actual code in the method body, not just the method signature shape.

See [SafeVarargs Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SafeVarargs.html).

## 11. Compiler Warnings Are Part of the Evidence

### 11.1. Enable Relevant Warnings

A command commonly used when reviewing this kind of code:

```shell
javac --release 17 -Xlint:rawtypes,unchecked Example.java
```

- `rawtypes` highlights where type arguments are omitted.
- `unchecked` highlights where the compiler cannot fully verify conversions, method calls, or related generic constructs.

Warnings do not necessarily fail the build. Therefore, "the build succeeded" does not prove the absence of type-safety risks.

### 11.2. Do Not Equate Every Warning with a Guaranteed Runtime Failure

A cast may be sound due to an invariant that the compiler cannot express. Conversely, a cast may be broken even if execution has not yet encountered data that triggers the failure.

The goal is to establish evidence of correctness, not merely to make warnings disappear.

### 11.3. SuppressWarnings Adds No Protection

`@SuppressWarnings("unchecked")` only affects warning reporting; it does not validate elements and does not alter runtime behavior.

If you truly must use it:

1. Place it on the smallest possible scope containing the unverified operation.
2. Document the invariant that makes the operation safe.
3. Keep write paths and data ownership aligned with that invariant.
4. Maintain tests that meaningfully verify the invariant.

Do not suppress warnings across an entire module just to hide an unanalyzed legacy API boundary.

### 11.4. Pay Attention to Warnings in Libraries and Other Boundaries

Caller code being free of dangerous casts is not enough to prove that the entire program is free of heap pollution. A library, legacy API, or mechanism outside generic type checking can still return an object whose type promise is violated.

When an exception occurs on a simple read line, examine both the data source and any other places holding aliases.

## 12. Complete Java Program

The following program intentionally creates several unsafe situations to compare where errors are detected. Do not use `legacyAdd` or `unsafeVarargs` as templates for new APIs.

Save as `CollectionTypePollutionDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.List;

public class CollectionTypePollutionDemo {
    private static void legacyAdd(List list, Object value) {
        list.add(value);
    }

    private static List<String> copyStrings(Collection<?> source) {
        List<String> result = new ArrayList<>();
        for (Object value : source) {
            if (!(value instanceof String text)) {
                String actualType = value == null
                        ? "null" : value.getClass().getSimpleName();
                throw new IllegalArgumentException(
                        "Expected String, found " + actualType);
            }
            result.add(text);
        }
        return result;
    }

    private static String unsafeVarargs(List<String>... groups) {
        Object[] exposed = groups;
        exposed[0] = List.of(123);
        return groups[0].get(0);
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        legacyAdd(names, 42);
        System.out.println("size after legacy write: " + names.size());

        try {
            String first = names.get(0);
            System.out.println("unexpected string: " + first);
        } catch (ClassCastException ex) {
            System.out.println("typed read: ClassCastException");
        }

        List<String> backing = new ArrayList<>();
        List<String> checked = Collections.checkedList(backing, String.class);

        try {
            legacyAdd(checked, 99);
        } catch (ClassCastException ex) {
            System.out.println("checked write: ClassCastException");
        }
        System.out.println("checked size after rejected write: "
                + checked.size());

        legacyAdd(backing, 99);
        System.out.println("backing bypass size: " + checked.size());
        try {
            String first = checked.get(0);
            System.out.println("unexpected checked string: " + first);
        } catch (ClassCastException ex) {
            System.out.println("bypass typed read: ClassCastException");
        }

        List<String> valid = copyStrings(List.of("An", "Binh"));
        System.out.println("validated copy: " + valid);

        Object candidate = List.of("An", 7);
        if (candidate instanceof List<?> unknown) {
            System.out.println("runtime shape is List: true");
            try {
                copyStrings(unknown);
            } catch (IllegalArgumentException ex) {
                System.out.println("validation: " + ex.getMessage());
            }
        }

        try {
            unsafeVarargs(List.of("safe"));
        } catch (ClassCastException ex) {
            System.out.println("varargs typed read: ClassCastException");
        }
    }
}
```

Compile:

```shell
javac --release 17 -Xlint:rawtypes,unchecked CollectionTypePollutionDemo.java
```

The compiler emits warnings about raw types, unchecked calls, and generic varargs. These warnings are an intentional part of the experiment. Exact wording, file paths, and diagnostic line numbers may vary across JDK distributions.

After compiling successfully, run:

```shell
java CollectionTypePollutionDemo
```

Expected stdout:

```text
size after legacy write: 1
typed read: ClassCastException
checked write: ClassCastException
checked size after rejected write: 0
backing bypass size: 1
bypass typed read: ClassCastException
validated copy: [An, Binh]
runtime shape is List: true
validation: Expected String, found Integer
varargs typed read: ClassCastException
```

### 12.1. The First Error Is Detected at Read Time

`legacyAdd(names, 42)` accepts a raw `List`, allowing it to add an element that violates the type promise of the `names` variable.

`size()` still returns 1. Only when retrieving the element to assign it to a `String` does `ClassCastException` occur.

### 12.2. The Checked View Moves Failure to Write Time

The attempt to write a number through `checked` is rejected immediately. The size remains 0 because the insertion was not accepted.

This helps pinpoint the offending write site earlier; it does not make a raw API a recommended design.

### 12.3. A Backing Alias Can Bypass the View

Writing directly through `backing` bypasses the wrapper. `checked.size()` sees the new element because the view shares the underlying list.

When the caller reads the element as a string, the failure happens again. This example illustrates the limitation of wrappers when write paths are not strictly controlled.

### 12.4. Element-by-Element Validation Produces a Valid New Result

`copyStrings` accepts data via `Collection<?>`, checks each element, and builds a new `List<String>`.

A valid source produces `[An, Binh]`. A mixed source containing a string and a number is rejected with an explicit application-generated message rather than leaving a cast failure to surface later at a read site.

### 12.5. Varargs Demonstrates a Pollution Source Other Than Raw List

The final method corrupts the type of a slot in the varargs array and then reads from it under the `List<String>` assumption. It illustrates why you must inspect arrays and aliasing paths as well, rather than searching only for raw type declarations.

The exception-handling blocks allow the demo program to run through all experiments in one execution. In real systems, the proper solution is to protect data boundaries and type contracts, not to wrap every collection read in a `try-catch` for `ClassCastException`.

## 13. Working with Legacy APIs or External Data

### 13.1. Isolate Untyped Boundaries

If a library returns a raw collection, do not pass it deep across multiple layers and cast it at every use site.

Establish a clear boundary:

```text
legacy API or untyped data
         |
         v
validate structure and elements
         |
         v
strongly typed application collection
```

Past the boundary, the rest of the codebase uses normal generic types without repeating casts.

### 13.2. Choose Explicit Behavior for Invalid Elements

Options include:

- Rejecting the entire dataset and reporting an error.
- Collecting per-index errors so the user can fix them.
- Converting specific data representations according to explicit rules.
- Skipping invalid elements if that is genuinely a specified requirement.

Do not silently convert arbitrary objects into strings via `toString()` just to satisfy `List<String>`. The resulting strings may not carry the data semantics the application actually expects.

### 13.3. Preserve the Source When Validation Fails

Validating into a newly created collection avoids mutating the original input during verification.

If the source collection or its elements can be modified concurrently, you must arrange appropriate ownership, snapshots, or synchronization; a validation loop does not automatically create a transaction over shared data.

### 13.4. Do Not Use Generics to Disguise an Unclear Domain Model

If the data genuinely permits multiple valid element types, express that explicitly using `List<Object>`, a meaningful common supertype, or a domain model that distinguishes each variant.

Slapping `List<String>` onto non-string data and forcing casts does not make the model more accurate.

## 14. Diagnostic Checklist for ClassCastException in Collections

When a failure occurs at `String name = names.get(i)` or inside `for (String name : names)`, check the following in order:

1. What is the actual runtime class of the element at the failing index?
2. What is the compile-time type of the collection variable?
3. Where was the collection created or returned from?
4. Are there any raw parameters, raw return types, or unchecked casts along that path?
5. Is another alias writing to the same underlying collection object?
6. Are generic arrays, varargs, or wrappers being misused?
7. Was a shallow copy or unmodifiable view mistaken for a type-verification step?
8. Does the boundary transitioning from untyped data to domain types perform actual runtime checks?
9. If warnings were suppressed, does the invariant documented there still hold?
10. Should the contract source be fixed rather than patching a single read site?

Do not add another cast at the failing line as your first reflex. An extra cast will not turn an `Integer` into a `String` and usually only shifts where the error is reported.

## 15. Self-Verification Exercises

### Exercise 1: Choose the Right Declared Type

Given three requirements:

- A list guaranteed to hold string names.
- A list that may hold values of various valid object types.
- A method that only needs to check the size and read each element without knowing its specific type.

Choose `List<String>`, `List<Object>`, and `List<?>` respectively. Explain why a raw `List` should not be the default choice for the third requirement.

### Exercise 2: Predict Where the Error Is Detected

Create a `List<String>`, create a raw alias to it, insert an `Integer`, and then:

- Call `size()`.
- Read through the raw alias into an `Object` variable.
- Read through the parameterized variable into a `String` variable.

Predict which operation requires a string cast check and explain why the failure does not occur immediately on every operation.

### Exercise 3: Validate a Mixed Source

Write a method that builds a new `List<String>` from a `Collection<?>` according to this policy:

- Accept only non-null strings.
- If an invalid element is encountered, report both its index and its actual type.
- Do not modify the source collection.
- Do not use unchecked casts.

Test it with an empty source, an all-string source, a source with a number at the end, and a source containing `null`.

### Exercise 4: Demonstrate the Limits of checkedList

Create a backing list and a checked view over it. Attempt an invalid write through the view, then attempt one through a raw alias to the backing list.

Explain why only calls through the view are protected and why controlling ownership of the backing collection is essential.

### Exercise 5: Validate Nested Generics

Accept an `Object` expected to be a list of lists of strings. Write layer-by-layer validation and construct a new result structure.

Do not rely on `List.class` as sufficient proof for the entire `List<List<String>>`.

### Exercise 6: Audit a Warning Suppression

Find or construct a scenario assumed to require `@SuppressWarnings("unchecked")`. Explicitly document:

- What can the compiler not verify?
- What program evidence makes the conversion safe?
- Who else can still write to the underlying data?
- What tests are needed in case that invariant is broken in the future?

If you cannot answer these questions, there is not yet a valid basis for treating the warning suppression as a complete fix.

## 16. Conclusions to Avoid

- "A raw `List` is just shorthand for `List<Object>`."
- "`List<?>` means nothing in the list can ever be modified."
- "A list containing elements of different classes is always heap pollution."
- "Casting to `List<String>` checks every element inside the list."
- "If I didn't write a cast at `get`, a `ClassCastException` cannot happen there."
- "Wrapping with `unmodifiableList` or calling `List.copyOf` sanitizes mistyped elements."
- "`checkedList` also protects writes made directly to the backing list."
- "`@SafeVarargs` or `@SuppressWarnings` automatically makes a method body type-safe."
- "If there are no warnings in caller code, the library source is guaranteed to be type-correct."
- "Adding another cast is the way to fix a value of an incompatible type."

The goal is to keep element-type promises well-founded: use generics end-to-end wherever possible, place explicit validation at untyped boundaries, control write paths, and treat unexplained warnings as remaining analysis work.
