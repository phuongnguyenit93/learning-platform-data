# Why Can't All Parameterized Types Be Matched Directly in Java?

## 1. Where does the problem come from?

Consider a generic list:

```java
import java.util.List;

Object value = List.of("Java", "Pattern");
```

When reading `value`, we might want to check "is this a list of strings?" using:

```java
// Does not compile when value has static type Object:
// if (value instanceof List<String> names) {
//     System.out.println(names.get(0).toUpperCase());
// }
```

Java cannot perform that check safely based solely on the object at runtime. The main reasons are **type erasure** and the requirement that an `instanceof` check must be able to verify the target type according to the language rules.

However, the accurate conclusion is: **you cannot arbitrarily match every parameterized type from a broad-typed expression such as `Object`**. Not every syntax with generic type arguments in `instanceof` is strictly forbidden. Java also relies on the **static type of the expression before `instanceof`** to allow certain safe checks. The sections below explain both cases.

This article uses `instanceof` type patterns, which became stable in Java 16 and work on Java 17+.

## 2. What is a parameterized type?

In Java, `List<E>`, `Map<K, V>`, and `Box<T>` are generic declarations. When type arguments are supplied for the type parameters, we get **parameterized types**:

- `List<String>`: a list declared to hold `String`.
- `List<Integer>`: a list declared to hold `Integer`.
- `Map<String, Integer>`: a map from `String` to `Integer`.
- `List<?>`: a list with an unknown type argument.
- `List<? extends Number>`: a list with an unknown type argument bounded by `Number`.

Type arguments help the compiler check calls like `list.add(...)`, the return type of `get(...)`, and generic constraints at **compile time**. It does not mean the JVM creates separate `ArrayList<String>` and `ArrayList<Integer>` classes.

For example:

```java
List<String> words = List.of("a", "b");
List<Integer> numbers = List.of(1, 2);

System.out.println(words.getClass() == numbers.getClass()); // true
```

In the `List.of(...)` example, the objects belong to the same JDK runtime implementation class. This illustrates why **looking only at the object's class is not enough to infer `String` or `Integer`**. On the other hand, you should not rely on the specific implementation class that `List.of` chooses, because that is an implementation detail.

## 3. What information does type erasure remove?

Java generics are primarily implemented using **type erasure**: after the compiler checks type constraints, the bytecode uses types with their generic parameters erased in many places. Both `List<String>` and `List<Integer>` are generally handled at runtime as the `List` interface.

There are two different kinds of information to distinguish:

| Information | Can the compiler know | Can the JVM usually check directly with `instanceof` |
| --- | --- | --- |
| Is the object a `List`? | Yes | Yes |
| Is the object an `ArrayList`? | Yes | Yes |
| Are all elements of type `String`? | Can be known from declarations or code analysis | Cannot be inferred solely from the runtime class of `List` |
| Is the specific generic argument `String` or `Integer`? | Can be based on the static type | Usually not retained on each object for `instanceof` checks |
| Is a single element currently a `String`? | Possibly | Yes, if checking the element itself |

Some generic signatures may be stored in **declaration metadata** for reflection, but that metadata is not proof of the generic arguments of *every specific running object*. Do not confuse reflection information on a field or class with the ability to ask a `List<?>` instance "does this have `String` as its type argument inside?".

For example, even if a list currently contains only strings, `List<Integer>` and `List<String>` are not distinguished by a pure runtime check on the list's class.

## 4. Reifiable types: types with enough information to check at runtime

In Java, a **reifiable type** is a type whose information needed for type checking remains available at runtime according to the language rules (JLS §4.7).

Common cases include:

- Non-generic types such as `String`, `Integer`, `Runnable`, and `Number`.
- Raw types such as `List` and `Map`; however, using raw types usually loses generic type safety.
- Parameterized types where **all** type arguments are unbounded wildcards `?`, such as `List<?>` and `Map<?, ?>`.
- Arrays with a reifiable component type, such as `String[]` or `List<?>[]`.

Conversely, the following types are generally **non-reifiable**: `List<String>`, `List<Integer>`, `Map<String, Integer>`, `List<? extends Number>`, and `List<List<?>>`. A type variable `T` is also not a type that can be arbitrarily matched via `instanceof T`.

**Why is `List<?>` reifiable while `List<String>` is not?**

`List<?>` only requires determining whether the object implements `List`. It does not promise that the elements are of a specific type, so the JVM has enough information to check the "is a `List`" part.

`List<String>` adds an assertion about the type argument `String`. That information is usually erased at runtime, so from an `Object` expression, the JVM cannot verify that assertion using `instanceof` alone.

```java
Object value = java.util.List.of("A", "B");

if (value instanceof java.util.List<?> items) {
    System.out.println(items.size()); // 2
}

// Invalid from Object:
// if (value instanceof java.util.List<String> names) { ... }
```

The pattern variable `items` has type **`List<?>`**, not `List<String>`. An element read via `items.get(0)` therefore only has a static type broad enough to be assigned to `Object`, unless we check further.

## 5. Why the compiler rejects certain patterns with generic type arguments

For an expression with static type `Object`:

```java
Object data = java.util.List.of("A", "B");

// Error: Object cannot be safely checked against List<String>
// using instanceof with this type pattern.
// if (data instanceof java.util.List<String> strings) { ... }
```

If the compiler allowed it, one might mistakenly assume that any matched `List` object contains `String` elements. However, a `List<Integer>` at runtime also implements the same `List` interface. Treating it as a `List<String>` could lead to a `ClassCastException` when reading elements under that false assumption.

The compiler also rejects impossible generic type checks such as:

```java
// With data of type Object, these type patterns are unsafe:
// if (data instanceof java.util.List<Integer> nums) { ... }
// if (data instanceof java.util.Map<String, Integer> dict) { ... }
// if (data instanceof java.util.List<? extends Number> nums) { ... }
```

**Cannot be replaced with a type variable**:

```java
// Illustrative snippet that cannot compile with instanceof T:
static <T> boolean invalid(Object data) {
    // return data instanceof T;
    return false;
}
```

The line `data instanceof T` is invalid because `T` is a type variable, which does not provide a runtime type that can be checked directly in that way. You can pass a `Class<?>` as a type token to check **an appropriate raw/reifiable class**, but it does not by itself verify the element type of `List<String>`.

## 6. Important exception: static typing can make a parameterized type pattern valid

This is an easy place to learn the wrong rule if you only remember "`instanceof` does not support generics".

Java considers **whether a safe cast/conversion is possible from the static type of the expression to the type in the pattern**. If the compiler already knows the generic type argument from the static type, a pattern with a specific type argument can be valid, even if that type pattern is non-reifiable on its own.

A valid example on Java 17:

```java
import java.util.ArrayList;
import java.util.List;

static void narrow(List<String> words) {
    if (words instanceof ArrayList<String> array) {
        System.out.println(array.size());
    }
}
```

Why it is valid:

1. `words` already has the static type **`List<String>`**. The compiler knows the `String` type argument constraint from the declaration, without needing to inspect elements at runtime.
2. The target is a concrete implementation class **`ArrayList<String>`**. The conversion relationship from `List<String>` to `ArrayList<String>` here can be safely checked using the static information already available.
3. At runtime, it only needs to check whether the object is actually an `ArrayList`; the `String` constraint is guaranteed by the static type system, assuming no raw/unchecked operations corrupted the data earlier.

Compare the five cases:

| Static type of expression | Pattern | Typical result on Java 17 |
| --- | --- | --- |
| `Object data` | `List<String> names` | Compile error: cannot safely check the `String` type argument |
| `Object data` | `List<?> names` | Valid: unbounded wildcard argument, reifiable |
| `List<String> words` | `ArrayList<String> array` | Valid: the static type already provides the `String` type argument |
| `List<?> unknown` | `ArrayList<String> array` | Compile error: cannot prove `String` |
| `List<?> unknown` | `ArrayList<?> array` | Valid: checks the implementation class, makes no promise about specific type arguments |

Therefore, do not assume that the JVM can read the `String` type argument from an `ArrayList` at runtime just because the `List<String> -> ArrayList<String>` example compiles. **The compiler relies on the generic constraint already present in the static type**. If the input is `Object` or `List<?>`, that proof is no longer there.

We must also separate **type validity** from whether the object is actually an `ArrayList`: a method accepting `List<String>` may be passed a different `List` implementation; in that case, the `ArrayList<String>` pattern simply does not match.

## 7. Complete Java 17 program: illustrating three kinds of checks

Save the following file as **ReifiableDemo.java**. The program does not use preview features:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class ReifiableDemo {
    static boolean allStrings(Object value) {
        if (!(value instanceof List<?> items)) {
            return false;
        }
        for (Object item : items) {
            if (!(item instanceof String)) {
                return false;
            }
        }
        return true;
    }

    static void inspect(Object value) {
        if (value instanceof List<?> items) {
            System.out.println("List size=" + items.size());
            System.out.println("All strings=" + allStrings(value));
            if (!items.isEmpty()
                    && items.get(0) instanceof String first) {
                System.out.println("First upper="
                        + first.toUpperCase());
            }
        } else {
            System.out.println("Not a List");
        }
    }

    public static void main(String[] args) {
        inspect(List.of("A", "B"));
        inspect(List.of("A", 7));
        inspect(null);

        List<String> typed =
                new ArrayList<>(List.of("x", "y"));
        if (typed instanceof ArrayList<String> arrayList) {
            System.out.println("ArrayList size="
                    + arrayList.size());
        }

        Object map = Map.of("k", 1);
        if (map instanceof Map<?, ?> entries) {
            System.out.println("Map size=" + entries.size());
        }
    }
}
```

Compile and run:

```bash
javac ReifiableDemo.java
java ReifiableDemo
```

Exact output:

```text
List size=2
All strings=true
First upper=A
List size=2
All strings=false
First upper=A
Not a List
ArrayList size=2
Map size=1
```

Analysis:

- Both `List.of("A", "B")` and `List.of("A", 7)` match `List<?>`. This pattern checks the **container kind**, not the type of each element.
- `allStrings` checks **each element**, so the first list returns `true` and the second list returns `false`.
- The first element of both lists is a `String`, so both print `First upper=A`. Checking one element does **not** imply the entire list consists of strings.
- `null instanceof List<?>` returns `false`. The `instanceof` condition does not throw a `NullPointerException` when the value is `null`.
- `List<String> typed` is allowed to be checked against `ArrayList<String>` because the type argument information is already in the static type; runtime only needs to determine the implementation.
- `Map<?, ?>` is also a reifiable parameterized type because both type arguments are unbounded `?`.

If an empty list is passed, `allStrings` returns `true` by the logical rule "every element is a String" over an empty set. If business logic also requires the list to be **non-empty**, an additional `!items.isEmpty()` check is needed.

## 8. What should you do to safely obtain a `List<String>` from an `Object`?

First use the `List<?>` pattern to check the container, then check and add the verified elements into a new list with static type `List<String>`.

Example method (requires `import java.util.ArrayList;`, `import java.util.List;`, and `import java.util.Optional;`):

```java
static Optional<List<String>> validatedStrings(Object input) {
    if (!(input instanceof List<?> items)) {
        return Optional.empty();
    }

    List<String> result = new ArrayList<>(items.size());
    for (Object element : items) {
        if (!(element instanceof String text)) {
            return Optional.empty();
        }
        result.add(text);
    }
    return Optional.of(List.copyOf(result));
}
```

With the following standalone expressions:

```java
System.out.println(
        validatedStrings(List.of("A", "B")).orElseThrow());
System.out.println(
        validatedStrings(List.of("A", 7)).isEmpty());
System.out.println(
        validatedStrings(List.of()).orElseThrow());
```

Result:

```text
[A, B]
true
[]
```

This approach has the following characteristics:

- No unchecked cast from `List<?>` to `List<String>` is needed; each element is proven to be a `String` before being added to the result list.
- `List.copyOf(result)` returns an unmodifiable list, preventing the caller from depending on a source list that might still be mutated after validation.
- A `null` element will **not** match `instanceof String`, so the method returns `Optional.empty()`. If business logic allows null, you need to design separate handling, while keeping in mind that `List.copyOf` does not accept null elements.
- This is a **content-level** check, with time complexity proportional to the number of elements. The initial `instanceof List<?>` only checks the container kind and does not iterate over elements.

For input data from JSON, APIs, or external systems with complex structures, it is usually better to use a deserializer or schema validation with declared target types and field-by-field verification, rather than expecting a single `instanceof List<String>` to suffice.

## 9. Raw types and unchecked casts do not solve the problem

You can write:

```java
Object input = java.util.List.of("A", 7);

if (input instanceof java.util.List rawList) {
    System.out.println(rawList.size()); // 2
}
```

Checking the raw type `List` only proves that it is a `List`. It does **not** prove the element type. Widespread use of raw types also forfeits compile-time generic type checking.

Similarly, the cast snippet:

```java
@SuppressWarnings("unchecked")
static java.util.List<String> unsafe(Object input) {
    return (java.util.List<String>) input;
}
```

does not perform element-by-element verification. For a list containing an `Integer`, the `List<String>` promise is false even though the cast may pass the raw container check. A `ClassCastException` can appear **later**, when the program reads an element and uses it as a `String`.

Using `@SuppressWarnings("unchecked")` only hides the warning; it does not make the generic assertion true. If you truly must accept broad-typed data, check the elements and copy them as in Section 8, or preserve type information through the API from the start.

## 10. Arrays and generics: a useful comparison

Java arrays know their element type at runtime, whereas generic type arguments are usually erased:

```java
Object value = new String[] {"A", "B"};

if (value instanceof String[] strings) {
    System.out.println(strings.length); // 2
}
```

`String[]` is reifiable, so the check above is valid. For arrays of parameterized types with unbounded wildcards, `List<?>[]` is also a reifiable case supported by the language.

In contrast, you cannot use a runtime check from `Object` to directly verify an "array of `List<String>`" as `List<String>[]`. The generic `String` type argument inside each list still cannot be checked that way.

This difference also explains why Java forbids creating generic arrays like `new List<String>[10]`: arrays check their element type at runtime, whereas a specific generic element type no longer has full runtime information. When you need a dynamic generic collection, prefer `List<List<String>>` enforced by the type system instead of a generic array.

## 11. Common errors and misconceptions

| Misconception | Correction |
| --- | --- |
| "`List<String>` and `List<Integer>` are two different runtime classes." | Generic parameters are mostly erased; the runtime class is not enough to indicate the element type. |
| "`Object instanceof List<String>` should work when the list currently contains only Strings." | The compiler does not rely on inspecting all elements to validate that unsafe type pattern. |
| "Generic type arguments can never appear in `instanceof`." | `List<?>` and `Map<?, ?>` are reifiable; certain narrowing patterns like `List<String>` to `ArrayList<String>` are valid when the static type already has enough information. |
| "Matching `List<?>` means all elements have the same type." | `?` only means the type argument is unknown; you must check elements if you want to guarantee a specific type. |
| "`List<? extends Number>` will be checked just like `List<?>` from Object." | A bounded wildcard differs from an unbounded `?` wildcard; it is not reifiable under the same rule. |
| "If `List<?>` matches, calling `get(0)` is safe." | You must check that the list is non-empty; `get(0)` also returns `Object` statically. |
| "Checking that the first element is a String proves the whole List is." | It only proves the element just checked; you must iterate over all elements or rely on a typed API contract. |
| "Casting `(List<String>) input` verifies the contents." | That is an unchecked cast; the element type is not guaranteed. |
| "Using `Class.isInstance` can check `List<String>`." | `Class` checks a raw/reifiable class and does not by itself verify the container's `String` type parameter. |
| "Generics never leave any trace at runtime." | Some generic declaration signatures have metadata; that does not make every generic argument of every instance verifiable. |

A common phrasing mistake: claiming that parameterized types can **never** appear on the right-hand side of `instanceof`. Be more specific about **reifiability**, **the static type of the expression**, and **safe type conversion**. These are the three factors that explain each case accurately.

## 12. Self-check exercises

### Exercise 1 — Which cases are valid?

Given:

```java
Object x = java.util.List.of("a");
```

Classify the following patterns:

1. `x instanceof java.util.List<?> list`: **valid**, because `List<?>` is reifiable.
2. `x instanceof java.util.List<String> list`: **compile error** from `Object`, cannot safely check the `String` type argument.
3. `x instanceof java.util.Map<?, ?> map`: **syntactically and type-wise valid**, but returns `false` at runtime because the object is a `List`.
4. `x instanceof java.util.List<? extends Number> nums`: **compile error** from `Object` because the target type is non-reifiable and there is no sufficiently strong proof from the static type.

### Exercise 2 — Why is this snippet valid?

```java
static void check(java.util.List<String> values) {
    if (values instanceof java.util.ArrayList<String> arr) {
        System.out.println(arr.size());
    }
}
```

**Answer:** the parameter `values` already has the static type `List<String>`; the compiler knows the `String` generic argument. The runtime check only needs to distinguish whether the object is an `ArrayList` or another implementation. This code does not prove that Java has a mechanism to read the `String` generic argument from a runtime instance.

### Exercise 3 — Checking actual contents

Given `Object data = java.util.List.of("Java", 21);`. Why does `data instanceof List<?>` evaluate to true while `allStrings(data)` in Section 7 returns `false`?

**Answer:** `List<?>` only checks that the data is a `List` container. `allStrings` iterates through the elements and encounters the `Integer` `21`, so it concludes the list does not consist solely of strings.

### Exercise 4 — Writing a safe API

Write a method that accepts `Object` and returns `Optional<List<String>>` if all elements are `String`, or `Optional.empty()` otherwise, without using an unchecked cast.

**Hint and solution:** see `validatedStrings` in Section 8. Check `List<?>` first, then match each element with `String text`, add to a new `List<String>`, and return the resulting list. Decide clearly whether empty lists or null elements are allowed according to business requirements.

## 13. Key takeaways

**`instanceof` can check an object's runtime type relationship, but cannot arbitrarily verify erased generic type parameters.** For an `Object`-typed input, use `List<?>` or `Map<?, ?>` to verify the container; if you need to assert the element type, verify each element.

Do not overgeneralize a rule that all parameterized types are forbidden in `instanceof`. When the static type of the expression already guarantees the generic type argument, a narrowing type pattern such as `List<String> -> ArrayList<String>` can be valid on Java 17. That validity comes from **compile-time type information**, not from the JVM's ability to read back the `String` type parameter on the object.

Official documentation:
- [Java Language Specification, Java SE 17 — Reifiable Types (§4.7)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7)
- [Java Language Specification, Java SE 17 — The instanceof Operator (§15.20.2)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Oracle Java 17 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html)
