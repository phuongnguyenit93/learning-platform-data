# Distinguishing overall type checking from verifying every element's type in Java Generics

When receiving an `Object` value from an API, JSON, reflection, legacy code, or an external library, we often want to know: "Is this a list containing only `String`?". That question actually consists of **two distinct checking requirements**:

1. **Checking the outer object's type**: is the value an object implementing `List`?
2. **Verifying every element**: does each element in the list actually satisfy the condition "is `String`"?

In Java, the first check can be written as `value instanceof List<?>`. The second check requires **iterating through the elements and checking each value**, for example using `instanceof String` or `String.class.isInstance(element)`.

```java
// Illustrative snippet inside a method; import java.util.List.
Object value = List.of("Java", 42);

boolean isList = value instanceof List<?>; // true
// Cannot infer that all elements are String.
```

The object above is a valid `List`, yet it contains an `Integer` at the second position. Therefore, `isList == true` **does not prove** that the list is a `List<String>` in the sense that all current data are `String`.

This is the core difference between **checking the outer shape/type** and **verifying data contents**.

## 1. Two levels of checks answer two different questions

Suppose:

```java
Object input = java.util.List.of("An", 123);
```

Overall check:

```java
if (input instanceof java.util.List<?> values) {
    System.out.println("Đây là danh sách với " + values.size() + " phần tử");
}
```

The compiler can bind `input` to pattern variable `values` of type `List<?>` when the check succeeds. However, type `List<?>` only states there is an **unknown element type**; it does not restrict that type to `String`.

Per-element check:

```java
// Snippet continuing in the branch where values is known to be List<?>.
boolean allStrings = true;

for (Object element : values) {
    if (!(element instanceof String)) {
        allStrings = false;
        break;
    }
}
```

With `["An", 123]`, the result is `false`. With `["An", "Binh"]`, the result is `true`. Both snippets compile under Java 17+ syntax when placed inside a valid method, yet overall checking and per-element checking have different scopes.

| Actual value | `instanceof List<?>` | Every element is `String`? |
| --- | --- | --- |
| `List.of("An", "Binh")` | `true` | `true` |
| `List.of("An", 42)` | `true` | `false` |
| `List.of(1, 2)` | `true` | `false` |
| `List.of()` | `true` | `true` under the "every element" condition, because an empty list has no counterexample element |
| `"An"` | `false` | Not a list, so the combined check must reject |
| `null` | `false` | Not a list, so the combined check must reject |

**Note on empty lists:** `allStrings(emptyList)` normally returns `true` under the logical rule "every element satisfies"; that **provides no evidence that any `String` element exists**. If business rules require a non-empty list, add the condition `!list.isEmpty()`.

## 2. Why cannot `instanceof List<String>` replace per-element checking?

Standard Java Generics uses **type erasure**. The parameterized type `List<String>` is checked in source code, yet the runtime class of an `ArrayList<String>` remains `ArrayList`, identical to an `ArrayList<Integer>` object created from the same class.

```java
// Illustrative snippet:
java.util.List<String> text = new java.util.ArrayList<>();
java.util.List<Integer> numbers = new java.util.ArrayList<>();

boolean sameClass = text.getClass() == numbers.getClass(); // true
```

The `String` or `Integer` type argument information does not cause Java to generate a separate runtime class for each parameterization. For a value whose static type is merely `Object`, the following statement **is invalid**:

```java
Object value = java.util.List.of("An");
// boolean result = value instanceof java.util.List<String>; // Compile-time error
```

Meanwhile:

```java
Object value = java.util.List.of("An");
boolean result = value instanceof java.util.List<?>; // Valid, true
```

`List<?>` is a **reifiable type**: the runtime check does not require verifying a concrete type argument. It only needs to check that the object implements `List`. By contrast, `List<String>` is not a reifiable parameterized type for checking element type `String` directly in this way.

Certain `instanceof` cases where the expression already has a very specific static type are handled by modern Java versions under type-compatibility rules; however, that **does not** create a general runtime mechanism to confirm that every element of an `Object` is `String`. When receiving unknown data, use `List<?>` and then verify the contents.

## 3. Data must pass through two checking steps

A properly targeted validation function can be written as:

```java
// Method snippet that can be placed inside a Java class.
static boolean isListOfStrings(Object input) {
    if (!(input instanceof java.util.List<?> items)) {
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

**Step 1:** if `input` is not a `List`, return `false`. Thanks to pattern matching in `instanceof`, once past the `if` condition, the variable `items` already has a valid `List<?>` type.

**Step 2:** the `for` loop reads each value as `Object` and asks `item instanceof String`. Any wrongly typed value makes the result `false`.

**Step 3:** if the loop finishes without finding a counterexample, return `true`. For an empty list, the loop does not run and the function returns `true`, consistent with the "every element satisfies the condition" reading.

This method returns a **verification result at the moment of traversal**. It does not change the generic type declared on old references, and it does not protect a list that might be modified right after the check.

### Can Streams be used?

Yes:

```java
static boolean isListOfStrings(Object input) {
    return input instanceof java.util.List<?> items
            && items.stream().allMatch(String.class::isInstance);
}
```

`allMatch` returns `true` when **every** element satisfies the predicate; for an empty stream, the result is also `true`. The syntax is shorter, yet it still checks each element until it can determine the result.

Behaviorally, `allMatch` is a **short-circuiting terminal operation**: it can stop immediately upon encountering a non-matching element. Do not treat using a stream as a type-argument check built into the JVM; it still has to inspect the data.

## 4. Checking every element does not mean the list has become `List<String>`

Consider:

```java
Object input = java.util.List.of("An", "Binh");

if (input instanceof java.util.List<?> items) {
    boolean verified = items.stream().allMatch(String.class::isInstance);

    // Even though verified is true, the static type of items is still List<?>.
    // java.util.List<String> result = items; // Does not compile
}
```

The boolean result is an assertion about **the elements just inspected**, yet the Java compiler has no mechanism to automatically promote static type `List<?>` to `List<String>` simply because a loop check returned `true`. Java is not a type system capable of automatically inferring the condition "every element in the collection is String" into a change of the variable's type argument.

There are three directions depending on the goal:

1. Only a true/false conclusion is needed: keep the boolean result and continue working through `List<?>`.
2. A `List<String>` with trustworthy data is needed: **check each element and copy into a new list with the proper type**.
3. Copying must be avoided for performance: only use a controlled cast when there is a sufficiently strong data contract and complete control over all ways the list could be mutated; this is a strictly guarded safety situation, not the default.

Do not write `(List<String>) items` and assume the cast automatically scans every element. Java has no full runtime check for the `String` type argument of `List<String>`.

## 5. Check and then copy into a reliably typed list

When handling external data, the clean approach is **creating a validated copy**. With `Class<T>` from the caller, you can write a generic adapter:

```java
// Method snippet; requires java.util.List and java.util.ArrayList.
static <T> java.util.List<T> validatedCopy(Object value, Class<T> expected) {
    if (!(value instanceof java.util.List<?> items)) {
        throw new IllegalArgumentException("Not a list");
    }

    java.util.List<T> result = new java.util.ArrayList<>();
    for (int i = 0; i < items.size(); i++) {
        Object item = items.get(i);
        if (!expected.isInstance(item)) {
            throw new IllegalArgumentException("Invalid element at " + i);
        }
        result.add(expected.cast(item));
    }

    return java.util.List.copyOf(result);
}
```

Call:

```java
// Snippet inside a method:
java.util.List<String> names =
        validatedCopy(java.util.List.of("An", "Binh"), String.class);
```

Mechanism:

- `value instanceof List<?> items` confirms the outer structure.
- `expected.isInstance(item)` checks the runtime class of **each** element. With `String.class`, only `String` instances are accepted; `null` is rejected because `Class.isInstance(null)` is `false`.
- `expected.cast(item)` performs a checked cast; the compiler knows the result has type `T`, thanks to the `Class<T>` token.
- `List.copyOf(result)` produces an unmodifiable result containing no `null`. It is a **shallow copy**: if elements are mutable objects, their internal state can still change; `String` itself is immutable.

Because the new result list does not share a mutable element container with the source, structural modification of the source list **after copying completes** cannot insert a wrongly typed element into the result list.

However, **checking every element does not automatically prevent races** when another thread modifies the list *during traversal*. For concurrently mutable collections, you need synchronization, a consistent snapshot under the source's contract, or appropriate ownership before iterating. An ordinary read loop does not promise to provide an atomic snapshot.

## 6. Complete runnable Java 17+ program

Save the entire program below in **`OverallVsElementsDemo.java`**:

```java
public class OverallVsElementsDemo {
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

    static <T> java.util.List<T> validatedCopy(
            Object value, Class<T> expected) {
        if (!(value instanceof java.util.List<?> items)) {
            throw new IllegalArgumentException("Not a list");
        }

        java.util.List<T> result = new java.util.ArrayList<>();
        for (int i = 0; i < items.size(); i++) {
            Object item = items.get(i);
            if (!expected.isInstance(item)) {
                throw new IllegalArgumentException(
                        "Invalid element at " + i);
            }
            result.add(expected.cast(item));
        }

        return java.util.List.copyOf(result);
    }

    static boolean nestedStrings(Object value) {
        if (!(value instanceof java.util.List<?> rows)) {
            return false;
        }
        for (Object row : rows) {
            if (!(row instanceof java.util.List<?> cells)) {
                return false;
            }
            for (Object cell : cells) {
                if (!(cell instanceof String)) {
                    return false;
                }
            }
        }
        return true;
    }

    public static void main(String[] args) {
        Object mixed = java.util.List.of("Java", 42);
        Object valid = java.util.List.of("An", "Binh");
        Object empty = java.util.List.of();

        System.out.println("Mixed instanceof List<?>: "
                + (mixed instanceof java.util.List<?>));
        System.out.println("Mixed all Strings: " + allStrings(mixed));
        System.out.println("Valid all Strings: " + allStrings(valid));
        System.out.println("Empty all Strings: " + allStrings(empty));

        try {
            validatedCopy(mixed, String.class);
        } catch (IllegalArgumentException exception) {
            System.out.println("Mixed copy rejected: "
                    + exception.getMessage());
        }

        java.util.List<String> copy = validatedCopy(valid, String.class);
        System.out.println("Validated copy: " + copy);
        System.out.println("Copy shares list object: " + (copy == valid));

        Object goodNested = java.util.List.of(
                java.util.List.of("A"), java.util.List.of("B"));
        Object badNested = java.util.List.of(
                java.util.List.of("A"), java.util.List.of(7));

        System.out.println("Nested valid: " + nestedStrings(goodNested));
        System.out.println("Nested invalid: " + nestedStrings(badNested));

        Object array = new String[] { "x" };
        System.out.println("String[] runtime check: "
                + (array instanceof String[]));
    }
}
```

Run with JDK 17 or higher:

```bash
javac -encoding UTF-8 OverallVsElementsDemo.java
java OverallVsElementsDemo
```

Standard output:

```text
Mixed instanceof List<?>: true
Mixed all Strings: false
Valid all Strings: true
Empty all Strings: true
Mixed copy rejected: Invalid element at 1
Validated copy: [An, Binh]
Copy shares list object: false
Nested valid: true
Nested invalid: false
String[] runtime check: true
```

The results illustrate key points:

- `mixed instanceof List<?>` is `true` even though `mixed` contains an `Integer`.
- `allStrings(mixed)` returns `false` after encountering `42`, whereas `allStrings(valid)` is `true`.
- An empty list yields `true` for the "every element is String" condition. If non-emptiness is needed, check it separately.
- `validatedCopy(mixed, String.class)` rejects the element at index 1 and clearly reports the position.
- The validated copy is not the same object as the source list.
- Two layers of data `List<List<String>>` require two checking tiers: the outer list contains sublists, and each sublist contains strictly `String`.
- `String[]` has a runtime-recognizable component type; that is a different mechanism from checking generic elements of `List<String>`.

## 7. Empty lists, null elements, and quantified checks

### 7.1. "Every element satisfies" differs from "at least one element satisfies"

With `List.of()`, `allMatch(String.class::isInstance)` evaluates to `true`; this is the **vacuous truth** of the universal quantifier "every element."

If the business requirement is that **the list must contain at least one string**, write:

```java
static boolean nonEmptyStringList(Object input) {
    return input instanceof java.util.List<?> list
            && !list.isEmpty()
            && list.stream().allMatch(String.class::isInstance);
}
```

Do not use `anyMatch` in place of `allMatch` when the contract requires **every** element to match. `anyMatch` only requires **at least one** element to be a `String`.

For example, with `["An", 42]`: `anyMatch(String.class::isInstance)` is `true` whereas `allMatch(String.class::isInstance)` is `false`.

### 7.2. Is `null` accepted?

The expression `null instanceof String` is `false`, and `String.class.isInstance(null)` is also `false`. Therefore, both `allStrings` and `validatedCopy` above have a **strict contract rejecting null**.

This must be stated explicitly because a `List<String>` variable in Java source code **can contain null** if the collection permits it: the `String` type argument itself does not mean "non-null String." If business rules permit `null`, express the predicate clearly:

```java
static boolean stringsOrNull(Object input) {
    return input instanceof java.util.List<?> list
            && list.stream().allMatch(
                    element -> element == null || element instanceof String);
}
```

Do not use `List.copyOf` directly for lists that may contain null: that API **does not accept null elements**. When null is permitted, you can copy into an `ArrayList<String>` after checking, then apply an appropriate unmodifiable wrapper strategy if needed.

### 7.3. Checking every element is only one form of validation

A list containing only `String` can still be invalid per business rules: empty strings, excessive length, malformed format, or duplicate values. The "type validation" problem only confirms the **element kind**; business validation may require additional predicates:

```java
// Illustrative snippet:
boolean valid = input instanceof java.util.List<?> list
        && !list.isEmpty()
        && list.stream().allMatch(
                item -> item instanceof String s
                        && !s.isBlank()
                        && s.length() <= 50);
```

These requirements must come from a specific data contract, not be applied automatically when merely asked "is this a list of String?".

## 8. Nested data: must check every layer

Suppose you want to validate data whose structure approximates `List<List<String>>`:

```java
Object rows = java.util.List.of(
        java.util.List.of("A", "B"),
        java.util.List.of("C"));
```

Checking `rows instanceof List<?>` only states that **the outer container** is a list. It does not prove:

1. Each outer element is another list.
2. Each element of the inner lists is `String`.

Therefore, you must check layer by layer:

```java
static boolean nestedStrings(Object value) {
    if (!(value instanceof java.util.List<?> rows)) {
        return false;
    }
    for (Object row : rows) {
        if (!(row instanceof java.util.List<?> cells)) {
            return false;
        }
        for (Object cell : cells) {
            if (!(cell instanceof String)) {
                return false;
            }
        }
    }
    return true;
}
```

Every erased generic layer must be verified against the actual structure when input is untrusted. For deeply nested data, you can design a recursive validator or a schema-driven parser; yet verifying both **the structure and every leaf** remains the responsibility of the validation mechanism.

The same idea applies to `Map<String, Integer>`: `value instanceof Map<?, ?>` only checks that it is a `Map`. To confirm `String` keys and `Integer` values, iterate over `entrySet()` and check **both key and value**.

## 9. Checking classes with `Class<T>`: useful yet limited

`Class<T>` provides the token of a concrete runtime class:

```java
static <T> boolean everyElementIs(
        Object input, Class<T> expected) {
    return input instanceof java.util.List<?> list
            && list.stream().allMatch(expected::isInstance);
}
```

For example, `everyElementIs(List.of(1, 2), Number.class)` is `true`, because `Integer` is a subtype of `Number`. `Class.isInstance` checks **assignment compatibility** by runtime class, without requiring `element.getClass() == Number.class`.

If business rules demand an exact concrete class and **disallow subclasses**, a different rule is needed, such as `element != null && element.getClass() == expected`. That is a design choice usually unnecessary in typical object-oriented APIs.

However, a single `Class<T>` token **does not fully describe nested parameterized types**. There is no Java class literal like `List<String>.class` to verify all elements. `List.class` only helps confirm the outer class/interface; the `String.class` token helps check one element at a time.

To verify `List<List<String>>`, you need structural information for "list of list of string" and corresponding checking steps; you cannot simply pass `List.class` once.

## 10. How does overall array checking differ from generic collections?

Java arrays carry a **runtime component type**, whereas ordinary generic collections do not store concrete type arguments as part of each instance's runtime class.

```java
Object value = new String[] { "A", "B" };

System.out.println(value instanceof String[]); // true
```

For a `String[]` array, the JVM can confirm the object is an array holding `String` elements according to its runtime component type. If an `Object[]` reference points to an actual `String[]` array, attempting to write an `Integer` triggers `ArrayStoreException`:

```java
Object[] array = new String[1];

try {
    array[0] = 42;
} catch (ArrayStoreException exception) {
    System.out.println("Rejected by runtime array type");
}
```

Arrays check their component type upon writes. Meanwhile, if raw code or an unchecked operation inserts an `Integer` into a `List<String>` object, a generic collection does not have element-type checking enforced by the runtime container the way arrays do. The error may surface upon casting while reading data out as `String`.

You should also understand that `String[]` is an array with a reifiable component type, while `List<String>` is **not a reifiable type**. Java permits `new List<?>[3]` because `List<?>` is reifiable, yet forbids directly creating `new List<String>[3]`.

Even so, checking `instanceof String[]` only asserts the runtime array component type. It does not automatically evaluate business conditions such as length, empty strings, formatting rules, or `null` policies.

## 11. Why does an unchecked cast not prove every element's type?

Consider this intentionally unsafe snippet:

```java
// Snippet illustrating an unchecked warning, not a pattern to use.
Object value = java.util.List.of("Java", 42);

@SuppressWarnings("unchecked")
java.util.List<String> casted = (java.util.List<String>) value;

// String second = casted.get(1); // May throw ClassCastException
```

The cast `(List<String>) value` does not check that every element is `String`. When the runtime can only confirm the raw `List` part, trusting the `String` type argument is **unchecked**. `@SuppressWarnings("unchecked")` merely hides the warning; it does not give the cast the ability to check generic contents.

If you attempt to read `casted.get(1)` as `String`, the compiler may insert `checkcast String`, and the element `42` causes `ClassCastException` to be thrown.

**Rule:** to verify all elements, you must have evidence from a trustworthy data structure or inspect them yourself; an unchecked cast does not create such evidence.

Similarly, raw types can cause **heap pollution**:

```java
// Snippet illustrating polluted data.
java.util.List<String> names = new java.util.ArrayList<>();
java.util.List raw = names;
raw.add(42); // Unchecked warning, yet an Integer can be written into List<String>
```

This shows that checking an outer `List` is valid is completely insufficient to guarantee that the objects inside match a desired type argument.

## 12. Checking once is not enough if the data can mutate

Suppose one thread confirms every element is `String`, yet another thread subsequently modifies the list through a raw reference. The check was true **at a single point in time**, yet the current list may no longer be valid.

Even with a single thread, another API holding an alias to the `ArrayList` could append an element after the validation function returns.

If a stable result is required:

1. **Know data ownership clearly**: who can modify the collection?
2. **Check under consistent timing/conditions**: do not iterate over a list undergoing uncontrolled mutation and assume it is an atomic snapshot.
3. **Copy validated elements** into a new collection of the corresponding type, instead of casting the original reference.
4. **Prevent structural mutation of the copy** if the result must uphold a long-lived contract: use `List.copyOf` when elements are non-null, or an unmodifiable view over an appropriate copy.

`List.copyOf` is a **shallow** copy and does not make the objects inside immutable. With `String`, elements are already immutable so the result is straightforward; with `List<Person>`, a `Person` could still mutate its internal state. Class-type validation does not equal full validation of object state.

Some APIs like `Collections.checkedList(list, String.class)` create a wrapper that checks the type of **additions performed through that wrapper**, yet it does not automatically validate all data already in the list nor prevent another alias from writing directly to the underlying list. That is a forward-looking safeguard, distinct from iterating to verify all existing elements.

## 13. Reflection and generic metadata do not verify contents

Reflection can read information about a field **declared** as `List<String>`:

```java
class Sample {
    java.util.List<String> names;
}
```

`Sample.class.getDeclaredField("names").getGenericType()` can return the `List<String>` representation from `Signature` metadata, while `getType()` normally returns the raw runtime interface `List`.

However, that information describes **the field's declared type**, not proof that the collection attached to the field at runtime contains only `String`. Raw types, unchecked conversions, reflection, or untrusted data sources can still violate the generic invariant that the compiler protected in ordinary source code.

Therefore, reflection helps clarify **the intended type contract**, yet when receiving data across an untrusted boundary, validating elements still depends on the actual data and the chosen checking strategy.

## 14. API design: where should type checks happen?

If an API accepts a `List<String>` from **safely compiled Java source code**, the compiler has already checked most type-argument relationships at the call site. There is no need to scan every element in every method just to repeat the compiler's work, unless the API has additional requirements (such as disallowing null, enforcing formats, or defending against polluted data).

If an API accepts `Object`, raw `List`, dynamically mapped JSON data, or input that may have passed through unchecked operations, make the strategy explicit:

| Case | Appropriate check | Meaning |
| --- | --- | --- |
| Only need to know if it is a list | `instanceof List<?>` | Checks the outer interface |
| Need every element to be `String` | Outer check, then `allMatch(String.class::isInstance)` | Validates data at traversal time |
| Need at least one element and all `String` | Add `!list.isEmpty()` | Prevents empty lists from passing validation |
| Allow null elements | Check `item == null` **or** `item instanceof String` | States null policy explicitly |
| Need to return a stable `List<String>` | Verify, cast each element, then copy | Produces a new collection with the right static type |
| Need `List<List<String>>` | Check each tier and leaf elements | Validates nested structure |
| Need business validation | Add content/format/range conditions | Right element kind can still violate business rules |

If data has already passed through a trusted parser/schema validator with an explicit contract, verification can be placed at the **data ingestion boundary**, and internal flows can maintain invariants via the type system and ownership. Heavy checks do not necessarily have to be repeated across every application layer.

## 15. Common mistakes

**Mistake 1: "`instanceof List<?>` returning `true` means `List<String>`."** No. It only confirms the object implements `List`, without checking type arguments.

**Mistake 2: "Checking only the first element is `String` is enough."** No. A list can start with `String` and contain `Integer` later, so checks must cover all required elements.

**Mistake 3: "`anyMatch` and `allMatch` are the same."** No. `anyMatch` checks whether at least one element matches; `allMatch` requires all elements to match.

**Mistake 4: "An empty list must be treated as not `List<String>`."** That is a contract decision. The proposition "every element is String" holds on the empty set; if data is required, add `!isEmpty()`.

**Mistake 5: "Generic `List<String>` forbids null by default."** No. Java's `String` type argument does not forbid null on its own. An explicit rule must be added if null is disallowed.

**Mistake 6: "Casting `(List<String>)` has checked every element."** No. Due to type erasure, type arguments are not verified as part of an ordinary cast.

**Mistake 7: "Reflection seeing `List<String>` means the data definitely contains only `String`."** No. Reflection can inspect declaration metadata, not validate runtime contents.

**Mistake 8: "Once checked, the collection is safe forever."** Not if the collection or inner objects remain mutable, aliased, or exposed to unsafe operations. Mutation control or snapshotting is required.

**Mistake 9: "`Class<T>` can represent any nested generic type."** No. `Class<String>` checks `String`; types like `List<List<String>>` require structural descriptions and multi-tier validation.

## 16. Self-check exercises

**Question 1.** Is `Object x = List.of("A", 7); x instanceof List<?>;` `true` or `false`?

`true`: the outer wrapper is a list. The result does not depend on what element types the list contains.

**Question 2.** With `List.of("A", 7)`, what does `allMatch(String.class::isInstance)` return?

`false`, because `7` is an `Integer`, not a `String`.

**Question 3.** Why is `List.of().stream().allMatch(String.class::isInstance)` `true`?

Because there is no counterexample element; this is the definition of checking "every element" over an empty set.

**Question 4.** Does `List<String>` allow `null`?

The type `List<String>` itself does not forbid `null`. Whether null can be inserted depends on the collection implementation and contract; `List.of` and `List.copyOf` do not allow null elements.

**Question 5.** Once you have verified that a `List<?>` contains only `String`, can you assign it directly to `List<String>`?

No. Its static type is still `List<?>`; a safely proven conversion mechanism such as checking every element and copying is required.

**Question 6.** Is `Object x = List.of(List.of("A"), List.of(9)); x instanceof List<?>;` enough to verify `List<List<String>>`?

No. You must check that each outer element is `List<?>` and all elements of each sublist are `String`.

**Question 7.** How does `String[]` differ from `List<String>` in runtime checking capability?

`String[]` retains the runtime component type `String`; `List<String>` has no separate runtime class carrying the `String` type argument that would allow `instanceof List<String>` as a check on an untyped `Object`.

## 17. Application rule

```text
Input Object
    |
    v
instanceof List<?> ?
    | no -> reject input
    | yes
    v
Iterate over every element
    | wrong type encountered -> reject / return false
    | all valid
    v
If only an answer is needed -> true
If a trustworthy List<T> is needed -> cast each element and create an appropriate copy
```

**Conclusion:** `instanceof List<?>` only checks whether **the overall object** is a list. When the contract requires **every element** to have a specific type, Java must inspect the actual elements or rely on a data source that already guarantees the contract. Type erasure prevents a type argument like `String` from being verified directly via the runtime class of `List`. Distinguish outer checks, per-element checks, and creating a validated copy; and explicitly specify how empty lists, nulls, nested data, and mutation are handled.