# Limits of type patterns and casting after type erasure in Java

Java allows runtime type checking via `instanceof`, casting via cast expressions, and since Java 16 **pattern matching for `instanceof`** to combine the check with declaring a narrowed-type variable. However, standard Java Generics uses **type erasure**: the JVM normally does not store concrete type arguments such as `String` inside the runtime class of an `ArrayList<String>`.

Therefore, there is a huge difference between two questions:

- "Is this value a `List`?" — can be checked directly with `instanceof List<?>`.
- "Is this value a `List<String>` containing only `String` elements?" — cannot be concluded solely from `instanceof` on an `Object` value; a safe data contract or element-by-element validation is required.

In particular, **casting `(List<String>) value` does not validate every element**. With untrusted data sources, an unchecked cast may succeed first and then throw `ClassCastException` where an element is read.

## 1. What can the `instanceof` operator check?

The `instanceof` operator relies on type information still inspectable at runtime. When a value is an object carrying runtime class information, we can generally check its class or interface without requiring concrete type arguments:

```java
// Illustrative statements; import java.util.List.
Object text = "Java";
Object items = List.of("An", 42);

boolean a = text instanceof String;  // true
boolean b = items instanceof List<?>; // true
boolean c = items instanceof List;    // true, though List is a raw type
```

For `items`, both `List` check expressions return `true` because the actual object is a list. This **does not prove the second element is a `String`**; in that example the second element is an `Integer`.

The type `List<?>` is a **reifiable type** because the `?` wildcard is unbounded: the runtime check only needs to confirm that it is a `List`. By contrast, `List<String>` requires knowing the concrete type argument `String`, which an ordinary `List` object does not carry as a separate runtime class.

A reifiable type does not mean data is always safe. Raw `List` is also reifiable, yet calling `raw.add(42)` can cause heap pollution if the same list is being used elsewhere under type `List<String>`.

## 2. What does pattern matching for `instanceof` add?

Before pattern matching, developers commonly wrote:

```java
// Snippet placed inside a method with an Object value variable.
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
```

From Java 16 onward (and usable normally on Java 17+), you can write:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

`String text` is a **type pattern**. When the check succeeds, Java binds a pattern variable `text` already typed as `String`, avoiding a redundant cast.

A type pattern only creates a variable when **the corresponding check is valid**. It adds no capability to read erased generic type arguments. For example:

```java
Object value = java.util.List.of("An");

if (value instanceof java.util.List<?> items) {
    System.out.println(items.size()); // Valid
}

// Invalid for Object value:
// if (value instanceof java.util.List<String> items) { ... }
```

Inside the `List<?> items` branch, the compiler knows `items` is `List<?>`; each `items.get(i)` can only be used as `Object` unless checked further. It **does not infer that `items` is `List<String>`**.

## 3. Why cannot a `List<String>` pattern be used like a `List<?>` pattern?

Given an `Object` value, the following cannot be used as a runtime element check:

```java
Object input = java.util.List.of("A", "B");

// DOES NOT COMPILE in this context:
// if (input instanceof java.util.List<String> strings) {
//     System.out.println(strings.get(0));
// }
```

Reason: `List<String>` is a **non-reifiable parameterized type**. The JVM does not have enough information from the runtime class `List` alone to verify that every element conforms to `String`. Java will not accept an `instanceof` check as though it could check that.

Valid way to write it:

```java
if (input instanceof java.util.List<?> values) {
    for (Object element : values) {
        if (element instanceof String text) {
            System.out.println(text.toUpperCase(java.util.Locale.ROOT));
        } else {
            System.out.println("Phần tử không phải String");
        }
    }
}
```

Here there are **two checking layers**: the outer layer proves it is a `List`; the inner layer uses `instanceof String` on each value. The original generic `String` argument is not automatically recovered by the JVM.

### An important nuance of `instanceof` since Java 16

For an expression with a **very specific known static type**, compile-time type compatibility rules can permit certain uses of `instanceof` involving non-reifiable parameterized types. That does not create a new runtime type-argument check.

Therefore, do not over-memorize that "every `instanceof List<String>` syntax is wrong in every context." The accurate practical rule for inspecting an unknown `Object` value is: **use a reifiable type such as `List<?>` and then verify contents if needed**. With type patterns, the compiler also applies dedicated rules for compatibility and pattern variables.

## 4. Pattern variables have flow-sensitive scope

A variable declared in a type pattern does not have the same scope as an ordinary local variable. It **can only be used where the compiler proves the pattern check succeeded**.

### 4.1. `if` branch

```java
static void show(Object input) {
    if (input instanceof String text) {
        System.out.println(text.length()); // text has been confirmed to be String
    }
    // System.out.println(text); // Invalid: text is out of scope here
}
```

### 4.2. Combining with `&&`

```java
static boolean nonEmptyList(Object input) {
    return input instanceof java.util.List<?> values
            && !values.isEmpty();
}
```

The RHS of `&&` only executes when the LHS is `true`, so pattern variable `values` is definitely assigned and can be used on the RHS.

You cannot simply replace `&&` with `||` and use the variable on the RHS:

```java
// DOES NOT COMPILE:
// return input instanceof java.util.List<?> values
//         || values.isEmpty();
```

When `||` evaluates the RHS, the LHS was `false`; the pattern variable is not guaranteed to have been created.

### 4.3. Guard clause with `!` and `return`

```java
static int listSizeOrZero(Object input) {
    if (!(input instanceof java.util.List<?> values)) {
        return 0;
    }
    return values.size(); // Valid because reaching this line guarantees the pattern matched
}
```

This checking style is useful when validating data at the start of a method and then using the narrowed variable in the rest of the body.

### 4.4. `null` does not match a type pattern

```java
Object input = null;
boolean matched = input instanceof String; // false
```

Pattern matching does not treat `null` as a valid `String`. If `null` is a permissible business value, a separate branch or policy is needed.

### 4.5. An obviously true pattern can also be rejected

If the expression already has a static type that is a subtype of the pattern type, a type pattern such as `String s; if (s instanceof String text)` is disallowed because the narrowing is already guaranteed in source code. This is a rule of **compile-time pattern compatibility**, unrelated to the JVM forgetting `String`.

## 5. Casting after erasure: checked parts vs. unchecked parts

A Java cast can be a **checked cast** or an **unchecked cast**, depending on whether the JVM has enough information to verify the entire target type.

Example of a checked cast for a reifiable class:

```java
Object input = "Java";
String text = (String) input; // Runtime can check String
```

If `input` is actually an `Integer`, casting to `String` throws `ClassCastException`.

However, for a concrete generic type:

```java
Object input = java.util.List.of("Java", 42);

// This is an UNCHECKED cast; the compiler will warn unless suppressed.
java.util.List<String> names = (java.util.List<String>) input;
```

This cast cannot verify that every element is `String`; it can only check the appropriate runtime part, such as whether the object is a `List`. Wrong-typed data can sit inside the list without failing immediately at the cast statement.

Later:

```java
// Snippet continues:
String second = names.get(1); // ClassCastException when Integer is treated as String
```

The compiler treats the result of `get` on `List<String>` as `String`. Bytecode after erasure may contain a `checkcast java/lang/String` instruction at the site consuming the result. Thus **the location of the runtime failure can differ from the original unchecked cast site**.

Distinguish three cases:

1. Casting to `String` can verify the object's type immediately at the cast site.
2. Casting to `List<String>` does not verify the `String` part of the type argument that way.
3. `List<?> values = (List<?>) input;` has a reifiable target type: the cast checks whether the object is a `List`, yet still does not verify each element's type.

Point (3) is usually good practice when receiving a list from an `Object` whose element type is not yet known.

## 6. Runnable Java 17+ program: patterns and unchecked casts

Save the following complete code as **`PatternErasureDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class PatternErasureDemo {
    static boolean allStrings(Object input) {
        if (!(input instanceof List<?> values)) {
            return false;
        }
        for (Object value : values) {
            if (!(value instanceof String)) {
                return false;
            }
        }
        return true;
    }

    static List<String> checkedCopy(Object input) {
        if (!(input instanceof List<?> values)) {
            throw new IllegalArgumentException("Not a list");
        }

        List<String> result = new ArrayList<>();
        for (int i = 0; i < values.size(); i++) {
            Object value = values.get(i);
            if (!(value instanceof String s)) {
                throw new IllegalArgumentException("Bad element at " + i);
            }
            result.add(s);
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        Object mixed = new ArrayList<>(List.of("Java", 42));

        System.out.println("Outer List<?>: "
                + (mixed instanceof List<?>));
        System.out.println("All Strings: " + allStrings(mixed));
        System.out.println("Null is List<?>: " + (null instanceof List<?>));

        if (mixed instanceof List<?> values) {
            System.out.println("List size: " + values.size());
            Object first = values.get(0);
            System.out.println("First is String: "
                    + (first instanceof String));
        }

        try {
            @SuppressWarnings("unchecked")
            List<String> assumed = (List<String>) mixed;
            String second = assumed.get(1);
            System.out.println(second);
        } catch (ClassCastException exception) {
            System.out.println("Unchecked read: ClassCastException");
        }

        try {
            checkedCopy(mixed);
        } catch (IllegalArgumentException exception) {
            System.out.println("Validation: " + exception.getMessage());
        }

        System.out.println("Checked copy: "
                + checkedCopy(List.of("An", "Binh")));
        System.out.println("Empty all Strings: "
                + allStrings(List.of()));

        try {
            String.class.cast(42);
        } catch (ClassCastException exception) {
            System.out.println("Class token: ClassCastException");
        }
    }
}
```

Run with JDK 17 or higher:

```bash
javac -encoding UTF-8 -Xlint:unchecked PatternErasureDemo.java
java PatternErasureDemo
```

Standard output:

```text
Outer List<?>: true
All Strings: false
Null is List<?>: false
List size: 2
First is String: true
Unchecked read: ClassCastException
Validation: Bad element at 1
Checked copy: [An, Binh]
Empty all Strings: true
Class token: ClassCastException
```

The test demonstrates:

- `instanceof List<?>` confirms the outer class without asserting that every element is `String`.
- Pattern variable `values` has type `List<?>`, so elements must be read as `Object` before checking `instanceof String`.
- Casting `mixed` to `List<String>` does not scan the list; `ClassCastException` only appears when reading `Integer` as `String`.
- `checkedCopy` checks each element, reports an error at index 1 on type mismatch, and returns a new `List<String>` when all data conform.
- `allStrings(List.of())` is `true` under the "every element is String" logic for an empty set. If non-empty data is required, check that separately.
- `String.class.cast(42)` checks the concrete runtime class and throws `ClassCastException` right at the cast.

The file has one `public` class matching the filename, using APIs and syntax available in Java 17. The `-Xlint:unchecked` flag is useful when actively testing unsuppressed casts; in the runnable example, `@SuppressWarnings("unchecked")` is used solely on the intentionally unsafe declaration to focus on illustrating behavior.

## 7. Why cannot `Class<T>` solve nested generics on its own?

When checking an element against a runtime class, `Class<T>` is a useful mechanism:

```java
static <T> T castOne(Object input, Class<T> type) {
    return type.cast(input);
}

// castOne("Java", String.class) -> "Java"
// castOne(42, String.class) -> throws ClassCastException
```

`String.class` describes the `String` class at runtime. However, there is no Java class literal `List<String>.class` to check the `String` argument inside a collection in an equivalent way.

You can use `List.class.isInstance(input)` to confirm the outer class, and `String.class.isInstance(item)` to confirm each element. With nested generics such as `List<List<String>>`, you must check the outer list, the sublists, and the leaf elements in sequence.

In addition, `Class<T>` typically checks **class compatibility**. `Number.class.isInstance(Integer.valueOf(42))` is `true`, even though the value's exact runtime class is `Integer`. If a contract requires **one exact class**, you must define a stricter policy yourself rather than assuming subclasses are rejected by default.

## 8. The issue with type variable `T` in patterns and casts

A generic method cannot directly use a type variable as a runtime class for checks:

```java
// Snippet illustrating an INVALID generic method:
static <T> boolean isType(Object input) {
    // return input instanceof T; // Cannot check type variable T
    return false;
}
```

The `return false` statement only gives the snippet a valid method body; the key line is `instanceof T`, commented out because it is invalid. Even with `T extends Number`, that does not tell whether `T` is `Integer`, `Double`, or another subtype at runtime.

The pattern `input instanceof T item` does not recover the erased type either. If you need to check the class of a value requested by the caller, pass a token:

```java
static <T> boolean matches(Object input, Class<T> type) {
    return type.isInstance(input);
}
```

This token handles checking **a concrete class**. Do not infer that it can represent a nested type argument such as `Map<String, List<Integer>>`.

Similarly, a cast to `T` in generic code may only be checked against the erased bound or become unchecked in certain situations. It is not independent proof that the object satisfies every type constraint the caller deduced at the source-code level.

## 9. Raw types and heap pollution make casts even easier to misuse

Normal generics catches many errors at compile time:

```java
java.util.List<String> names = new java.util.ArrayList<>();
names.add("An");
// names.add(42); // Compile-time error
```

Yet a raw alias can insert incompatible data:

```java
java.util.List<String> names = new java.util.ArrayList<>();
java.util.List raw = names;
raw.add(42); // Unchecked warning
// String s = names.get(0); // May throw ClassCastException
```

When an object is used under type `List<String>` yet contains `Integer`, we have **heap pollution**. The fact that `names` looks properly generic in source code does not guarantee every element stays valid if an unsafe access path exists.

Nor should you think casting `(List<String>) raw` fixes heap pollution. That cast may not fail immediately, because the runtime does not verify the list's `String` parameter. To restore trustworthiness, inspect the contents and copy/normalize data into a new collection.

### What do unchecked warnings tell us?

`unchecked` means **the compiler cannot fully prove the type safety** of the conversion or call. It is a helpful warning, not necessarily a syntax error.

Typical remedies include:

1. Replace raw `List` with `List<?>` when only reading or inspecting structure.
2. Use explicit parameterized types on APIs receiving/returning data.
3. Iterate, validate, and convert each element when reading untrusted data.
4. Narrow the scope of `@SuppressWarnings("unchecked")` to the block proven safe and document the invariant.
5. Avoid chained unchecked casts that mislead downstream API layers about data safety.

## 10. When can we move from `List<?>` to `List<String>`?

After checking:

```java
Object input = java.util.List.of("An", "Binh");
if (input instanceof java.util.List<?> values) {
    boolean allStrings = values.stream()
            .allMatch(String.class::isInstance);
    // values still has static type List<?> even though allStrings is true.
}
```

The Java compiler **does not automatically promote** `List<?>` to `List<String>` just because a boolean predicate returned `true`. There are two options worth considering:

- If you need to return a guaranteed `List<String>`, check **every element** and add them to a new `ArrayList<String>`. The result has the right static type with no unchecked cast; you can use `List.copyOf` if you want the resulting collection to be structurally unmodifiable.
- If you only need to read without asserting all elements, keep `List<?>` and check each value at the point of use.

Even when all elements are currently `String`, a **mutable** list could be modified through another alias after the check. Therefore, checking and then casting the original reference to `List<String>` can be unsafe if other code can still mutate the list. Copying after validation separates the result structure from the source, though creating a consistent snapshot still requires controlling concurrent mutation during traversal.

### The `null` case

`String.class.isInstance(null)` is `false`, and `null instanceof String` is also `false`. Therefore, the validator in the runnable example treats `null` as invalid.

A general `List<String>` **does not forbid null by default**: a Java type parameter is not a non-null type annotation. If business rules permit null, express a dedicated predicate such as `value == null || value instanceof String`; also remember that `List.copyOf` rejects null elements.

## 11. Why can `List<?>[]` be created while `List<String>[]` cannot?

Java arrays know their **runtime component type**, whereas the generic element type `List<String>` is non-reifiable. Therefore:

```java
// Valid:
java.util.List<?>[] groups = new java.util.List<?>[2];
groups[0] = java.util.List.of("An");
groups[1] = java.util.List.of(42);

// Invalid:
// java.util.List<String>[] names = new java.util.List<String>[2];
```

`List<?>` is reifiable, so the array has a component type suitable for runtime checking. However, `List<String>` is non-reifiable, causing direct creation of an array with component `List<String>` to be forbidden.

A striking difference:

```java
Object[] array = new String[1];
try {
    array[0] = 42;
} catch (ArrayStoreException exception) {
    System.out.println("ArrayStoreException");
}
```

With a runtime `String[]` array, the JVM catches the error immediately when writing a wrong-typed value. With an `ArrayList<String>` polluted by a raw alias, the error may only appear when reading via a cast to `String`. Both mechanisms involve type checking, yet **the kind of runtime information preserved is different**.

## 12. Does Reflection seeing `List<String>` contradict erasure?

No. Class files can contain metadata about **generic declarations**, such as the `Signature` attribute. Reflection can read the declared type of a field:

```java
class FieldHolder {
    java.util.List<String> names;
}
```

For example, `FieldHolder.class.getDeclaredField("names").getGenericType()` can describe `List<String>`; while `getType()` reflects the raw interface `List`.

Declaration information does not mean that every list object attached to the field carries a separate runtime class `List<String>`, or that every value inserted through raw/unchecked code is a `String`.

Therefore, when receiving an object of unknown origin, reflection only tells you **the contract declared somewhere**; verifying actual data still requires appropriate checks.

## 13. Common misconceptions

**Misconception 1 — "Pattern matching `instanceof` can read generic type arguments."** False. It only binds a variable when the runtime type check is valid; `List<?> values` does not become `List<String>`.

**Misconception 2 — "Using `instanceof List<?>` is enough to know a list contains only `String`."** False. It only confirms the overall type of the object.

**Misconception 3 — "Casting `(List<String>)` checks every element."** False. This can be an unchecked cast; type errors may surface only when retrieving an element as `String`.

**Misconception 4 — "A pattern variable can be used anywhere after `if`."** False. Scope depends on control flow; `&&` and guard clauses follow different rules from `||`.

**Misconception 5 — "Type variable `T` is a runtime class directly usable in `instanceof`."** False. `T` is not a reifiable type and has no ordinary `T.class`.

**Misconception 6 — "No `ClassCastException` at cast time means the data already has the right type."** False. An unchecked cast may fail to check type arguments; wrong data only reveals itself when used.

**Misconception 7 — "`List<String>` is non-reifiable, so the compiler does not check generics."** False. The generic type system still checks at compile time; non-reifiable refers to the ability to perform full checks at runtime.

**Misconception 8 — "Reflection sees `List<String>`, so any list can be cast to `List<String>`."** False. Declaration metadata differs from per-element evidence on a runtime object.

**Misconception 9 — "After validating the whole list, all future reads are safe."** Not guaranteed if the list is modified through another alias. Mutation control or creating a trustworthy snapshot/copy is required.

## 14. Self-check exercises

**Question 1.** What does `Object x = List.of("A", 7); x instanceof List<?>;` evaluate to?

`true`. Only the outer type is checked; an `Integer` inside the list does not make `instanceof List<?>` return `false`.

**Question 2.** Given `Object x`, why is `x instanceof List<String> names` not a way to check all elements?

Because the `String` type argument of `List<String>` is not reifiable at runtime for that kind of check. Use `List<?>` and check each element.

**Question 3.** Does `Object x = List.of("A", 7); List<String> y = (List<String>) x;` necessarily throw an exception immediately at the cast?

No. The cast can succeed when the object is a `List`; `ClassCastException` may only happen when retrieving the `Integer` element to use as `String`.

**Question 4.** Why can `values` be used on the RHS in `input instanceof List<?> values && !values.isEmpty()`?

Because the `&&` operator only evaluates the RHS when the pattern on the LHS has matched, so `values` is validly in scope there.

**Question 5.** Does `Class<String>` allow checking an entire `List<String>` with a single `cast` call?

No. `String.class` checks a single `String` object; it does not fully describe the type parameter inside a `List` and does not scan all elements.

**Question 6.** If a function has already checked every element is `String`, why does `List<?> values` still not automatically become `List<String>`?

Because Java does not use the boolean result of an arbitrary validator to automatically change generic type arguments in the static type system. A checked conversion is needed, or else keep the wildcard type.

## 15. How to apply when designing APIs

When receiving data, clearly decide **what you need to know**:

1. Only want to know if it is a `List`: `input instanceof List<?>` is appropriate.
2. Want to handle each element according to its runtime class: use `List<?> values`, then patterns like `element instanceof String s` or patterns for the appropriate class.
3. Want to guarantee **every** element is `String`: iterate through all elements and reject non-matching data.
4. Want to return a trustworthy `List<String>`: validate and copy elements into a new collection with static type `List<String>`.
5. Want to check objects of caller-specified type `T`: use `Class<T>` when `T` is a class representable by that token; for nested generics, use a schema or explicit structural validator.
6. Seeing an `unchecked` warning: inspect the cause and trust boundary; do not treat `@SuppressWarnings` as a data-sanitization measure.

**Conclusion:** `instanceof` type patterns help Java write cleaner and safer runtime class/interface checks, yet they do not reverse **type erasure** to recover the `T` or `List<String>` argument of individual generic instances. Casting to a generic parameterized type can produce unchecked warnings and does not inspect every element. When a contract demands a specific element type, combine overall checks, actual data validation, and controlled conversion/copying.