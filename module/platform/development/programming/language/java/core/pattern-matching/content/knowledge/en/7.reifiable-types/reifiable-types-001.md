# Pattern Matching with Generic Types in Java

## 1. Goal: Checking Types When Generics Have Been Partially Erased

Java combines **generics** and **pattern matching** to write concise type checks, but you need to distinguish between two layers of information:

- **Compile time:** the compiler knows `List<String>`, `List<Integer>`, `Map<String, Integer>` and checks operations against the type arguments.
- **Runtime:** due to **type erasure**, the JVM generally knows an object is a class such as `ArrayList` or `HashMap`, rather than storing a list of type arguments to check each `String` or `Integer`.

For example:

```java
List<String> names = new ArrayList<>();
List<Integer> scores = new ArrayList<>();
```

Both variables can point to objects whose runtime class is `java.util.ArrayList`. The difference between `String` and `Integer` still matters greatly for *compile-time* type checking, but a regular `instanceof` test cannot verify that every element in a collection is a `String`.

**Pattern matching with generic types** usually solves two tasks:

1. Checking the actual type of an object, such as `List<?>`, and declaring a **pattern variable** to use the `List` API safely.
2. Leveraging generic information **already established in the static type of the source expression** to check a concrete implementation type, such as `List<String>` to `ArrayList<String>`, in cases Java permits.

These are two different cases. You should neither learn an overly broad rule that "all generics are forbidden in `instanceof`", nor assume that `instanceof` can automatically verify the contents of `List<String>`.

The main examples use **Java 17+**. The `switch` section with type patterns requires **Java 21+**, when pattern matching for `switch` became a standard feature.

## 2. `type erasure`: Why Can't All Generic Arguments Be Checked?

Java generics primarily protect type safety at compile time. According to the Java Language Specification (JLS), *erasure* transforms a parameterized type `G<T>` into the raw/erased representation `G` without type arguments.

For example, suppose you have:

```java
Object input = java.util.List.of("a", "b");
```

You **cannot** write:

```java
// DOES NOT COMPILE when input has static type Object:
if (input instanceof java.util.List<String> strings) {
    System.out.println(strings.get(0));
}
```

A `List` object at runtime does not carry enough evidence for this test to guarantee it is a `List<String>`. If guessing solely from the runtime class were allowed, the program could mistake a `List<Integer>` for a `List<String>`.

The valid way to check:

```java
if (input instanceof java.util.List<?> elements) {
    System.out.println(elements.size());
}
```

`List<?>` carries an **unbounded wildcard** (`?`), meaning the element type is unknown. The pattern variable `elements` has static type `List<?>`; you can call `size()`, `isEmpty()`, iterate over elements, and read each element as `Object`; **you cannot assume they are `String`**.

Complete example of reading an element:

```java
Object input = java.util.List.of("Java", 42);
if (input instanceof java.util.List<?> elements) {
    for (Object element : elements) {
        if (element instanceof String text) {
            System.out.println("text=" + text.toUpperCase());
        } else if (element instanceof Integer number) {
            System.out.println("number=" + number);
        }
    }
}
```

Output:

```text
text=JAVA
number=42
```

`instanceof List<?>` verifies the **type relationship of the list itself**; the subsequent `instanceof String text` or `instanceof Integer number` checks then verify **each individual element**.

## 3. Reifiable Types and Type Patterns

A type is called **reifiable** if the type information needed is fully available to identify it at runtime. According to JLS §4.7, typical examples include:

| Type | Reifiable? | Meaning for pattern matching |
| --- | --- | --- |
| `String`, `Integer` | Yes | Regular class types can be checked at runtime |
| `List<?>` | Yes | Can check that the object is a `List`, element type unknown |
| `Map<?, ?>` | Yes | Can check that the object is a `Map`, key/value types unknown |
| `List` (raw type) | Yes | Can check the class, but loses generic type-checking benefits |
| `List<String>` | No | Cannot verify the `String` type argument solely from the runtime class |
| `List<? extends Number>` | No | Bounded wildcard, not an unbounded `?` wildcard |
| `String[]` | Yes | The element type of this array can be checked at runtime |
| `List<?>[]` | Yes | Array with a reifiable element type |
| `List<String>[]` | No | Non-reifiable generic component |

**Do not conclude that "every type on the right-hand side of `instanceof` must be reifiable."** Since **Java 16**, Java has relaxed this rule for certain parameterized checks when **the static type of the source expression allows a safe type conversion**. Details are in section 5.

On the other hand, `input instanceof List<?> elements` is the direct choice when `input` has a broad static type such as `Object`.

### `List<?>` Is Not Equivalent to `List<Object>`

These two types are different:

```java
java.util.List<String> words = java.util.List.of("A", "B");
java.util.List<?> unknown = words;   // Valid
// java.util.List<Object> objects = words; // ERROR: generics are invariant
```

`List<?>` represents a `List` with an **unknown** element type, and accepts `List<String>`, `List<Integer>`, etc. in read-safe positions. `List<Object>` is a list declared with the exact element type `Object`. Java generics are **invariant**: `List<String>` is not a subtype of `List<Object>`.

In `List<?>`, elements read out have type `Object`. You generally cannot add a non-`null` element because the actual element type is unknown; calling methods that do not depend on the element type, such as `size()`, remains valid.

### When to Use `Map<?, ?>`?

Similarly, when receiving `Object input`:

```java
if (input instanceof java.util.Map<?, ?> entries) {
    for (java.util.Map.Entry<?, ?> entry : entries.entrySet()) {
        Object key = entry.getKey();
        Object value = entry.getValue();
        System.out.println(key + " => " + value);
    }
}
```

The variable `entries` is `Map<?, ?>`; the keys and values do not have a more specific type than `Object` at the read site. If you need `String`- or `Number`-specific operations, use a type pattern for each part's value.

## 4. Pattern Variables and Flow Scoping with Generics

Java 17 syntax:

```java
if (input instanceof java.util.List<?> items) {
    System.out.println(items.size());
}
```

`items` is a **pattern variable**. It is only available where the compiler proves `List<?>` has *definitely matched*.

Short example:

```java
static int sizeOrMinusOne(Object input) {
    if (!(input instanceof java.util.List<?> items)) {
        return -1;
    }
    return items.size(); // Valid because the non-matching branch returns.
}
```

Inside the negated `if` body, `items` is not initialized; after the `if`, it has matched on all remaining execution paths. You can write an additional condition with `&&`:

```java
if (input instanceof java.util.List<?> items && !items.isEmpty()) {
    Object first = items.get(0);
    System.out.println(first);
}
```

`items.get(0)` is only called after the pattern matches and `items` is non-empty. Conversely, the following code is a **compile-time error** because `||` can evaluate the right-hand side when the pattern does not match:

```java
// DOES NOT COMPILE:
if (input instanceof java.util.List<?> items || items.isEmpty()) {
    System.out.println("...");
}
```

Flow scoping for generic-typed pattern variables follows the **same rules** as `String text`: Java checks whether the pattern has matched and the variable is definitely assigned, without requiring the variable to have a non-generic type.

## 5. Important Exception Since Java 16: Refinement of Statically Known Generics

Some types with **concrete** generic arguments can still be used in an `instanceof` test or type pattern, if the static type of the source expression proves the conversion is safe according to the JLS.

Example:

```java
java.util.List<String> words = new java.util.ArrayList<>();
if (words instanceof java.util.ArrayList<String> arrayList) {
    arrayList.add("hello");
    System.out.println(arrayList.size()); // 1
}
```

This is **valid syntax since Java 16**, even though `ArrayList<String>` is not a reifiable type. Key points:

- The source variable `words` **is already declared as `List<String>`**, so the compiler has static evidence that the list's elements have type `String` according to the generic contract.
- The runtime check only needs to verify whether the object belongs to the `ArrayList` implementation class. The `<String>` part is preserved through a **valid type conversion** from `List<String>` to `ArrayList<String>`; there is no "reading" of the generic type argument from the JVM.
- The pattern variable `arrayList` has type `ArrayList<String>`, so after matching you can call `add("hello")` or `get(0)` under normal Java type checking.

Two **invalid** examples:

```java
java.util.List<String> words = new java.util.ArrayList<>();

// No valid conversion to ArrayList<Integer>:
// if (words instanceof java.util.ArrayList<Integer> nums) { }

// Cannot convert from Object to ArrayList<String> with full type checking:
// Object unknown = words;
// if (unknown instanceof java.util.ArrayList<String> strings) { }
```

Thus, the true condition **is not** "that `<String>` metadata exists at runtime." The true condition is **that Java can check the runtime class combined with statically known generic evidence, without needing an unchecked cast**.

Note: if data suffers from **heap pollution** due to raw types, unchecked casts, or legacy libraries, the static generic evidence may reflect a false promise from upstream. Pattern matching cannot fix that problem on its own.

## 6. Complete Java 17+ Example

Save as **`GenericPatternDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class GenericPatternDemo {
    static String summary(Object value) {
        if (value instanceof List<?> list) {
            int nonblankStrings = 0;
            for (Object item : list) {
                if (item instanceof String text && !text.isBlank()) {
                    nonblankStrings++;
                }
            }
            return "List(size=" + list.size()
                    + ", nonblankStrings=" + nonblankStrings + ")";
        }
        if (value instanceof Map<?, ?> map) {
            return "Map(size=" + map.size() + ")";
        }
        return value == null ? "null" : "other";
    }

    static String refinedType(List<String> words) {
        if (words instanceof ArrayList<String> concrete) {
            return "ArrayList first="
                    + (concrete.isEmpty() ? "(empty)" : concrete.get(0));
        }
        return "Other List";
    }

    public static void main(String[] args) {
        Object mixed = List.of("Java", 7, " ", "hello");
        System.out.println(summary(mixed));
        System.out.println(summary(Map.of("id", 2)));
        System.out.println(summary(null));

        List<String> words = new ArrayList<>(List.of("A", "B"));
        System.out.println(refinedType(words));
        System.out.println(summary(99));
    }
}
```

Compile and run with **JDK 17 or later**, without preview:

```bash
javac GenericPatternDemo.java
java GenericPatternDemo
```

Exact expected output:

```text
List(size=4, nonblankStrings=2)
Map(size=1)
null
ArrayList first=A
other
```

**Why does it produce this output?**

1. `mixed` is a `List` containing the string `"Java"`, the number `7`, the whitespace-only string `" "`, and the string `"hello"`. `List<?> list` matches; the loop counts **two** non-blank strings (`"Java"` and `"hello"`), out of four elements total.
2. `Map.of("id", 2)` matches `Map<?, ?> map`, has one entry, so it prints `Map(size=1)`.
3. `null` does not match any reference type pattern, so it reaches `return "null"`.
4. `words` has static type `List<String>` and runtime object `ArrayList`; the pattern `ArrayList<String> concrete` is valid thanks to the known static type. `get(0)` returns `"A"`.
5. `99` is an `Integer`, matching neither `List<?>` nor `Map<?, ?>`, so it prints `other`.

Note that `List.of(...)` creates a list that does not support adding/removing, though the example does not modify `mixed`. In contrast, `words` is created with `new ArrayList<>(...)`, so only the refined branch uses `ArrayList`-specific APIs when needed.

## 7. Pattern Matching for Generics in `switch` (Java 21+)

Since **Java 21**, you can use type patterns with `switch`:

```java
case List<?> items -> ...
```

A `case List<?> items` matches objects whose runtime type implements `List`; `items` is a pattern variable usable in the body of **that specific case**, and in its `when` guard if present. The erasure and reifiability rules explained earlier still apply.

Standalone example, save as **`GenericSwitchDemo.java`**:

```java
import java.util.List;
import java.util.Map;

public class GenericSwitchDemo {
    static String classify(Object value) {
        return switch (value) {
            case null -> "null";
            case List<?> items when items.isEmpty() -> "empty list";
            case List<?> items -> "list of " + items.size();
            case Map<?, ?> entries -> "map of " + entries.size();
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(List.of()));
        System.out.println(classify(List.of(1, "two")));
        System.out.println(classify(Map.of("a", 10)));
        System.out.println(classify(null));
        System.out.println(classify("text"));
    }
}
```

Run with **JDK 21 or later**:

```bash
javac GenericSwitchDemo.java
java GenericSwitchDemo
```

Output:

```text
empty list
list of 2
map of 1
null
other
```

Explanation:

- The guard `when items.isEmpty()` is only evaluated **after** `List<?> items` matches, so calling `items.isEmpty()` is allowed.
- The unguarded rule `case List<?> items` handles the remaining `List` instances. Place the guarded rule first so it is not *dominated* by the broader rule.
- Both labels declare `items` independently; each pattern variable belongs only to its own branch and is not "borrowed" from the previous branch.
- `case Map<?, ?> entries` works similarly for `Map`.
- `case null` handles `null` explicitly; do not assume `default` catches `null`.

Do not use this `switch` code as a default runnable example on Java 17: pattern matching for `switch` was not yet a standard feature then. Use `if (value instanceof List<?> items)` if your project targets JDK 17 as its baseline.

### Can You Write `case List<String> strings`?

If the selector is `Object` as in the example, you **cannot** use `case List<String> strings` to assert that every element is a `String`. The runtime type of `List` does not retain that full generic argument. Use `List<?>`, then check individual elements when needed.

## 8. Generic Records and Nested Patterns: Recognizing the Right Boundary

Java 21 also supports **record patterns**. For a generic record:

```java
record Box<T>(T item) {}
```

If the input has type `Object`, you can use:

```java
Object value = new Box<>("Java");
if (value instanceof Box<?> box) {
    Object item = box.item(); // Not yet inferred as String.
    if (item instanceof String text) {
        System.out.println(text.toUpperCase()); // JAVA
    }
}
```

`Box<?>` verifies the object is a `Box` without knowing the type argument `T`. You still have to check `item` separately if you want to use the `String` API.

A **nested record pattern** can combine checking the record and its component, but that is a **structural** match on the component; it does not mean the JVM stores `T=String` as metadata that can always be verified. Avoid interpreting component matching as an unconditional validation of the entire generic container.

`record Box<T>(T item) {}` works starting in Java 17; nested record patterns are specific to Java 21+. The goal here is to understand the generic boundary: checking the **container** and checking the **inner value** are two independent tasks.

## 9. Raw Types, Unchecked Casts, and Runtime Errors

The example below **illustrates unsafe code** and should not be used in new code:

```java
java.util.List raw = new java.util.ArrayList();
raw.add(123); // Raw type bypasses generic checking on add.

java.util.List<String> texts = raw; // Unchecked warning.
String first = texts.get(0);        // ClassCastException at runtime.
```

`texts` is declared as `List<String>`, but the actual data inside is an `Integer`. Due to the raw type / unchecked conversion, the compile-time type promise has been broken. An `instanceof List<?>` check or a valid refinement to `ArrayList<String>` **does not scan and re-validate the contents** of the list.

Safer approaches:

- Accept `Object`/`List<?>` at data boundaries; check each element with `instanceof String s` before using it.
- Copy validated data into a new `List<String>`, adding only elements verified to have the right type.
- Prefer fully generic-declared APIs; avoid raw types and unchecked casts except for controlled legacy integration.
- If you need to validate multi-level structures, such as `List<Map<String, Integer>>`, you must check each level and each element; a single `instanceof` cannot validate the entire structure.

## 10. Generic Type Parameters and `Class<T>`: Two Different Tools

In a generic method:

```java
static <T> boolean isExpected(Object value, Class<T> type) {
    return type.isInstance(value);
}
```

`Class<T>.isInstance(value)` uses a **class token** (`String.class`, `Integer.class`, `Number.class`) to check a class at runtime; `Class<T>.cast(value)` can perform a checked cast using the class token. For example:

```java
boolean ok = isExpected("Java", String.class); // true
boolean no = isExpected(42, String.class);     // false
```

However, `Class<List<String>>` has no class literal `List<String>.class`: generic arguments are not represented as an equivalent class token. Only `List.class` exists for the erased class/interface. Therefore, `Class<T>` is useful for checking the **runtime class**, but by itself it also cannot verify the types of all nested generic elements.

In the same vein, you cannot expect to write `value instanceof T` with a method type parameter `T` and check `T` at runtime like `String.class`; the type `T` is normally erased to its bound. When dynamic type checking is needed, pass `Class<T>` for an appropriate reifiable type or a dedicated structural validator.

## 11. Common Mistakes to Avoid

1. **Assuming `instanceof List<?> list` proves `List<String>`.** It only verifies the object is a `List`; each element can still be a different type.
2. **Writing `Object x; if (x instanceof List<String> s)`.** Checking from `Object` to a concrete generic type lacks sufficient guarantee and is rejected by the compiler.
3. **Claiming all generic types are forbidden.** Java 16+ accepts certain refinements from a statically known type, such as `List<String>` to `ArrayList<String>` when the conversion is valid.
4. **Confusing `List<?>` with `List<Object>`.** Generics are invariant; `List<String>` does not automatically convert to `List<Object>`.
5. **Calling `String`-specific methods on an element taken from `List<?>` without checking.** The element has static type `Object`; use `instanceof String text` when needed.
6. **Thinking `? extends Number` is reifiable.** `List<? extends Number>` is not the same as `List<?>`; from `Object`, you cannot use it to verify a generic type in the same simple way.
7. **Using raw types to "bypass" checks.** `List raw` removes type safety and easily causes heap pollution and delayed `ClassCastException`.
8. **Using a pattern variable out of scope.** After a regular `if` or in a non-matching branch, the pattern variable may not exist; use `&&` or a properly structured guard clause.
9. **Using `case List<?>` on JDK 17 without preview enabled.** Switch type patterns became standard in Java 21; for Java 17, use `instanceof`.
10. **Equating a class token with a type token for nested generics.** `List.class` only checks the `List` class, not `List<String>`.

## 12. Practice Exercises

1. Write `static int countStrings(Object x)` using `instanceof List<?> list` to return the number of `String` elements; for `List.of("a", 10, "b")` return 2, and for `"not a list"` return 0.
2. With `Object x = List.of("a")`, try compiling `if (x instanceof List<String> names)`. Explain why the compiler rejects it; fix it using `List<?>`.
3. With `List<String> names = new ArrayList<>();`, try `if (names instanceof ArrayList<String> concrete)`. Explain why the compiler allows this case even though `ArrayList<String>` is not reifiable.
4. Use `Map<?, ?>` to check an `Object` and count the number of entries whose key is `String` and value is `Integer`. Check key/value separately in the loop.
5. Write a Java 21 `switch` program with `case List<?> list when list.isEmpty()`, `case List<?> list`, `case Map<?, ?> map`, and `default`; try swapping the order of the two `List` branches to observe the dominance error.
6. Receive data with the structure `List<List<?>>`; explain why a single container check is not enough, then iterate and verify each level. Do not use unchecked casts to achieve the result.
7. Create a `Class<T>` validator for `String.class`, then explain why you cannot obtain `List<String>.class` in the same way.

**Key takeaway:** Pattern matching with generic types must be based on **what Java can actually verify at runtime** and **the static type evidence the compiler already has**. `List<?>` is safe for checking the container; `instanceof String s` checks elements; some types like `ArrayList<String>` can still be used in refinements from `List<String>` under Java 16+ conversion rules. Do not use type erasure as an excuse to skip element checks when input is untrusted.

## References

- [JLS 17, §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6).
- [JLS 17, §4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7).
- [JLS 17, §15.20.2 — `instanceof` Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2).
- [Oracle Java 17 — Pattern Matching for `instanceof`](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html).
- [OpenJDK JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394).
- [Oracle Java 21 — Pattern Matching for `switch`](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [OpenJDK JEP 441 — Pattern Matching for `switch`](https://openjdk.org/jeps/441).
