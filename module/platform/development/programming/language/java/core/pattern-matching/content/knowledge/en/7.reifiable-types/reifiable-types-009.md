# Avoiding Unchecked Casts in Java Pattern Code

## 1. The Problem: Matching the Collection Type Does Not Mean Matching the Element Type

In Java, **pattern matching for instanceof** lets you test an object and bind a type-checked variable in the same expression. For regular types, this directly replaces the **instanceof → cast** pattern:

~~~java
static String describe(Object value) {
    if (value instanceof String text) {
        return text.strip();
    }
    return "not a String";
}
~~~

However, **generics** have an important limitation: the JVM generally does not store type arguments such as **String** or **Integer** of **List<String>**, due to **type erasure**. An object can be checked to be a **List**, but that does not prove all of its elements are **String**. If you create a **List<String>** variable using an unchecked cast, the program may compile with a warning and fail when reading an element.

The goal of this article is to replace **unchecked casts** with approaches that have type evidence: **appropriate type patterns, per-value checks, statically typed APIs, and copying verified data**. The main examples run on **Java 17+**.

## 2. Checked Casts, Unchecked Casts, and When Failures Happen

A **checked cast** is a cast whose compatibility can actually be verified at runtime, such as from **Object** to **String**:

~~~java
Object value = "Java";
String text = (String) value; // Runtime check: the value is actually a String
~~~

If **value** holds an **Integer**, this cast compiles but throws **ClassCastException** right at the cast. With the pattern **value instanceof String text**, the branch only executes when the match succeeds; no manual cast is needed.

An **unchecked cast** occurs when the compiler cannot fully prove the correctness of the generic type arguments. The following example is for analysis only and should not be used in a safe production program:

~~~java
Object input = java.util.List.of(1, 2);
@SuppressWarnings("unchecked")
java.util.List<String> strings = (java.util.List<String>) input;

// A ClassCastException may occur when reading an element as String.
System.out.println(strings.get(0).length());
~~~

At runtime, this cast to a generic type mainly checks whether the object is a **List**; it **does not verify** that the elements are strings. Therefore, the cast can succeed initially, but when the code uses **strings.get(0)** as a **String**, the type check inserted at the read site encounters an **Integer** element and causes a **ClassCastException**.

If you remove the **@SuppressWarnings("unchecked")** annotation, the compiler emits an *unchecked cast* warning. That warning indicates that part of the **List<String>** type promise has not been proven. **SuppressWarnings** only hides the diagnostic; it performs no runtime check and does not make the data any safer.

## 3. Reifiable Types: What Does the JVM Know About Generic Types?

A **reifiable** type is a type that retains enough information so that its type representation can be determined at runtime. Key cases when using **instanceof**:

| Type | What can be checked at runtime | Notes |
| --- | --- | --- |
| **String** | Whether the object is a String | Has full class type information |
| **List<?>** | Whether the object is a List | Element type is unknown |
| **Map<?, ?>** | Whether the object is a Map | Key/value types are unknown |
| **List** (raw type) | Whether the object is a List | Loses compile-time generic checks |
| **String[]** | Whether the object is a String array | Arrays retain element type information |
| **List<String>** | Cannot confirm the String type argument from just an Object | Generic element type is erased |
| **Map<String, Integer>** | Cannot confirm both type arguments from just Object | Requires checking entries or having other type evidence |

A common and safe type pattern at an untyped data boundary:

~~~java
if (input instanceof java.util.List<?> elements) {
    System.out.println(elements.size());
}
~~~

The variable **elements** has type **List<?>**. You can call **size()**, iterate over elements as **Object**, or perform other operations that do not need to know the component type. You must **not** treat an arbitrary element as **String** without checking it first.

An invalid example when the source only has type **Object**:

~~~java
Object input = java.util.List.of("A", "B");

// Compile error: cannot check the String type argument from Object.
// if (input instanceof java.util.List<String> elements) { ... }
~~~

**A subtlety in Java 16+:** not every **instanceof** containing a parameterized type is forbidden. If the source's static type already carries the required generic information, the compiler can validate a more specific type check, for example:

~~~java
java.util.List<String> known = new java.util.ArrayList<>();
if (known instanceof java.util.ArrayList<String> arrayList) {
    System.out.println(arrayList.size());
}
~~~

This case is valid in Java 17 because **List<String>** on the left-hand side already supplies the element type constraint, and the pattern only verifies the concrete **ArrayList** implementation. **instanceof** does not inspect the contents of each element on its own. Conversely, from an unproven **Object** or **List<?>**, you cannot infer **List<String>** solely from the collection class name.

The full rule is that **the source type must be downcast-compatible with the pattern type, and the check must be provably safe by the compiler**. You should not oversimplify this as "Java always forbids all parameterized types in instanceof."

## 4. Why a Pattern Does Not Make an Unchecked Cast Safe

Consider the following code:

~~~java
static void unsafe(Object input) {
    if (input instanceof java.util.List<?> list) {
        // Unchecked warning: the String element type is not proven.
        @SuppressWarnings("unchecked")
        java.util.List<String> strings =
                (java.util.List<String>) list;

        // A non-String element can cause a ClassCastException.
        System.out.println(strings.get(0).length());
    }
}
~~~

**instanceof List<?>** only confirms that the *outer shape* is a **List**. Casting **List<?> → List<String>** afterward is still an **unchecked cast**, because the JVM does not check each element against the generic type argument. Pattern matching eliminates one cast from **Object** to **List<?>**; it does not prove the type information removed by type erasure.

Another flawed fix is casting each element inside the loop:

~~~java
for (Object value : list) {
    String text = (String) value; // Checked cast; may throw an exception
    System.out.println(text.length());
}
~~~

This approach **has no unchecked cast**, but if the data has mixed types, it throws **ClassCastException**. When the input is untrusted or you want to return a controlled failure result, use **instanceof String text** for each element.

## 5. The Safe Approach: Check the Collection, Then Check Each Element

You can accept an **Object**, check that it is a **List<?>**, check that each element is a **String**, and then build a new list of type **List<String>**:

~~~java
static java.util.Optional<java.util.List<String>> readStrings(Object input) {
    if (!(input instanceof java.util.List<?> values)) {
        return java.util.Optional.empty();
    }

    java.util.List<String> checked = new java.util.ArrayList<>();
    for (Object value : values) {
        if (!(value instanceof String text)) {
            return java.util.Optional.empty();
        }
        checked.add(text);
    }
    return java.util.Optional.of(java.util.List.copyOf(checked));
}
~~~

This is **an illustrative method**; a complete program with **main** is in the next section.

The chain of type evidence works as follows:

1. **input instanceof List<?> values**: verifies that the input is a non-**null** list, though without element type information yet.
2. **for (Object value : values)**: reads each element under the safe type **Object**.
3. **value instanceof String text**: if an element is not a **String** (including **null**), returns **Optional.empty()**.
4. **checked.add(text)**: the compiler knows **text** is a **String**, so adding it to **List<String>** requires no cast.
5. **List.copyOf(checked)**: returns an unmodifiable list built from the verified values. This avoids exposing the unverified source list under an overly strong generic type.

This article chooses to **reject the entire list if any element has the wrong type or is null**. That is a specific data policy, not a mandatory Java requirement: another application might choose to return a detailed error, skip invalid elements, or allow null using a different result structure. Make the policy explicit so data is not silently altered.

Do not mistake **List.copyOf** for a generic type checker: the type verification happens in the loop. **copyOf** mainly produces an unmodifiable result that does not alias the source list; it rejects null elements, and here null has already been filtered out.

## 6. Complete Java 17 Example: List, Map, and Class<T>

Save the full program as **SafePatternCollections.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

public class SafePatternCollections {
    static Optional<List<String>> readStrings(Object input) {
        if (!(input instanceof List<?> values)) {
            return Optional.empty();
        }

        List<String> result = new ArrayList<>();
        for (Object value : values) {
            if (!(value instanceof String text)) {
                return Optional.empty();
            }
            result.add(text);
        }
        return Optional.of(List.copyOf(result));
    }

    static <T> Optional<List<T>> checkedList(
            Object input, Class<T> elementType) {
        if (!(input instanceof List<?> values)) {
            return Optional.empty();
        }

        List<T> result = new ArrayList<>();
        for (Object value : values) {
            if (!elementType.isInstance(value)) {
                return Optional.empty();
            }
            result.add(elementType.cast(value));
        }
        return Optional.of(List.copyOf(result));
    }

    static Optional<Map<String, Integer>> readCounts(Object input) {
        if (!(input instanceof Map<?, ?> raw)) {
            return Optional.empty();
        }

        Map<String, Integer> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : raw.entrySet()) {
            if (!(entry.getKey() instanceof String key)
                    || !(entry.getValue() instanceof Integer count)) {
                return Optional.empty();
            }
            result.put(key, count);
        }
        return Optional.of(Map.copyOf(result));
    }

    public static void main(String[] args) {
        System.out.println(
                readStrings(List.of("red", "blue")).orElseThrow());
        System.out.println(
                readStrings(List.of("red", 7)).isPresent());
        System.out.println(
                readStrings(Arrays.asList("red", null)).isPresent());
        System.out.println(readStrings(null).isPresent());

        System.out.println(
                checkedList(List.of(4, 8), Integer.class).orElseThrow());
        System.out.println(
                checkedList(List.of(4, "eight"), Integer.class).isPresent());

        System.out.println(
                readCounts(Map.of("apples", 2)).orElseThrow().get("apples"));
        System.out.println(
                readCounts(Map.of(99, "wrong")).isPresent());
    }
}
~~~

Compile on **JDK 17+** with unchecked and raw-type warnings enabled:

~~~bash
javac -encoding UTF-8 -Xlint:unchecked,rawtypes SafePatternCollections.java
java SafePatternCollections
~~~

Exact output:

~~~text
[red, blue]
false
false
false
[4, 8]
false
2
false
~~~

**Step-by-step explanation:**

- The list **["red", "blue"]** passes per-element type checking and returns a safe **List<String>**.
- The list containing **7** is rejected; there is no blind cast and no **ClassCastException** just from encountering a non-**String** element.
- **Arrays.asList("red", null)** creates a list with a null element. **null instanceof String** is **false**, so the result is **Optional.empty()** under the chosen policy.
- **input == null** itself does not match **List<?>**, returning an empty result.
- **checkedList** accepts **Integer.class**; it checks **Class.isInstance** first and then uses **Class.cast** to bind the value to **T**. With **[4, 8]** it succeeds; with **[4, "eight"]** it fails in a controlled way.
- **readCounts** checks the types of both every key and every value in **Map<?, ?>**. The map with key **"apples"** and value **2** is accepted; the map with an **Integer** key and **String** value is rejected.

The program contains no **unchecked casts** or raw collection declarations. **-Xlint:unchecked,rawtypes** produces no warnings from these operations. **Class.cast** is a checked cast using a **Class<T>** class token, not an unchecked cast to a generic parameter that the runtime cannot verify.

One technical detail: **Map.copyOf** does not guarantee iteration order; the example only looks up the value by key **"apples"**, so the output is stable. If your application needs ordering, choose an appropriate API and return type contract instead of relying on the order of **Map.copyOf**.

## 7. What Can Class<T> Solve, and What Can It Not?

A general-purpose method:

~~~java
static <T> java.util.Optional<T> checkedValue(
        Object input, Class<T> type) {
    return type.isInstance(input)
            ? java.util.Optional.of(type.cast(input))
            : java.util.Optional.empty();
}
~~~

This is an **illustrative method snippet**, not a standalone program. With **String.class** or **Integer.class**, the type token allows the runtime to verify that an object is an instance of the corresponding class. **isInstance(null)** returns **false**, so **Optional.of(...)** only receives a verified non-null value.

However, **String.class** provides a token for **String**, whereas **List<String>.class** does not exist in Java. Using **List.class** only checks the list itself, not that its elements are **String**. That is why **checkedList(..., Class<T>)** combines a class token with a loop that checks each element.

For nested generics such as **List<List<String>>**, a **Class<List>** token is not enough to validate the entire structure. You must check the outer list layer, each inner list, and each **String** element, or use a dedicated decoder/validator with a defined data contract.

**Class<T>** is useful for checking reference types that can be represented by a class token; it does not replace checking nested generic structures or per-element business constraints.

## 8. Common Code Patterns: Which Solution Should You Choose?

| Actual input | Preferred way to write it | Guarantee level |
| --- | --- | --- |
| **Object** that may be a string | **input instanceof String text** | Guaranteed to be a String when matched |
| **Object** that may be a list | **input instanceof List<?> values** | Guaranteed collection type; elements still unknown |
| **Object** that may be **List<String>** | **List<?>** + check **String** per element + build new **List<String>** | Guaranteed type for every accepted element |
| **Object** that may be **Map<String,Integer>** | **Map<?,?>** + check each key/value + build typed Map | Guaranteed checked keys and values |
| **Object** that must become caller-chosen **T** | **Class<T>.isInstance** then **Class<T>.cast** | Checks T's class via class token |
| Already received **List<String>** from a trusted typed API | Use **List<String>** directly | Type contract is the API/caller's responsibility |
| Receiving JSON, reflection, or raw library data | Parse/validate into a DTO or typed structure at the boundary | Clear type contract after validation |
| Only know it is a **List** and need to count elements | **List<?>** + **size()** | No need to cast to List<String> |

The goal is not to turn every collection into **List<String>**. If an algorithm only counts elements, keeping **List<?>** is enough. Only when you need to process strings do you need to prove the elements are actually **String**.

## 9. Where Can Unchecked Casts Hide?

### 9.1. Casting List<?> to List<String>

~~~java
// Unchecked warning, even though the list has already been checked as List<?>.
List<String> names = (List<String>) unknownList;
~~~

Keep it as **List<?>**, then check each element and build a typed list. Casting to a raw **List** does not prove generics either; raw types often suppress type-safety warnings at call sites.

### 9.2. Passing Raw Types Across API Boundaries

~~~java
// Weak design example: raw type, discarding generic information from the result.
static java.util.List legacyValues() {
    return java.util.List.of("A", 123);
}
~~~

If a caller receives it as **List<String>**, an **unchecked conversion** can occur. For new APIs, prefer **List<String>** if the elements are truly only strings, **List<?>** if the element type is unknown, or a concrete data model if mixed types are intentional.

### 9.3. Hiding Warnings With Annotations Without Proving Invariants

~~~java
@SuppressWarnings("unchecked")
List<String> names = (List<String>) arbitraryInput;
~~~

Do not use annotations as a type fix. If you must integrate with a legacy non-generic library, isolate the unchecked cast, verify the data with tests/validation or maintain a clear invariant, and document exactly why the cast is safe. Ideally, update the API contract or build a typed copy from verified values.

### 9.4. Assuming Collections.checkedList Verifies Existing Data

**Collections.checkedList(list, String.class)** provides a type-checked view for insertions made through that view. It does not scan elements already in the source list and does not block modifications made through another alias of the underlying list. Therefore, it must not be treated as proof that an existing raw list contains only **String** values. To verify existing contents, you still have to iterate and check.

### 9.5. Forgetting Nulls and Concurrent Mutation During Validation

**null** does not match an **instanceof** type pattern. The examples choose to reject null and any invalid input; another project might need detailed error statuses. Iterating over a collection that is being modified concurrently can cause inconsistent behavior or **ConcurrentModificationException**; if data is shared across threads, ensure proper synchronization or take an appropriate snapshot before and during validation. **List.copyOf** only builds the result after reading/checking finishes; it does not fix concurrency issues that occur during that process.

## 10. How to Refactor From Blind Casts to Pattern Code

Suppose legacy code retrieves a list from an API returning **Object**:

~~~java
static int countLongNames(Object response) {
    @SuppressWarnings("unchecked")
    List<String> names = (List<String>) response;
    return (int) names.stream().filter(s -> s.length() >= 3).count();
}
~~~

This version both has an unchecked cast and can fail when **response** is not a List or contains a non-String element. A safe Java 17 approach:

~~~java
static int countLongNames(Object response) {
    if (!(response instanceof List<?> values)) {
        return 0;
    }
    int count = 0;
    for (Object item : values) {
        if (item instanceof String name && name.length() >= 3) {
            count++;
        }
    }
    return count;
}
~~~

**Both methods are illustrative snippets in a context with java.util.List imported**, not a full program with **main**. The new version adopts a policy of **skipping non-String elements**; the old version could throw an exception. If the contract requires **rejecting the whole list on a type mismatch**, choose a validate-then-fail approach like **readStrings** in Section 5. **Safe refactoring** is not just removing warnings; it also means intentionally deciding whether to preserve or change error behavior.

A practical workflow:

1. Identify the data source and its **static type**: **Object**, **List<?>**, raw **List**, JSON, reflection, or a typed API.
2. Specify the **expected data contract**: what element types are expected, whether null is allowed, and whether invalid elements should fail or be skipped.
3. Choose a sensible reifiable type pattern for the outer structure, such as **List<?>** or **Map<?, ?>**.
4. Check each element, key/value, or nested structure using type patterns and/or **Class.isInstance**.
5. Build a new typed result using compiler-checked additions. Avoid generic casts of the entire collection.
6. Enable **-Xlint:unchecked,rawtypes** and review any remaining warnings; test valid, invalid, and null inputs.
7. Preserve the chosen business contract and error handling, especially when replacing legacy code.

## 11. Self-Check Exercises

**Exercise 1.** Given **Object value = List.of("a", 3)**, can **value instanceof List<?> xs** return **true**? Yes, because the runtime object is a List. Can you assign **List<String> names = (List<String>) xs** without a warning? No; the element type has not been verified.

**Exercise 2.** Given **Object value = List.of("a", "b")**, is **value instanceof List<String> xs** valid in Java 17? No, because the static type **Object** does not prove the List's **String** type argument. To obtain **List<String>**, either receive it typed directly from the API or check the elements and build a new result.

**Exercise 3.** Given **List<String> known = new ArrayList<>()**, is **known instanceof ArrayList<String> xs** valid? Yes in Java 17: here the static type **List<String>** supplies the generic information, and the check refines the implementation to **ArrayList**. That does not mean an arbitrary **Object** can be tested directly as **List<String>**.

**Exercise 4.** Would a list **["a", null]** be accepted by **readStrings**? No. **null** does not match the **String** pattern; the example intentionally returns **Optional.empty()**.

**Exercise 5.** Can **Class<String>.cast** be used to verify **List<String>** in a single call? No. **String.class** only checks that a single object is a String; you must iterate over the entire list or use a validator for complex structures.

## 12. References

- [JLS 17 §4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7): which types retain sufficient information at runtime.
- [JLS 17 §5.5 — Casting Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.5): checked and unchecked conversions.
- [JLS 17 §14.30.1 — Kinds of Patterns](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30.1): compatibility rules for type patterns.
- [JLS 17 §15.20.2 — instanceof](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): type comparisons, pattern matching, and examples of refined generic types since Java 16.
- [Java SE 17 API — Class.cast / isInstance](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): checking values through a class token.

**Conclusion:** **instanceof List<?>** proves that a value is a list, while **List<String>** promises that its elements can be used as String. To uphold that promise at untrusted boundaries, check each element and build a typed result, or rely on an API that already provides accurate generic type information. Pattern matching eliminates unnecessary casts, but it does not erase the limits of type erasure; understanding this boundary is the real way to avoid unchecked casts.
