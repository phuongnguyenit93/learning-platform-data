# Patterns with Raw Types and Warnings in Java 21

A **raw type** is a use of a generic type that **omits the type argument list**. For example, `List` is the raw type of `List<E>`, whereas `List<String>` and `List<?>` both declare a type argument. With pattern matching, Java 21 allows writing:

```java
static void examine(Object value) {
    if (value instanceof java.util.List raw) {
        System.out.println("Size: " + raw.size());
    }
}
```

The type pattern `List raw` can match a `List` object, but it **does not prove the element type**. Because `raw` has the raw type `List`, the compiler loses generic information that the source code could otherwise use. When `javac -Xlint:rawtypes` is enabled, raw type declarations may trigger a warning; when calling operations that write values into a raw collection, `javac -Xlint:unchecked` usually issues further warnings.

The key point: **a pattern matching successfully does not mean the data in the collection is type-safe**. Distinguish between checking the actual runtime type of the collection, the static type of the pattern variable, and checking each individual element.

## 1. How do raw types differ from full generic types?

With `java.util.List<E>`:

```java
java.util.List<String> names; // E is specified as String
java.util.List<?> unknown;    // Has a wildcard type argument: element type is unknown
java.util.List raw;           // Raw type: omits the type argument entirely
```

These are illustrative declarations, not a standalone program; the variables must be initialized before use.

| Syntax | Meaning of the static type | Ability to add elements |
| --- | --- | --- |
| `List<String>` | Elements are checked against `String` at compile time | Can call `add(String)` |
| `List<?>` | The list has an **unspecified** element type | Cannot `add` an arbitrary non-`null` value |
| `List` (raw) | Skips type argument checking in related operations | `add(...)` calls may compile but emit an unchecked warning |

Raw types exist primarily for compatibility with Java code written before generics and with legacy APIs. They are not a shorthand with the same level of type safety as `List<?>`. For new code, use a parameterized type or an appropriate wildcard.

## 2. Why is `instanceof List raw` valid?

Java implements generics primarily through **type erasure**: much of the type argument information is no longer available for inspection at runtime. An `ArrayList<String>` and an `ArrayList<Integer>` both have the runtime class `ArrayList`, so an `instanceof List` check only confirms that the object implements the `List` interface.

**Raw types are reifiable**: a raw type such as `List` has enough representation to check the type itself at runtime. The following type pattern is valid when `value` is `Object`:

```java
if (value instanceof java.util.List raw) {
    Object first = raw.isEmpty() ? null : raw.get(0);
    System.out.println(first);
}
```

This snippet must be placed inside a method that has a `value` variable. Even if the pattern matches, the variable `first` is only treated as `Object`, because `raw.get(0)` carries no `String` type guarantee.

Both a `List<String>` and a `List<Integer>` can match `List raw`. Therefore, **you cannot infer from the pattern `List raw` that the elements are strings, integers, or any other specific type**.

## 3. A raw pattern cannot check `List<String>` at runtime

Suppose a variable only has static type `Object`:

```java
Object data = java.util.List.of("A", "B");

if (data instanceof java.util.List<?> list) {
    System.out.println(list.size()); // valid
}

// DOES NOT COMPILE when data has static type Object:
// if (data instanceof java.util.List<String> strings) {
//     System.out.println(strings.get(0));
// }
```

`List<String>` is generally **non-reifiable**: the `String` information cannot be verified with just a type test on `Object`. In contrast, `List<?>` has only unbounded wildcard type arguments, so it can be used in a runtime type test.

There are cases where Java allows a parameterized type pattern when the **static type of the expression** already carries a compatible generic constraint. That does not add any ability to check erased type arguments at runtime. For dynamic data arriving as `Object`, do not rely on `List<String>` syntax to prove that all elements are `String`.

A safe approach:

```java
static boolean allStrings(Object value) {
    if (!(value instanceof java.util.List<?> items)) {
        return false;
    }
    for (Object item : items) {
        if (!(item instanceof String)) {
            return false;
        }
    }
    return true;
}
```

This method returns `false` if the data is not a `List`, if any element is not a `String`, or if there is a `null` element. For an empty list, the loop finds no violating element and returns `true`. This follows the rule "every element is a String"; if your business logic requires a non-empty list, add `!items.isEmpty()`.

## 4. Two warning categories to read separately: `rawtypes` and `unchecked`

Enable specific warning modes when compiling:

```bash
javac -Xlint:rawtypes,unchecked RawTypePatternDemo.java
```

The command above still **compiles** valid code and emits the corresponding warnings via the compiler's diagnostic stream; exact line numbers and wording may vary by JDK version. Two common warning categories:

### `rawtypes`: using a generic name without type arguments

```java
java.util.List rawList = new java.util.ArrayList<String>();

if (value instanceof java.util.List rawPattern) {
    System.out.println(rawPattern.size());
}
```

This is an illustrative snippet inside a method with a `value` variable. Using `List` without `<...>` is using a raw type; `-Xlint:rawtypes` helps detect these places.

### `unchecked`: operations not fully verified by the generic type checker

```java
java.util.List<String> strings = new java.util.ArrayList<>();
java.util.List raw = strings; // raw type
raw.add(123);                // unchecked call to add(E)
```

Java allows the call `raw.add(123)` because `raw` does not retain the `E=String` constraint at the static checking level. The compiler usually warns about an **unchecked call**, but does not block the statement itself. The underlying `ArrayList` object receives an `Integer` into a list that is still referenced as `List<String>`.

Casts or assignments from a raw collection to a collection with type arguments can also produce an **unchecked cast/assignment**:

```java
java.util.List raw = new java.util.ArrayList();
// java.util.List<String> strings = raw; 
// Compiles with an unchecked conversion warning; does not validate elements.
```

The `rawtypes` warning reports **missing type arguments in a type**, whereas `unchecked` reports **an operation or conversion whose type safety cannot be fully verified**. They are related but not synonymous. Code can emit one or both.

## 5. Risk of heap pollution and `ClassCastException`

**Heap pollution** occurs when a variable of a parameterized type refers to an object or data structure containing values that do not match the type promised by that variable. Raw collections are a common path to this situation.

Example:

```java
java.util.List<String> names = new java.util.ArrayList<>();
names.add("Lan");

java.util.List raw = names;
raw.add(123); // unchecked warning

String first = names.get(0);  // "Lan": still readable
// String second = names.get(1); // compiles, throws ClassCastException at runtime
```

At runtime, generic erasure means `ArrayList` does not automatically enforce that values added via `raw` must be `String`. However, when code reads through `List<String>`, the compiler inserts the necessary type check on the returned result; an `Integer` cannot become a `String`, so a `ClassCastException` is thrown.

**`instanceof List raw` does not cause heap pollution merely by matching.** The risk arises when using raw access to insert values of the wrong type or when performing an unchecked cast. Therefore, only reading `size()` or reading elements as `Object` is different from writing elements through a raw reference.

It is also important to distinguish: a `List<Integer>` matching `List raw` is **correct according to the semantics** of a runtime type check; it is not a bug in pattern matching. The mistake is further assuming that the list contains `String` without verifying it.

## 6. What is lost when a pattern variable has a raw type?

In:

```java
static void printItems(Object input) {
    if (input instanceof java.util.List raw) {
        for (Object item : raw) {
            System.out.println(item);
        }
    }
}
```

The variable `raw` is declared by the type pattern and has the **raw type `List`**. You can still call `size()`, `isEmpty()`, `get(int)`, and iterate over elements as `Object`. However, the compiler no longer checks `add` against the collection's original type argument.

In addition, **flow scoping** still applies just as with other pattern variables: `raw` is only in scope where the match `input instanceof List raw` is definitely true. A raw type does not let the variable escape control-flow scoping and does not make `null` match.

Compare with a wildcard:

```java
static void readSafely(Object input) {
    if (input instanceof java.util.List<?> items) {
        for (Object item : items) {
            if (item instanceof String text) {
                System.out.println(text.toUpperCase());
            }
        }
        // items.add("new"); // compile error: element type of List<?> is unknown
    }
}
```

`items` lets you read elements as `Object` just like a raw list, but **prevents adding a specific value** that might not match the unknown type argument. Checking each element with `instanceof String text` is what proves that element is a string.

## 7. With `switch`, prefer `List<?>` and appropriate guards

Java 21 supports pattern matching for `switch`. When the selector has type `Object`, you can use a `List<?>` pattern and then inspect its state:

```java
static String describe(Object input) {
    return switch (input) {
        case null -> "null";
        case java.util.List<?> list when list.isEmpty() -> "empty list";
        case java.util.List<?> list -> "list of size " + list.size();
        default -> "other";
    };
}
```

The first branch handles a `null` selector, the two `List<?>` branches distinguish empty and non-empty lists, and `default` covers all other types.

You *can* write `case java.util.List raw -> ...` to match the raw type, but there is usually no benefit when you only need to read the structure. A wildcard expresses "a `List` whose element type is unknown" more clearly and avoids `rawtypes` warnings.

Remember that `when list.isEmpty()` only checks **whether the list is empty**; it does not assert that the elements of a non-empty list are `String`. To validate the contents, you still need to iterate over the elements or use a data class with an explicit type contract.

## 8. Reading legacy code that uses raw types: controlled handling

Some legacy APIs return raw `List`, `Map`, or `Class`. When encountering them:

1. **Identify the raw boundary**: which APIs return or accept raw types, and where `rawtypes` or `unchecked` warnings are emitted.
2. **Check the outer shape with a reifiable pattern**: for example `input instanceof List<?> list` or `input instanceof Map<?, ?> map`.
3. **Validate each element or key/value** according to business requirements before using it as a specific type.
4. **Build a strongly typed collection** if you need to return `List<String>`, instead of blindly casting from `List`.
5. **Isolate raw code if unavoidable**: keep raw references in a small scope, and if `@SuppressWarnings("rawtypes")` or `@SuppressWarnings("unchecked")` is truly needed, place the annotation only on the narrowest verified scope and document why it is safe.

Example of converting dynamic data into a verified list of strings:

```java
static java.util.List<String> checkedCopy(Object input) {
    if (!(input instanceof java.util.List<?> list)) {
        throw new IllegalArgumentException("Expected a List");
    }

    java.util.List<String> result = new java.util.ArrayList<>();
    for (Object item : list) {
        if (!(item instanceof String text)) {
            throw new IllegalArgumentException("Non-String element");
        }
        result.add(text);
    }
    return java.util.List.copyOf(result);
}
```

`List.copyOf` creates a list that cannot be modified through its API; here every element has already been verified to be a non-`null` `String`, so it will not fail on `null` elements. The result has type `List<String>` genuinely through **reading and validating each element**, not through an unchecked cast.

This validation incurs the cost of traversing the list. For data that may be concurrently modified during validation, you need an additional synchronization contract or a reliable snapshot; a single traversal does not guarantee avoiding all data races.

## 9. Complete program: compile-time warnings and runtime errors

Create the file **`RawTypePatternDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class RawTypePatternDemo {
    static String inspect(Object input) {
        if (input instanceof List raw) {
            Object first = raw.isEmpty() ? null : raw.get(0);
            return "raw list, first-is-String=" + (first instanceof String);
        }
        return "not a list";
    }

    static boolean allStrings(Object input) {
        if (!(input instanceof List<?> items)) {
            return false;
        }
        for (Object item : items) {
            if (!(item instanceof String)) {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("Lan");

        System.out.println(inspect(names));
        System.out.println(allStrings(names));

        List raw = names;
        raw.add(123); // unchecked call: breaks the List<String> contract

        System.out.println(allStrings(names));
        try {
            String second = names.get(1);
            System.out.println(second);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }

        Object numbers = List.of(1, 2);
        System.out.println(inspect(numbers));
        System.out.println(allStrings(numbers));
    }
}
```

Compile with **JDK 21**, enabling warnings to observe raw type usage:

```bash
javac --release 21 -Xlint:rawtypes,unchecked RawTypePatternDemo.java
java RawTypePatternDemo
```

The compilation step will emit warnings related to raw types and unchecked calls; compiler warning diagnostics **are not part of the program's stdout**. If the compiler is configured to treat warnings as errors (for example, by adding `-Werror`), the warnings must be resolved before running.

Stdout of the `java` command:

```text
raw list, first-is-String=true
true
false
ClassCastException
raw list, first-is-String=false
false
```

Why does this output occur?

- Initially `names` contains `"Lan"`; both `List raw` and `List<?>` match the `ArrayList` object. The first element is a `String`, so `allStrings(names)` returns `true`.
- `raw.add(123)` adds an `Integer` to the same object that `names` views as `List<String>`. That is the path that causes heap pollution.
- `allStrings(names)` then returns `false` because it detects that the `Integer` element is not a `String`.
- `names.get(1)` reads under the static type `List<String>` and triggers a `ClassCastException` when reading the element of the wrong type; the `catch` block handles the error so the program continues.
- `List.of(1, 2)` still matches `List raw` even though it contains `Integer`; raw matching says nothing about the type argument.

This example intentionally uses a raw type to **reproduce the warnings and consequences**. In production code, do not call `add` through a raw reference without ensuring the element type.

## 10. Misconceptions to avoid

**"A raw pattern checks the generic argument too."** False. `instanceof List raw` only matches `List` at runtime; it does not prove `List<String>`.

**"If there is no `ClassCastException`, the raw collection is safe."** False. The error may only appear later when other code reads an element with an expected type, or it may simply never be triggered on a particular execution path.

**"`List<?>` knows what type the elements are."** False. `List<?>` preserves element-type uncertainty in a safer way: read as `Object`, no arbitrary writes. To get `String`, you must check each element.

**"Just adding `@SuppressWarnings` fixes the problem."** False. The annotation only hides or suppresses compiler diagnostics for the annotated scope; it adds no runtime checks, restores no type arguments, and eliminates no heap pollution.

**"Any `instanceof List<String>` can be checked at runtime."** False. When data only has static type `Object`, the generic argument cannot be verified by that type test. Being allowed in some contexts constrained by static types does not turn Java into a full runtime-checking system for generic type arguments.

**"If a raw type pattern is allowed, you should use it."** Not necessarily. In new code, `List<?> list` or `Map<?, ?> map` usually expresses intent more clearly, helps the compiler check type safety, and avoids unnecessary warnings.

## 11. How to decide in practice

When you need to inspect dynamic data:

- Need to know whether it is a `List`? Use `instanceof List<?> list`.
- Need to know whether it is a `List` containing only `String`? Match `List<?>`, then verify **every element** according to your policy for `null` and empty lists.
- Need a `List<String>` for long-term use? Construct a typed list from validated data, or accept input from a generic API with a clear contract.
- Encountering raw types from a legacy library? Establish a data-validation boundary and narrow the scope of raw operations; read `rawtypes` and `unchecked` warnings before deciding whether any can be ignored.
- Want to test actual behavior? Compile with `-Xlint:rawtypes,unchecked`, run tests including wrong-type elements, and check where `ClassCastException` could be thrown.

**Remember:** a raw type is a type that can be checked at runtime, so raw type patterns are valid in Java 21; however, **being reifiable does not mean preserving type arguments**. When the goal is generic safety, `List<?>` plus element-level checks and a clear data contract is usually the better choice.
