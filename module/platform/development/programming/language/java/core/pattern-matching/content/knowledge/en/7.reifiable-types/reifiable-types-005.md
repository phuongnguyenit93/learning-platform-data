# Patterns with Wildcards in Java 21

## 1. Objectives and Context

When learning pattern matching with Java generics, you will encounter code like this:

```java
Object candidate = java.util.List.of("A", "B");

if (candidate instanceof java.util.List<?> elements) {
    System.out.println(elements.size());
}
```

`List<?> elements` is a **type pattern**: the program checks whether `candidate` is a `List` and, if it matches, creates a **pattern variable** `elements` of type `List<?>`. The `?` here is a **generic wildcard type argument**, expressing an "unknown element type". It does **not** automatically check each element, nor is it an independent kind of pattern.

This lesson explains how to read and write patterns with wildcards in Java 21, why `List<?>` is allowed in `instanceof` or `switch`, the limits of **type erasure**, how to safely check elements, interactions with **record patterns**, and common mistakes.

After this lesson, you should be able to distinguish:

1. `List<?> list`: a type pattern with an **unbounded wildcard** in the generic type.
2. `List<String> list`: a concrete parameterized type, which usually **cannot be safely checked from `Object`**.
3. `List<? extends Number>` and `List<? super Integer>`: bounded wildcards useful in API declarations, but without the same runtime-check capability as `List<?>`.
4. `Box<?> box`: a type pattern for a generic record; its components can be inspected after matching.
5. The `?` of generics differs from the `_` of **unnamed patterns** (preview in Java 21).

## 2. What Does the `?` Wildcard Actually Represent?

Generics allow defining a type that contains another type:

```java
java.util.List<String> words = java.util.List.of("Java", "Pattern");
java.util.List<Integer> numbers = java.util.List.of(10, 20);
```

`List<String>` and `List<Integer>` share the same raw type `List`, but the compiler tracks their element types separately to support type safety.

When you only need to know "this is a list, regardless of the element type", use an **unbounded wildcard**:

```java
java.util.List<?> unknownElements = words;
unknownElements = numbers;
```

`List<?>` means: *this list has some element type, but at the call site where we are reading it, we do not know what that type is*. It does **not** mean "a list guaranteed to hold every type", and it certainly does not mean "the elements have been verified as `Object` in the sense that any object can be added".

Reading a value from `List<?>` safely:

```java
Object first = unknownElements.get(0);
```

However, you cannot add an arbitrary `String` or `Integer`:

```java
// COMPILE ERROR: actual element type is unknown
unknownElements.add("new item");
```

Passing `null` is permitted by the type bounds of `List<?>` in many cases, but **compilability does not guarantee the list is modifiable**: `List.of(...)` is immutable/unmodifiable and will reject update operations. Do not use `add(null)` as a workaround for element type issues.

## 3. Why Can `List<?>` Be Used in Patterns?

### 3.1. Type Erasure and Reifiable Types

Java generics use **type erasure**: at runtime, both `ArrayList<String>` and `ArrayList<Integer>` objects are identified by the class `ArrayList`; the JVM does not retain a "runtime `String` tag" for the entire list object for `instanceof` to verify.

The Java Language Specification §4.7 calls a type that has enough information to perform runtime checks a **reifiable type**. For generics, a parameterized type is considered reifiable when **all of its type arguments are unbounded wildcards**.

| Type | Reifiable in Java 21? | Notes |
| --- | --- | --- |
| `String` | **Yes** | Non-generic class type |
| `List<?>` | **Yes** | Single type argument is an unbounded `?` |
| `Map<?, ?>` | **Yes** | Both type arguments are `?` |
| `Box<?>` | **Yes** | If `Box<T>` is a generic class or record |
| `List` (raw) | **Yes** | Raw type can be used, but loses generic safety when operating on it |
| `List<String>` | **No** | `String` type info cannot be checked from an arbitrary object |
| `List<? extends Number>` | **No** | Bounded wildcard, not unbounded `?` |
| `List<? super Integer>` | **No** | Bounded wildcard |
| `Map<String, ?>` | **No** | Has a concrete `String` type argument |
| `List<List<?>>` | **No** | The outer `List`'s argument is `List<?>`, not `?` directly |

Therefore, checking from a value with static type `Object`:

```java
Object candidate = java.util.List.of("one", "two");

if (candidate instanceof java.util.List<?> elements) {
    System.out.println(elements.size()); // Valid
}
```

The pattern only confirms that **the container type is `List`**. Even though the example uses `List.of("one", "two")`, the pattern `List<?> elements` itself knows nothing about `String` in the elements.

### 3.2. Invalid Patterns When the Source Is `Object`

```java
// CODE SNIPPET INTENTIONALLY DOES NOT COMPILE
Object candidate = java.util.List.of("one", "two");

if (candidate instanceof java.util.List<String> strings) {
    System.out.println(strings.get(0));
}
```

This is a check from `Object` to `List<String>` that cannot be fully verified by the JVM; the compiler rejects it. There is no way to turn `instanceof` into an automatic check of every element by writing a concrete generic argument.

Similarly, from `Object`:

```java
// Both are invalid from an Object source:
candidate instanceof java.util.List<? extends Number> nums
candidate instanceof java.util.Map<String, ?> records
```

**Important nuance:** do not turn the examples above into a rule that "every `instanceof` with a concrete generic type is forbidden". Since Java 16, the compiler allows certain cases when the **static type of the left-hand operand** already provides enough information and the cast is a *checked cast conversion*. For example:

```java
java.util.List<String> words = new java.util.ArrayList<>();

if (words instanceof java.util.ArrayList<String> arrayList) {
    System.out.println(arrayList.size());
}
```

This case is valid because `words` already has the type `List<String>` at compile time; the additional runtime check mainly verifies the concrete class `ArrayList`. It is **not** checking the type argument of an arbitrary list obtained from `Object`.

The right way to evaluate this is to see whether the compiler can perform a **checked cast** from the *left-hand static type* to the pattern type (JLS §14.30.3 and §5.5).

## 4. Type Patterns with `List<?>` in `instanceof`

Common pattern:

```java
static String sizeOfList(Object candidate) {
    if (candidate instanceof java.util.List<?> elements) {
        return "size=" + elements.size();
    }
    return "not a list";
}
```

Syntactic structure:

- `candidate`: the value to check.
- `instanceof`: the operator that tests and, when matched, introduces a variable.
- `List<?>`: a **reifiable type** permitted for a type pattern from `Object`.
- `elements`: a **pattern variable** scoped to the branch where the compiler knows the pattern matched.

If `candidate` is `null`, the condition does not match. If it is a `List<String>`, `List<Integer>`, `List<Object>`, or another `List` implementation, the pattern still matches because it checks the **container type**.

What you can do once matched:

```java
if (candidate instanceof java.util.List<?> elements) {
    int size = elements.size();
    for (Object element : elements) {
        System.out.println(element);
    }
}
```

What you must **not** infer:

- Do not treat `elements` as `List<String>` and call `String` methods directly on `elements.get(0)`.
- Do not infer that every element is non-`null`; some lists allow `null`.
- Do not infer that the list is modifiable; `List.of`, `List.copyOf`, and many other implementations are unmodifiable.
- Do not infer the element type based on the first element: the list may be heterogeneous or empty.

## 5. Patterns with Multiple Wildcards: `Map<?, ?>`

When a generic class/interface has multiple type parameters, use a corresponding wildcard for each parameter if you want a reifiable type:

```java
static String describeMap(Object candidate) {
    if (candidate instanceof java.util.Map<?, ?> entries) {
        return "entries=" + entries.size();
    }
    return "not a map";
}
```

`Map<?, ?> entries` is **one type pattern**, not two patterns. The two `?` tokens are the type arguments of `Map<K, V>`:

- `K`: unknown key type.
- `V`: unknown value type.
- `entries`: the pattern variable representing **the entire map**.

If you need to iterate:

```java
if (candidate instanceof java.util.Map<?, ?> entries) {
    for (java.util.Map.Entry<?, ?> entry : entries.entrySet()) {
        Object key = entry.getKey();
        Object value = entry.getValue();
        System.out.println(key + " -> " + value);
    }
}
```

You can read keys/values as `Object` and check each value further. However, you cannot assume it is a `Map<String, Integer>` just because `Map<?, ?>` matched.

For example, a `Map<?, ?>` may have `String`, `Integer`, or other key types; to use the right domain types, check the key/value before processing.

## 6. Checking Individual Elements with Patterns After the Container Matches

This is the most practical technique when receiving data from an API or from a place declared with a general type:

```java
static int sumIntegers(Object candidate) {
    if (!(candidate instanceof java.util.List<?> elements)) {
        return 0;
    }
    int total = 0;
    for (Object element : elements) {
        if (element instanceof Integer number) {
            total += number;
        }
    }
    return total;
}
```

The program performs **two layers of checks**:

1. `candidate instanceof List<?> elements` confirms this is a list.
2. `element instanceof Integer number` checks each element before using it as an `Integer`.

This is not "the pattern automatically inspecting the element type of `List<Integer>`"; it is **checking elements with a second pattern**.

For example, `List.of(1, "skip", 2, 3L, 4)` returns `7`, because only the `Integer` values 1, 2, and 4 are summed; `String` and `Long` do not match `Integer`.

### When You Need an Actual `List<String>`

A safe approach is to **check each element and create a new list with a concrete static type**, rather than casting blindly:

```java
static java.util.List<String> requireStrings(Object candidate) {
    if (!(candidate instanceof java.util.List<?> values)) {
        throw new IllegalArgumentException("Expected List");
    }

    java.util.ArrayList<String> result = new java.util.ArrayList<>();
    for (Object value : values) {
        if (!(value instanceof String text)) {
            throw new IllegalArgumentException(
                    "Expected String element, got " + value);
        }
        result.add(text);
    }
    return java.util.List.copyOf(result);
}
```

This is an **illustrative method** that can be placed in a valid Java class. It intentionally rejects `null` because `null instanceof String text` is false. The `List.copyOf` result does not allow adding elements and is independent of the source list.

Creating a copy after checking has the advantage that the resulting data genuinely satisfies the promised element type and does not depend on later mutations to the input list.

## 7. Using Wildcards with Pattern `switch` in Java 21

**Pattern matching for `switch`** is a standard feature in Java 21. You can place a type pattern using wildcards in a `case` branch:

```java
static String category(Object candidate) {
    return switch (candidate) {
        case null -> "null";
        case java.util.List<?> list -> "list: " + list.size();
        case java.util.Map<?, ?> map -> "map: " + map.size();
        default -> "other";
    };
}
```

`case List<?> list` checks the container type; `case Map<?, ?> map` checks another container type. The pattern variable `list` or `map` is scoped only to its corresponding branch.

### 7.1. `when` Guards with `List<?>`

If you need to distinguish an empty list from a non-empty list:

```java
return switch (candidate) {
    case null -> "null";
    case java.util.List<?> values when values.isEmpty() -> "empty list";
    case java.util.List<?> values -> "list size=" + values.size();
    default -> "other";
};
```

The branch with `when` is evaluated after the `List<?> values` type pattern matches. `when` is a **guard** on the `case` label, not a separate kind of wildcard pattern.

Place the specific guarded branch **before** the general branch. If you put `case List<?> values ->` without a guard first, it will cover all lists and make the subsequent empty-list branch unreachable (violating the **dominance** rule).

### 7.2. Avoid Confusing Wildcards with Element Type Checks

This snippet does not branch by `List<String>` and `List<Integer>`:

```java
// CODE SNIPPET INTENTIONALLY DOES NOT COMPILE, source is Object
switch (candidate) {
    case java.util.List<String> strings -> System.out.println("strings");
    case java.util.List<Integer> ints -> System.out.println("ints");
    default -> {}
}
```

When the source is `Object`, the JVM has no generic information to distinguish the two lists by type parameter. Use `case List<?> values` and then check each element, or use a domain model with distinct runtime types (for example, `StringItems` and `NumberItems` records).

### 7.3. `null` and Exhaustiveness Rules

`case List<?> values` does not match `null`. If the `switch` can receive `null`, handle it explicitly with `case null` or check beforehand. `default` should not be assumed to catch `null`; in a Java 21 pattern `switch`, when a matching `null` label is missing, `null` normally leads to a `NullPointerException`.

A `switch` expression requires branches that cover all possible values. `default` in the example above makes the expression exhaustive for all other values.

## 8. Distinguishing Unbounded and Bounded Wildcards

There are three basic generic wildcard syntaxes:

| Syntax | Type-level Meaning | Typical Usage |
| --- | --- | --- |
| `List<?>` | Unknown element type | Inspecting/counting/iterating; checking container with a pattern |
| `List<? extends Number>` | An unknown type that is a subtype of `Number` | **Reading** elements as `Number` |
| `List<? super Integer>` | An unknown type that is `Integer` or a supertype of it | Can **add `Integer`**, read out as `Object` |

Examples of **valid** declarations:

```java
java.util.List<? extends Number> measured =
        java.util.List.of(10, 20.5);
Number first = measured.get(0);

// ArrayList<Number> can serve as a target for a lower-bound wildcard:
java.util.List<? super Integer> sink =
        new java.util.ArrayList<Number>();
sink.add(42);
Object stored = sink.get(0);
```

This is the rule commonly remembered as **PECS: Producer Extends, Consumer Super**. With `? extends Number`, you can read `Number` but cannot arbitrarily add `Number` because the actual list might be `List<Integer>`. With `? super Integer`, you can add `Integer`, but when reading you know no more specific type than `Object`.

**Important:** `List<? extends Number>` and `List<? super Integer>` are usable in **variable declarations, parameters, and return types**, but they are **not reifiable**. Therefore, by default they cannot be used in a type pattern from an `Object` source.

Incorrect example:

```java
// CODE SNIPPET INTENTIONALLY DOES NOT COMPILE, candidate has type Object
if (candidate instanceof java.util.List<? extends Number> nums) {
    // ...
}
```

Fix it by identifying the container at runtime, then checking its contents:

```java
if (candidate instanceof java.util.List<?> elements) {
    for (Object element : elements) {
        if (element instanceof Number number) {
            System.out.println(number.doubleValue());
        }
    }
}
```

This fix **only processes elements that match `Number`**; it does not prove that every element in the list is a `Number`. If the business logic requires *all* elements to be numbers, you must check and handle non-matching cases (e.g., throw an exception or reject the entire list).

## 9. Generic Records and Patterns with Wildcards

In Java 21, records can also accept type parameters:

```java
record Box<T>(T value) {}
```

When the initial data has type `Object`, use a wildcard in a **type pattern** to recognize a `Box` regardless of its type parameter:

```java
static String boxKind(Object candidate) {
    if (candidate instanceof Box<?> box) {
        Object value = box.value();
        return value == null ? "empty box" : value.getClass().getSimpleName();
    }
    return "not a box";
}
```

`Box<?> box` is a type pattern. It confirms the object is an instance of the `Box` record, **not** whether `T` is `String`, `Integer`, or another type. `box.value()` can be read as `Object`; if you need to handle a specific type, check further with `instanceof`:

```java
if (candidate instanceof Box<?> box
        && box.value() instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

Both pattern variables `box` and `text` are only in scope along the path where the `&&` expression proves a match. This preserves **type safety** without using raw `Box` or an unchecked `Box<String>` cast.

### 9.1. Wildcards in Record Patterns

You can also use a wildcard in the **record type** of a record pattern:

```java
if (candidate instanceof Box<?>(var item)) {
    System.out.println(item);
}
```

Here:

- `Box<?>(var item)` is a **record pattern**, because it has a component list `(...)`.
- `Box<?>` is a generic type using an unbounded wildcard, suitable for checking from `Object`.
- `var item` is a component type pattern whose type is inferred from the component of `Box<?>`; when `T` is unknown, treat `item` as a value that can be viewed as `Object`.
- This line does **not** require `item` to be a `String`. If you need a `String`, check further with `item instanceof String text`.

For a value with a **concrete static type** such as `Box<String>`, Java 21 can infer the type argument when using the record pattern `Box(var text)`, and the variable `text` has type `String`. This is **inference from the static type**, not the JVM recovering an erased generic parameter from an `Object`.

### 9.2. Concrete Generic Types in Record Patterns: Limitations

```java
// CODE SNIPPET INTENTIONALLY DOES NOT COMPILE WITH AN Object SOURCE
if (candidate instanceof Box<String>(String text)) {
    // ...
}
```

With `candidate` having static type `Object`, the compiler cannot verify a checked conversion `Object` → `Box<String>`, so the example above fails to compile. However, if the input already has static type `Box<String>`, the pattern `Box<String>(String text)` can be valid and usable (subject to the checked cast rules for record patterns).

Do not confuse a **generic record pattern** with a **type pattern**. `Box<?> box` binds the whole object; `Box<?>(var item)` deconstructs the component and binds `item` separately.

## 10. Wildcard Capture: Why Can't You Assign a Concrete Type Yourself?

`List<?>` has an element type that is **unknown yet consistent for that list**. The compiler may create an internal type name to represent it (*capture conversion*), often seen in error messages as `CAP#1`.

For example:

```java
static void inspect(java.util.List<?> values) {
    Object first = values.get(0);
    // String s = values.get(0); // ERROR: not guaranteed that the element is a String
}
```

If you really need to work with the preserved element type, you can use a **generic helper method**. This helps the compiler maintain the relationship between values, but it **does not add the ability to check the type argument at runtime**.

For example, a method that only **counts** a list does not need to know the element type:

```java
static int count(java.util.List<?> values) {
    return values.size();
}
```

A method that wants to select an element and operate on its real type needs one of two approaches:

1. Declare an API with a concrete type parameter: `<T> T first(List<T> values)` when the caller knows `T`.
2. If the input is `Object` or `List<?>`, use patterns on individual elements: `if (value instanceof String text)`, `if (value instanceof Integer number)`, etc.

Do not fix the error by using an unchecked cast:

```java
// PRONE TO ClassCastException OR LATER BUGS
java.util.List<String> strings =
        (java.util.List<String>) candidate;
```

A cast can produce an `unchecked` warning when the type argument cannot be proven; the runtime does not automatically check every element. A list that actually contains `Integer`s can pass the container cast and only fail later when subsequent code reads elements as `String`.

## 11. Distinguishing `?` from Symbols That Look Like Wildcards

| Syntax | Is it a "wildcard pattern" in Java 21? | Explanation |
| --- | --- | --- |
| `List<?> list` | Not a separate pattern kind | **Type pattern** with a generic unbounded wildcard |
| `Map<?, ?> map` | Not a separate pattern kind | **Type pattern** with two generic wildcards |
| `Box<?>(var item)` | Not a separate pattern kind | **Record pattern** with a wildcard generic type |
| `case _ -> ...` | Not a valid general wildcard syntax in Java 21 | Do not use `_` as a standalone `case` label in Java 21 |
| `Point(var x, _)` | **Unnamed pattern** (preview in Java 21) | Ignores a record component; separate `_` syntax, unrelated to `?` |
| `case String _ -> ...` | Type pattern with an **unnamed pattern variable** (Java 21 preview) | Requires enabling preview in Java 21 |
| `java.util.regex.Pattern` | No | Regular expression API, not part of this pattern-matching grammar |

In standard Java 21 code, you should use `List<?> list` and check elements with **standard type patterns**. No `--enable-preview` is needed for generic wildcards, type patterns, record patterns, or pattern matching for `switch`.

The `_` of **unnamed patterns and variables** is a preview feature under JEP 443 in Java 21, and became standard in Java 22 under JEP 456. Do not apply Java 22's status retroactively to Java 21.

## 12. Complete Java 21 Example: Check Container Then Classify Contents

Save the following program as **`WildcardPatternDemo.java`**:

```java
import java.util.List;
import java.util.Map;

public class WildcardPatternDemo {
    record Box<T>(T value) {}

    static String describeElement(Object element) {
        return switch (element) {
            case null -> "null";
            case String text -> "String:" + text;
            case Integer number -> "Integer:" + number;
            default -> "other";
        };
    }

    static String describe(Object candidate) {
        return switch (candidate) {
            case null -> "null";
            case List<?> list when list.isEmpty() -> "empty list";
            case List<?> list ->
                    "list(size=" + list.size() + ", first="
                    + describeElement(list.get(0)) + ")";
            case Map<?, ?> map -> "map(size=" + map.size() + ")";
            case Box<?> box ->
                    "box(" + describeElement(box.value()) + ")";
            default -> "other";
        };
    }

    static int sumIntegers(List<?> values) {
        int total = 0;
        for (Object value : values) {
            if (value instanceof Integer number) {
                total += number;
            }
        }
        return total;
    }

    public static void main(String[] args) {
        System.out.println(describe(List.of()));
        System.out.println(describe(List.of("A", "B")));
        System.out.println(describe(List.of(7, 8)));
        System.out.println(describe(Map.of("code", 10)));
        System.out.println(describe(new Box<>("ready")));
        System.out.println(describe(new Box<>(42)));
        System.out.println(describe(null));
        System.out.println(describe("plain"));
        System.out.println(
                sumIntegers(List.of(1, "skip", 2, 3L, 4)));
    }
}
```

Using **JDK 21**:

```bash
javac --release 21 WildcardPatternDemo.java
java WildcardPatternDemo
```

Stdout output:

```text
empty list
list(size=2, first=String:A)
list(size=2, first=Integer:7)
map(size=1)
box(String:ready)
box(Integer:42)
null
other
7
```

Analysis:

- `List.of()` matches the `List<?> list when list.isEmpty()` branch.
- Both `List.of("A", "B")` and `List.of(7, 8)` match the **`List<?>`** branch, and then the first element is classified by `String text` or `Integer number`.
- `Map.of("code", 10)` matches `Map<?, ?>` without needing to know the key/value generics.
- Both `new Box<>("ready")` and `new Box<>(42)` match `Box<?> box`; `describeElement` inspects the inner value.
- `null` has its own branch; `"plain"` is not a container in any preceding branch, so it falls into `default`.
- `sumIntegers` only sums elements that are actually `Integer`, avoiding an improper cast to `List<Integer>`.

In this program, all pattern features used are **standard in Java 21**. There are no preview features, raw generic casts, or unchecked conversions.

## 13. Common Mistakes and How to Fix Them

### Mistake A: Assuming `List<?> list` verifies the type of every element

```java
// CODE SNIPPET INTENTIONALLY DOES NOT COMPILE
if (candidate instanceof java.util.List<?> list) {
    String first = list.get(0); // Not guaranteed to be a String
}
```

**Fix:** receive `Object first`, then use `if (first instanceof String text)` or `switch` on the actual type of each element.

### Mistake B: Replacing `?` with `String` in a pattern receiving `Object`

```java
// CODE SNIPPET INTENTIONALLY DOES NOT COMPILE
if (candidate instanceof java.util.List<String> strings) {
    // ...
}
```

**Fix:** use `List<?> values` and inspect the contents, or change the input API to carry a sufficiently concrete static type. Do not suppress unchecked warnings to "force" the runtime to understand generics.

### Mistake C: Using a bounded wildcard thinking `extends` enables deep checks

```java
// CODE SNIPPET INTENTIONALLY DOES NOT COMPILE from Object
if (candidate instanceof java.util.List<? extends Number> numbers) {
    // ...
}
```

**Fix:** `List<?> values` + check each element with `instanceof Number number`; if you need to guarantee the list contains only numbers, check **all** elements and build a properly typed copy.

### Mistake D: Adding a new value to `List<?>`

```java
// CODE SNIPPET INTENTIONALLY DOES NOT COMPILE
if (candidate instanceof java.util.List<?> list) {
    list.add("new"); // Compiler does not know T of list
}
```

**Fix:** if writing is needed, design the output with a concrete type and create a new list. Do not treat raw types as a safe fix.

### Mistake E: Two branches with the same `List<?>` pattern, but placing the broader branch first

```java
// CODE SNIPPET INTENTIONALLY DOES NOT COMPILE because the later branch is dominated
switch (candidate) {
    case java.util.List<?> list -> System.out.println(list.size());
    case java.util.List<?> list when list.isEmpty() ->
            System.out.println("empty");
    default -> {}
}
```

**Fix:** place the `when list.isEmpty()` branch first, and the general `List<?> list` branch afterward.

### Mistake F: Forgetting `null` when using pattern `switch`

A `case List<?> list` does not match `null`. **Fix:** add `case null` when the input may be missing, or check for `null` before the `switch`. Do not assume `default` always catches `null`.

### Mistake G: Confusing the `?` wildcard with the unnamed pattern `_`

`List<?> list` works in standard Java 21; `Box(var x, _)` is a different syntax belonging to Java 21 preview. **Fix:** read `?` as a generic type argument, and read `_` according to the unnamed pattern/variable rules of the appropriate JDK version.

## 14. Code-Reading Exercises and Answers

**Exercise 1.** Which lists does the following snippet match?

```java
if (candidate instanceof java.util.List<?> list) {
    System.out.println(list.size());
}
```

**Answer:** Any runtime object implementing `List` compatible with the cast, regardless of whether its generic parameter is `String`, `Integer`, or another type; `null` does not match. It does not prove that the elements have a specific type.

**Exercise 2.** Why does `Map<?, ?>` work from `Object` while `Map<String, ?>` does not?

**Answer:** `Map<?, ?>` has **all** type arguments as unbounded wildcards, so it is reifiable. `Map<String, ?>` contains a concrete `String` type argument, which is not reifiable; checking from `Object` would require an unchecked conversion.

**Exercise 3.** Where can `List<? extends Number>` be used?

**Answer:** It can be used in variable declarations, method parameters, or return types to indicate a list that produces `Number`s; it cannot be used as an arbitrary type pattern check from an `Object`. After `List<?> list`, to process `Number`s you must check each element individually.

**Exercise 4.** Given `record Box<T>(T value) {}`, how do the following two patterns differ?

```java
obj instanceof Box<?> box
obj instanceof Box<?>(var content)
```

**Answer:** The first line is a **type pattern** and binds the whole `box` object. The second line is a **record pattern**, deconstructing the component and binding `content`. Both use a wildcard to express an unknown generic type; neither verifies `T` at runtime.

**Exercise 5.** Once `List<?> list` matches, can you call `list.add("x")`?

**Answer:** No. The compiler does not know the actual element type of `list`; writing a `String` could break invariants if the list is a `List<Integer>`. Create an output collection with a concrete type or change the API to pass the proper type.

**Exercise 6.** Code has `switch (obj)` with `case List<?> list ->` before `case List<?> list when list.isEmpty() ->`. Is this valid?

**Answer:** No. The first branch covers empty lists as well, so the second branch is **dominated**. Move the guarded branch before it.

## 15. Review Checklist for Patterns with Wildcards

- [ ] Clearly understood that `?` is a **generic wildcard type argument**, not a pattern that checks individual elements.
- [ ] When the source is `Object`, used a reifiable type such as `List<?>`, `Map<?, ?>`, or `Box<?>` to identify the container.
- [ ] Did not write `List<String>`, `List<? extends Number>`, or `Map<String, ?>` as a check for the entire generic type of an `Object`.
- [ ] If a concrete generic type is used in a pattern, verified that the **source static type** permits a checked cast.
- [ ] After matching `List<?>`, read elements as `Object`, and only used type-specific members after a separate check.
- [ ] If the business logic requires a homogeneous list, checked every element and handled `null`/invalid elements.
- [ ] Did not add non-null elements to `List<?>` or cast to a raw type to bypass checks.
- [ ] With `switch`, checked guard ordering, dominance, exhaustiveness, and `null`.
- [ ] With generic records, distinguished the type pattern `Box<?> box` from the record pattern `Box<?>(var item)`.
- [ ] Did not confuse the standard generics `?` with the Java 21 preview `_`.

## 16. Official References

- [Java Language Specification 21 §4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.7): definition of reifiability; generic types consisting solely of unbounded wildcards are reifiable.
- [Java Language Specification 21 §5.5 — Casting Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.5): checked/unchecked casts, the basis for determining whether a pattern is valid.
- [Java Language Specification 21 §14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): type/record patterns, applicability, and runtime matching.
- [Java Language Specification 21 §15.20.2 — Type Comparison Operator `instanceof`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2): type-testing conditions.
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html): generic record examples and type argument inference.
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): pattern variables and safe cast conversion conditions.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440) and [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): standard syntax in Java 21.
- [JEP 443 — Unnamed Patterns and Variables (Preview)](https://openjdk.org/jeps/443): `_` is a preview feature in Java 21, distinct from the generic wildcard `?`.
